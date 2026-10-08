"""The Gateway client, checked at the byte level.

The stub Gateway used elsewhere cannot prove what actually goes over a wire, and
that is the boundary the platform's whole design rests on. So these tests drive a
real ``httpx`` request into a recording transport: the body, the header, the path,
and what every upstream failure becomes.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from typing import Any

import httpx
import pytest

from futurekind_radiology.copilot import RadiologyCopilot
from futurekind_radiology.errors import GatewayRequestError
from futurekind_radiology.gateway import GatewayClient, GatewayCompletion
from tests.conftest import RADIOLOGY_POLICY, fixture_text, submission

BASE = "http://127.0.0.1:8100"
KEY = "fk-application-key"


def ok(content: str, **overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "request_id": "fk-wire-1",
        "skill": "radiology-report",
        "capability": "reasoning",
        "model": "ollama/qwen3:14b",
        "provider": "litellm",
        "selected_by": "skill",
        "policy": dict(RADIOLOGY_POLICY),
        "attempts": 1,
        "degraded": False,
        "content": content,
        "finish_reason": "stop",
        "usage": {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3},
        "latency_ms": 10,
    }
    payload.update(overrides)
    return payload


def client_for(
    handler: Callable[[httpx.Request], httpx.Response],
    *,
    api_key: str | None = KEY,
    **kwargs: Any,
) -> GatewayClient:
    return GatewayClient(
        base_url=BASE, api_key=api_key, transport=httpx.MockTransport(handler), **kwargs
    )


def ask(client: GatewayClient, **call_kwargs: Any) -> Any:
    messages = [{"role": "user", "content": "Draft the report."}]
    skill = call_kwargs.pop("skill", "radiology-report")
    return asyncio.run(client.complete(skill=skill, messages=messages, **call_kwargs))


# -- what leaves the application ----------------------------------------------------------------


def test_the_body_names_the_skill_and_nothing_else() -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=ok(fixture_text("normal_ct_head.json")))

    ask(client_for(handler))

    assert seen["path"] == "/chat"
    assert set(seen["body"]) == {"skill", "messages"}
    assert seen["body"]["skill"] == "radiology-report"


def test_no_field_can_smuggle_infrastructure_into_the_request() -> None:
    """The Gateway refuses these, and an application that never sends them cannot
    be quietly edited into sending them."""
    captured: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(json.loads(request.content))
        return httpx.Response(200, json=ok(fixture_text("normal_ct_head.json")))

    ask(client_for(handler), temperature=0.2)

    body = captured[0]
    assert body["temperature"] == 0.2
    for forbidden in ("model", "provider", "api_base", "allow_downgrade", "max_completion_tokens"):
        assert forbidden not in body


def test_the_credential_is_a_header_and_never_part_of_the_payload() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["header"] = request.headers.get("authorization", "")
        seen["body"] = request.content.decode()
        return httpx.Response(200, json=ok(fixture_text("normal_ct_head.json")))

    ask(client_for(handler))

    assert seen["header"] == f"Bearer {KEY}"
    assert KEY not in seen["body"]


def test_a_client_with_no_credential_sends_no_authorization_header() -> None:
    seen: dict[str, bool] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["sent"] = "authorization" in request.headers
        return httpx.Response(200, json=ok(fixture_text("normal_ct_head.json")))

    ask(client_for(handler, api_key=None))

    assert seen["sent"] is False


def test_a_trailing_slash_does_not_become_a_double_path() -> None:
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        return httpx.Response(200, json=ok("{}"))

    client = GatewayClient(
        base_url=f"{BASE}/", transport=httpx.MockTransport(handler), api_key=KEY
    )
    ask(client)

    assert paths == ["/chat"]


@pytest.mark.parametrize("base_url", ["127.0.0.1:8100", "localhost:8100", "/chat"])
def test_a_base_url_that_is_not_an_absolute_http_url_is_refused_early(base_url: str) -> None:
    with pytest.raises(ValueError):
        GatewayClient(base_url=base_url)


# -- what comes back ----------------------------------------------------------------------------


def test_a_good_answer_is_read_in_full() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=ok(fixture_text("normal_ct_head.json")))

    completion = ask(client_for(handler))

    assert isinstance(completion, GatewayCompletion)
    assert completion.policy["clinical_risk"] == "high"
    assert completion.usage["total_tokens"] == 3
    assert completion.ran_out_of_tokens is False


def test_a_truncated_answer_is_visible_to_the_copilot() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=ok("{}", finish_reason="length"))

    completion = ask(client_for(handler))

    assert completion.ran_out_of_tokens is True


@pytest.mark.parametrize(
    ("status", "code", "retryable"),
    [
        (401, "unauthenticated", False),
        (403, "approval_required", False),
        (404, "unknown_skill", False),
        (422, "invalid_request", False),
        (502, "provider_unavailable", True),
        (504, "provider_timeout", True),
    ],
)
def test_an_upstream_refusal_keeps_its_own_name(status: int, code: str, retryable: bool) -> None:
    """The Gateway's code is the diagnosis. Re-labelling every failure as
    "gateway failed" would make a policy refusal look like an outage."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status,
            json={
                "error": {
                    "code": code,
                    "message": "A message the operator already knows how to act on.",
                    "retryable": retryable,
                    "request_id": "fk-wire-1",
                    "details": {"limit": "max_messages"},
                }
            },
        )

    with pytest.raises(GatewayRequestError) as caught:
        ask(client_for(handler))

    error = caught.value.to_body()["error"]
    assert error["details"]["upstream_code"] == code
    assert error["details"]["http_status"] == status
    assert error["request_id"] == "fk-wire-1"
    assert error["retryable"] is retryable
    assert error["message"].startswith("A message the operator")


def test_an_upstream_message_too_long_is_cut_without_becoming_a_lie() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            502,
            json={"error": {"code": "x", "message": "y" * 4_000, "retryable": True}},
        )

    with pytest.raises(GatewayRequestError) as caught:
        ask(client_for(handler))

    assert len(caught.value.message) <= 500


def test_an_upstream_body_that_is_not_the_error_shape_is_still_a_refusal() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="<html>proxy error</html>")

    with pytest.raises(GatewayRequestError) as caught:
        ask(client_for(handler))

    assert "HTTP 503" in caught.value.message
    assert caught.value.details["http_status"] == 503


def test_an_answer_of_the_wrong_shape_is_refused_without_quoting_it() -> None:
    """Pydantic's error entries include the offending value. Here the offending
    value is patient text, and a refusal is the one artefact guaranteed to be
    logged, printed and forwarded — so the values are stripped."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=ok("{}", model={"clinical_note": "A 4.5 cm basal ganglia haematoma."}),
        )

    with pytest.raises(GatewayRequestError) as caught:
        ask(client_for(handler))

    rendered = json.dumps(caught.value.to_body())
    assert "basal ganglia" not in rendered
    assert "haematoma" not in rendered
    assert any(entry["type"] == "string_type" for entry in caught.value.details["problem"])


def test_an_unparseable_json_body_is_refused() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not json at all")

    with pytest.raises(GatewayRequestError) as caught:
        ask(client_for(handler))

    assert "documented completion shape" in caught.value.message


# -- the transport failing, which is how a hospital outage actually looks -----------------------


def test_a_gateway_that_does_not_answer_in_time_is_a_timeout_not_a_crash() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("too slow", request=request)

    with pytest.raises(GatewayRequestError) as caught:
        ask(client_for(handler, timeout_seconds=1.0))

    error = caught.value.to_body()["error"]
    assert error["code"] == "gateway_request_failed"
    assert error["retryable"] is True
    assert error["details"]["timeout_seconds"] == 1.0


def test_a_gateway_that_is_not_running_says_so_and_names_itself() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    with pytest.raises(GatewayRequestError) as caught:
        ask(client_for(handler))

    error = caught.value.to_body()["error"]
    assert error["details"]["base_url"] == BASE
    assert error["retryable"] is True
    assert "FK_RADIOLOGY_GATEWAY_BASE_URL" in error["message"]


# -- the whole application over a real serializer -----------------------------------------------


def test_the_copilot_drafts_from_bytes_that_crossed_a_transport() -> None:
    """The stub Gateway elsewhere is a signature check; this is the real client,
    so JSON serialisation, the path, the header and the parse all have to hold."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=ok(fixture_text("hypertensive_bleed.json")))

    client = client_for(handler)
    copilot = RadiologyCopilot(client)

    report = asyncio.run(copilot.draft(submission()))

    assert report.model_provenance.request_id == "fk-wire-1"
    assert "9 mm midline shift" in report.impression
