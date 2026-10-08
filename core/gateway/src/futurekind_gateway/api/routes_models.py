"""``GET /models`` — what the platform can currently be asked to do.

Read-only introspection, for the operator who holds a credential.  Applications
are expected to name a capability rather than poll this endpoint, but seeing the
resolved routing table is how an operator notices that a fallback is missing, or
that a catalogue provider was never implemented.

Everything below the skill layer — provider, model id, fallback chain — is the
internal inventory ``docs/CONSTITUTION.md`` P8 keeps out of application reach, so
this door is authenticated like ``POST /chat`` is.  The application-facing view of
"what can this Gateway do" is ``GET /v1/models``, which lists skills and nothing
else, and which requires a credential too: on this platform an inventory is not a
public notice.  Even here the alias is absent (``ADR-0002`` forbids it crossing in
either direction) and the catalogue's filesystem path is absent, because where a
configuration file lives is a deployment detail, not a fact about a request.
"""

from __future__ import annotations

from fastapi import APIRouter, Request

from ..catalog import ModelEntry, Skill
from ..routing import Route
from ..schemas import (
    ErrorResponseSchema,
    ModelCardSchema,
    ModelListResponseSchema,
    ModelRouteResponseSchema,
    RouteCardSchema,
    SkillCardSchema,
)
from .deps import AuthenticatedCaller, RegistryDep, RouterDep

router = APIRouter(tags=["models"])


def _card(entry: ModelEntry) -> ModelCardSchema:
    return ModelCardSchema(**entry.to_public_dict())


def _skill_card(skill: Skill) -> SkillCardSchema:
    return SkillCardSchema(**skill.to_public_dict())


def _route_card(route: Route) -> RouteCardSchema:
    return RouteCardSchema(
        capability=route.capability,
        provider=route.provider,
        model=route.model,
        chain=list(route.candidate_capabilities()),
    )


@router.get(
    "/models",
    response_model=ModelListResponseSchema,
    summary="Available models (operator view)",
    description=(
        "The loaded catalogue plus the routing chains the Gateway will actually "
        "follow. `skills` is the application-facing list, each card carrying the "
        "policy that governs it — clinical risk, approval, audit, whether a lesser "
        "model may answer. `models` is the internal routing table beneath it. "
        "`providers_missing` lists catalogue providers this build cannot invoke yet, "
        "which is why a fresh skeleton reports `litellm` there.\n\n"
        "Requires a credential: the routing table names infrastructure."
    ),
    responses={
        200: {"description": "The routing table."},
        401: {
            "description": "No credential, or an unknown one.",
            "model": ErrorResponseSchema,
        },
        503: {"description": "The model catalogue is unavailable."},
    },
)
async def list_models(
    request: Request,
    caller: AuthenticatedCaller,
    model_router: RouterDep,
    registry: RegistryDep,
) -> ModelListResponseSchema:
    request.state.caller = caller
    catalog = model_router.catalog
    registered = registry.names()
    models = [_card(entry) for entry in catalog.entries]
    return ModelListResponseSchema(
        default_capability=model_router.default_capability,
        count=len(models),
        skills=[_skill_card(skill) for skill in catalog.skills],
        models=models,
        routes=[_route_card(route) for route in model_router.routes()],
        providers_registered=list(registered),
        providers_missing=model_router.missing_providers(registered),
    )


@router.get(
    "/models/{capability}",
    response_model=ModelRouteResponseSchema,
    summary="One capability's resolved route (operator view)",
    description=(
        "Resolve a single capability, including its fallback chain, and report "
        "whether a provider implementation exists to serve it. Requires a "
        "credential, for the same reason `GET /models` does."
    ),
    responses={
        200: {"description": "The capability and its resolved route."},
        400: {"description": "The capability exists but is disabled."},
        401: {
            "description": "No credential, or an unknown one.",
            "model": ErrorResponseSchema,
        },
        404: {"description": "No catalogue entry for that capability."},
        503: {"description": "The model catalogue is unavailable."},
    },
)
async def describe_capability(
    capability: str,
    request: Request,
    caller: AuthenticatedCaller,
    model_router: RouterDep,
    registry: RegistryDep,
) -> ModelRouteResponseSchema:
    request.state.caller = caller
    route = model_router.resolve(capability=capability)
    entry = route.entry
    return ModelRouteResponseSchema(
        default_capability=model_router.default_capability,
        model=_card(entry),
        route=_route_card(route),
        provider_implemented=registry.is_registered(entry.provider),
    )


__all__ = ["router"]
