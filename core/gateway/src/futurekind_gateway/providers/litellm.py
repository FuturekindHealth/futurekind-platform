"""The first provider: LiteLLM, the only AI backend the Gateway is allowed to speak to.

``docs/ARCHITECTURE.md:106`` ("All AI traffic passes through FutureKind
Gateway") and ``ADR-0002`` together produce one rule with two halves:
applications reach no model directly, and the Gateway reaches no model directly
either. The Gateway's job is permission, policy, provenance and privacy;
choosing weights, retrying, failing over and counting cost belongs to LiteLLM.

So this class does something deliberately narrower than it looks. It sends the
**alias** as the OpenAI ``model`` field and lets LiteLLM decide what that means
today. It does not hold a list of backends, does not retry, and does not
fail over — the fallback chain in :mod:`futurekind_gateway.routing` stays a
catalogue concern for as long as ``ADR-0002`` assigns those four verbs to
LiteLLM, and a second copy of either would be two answers to one question.

Failure translation is the substance here. Every transport outcome becomes one
of the ``ProviderError`` subtypes in :mod:`.base`, and the ``retryable`` flag on
each is what tells the service layer whether walking to the next candidate could
honestly help. Two properties hold throughout:

* **Nothing of the conversation crosses this boundary twice.** An upstream error
  body may echo prompt text, and prompt text may be patient narrative, so the
  detail carried into a log line or an error response is truncated, whitespace
  collapsed, and stripped of the credential — never the request.
* **A 404 is a refusal, not a miss.** "No deployment answers that alias" is a
  deployment contradiction. Retrying it against a lesser model would launder a
  routing failure into an answer that looks normal.
"""

from __future__ import annotations

from typing import Any, ClassVar

import httpx

from .base import (
    ChatRequest,
    ChatResult,
    Provider,
    ProviderAuthenticationError,
    ProviderError,
    ProviderHealth,
    ProviderRateLimitedError,
    ProviderRequestRejectedError,
    ProviderResponseInvalidError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    TokenUsage,
)

#: LiteLLM's OpenAI-compatible completion endpoint.
CHAT_COMPLETIONS_PATH = "/v1/chat/completions"

#: LiteLLM's own liveness path — its container healthcheck target, so the Gateway
#: and the orchestrator ask the same question of it.
LIVELINESS_PATH = "/health/liveliness"

#: How long a liveness probe may hold up ``GET /health``. Deliberately far shorter
#: than a completion timeout: an unreachable backend is information, and the
#: health endpoint must still be an answer rather than a second outage.
HEALTH_PROBE_TIMEOUT_SECONDS = 2.0

#: Longest upstream fragment carried into a log line or an error body.
MAX_DETAIL_CHARS = 300

_ALLOWED_SCHEMES = ("http://", "https://")


class LiteLLMProvider(Provider):
    """Invoke LiteLLM over its OpenAI-compatible HTTP API.

    One instance holds one connection pool for the process. It is built lazily by
    :class:`~futurekind_gateway.providers.ProviderRegistry`, which means an
    unusable endpoint is discovered on the first request or the first health
    probe — not at import time, and never by inventing a default address.
    """

    name: ClassVar[str] = "litellm"

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str | None = None,
        timeout_seconds: float = 120.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        """Configure one route to one LiteLLM deployment.

        ``transport`` exists for tests: passing an ``httpx.MockTransport`` keeps
        the status-code translation under test without a backend. Nothing in
        ``src`` uses it.
        """
        cleaned = (base_url or "").strip().rstrip("/")
        if not cleaned.startswith(_ALLOWED_SCHEMES):
            raise ValueError(
                "LiteLLM base_url must be an absolute http(s) URL, e.g. "
                f"http://fk-litellm:4000 — got {cleaned!r}"
            )
        self._api_key = (api_key or "").strip() or None
        self._timeout_seconds = float(timeout_seconds)
        self._client = httpx.AsyncClient(
            base_url=cleaned,
            timeout=httpx.Timeout(
                self._timeout_seconds,
                connect=min(10.0, self._timeout_seconds),
            ),
            transport=transport,
        )

    @property
    def base_url(self) -> str:
        """The endpoint in use. Safe to report: it is the operator's own config."""
        return str(self._client.base_url).rstrip("/")

    async def chat(self, request: ChatRequest) -> ChatResult:
        """Send one completion request addressed by alias, and translate the answer.

        The payload comes from :meth:`ChatRequest.to_dict`, whose ``model`` field
        carries the alias the service layer resolved — the Gateway never sends a
        weights id here, which is the whole point of the alias namespace.
        """
        payload = request.to_dict()
        if payload.get("stream"):
            # Refused rather than ignored: a streaming response would arrive as
            # Server-Sent Events and be parsed as a broken body, blaming LiteLLM
            # for a feature this build never agreed to. See SPEC-15-03.
            raise ProviderRequestRejectedError(
                "Streaming is not implemented in this Gateway build",
                provider=self.name,
            )

        try:
            response = await self._client.post(
                CHAT_COMPLETIONS_PATH,
                json=payload,
                headers=self._headers(),
            )
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError(
                f"LiteLLM did not respond within {self._timeout_seconds:.1f}s",
                provider=self.name,
            ) from exc
        except httpx.NetworkError as exc:
            raise ProviderUnavailableError(
                f"LiteLLM at {self.base_url} is not reachable ({type(exc).__name__})",
                provider=self.name,
            ) from exc

        if response.status_code >= 400:
            raise self._classify(response)

        return self._parse(response, requested_model=request.model)

    async def health(self) -> ProviderHealth:
        """Ask LiteLLM's own liveness endpoint, on a short leash."""
        try:
            response = await self._client.get(
                LIVELINESS_PATH,
                headers=self._headers(),
                timeout=HEALTH_PROBE_TIMEOUT_SECONDS,
            )
        except httpx.HTTPError as exc:
            return ProviderHealth(
                provider=self.name,
                healthy=False,
                detail=f"{self.base_url}: {type(exc).__name__}",
            )
        if response.status_code >= 400:
            return ProviderHealth(
                provider=self.name,
                healthy=False,
                detail=f"{self.base_url}: HTTP {response.status_code}",
            )
        return ProviderHealth(provider=self.name, healthy=True, detail=self.base_url)

    async def close(self) -> None:
        await self._client.aclose()

    # -- internals -----------------------------------------------------------------------

    def _headers(self) -> dict[str, str]:
        """Credential headers. LiteLLM's master key is a bearer token, as it is
        everywhere else in this deployment; with no key configured the request is
        still sent, because refusing here would hide the 401 that explains itself."""
        if self._api_key:
            return {"Authorization": f"Bearer {self._api_key}"}
        return {}

    def _classify(self, response: httpx.Response) -> ProviderError:
        """Map one HTTP status onto the failure type the service layer needs.

        The mapping is the contract: ``retryable`` decides whether a clinical
        request may be answered by a different model, and a 401, a 404 or a
        refusal must never be laundered into a fallback attempt.
        """
        status = response.status_code
        detail = self._describe(response)
        message = f"LiteLLM answered HTTP {status}"
        if detail:
            message = f"{message}: {detail}"

        if status in (401, 403):
            return ProviderAuthenticationError(message, provider=self.name)
        if status == 408:
            return ProviderTimeoutError(message, provider=self.name)
        if status == 429:
            return ProviderRateLimitedError(message, provider=self.name)
        if status >= 500:
            return ProviderUnavailableError(message, provider=self.name)
        return ProviderRequestRejectedError(message, provider=self.name)

    def _describe(self, response: httpx.Response) -> str:
        """A short, credential-free, conversation-free account of an upstream failure.

        LiteLLM error bodies can quote the request, and the request can contain
        patient narrative, so the fragment is truncated and flattened before it
        goes anywhere a log shipper or a caller could repeat it. The credential
        is removed even though it should never appear, because "should not" is not
        a property this class can rely on.
        """
        text = ""
        try:
            body = response.json()
        except ValueError:
            body = None
        if isinstance(body, dict):
            error = body.get("error")
            candidates = [error, body.get("message"), body.get("detail")]
            for candidate in candidates:
                if isinstance(candidate, str) and candidate.strip():
                    text = candidate
                    break
                if isinstance(candidate, dict):
                    inner = candidate.get("message") or candidate.get("msg")
                    if isinstance(inner, str) and inner.strip():
                        text = inner
                        break
        if not text:
            text = response.text or ""
        if self._api_key:
            text = text.replace(self._api_key, "[redacted]")
        flattened = " ".join(text.split())
        if len(flattened) > MAX_DETAIL_CHARS:
            flattened = flattened[:MAX_DETAIL_CHARS].rstrip() + "…"
        return flattened

    def _parse(self, response: httpx.Response, *, requested_model: str) -> ChatResult:
        """Normalise one OpenAI-shaped completion into the contract's result type."""
        try:
            body = response.json()
        except ValueError as exc:
            raise ProviderResponseInvalidError(
                "LiteLLM answered with a body that is not JSON",
                provider=self.name,
            ) from exc
        if not isinstance(body, dict):
            raise ProviderResponseInvalidError(
                f"LiteLLM answered with {type(body).__name__}, expected an object",
                provider=self.name,
            )

        choices = body.get("choices")
        if not isinstance(choices, list) or not choices:
            raise ProviderResponseInvalidError(
                "LiteLLM answered with no choices", provider=self.name
            )
        first = choices[0]
        if not isinstance(first, dict):
            raise ProviderResponseInvalidError(
                "LiteLLM answered with a choice that is not an object", provider=self.name
            )
        message = first.get("message")
        if not isinstance(message, dict):
            raise ProviderResponseInvalidError(
                "LiteLLM answered with no message object", provider=self.name
            )
        content = message.get("content")
        if content is None:
            # Absent, not empty: an empty answer is a model's doing, a missing one
            # is a protocol break, and only the second is worth a fallback.
            raise ProviderResponseInvalidError(
                "LiteLLM answered with no message content", provider=self.name
            )
        if not isinstance(content, str):
            raise ProviderResponseInvalidError(
                f"LiteLLM returned content of type {type(content).__name__}, expected text",
                provider=self.name,
            )

        finish_reason = first.get("finish_reason")
        reported = body.get("model")
        return ChatResult(
            content=content,
            model=reported if isinstance(reported, str) and reported else requested_model,
            provider=self.name,
            usage=self._usage(body),
            finish_reason=finish_reason if isinstance(finish_reason, str) else None,
        )

    @staticmethod
    def _usage(body: dict[str, Any]) -> TokenUsage:
        """Token counts as LiteLLM reports them, tolerating a missing usage block."""
        usage = body.get("usage")
        if not isinstance(usage, dict):
            return TokenUsage()

        def count(key: str) -> int:
            value = usage.get(key)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                return 0
            return int(value)

        return TokenUsage(
            prompt_tokens=count("prompt_tokens"),
            completion_tokens=count("completion_tokens"),
        )


__all__ = ["CHAT_COMPLETIONS_PATH", "LIVELINESS_PATH", "LiteLLMProvider"]
