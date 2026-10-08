"""Unit tests for environment-driven configuration."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from futurekind_gateway.config import ENV_PREFIX, GatewaySettings, discover_catalog_path
from tests.conftest import REPO_CATALOG


def test_defaults_are_safe_for_a_clinical_gateway() -> None:
    settings = GatewaySettings()
    assert settings.require_auth is True
    assert settings.api_keys == ()
    assert settings.authentication_configured is False


def test_from_env_reads_every_typed_field(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(f"{ENV_PREFIX}HOST", "127.0.0.1")
    monkeypatch.setenv(f"{ENV_PREFIX}PORT", "9000")
    monkeypatch.setenv(f"{ENV_PREFIX}REQUIRE_AUTH", "false")
    monkeypatch.setenv(f"{ENV_PREFIX}API_KEYS", "one, two,three")
    monkeypatch.setenv(f"{ENV_PREFIX}REQUEST_TIMEOUT_SECONDS", "30")
    monkeypatch.setenv(f"{ENV_PREFIX}MAX_MESSAGES", "12")
    monkeypatch.setenv(f"{ENV_PREFIX}JSON_LOGS", "no")
    monkeypatch.setenv(f"{ENV_PREFIX}DEFAULT_CAPABILITY", "Fast")

    settings = GatewaySettings.from_env()

    assert settings.host == "127.0.0.1"
    assert settings.port == 9000
    assert settings.require_auth is False
    assert settings.api_keys == ("one", "two", "three")
    assert settings.request_timeout_seconds == 30.0
    assert settings.max_messages == 12
    assert settings.json_logs is False
    assert settings.default_capability == "fast"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("true", True), ("TRUE", True), ("1", True), ("on", True), ("yes", True)],
)
def test_boolean_parsing_accepts_common_spellings(
    monkeypatch: pytest.MonkeyPatch, raw: str, expected: bool
) -> None:
    monkeypatch.setenv(f"{ENV_PREFIX}REQUIRE_AUTH", raw)
    assert GatewaySettings.from_env().require_auth is expected


@pytest.mark.parametrize("raw", ["false", "0", "off", "no", "nonsense"])
def test_unrecognised_boolean_text_falls_back_to_the_secure_default(
    monkeypatch: pytest.MonkeyPatch, raw: str
) -> None:
    monkeypatch.setenv(f"{ENV_PREFIX}REQUIRE_AUTH", raw)
    assert GatewaySettings.from_env().require_auth is (raw == "nonsense")


@pytest.mark.parametrize(
    ("name", "raw", "expected"),
    [
        ("PORT", "70000", 65_535),
        ("PORT", "0", 1),
        ("PORT", "not-a-number", 8100),
        ("REQUEST_TIMEOUT_SECONDS", "99999", 3600.0),
        ("REQUEST_TIMEOUT_SECONDS", "-5", 1.0),
        ("MAX_MESSAGES", "0", 1),
    ],
)
def test_numeric_values_are_clamped_not_crashed(
    monkeypatch: pytest.MonkeyPatch, name: str, raw: str, expected: object
) -> None:
    monkeypatch.setenv(f"{ENV_PREFIX}{name}", raw)
    settings = GatewaySettings.from_env()
    field = name.lower()
    assert getattr(settings, field) == pytest.approx(expected)


def test_blank_env_values_are_treated_as_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(f"{ENV_PREFIX}API_KEYS", "   ")
    monkeypatch.setenv(f"{ENV_PREFIX}HOST", "")
    settings = GatewaySettings.from_env()
    assert settings.api_keys == ()
    assert settings.host == "0.0.0.0"


def test_api_keys_path_defaults_to_the_repository_catalogue() -> None:
    """The shipped models.yaml is discovered from the package, not hard-coded twice."""
    assert REPO_CATALOG.is_file()
    assert discover_catalog_path(Path(__file__).parent) == REPO_CATALOG


def test_explicit_models_path_wins(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    catalogue = tmp_path / "models.yaml"
    catalogue.write_text("models:\n  default:\n    provider: p\n    model: m\n", encoding="utf-8")
    monkeypatch.setenv(f"{ENV_PREFIX}MODELS_PATH", str(catalogue))
    assert GatewaySettings.from_env().catalog_path == catalogue


def test_settings_are_immutable_and_overrides_return_a_copy() -> None:
    settings = GatewaySettings(port=8100)
    with pytest.raises(FrozenInstanceError):
        settings.port = 9000  # type: ignore[misc]
    updated = settings.with_overrides(port=9000)
    assert updated.port == 9000
    assert settings.port == 8100
