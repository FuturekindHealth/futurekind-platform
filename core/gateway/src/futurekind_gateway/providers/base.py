"""The provider contract — one interface behind which every AI backend sits.

A provider adapts one concrete backend (LiteLLM today; Ollama and any cloud API
stay on the far side of it, per ``ADR-0002``) to the Gateway's single vocabulary.
The Gateway depends only on this module: it never imports a backend, and no
backend ever sees a platform capability name — it receives the resolved alias and
standard sampling parameters.

Adding a provider is still a three-step act that changes nothing in the HTTP or
routing layers:

1. subclass :class:`Provider`,
2. set a unique :attr:`Provider.name`,
3. register a factory with
   :class:`~futurekind_gateway.providers.ProviderRegistry`.

A route whose provider answers to none of those gets ``501
provider_not_implemented``, naming the provider so the gap is explicit. That is
the expected answer for a catalogue row pointing at a backend nobody has wired —
not for LiteLLM, which the deployed Gateway implements.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, ClassVar

ROLE_SYSTEM = "system"
ROLE_USER = "user"
ROLE_ASSISTANT = "assistant"
VALID_ROLES = (ROLE_SYSTEM, ROLE_USER, ROLE_ASSISTANT)


class ProviderError(Exception):
    """Base class for anything that goes wrong inside a provider.

    ``retryable`` decides whether the service layer may move to the next
    candidate in the fallback chain.  Defaults to ``False`` on purpose: an
    unknown failure is not silently retried against a clinical request.
    """

    retryable: bool = False

    def __init__(self, message: str, *, provider: str | None = None) -> None:
        self.provider = provider
        super().__init__(message)


class ProviderUnavailableError(ProviderError):
    """The backend is down, refusing connections, or overloaded."""

    retryable = True


class ProviderTimeoutError(ProviderError):
    """The backend did not answer in time."""

    retryable = True


class ProviderRateLimitedError(ProviderError):
    """The backend throttled us; a different candidate may still answer."""

    retryable = True


class ProviderAuthenticationError(ProviderError):
    """Our credentials for this backend were rejected — retrying cannot help."""

    retryable = False


class ProviderRequestRejectedError(ProviderError):
    """The backend understood the request and refused it (bad input, safety block)."""

    retryable = False


class ProviderResponseInvalidError(ProviderError):
    """The backend answered, but not in the shape the contract requires."""

    retryable = False


@dataclass(frozen=True)
class ChatMessage:
    """One turn in a conversation."""

    role: str
    content: str

    def __post_init__(self) -> None:
        if self.role not in VALID_ROLES:
            raise ValueError(
                f"Unsupported message role '{self.role}'; expected one of {', '.join(VALID_ROLES)}"
            )
        if not isinstance(self.content, str):
            raise ValueError("Message content must be a string")

    def to_dict(self) -> dict[str, str]:
        return {"role": self.role, "content": self.content}


@dataclass(frozen=True)
class ChatRequest:
    """Everything a provider needs to produce one completion.

    ``model`` is the resolved provider-native model id, never a capability.
    """

    model: str
    messages: tuple[ChatMessage, ...]
    temperature: float | None = None
    max_tokens: int | None = None
    stop: tuple[str, ...] = ()
    #: Provider-specific passthrough. Providers must ignore keys they do not know.
    extra: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.model:
            raise ValueError("ChatRequest requires a resolved model id")
        if not self.messages:
            raise ValueError("ChatRequest requires at least one message")

    def to_dict(self) -> dict[str, Any]:
        """OpenAI-compatible payload shape, which most backends already accept."""
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [message.to_dict() for message in self.messages],
        }
        if self.temperature is not None:
            payload["temperature"] = self.temperature
        if self.max_tokens is not None:
            payload["max_tokens"] = self.max_tokens
        if self.stop:
            payload["stop"] = list(self.stop)
        payload.update(self.extra)
        return payload


@dataclass(frozen=True)
class TokenUsage:
    """Token accounting for one completion."""

    prompt_tokens: int = 0
    completion_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    def to_dict(self) -> dict[str, int]:
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
        }


@dataclass(frozen=True)
class ChatResult:
    """A provider's answer, normalised so callers never depend on backend quirks."""

    content: str
    model: str
    provider: str
    usage: TokenUsage = field(default_factory=TokenUsage)
    finish_reason: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.content is None:
            raise ValueError("ChatResult requires content (use an empty string, not None)")


@dataclass(frozen=True)
class ProviderHealth:
    """The result of one provider health probe."""

    provider: str
    healthy: bool
    detail: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"provider": self.provider, "healthy": self.healthy}
        if self.detail:
            payload["detail"] = self.detail
        return payload


class Provider(ABC):
    """The only interface the Gateway knows about an AI backend."""

    #: Catalogue value in ``models.yaml`` that selects this provider. Must be unique.
    name: ClassVar[str] = ""

    @abstractmethod
    async def chat(self, request: ChatRequest) -> ChatResult:
        """Produce one completion. Raise a :class:`ProviderError` subtype on failure."""

    async def health(self) -> ProviderHealth:
        """Report whether the backend is reachable.

        The default answers optimistically because a provider may hold no
        connection until first use.  Real providers should probe their backend.
        """
        return ProviderHealth(provider=self.name, healthy=True, detail="not probed")

    async def close(self) -> None:
        """Release connections, clients, or sessions. Safe to call more than once."""
        return None

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<{type(self).__name__} name={self.name or 'unset'}>"


__all__ = [
    "VALID_ROLES",
    "ChatMessage",
    "ChatRequest",
    "ChatResult",
    "Provider",
    "ProviderAuthenticationError",
    "ProviderError",
    "ProviderHealth",
    "ProviderRateLimitedError",
    "ProviderRequestRejectedError",
    "ProviderResponseInvalidError",
    "ProviderTimeoutError",
    "ProviderUnavailableError",
    "TokenUsage",
]
