"""Golden cases: six studies, drafted deterministically, checked field by field.

Each case feeds a stored model answer through the real workflow, against the study
that answer was written for, and asserts the whole document — the six sections, the
quality pass and confidence computed over them, and the metadata, provenance, skill
and policy that make the draft auditable. No model runs here; the answer is the
fixture, so the only thing these tests can fail on is this application's own
behaviour.

Three of the six are MRI brain, the workflow Sprint 9 exists to run. Their dictated
text comes from `docs/product/GOLDEN_DATASET.yaml` (N-04, E-17, C-16), so the golden
fixtures and the golden dataset are the same clinical material rather than two
versions of it.
"""

from __future__ import annotations

import asyncio

import pytest

from futurekind_radiology.errors import ModelOutputError, ReportTruncatedError
from futurekind_radiology.prompt import PROMPT_VERSION
from futurekind_radiology.report import MODEL_SECTION_KEYS
from tests.conftest import (
    FROZEN_STAMP,
    REQUIRED_OUTPUT,
    completion,
    fixture_text,
    golden,
    make_copilot,
    submission,
    submission_for,
)

GOLDEN_CASES = (
    "normal_ct_head.json",
    "hypertensive_bleed.json",
    "nph_hydrocephalus.json",
    "mri_brain_normal.json",
    "mri_brain_abscess.json",
    "mri_brain_epilepsy.json",
)


def draft(fixture: str, **completion_overrides: object):
    copilot, stub = make_copilot(completion(fixture_text(fixture), **completion_overrides))
    return asyncio.run(copilot.draft(submission_for(fixture))), stub


@pytest.mark.parametrize("fixture", GOLDEN_CASES)
def test_a_golden_study_drafts_the_whole_document(fixture: str) -> None:
    expected = golden(fixture)

    report, stub = draft(fixture)

    assert tuple(report.model_dump()) == REQUIRED_OUTPUT
    for key in MODEL_SECTION_KEYS:
        assert report.section(key) == expected[key]
    assert report.clinical_indication == submission_for(fixture).clinical_indication
    assert stub.last_request["skill"] == "radiology-report"


@pytest.mark.parametrize("fixture", GOLDEN_CASES)
def test_a_golden_draft_is_signed_without_the_checks_refusing_it(fixture: str) -> None:
    """The clinical material the product is built on must pass its own gates.

    A golden case that came back blocking would mean either the check is wrong or
    the reference report is — and both of those are worth a failing test, not a
    fixture nobody looks at again.
    """
    report, _ = draft(fixture)
    study = submission_for(fixture)

    assert report.quality.blocking == [], [finding.message for finding in report.quality.blocking]

    copilot, _ = make_copilot(completion(fixture_text(fixture)))
    signed = copilot.review(
        report, decision="signed", clinician="Dr A. Nair", submission=study
    )

    assert signed.is_signed
    assert signed.quality.checked_at == FROZEN_STAMP


def test_the_indication_in_the_report_is_the_clinicians_own_words() -> None:
    """The regression the live demonstration exposed.

    An answer that restates the indication with a different history is not allowed
    to become the document's indication: the reason a study was performed is the
    referrer's statement, and a draft that rewrites it has changed the question the
    radiologist answered.
    """
    report, _ = draft("wrapped_answer.txt")

    assert report.clinical_indication == submission().clinical_indication
    assert report.metadata.extra_sections == ["clinical_indication"]


def test_the_dictation_is_kept_beside_the_findings_it_became() -> None:
    """A reviewer comparing what they said with what the draft says needs both."""
    study = submission(findings="No haemorrhage. No midline shift.")
    copilot, _ = make_copilot(completion(fixture_text("normal_ct_head.json")))

    report = asyncio.run(copilot.draft(study))

    assert report.metadata.dictated_findings == "No haemorrhage. No midline shift."
    assert report.findings != report.metadata.dictated_findings


def test_the_draft_carries_the_study_and_the_moment_it_was_made() -> None:
    report, _ = draft("normal_ct_head.json")

    metadata = report.metadata
    assert metadata.study == "CT HEAD WITHOUT CONTRAST"
    assert metadata.modality == "CT"
    assert metadata.drafted_at == FROZEN_STAMP
    assert metadata.prompt_version == PROMPT_VERSION
    assert metadata.generator.startswith("futurekind-radiology-copilot/")
    assert metadata.review.state == "pending_review"
    assert metadata.review.clinician is None


def test_the_report_id_is_the_gateway_request_id_and_nothing_invented() -> None:
    """No identifier scheme of its own. ``DOMAIN_MODEL`` Q2 is explicit about why:
    an id format an application invents is a defect that outlives its convenience."""
    report, _ = draft("normal_ct_head.json")

    assert report.metadata.report_id == "fk-test-request-1"
    assert report.model_provenance.request_id == report.metadata.report_id


def test_the_provenance_is_the_gateways_own_report_of_what_ran() -> None:
    report, _ = draft("normal_ct_head.json")

    provenance = report.model_provenance
    assert provenance.model == "ollama/qwen3:14b"
    assert provenance.provider == "litellm"
    assert provenance.selected_by == "skill"
    assert provenance.attempts == 1
    assert provenance.degraded is False
    assert provenance.finish_reason == "stop"
    assert (provenance.prompt_tokens, provenance.completion_tokens) == (640, 210)
    assert provenance.total_tokens == 850
    assert provenance.latency_ms == 4200


def test_the_policy_is_reported_as_the_gateway_declared_it() -> None:
    report, _ = draft("normal_ct_head.json")

    assert report.skill.name == "radiology-report"
    assert report.skill.capability == "reasoning"
    assert report.policy.clinical_risk == "high"
    assert report.policy.audit_required is True
    assert report.policy.allow_downgrade is False
    assert report.policy.approval_required is False


def test_a_technique_the_department_supplied_reaches_the_model() -> None:
    """The prompt is the only place the acquisition parameters can travel."""
    copilot, stub = make_copilot(completion(fixture_text("nph_hydrocephalus.json")))

    asyncio.run(
        copilot.draft(
            submission(technique="MRI lumbar spine, 1.5T, no contrast.")
        )
    )

    user_turn = stub.last_request["messages"][1]["content"]
    assert "MRI lumbar spine, 1.5T, no contrast." in user_turn


def test_a_supplied_technique_wins_over_the_line_the_model_wrote() -> None:
    """Ownership, not preference.

    This answer says the technique was not provided, because the golden case was
    dictated without it. Where the department *did* supply the parameters, they are
    a fact the application holds and the model merely formats — so the submitted
    line is the document's, and the draft records who it came from.
    """
    copilot, _ = make_copilot(completion(fixture_text("normal_ct_head.json")))

    report = asyncio.run(
        copilot.draft(submission(technique="CT head with contrast, 1 mm axial acquisitions."))
    )

    assert report.technique == "CT head with contrast, 1 mm axial acquisitions."
    assert report.metadata.technique_from == "department"


def test_an_unsupplied_technique_stays_the_models_responsibility_to_declare() -> None:
    copilot, _ = make_copilot(completion(fixture_text("normal_ct_head.json")))

    report = asyncio.run(copilot.draft(submission()))

    assert report.technique == "Technique not provided."
    assert report.metadata.technique_from == "model"


def test_a_recommendation_of_none_is_a_legitimate_answer() -> None:
    """Empty is refused; "None." is a readable statement that nothing follows."""
    report, _ = draft("nph_hydrocephalus.json")

    assert report.recommendations == "None."


def test_the_draft_never_carries_a_patient_identifier() -> None:
    report, _ = draft("normal_ct_head.json")

    dumped = report.model_dump_json()
    for field in ("mrn", "patient_id", "patient_name", "hospital_number", "accession"):
        assert field not in dumped


def test_a_truncated_answer_produces_no_draft() -> None:
    """The section most likely to be cut is the last one, and a half-read impression
    looks like a whole one."""
    copilot, _ = make_copilot(
        completion(fixture_text("hypertensive_bleed.json"), finish_reason="length")
    )

    with pytest.raises(ReportTruncatedError) as caught:
        asyncio.run(copilot.draft(submission()))

    assert caught.value.retryable is True
    assert caught.value.request_id == "fk-test-request-1"


def test_a_prose_answer_produces_no_draft() -> None:
    copilot, _ = make_copilot(completion(fixture_text("prose_answer.txt")))

    with pytest.raises(ModelOutputError):
        asyncio.run(copilot.draft(submission()))


def test_the_conversation_is_two_turns_and_names_no_infrastructure() -> None:
    _, stub = draft("normal_ct_head.json")

    request = stub.last_request
    assert [message["role"] for message in request["messages"]] == ["system", "user"]
    assert request["temperature"] is None
    assert set(request) == {"skill", "messages", "temperature"}
