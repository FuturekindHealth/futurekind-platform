"""``GET /health`` and ``GET /health/ready``.

The two endpoints answer different questions and are documented as such:

* ``/health`` — is the process alive, and is each of its parts working?
  Always ``200`` while the Gateway runs, even when a component is unhealthy, so
  a liveness probe never restarts a container that is reporting a problem
  correctly.
* ``/health/ready`` — should traffic be routed here at all? ``503`` when a hard
  misconfiguration means the Gateway cannot honestly serve: no usable catalogue,
  or authentication demanded with no keys configured.

Both stay unauthenticated, because a container runtime and a network load
balancer cannot hold an application credential. That is exactly why neither
carries an inventory. An earlier build answered them with the catalogue's
filesystem path, the provider list and a per-capability routing summary, which
let anyone who could reach the port read the deployment the platform exists to
keep out of application reach (``docs/CONSTITUTION.md`` P8, P10). What they
publish now is a verdict: which component is unhappy, in words that identify no
backend, no path and no model.

The detail an operator needs to fix the problem goes to the log, and the
inventory stays available to anyone who can pay for it at ``GET /models``.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Request

from .. import __version__
from ..errors import GatewayError
from ..observability.logging import get_logger, log_event
from ..schemas import (
    ComponentHealthSchema,
    HealthResponseSchema,
    ReadinessResponseSchema,
)
from .deps import get_catalog, get_registry, get_settings

router = APIRouter(tags=["health"])

#: Public wording for a catalogue that failed to load. The real reason names a file.
CATALOGUE_UNAVAILABLE = "model catalogue is not loaded — the Gateway log names the cause"


def _timestamp() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _catalogue_detail(request: Request) -> str | None:
    """The operator-facing cause, logged rather than returned.

    A path is the useful half of a catalogue failure, and it is also a deployment
    detail, so it goes out here and nowhere public.
    """
    reason = getattr(request.app.state, "catalog_error", None)
    if reason is None:
        return None
    log_event(
        get_logger("futurekind.gateway"),
        "warning",
        "health_catalogue_unavailable",
        detail=reason,
    )
    return str(reason)


def _catalogue_component(request: Request) -> ComponentHealthSchema:
    catalog = get_catalog(request)
    if catalog is None:
        _catalogue_detail(request)
        return ComponentHealthSchema(name="catalogue", healthy=False, detail=CATALOGUE_UNAVAILABLE)
    return ComponentHealthSchema(name="catalogue", healthy=True, detail="loaded")


def _authentication_component(request: Request) -> ComponentHealthSchema:
    settings = get_settings(request)
    if not settings.require_auth:
        return ComponentHealthSchema(
            name="authentication",
            healthy=True,
            detail="credentials are not required by configuration",
        )
    if not settings.api_keys:
        return ComponentHealthSchema(
            name="authentication",
            healthy=False,
            detail="authentication is required but no credential is configured",
        )
    return ComponentHealthSchema(
        name="authentication",
        healthy=True,
        detail="credentials required and configured",
    )


async def _providers_component(request: Request) -> ComponentHealthSchema:
    registry = get_registry(request)
    service = getattr(request.app.state, "service", None)
    registered = list(registry.names())

    if not registered:
        return ComponentHealthSchema(
            name="providers",
            healthy=False,
            detail="no provider implementation registered — chat returns 501",
        )
    if service is None:
        return ComponentHealthSchema(
            name="providers", healthy=False, detail="gateway not initialised"
        )

    probes = await service.probe_providers()
    unhealthy = [probe.provider for probe in probes if not probe.healthy]
    if unhealthy:
        # Which backend is down, and why, is in the log; the names and their error
        # strings (which quote upstream addresses) are not for this response.
        log_event(
            get_logger("futurekind.gateway"),
            "warning",
            "health_provider_unhealthy",
            count=len(unhealthy),
            detail="; ".join(
                f"{probe.provider}: {probe.detail or 'unhealthy'}"
                for probe in probes
                if not probe.healthy
            ),
        )
        return ComponentHealthSchema(
            name="providers",
            healthy=False,
            detail=f"{len(unhealthy)} of {len(registered)} providers unhealthy",
        )
    return ComponentHealthSchema(
        name="providers",
        healthy=True,
        detail=f"{len(registered)} registered, all reporting healthy",
    )


@router.get(
    "/health",
    response_model=HealthResponseSchema,
    summary="Gateway health",
    description=(
        "Current self-assessment of the Gateway. Always `200` while the process "
        "runs, with `status: degraded` when a component is unhealthy, so liveness "
        "probes do not restart a container that is reporting honestly.\n\n"
        "Unauthenticated, so it names no provider, no model and no path. "
        "`GET /models` with a credential is the inventory."
    ),
    responses={200: {"description": "The Gateway process is answering."}},
)
async def health(request: Request) -> HealthResponseSchema:
    settings = get_settings(request)

    components = [
        _catalogue_component(request),
        await _providers_component(request),
        _authentication_component(request),
    ]
    return HealthResponseSchema(
        status="ok" if all(component.healthy for component in components) else "degraded",
        service=settings.service_name,
        version=__version__,
        checked_at=_timestamp(),
        components=components,
        authentication=settings.require_auth,
    )


@router.get(
    "/health/ready",
    response_model=ReadinessResponseSchema,
    summary="Gateway readiness",
    description=(
        "`200` when the Gateway can honestly accept traffic. `503` with the "
        "blocking reasons when its model catalogue is unusable or when "
        "authentication is required but no key is configured.\n\n"
        "The reason strings identify the fault, not the file: a probe reads this "
        "without a credential, so the path that failed is logged instead."
    ),
    responses={
        200: {"description": "Ready to accept traffic."},
        503: {"description": "Not ready. The response body lists the reasons."},
    },
)
async def readiness(request: Request) -> ReadinessResponseSchema:
    settings = get_settings(request)
    reasons: list[str] = []

    if get_catalog(request) is None:
        _catalogue_detail(request)
        reasons.append("model catalogue unavailable")
    if settings.require_auth and not settings.api_keys:
        reasons.append("authentication required but no API keys are configured")

    if reasons:
        raise GatewayError(
            "Gateway is not ready",
            code="not_ready",
            status_code=503,
            details={"reasons": reasons},
        )

    return ReadinessResponseSchema(ready=True, checked_at=_timestamp(), reasons=[])


__all__ = ["router"]
