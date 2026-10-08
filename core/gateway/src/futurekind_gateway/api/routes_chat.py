"""``POST /chat`` — the one endpoint applications are expected to call.

This module is a door, and deliberately very little else. The order of
operations that makes the Gateway safe — authenticate the caller, resolve the
route so its policy is known, enforce that policy, and only then touch a model —
lives in :meth:`~futurekind_gateway.service.GatewayService.handle`, because the
OpenAI-compatible surface has to pass through the identical sequence. Two doors
with two rule books is how a platform ends up with the weaker one.

What stays here is what only this transport knows: the credential is attributed
before anything else happens, and a streaming request is refused at the door
rather than answered wrongly by the service.
"""

from __future__ import annotations

from fastapi import APIRouter, Request

from ..errors import FeatureNotImplementedError
from ..observability.logging import get_request_id
from ..schemas import ChatRequestSchema, ChatResponseSchema, ErrorResponseSchema
from .deps import AuthenticatedCaller, ServiceDep

router = APIRouter(tags=["chat"])

#: Shared OpenAPI descriptions for the failure modes of this endpoint.
CHAT_RESPONSES: dict[int | str, dict] = {
    200: {"description": "The model answered."},
    401: {
        "description": "No credential, or an unknown one.",
        "model": ErrorResponseSchema,
    },
    403: {
        "description": "The skill's policy requires an approval the Gateway cannot verify.",
        "model": ErrorResponseSchema,
    },
    404: {
        "description": "No skill or capability of that name exists in the catalogue.",
        "model": ErrorResponseSchema,
    },
    422: {
        "description": "The request is malformed or exceeds the limits its skill declares.",
        "model": ErrorResponseSchema,
    },
    501: {
        "description": "Routing succeeded but the provider is not implemented in this build.",
        "model": ErrorResponseSchema,
    },
    502: {
        "description": "The provider failed, or the whole chain was exhausted.",
        "model": ErrorResponseSchema,
    },
    503: {
        "description": (
            "Catalogue unavailable, auth required but unconfigured, or LiteLLM "
            "has no endpoint set."
        ),
        "model": ErrorResponseSchema,
    },
    504: {"description": "The provider did not answer in time.", "model": ErrorResponseSchema},
}


@router.post(
    "/chat",
    response_model=ChatResponseSchema,
    summary="Chat completion",
    description=(
        "Ask the platform for a completion by **skill** — what the application is "
        "doing — never by model. The Gateway authenticates the caller, resolves the "
        "skill to a capability and then to an alias, enforces the policy that skill "
        "declares, and hands the request to LiteLLM under the alias contract in "
        "`ADR-0002`. The answer comes back with the routing decision and the policy "
        "it ran under.\n\n"
        "A request body that names a model is rejected: model selection belongs to "
        "LiteLLM, and accepting it here would make every hardware change a breaking "
        "change for clinical applications.\n\n"
        "Naming a `skill` rather than a `capability` also selects a policy. A request "
        "that names only a capability runs under the default one, whose risk level is "
        "reported as `unspecified`.\n\n"
        "An interface that speaks the OpenAI wire format should use "
        "`POST /v1/chat/completions` instead, where `model` carries the skill name. "
        "Both doors enforce the same rules in the same order."
    ),
    operation_id="chatCompletion",
    responses=CHAT_RESPONSES,
)
async def chat(
    payload: ChatRequestSchema,
    request: Request,
    caller: AuthenticatedCaller,
    service: ServiceDep,
) -> ChatResponseSchema:
    # Attribution without a secret: the caller's digest label, never its key.
    request.state.caller = caller

    if payload.stream:
        raise FeatureNotImplementedError(
            "Streaming responses are part of the contract but are not implemented in this build",
            details={"feature": "streaming", "use_instead": "stream=false"},
        )

    outcome = await service.handle(payload.to_intent(), request_id=get_request_id())
    return ChatResponseSchema(**outcome.to_response_dict())


__all__ = ["CHAT_RESPONSES", "router"]
