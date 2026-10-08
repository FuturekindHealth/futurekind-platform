"""Unit tests for the provider contract and the registry that owns it."""

from __future__ import annotations

import asyncio

import pytest

from futurekind_gateway.errors import ConfigurationError, ProviderNotImplementedError
from futurekind_gateway.providers import ProviderRegistry
from futurekind_gateway.providers.base import (
    ChatMessage,
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
from tests.conftest import FakeProvider


def run(coroutine):  # noqa: ANN201
    return asyncio.run(coroutine)


class TestProviderContract:
    def test_the_base_class_cannot_be_instantiated(self) -> None:
        with pytest.raises(TypeError):
            Provider()  # type: ignore[abstract]

    def test_chat_is_the_only_mandatory_method(self) -> None:
        class Minimal(Provider):
            name = "minimal"

            async def chat(self, request: ChatRequest) -> ChatResult:
                return ChatResult(content="ok", model=request.model, provider=self.name)

        instance = Minimal()
        result = run(instance.chat(ChatRequest(model="m", messages=(ChatMessage("user", "hi"),))))

        assert result.content == "ok"
        assert result.provider == "minimal"

    def test_health_answers_optimistically_until_a_provider_overrides_it(self) -> None:
        class Minimal(Provider):
            name = "minimal"

            async def chat(self, request: ChatRequest) -> ChatResult:  # pragma: no cover
                raise NotImplementedError

        health = run(Minimal().health())

        assert health.healthy is True
        assert health.provider == "minimal"

    def test_close_is_safe_by_default(self) -> None:
        class Minimal(Provider):
            name = "minimal"

            async def chat(self, request: ChatRequest) -> ChatResult:  # pragma: no cover
                raise NotImplementedError

        assert run(Minimal().close()) is None

    def test_a_provider_must_accept_the_resolved_model_not_a_capability(self) -> None:
        request = ChatRequest(
            model="gpt-oss:20b",
            messages=(ChatMessage(role="user", content="question"),),
        )

        assert request.to_dict()["model"] == "gpt-oss:20b"
        assert "capability" not in request.to_dict()

    @pytest.mark.parametrize(
        "role",
        ["system", "user", "assistant"],
    )
    def test_supported_roles(self, role: str) -> None:
        assert ChatMessage(role=role, content="x").role == role

    def test_unsupported_roles_are_rejected(self) -> None:
        with pytest.raises(ValueError, match="Unsupported message role"):
            ChatMessage(role="patient", content="x")

    def test_non_string_content_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="content must be a string"):
            ChatMessage(role="user", content=42)  # type: ignore[arg-type]

    def test_a_request_without_a_model_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="resolved model id"):
            ChatRequest(model="", messages=(ChatMessage(role="user", content="x"),))

    def test_a_request_without_messages_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="at least one message"):
            ChatRequest(model="m", messages=())

    def test_request_payload_is_openai_shaped_and_omits_unset_options(self) -> None:
        request = ChatRequest(
            model="m",
            messages=(ChatMessage(role="system", content="be brief"),),
            extra={"top_p": 0.9},
        )

        payload = request.to_dict()

        assert payload["messages"] == [{"role": "system", "content": "be brief"}]
        assert "temperature" not in payload
        assert "max_tokens" not in payload
        assert "stop" not in payload
        assert payload["top_p"] == 0.9

    def test_stop_sequences_are_forwarded_as_a_list(self) -> None:
        request = ChatRequest(
            model="m",
            messages=(ChatMessage(role="user", content="x"),),
            stop=("###", "\n\n"),
        )
        assert request.to_dict()["stop"] == ["###", "\n\n"]

    def test_usage_totals_are_derived(self) -> None:
        usage = TokenUsage(prompt_tokens=7, completion_tokens=3)
        assert usage.total_tokens == 10
        assert usage.to_dict() == {
            "prompt_tokens": 7,
            "completion_tokens": 3,
            "total_tokens": 10,
        }

    def test_health_dict_reports_detail_only_when_present(self) -> None:
        assert ProviderHealth(provider="p", healthy=True).to_dict() == {
            "provider": "p",
            "healthy": True,
        }

    def test_a_result_without_content_is_rejected_at_construction(self) -> None:
        with pytest.raises(ValueError, match="not None"):
            ChatResult(content=None, model="m", provider="p")  # type: ignore[arg-type]


class TestProviderErrors:
    @pytest.mark.parametrize(
        ("error", "retryable"),
        [
            (ProviderError("x"), False),
            (ProviderUnavailableError("x"), True),
            (ProviderTimeoutError("x"), True),
            (ProviderRateLimitedError("x"), True),
            (ProviderAuthenticationError("x"), False),
            (ProviderRequestRejectedError("x"), False),
            (ProviderResponseInvalidError("x"), False),
        ],
    )
    def test_only_transient_failures_are_retryable(self, error: Exception, retryable: bool) -> None:
        assert type(error).retryable is retryable

    def test_a_provider_error_keeps_its_provider_name(self) -> None:
        assert ProviderUnavailableError("down", provider="ollama").provider == "ollama"


class TestProviderRegistry:
    def test_an_empty_registry_is_the_skeleton_state(self) -> None:
        registry = ProviderRegistry()

        assert registry.names() == ()
        assert len(registry) == 0

    def test_asking_for_an_unregistered_provider_names_the_missing_one(self) -> None:
        registry = ProviderRegistry()
        registry.register("other", lambda: FakeProvider())

        with pytest.raises(ProviderNotImplementedError) as caught:
            registry.get("ollama")

        assert caught.value.code == "provider_not_implemented"
        assert caught.value.status_code == 501
        assert caught.value.details["registered_providers"] == ["other"]
        assert caught.value.message == (
            "Provider 'ollama' has no implementation registered with this Gateway"
        )

    def test_instances_are_built_lazily_and_then_reused(self) -> None:
        builds = []

        def factory() -> Provider:
            builds.append(1)
            return FakeProvider()

        registry = ProviderRegistry()
        registry.register("fake", factory)

        assert builds == []
        first = registry.get("fake")
        second = registry.get("fake")

        assert builds == [1]
        assert first is second

    def test_a_provider_class_is_a_valid_factory(self) -> None:
        registry = ProviderRegistry()
        registry.register("fake", FakeProvider)

        assert isinstance(registry.get("fake"), FakeProvider)

    def test_registration_requires_a_name(self) -> None:
        registry = ProviderRegistry()
        for bad in ("", "   ", None):
            with pytest.raises(ConfigurationError, match="non-empty name"):
                registry.register(bad, FakeProvider)  # type: ignore[arg-type]

    def test_registration_requires_a_callable(self) -> None:
        registry = ProviderRegistry()
        with pytest.raises(ConfigurationError, match="callable factory"):
            registry.register("fake", "not-callable")  # type: ignore[arg-type]

    def test_double_registration_is_refused_unless_replaced(self) -> None:
        registry = ProviderRegistry()
        registry.register("fake", FakeProvider)

        with pytest.raises(ConfigurationError, match="already registered"):
            registry.register("fake", FakeProvider)

        registry.register("fake", lambda: FakeProvider(), replace=True)
        assert registry.is_registered("fake")

    def test_replacing_a_provider_discards_the_cached_instance(self) -> None:
        first = FakeProvider()
        replacement = FakeProvider()
        registry = ProviderRegistry()
        registry.register("fake", lambda: first)
        assert registry.get("fake") is first

        registry.register("fake", lambda: replacement, replace=True)

        assert registry.get("fake") is replacement

    def test_a_factory_must_produce_a_provider(self) -> None:
        registry = ProviderRegistry()
        registry.register("fake", lambda: "not a provider")

        with pytest.raises(ConfigurationError, match="did not return a Provider"):
            registry.get("fake")

    def test_a_declared_name_must_match_the_registration(self) -> None:
        class Mismatched(Provider):
            name = "something-else"

            async def chat(self, request: ChatRequest) -> ChatResult:  # pragma: no cover
                raise NotImplementedError

        registry = ProviderRegistry()
        registry.register("fake", Mismatched)

        with pytest.raises(ConfigurationError, match="declares the name"):
            registry.get("fake")

    def test_a_failing_factory_is_reported_as_configuration(self) -> None:
        def broken() -> Provider:
            raise RuntimeError("bad credentials")

        registry = ProviderRegistry()
        registry.register("fake", broken)

        with pytest.raises(ConfigurationError, match="failed to initialize"):
            registry.get("fake")

    def test_membership_and_iteration_use_sorted_names(self) -> None:
        registry = ProviderRegistry()
        registry.register("zeta", FakeProvider)
        registry.register("alpha", FakeProvider)

        assert registry.names() == ("alpha", "zeta")
        assert "alpha" in registry
        assert "missing" not in registry
        assert list(registry) == ["alpha", "zeta"]

    def test_unregister_forgets_both_factory_and_instance(self) -> None:
        built = FakeProvider()
        registry = ProviderRegistry()
        registry.register("fake", lambda: built)
        registry.get("fake")

        registry.unregister("fake")

        assert registry.names() == ()
        assert not registry.is_registered("fake")

    def test_close_all_forgets_the_instances_it_closed(self) -> None:
        """A closed registry must rebuild on demand, not hand back a closed client."""
        registry = ProviderRegistry()
        registry.register("fake", FakeProvider)
        first = registry.get("fake")

        run(registry.close_all())

        assert registry.get("fake") is not first

    def test_close_all_closes_only_built_instances(self) -> None:
        built = FakeProvider()
        never_built = FakeProvider()
        registry = ProviderRegistry()
        registry.register("fake", lambda: built)
        registry.register("never", lambda: never_built)
        registry.get("fake")

        run(registry.close_all())

        assert built.closed == 1
        assert never_built.closed == 0

    def test_close_all_survives_a_provider_that_fails_to_close(self) -> None:
        class Unfriendly(FakeProvider):
            async def close(self) -> None:
                raise RuntimeError("connection stuck")

        registry = ProviderRegistry()
        registry.register("fake", Unfriendly)
        first = registry.get("fake")

        run(registry.close_all())  # must not raise

        assert registry.get("fake") is not first

    def test_close_on_an_untouched_provider_is_a_no_op(self) -> None:
        registry = ProviderRegistry()
        registry.register("fake", FakeProvider)

        run(registry.close("fake"))
