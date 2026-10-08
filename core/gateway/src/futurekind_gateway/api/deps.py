"""FastAPI dependencies: application state and caller authentication."""

from __future__ import annotations

import hashlib
import secrets
from typing import Annotated

from fastapi import Depends, Header, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from ..config import GatewaySettings
from ..errors import (
    AuthenticationError,
    AuthenticationNotConfiguredError,
    CatalogError,
)
from ..providers import ProviderRegistry
from ..routing import ModelRouter
from ..service import GatewayService

#: Declared so the generated OpenAPI documents the credential header.
#: ``auto_error=False`` keeps FastAPI from answering 403 before our own 401/503 logic runs.
bearer_scheme = HTTPBearer(
    auto_error=False,
    description="Gateway API key issued to the calling application.",
)

API_KEY_HEADER = "X-FK-Api-Key"


def get_settings(request: Request) -> GatewaySettings:
    return request.app.state.settings


def get_catalog(request: Request):  # noqa: ANN401 - ModelCatalog or None during a failed start
    return getattr(request.app.state, "catalog", None)


def get_registry(request: Request) -> ProviderRegistry:
    registry: ProviderRegistry = request.app.state.registry
    return registry


def _require_initialised(request: Request, surface: str) -> None:
    """A Gateway that could not load its catalogue serves health checks, not traffic."""
    if getattr(request.app.state, surface, None) is None:
        reason = getattr(request.app.state, "catalog_error", None) or "not initialised"
        raise CatalogError(
            f"The Gateway cannot serve this request: {reason}",
            details={"reason": reason},
        )


def get_router(request: Request) -> ModelRouter:
    _require_initialised(request, "router")
    router: ModelRouter = request.app.state.router
    return router


def get_service(request: Request) -> GatewayService:
    _require_initialised(request, "service")
    service: GatewayService = request.app.state.service
    return service


def caller_label(presented: str) -> str:
    """A stable, non-secret identity for log and metric lines.

    Never the key itself, and not a prefix either: eight hex characters of the
    digest identify a credential without making the log a copy of it.
    """
    return hashlib.sha256(presented.encode("utf-8")).hexdigest()[:8]


async def require_api_key(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    api_key_header: Annotated[str | None, Header(alias=API_KEY_HEADER)] = None,
) -> str:
    """Authenticate the caller and return its non-secret label.

    Fails closed. If authentication is switched on but no keys are configured,
    the Gateway refuses traffic with 503 rather than admitting everyone — the
    pattern already proven on the CARE OCR worker.
    """
    settings = get_settings(request)
    if not settings.require_auth:
        return "anonymous"

    if not settings.api_keys:
        raise AuthenticationNotConfiguredError(
            "Authentication is required but FK_GATEWAY_API_KEYS is empty — "
            "refusing to serve unauthenticated AI traffic",
            details={"configured_keys": 0},
        )

    presented: str | None = None
    if credentials is not None and credentials.credentials:
        presented = credentials.credentials.strip()
    elif api_key_header:
        presented = api_key_header.strip()

    if not presented:
        raise AuthenticationError(
            "Provide the Gateway API key as 'Authorization: Bearer <key>' "
            f"or '{API_KEY_HEADER}: <key>'",
            details={"schemes": ["bearerAuth", API_KEY_HEADER]},
        )

    for candidate in settings.api_keys:
        if secrets.compare_digest(presented, candidate):
            return caller_label(presented)

    # Deliberately identical wording for "unknown key" and "wrong key".
    raise AuthenticationError(
        "The API key presented is not recognised by this Gateway",
        details={"presented_length": len(presented)},
    )


AuthenticatedCaller = Annotated[str, Depends(require_api_key)]
SettingsDep = Annotated[GatewaySettings, Depends(get_settings)]
ServiceDep = Annotated[GatewayService, Depends(get_service)]
RouterDep = Annotated[ModelRouter, Depends(get_router)]
RegistryDep = Annotated[ProviderRegistry, Depends(get_registry)]

__all__ = [
    "API_KEY_HEADER",
    "AuthenticatedCaller",
    "RegistryDep",
    "SettingsDep",
    "ServiceDep",
    "bearer_scheme",
    "caller_label",
    "get_catalog",
    "get_registry",
    "get_router",
    "get_service",
    "get_settings",
    "require_api_key",
]
