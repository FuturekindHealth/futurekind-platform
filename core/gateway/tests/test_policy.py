"""Unit tests for the declarative policy layer.

Two halves: the rules a policy must satisfy before it can be loaded at all, and
the arithmetic of what a loaded policy does to a request. Both live here rather
than spread across the catalogue and API suites, because the point of the layer
is that these decisions exist in exactly one place — and one place is testable.
"""

from __future__ import annotations

from typing import Any

import pytest

from futurekind_gateway.catalog import ModelCatalog
from futurekind_gateway.errors import (
    ApprovalRequiredError,
    CatalogError,
    ValidationError,
)
from futurekind_gateway.policy import (
    CLINICAL_RISK_LEVELS,
    DECLARABLE_RISK_LEVELS,
    DEFAULT_POLICY,
    POLICY_KEYS,
    SkillPolicy,
    check_approval,
    check_request,
    declared_policy,
    limits_for,
    resolve_policy,
)
from tests.conftest import make_policy_catalog, make_settings


def load_policy(declared: dict[str, Any], *, owner: str = "s") -> SkillPolicy:
    """Validate one skill's declared policy exactly as the loader does."""
    return resolve_policy(owner, declared_policy(owner, declared))


def skills_with(policy: dict[str, Any]) -> dict[str, Any]:
    """A minimal catalogue whose one skill declares `policy`."""
    return {
        "models": {"default": {"provider": "p", "model": "m"}},
        "skills": {"s": {"capability": "default", **policy}},
    }


def check(policy: SkillPolicy = DEFAULT_POLICY, **changes: Any) -> None:
    """Run the request check with a baseline that passes, changing one thing."""
    arguments: dict[str, Any] = {
        "skill": "s",
        "message_count": 1,
        "longest_message_chars": 5,
        "requested_max_tokens": None,
        "settings": make_settings(),
    }
    arguments.update(changes)
    check_request(policy, **arguments)


# -- the schema --------------------------------------------------------------------------------


def test_every_policy_key_is_a_field_and_a_documented_key() -> None:
    """A key in the vocabulary list that is not a field is a typo that loads happily."""
    assert set(SkillPolicy.to_dict(DEFAULT_POLICY)) == POLICY_KEYS


def test_the_default_policy_is_the_inert_one() -> None:
    """A policy nobody declared must not change what the Gateway already did.

    This is the guard on that claim: if a default flips here, every request that
    names no skill changes behaviour without any operator editing any file.
    """
    assert DEFAULT_POLICY.clinical_risk == "unspecified"
    assert DEFAULT_POLICY.approval_required is False
    assert DEFAULT_POLICY.audit_required is True
    assert DEFAULT_POLICY.allow_downgrade is True
    assert DEFAULT_POLICY.to_dict()["max_messages"] is None


def test_an_escalated_flag_is_derived_from_the_risk_level_not_declared() -> None:
    assert SkillPolicy(clinical_risk="high").escalated is True
    assert SkillPolicy(clinical_risk="critical").escalated is True
    assert SkillPolicy(clinical_risk="low").escalated is False
    assert DEFAULT_POLICY.escalated is False


def test_the_public_policy_is_governance_only() -> None:
    """Limits are deployment tuning; publishing them teaches a caller to hit the ceiling."""
    policy = load_policy({"clinical_risk": "low", "max_messages": 4, "request_timeout_seconds": 3})

    assert set(policy.to_public_dict()) == {
        "clinical_risk",
        "approval_required",
        "audit_required",
        "allow_downgrade",
    }
    assert "max_messages" not in policy.to_public_dict()


# -- validation --------------------------------------------------------------------------------


def test_a_skill_must_declare_its_clinical_risk() -> None:
    """The one mandatory field: an unassessed clinical skill is the failure to prevent."""
    with pytest.raises(CatalogError, match="must declare clinical_risk"):
        ModelCatalog.from_document(skills_with({}))


@pytest.mark.parametrize(
    ("risk", "couplings"),
    [
        ("low", {}),
        ("moderate", {}),
        ("high", {"allow_downgrade": False}),
        ("critical", {"allow_downgrade": False, "approval_required": True}),
    ],
)
def test_each_declarable_risk_level_loads_when_its_couplings_are_stated(
    risk: str, couplings: dict[str, Any]
) -> None:
    assert load_policy({"clinical_risk": risk, **couplings}).clinical_risk == risk


def test_risk_is_written_case_insensitively_and_stored_canonically() -> None:
    assert load_policy({"clinical_risk": " MODERATE "}).clinical_risk == "moderate"


@pytest.mark.parametrize(
    "risk",
    ["", "serious", "unspecified", "high-2", "moderate-ish", 4],
    ids=["blank", "unknown", "not-for-a-skill", "suffix", "typo", "number"],
)
def test_an_unknown_risk_level_is_refused(risk: Any) -> None:
    with pytest.raises(CatalogError, match="clinical_risk"):
        load_policy({"clinical_risk": risk})


def test_the_risk_levels_are_an_ordered_ladder() -> None:
    """Documentation and dashboards quote this order, so it must not be re-sorted."""
    assert CLINICAL_RISK_LEVELS == ("unspecified", "low", "moderate", "high", "critical")
    assert CLINICAL_RISK_LEVELS[1:] == DECLARABLE_RISK_LEVELS


def test_only_unspecified_is_not_declarable() -> None:
    """`unspecified` is what the Gateway gives a request nobody assessed. An operator
    may not write it into a skill and call that an assessment."""
    assert "unspecified" not in DECLARABLE_RISK_LEVELS


def test_a_high_risk_skill_may_not_be_unaudited() -> None:
    with pytest.raises(CatalogError, match="audit_required: false"):
        load_policy({"clinical_risk": "high", "allow_downgrade": False, "audit_required": False})


def test_a_high_risk_skill_may_not_be_downgradable_by_default() -> None:
    """Suppressing the chain is forced rather than suggested, because the floor is True."""
    with pytest.raises(CatalogError, match="allow_downgrade: false"):
        load_policy({"clinical_risk": "high"})
    with pytest.raises(CatalogError, match="allow_downgrade: false"):
        load_policy({"clinical_risk": "critical", "approval_required": True})


def test_a_critical_skill_must_be_approved() -> None:
    with pytest.raises(CatalogError, match="approval_required: false"):
        load_policy({"clinical_risk": "critical", "allow_downgrade": False})


def test_the_only_legal_critical_skill_is_the_one_that_states_every_coupling() -> None:
    policy = load_policy(
        {
            "clinical_risk": "critical",
            "allow_downgrade": False,
            "audit_required": True,
            "approval_required": True,
        }
    )

    assert policy.escalated and policy.approval_required and not policy.allow_downgrade


@pytest.mark.parametrize("key", ["approval_required", "audit_required", "allow_downgrade"])
def test_a_policy_flag_has_to_be_a_boolean(key: str) -> None:
    for value in ("yes", "true", 1, None):
        with pytest.raises(CatalogError, match=f"'{key}' must be true or false"):
            load_policy({"clinical_risk": "low", key: value})


@pytest.mark.parametrize(
    "key", ["max_messages", "max_content_chars", "max_completion_tokens"]
)
def test_a_policy_limit_has_to_be_a_positive_whole_number(key: str) -> None:
    for value in (0, -1, "12", 1.5, True):
        with pytest.raises(CatalogError, match="positive whole number"):
            load_policy({"clinical_risk": "low", key: value})


def test_a_policy_timeout_has_to_be_a_plausible_number_of_seconds() -> None:
    for value in (0, -5, "12s", True):
        with pytest.raises(CatalogError, match="timeout"):
            load_policy({"clinical_risk": "low", "request_timeout_seconds": value})
    with pytest.raises(CatalogError, match="between 0 and"):
        load_policy({"clinical_risk": "low", "request_timeout_seconds": 4000})


def test_an_unknown_policy_key_is_refused_by_name() -> None:
    """A typo in a governance rule must not read as 'the operator did not ask for it'."""
    with pytest.raises(CatalogError, match="unsupported policy field"):
        declared_policy("s", {"alow_downgrade": False})


def test_an_unsafe_policy_refuses_the_whole_catalogue_not_just_that_skill() -> None:
    """Fail at startup: an operator must not discover this from an audit request."""
    with pytest.raises(CatalogError):
        ModelCatalog.from_document(skills_with({"clinical_risk": "high"}))


# -- the loader --------------------------------------------------------------------------------


def test_the_shipped_policy_loads_and_says_what_it_means() -> None:
    catalog = make_policy_catalog()

    assert catalog.require_skill("radiology-report").policy.allow_downgrade is False
    assert catalog.require_skill("radiology-report").policy.clinical_risk == "high"
    assert catalog.require_skill("critical-care-summary").policy.approval_required is True
    assert catalog.require_skill("patient-leaflet").policy.max_messages == 2
    assert catalog.require_skill("patient-leaflet").policy.audit_required is False


def test_a_capability_row_may_carry_the_alias_that_litellm_knows_it_by() -> None:
    catalog = make_policy_catalog()

    assert catalog.require("reasoning").alias == "fk-reasoning"
    assert catalog.require("retired").alias is None


def test_two_rows_sharing_one_alias_are_refused() -> None:
    """One alias meaning two capabilities is a silent misroute carrying two policies."""
    with pytest.raises(CatalogError, match="alias 'shared'"):
        ModelCatalog.from_document(
            {
                "models": {
                    "a": {"provider": "p", "model": "m", "alias": "shared"},
                    "b": {"provider": "p", "model": "n", "alias": "shared"},
                }
            }
        )


@pytest.mark.parametrize("blank", ["", "   "], ids=["empty", "whitespace"])
def test_a_blank_alias_is_refused(blank: str) -> None:
    with pytest.raises(CatalogError, match="non-empty string 'alias'"):
        ModelCatalog.from_document(
            {"models": {"a": {"provider": "p", "model": "m", "alias": blank}}}
        )


def test_a_skill_may_not_declare_an_alias() -> None:
    """An alias names a routing target, not an intent. On a skill it would be a model
    selector wearing a governance name."""
    with pytest.raises(CatalogError, match="unsupported field"):
        ModelCatalog.from_document(
            {
                "models": {"default": {"provider": "p", "model": "m", "alias": "fk-a"}},
                "skills": {
                    "s": {"capability": "default", "clinical_risk": "low", "alias": "fk-a"}
                },
            }
        )


def test_an_absent_alias_stays_none_rather_than_becoming_the_capability_name() -> None:
    """Deriving one would invent a LiteLLM name no operator ever wrote."""
    catalog = ModelCatalog.from_document({"models": {"default": {"provider": "p", "model": "m"}}})

    assert catalog.require("default").alias is None


# -- enforcement -------------------------------------------------------------------------------


def test_a_policy_tightens_a_platform_limit_and_can_never_raise_it() -> None:
    settings = make_settings(
        max_messages=100, max_content_chars=32_000, max_completion_tokens=8192
    )
    policy = SkillPolicy(
        clinical_risk="low",
        max_messages=10,
        max_content_chars=999_999,
        max_completion_tokens=512,
    )

    limits = limits_for(policy, settings)

    assert limits.max_messages == 10
    assert limits.max_content_chars == 32_000
    assert limits.max_completion_tokens == 512


def test_a_policy_that_declares_no_limit_leaves_the_platform_alone() -> None:
    settings = make_settings()
    limits = limits_for(DEFAULT_POLICY, settings)

    assert limits.max_messages == settings.max_messages
    assert limits.max_content_chars == settings.max_content_chars
    assert limits.max_completion_tokens == settings.max_completion_tokens
    assert limits.request_timeout_seconds == settings.request_timeout_seconds


def test_a_policy_timeout_shortens_the_wait_and_cannot_lengthen_it() -> None:
    settings = make_settings(request_timeout_seconds=5.0)

    assert limits_for(
        SkillPolicy(request_timeout_seconds=2.5), settings
    ).request_timeout_seconds == 2.5
    assert limits_for(
        SkillPolicy(request_timeout_seconds=600), settings
    ).request_timeout_seconds == 5.0


def test_a_request_inside_every_ceiling_passes_quietly() -> None:
    check()
    check(message_count=100, longest_message_chars=32_000, requested_max_tokens=8192)


def test_a_skill_specific_message_ceiling_is_reported_with_its_rule_and_risk() -> None:
    policy = load_policy({"clinical_risk": "high", "allow_downgrade": False, "max_messages": 2})

    with pytest.raises(ValidationError) as caught:
        check(policy, skill="radiology-report", message_count=3)

    assert caught.value.details["limit"] == "max_messages"
    assert caught.value.details["allowed"] == 2
    assert caught.value.details["skill"] == "radiology-report"
    assert caught.value.details["clinical_risk"] == "high"


def test_a_skill_specific_character_ceiling_is_enforced() -> None:
    policy = load_policy({"clinical_risk": "low", "max_content_chars": 10})

    with pytest.raises(ValidationError) as caught:
        check(policy, longest_message_chars=11)

    assert caught.value.details["limit"] == "max_content_chars"


def test_a_skill_specific_token_ceiling_is_enforced_below_the_platform_one() -> None:
    policy = load_policy({"clinical_risk": "low", "max_completion_tokens": 64})

    with pytest.raises(ValidationError) as caught:
        check(policy, requested_max_tokens=4096)

    assert caught.value.details["limit"] == "max_completion_tokens"
    assert caught.value.details["allowed"] == 64


def test_an_unapproved_request_is_refused_before_any_model_is_named() -> None:
    with pytest.raises(ApprovalRequiredError) as caught:
        check_approval(SkillPolicy(clinical_risk="critical", approval_required=True), skill="s")

    assert caught.value.code == "approval_required"
    assert caught.value.status_code == 403
    assert caught.value.details["clinical_risk"] == "critical"
    assert "approvals service" in caught.value.details["hint"]


def test_the_approval_gate_is_checked_before_the_limits() -> None:
    """A request that is both unapproved and oversized is refused for the clinical
    reason, not the incidental one."""
    policy = load_policy(
        {
            "clinical_risk": "critical",
            "allow_downgrade": False,
            "approval_required": True,
            "max_messages": 1,
        }
    )
    with pytest.raises(ApprovalRequiredError):
        check(policy, message_count=50)


def test_a_policy_that_needs_no_approval_returns_immediately() -> None:
    assert check_approval(DEFAULT_POLICY, skill=None) is None
