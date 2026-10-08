"""LiteLLMProvider: the alias goes out, the answer comes back, failures are typed.

Nothing here needs a running LiteLLM. ``httpx.MockTransport`` intercepts at the
transport boundary, so the provider's own code — URL building, header assembly,
payload shape, status translation, response normalisation — is the thing under
test. The full stack over real sockets is ``tests/test_end_to_end.py``.

The tests are organised around the two properties that make this class safe to
put in front of a clinician: what leaves the process is the alias and nothing
else, and what an upstream failure contributes to a log line is a status code and
a short fragment — never the conversation, never the credential.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx
import pytest

from futurekind_gateway.providers.base import (
    ChatMessage,
    ChatRequest,
    ProviderAuthenticationError,
    ProviderError,
    ProviderRateLimitedError,
    ProviderRequestRejectedError,
    ProviderResponseInvalidError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from futurekind_gateway.providers.litellm import (
    CHAT_COMPLETIONS_PATH,
    LiteLLMProvider,
)

BASE_URL = "http://fk-litellm:4000"
UPSTREAM_KEY = "sk-master-secret-value"

#: A prompt fragment that must never come back out inside an error message.
CONVERSATION_FRAGMENT = "62-year-old with right hemiparesis"


def request_for(**overrides: Any) -> ChatRequest:
    defaults: dict[str, Any] = {
        "model": "fk-default",
        "messages": (ChatMessage(role="user", content="Summarise the impression."),),
    }
    defaults.update(overrides)
    return ChatRequest(**defaults)


def provider_for(
    handler: Any,
    *,
    base_url: str = BASE_URL,
    api_key: str | None = UPSTREAM_KEY,
    **settings: Any,
) -> LiteLLMProvider:
    return LiteLLMProvider(
        base_url=base_url,
        api_key=api_key,
        transport=httpx.MockTransport(handler),
        **settings,
    )


def completion_body(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "id": "chatcmpl-1",
        "model": "ollama/gpt-oss:20b",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "No acute intracranial process."},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 21, "completion_tokens": 7, "total_tokens": 28},
    }
    body.update(overrides)
    return body


def run(coro: Any) -> Any:
    return asyncio.run(coro)


# -- what goes out -------------------------------------------------------------------------


def test_the_alias_is_the_name_litellm_is_addressed_with() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=completion_body())

    result = run(provider_for(handler).chat(request_for()))

    assert seen[0].url.path == CHAT_COMPLETIONS_PATH
    assert seen[0].url.host == "fk-litellm"
    assert seen[0].url.port == 4000
    payload = json.loads(seen[0].content)
    assert payload["model"] == "fk-default"
    assert result.content == "No acute intracranial process."


def test_the_payload_is_openai_shaped_and_carries_the_sampling_knobs() -> None:
    seen: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(200, json=completion_body())

    run(
        provider_for(handler).chat(
            request_for(temperature=0.2, max_tokens=64, stop=("###",), extra={"top_k": 3})
        )
    )

    payload = seen[0]
    assert payload["messages"] == [{"role": "user", "content": "Summarise the impression."}]
    assert payload["temperature"] == 0.2
    assert payload["max_tokens"] == 64
    assert payload["stop"] == ["###"]
    # Passthrough reaches the upstream untouched, which is what `parameters` means.
    assert payload["top_k"] == 3


def test_the_credential_is_a_bearer_token_and_is_omitted_when_unset() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=completion_body())

    with_credential = provider_for(handler)
    run(with_credential.chat(request_for()))
    assert seen[0].headers["authorization"] == f"Bearer {UPSTREAM_KEY}"

    without = provider_for(handler, api_key=None)
    run(without.chat(request_for()))
    assert "authorization" not in seen[1].headers


def test_a_streaming_request_is_refused_before_it_leaves() -> None:
    """A streamed body would be parsed as a broken answer and blame LiteLLM for it."""

    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover - must not run
        raise AssertionError("a refused request must never reach the transport")

    with pytest.raises(ProviderRequestRejectedError) as caught:
        run(provider_for(handler).chat(request_for(extra={"stream": True})))

    assert caught.value.retryable is False
    assert "Streaming" in str(caught.value)


# -- what comes back -----------------------------------------------------------------------


def test_tokens_finish_reason_and_reported_model_are_normalised() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=completion_body())

    result = run(provider_for(handler).chat(request_for()))

    assert result.provider == "litellm"
    assert result.model == "ollama/gpt-oss:20b"
    assert result.finish_reason == "stop"
    assert result.usage.prompt_tokens == 21
    assert result.usage.completion_tokens == 7
    assert result.usage.total_tokens == 28


def test_a_missing_usage_block_reads_as_zero_not_as_an_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=completion_body(usage=None))

    result = run(provider_for(handler).chat(request_for()))

    assert result.usage.total_tokens == 0
    assert result.content  # the answer is still an answer


def test_a_backend_that_reports_no_model_leaves_the_alias_in_place() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=completion_body(model=None))

    result = run(provider_for(handler).chat(request_for()))

    assert result.model == "fk-default"


def test_an_empty_answer_is_the_models_doing_not_a_protocol_break() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = completion_body()
        body["choices"][0]["message"]["content"] = ""
        return httpx.Response(200, json=body)

    result = run(provider_for(handler).chat(request_for()))

    assert result.content == ""


@pytest.mark.parametrize(
    "body",
    [
        pytest.param({"choices": []}, id="no-choices"),
        pytest.param({"choices": [{"index": 0}]}, id="no-message"),
        pytest.param({"choices": [{"message": {"role": "assistant"}}]}, id="content-absent"),
        pytest.param({"choices": [{"message": {"content": ["part"]}}]}, id="content-not-text"),
        pytest.param({"choices": "not-a-list"}, id="choices-not-a-list"),
        pytest.param({}, id="empty-object"),
    ],
)
def test_an_answer_that_is_not_a_completion_is_a_protocol_break(body: dict[str, Any]) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=body)

    with pytest.raises(ProviderResponseInvalidError) as caught:
        run(provider_for(handler).chat(request_for()))

    # A protocol break is not retried: another model is unlikely to answer in a
    # different shape, and a second attempt doubles the cost of finding out.
    assert caught.value.retryable is False


def test_a_response_that_is_not_json_at_all_is_a_protocol_break() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>gateway in front of the gateway</html>")

    with pytest.raises(ProviderResponseInvalidError):
        run(provider_for(handler).chat(request_for()))


# -- failure translation -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("status", "error_type"),
    [
        pytest.param(401, ProviderAuthenticationError, id="unauthorized"),
        pytest.param(403, ProviderAuthenticationError, id="forbidden"),
        pytest.param(408, ProviderTimeoutError, id="request-timeout"),
        pytest.param(429, ProviderRateLimitedError, id="throttled"),
        pytest.param(400, ProviderRequestRejectedError, id="bad-request"),
        pytest.param(404, ProviderRequestRejectedError, id="unknown-alias"),
        pytest.param(422, ProviderRequestRejectedError, id="unprocessable"),
        pytest.param(500, ProviderUnavailableError, id="server-error"),
        pytest.param(502, ProviderUnavailableError, id="bad-gateway"),
        pytest.param(503, ProviderUnavailableError, id="overloaded"),
    ],
)
def test_each_upstream_status_becomes_the_failure_type_that_decides_retry(
    status: int,
    error_type: type[ProviderError],
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json={"error": {"message": "upstream said no"}})

    with pytest.raises(error_type) as caught:
        run(provider_for(handler).chat(request_for()))

    assert caught.value.retryable is error_type.retryable


def test_a_connection_failure_is_retryable_but_a_refusal_is_not() -> None:
    """The distinction the fallback chain depends on, in one pair of tests.

    An unreachable LiteLLM may be answered by the next capability in the chain;
    a LiteLLM that understood the request and said no must not, because that is
    how a refusal gets laundered into an answer that looks normal.
    """

    def unreachable(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route to fk-litellm")

    with pytest.raises(ProviderUnavailableError) as caught:
        run(provider_for(unreachable).chat(request_for()))
    assert caught.value.retryable is True

    def refused(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"error": {"message": "Unknown model: fk-default"}})

    with pytest.raises(ProviderRequestRejectedError) as rejected:
        run(provider_for(refused).chat(request_for()))
    assert rejected.value.retryable is False


def test_a_read_timeout_is_reported_as_a_timeout() -> None:
    def slow(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("too slow", request=request)

    with pytest.raises(ProviderTimeoutError) as caught:
        run(provider_for(slow).chat(request_for()))

    assert caught.value.retryable is True


# -- what an error may say ----------------------------------------------------------------


def test_an_upstream_error_never_carries_the_credential() -> None:
    leaked = f"authentication rejected for key {UPSTREAM_KEY}"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"message": leaked}})

    with pytest.raises(ProviderAuthenticationError) as caught:
        run(provider_for(handler).chat(request_for()))

    assert UPSTREAM_KEY not in str(caught.value)
    assert "[redacted]" in str(caught.value)


def test_an_upstream_error_is_short_and_flattened() -> None:
    rambling = "  " .join([CONVERSATION_FRAGMENT] * 200)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, text=rambling)

    with pytest.raises(ProviderRequestRejectedError) as caught:
        run(provider_for(handler).chat(request_for()))

    message = str(caught.value)
    assert "HTTP 400" in message
    assert len(message) < 400
    assert "\n" not in message


def test_the_request_content_is_never_echoed_into_a_failure() -> None:
    """The prompt stays in the Gateway. An error body quotes the upstream, not us."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": {"message": "upstream exploded"}})

    with pytest.raises(ProviderUnavailableError) as caught:
        run(
            provider_for(handler).chat(
                request_for(messages=(ChatMessage(role="user", content=CONVERSATION_FRAGMENT),))
            )
        )

    assert CONVERSATION_FRAGMENT not in str(caught.value)


# -- construction and health ---------------------------------------------------------------


@pytest.mark.parametrize(
    "base_url",
    [
        pytest.param("", id="empty"),
        pytest.param("fk-litellm:4000", id="no-scheme"),
        pytest.param("litellm.local", id="bare-host"),
        pytest.param("socks5://litellm:4000", id="wrong-scheme"),
    ],
)
def test_an_endpoint_that_is_not_a_usable_url_refuses_to_build(base_url: str) -> None:
    """No invented default, ever.

    A Gateway that guessed an address would send clinical requests to a host nobody
    chose; the registry turns this ``ValueError`` into a ``503 configuration_error``
    that names the setting instead.
    """
    with pytest.raises(ValueError, match="absolute http"):
        LiteLLMProvider(base_url=base_url)


def test_a_trailing_slash_and_surrounding_spaces_are_tolerated() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=completion_body())

    provider = provider_for(handler, base_url="  http://fk-litellm:4000/  ")

    assert provider.base_url == "http://fk-litellm:4000"
    run(provider.chat(request_for()))


def test_health_reports_the_upstream_as_it_found_it() -> None:
    def live(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/health/liveliness"
        return httpx.Response(200, text="OK")

    report = run(provider_for(live).health())

    assert report.healthy is True
    assert report.provider == "litellm"
    assert report.detail == BASE_URL


def test_an_unreachable_upstream_is_reported_and_never_raises() -> None:
    """``GET /health`` answers on a broken LiteLLM, because the answer is the point.

    A probe that raises would take the health endpoint down with it, and an
    operator would be left with no statement from the process at all.
    """

    def unreachable(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route to fk-litellm")

    report = run(provider_for(unreachable).health())

    assert report.healthy is False
    assert "ConnectError" in (report.detail or "")


def test_an_upstream_that_answers_badly_is_unhealthy_with_its_status() -> None:
    def broken(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="still starting")

    report = run(provider_for(broken).health())

    assert report.healthy is False
    assert "503" in (report.detail or "")


def test_close_releases_the_client_and_survives_being_called_twice() -> None:
    """The contract says closing is safe more than once, so prove it.

    What follows a close is asserted rather than assumed: httpx raises
    ``RuntimeError`` on a closed client, and that is the right answer — a provider
    nobody has shut down must fail loudly instead of quietly reopening a pool the
    process meant to close.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=completion_body())

    provider = provider_for(handler)
    run(provider.chat(request_for()))

    run(provider.close())
    run(provider.close())

    with pytest.raises(RuntimeError, match="closed"):
        run(provider.chat(request_for()))

