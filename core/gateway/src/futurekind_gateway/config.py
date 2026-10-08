"""Environment-driven configuration for the FutureKind Gateway.

Every tunable lives here, read once at startup into an immutable
:class:`GatewaySettings`.  No other module reads ``os.environ``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

_TRUE = frozenset({"1", "true", "yes", "on"})
_FALSE = frozenset({"0", "false", "no", "off"})

ENV_PREFIX = "FK_GATEWAY_"

#: The catalogue that ships in the repository next to this component.
_CATALOG_FILENAME = "models.yaml"

#: Where LiteLLM's own model list lives, relative to the repository root.  The
#: Gateway reads it to prove that every alias it will send exists on the other
#: side of the alias contract (``ADR-0002``); it never writes to it.
_LITELLM_CONFIG_RELPATH = ("configs", "litellm", "config.yaml")


def _get(name: str) -> str | None:
    """Return a stripped environment value, or ``None`` when absent or blank."""
    raw = os.environ.get(ENV_PREFIX + name)
    if raw is None:
        return None
    raw = raw.strip()
    return raw or None


def _as_bool(name: str, default: bool) -> bool:
    raw = _get(name)
    if raw is None:
        return default
    lowered = raw.lower()
    if lowered in _TRUE:
        return True
    if lowered in _FALSE:
        return False
    return default


def _as_int(name: str, default: int, *, minimum: int, maximum: int) -> int:
    raw = _get(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return min(max(value, minimum), maximum)


def _as_float(name: str, default: float, *, minimum: float, maximum: float) -> float:
    raw = _get(name)
    if raw is None:
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    return min(max(value, minimum), maximum)


def _as_tuple(name: str) -> tuple[str, ...]:
    """Split a comma- or whitespace-separated list, dropping empty members."""
    raw = _get(name)
    if raw is None:
        return ()
    return tuple(item for item in raw.replace(",", " ").split() if item)


def discover_catalog_path(start: Path | None = None) -> Path | None:
    """Find ``models.yaml`` by walking up from this package.

    In a checkout this resolves ``core/gateway/models.yaml``.  When the package
    is installed into a virtualenv the walk finds nothing and the caller must
    set ``FK_GATEWAY_MODELS_PATH``.  Returns ``None`` rather than raising so the
    caller can decide whether the catalogue is optional.
    """
    origin = (start or Path(__file__)).resolve()
    for candidate in (origin, *origin.parents):
        if not candidate.is_dir():
            continue
        found = candidate / _CATALOG_FILENAME
        if found.is_file():
            return found
    return None


def discover_litellm_config_path(start: Path | None = None) -> Path | None:
    """Find ``configs/litellm/config.yaml`` by walking up from this package.

    The counterpart of :func:`discover_catalog_path`, and it fails the same way:
    returning ``None`` instead of guessing.  A checkout finds the file the
    repository ships; a wheel installed without the repository does not, and
    then the operator must set ``FK_GATEWAY_LITELLM_CONFIG`` — which is the
    signal for the alias check to refuse rather than to stay quiet.
    """
    origin = (start or Path(__file__)).resolve()
    for candidate in (origin, *origin.parents):
        if not candidate.is_dir():
            continue
        found = candidate.joinpath(*_LITELLM_CONFIG_RELPATH)
        if found.is_file():
            return found
    return None


@dataclass(frozen=True)
class GatewaySettings:
    """Immutable runtime configuration for one Gateway process."""

    host: str = "0.0.0.0"
    port: int = 8100
    catalog_path: Path | None = None
    default_capability: str = "default"
    require_auth: bool = True
    api_keys: tuple[str, ...] = ()
    request_timeout_seconds: float = 120.0
    max_messages: int = 100
    max_content_chars: int = 32_000
    max_completion_tokens: int = 8192
    log_level: str = "INFO"
    json_logs: bool = True
    service_name: str = "futurekind-gateway"
    #: Where LiteLLM listens. No default on purpose: a Gateway that invents an
    #: endpoint would be choosing infrastructure for itself, which `ADR-0002`
    #: gives to LiteLLM's configuration, not to Python.
    litellm_base_url: str | None = None
    #: The credential LiteLLM expects (its master key). Distinct from the keys
    #: this Gateway issues to applications: two boundaries, two secrets.
    litellm_api_key: str | None = None
    #: LiteLLM's own model list, read once at startup to prove the aliases match.
    litellm_config_path: Path | None = None

    @classmethod
    def from_env(cls) -> GatewaySettings:
        """Build settings from ``FK_GATEWAY_*`` environment variables."""
        catalog_raw = _get("MODELS_PATH")
        catalog_path = Path(catalog_raw).expanduser() if catalog_raw else discover_catalog_path()
        litellm_config_raw = _get("LITELLM_CONFIG")
        litellm_config_path = (
            Path(litellm_config_raw).expanduser()
            if litellm_config_raw
            else discover_litellm_config_path()
        )
        return cls(
            host=_get("HOST") or "0.0.0.0",
            port=_as_int("PORT", 8100, minimum=1, maximum=65_535),
            catalog_path=catalog_path,
            default_capability=(_get("DEFAULT_CAPABILITY") or "default").lower(),
            require_auth=_as_bool("REQUIRE_AUTH", True),
            api_keys=_as_tuple("API_KEYS"),
            request_timeout_seconds=_as_float(
                "REQUEST_TIMEOUT_SECONDS", 120.0, minimum=1.0, maximum=3_600.0
            ),
            max_messages=_as_int("MAX_MESSAGES", 100, minimum=1, maximum=1_000),
            max_content_chars=_as_int("MAX_CONTENT_CHARS", 32_000, minimum=1, maximum=1_000_000),
            max_completion_tokens=_as_int(
                "MAX_COMPLETION_TOKENS", 8192, minimum=1, maximum=1_000_000
            ),
            log_level=(_get("LOG_LEVEL") or "INFO").upper(),
            json_logs=_as_bool("JSON_LOGS", True),
            service_name=_get("SERVICE_NAME") or "futurekind-gateway",
            litellm_base_url=_get("LITELLM_BASE_URL"),
            litellm_api_key=_get("LITELLM_API_KEY"),
            litellm_config_path=litellm_config_path,
        )

    def with_overrides(self, **changes: Any) -> GatewaySettings:
        """Return a copy with the given fields replaced (used by tests and embedders)."""
        return replace(self, **changes)

    @property
    def authentication_configured(self) -> bool:
        """True when a caller can actually be authenticated."""
        return bool(self.api_keys)

    @property
    def litellm_endpoint_configured(self) -> bool:
        """True when the Gateway has somewhere to send an alias.

        Nothing in the Gateway invents an endpoint: a catalogue that routes to
        LiteLLM with no ``FK_GATEWAY_LITELLM_BASE_URL`` is a deployment that
        cannot answer a single request, so the provider refuses to build and
        says so as ``503 configuration_error`` rather than racing a ``502`` in
        front of a clinician.
        """
        return bool(self.litellm_base_url)

    @property
    def litellm_credential_configured(self) -> bool:
        """True when LiteLLM will accept this Gateway at all."""
        return bool(self.litellm_api_key)


__all__ = [
    "ENV_PREFIX",
    "GatewaySettings",
    "discover_catalog_path",
    "discover_litellm_config_path",
]
