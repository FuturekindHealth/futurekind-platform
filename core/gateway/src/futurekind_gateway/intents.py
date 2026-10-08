"""One request's intent, before any transport has shaped it.

The Gateway now has two doors and one rule book. ``POST /chat`` speaks
FutureKind (a skill, a capability); the OpenAI-compatible surface speaks OpenAI
(a ``model`` field that carries a skill name, ``messages``, sampling knobs).
:class:`ChatIntent` is the shape both translate into and nothing else — the
point is that route resolution, policy enforcement and invocation exist in
exactly one place (:meth:`~futurekind_gateway.service.GatewayService.handle`),
so a second door cannot become a second set of rules.

An intent states what was asked, never what is allowed. Governance still comes
from the catalogue for the skill it names: an intent carries no clinical risk
level, no approval flag and no limit, because a caller that could fill those in
would be writing its own policy.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from .providers.base import ChatMessage, ChatRequest


@dataclass(frozen=True)
class ChatIntent:
    """What a caller asked for, in the Gateway's own vocabulary."""

    skill: str | None = None
    capability: str | None = None
    messages: tuple[ChatMessage, ...] = ()
    temperature: float | None = None
    max_tokens: int | None = None
    stop: tuple[str, ...] = ()
    #: Passthrough for provider-specific knobs. Unknown keys are ignored by
    #: providers, which is what lets the OpenAI surface drop the fields this
    #: platform does not model without refusing a well-formed client.
    parameters: Mapping[str, Any] = field(default_factory=dict)

    @property
    def message_count(self) -> int:
        return len(self.messages)

    @property
    def longest_message_chars(self) -> int:
        return max((len(message.content) for message in self.messages), default=0)

    @classmethod
    def of(
        cls,
        *,
        skill: str | None = None,
        capability: str | None = None,
        messages: Sequence[ChatMessage],
        temperature: float | None = None,
        max_tokens: int | None = None,
        stop: Sequence[str] = (),
        parameters: Mapping[str, Any] | None = None,
    ) -> ChatIntent:
        """Build an intent from either transport, normalising the containers.

        The keyword-only signature is the seam: a new transport expresses the
        same five things — which skill, which turns, how much to sample — and
        cannot quietly add a sixth field that only that transport honours.
        """
        return cls(
            skill=skill,
            capability=capability,
            messages=tuple(messages),
            temperature=temperature,
            max_tokens=max_tokens,
            stop=tuple(stop),
            parameters=dict(parameters or {}),
        )

    def to_provider_request(self, *, model: str) -> ChatRequest:
        """The provider-facing request, once routing has chosen what to address.

        ``model`` is the name the Gateway sends to *its* provider — the alias,
        under ``ADR-0002`` — and it arrives from routing rather than from here,
        because an intent must not be able to carry infrastructure.
        """
        return ChatRequest(
            model=model,
            messages=self.messages,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            stop=self.stop,
            extra=self.parameters,
        )


__all__ = ["ChatIntent"]
