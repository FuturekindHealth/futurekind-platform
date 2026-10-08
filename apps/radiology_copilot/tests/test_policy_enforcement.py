"""Policy enforcement, from the application's side of the boundary.

The Gateway decides policy; this application *refuses to work without it*. Every
case here is a Gateway that answered while its policy was not the one a radiology
draft needs — a downgrade that happened, an audit line that will not be written, a
risk level that was lowered — and the behaviour under test is the refusal.

The ordering matters as much as the outcome: governance is read before the answer
is parsed, so a broken policy never gets dressed up as a usable report.
"""

from __future__ import annotations

import asyncio

import pytest
from pydantic import ValidationError

from futurekind_radiology.errors import (
    DegradedAnswerError,
    GatewayRequestError,
    PolicyNotEnforcedError,
    RadiologyError,
    SkillMismatchError,
)
from futurekind_radiology.report import RadiologyReport
from tests.conftest import RADIOLOGY_POLICY, completion, fixture_text, make_copilot, submission

ANSWER = fixture_text("normal_ct_head.json")


def draft_with(**overrides: object) -> RadiologyReport:
    copilot, _ = make_copilot(completion(ANSWER, **overrides))
    return asyncio.run(copilot.draft(submission()))


def policy_with(**changes: object) -> dict[str, object]:
    policy = dict(RADIOLOGY_POLICY)
    policy.update(changes)
    return policy


@pytest.mark.parametrize(
    ("field", "relaxed"),
    [
        ("audit_required", False),
        ("allow_downgrade", True),
        ("approval_required", True),
    ],
)
def test_a_relaxed_governance_field_stops_the_draft(field: str, relaxed: object) -> None:
    with pytest.raises(PolicyNotEnforcedError) as caught:
        draft_with(policy=policy_with(**{field: relaxed}))

    assert caught.value.code == "policy_not_enforced"
    breached = caught.value.details["breached"]
    assert [entry["field"] for entry in breached] == [field]
    assert breached[0]["reported"] is relaxed


@pytest.mark.parametrize("risk", ["low", "moderate", "unspecified"])
def test_a_lower_risk_level_is_not_treated_as_a_stricter_one(risk: str) -> None:
    with pytest.raises(PolicyNotEnforcedError) as caught:
        draft_with(policy=policy_with(clinical_risk=risk))

    assert caught.value.details["clinical_risk"] == risk


def test_critical_risk_is_accepted() -> None:
    """An installation may raise the bar above what this application assumed."""
    report = draft_with(policy=policy_with(clinical_risk="critical"))

    assert report.policy.clinical_risk == "critical"


def test_a_degraded_answer_is_refused_even_though_it_is_readable() -> None:
    """The text would parse into a perfect report. It is still refused.

    ``allow_downgrade: false`` makes this unreachable in a correct deployment,
    which is exactly why the application checks rather than assumes it (P13: a
    substitution may not be silent).
    """
    with pytest.raises(DegradedAnswerError) as caught:
        draft_with(degraded=True, attempts=2, model="ollama/gemma3:12b")

    assert caught.value.code == "degraded_answer"
    assert caught.value.details["model"] == "ollama/gemma3:12b"
    assert caught.value.details["attempts"] == 2


def test_a_completion_from_another_skill_is_not_a_radiology_draft() -> None:
    with pytest.raises(SkillMismatchError) as caught:
        draft_with(skill="clinical-chat")

    assert caught.value.code == "skill_mismatch"


def test_a_policy_reported_incompletely_is_a_refusal_not_a_guess() -> None:
    """No silent default for a governance field. If the Gateway did not say it,
    this application does not know the rule the report was written under."""
    partial = {key: value for key, value in RADIOLOGY_POLICY.items() if key != "audit_required"}

    with pytest.raises(GatewayRequestError) as caught:
        draft_with(policy=partial)

    assert caught.value.details["missing"] == ["audit_required"]
    assert caught.value.request_id == "fk-test-request-1"


def test_governance_is_checked_before_the_answer_is_read() -> None:
    """A prose answer under a broken policy must report the policy.

    The parse failure is the less important fact, and a clinician told "the model
    answered in prose" would go and shorten their dictation instead of calling the
    person who owns ``models.yaml``.
    """
    copilot, _ = make_copilot(
        completion(fixture_text("prose_answer.txt"), policy=policy_with(allow_downgrade=True))
    )

    with pytest.raises(PolicyNotEnforcedError):
        asyncio.run(copilot.draft(submission()))


def test_an_upstream_refusal_is_carried_through_unchanged() -> None:
    """A 403 from the Gateway is the platform's answer, not this application's."""
    upstream = GatewayRequestError(
        "This skill requires an approval the Gateway cannot verify.",
        upstream_code="approval_required",
        request_id="fk-test-request-9",
    )
    copilot, _ = make_copilot(upstream)

    with pytest.raises(RadiologyError) as caught:
        asyncio.run(copilot.draft(submission()))

    assert caught.value.details["upstream_code"] == "approval_required"
    assert caught.value.request_id == "fk-test-request-9"


# -- the one limit this application owns ---------------------------------------------------------


def test_an_absurdly_long_dictation_is_refused_before_the_gateway() -> None:
    """A bound on what a clinician may submit, so a paste of a whole thesis is
    refused on the spot rather than travelling into the platform."""
    with pytest.raises(ValidationError):
        submission(findings="middle meningeal artery " * 1_000)


def test_a_study_without_findings_is_refused_before_the_gateway() -> None:
    with pytest.raises(ValidationError):
        submission(findings="")


def test_an_unknown_input_field_is_refused_not_ignored() -> None:
    """Silently dropping a typo'd field would let a clinician believe they had
    supplied a technique they had not."""
    with pytest.raises(ValidationError):
        submission(tequnue="CT 5 mm")
