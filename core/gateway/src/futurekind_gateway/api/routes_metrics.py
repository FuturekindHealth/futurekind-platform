"""``GET /metrics`` — Prometheus exposition.

Requires a credential.  It used to be public on the theory that a counter is not
a secret, but the exposition carries label values: which providers exist, which
model ids answer each capability, which routing chains the catalogue declares.
That is the internal inventory ``docs/CONSTITUTION.md`` P8 keeps away from
anything that has not been authorised, and a scrape endpoint on a hospital
network is reachable by things that were never authorised.

Prometheus supports a bearer token on its scrape config
(``authorization: {credentials_file: ...}``), so authenticating the scrape is a
deployment setting, not a code change.  Nothing in this repository ships a
Prometheus, so nothing here is broken by the gate today.

The payload still carries no prompt, no completion and no caller identity beyond
a hashed key label.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import Response

from ..schemas import ErrorResponseSchema
from .deps import AuthenticatedCaller

router = APIRouter(tags=["metrics"])


@router.get(
    "/metrics",
    summary="Prometheus Metrics",
    description=(
        "The Gateway's metrics in Prometheus text exposition format. "
        "Requires a credential because the label values name providers and models."
    ),
    response_class=Response,
    responses={
        200: {"description": "Metrics.", "content": {"text/plain": {}}},
        401: {"description": "No credential, or an unknown one.", "model": ErrorResponseSchema},
    },
)
async def metrics(request: Request, caller: AuthenticatedCaller) -> Response:
    request.state.caller = caller
    body, content_type = request.app.state.metrics.render()
    return Response(content=body, media_type=content_type)


__all__ = ["router"]
