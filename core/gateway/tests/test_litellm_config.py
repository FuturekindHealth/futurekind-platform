"""The alias contract, checked against the file on the other side of it.

``ADR-0002`` gives LiteLLM the alias namespace, and Sprint 6 puts the Gateway's
traffic on it. That is only true if the name the Gateway sends is a name LiteLLM
will accept, so the comparison happens at startup, the two shipped files are
asserted to agree here, and a container that cannot prove it refuses to start.
The request-level consequence is in ``tests/test_end_to_end.py``; this file is
about the check itself.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from futurekind_gateway.app import create_app, verify_alias_contract
from futurekind_gateway.catalog import ModelCatalog
from futurekind_gateway.errors import ConfigurationError
from futurekind_gateway.litellm_config import (
    LITELLM_PROVIDER_NAME,
    LiteLLMConfig,
    litellm_rows,
    verify_aliases,
)
from futurekind_gateway.providers import ProviderRegistry
from tests.conftest import (
    GATEWAY_ROOT,
    REPO_CATALOG,
    FakeProvider,
    make_catalog,
    make_settings,
)

REPO_LITELLM_CONFIG = GATEWAY_ROOT.parent.parent / "configs" / "litellm" / "config.yaml"

#: A catalogue whose every row routes through the platform's one transport.
LITELLM_CATALOG: dict[str, Any] = {
    "skills": {"platform-chat": {"capability": "default", "clinical_risk": "low"}},
    "models": {
        "default": {"provider": "litellm", "model": "ollama/gpt-oss:20b", "alias": "fk-default"},
        "fast": {"provider": "litellm", "model": "ollama/gemma3:12b", "alias": "fk-fast"},
        "retired": {
            "provider": "litellm",
            "model": "ollama/old:1b",
            "alias": "fk-obsolete",
            "enabled": False,
        },
    },
}

CONFIG_TEXT = """
model_list:
  - model_name: fk-default
    litellm_params:
      model: ollama/gpt-oss:20b
      api_base: ${OLLAMA_PRIMARY}
  - model_name: fk-fast
    litellm_params:
      model: ollama/gemma3:12b
"""


def one_row_catalog(**overrides: Any) -> ModelCatalog:
    """A single-capability catalogue, for the cases that are about one row."""
    row: dict[str, Any] = {
        "capability": "default",
        "provider": "litellm",
        "model": "ollama/gpt-oss:20b",
        "alias": "fk-default",
    }
    name = row.pop("capability")
    row.update(overrides)
    return catalog_of({"models": {name: row}})


def catalog_of(document: dict[str, Any]) -> ModelCatalog:
    return ModelCatalog.from_document(document, source="test-litellm-catalog")


def config_of(*pairs: tuple[str, str]) -> LiteLLMConfig:
    """An in-memory view of LiteLLM's model list.

    Parsing is tested separately from files; these tests are about what the
    comparison *decides*, so they should not depend on YAML to make their point.
    """
    targets: dict[str, list[str]] = {}
    for alias, target in pairs:
        targets.setdefault(alias, []).append(target)
    return LiteLLMConfig(
        source="test-litellm-config",
        targets={alias: tuple(values) for alias, values in targets.items()},
    )


def write_config(tmp_path: Path, text: str = CONFIG_TEXT) -> Path:
    path = tmp_path / "litellm-config.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def registry_with_fake() -> ProviderRegistry:
    registry = ProviderRegistry()
    registry.register("fake", lambda: FakeProvider())
    return registry


# -- the two files that ship together --------------------------------------------------------


def test_the_litellm_file_lives_where_the_deployment_says_it_does() -> None:
    """The check is worthless if it silently reads the wrong file."""
    assert REPO_LITELLM_CONFIG.is_file(), REPO_LITELLM_CONFIG


def test_the_two_shipped_files_agree() -> None:
    """The headline guard of Sprint 6: every alias the Gateway sends exists in LiteLLM.

    Editing one file without the other is the mistake this test exists to make
    impossible, and it is the same comparison that refuses a container to start.
    """
    report = verify_aliases(
        ModelCatalog.load(REPO_CATALOG), LiteLLMConfig.load(REPO_LITELLM_CONFIG)
    )

    assert report.checked == 3
    assert report.has_drift is False
    assert set(LiteLLMConfig.load(REPO_LITELLM_CONFIG).aliases()) >= {
        "fk-default",
        "fk-fast",
        "fk-reasoning",
    }


def test_the_shipped_catalogue_describes_the_backends_the_litellm_file_routes_to() -> None:
    """No drift between what the audit will claim answered and what LiteLLM will run."""
    config = LiteLLMConfig.load(REPO_LITELLM_CONFIG)

    for entry in ModelCatalog.load(REPO_CATALOG).entries:
        assert config.targets_for(entry.alias or "") == (entry.model,)


# -- reading LiteLLM's configuration ---------------------------------------------------------


def test_the_model_list_is_read_as_alias_to_deployment(tmp_path: Path) -> None:
    config = LiteLLMConfig.load(write_config(tmp_path))

    assert config.aliases() == ("fk-default", "fk-fast")
    assert config.targets_for("fk-default") == ("ollama/gpt-oss:20b",)
    assert config.has_alias("fk-obsolete") is False


def test_one_alias_may_legitimately_carry_several_deployments(tmp_path: Path) -> None:
    """LiteLLM's own load balancing repeats a model_name; that is not a broken contract."""
    config = LiteLLMConfig.load(
        write_config(
            tmp_path,
            """
model_list:
  - model_name: fk-default
    litellm_params:
      model: ollama/gpt-oss:20b
  - model_name: fk-default
    litellm_params:
      model: ollama/gpt-oss:14b
""",
        )
    )

    assert config.targets_for("fk-default") == ("ollama/gpt-oss:20b", "ollama/gpt-oss:14b")
    assert verify_aliases(one_row_catalog(model="ollama/gpt-oss:14b"), config).has_drift is False


@pytest.mark.parametrize(
    "text",
    [
        pytest.param("", id="empty-file"),
        pytest.param("general_settings:\n  master_key: x\n", id="no-model-list"),
        pytest.param("model_list: []\n", id="empty-model-list"),
        pytest.param("model_list:\n  - not_a_mapping\n", id="item-not-a-mapping"),
        pytest.param("model_list:\n  - litellm_params:\n      model: ollama/x\n", id="no-name"),
        pytest.param(
            "model_list:\n  - model_name: fk-x\n    litellm_params: {}\n", id="name-without-target"
        ),
        pytest.param("model_list: [\n", id="invalid-yaml"),
    ],
)
def test_a_litellm_file_that_cannot_be_honoured_is_refused_rather_than_trusted(
    tmp_path: Path, text: str
) -> None:
    """"I could not read it" must never be reported as "it matched"."""
    with pytest.raises(ConfigurationError):
        LiteLLMConfig.load(write_config(tmp_path, text))


def test_a_missing_litellm_file_names_the_path_it_tried(tmp_path: Path) -> None:
    absent = tmp_path / "nowhere.yaml"

    with pytest.raises(ConfigurationError) as caught:
        LiteLLMConfig.load(absent)

    assert caught.value.details["path"] == str(absent)


# -- which rows this applies to --------------------------------------------------------------


def test_only_enabled_rows_that_route_to_litellm_are_checked() -> None:
    rows = litellm_rows(catalog_of(LITELLM_CATALOG))

    assert [entry.capability for entry in rows] == ["default", "fast"]
    assert all(entry.provider == LITELLM_PROVIDER_NAME for entry in rows)


def test_a_catalogue_that_uses_no_litellm_needs_no_litellm_file() -> None:
    """The fake-provider tests must not require a LiteLLM installation to run."""
    assert verify_alias_contract(make_settings(), make_catalog()) is None


def test_a_catalogue_that_failed_to_load_has_nothing_to_check() -> None:
    assert verify_alias_contract(make_settings(), None) is None


# -- the refusals ----------------------------------------------------------------------------


def test_an_alias_liteLLM_does_not_know_about_is_named_in_the_refusal() -> None:
    with pytest.raises(ConfigurationError) as caught:
        verify_aliases(catalog_of(LITELLM_CATALOG), config_of(("fk-fast", "ollama/gemma3:12b")))

    details = caught.value.details
    assert [item["alias"] for item in details["missing"]] == ["fk-default"]
    assert details["litellm_aliases"] == ["fk-fast"]
    assert "configs/litellm/config.yaml" in details["hint"]


def test_a_litellm_row_without_an_alias_is_refused_as_well() -> None:
    """Sending the weights id instead would put model selection back in the Gateway."""
    catalog = catalog_of(
        {"models": {"default": {"provider": "litellm", "model": "ollama/gpt-oss:20b"}}}
    )

    with pytest.raises(ConfigurationError) as caught:
        verify_aliases(catalog, config_of(("fk-fast", "ollama/gemma3:12b")))

    missing = caught.value.details["missing"]
    assert missing[0]["alias"] is None
    assert missing[0]["reason"].startswith("routes to LiteLLM without")


def test_a_drifted_model_string_is_reported_but_does_not_refuse_startup() -> None:
    """The audit line would be wrong; the request would still be routed correctly."""
    report = verify_aliases(
        one_row_catalog(model="ollama/renamed:9b"),
        config_of(("fk-default", "ollama/gpt-oss:20b")),
    )

    assert report.checked == 1
    assert report.has_drift is True
    assert report.drift[0]["capability"] == "default"
    assert report.drift[0]["litellm_models"] == ["ollama/gpt-oss:20b"]


def test_every_alias_present_means_no_drift_and_no_refusal() -> None:
    report = verify_aliases(
        catalog_of(LITELLM_CATALOG),
        config_of(("fk-default", "ollama/gpt-oss:20b"), ("fk-fast", "ollama/gemma3:12b")),
    )

    assert report.checked == 2
    assert report.drift == ()


# -- the startup consequence -----------------------------------------------------------------


def test_the_gateway_refuses_to_start_when_the_alias_is_missing(tmp_path: Path) -> None:
    """SPEC-07-03, stated as an outcome rather than as a description."""
    with pytest.raises(ConfigurationError) as caught:
        create_app(
            make_settings(litellm_config_path=write_config(tmp_path)),
            catalog=catalog_of(
                {
                    "models": {
                        "default": {
                            "provider": "litellm",
                            "model": "ollama/gpt-oss:20b",
                            "alias": "fk-nowhere",
                        }
                    }
                }
            ),
            provider_registry=registry_with_fake(),
        )

    assert "fk-nowhere" in caught.value.message


def test_the_gateway_starts_when_the_alias_exists(tmp_path: Path) -> None:
    app = create_app(
        make_settings(litellm_config_path=write_config(tmp_path)),
        catalog=catalog_of(LITELLM_CATALOG),
        provider_registry=registry_with_fake(),
    )

    assert app.state.alias_report is not None
    assert app.state.alias_report.checked == 2


def test_a_container_with_no_litellm_file_is_told_which_setting_to_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Discovery only helps a checkout; an installed wheel has to be told."""
    import futurekind_gateway.app as app_module

    monkeypatch.setattr(app_module, "discover_litellm_config_path", lambda: None)

    with pytest.raises(ConfigurationError) as caught:
        create_app(
            make_settings(litellm_config_path=None),
            catalog=catalog_of(LITELLM_CATALOG),
            provider_registry=registry_with_fake(),
        )

    assert "FK_GATEWAY_LITELLM_CONFIG" in caught.value.details["hint"]


def test_the_shipped_files_pass_the_startup_check_from_the_repository_root() -> None:
    """The repository's own two files must satisfy the path a container takes.

    ``create_app`` is given no explicit LiteLLM path here on purpose: it discovers
    the file the way a checkout does, so a shipped alias that LiteLLM would reject
    fails this test rather than a deployment three days later.
    """
    app = create_app(
        make_settings(),
        catalog=ModelCatalog.load(REPO_CATALOG),
        provider_registry=registry_with_fake(),
    )

    assert app.state.alias_report is not None
    assert app.state.alias_report.checked == 3
