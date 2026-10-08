"""Console entrypoint for the Gateway.

Configuration comes from ``FK_GATEWAY_*`` environment variables, not from
command-line flags, so a container, a systemd unit and a developer terminal all
start the identical thing.  Run ``futurekind-gateway`` after installing the
package, or ``python -m futurekind_gateway``.

The split that matters lives in the two assembly functions here. ``create_app``
is the test seam: it assembles whatever it is handed and registers no provider,
so a test that wants a fake can only get a fake. :func:`build_production_app` is
what the process runs: the same factory plus the one provider this deployment
speaks to — LiteLLM, per ``ADR-0002``. Keeping that wiring in the entrypoint
rather than inside the factory is what makes "which backends can this build
invoke" a deployment fact instead of an import side effect.
"""

from __future__ import annotations

from functools import partial
from typing import Any

import uvicorn
from fastapi import FastAPI

from .app import create_app
from .config import GatewaySettings
from .observability.logging import configure_logging, log_event
from .providers import ProviderRegistry
from .providers.litellm import LiteLLMProvider


def uvicorn_log_config(service: str, json_logs: bool) -> dict[str, Any]:
    """A logging config that makes uvicorn write in the Gateway's own format.

    Uvicorn installs plain-text handlers by default, so a deployed Gateway would
    otherwise emit one JSON line and then ``INFO: Started server process``.  A
    log pipeline parses one shape, not two — which matters when these lines are
    part of the clinical audit record.
    """
    formatter: dict[str, Any] = (
        {"()": "futurekind_gateway.observability.logging.JsonFormatter", "service": service}
        if json_logs
        else {"()": "futurekind_gateway.observability.logging.PlainFormatter"}
    )
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {"gateway": formatter},
        "handlers": {
            "gateway": {
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stdout",
                "formatter": "gateway",
            }
        },
        "loggers": {
            "uvicorn": {"handlers": ["gateway"], "level": "INFO", "propagate": False},
            "uvicorn.error": {"handlers": ["gateway"], "level": "INFO", "propagate": False},
            # Uvicorn's own access log is switched off: the Gateway writes a richer line
            # that carries the request id, so only real warnings come through here.
            "uvicorn.access": {"handlers": ["gateway"], "level": "WARNING", "propagate": False},
        },
    }


def production_provider_registry(settings: GatewaySettings) -> ProviderRegistry:
    """The providers this deployment can invoke: LiteLLM, and nothing else.

    Registered unconditionally, even with no endpoint configured. The registry
    builds providers lazily, so an unusable ``base_url`` surfaces as
    ``503 configuration_error`` naming the setting at fault, and ``GET /health``
    reports the same thing as an unhealthy component. Silently leaving it out
    would instead answer ``501 provider_not_implemented`` — a sentence that would
    be false, and would read like a missing feature rather than a missing setting.
    """
    registry = ProviderRegistry()
    registry.register(
        LiteLLMProvider.name,
        partial(
            LiteLLMProvider,
            base_url=settings.litellm_base_url or "",
            api_key=settings.litellm_api_key,
            # Slightly above the Gateway's own deadline, so the platform's
            # timeout is the one that fires and produces a 504 the skill's policy
            # explains — not a socket race that produces whatever httpx says.
            timeout_seconds=settings.request_timeout_seconds + 5.0,
        ),
    )
    return registry


def build_production_app() -> FastAPI:
    """Assemble the Gateway exactly as a deployed process runs it."""
    settings = GatewaySettings.from_env()
    return create_app(settings, provider_registry=production_provider_registry(settings))


def main() -> int:
    """Start the Gateway and block until it stops."""
    settings = GatewaySettings.from_env()
    # Configured before uvicorn binds, so a startup failure is still structured.
    logger = configure_logging(
        level=settings.log_level,
        json_logs=settings.json_logs,
        service=settings.service_name,
    )
    log_event(
        logger,
        "info",
        "gateway_launch_requested",
        host=settings.host,
        port=settings.port,
        catalog_path=str(settings.catalog_path) if settings.catalog_path else None,
        litellm_config_path=(
            str(settings.litellm_config_path) if settings.litellm_config_path else None
        ),
        litellm_endpoint_configured=settings.litellm_endpoint_configured,
    )
    uvicorn.run(
        "futurekind_gateway.main:build_production_app",
        factory=True,
        host=settings.host,
        port=settings.port,
        # The Gateway emits its own structured access line per request, including
        # the request id and the caller label, which uvicorn's cannot carry.
        access_log=False,
        log_config=uvicorn_log_config(settings.service_name, settings.json_logs),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
