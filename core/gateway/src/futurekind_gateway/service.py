"""The Gateway service layer: route, apply policy, invoke, record.

This is where the platform rule is enforced in code — an application's request
becomes a :class:`~futurekind_gateway.routing.Route`, which carries the skill's
policy with it, and only then does it become a provider call.  Providers never
see a capability name; they see the alias the catalogue resolved for this
attempt, which is the only model-facing name this side of ``ADR-0002`` is allowed
to send.

How far a request may travel is decided by that policy, not here: how long one
attempt may take, and whether there is anything to fall back to at all.

Fallback policy: a candidate is replaced only when the failure was plausibly
transient (unreachable, timed out, throttled).  A rejected request or a bad
credential is answered immediately, because retrying the same clinical question
against a different model after a refusal would be laundering a decision the
platform already declined to make.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, replace
from typing import Any

from .catalog import ModelEntry
from .config import GatewaySettings
from .errors import (
    GatewayError,
    ProviderFailedError,
    ProviderNotImplementedError,
    UpstreamTimeoutError,
)
from .intents import ChatIntent
from .observability.logging import get_logger, log_event
from .observability.metrics import Metrics
from .policy import DEFAULT_POLICY, SkillPolicy, check_request, limits_for
from .providers import ProviderRegistry
from .providers.base import (
    ChatRequest,
    ChatResult,
    Provider,
    ProviderAuthenticationError,
    ProviderError,
    ProviderHealth,
    ProviderRateLimitedError,
    ProviderRequestRejectedError,
    ProviderTimeoutError,
    TokenUsage,
)
from .routing import ModelRouter, Route

logger = get_logger("futurekind.gateway.service")

#: Outcome labels used in metrics and logs. Stable strings so dashboards never parse prose.
OUTCOME_SUCCESS = "success"
OUTCOME_FALLBACK = "fallback"
OUTCOME_ERROR = "error"
OUTCOME_TIMEOUT = "timeout"
OUTCOME_UNIMPLEMENTED = "unimplemented"


@dataclass(frozen=True)
class ChatOutcome:
    """What one completed chat request produced, plus how it got there."""

    request_id: str | None
    capability: str
    skill: str | None
    model: str
    provider: str
    selected_by: str
    attempts: int
    degraded: bool
    content: str
    finish_reason: str | None
    usage: TokenUsage
    latency_ms: int
    policy: SkillPolicy = DEFAULT_POLICY

    def to_response_dict(self) -> dict[str, Any]:
        """Shape for ``ChatResponseSchema``."""
        return {
            "request_id": self.request_id or "",
            "capability": self.capability,
            "skill": self.skill,
            "model": self.model,
            "provider": self.provider,
            "selected_by": self.selected_by,
            "policy": self.policy.to_public_dict(),
            "attempts": self.attempts,
            "degraded": self.degraded,
            "content": self.content,
            "finish_reason": self.finish_reason,
            "usage": {
                "prompt_tokens": self.usage.prompt_tokens,
                "completion_tokens": self.usage.completion_tokens,
                "total_tokens": self.usage.total_tokens,
            },
            "latency_ms": self.latency_ms,
        }


class GatewayService:
    """Executes routed chat requests against the registered providers."""

    def __init__(
        self,
        *,
        router: ModelRouter,
        registry: ProviderRegistry,
        settings: GatewaySettings,
        metrics: Metrics | None = None,
    ) -> None:
        self._router = router
        self._registry = registry
        self._settings = settings
        self._metrics = metrics

    @property
    def settings(self) -> GatewaySettings:
        return self._settings

    @property
    def router(self) -> ModelRouter:
        return self._router

    @property
    def registry(self) -> ProviderRegistry:
        return self._registry

    def route_for(
        self,
        *,
        skill: str | None = None,
        capability: str | None = None,
    ) -> Route:
        """Resolve a request into a route without touching any provider."""
        return self._router.resolve(skill=skill, capability=capability)

    async def handle(self, intent: ChatIntent, *, request_id: str | None = None) -> ChatOutcome:
        """The one place where an intent becomes a provider call.

        Three steps, in this order, and nothing else in the platform repeats them:
        resolve the route so its policy is known, enforce that policy, then invoke.
        Every HTTP surface — ``POST /chat`` and the OpenAI-compatible one — arrives
        here, which is what stops a second door from growing a second set of rules
        (``SPEC-05-02``).

        The request the provider receives is addressed by ``route.target``: the
        alias, per ``ADR-0002``. A model id is never sent, because choosing
        weights is LiteLLM's decision and an answer that came from a different
        deployment than the catalogue claims would be an audit line about a
        request that never happened.
        """
        route = self.route_for(skill=intent.skill, capability=intent.capability)
        check_request(
            route.policy,
            skill=route.skill,
            message_count=intent.message_count,
            longest_message_chars=intent.longest_message_chars,
            requested_max_tokens=intent.max_tokens,
            settings=self._settings,
        )
        template = intent.to_provider_request(model=route.target)
        return await self.complete(route=route, template=template, request_id=request_id)

    async def complete(
        self,
        *,
        route: Route,
        template: ChatRequest,
        request_id: str | None = None,
    ) -> ChatOutcome:
        """Walk the fallback chain until a candidate answers or the chain is spent.

        ``template`` carries the messages and sampling parameters; its ``model``
        is rewritten per candidate, so a fallback genuinely changes the alias —
        and therefore the deployment — the request is sent to.  How far that walk
        may go, and how long each attempt may take, comes from the route's policy
        rather than from this method — a ``high`` risk skill has no chain to walk.
        """
        chain = route.candidates
        limits = limits_for(route.policy, self._settings)
        started = time.perf_counter()
        failures: list[dict[str, str]] = []
        remaining = len(chain)
        answered_by: ModelEntry | None = None

        if self._metrics is not None:
            self._metrics.start_request()
        try:
            for index, candidate in enumerate(chain):
                remaining -= 1
                provider = self._resolve_provider(
                    candidate, request_id=request_id, route=route
                )

                request = replace(template, model=candidate.target)
                log_event(
                    logger,
                    "info",
                    "provider_attempt",
                    request_id=request_id,
                    skill=route.skill,
                    capability=route.capability,
                    clinical_risk=route.policy.clinical_risk,
                    alias=candidate.alias,
                    candidate=candidate.capability,
                    provider=candidate.provider,
                    model=candidate.model,
                    attempt=index + 1,
                    of=len(chain),
                    fallback=index > 0,
                    message_count=len(request.messages),
                )

                attempt_started = time.perf_counter()
                try:
                    result = await asyncio.wait_for(
                        provider.chat(request), timeout=limits.request_timeout_seconds
                    )
                except TimeoutError as exc:
                    self._record_attempt(candidate, OUTCOME_TIMEOUT)
                    failures.append({"capability": candidate.capability, "error": "timeout"})
                    if remaining:
                        self._log_failed_attempt(
                            candidate,
                            error="timeout",
                            retried=True,
                            attempt_started=attempt_started,
                        )
                        continue
                    self._log_failed_attempt(
                        candidate, error="timeout", retried=False, attempt_started=attempt_started
                    )
                    raise UpstreamTimeoutError(
                        f"Provider '{candidate.provider}' timed out after "
                        f"{limits.request_timeout_seconds:.1f}s",
                        details={
                            "provider": candidate.provider,
                            "model": candidate.model,
                            "capability": candidate.capability,
                            "timeout_seconds": limits.request_timeout_seconds,
                        },
                    ) from exc
                except ProviderError as exc:
                    self._record_attempt(
                        candidate,
                        OUTCOME_TIMEOUT if isinstance(exc, ProviderTimeoutError) else OUTCOME_ERROR,
                    )
                    failures.append({"capability": candidate.capability, "error": str(exc)})
                    if not exc.retryable:
                        # A refusal or a bad credential will not be answered differently
                        # by another model, so nothing further is attempted.
                        self._log_failed_attempt(
                            candidate,
                            error=f"{type(exc).__name__}: {exc}",
                            retried=False,
                            attempt_started=attempt_started,
                        )
                        raise self._translate(exc, candidate=candidate, failures=failures) from exc
                    self._log_failed_attempt(
                        candidate,
                        error=f"{type(exc).__name__}: {exc}",
                        retried=remaining > 0,
                        attempt_started=attempt_started,
                    )
                    if remaining == 0:
                        # Chain spent: report the whole attempt, not just the last failure.
                        break
                    continue

                latency_ms = int((time.perf_counter() - started) * 1000)
                self._record_attempt(candidate, OUTCOME_SUCCESS)
                outcome = self._build_outcome(
                    result,
                    route=route,
                    candidate=candidate,
                    attempts=index + 1,
                    latency_ms=latency_ms,
                    request_id=request_id,
                )
                self._record_success(outcome, route=route)
                answered_by = candidate
                return outcome

            raise ProviderFailedError(
                "Every model that can serve this request failed",
                details={
                    "capability": route.capability,
                    "attempted": [entry.capability for entry in chain],
                    "failures": failures,
                },
            )
        finally:
            if self._metrics is not None:
                self._metrics.end_request()
            self._audit(route, request_id=request_id, answered_by=answered_by)

    async def probe_providers(self) -> tuple[ProviderHealth, ...]:
        """Ask every registered provider how it is doing. Never raises."""
        results: list[ProviderHealth] = []
        for name in self._registry.names():
            try:
                provider = self._registry.get(name)
            except GatewayError as exc:
                results.append(ProviderHealth(provider=name, healthy=False, detail=exc.message))
                continue
            try:
                results.append(await provider.health())
            except Exception as exc:  # noqa: BLE001 - /health must never fail because a probe did
                results.append(
                    ProviderHealth(
                        provider=name,
                        healthy=False,
                        detail=str(exc) or type(exc).__name__,
                    )
                )
        return tuple(results)

    # -- internals -----------------------------------------------------------------------

    def _audit(
        self,
        route: Route,
        *,
        request_id: str | None,
        answered_by: ModelEntry | None,
    ) -> None:
        """Write the record ``ADR-0002`` gives the Gateway, for the skills that ask for one.

        One line per audited request whatever the outcome, because a trail that
        only exists when the model answered is a success log, not an audit.  It
        names the alias that was asked for and the model that actually replied —
        the pairing the ADR requires, and the one an application cannot supply
        because it is never told the alias.
        """
        if not route.policy.audit_required:
            return
        log_event(
            logger,
            "info" if answered_by is not None else "warning",
            "skill_audit",
            request_id=request_id,
            skill=route.skill,
            capability=route.capability,
            clinical_risk=route.policy.clinical_risk,
            approval_required=route.policy.approval_required,
            alias=route.alias,
            answered=answered_by is not None,
            provider=answered_by.provider if answered_by else None,
            model=answered_by.model if answered_by else None,
            downgrades_allowed=route.policy.allow_downgrade,
            # Deliberately absent: prompt and completion text. See observability/logging.py.
        )

    def _resolve_provider(
        self, candidate: ModelEntry, *, request_id: str | None, route: Route
    ) -> Provider:
        """Return the provider instance for a candidate, or raise ``501``.

        An unimplemented provider is never skipped over in favour of another
        capability: silently downgrading a clinical request would hide a
        deployment gap behind an answer that looks normal.
        """
        try:
            return self._registry.get(candidate.provider)
        except ProviderNotImplementedError as exc:
            self._record_attempt(candidate, OUTCOME_UNIMPLEMENTED)
            log_event(
                logger,
                "warning",
                "provider_not_implemented",
                request_id=request_id,
                skill=route.skill,
                clinical_risk=route.policy.clinical_risk,
                alias=candidate.alias,
                provider=candidate.provider,
                capability=candidate.capability,
                registered=list(exc.details.get("registered_providers", [])),
            )
            raise

    def _record_attempt(self, candidate: ModelEntry, outcome: str) -> None:
        if self._metrics is None:
            return
        self._metrics.record_attempt(
            provider=candidate.provider, model=candidate.model, outcome=outcome
        )

    def _record_success(self, outcome: ChatOutcome, *, route: Route) -> None:
        if self._metrics is None:
            return
        self._metrics.observe_request(
            capability=route.capability,
            provider=outcome.provider,
            outcome=OUTCOME_FALLBACK if outcome.degraded else OUTCOME_SUCCESS,
            seconds=outcome.latency_ms / 1000,
        )
        self._metrics.record_tokens(
            capability=route.capability,
            prompt_tokens=outcome.usage.prompt_tokens,
            completion_tokens=outcome.usage.completion_tokens,
        )

    def _log_failed_attempt(
        self,
        candidate: ModelEntry,
        *,
        error: str,
        retried: bool,
        attempt_started: float,
    ) -> None:
        log_event(
            logger,
            "warning",
            "provider_attempt_failed",
            provider=candidate.provider,
            model=candidate.model,
            capability=candidate.capability,
            error=error[:500],
            retried=retried,
            duration_ms=int((time.perf_counter() - attempt_started) * 1000),
        )

    def _build_outcome(
        self,
        result: ChatResult,
        *,
        route: Route,
        candidate: ModelEntry,
        attempts: int,
        latency_ms: int,
        request_id: str | None,
    ) -> ChatOutcome:
        if not isinstance(result.content, str):
            raise ProviderFailedError(
                f"Provider '{candidate.provider}' returned content that is not text",
                code="provider_protocol_error",
                details={
                    "provider": candidate.provider,
                    "capability": route.capability,
                    "returned": type(result.content).__name__,
                },
            )
        degraded = candidate.capability != route.entry.capability
        log_event(
            logger,
            "info",
            "chat_completed",
            request_id=request_id,
            skill=route.skill,
            capability=route.capability,
            clinical_risk=route.policy.clinical_risk,
            alias=route.alias,
            provider=candidate.provider,
            model=candidate.model,
            attempts=attempts,
            degraded=degraded,
            latency_ms=latency_ms,
            prompt_tokens=result.usage.prompt_tokens,
            completion_tokens=result.usage.completion_tokens,
            # Deliberately absent: the generated text. See observability/logging.py.
            content_chars=len(result.content),
        )
        return ChatOutcome(
            request_id=request_id,
            capability=route.capability,
            skill=route.skill,
            model=candidate.model,
            provider=candidate.provider,
            selected_by=route.selected_by,
            attempts=attempts,
            degraded=degraded,
            content=result.content,
            finish_reason=result.finish_reason,
            usage=result.usage,
            latency_ms=latency_ms,
            policy=route.policy,
        )

    def _translate(
        self,
        exc: ProviderError,
        *,
        candidate: ModelEntry,
        failures: list[dict[str, str]],
    ) -> GatewayError:
        """Map a provider failure onto one stable Gateway error code."""
        details = {
            "provider": candidate.provider,
            "model": candidate.model,
            "capability": candidate.capability,
            "failures": failures,
        }
        if isinstance(exc, ProviderAuthenticationError):
            return ProviderFailedError(
                f"Provider '{candidate.provider}' rejected its credentials",
                code="provider_authentication_failed",
                details=details,
            )
        if isinstance(exc, ProviderRateLimitedError):
            return ProviderFailedError(
                f"Provider '{candidate.provider}' is rate limited",
                code="provider_rate_limited",
                details=details,
            )
        if isinstance(exc, ProviderRequestRejectedError):
            return ProviderFailedError(
                str(exc) or "Provider rejected the request",
                code="provider_request_rejected",
                details=details,
            )
        if isinstance(exc, ProviderTimeoutError):
            return UpstreamTimeoutError(
                f"Provider '{candidate.provider}' timed out",
                details=details,
            )
        return ProviderFailedError(
            str(exc) or type(exc).__name__,
            code="provider_unavailable",
            details=details,
        )


__all__ = [
    "ChatOutcome",
    "GatewayService",
    "OUTCOME_ERROR",
    "OUTCOME_FALLBACK",
    "OUTCOME_SUCCESS",
    "OUTCOME_TIMEOUT",
    "OUTCOME_UNIMPLEMENTED",
]
