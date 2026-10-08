"""Unit tests for the model catalogue loader."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from futurekind_gateway.catalog import ModelCatalog, ModelEntry, Skill
from futurekind_gateway.errors import CatalogError, UnknownCapabilityError, UnknownSkillError
from tests.conftest import FAKE_CATALOG_DOCUMENT, REPO_CATALOG, make_catalog


def document(**overrides: Any) -> dict[str, Any]:
    merged = dict(FAKE_CATALOG_DOCUMENT)
    merged.update(overrides)
    return merged


def models(raw: dict[str, Any]) -> dict[str, Any]:
    return {"models": raw}


# -- the file that actually ships ----------------------------------------------------------


def test_the_shipped_catalogue_loads_and_describes_the_platform() -> None:
    catalog = ModelCatalog.load(REPO_CATALOG)

    assert catalog.capability_names() == ("default", "fast", "reasoning")
    assert catalog.providers_in_use() == ("litellm",)
    assert catalog.size() == 3
    assert catalog.source == str(REPO_CATALOG)


def test_the_shipped_catalogue_names_real_models() -> None:
    catalog = ModelCatalog.load(REPO_CATALOG)

    assert catalog.require("default").model == "ollama/gpt-oss:20b"
    assert catalog.require("fast").model == "ollama/gemma3:12b"
    assert catalog.require("reasoning").model == "ollama/qwen3:14b"
    assert all(entry.enabled for entry in catalog.entries)


def test_every_shipped_row_is_addressed_by_alias() -> None:
    """What the Gateway sends to LiteLLM is the alias, never the weights id.

    ``target`` is the single place that decision is written down, so a shipped row
    without an alias — which would silently send ``ollama/gpt-oss:20b`` and put
    model selection back in the Gateway's hands — fails here as well as at startup.
    """
    catalog = ModelCatalog.load(REPO_CATALOG)

    for entry in catalog.entries:
        assert entry.alias is not None, entry.capability
        assert entry.target == entry.alias
        assert entry.target != entry.model


# -- accepted documents --------------------------------------------------------------------


def test_minimal_entry_needs_only_provider_and_model() -> None:
    catalog = ModelCatalog.from_document(models({"default": {"provider": "ollama", "model": "m"}}))

    entry = catalog.require("default")
    assert entry == ModelEntry(capability="default", provider="ollama", model="m")
    assert entry.fallbacks == ()
    assert entry.enabled is True
    assert entry.description == ""


def test_optional_fields_are_parsed() -> None:
    catalog = ModelCatalog.from_document(
        models(
            {
                "fast": {
                    "provider": "ollama",
                    "model": "m",
                    "description": " Quick answers ",
                    "fallbacks": ["default"],
                    "enabled": False,
                },
                "default": {"provider": "ollama", "model": "n"},
            }
        )
    )

    entry = catalog.require("fast")
    assert entry.description == "Quick answers"
    assert entry.fallbacks == ("default",)
    assert entry.enabled is False
    assert catalog.enabled_entries() == (catalog.require("default"),)


# -- rejected documents --------------------------------------------------------------------


@pytest.mark.parametrize(
    "payload",
    [
        None,
        [],
        {"model": {}},
        {"models": []},
        {"models": None},
        {"models": {}, "defaults": {}},
        {"models": {"default": "ollama/gpt"}},
        {"models": {"default": {}}},
        {"models": {"default": {"provider": "ollama"}}},
        {"models": {"default": {"model": "gpt", "provder": "ollama"}}},
        {"models": {"default": {"provider": "", "model": "gpt"}}},
        {"models": {"default": {"provider": "ollama", "model": "  "}}},
        {"models": {"default": {"provider": "ollama", "model": "gpt", "fallbacks": "default"}}},
        {"models": {"default": {"provider": "ollama", "model": "gpt", "enabled": "no"}}},
    ],
    ids=[
        "empty-file",
        "list-root",
        "typo-top-level-key",
        "models-not-mapping",
        "models-null",
        "extra-top-level-key",
        "entry-not-mapping",
        "entry-empty",
        "entry-missing-model",
        "typo-field-name",
        "blank-provider",
        "blank-model",
        "fallbacks-not-a-list",
        "enabled-not-bool",
    ],
)
def test_invalid_catalogues_are_refused(payload: Any) -> None:
    with pytest.raises(CatalogError):
        ModelCatalog.from_document(payload)


def test_empty_models_mapping_is_refused() -> None:
    with pytest.raises(CatalogError, match="no models"):
        ModelCatalog.from_document(models({}))


def test_dangling_fallback_is_refused_at_load() -> None:
    with pytest.raises(CatalogError, match="unknown capability 'ghost'"):
        ModelCatalog.from_document(
            models({"default": {"provider": "p", "model": "m", "fallbacks": ["ghost"]}})
        )


def test_self_fallback_is_refused() -> None:
    with pytest.raises(CatalogError, match="lists itself"):
        ModelCatalog.from_document(
            models({"default": {"provider": "p", "model": "m", "fallbacks": ["default"]}})
        )


def test_repeated_fallback_is_refused() -> None:
    with pytest.raises(CatalogError, match="same fallback"):
        ModelCatalog.from_document(
            models(
                {
                    "default": {"provider": "p", "model": "m"},
                    "fast": {"provider": "p", "model": "f", "fallbacks": ["default", "default"]},
                }
            )
        )


def test_duplicate_capability_keys_in_yaml_are_refused(tmp_path: Path) -> None:
    """SafeLoader would let the second block silently win; that hides a model."""
    path = tmp_path / "models.yaml"
    path.write_text(
        "models:\n"
        "  default:\n    provider: a\n    model: one\n"
        "  default:\n    provider: b\n    model: two\n",
        encoding="utf-8",
    )

    with pytest.raises(CatalogError, match="Duplicate key 'default'"):
        ModelCatalog.load(path)


def test_malformed_yaml_reports_the_problem_not_a_stack_trace(tmp_path: Path) -> None:
    path = tmp_path / "models.yaml"
    path.write_text("models:\n  default: [unclosed\n", encoding="utf-8")

    with pytest.raises(CatalogError, match="not valid YAML"):
        ModelCatalog.load(path)


def test_missing_catalogue_file_reports_its_path(tmp_path: Path) -> None:
    missing = tmp_path / "nope.yaml"
    with pytest.raises(CatalogError, match="Cannot read model catalogue"):
        ModelCatalog.load(missing)


# -- capability lookups ------------------------------------------------------------------


def test_require_unknown_capability_carries_a_stable_code_and_the_alternatives() -> None:
    catalog = ModelCatalog.from_document(document())

    with pytest.raises(UnknownCapabilityError) as caught:
        catalog.require("vision")

    assert caught.value.code == "unknown_capability"
    assert caught.value.status_code == 404
    assert "default" in caught.value.details["known_capabilities"]


def test_disabled_entries_stay_visible_for_listing() -> None:
    """Refusing to route to a disabled capability is routing's job (test_routing)."""
    assert ModelCatalog.from_document(document()).require("retired").enabled is False


# -- skills ------------------------------------------------------------------------------


def test_a_skill_resolves_to_the_capability_it_declares() -> None:
    catalog = make_catalog(document())

    assert catalog.require_skill("clinical-chat").capability == "default"
    assert catalog.require_skill("summarize-document").description == "Condense a document."
    assert catalog.skill_names() == ("clinical-chat", "summarize-document", "retired-skill")


def test_a_skill_carries_no_infrastructure() -> None:
    """The whole point of the concept: a skill cannot smuggle in a model or endpoint."""
    card = make_catalog(document()).require_skill("clinical-chat").to_public_dict()

    assert set(card) == {
        "name",
        "capability",
        "description",
        "enabled",
        "clinical_risk",
        "approval_required",
        "audit_required",
        "allow_downgrade",
    }
    assert not {"model", "provider", "alias", "api_base", "fallbacks"} & set(card)


def test_a_skill_declares_its_policy_alongside_its_intent() -> None:
    policy = make_catalog(document()).require_skill("clinical-chat").policy

    assert policy.clinical_risk == "moderate"
    assert policy.audit_required is True
    assert policy.allow_downgrade is True
    assert policy.approval_required is False


def test_two_skills_may_share_one_capability() -> None:
    """Radiology and pathology are different intents on the same processing class."""
    catalog = ModelCatalog.from_document(
        {
            "models": {"reasoning": {"provider": "p", "model": "m"}},
            "skills": {
                "radiology-report": {"capability": "reasoning", "clinical_risk": "moderate"},
                "pathology-review": {"capability": "reasoning", "clinical_risk": "moderate"},
            },
        }
    )

    assert catalog.skill_names() == ("radiology-report", "pathology-review")
    assert catalog.require_skill("pathology-review").capability == "reasoning"


def test_a_skill_naming_an_undeclared_capability_is_refused_at_load() -> None:
    with pytest.raises(CatalogError, match="does not declare"):
        ModelCatalog.from_document(
            {
                "models": {"default": {"provider": "p", "model": "m"}},
                "skills": {"vision-report": {"capability": "vision", "clinical_risk": "low"}},
            }
        )


@pytest.mark.parametrize("field", ["model", "provider", "api_base", "fallbacks"])
def test_a_skill_carrying_a_routing_field_is_refused(field: str) -> None:
    """Rejected by name, so a skill can never quietly become the old model entry."""
    with pytest.raises(CatalogError, match="unsupported field"):
        ModelCatalog.from_document(
            {
                "models": {"default": {"provider": "p", "model": "m"}},
                "skills": {"s": {"capability": "default", field: "anything"}},
            }
        )


@pytest.mark.parametrize(
    "raw",
    [
        {},
        {"capability": ""},
        {"capability": "  "},
        {"capability": ["default"]},
        {"capability": "default", "enabled": "no"},
    ],
    ids=["empty", "blank", "whitespace", "list", "enabled-not-bool"],
)
def test_malformed_skills_are_refused(raw: dict) -> None:
    with pytest.raises(CatalogError):
        ModelCatalog.from_document(
            {"models": {"default": {"provider": "p", "model": "m"}}, "skills": {"s": raw}}
        )


def test_skills_are_optional() -> None:
    """A catalogue predating skills still loads; nothing about routing depends on them."""
    catalog = ModelCatalog.from_document(models({"default": {"provider": "p", "model": "m"}}))

    assert catalog.skills == ()
    assert catalog.skill_names() == ()


def test_duplicate_skill_names_are_refused_when_built_directly() -> None:
    entry = ModelEntry(capability="default", provider="p", model="m")
    with pytest.raises(CatalogError, match="twice"):
        ModelCatalog(
            entries=(entry,),
            skills=(
                Skill(name="x", capability="default"),
                Skill(name="x", capability="default"),
            ),
        )


def test_a_skill_not_mapping_is_refused() -> None:
    with pytest.raises(CatalogError, match="must be a mapping"):
        ModelCatalog.from_document(
            {"models": {"default": {"provider": "p", "model": "m"}}, "skills": {"s": "default"}}
        )


def test_the_skills_stanza_must_be_a_mapping() -> None:
    with pytest.raises(CatalogError, match="'skills' stanza must be a mapping"):
        ModelCatalog.from_document(
            {"models": {"default": {"provider": "p", "model": "m"}}, "skills": ["a"]}
        )


def test_unknown_skill_carries_a_stable_code_and_the_alternatives() -> None:
    catalog = make_catalog(document())

    with pytest.raises(UnknownSkillError) as caught:
        catalog.require_skill("MRI_READ")

    assert caught.value.code == "unknown_skill"
    assert caught.value.status_code == 404
    assert "clinical-chat" in caught.value.details["known_skills"]


def test_a_disabled_skill_is_listed_but_marked() -> None:
    catalog = make_catalog(document())

    assert catalog.require_skill("retired-skill").enabled is False
    assert catalog.enabled_skills() == (
        catalog.require_skill("clinical-chat"),
        catalog.require_skill("summarize-document"),
    )


def test_a_skill_named_by_a_model_id_is_not_resolvable() -> None:
    """The deleted model-id selector must not be re-derivable through skills."""
    catalog = make_catalog(document())

    with pytest.raises(UnknownSkillError):
        catalog.require_skill("fake-small")


# -- reporting ---------------------------------------------------------------------------


def test_public_summary_lists_skills_capabilities_and_providers() -> None:
    catalog = make_catalog(document())
    summary = catalog.to_public_dict()

    assert summary["count"] == 4
    assert summary["providers"] == ["fake"]
    assert summary["source"] == "test-catalog"
    assert "default" in summary["capabilities"]
    assert "radiology-report" not in summary["skills"]
    assert "clinical-chat" in summary["skills"]


def test_the_shipped_catalogue_declares_skills_as_well_as_capabilities() -> None:
    catalog = ModelCatalog.load(REPO_CATALOG)

    assert catalog.skill_names() == (
        "platform-chat",
        "radiology-report",
        "pathology-review",
        "clinical-chat",
        "summarize-document",
        "usg-advisory-suggestions",
    )
    assert catalog.require_skill("radiology-report").capability == "reasoning"
    assert catalog.require_skill("summarize-document").capability == "fast"


def test_the_migrated_usg_assistant_keeps_its_governance_oneway() -> None:
    """The ERP's ultrasound assistant arrived in Sprint 8 with rules it did not have.

    Pinned because the old path would fall back to any enabled provider, and a
    skill that silently relaxes `allow_downgrade` back to the default would put
    that behaviour back without anyone editing an application.
    """
    skill = ModelCatalog.load(REPO_CATALOG).require_skill("usg-advisory-suggestions")
    policy = skill.policy

    assert skill.capability == "fast"
    assert policy.clinical_risk == "moderate"
    assert policy.audit_required is True
    assert policy.allow_downgrade is False
    assert policy.approval_required is False
    assert policy.max_completion_tokens == 1200
    assert policy.request_timeout_seconds == 120
