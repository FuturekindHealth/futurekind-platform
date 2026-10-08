"""Unit tests for the service layer: routing, invocation, fallback, recording."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import pytest

from futurekind_gateway.config import GatewaySettings
from futurekind_gateway.errors import (
    ProviderFailedError,
    ProviderNotImplementedError,
    UnknownCapabilityError,
    UpstreamTimeoutError,
)
from futurekind_gateway.observability.metrics import Metrics
from futurekind_gateway.providers import ProviderRegistry
from futurekind_gateway.providers.base import (
    ChatMessage,
    ChatRequest,
    ChatResult,
    Provider,
    ProviderAuthenticationError,
    ProviderHealth,
    ProviderRateLimitedError,
    ProviderRequestRejectedError,
    ProviderUnavailableError,
    TokenUsage,
)
from futurekind_gateway.routing import ModelRouter
from futurekind_gateway.schemas import ChatResponseSchema
from futurekind_gateway.service import ChatOutcome, GatewayService
from tests.conftest import FakeProvider, make_catalog, make_settings, policy_document


def make_service(
    provider: Provider | None = None,
    *,
    document: dict[str, Any] | None = None,
    settings: GatewaySettings | None = None,
    metrics: Metrics | None = None,
    provider_name: str = "fake",
) -> tuple[GatewayService, Provider, Metrics]:
    catalog = make_catalog(document)
    registry = ProviderRegistry()
    if provider is not None:
        registry.register(provider_name, lambda: provider)
    runtime = settings or make_settings()
    collector = metrics or Metrics()
    service = GatewayService(
        router=ModelRouter(catalog, default_capability=runtime.default_capability),
        registry=registry,
        settings=runtime,
        metrics=collector,
    )
    return service, provider or FakeProvider(), collector


def template_for(model: str = "unused", *, text: str = "what does the scan show?") -> ChatRequest:
    return ChatRequest(model=model, messages=(ChatMessage(role="user", content=text),))


def run(
    service: GatewayService,
    route: Any,
    request: ChatRequest,
    *,
    request_id: str = "req-1",
) -> ChatOutcome:
    return asyncio.run(service.complete(route=route, template=request, request_id=request_id))


class Sequenced(Provider):
    """Fails as scripted, then answers, so fallback chains can be exercised."""

    name = "fake"

    def __init__(self, *outcomes: Any, final_content: str = "answered") -> None:
        self.outcomes = list(outcomes)
        self.final_content = final_content
        self.seen_models: list[str] = []

    async def chat(self, request: ChatRequest) -> ChatResult:
        self.seen_models.append(request.model)
        if self.outcomes:
            outcome = self.outcomes.pop(0)
            if isinstance(outcome, BaseException):
                raise outcome
            if isinstance(outcome, float):
                await asyncio.sleep(outcome)
                raise TimeoutError("scripted delay expired")
        return ChatResult(
            content=self.final_content,
            model=request.model,
            provider=self.name,
            usage=TokenUsage(prompt_tokens=2, completion_tokens=4),
        )


# -- the happy path ---------------------------------------------------------------------------


def test_a_routed_request_returns_the_providers_answer() -> None:
    provider = FakeProvider()
    service, _, _ = make_service(provider)
    route = service.route_for(capability="default")

    outcome = run(service, route, template_for())

    assert outcome.content == "answer"
    assert outcome.provider == "fake"
    assert outcome.model == "fake-large"
    assert outcome.capability == "default"
    assert outcome.attempts == 1
    assert outcome.degraded is False
    assert outcome.selected_by == "capability"
    assert outcome.request_id == "req-1"
    assert outcome.usage.total_tokens == 8
    assert outcome.latency_ms >= 0


def test_the_provider_is_addressed_by_alias_never_by_capability_or_weights() -> None:
    """The whole point of the abstraction boundary, in both directions.

    ADR-0002: the Gateway sends the alias and LiteLLM decides what runs. So the
    name that reaches a provider must be the alias — not the capability (that
    would be leaking platform vocabulary to a backend) and not the weights id
    (that would be the Gateway choosing infrastructure it does not own).
    """
    provider = FakeProvider()
    service, _, _ = make_service(provider)

    run(service, service.route_for(capability="default"), template_for())

    payload = provider.requests[0].to_dict()
    assert payload["model"] == "fk-default"
    # The old form of this guard searched the payload for the string "default" and
    # would now pass or fail by accident, because the shipped alias is fk-default.
    # What must not cross the boundary is the *vocabulary*, so the check is on the
    # field names a provider can be addressed by: never a capability, never a
    # skill, never an alias spelled out as something the backend has to interpret.
    assert "capability" not in payload
    assert "skill" not in payload
    assert "alias" not in payload


def test_the_resolved_alias_is_written_into_the_request_template() -> None:
    provider = FakeProvider()
    service, _, _ = make_service(provider)

    run(service, service.route_for(capability="fast"), template_for(model="placeholder"))

    assert provider.requests[0].model == "fk-fast"


def test_the_alias_is_sent_while_the_weights_id_is_reported() -> None:
    """The pairing ``ADR-0002`` asks for, checked on one request.

    What went out is the alias; what comes back in the outcome is the model the
    catalogue says that alias resolves to. A row with no alias at all keeps
    working by sending its model — which is exactly the pre-alias state the
    startup check refuses to let a LiteLLM row stay in.
    """
    provider = FakeProvider()
    service, _, _ = make_service(provider)

    outcome = run(service, service.route_for(capability="default"), template_for())

    assert provider.requests[0].model == "fk-default"
    assert outcome.model == "fake-large"


def test_sampling_parameters_survive_the_trip_through_routing() -> None:
    provider = FakeProvider()
    service, _, _ = make_service(provider)
    request = ChatRequest(
        model="placeholder",
        messages=(ChatMessage(role="user", content="x"),),
        temperature=0.2,
        max_tokens=64,
        stop=("###",),
        extra={"top_k": 3},
    )

    run(service, service.route_for(capability="default"), request)

    sent = provider.requests[0]
    assert sent.temperature == 0.2
    assert sent.max_tokens == 64
    assert sent.stop == ("###",)
    assert sent.extra == {"top_k": 3}


# -- fallback behaviour -----------------------------------------------------------------------


def test_a_transient_failure_moves_to_the_next_capability_and_marks_degraded() -> None:
    provider = Sequenced(ProviderUnavailableError("down", provider="fake"))
    service, _, _ = make_service(provider)

    outcome = run(service, service.route_for(capability="fast"), template_for())

    assert outcome.attempts == 2
    assert outcome.degraded is True
    assert provider.seen_models == ["fk-fast", "fk-default"]


def test_fallbacks_are_walked_transitively_until_one_answers() -> None:
    provider = Sequenced(
        ProviderUnavailableError("first down", provider="fake"),
        ProviderUnavailableError("second down", provider="fake"),
    )
    service, _, _ = make_service(provider)

    outcome = run(service, service.route_for(capability="reasoning"), template_for())

    assert outcome.attempts == 3
    assert provider.seen_models == ["fk-reasoning", "fk-fast", "fk-default"]


def test_a_refused_request_is_not_retried_against_another_model() -> None:
    """Retrying a refusal elsewhere would launder a decision the platform made."""
    provider = Sequenced(ProviderRequestRejectedError("refused", provider="fake"))
    service, _, _ = make_service(provider)

    with pytest.raises(ProviderFailedError) as caught:
        run(service, service.route_for(capability="fast"), template_for())

    assert caught.value.code == "provider_request_rejected"
    assert provider.seen_models == ["fk-fast"]


def test_bad_provider_credentials_are_reported_as_such() -> None:
    provider = Sequenced(ProviderAuthenticationError("403", provider="fake"))
    service, _, _ = make_service(provider)

    with pytest.raises(ProviderFailedError) as caught:
        run(service, service.route_for(capability="default"), template_for())

    assert caught.value.code == "provider_authentication_failed"


def test_a_rate_limited_provider_may_still_be_answered_by_a_fallback() -> None:
    provider = Sequenced(ProviderRateLimitedError("429", provider="fake"))
    service, _, _ = make_service(provider)

    outcome = run(service, service.route_for(capability="fast"), template_for())

    assert outcome.attempts == 2
    assert outcome.degraded is True


def test_an_exhausted_chain_reports_every_attempt() -> None:
    provider = Sequenced(
        ProviderUnavailableError("a", provider="fake"),
        ProviderUnavailableError("b", provider="fake"),
    )
    service, _, _ = make_service(provider)

    with pytest.raises(ProviderFailedError) as caught:
        run(service, service.route_for(capability="fast"), template_for())

    details = caught.value.details
    assert details["attempted"] == ["fast", "default"]
    assert [item["capability"] for item in details["failures"]] == ["fast", "default"]


def test_an_unimplemented_provider_is_never_skipped_past() -> None:
    """A silent downgrade would hide a deployment gap behind a normal-looking answer."""
    provider = FakeProvider()
    service, _, _ = make_service(provider, provider_name="something-else")

    with pytest.raises(ProviderNotImplementedError) as caught:
        run(service, service.route_for(capability="default"), template_for())

    assert caught.value.status_code == 501
    assert provider.requests == []


# -- timeouts ---------------------------------------------------------------------------------


def test_a_timeout_falls_back_and_a_later_candidate_may_answer() -> None:
    provider = Sequenced(0.25)
    service, _, metrics = make_service(
        provider, settings=make_settings(request_timeout_seconds=0.05)
    )

    outcome = run(service, service.route_for(capability="fast"), template_for())

    assert outcome.attempts == 2
    assert "timeout" in str(metrics.render()[0].decode())


def test_a_timeout_on_the_last_candidate_is_reported_as_a_gateway_timeout() -> None:
    provider = Sequenced(0.25)
    service, _, _ = make_service(provider, settings=make_settings(request_timeout_seconds=0.05))

    with pytest.raises(UpstreamTimeoutError) as caught:
        run(service, service.route_for(capability="default"), template_for())

    assert caught.value.status_code == 504
    assert caught.value.retryable is True


# -- protocol violations ----------------------------------------------------------------------


def test_non_text_content_is_refused_rather_than_serialised() -> None:
    """A provider that ignores the contract must not turn a dict into a clinical answer."""

    class Weird(Provider):
        name = "fake"

        async def chat(self, request: ChatRequest) -> ChatResult:
            return ChatResult(
                content={"text": "not a string"},  # type: ignore[dict-item]
                model=request.model,
                provider="fake",
            )

    service, _, _ = make_service(Weird())

    with pytest.raises(ProviderFailedError) as caught:
        run(service, service.route_for(capability="default"), template_for())

    assert caught.value.code == "provider_protocol_error"


# -- metrics and readiness --------------------------------------------------------------------


def test_success_updates_counters_and_leaves_nothing_in_flight() -> None:
    service, _, metrics = make_service(FakeProvider())
    metrics.start_request()
    metrics.end_request()

    run(service, service.route_for(capability="default"), template_for())

    body = metrics.render()[0].decode()
    assert 'fk_gateway_requests_total{capability="default",outcome="success"' in body or (
        'outcome="success"' in body and "fk_gateway_requests_total" in body
    )
    assert "fk_gateway_provider_attempts_total" in body
    assert "fk_gateway_tokens_total" in body
    assert metrics.in_flight._value.get() == 0


def test_failed_attempts_are_counted_per_provider() -> None:
    """Error codes are counted where they are rendered (see the API tests);
    the service counts the attempts themselves."""
    service, _, metrics = make_service(
        Sequenced(ProviderRequestRejectedError("no", provider="fake"))
    )
    with pytest.raises(ProviderFailedError):
        run(service, service.route_for(capability="default"), template_for())

    body = metrics.render()[0].decode()
    assert 'fk_gateway_provider_attempts_total{model="fake-large",outcome="error"' in body


def test_the_catalogue_is_published_as_a_labeled_gauge() -> None:
    collector = Metrics()
    collector.describe_catalog(make_catalog().entries)

    body = collector.render()[0].decode()
    assert 'fk_gateway_catalog_models{capability="default",model="fake-large"' in body
    assert 'capability="retired"' in body


@contextmanager
def capture_service_logs() -> Iterator[list[logging.LogRecord]]:
    """Collect the service logger's records, restoring it afterwards."""
    collected: list[logging.LogRecord] = []

    class Collect(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            collected.append(record)

    service_logger = logging.getLogger("futurekind.gateway.service")
    saved = (
        list(service_logger.handlers),
        service_logger.propagate,
        service_logger.level,
    )
    service_logger.handlers = [Collect()]
    service_logger.propagate = False
    service_logger.setLevel(logging.INFO)
    try:
        yield collected
    finally:
        handlers, propagate, level = saved
        service_logger.handlers = handlers
        service_logger.propagate = propagate
        service_logger.setLevel(level)


def test_the_audit_line_names_the_skill_and_never_the_prompt_text() -> None:
    """ADR-0002 gives the Gateway the audit duty; this proves the record is usable."""
    service, _, _ = make_service(FakeProvider())

    with capture_service_logs() as collected:
        outcome = run(service, service.route_for(skill="clinical-chat"), template_for())

    line = next(record for record in collected if getattr(record, "event", "") == "chat_completed")

    assert line.skill == "clinical-chat"
    assert line.capability == "default"
    assert outcome.skill == "clinical-chat"
    # The request text must be nowhere in the audit record.
    assert "what does the scan show?" not in repr(sorted(vars(line).items()))


def test_a_refused_request_is_audited_with_its_skill_too() -> None:
    """The failure a hospital most needs to see is 'we could not run this at all'."""
    service, _, _ = make_service(None)

    with capture_service_logs() as collected, pytest.raises(ProviderNotImplementedError):
        run(service, service.route_for(skill="clinical-chat"), template_for())

    line = next(
        record for record in collected if getattr(record, "event", "") == "provider_not_implemented"
    )
    assert line.skill == "clinical-chat"
    assert line.provider == "fake"


def test_routing_errors_surface_unchanged_from_the_service() -> None:
    service, _, _ = make_service(FakeProvider())

    with pytest.raises(UnknownCapabilityError):
        service.route_for(capability="vision")


def test_probe_providers_reports_state_without_raising() -> None:
    class Unreachable(FakeProvider):
        async def health(self) -> ProviderHealth:
            raise RuntimeError("socket closed")

    service, _, _ = make_service(Unreachable())

    probes = asyncio.run(service.probe_providers())

    assert [probe.healthy for probe in probes] == [False]
    assert "socket closed" in probes[0].detail


def test_probe_providers_is_empty_when_nothing_is_registered() -> None:
    service, _, _ = make_service(None)

    assert asyncio.run(service.probe_providers()) == ()


# -- contract shape ---------------------------------------------------------------------------


def test_outcome_serialises_exactly_what_the_response_schema_accepts() -> None:
    service, _, _ = make_service(FakeProvider())

    outcome = run(service, service.route_for(capability="default"), template_for())

    payload = outcome.to_response_dict()
    assert set(payload["policy"]) == {
        "clinical_risk",
        "approval_required",
        "audit_required",
        "allow_downgrade",
    }
    # A request that named no skill must not look as if somebody assessed it.
    assert payload["policy"]["clinical_risk"] == "unspecified"

    parsed = ChatResponseSchema.model_validate(payload)
    assert parsed.capability == "default"
    assert parsed.usage.total_tokens == 8
    assert parsed.attempts == 1
    assert parsed.degraded is False


# -- policy in execution -----------------------------------------------------------------------


def audited_events(collected: list[Any]) -> list[Any]:
    return [record for record in collected if getattr(record, "event", "") == "skill_audit"]


def test_an_audited_skill_writes_one_attestation_line() -> None:
    """`audit_required` is not a comment in a YAML file; it is this line."""
    service, _, _ = make_service(FakeProvider(), document=policy_document())

    with capture_service_logs() as collected:
        run(service, service.route_for(skill="clinical-chat"), template_for())

    line = audited_events(collected).pop()
    assert line.skill == "clinical-chat"
    assert line.answered is True
    assert line.clinical_risk == "moderate"
    assert line.model == "fake-large"
    assert line.alias == "fk-default"


def test_an_unaudited_skill_writes_no_attestation_line() -> None:
    """Opting out has to actually opt out, or the flag is decoration."""
    service, _, _ = make_service(FakeProvider(), document=policy_document())

    with capture_service_logs() as collected:
        run(service, service.route_for(skill="patient-leaflet"), template_for())

    assert audited_events(collected) == []
    assert any(getattr(record, "event", "") == "chat_completed" for record in collected), (
        "the operational log still happens"
    )


def test_a_refused_request_is_still_audited() -> None:
    """The outcome a hospital most needs in the record is 'this never ran'."""
    service, _, _ = make_service(None, document=policy_document())

    with capture_service_logs() as collected, pytest.raises(ProviderNotImplementedError):
        run(service, service.route_for(skill="radiology-report"), template_for())

    line = audited_events(collected).pop()
    assert line.answered is False
    assert line.clinical_risk == "high"
    assert line.model is None
    assert line.alias == "fk-reasoning"


def test_a_policy_timeout_shortens_the_wait_the_gateway_gives_a_provider() -> None:
    """The platform timeout is a ceiling; a skill may ask for less, and gets it."""
    document = policy_document()
    document["skills"]["quick-look"] = {
        "capability": "fast",
        "clinical_risk": "low",
        "request_timeout_seconds": 0.05,
        "allow_downgrade": False,
    }
    service, _, _ = make_service(
        Sequenced(1.0),
        document=document,
        settings=make_settings(request_timeout_seconds=30.0),
    )

    with pytest.raises(UpstreamTimeoutError) as caught:
        run(service, service.route_for(skill="quick-look"), template_for())

    assert caught.value.details["timeout_seconds"] == 0.05


def test_a_high_risk_skill_fails_instead_of_being_answered_by_a_lesser_model() -> None:
    """The suppressed chain has to suppress, not merely report: no fallback is attempted."""
    provider = Sequenced(ProviderUnavailableError("primary down", provider="fake"))
    service, _, _ = make_service(provider, document=policy_document())

    with pytest.raises(ProviderFailedError) as caught:
        run(service, service.route_for(skill="radiology-report"), template_for())

    assert caught.value.details["attempted"] == ["reasoning"]
    assert provider.seen_models == ["fk-reasoning"]


def test_a_high_risk_skill_answers_from_the_model_it_was_routed_to_and_no_other() -> None:
    service, provider, _ = make_service(FakeProvider(), document=policy_document())

    outcome = run(service, service.route_for(skill="radiology-report"), template_for())

    assert outcome.attempts == 1
    assert outcome.degraded is False
    assert outcome.model == "fake-thinker"
    assert outcome.policy.clinical_risk == "high"
    assert [request.model for request in provider.requests] == ["fk-reasoning"]


def test_a_downgradable_skill_still_walks_the_same_chain() -> None:
    """The suppression is per policy, not a global change to how fallback works."""
    provider = Sequenced(ProviderUnavailableError("primary down", provider="fake"))
    service, _, _ = make_service(provider, document=policy_document())

    outcome = run(service, service.route_for(skill="summarize-document"), template_for())

    assert outcome.skill == "summarize-document"
    assert outcome.attempts == 2
    assert outcome.degraded is True
    assert provider.seen_models == ["fk-fast", "fk-default"]
