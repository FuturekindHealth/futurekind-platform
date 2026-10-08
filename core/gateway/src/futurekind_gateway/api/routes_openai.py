"""``/v1`` — the OpenAI-compatible door, so an interface never has to reach LiteLLM.

``docs/ARCHITECTURE.md:106`` says all AI traffic passes through the Gateway, and
every deployment document so far assumed an interface would be configured with
LiteLLM's address to get there. That is the same sentence contradicted twice: the
rule is only true if there is something on the platform's own address that a
generic OpenAI client can talk to.

So this is a translation layer, and nothing more. Both operations convert to a
:class:`~futurekind_gateway.intents.ChatIntent` and call
:meth:`~futurekind_gateway.service.GatewayService.handle` — the same route
resolution, the same policy enforcement, the same alias, the same audit line as
``POST /chat``. There is no second code path here to weaken.

The reinterpretation is the part worth reading twice: on this surface ``model``
means **skill**. It has to, because a skill is the only name an application may
choose, and an interface's model picker is the one place a clinician selects what
answers. Listing deployments there would hand back the infrastructure selection
``ADR-0002`` deliberately took away — which is also why ``GET /v1/models`` returns
no provider and no model id, unlike ``GET /models``.
"""

from __future__ import annotations

import time

from fastapi import APIRouter, Request

from ..errors import FeatureNotImplementedError
from ..observability.logging import get_request_id
from ..schemas import (
    ErrorResponseSchema,
    OpenAIChatCompletionMessageSchema,
    OpenAIChatCompletionSchema,
    OpenAIChatRequestSchema,
    OpenAIChoiceSchema,
    OpenAIModelListSchema,
    OpenAIModelSchema,
    OpenAIUsageSchema,
)
from ..service import ChatOutcome
from .deps import AuthenticatedCaller, RouterDep, ServiceDep, SettingsDep

router = APIRouter(prefix="/v1", tags=["openai-compat"])

#: Failure modes shared by both operations, in the Gateway's own error envelope —
#: a client that only branches on the HTTP status still gets what it expects.
COMPAT_RESPONSES: dict[int | str, dict] = {
    200: {"description": "The request was served."},
    401: {"description": "No credential, or an unknown one.", "model": ErrorResponseSchema},
    403: {
        "description": "The skill's policy requires an approval the Gateway cannot verify.",
        "model": ErrorResponseSchema,
    },
    404: {
        "description": "No skill of that name. See `GET /v1/models`.",
        "model": ErrorResponseSchema,
    },
    422: {
        "description": "Malformed request, or one that exceeds its skill's limits.",
        "model": ErrorResponseSchema,
    },
    501: {
        "description": "`stream: true`, or a route whose provider is not implemented.",
        "model": ErrorResponseSchema,
    },
    502: {
        "description": "LiteLLM failed, or the fallback chain was exhausted.",
        "model": ErrorResponseSchema,
    },
    503: {
        "description": "Catalogue, credential or endpoint configuration unavailable.",
        "model": ErrorResponseSchema,
    },
    504: {"description": "LiteLLM did not answer in time.", "model": ErrorResponseSchema},
}


def _now() -> int:
    """Unix seconds, for the two `created` fields OpenAI clients expect to read."""
    return int(time.time())


@router.get(
    "/models",
    response_model=OpenAIModelListSchema,
    summary="Selectable skills, in OpenAI's format",
    description=(
        "Every enabled skill, dressed as an OpenAI model so an interface can list "
        "them in its picker. The `id` is a skill name to send back in `model`. "
        "Capabilities, aliases, providers and model ids are deliberately absent: "
        "this endpoint exists to let a clinician choose intent, not infrastructure, "
        "and it requires a credential because it is an application-facing door."
    ),
    operation_id="openaiListModels",
    responses={
        200: {"description": "The skills an application may name."},
        401: {"description": "No credential, or an unknown one.", "model": ErrorResponseSchema},
        503: {"description": "The model catalogue is unavailable.", "model": ErrorResponseSchema},
    },
)
async def list_models(
    request: Request,
    caller: AuthenticatedCaller,
    model_router: RouterDep,
    settings: SettingsDep,
) -> OpenAIModelListSchema:
    """The credential is resolved before the catalogue, on purpose.

    FastAPI resolves dependencies in declaration order. ``get_router`` raises a
    ``CatalogError`` quoting the file it could not read, so a route that asks for the
    catalogue first answers an anonymous caller with a server path whenever the
    deployment is misconfigured — the one state that guarantees the message. The same
    ordering rule holds on ``/chat``, ``/v1/chat/completions`` and ``GET /models``, and
    ``test_a_broken_catalogue_never_answers_an_anonymous_caller_with_a_path`` keeps it.
    """
    request.state.caller = caller
    created = _now()
    return OpenAIModelListSchema(
        data=[
            OpenAIModelSchema(
                id=skill.name,
                created=created,
                owned_by=settings.service_name,
            )
            for skill in model_router.catalog.enabled_skills()
        ]
    )


@router.post(
    "/chat/completions",
    response_model=OpenAIChatCompletionSchema,
    summary="Chat completion by skill, in OpenAI's format",
    description=(
        "The OpenAI-compatible completion endpoint. `model` carries a **skill** "
        "from `GET /v1/models`; it is never a model id, and an unknown name returns "
        "`404 unknown_skill` with the list of real ones.\n\n"
        "Policy is not negotiable here: the skill's clinical risk, approval, audit, "
        "downgrade and size limits are enforced exactly as on `POST /chat`, because "
        "the same function enforces them. Sampling knobs this platform does not model "
        "(`n`, `presence_penalty`, `seed` and friends) are ignored rather than "
        "forwarded to a model.\n\n"
        "`stream: true` returns `501`: streaming needs its cancellation and audit "
        "semantics specified before it can be implemented (SPEC-15-03), so configure "
        "the client for non-streaming responses until then.\n\n"
        "The response's `id` is the Gateway request id, so a screenshot is enough to "
        "find the audit line behind it."
    ),
    operation_id="openaiChatCompletion",
    responses=COMPAT_RESPONSES,
)
async def chat_completions(
    payload: OpenAIChatRequestSchema,
    request: Request,
    caller: AuthenticatedCaller,
    service: ServiceDep,
) -> OpenAIChatCompletionSchema:
    request.state.caller = caller

    if payload.stream:
        raise FeatureNotImplementedError(
            "Streaming responses are part of the contract but are not implemented in this build",
            details={
                "feature": "streaming",
                "use_instead": "stream=false",
                "specification": "SPEC-15-03",
            },
        )

    outcome = await service.handle(payload.to_intent(), request_id=get_request_id())
    return to_openai_completion(outcome, request_id=get_request_id())


def to_openai_completion(
    outcome: ChatOutcome, *, request_id: str | None
) -> OpenAIChatCompletionSchema:
    """Render one Gateway outcome as an OpenAI completion.

    Only four things cross over: the text, why it stopped, its token counts and
    the skill that produced it. ``outcome.model`` and ``outcome.provider`` stay
    behind on this door — they are the internal inventory ``GET /models`` reports
    for operators, and an interface has no use for a weights id it cannot select.
    """
    return OpenAIChatCompletionSchema(
        id=request_id or outcome.request_id or "",
        created=_now(),
        model=outcome.skill or outcome.capability,
        choices=[
            OpenAIChoiceSchema(
                message=OpenAIChatCompletionMessageSchema(content=outcome.content),
                finish_reason=outcome.finish_reason,
            )
        ],
        usage=OpenAIUsageSchema(
            prompt_tokens=outcome.usage.prompt_tokens,
            completion_tokens=outcome.usage.completion_tokens,
            total_tokens=outcome.usage.total_tokens,
        ),
    )


__all__ = ["COMPAT_RESPONSES", "router", "to_openai_completion"]
