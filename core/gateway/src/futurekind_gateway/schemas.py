"""Pydantic models — the Gateway's public REST contract.

Every field carries a description because these strings *are* the OpenAPI
documentation served at ``/docs`` and ``/openapi.json``.  The request models
validate shape (types, bounds, allowed roles); the limits an operator can tune
(``FK_GATEWAY_MAX_MESSAGES`` and friends) are enforced by the request handler so
they stay configurable without rebuilding a schema class.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .intents import ChatIntent
from .providers.base import ChatMessage

#: Mirrors ``providers.base.VALID_ROLES``. Kept as a Literal so it appears in the schema.
Role = Literal["system", "user", "assistant"]

#: Hard ceiling on a single message's size. Protects the process from an accidental
#: multi-megabyte payload regardless of the operator-configured limit.
ABSOLUTE_MAX_CONTENT_CHARS = 1_000_000


class _Base(BaseModel):
    model_config = ConfigDict(
        # `model` is a legitimate field name for an AI model id; it is not shadowing anything.
        protected_namespaces=(),
        str_strip_whitespace=True,
    )


class ChatMessageSchema(_Base):
    """One turn in a conversation."""

    role: Role = Field(description="Whose utterance this is.")
    content: str = Field(
        min_length=1,
        max_length=ABSOLUTE_MAX_CONTENT_CHARS,
        description="The message text.",
        examples=["Summarise this impression for the referring clinician."],
    )

    def to_domain(self) -> ChatMessage:
        return ChatMessage(role=self.role, content=self.content)


class ChatRequestSchema(_Base):
    """A chat request. Applications name an intent, never infrastructure.

    There is deliberately no field here that accepts a model, provider or
    endpoint: ``ADR-0002`` assigns those to LiteLLM, and accepting them would
    make every hardware change a breaking change for clinical applications.
    """

    model_config = ConfigDict(
        protected_namespaces=(),
        str_strip_whitespace=True,
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "skill": "radiology-report",
                    "messages": [{"role": "user", "content": "List the differential."}],
                }
            ]
        },
    )

    skill: str | None = Field(
        default=None,
        min_length=1,
        max_length=64,
        description=(
            "What the application is doing: 'radiology-report', 'clinical-chat', "
            "'summarize-document', 'pathology-review'. This is the selector "
            "applications are meant to use, and the only one that states clinical "
            "intent."
        ),
        examples=["radiology-report"],
    )
    capability: str | None = Field(
        default=None,
        min_length=1,
        max_length=64,
        description=(
            "Technical routing class, e.g. 'default', 'fast' or 'reasoning'. "
            "Prefer 'skill': a capability names how the work is processed, not what "
            "the clinician is doing. When both are supplied the skill wins and the "
            "two must agree. Omit both to use the Gateway's default capability."
        ),
    )
    messages: list[ChatMessageSchema] = Field(
        min_length=1,
        description="Conversation turns, oldest first.",
    )
    temperature: float | None = Field(
        default=None,
        ge=0.0,
        le=2.0,
        description="Sampling temperature, when the provider supports it.",
    )
    max_tokens: int | None = Field(
        default=None,
        ge=1,
        description="Upper bound on generated tokens.",
    )
    stop: list[str] = Field(
        default_factory=list,
        max_length=8,
        description="Stop sequences.",
    )
    stream: bool = Field(
        default=False,
        description=(
            "Streaming is declared in the contract but not implemented in this "
            "skeleton; setting it to true returns 501."
        ),
    )
    parameters: dict[str, Any] = Field(
        default_factory=dict,
        description="Provider-specific passthrough. Unknown keys are ignored by providers.",
    )

    def to_intent(self) -> ChatIntent:
        """Hand this request to the one code path that enforces the rules.

        Deliberately a *translation*, not a validation step: routing, policy and
        limits live in ``GatewayService.handle`` so that the OpenAI-compatible
        surface cannot drift into a second, laxer door.
        """
        return ChatIntent.of(
            skill=self.skill,
            capability=self.capability,
            messages=[message.to_domain() for message in self.messages],
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            stop=self.stop,
            parameters=self.parameters,
        )


class TokenUsageSchema(_Base):
    """Token accounting as reported by the provider."""

    prompt_tokens: int = Field(default=0, ge=0, description="Tokens consumed by the prompt.")
    completion_tokens: int = Field(default=0, ge=0, description="Tokens generated.")
    total_tokens: int = Field(default=0, ge=0, description="prompt_tokens + completion_tokens.")


class SkillPolicySchema(_Base):
    """The governance an operator declared for one skill.

    Reported so an application can act on it — a skill whose answer needs
    sign-off has to look different on screen from one that does not.  The
    numeric limits a policy may also carry are deliberately absent: they are
    deployment tuning, and publishing them teaches a caller to size a request
    to the ceiling.
    """

    clinical_risk: str = Field(
        description=(
            "Clinical consequence of getting this answer wrong: 'low', 'moderate', "
            "'high', 'critical' — or 'unspecified' when no skill was named, which "
            "means nobody assessed it."
        )
    )
    approval_required: bool = Field(
        description=(
            "True when a clinician must sign the result off. The Gateway cannot verify "
            "an approval yet, so a skill declared this way refuses rather than proceeding."
        )
    )
    audit_required: bool = Field(
        description="True when every request for this skill writes an audit record."
    )
    allow_downgrade: bool = Field(
        description=(
            "False when a lesser model may not answer in place of the routed one. "
            "High and critical risk skills are forced to false when the catalogue loads."
        )
    )


class ChatResponseSchema(_Base):
    """A completed chat request, with the routing decision attached."""

    request_id: str = Field(description="Correlates this result with Gateway log lines.")
    skill: str | None = Field(
        default=None, description="The skill the caller asked for, if one was supplied."
    )
    capability: str = Field(description="The capability the skill resolved to.")
    model: str = Field(
        description=(
            "The model that actually answered. Reported for provenance and audit only "
            "— it is not accepted as input (ADR-0002)."
        )
    )
    provider: str = Field(description="The backend that carried the request.")
    selected_by: str = Field(
        description="How routing chose this entry: 'skill', 'capability' or 'default'."
    )
    policy: SkillPolicySchema = Field(
        description=(
            "The policy this request ran under, as declared for its skill. Reported so "
            "an application can tell a clinician whether the answer still needs sign-off."
        )
    )
    attempts: int = Field(ge=1, description="Provider invocations made, including fallbacks.")
    degraded: bool = Field(
        description="True when a fallback capability answered instead of the primary."
    )
    content: str = Field(description="The generated text.")
    finish_reason: str | None = Field(
        default=None, description="Provider-supplied reason the generation stopped."
    )
    usage: TokenUsageSchema = Field(description="Token accounting for this completion.")
    latency_ms: int = Field(ge=0, description="Gateway-measured end-to-end latency.")


class SkillCardSchema(SkillPolicySchema):
    """One declared application intent, and the rules it runs under.

    The policy fields are inherited rather than restated, so a skill card and the
    policy reported on a completion cannot drift into two vocabularies.
    """

    name: str = Field(description="The identifier an application sends in 'skill'.")
    capability: str = Field(description="The technical capability that serves this skill.")
    description: str = Field(default="", description="Operator-authored note.")
    enabled: bool = Field(description="False when the skill is deliberately withdrawn.")


class ModelCardSchema(_Base):
    """One capability row in the catalogue."""

    capability: str = Field(description="Technical routing class, not an application intent.")
    provider: str = Field(description="Provider backend that serves this capability.")
    model: str = Field(
        description="Internal model id. Visible for provenance; never accepted as input."
    )
    description: str = Field(default="", description="Operator-authored note.")
    enabled: bool = Field(description="False when deliberately taken out of rotation.")
    fallbacks: list[str] = Field(
        default_factory=list, description="Capabilities tried, in order, if this one fails."
    )


class RouteCardSchema(_Base):
    """The resolved fallback chain for one capability."""

    capability: str
    provider: str
    model: str
    chain: list[str] = Field(description="Capabilities attempted in order, primary first.")


class ModelListResponseSchema(_Base):
    """What ``GET /models`` returns."""

    default_capability: str
    count: int = Field(ge=0)
    skills: list[SkillCardSchema] = Field(
        description=(
            "What applications may ask for. This is the application-facing list; "
            "'models' below is the internal routing table next to it."
        )
    )
    models: list[ModelCardSchema]
    routes: list[RouteCardSchema] = Field(
        description="Resolved chains. Disabled entries do not appear here."
    )
    providers_registered: list[str] = Field(
        description="Providers this build can actually invoke."
    )
    providers_missing: list[str] = Field(
        description="Providers the catalogue needs but this build cannot serve."
    )


class ModelRouteResponseSchema(_Base):
    """What ``GET /models/{capability}`` returns."""

    default_capability: str
    model: ModelCardSchema
    route: RouteCardSchema
    provider_implemented: bool = Field(
        description="False until a Provider implementation is registered for this backend."
    )


# -- the OpenAI-compatible surface -------------------------------------------------------------
#
# These schemas exist for one reason: an interface such as Open WebUI speaks the
# OpenAI wire format and nothing else, and the platform rule says it must not
# reach LiteLLM directly. So the Gateway grows a second *door*, not a second set
# of rules — every request shaped here is translated into the same ChatIntent and
# executed by the same service path as `POST /chat`.
#
# The one field that means something different on this door is `model`: it carries
# a **skill**, because a skill is the only thing an application may name. Nothing
# on this surface accepts or returns a model id, a provider or an endpoint, which
# makes it stricter than the OpenAI contract it imitates, not looser.


class OpenAIChatMessageSchema(_Base):
    """One conversation turn, in OpenAI's wire shape.

    ``content`` is a string, always. OpenAI also allows an array of content
    *parts* for vision; this Gateway declares no vision capability, and accepting
    an array only to drop its images would lose clinical data in silence. A client
    that sends one is refused with ``422`` instead.
    """

    role: Role = Field(description="Whose utterance this is.")
    content: str = Field(
        min_length=1,
        max_length=ABSOLUTE_MAX_CONTENT_CHARS,
        description="The message text. Must be non-empty, as on POST /chat.",
    )

    def to_domain(self) -> ChatMessage:
        return ChatMessage(role=self.role, content=self.content)


class OpenAIChatRequestSchema(_Base):
    """An OpenAI-format chat request, read as an intent rather than as infrastructure.

    Unknown fields are ignored rather than refused: Open WebUI and its cousins
    send a long tail of sampling knobs, and a clinical interface should not break
    because one arrived. Ignored here means *not forwarded* — nothing reaches a
    model except what ``GatewayService`` puts in the provider request, so the
    lenient door cannot become a back door for parameters the platform has not
    reviewed.
    """

    model_config = ConfigDict(
        protected_namespaces=(),
        str_strip_whitespace=True,
        extra="ignore",
        json_schema_extra={
            "examples": [
                {
                    "model": "platform-chat",
                    "messages": [{"role": "user", "content": "What can this platform do?"}],
                }
            ]
        },
    )

    model: str = Field(
        min_length=1,
        max_length=64,
        description=(
            "The **skill** to run — a FutureKind intent such as `platform-chat`, "
            "never a model id. `GET /v1/models` lists the names this Gateway will "
            "accept here. An unknown name is `404 unknown_skill`."
        ),
        examples=["platform-chat"],
    )
    messages: list[OpenAIChatMessageSchema] = Field(
        min_length=1,
        description="Conversation turns, oldest first.",
    )
    temperature: float | None = Field(
        default=None,
        ge=0.0,
        le=2.0,
        description="Sampling temperature, when the deployment behind the alias supports it.",
    )
    max_tokens: int | None = Field(
        default=None,
        ge=1,
        description="Upper bound on generated tokens, inside the skill's own ceiling.",
    )
    stop: list[str] | None = Field(
        default=None,
        description="Stop sequences. OpenAI permits a bare string; both forms are accepted.",
    )
    stream: bool = Field(
        default=False,
        description=(
            "Must stay false. Streaming is declared in the contract and refused "
            "with `501` until its cancellation and audit semantics are specified "
            "(SPEC-15-03); configure the client for non-streaming responses."
        ),
    )

    @field_validator("stop", mode="before")
    @classmethod
    def _accept_openai_stop_forms(cls, value: Any) -> Any:
        if isinstance(value, str):
            return [value]
        return value

    def to_intent(self) -> ChatIntent:
        """Route by skill name, exactly as `POST /chat` does.

        The mapping of ``model`` onto a skill is the whole translation. It is
        one-way: no field on this schema can name a capability, an alias or a
        deployment, so an interface that wants the technical selector has to ask
        for the skill that uses it.
        """
        return ChatIntent.of(
            skill=self.model,
            messages=[message.to_domain() for message in self.messages],
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            stop=self.stop or (),
        )


class OpenAIChatCompletionMessageSchema(_Base):
    """The assistant turn, as OpenAI clients expect to read it."""

    role: Literal["assistant"] = Field(default="assistant", description="Always `assistant`.")
    content: str = Field(description="The generated text.")


class OpenAIChoiceSchema(_Base):
    """One candidate answer. This Gateway always returns exactly one."""

    index: int = Field(default=0, description="Position in the choices array.")
    message: OpenAIChatCompletionMessageSchema = Field(description="The answer.")
    finish_reason: str | None = Field(
        default=None,
        description="Why generation stopped, as the deployment behind the alias reported it.",
    )
    logprobs: None = Field(
        default=None,
        description="Always null. Token log probabilities are not part of this contract.",
    )


class OpenAIUsageSchema(_Base):
    """Token accounting in OpenAI's field names."""

    prompt_tokens: int = Field(default=0, ge=0, description="Tokens consumed by the prompt.")
    completion_tokens: int = Field(default=0, ge=0, description="Tokens generated.")
    total_tokens: int = Field(default=0, ge=0, description="The sum of the two.")


class OpenAIChatCompletionSchema(_Base):
    """An OpenAI-format completion.

    ``model`` echoes the **skill** that answered, never the weights behind it, and
    ``id`` is the Gateway request id so that a screenshot from an interface is
    enough to find the audit line.
    """

    id: str = Field(description="The Gateway request id, identical to the one /chat returns.")
    object: Literal["chat.completion"] = Field(default="chat.completion")
    created: int = Field(description="Unix seconds at completion time.")
    model: str = Field(description="The skill that answered — not a model id.")
    choices: list[OpenAIChoiceSchema] = Field(description="Exactly one choice.")
    usage: OpenAIUsageSchema = Field(description="Token accounting for this completion.")


class OpenAIModelSchema(_Base):
    """One selectable skill, dressed as an OpenAI model.

    Open WebUI's model picker is the only place a clinician chooses what answers,
    so the picker has to list intents. Listing deployments there would hand the
    interface the infrastructure selection ``ADR-0002`` removed from it.
    """

    id: str = Field(description="The skill name to send in `model`.")
    object: Literal["model"] = Field(default="model")
    created: int = Field(description="Unix seconds; catalogue-derived, so effectively stable.")
    owned_by: str = Field(description="The Gateway service that publishes this skill.")


class OpenAIModelListSchema(_Base):
    """What `GET /v1/models` returns."""

    object: Literal["list"] = Field(default="list")
    data: list[OpenAIModelSchema] = Field(
        description="Every enabled skill, in catalogue order. No disabled skill appears."
    )


class ComponentHealthSchema(_Base):
    """One health check result."""

    name: str
    healthy: bool
    detail: str | None = None


class HealthResponseSchema(_Base):
    """What ``GET /health`` returns. Always 200 while the process is up.

    Deliberately small. A liveness probe has no credential and every container
    runtime on the network can read this answer, so it carries process state and
    component verdicts only — no catalogue path, no provider inventory, no routing.
    That is ``docs/CONSTITUTION.md`` P10 applied to the health door: an operator
    who wants the inventory authenticates and reads ``GET /models``.
    """

    status: Literal["ok", "degraded"] = Field(
        description="'degraded' when a component is unhealthy but the process answers."
    )
    service: str
    version: str
    checked_at: str = Field(description="UTC ISO-8601 timestamp.")
    components: list[ComponentHealthSchema]
    authentication: bool = Field(
        description="True when caller credentials are enforced on write endpoints."
    )


class ReadinessResponseSchema(_Base):
    """What ``GET /health/ready`` returns. 503 when the Gateway should receive no traffic."""

    ready: bool
    checked_at: str
    reasons: list[str] = Field(
        default_factory=list,
        description="Human-readable blockers, empty when ready.",
    )


class ErrorBodySchema(_Base):
    """The single error shape every endpoint can return."""

    code: str = Field(description="Stable machine-readable identifier to branch on.")
    message: str = Field(description="Operator-facing explanation. Never contains patient text.")
    retryable: bool = Field(description="Whether repeating this request may succeed.")
    request_id: str | None = Field(default=None, description="Correlates with Gateway logs.")
    details: dict[str, Any] | None = Field(default=None)


class ErrorResponseSchema(_Base):
    """Error envelope."""

    error: ErrorBodySchema


__all__ = [
    "ABSOLUTE_MAX_CONTENT_CHARS",
    "ChatMessageSchema",
    "ChatRequestSchema",
    "ChatResponseSchema",
    "ComponentHealthSchema",
    "ErrorBodySchema",
    "ErrorResponseSchema",
    "HealthResponseSchema",
    "ModelCardSchema",
    "ModelListResponseSchema",
    "ModelRouteResponseSchema",
    "OpenAIChatCompletionMessageSchema",
    "OpenAIChatCompletionSchema",
    "OpenAIChatMessageSchema",
    "OpenAIChatRequestSchema",
    "OpenAIChoiceSchema",
    "OpenAIModelListSchema",
    "OpenAIModelSchema",
    "OpenAIUsageSchema",
    "ReadinessResponseSchema",
    "Role",
    "RouteCardSchema",
    "SkillCardSchema",
    "SkillPolicySchema",
    "TokenUsageSchema",
]
