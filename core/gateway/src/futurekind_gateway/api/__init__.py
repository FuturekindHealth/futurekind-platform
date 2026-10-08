"""HTTP surface of the Gateway.

Two doors, one rule book: ``/chat`` speaks FutureKind and ``/v1`` speaks OpenAI,
and both hand the same intent to :class:`~futurekind_gateway.service.GatewayService`
so that policy enforcement exists in exactly one place.
"""

from __future__ import annotations

from .routes_chat import router as chat_router
from .routes_health import router as health_router
from .routes_metrics import router as metrics_router
from .routes_models import router as models_router
from .routes_openai import router as openai_router

#: Included by the application factory in this order so /docs reads top-down:
#: the platform's own door first, then the compatible one, then introspection.
ROUTERS = (chat_router, openai_router, models_router, health_router, metrics_router)

__all__ = [
    "ROUTERS",
    "chat_router",
    "health_router",
    "metrics_router",
    "models_router",
    "openai_router",
]
