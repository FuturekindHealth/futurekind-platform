"""End to end over real sockets: application → Gateway → LiteLLM → backend.

Everything else in this suite crosses the provider boundary inside one process.
This file does not: two uvicorn servers run on loopback ports in this process,
the Gateway reaches LiteLLM over a real TCP connection with a real bearer token,
and the assertions are made on bytes that travelled over that wire.

What is simulated is only the last hop. There is no Ollama here, and none of
these tests needs one: the stub answers by looking the alias up in the
repository's own ``configs/litellm/config.yaml``, which is exactly the decision
``ADR-0002`` assigns to LiteLLM. Anything it does with a request is a decision the
platform has already agreed to delegate.

The Gateway itself is not imitated. It is assembled by ``build_production_app``
from ``FK_GATEWAY_*`` variables — the same entrypoint the container runs — so
catalogue discovery, the alias check and the provider registration are the
production ones.

Run it with the rest of the suite: nothing here needs Docker, a model or a network.
"""

from __future__ import annotations

import asyncio
import json
import os
import socket
import threading
import time
from collections.abc import Iterator
from typing import Any

import httpx
import pytest
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from futurekind_gateway.config import ENV_PREFIX, GatewaySettings
from futurekind_gateway.errors import ConfigurationError
from futurekind_gateway.litellm_config import LiteLLMConfig
from futurekind_gateway.main import build_production_app

GATEWAY_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
REPO_CATALOG = os.path.join(GATEWAY_ROOT, "models.yaml")
REPO_LITELLM_CONFIG = os.path.abspath(
    os.path.join(GATEWAY_ROOT, "..", "..", "configs", "litellm", "config.yaml")
)

GATEWAY_KEY = "fk-e2e-application-key"
LITELLM_KEY = "fk-e2e-master-key"

#: Markers the stub reacts to, so the failure paths can be proved over a wire
#: without a second process, a broken backend, or a slow test suite.
FAIL_MARKER = "[[unavailable]]"
UNKNOWN_MARKER = "[[unknown-alias]]"
SLOW_MARKER = "[[slow]]"


class StubLiteLLM:
    """The last hop, delegated honestly, with a record of what arrived.

    ``addressed_as`` is the list that makes this file worth writing: it is what the
    Gateway actually put in the OpenAI ``model`` field, read off the far side.
    """

    def __init__(self, config_path: str) -> None:
        self.config = LiteLLMConfig.load(config_path)
        self.addressed_as: list[str] = []
        self.authorisation: list[str | None] = []
        self.app = self._build()

    def _build(self) -> FastAPI:
        app = FastAPI()

        @app.get("/health/liveliness")
        async def liveliness() -> dict[str, str]:
            return {"status": "alive"}

        @app.post("/v1/chat/completions")
        async def completions(request: Request) -> JSONResponse:
            body = await request.json()
            alias = str(body.get("model"))
            self.addressed_as.append(alias)
            self.authorisation.append(request.headers.get("authorization"))

            prompt = " ".join(
                str(message.get("content", "")) for message in body.get("messages", [])
            )
            if FAIL_MARKER in prompt:
                return JSONResponse(
                    {"error": {"message": "deployment unavailable"}}, status_code=503
                )
            if UNKNOWN_MARKER in prompt:
                return JSONResponse(
                    {"error": {"message": f"Unknown model: {alias}"}}, status_code=404
                )
            if SLOW_MARKER in prompt:
                await asyncio.sleep(1.5)

            targets = self.config.targets_for(alias)
            if not targets:
                return JSONResponse(
                    {"error": {"message": f"no deployment named {alias}"}}, status_code=404
                )
            # The delegated decision, read from the shipped file: alias in,
            # configured deployment out.
            backend = targets[0]
            return JSONResponse(
                {
                    "id": "chatcmpl-stub",
                    "object": "chat.completion",
                    "created": int(time.time()),
                    "model": backend,
                    "choices": [
                        {
                            "index": 0,
                            "message": {
                                "role": "assistant",
                                "content": f"{alias} ran on {backend}",
                            },
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {"prompt_tokens": 4, "completion_tokens": 6, "total_tokens": 10},
                }
            )

        return app


class RunningServer:
    """One uvicorn server on its own thread, stopped when the fixture ends."""

    def __init__(self, app: FastAPI, port: int) -> None:
        self.port = port
        self.base_url = f"http://127.0.0.1:{port}"
        self.server = uvicorn.Server(
            uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
        )
        self.thread = threading.Thread(target=self.server.run, daemon=True)

    def start(self, timeout: float = 15.0) -> RunningServer:
        self.thread.start()
        deadline = time.time() + timeout
        while not self.server.started and time.time() < deadline:
            time.sleep(0.02)
        if not self.server.started:
            raise RuntimeError(f"server on port {self.port} never became ready")
        return self

    def stop(self) -> None:
        self.server.should_exit = True
        self.thread.join(timeout=15.0)


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def with_environment(**values: str) -> dict[str, str | None]:
    """Set ``FK_GATEWAY_*`` values and return what to put back afterwards."""
    saved: dict[str, str | None] = {}
    for name, value in values.items():
        key = f"{ENV_PREFIX}{name}"
        saved[key] = os.environ.get(key)
        os.environ[key] = value
    return saved


def restore_environment(saved: dict[str, str | None]) -> None:
    for key, value in saved.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


@pytest.fixture(scope="module")
def stack() -> Iterator[dict[str, Any]]:
    """A shaped-like-production Gateway and a stub LiteLLM, both over TCP."""
    stub = StubLiteLLM(REPO_LITELLM_CONFIG)
    stub_server = RunningServer(stub.app, free_port()).start()
    saved = with_environment(
        MODELS_PATH=REPO_CATALOG,
        LITELLM_CONFIG=REPO_LITELLM_CONFIG,
        LITELLM_BASE_URL=stub_server.base_url,
        LITELLM_API_KEY=LITELLM_KEY,
        API_KEYS=GATEWAY_KEY,
        HOST="127.0.0.1",
        PORT=str(free_port()),
        # One second, so the timeout path is reachable in a test run instead of
        # being asserted about. Everything here answers in milliseconds.
        REQUEST_TIMEOUT_SECONDS="1",
        JSON_LOGS="false",
    )
    gateway_server: RunningServer | None = None
    try:
        gateway_server = RunningServer(build_production_app(), int(os.environ[f"{ENV_PREFIX}PORT"]))
        gateway_server.start()
        yield {
            "gateway": gateway_server,
            "litellm": stub,
            "settings": GatewaySettings.from_env(),
        }
    finally:
        if gateway_server is not None:
            gateway_server.stop()
        stub_server.stop()
        restore_environment(saved)


def client_for(stack: dict[str, Any]) -> httpx.Client:
    return httpx.Client(base_url=stack["gateway"].base_url, timeout=20.0)


def auth() -> dict[str, str]:
    return {"Authorization": f"Bearer {GATEWAY_KEY}"}


def ask(
    stack: dict[str, Any],
    skill: str,
    text: str,
    *,
    path: str = "/chat",
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    """One request, in whichever dialect the path speaks."""
    body: dict[str, Any] = {"messages": [{"role": "user", "content": text}]}
    body["skill" if path == "/chat" else "model"] = skill
    with client_for(stack) as client:
        return client.post(path, json=body, headers=headers if headers is not None else auth())


# -- the headline: one request, all the way through -----------------------------------------


def test_platform_chat_answers_through_the_full_stack(stack: dict[str, Any]) -> None:
    """The first complete end-to-end request, and everything it had to pass."""
    response = ask(stack, "platform-chat", "What is this platform?")

    assert response.status_code == 200
    payload = response.json()
    assert payload["skill"] == "platform-chat"
    assert payload["capability"] == "default"
    assert payload["provider"] == "litellm"
    assert payload["selected_by"] == "skill"
    assert payload["policy"]["clinical_risk"] == "low"
    # What the far side answered with is what the Gateway reports: the delegation held.
    assert payload["content"] == "fk-default ran on ollama/gpt-oss:20b"
    assert payload["model"] == "ollama/gpt-oss:20b"
    assert payload["usage"]["total_tokens"] == 10
    assert payload["attempts"] == 1


def test_the_alias_crossed_the_wire_and_nothing_else_did(stack: dict[str, Any]) -> None:
    """The alias contract, measured on a socket.

    The Gateway addressed LiteLLM by alias. The skill name and the weights id both
    stopped at the boundary — if either ever crosses, this is the assertion that
    says so.
    """
    before = len(stack["litellm"].addressed_as)

    ask(stack, "summarize-document", "short note")

    assert stack["litellm"].addressed_as[before:] == ["fk-fast"]


def test_upstream_received_its_own_credential_not_the_applications(stack: dict[str, Any]) -> None:
    """Two boundaries, two secrets: the application's key stops at the Gateway."""
    before = len(stack["litellm"].authorisation)

    ask(stack, "platform-chat", "hi")

    assert stack["litellm"].authorisation[before:] == [f"Bearer {LITELLM_KEY}"]


def test_the_gateway_measured_latency_is_reported_with_the_answer(stack: dict[str, Any]) -> None:
    payload = ask(stack, "platform-chat", "hi").json()

    assert payload["latency_ms"] >= 0
    assert payload["request_id"]


# -- the rules are enforced on the way, not after --------------------------------------------


def test_an_unauthenticated_request_never_reaches_a_model(stack: dict[str, Any]) -> None:
    before = len(stack["litellm"].addressed_as)

    response = ask(stack, "platform-chat", "hi", headers={})

    assert response.status_code == 401
    assert len(stack["litellm"].addressed_as) == before


def test_a_high_risk_skill_that_cannot_fall_back_reports_the_outage(stack: dict[str, Any]) -> None:
    """Radiology allows no downgrade, so a 503 upstream is the answer, not a retry."""
    before = len(stack["litellm"].addressed_as)

    response = ask(stack, "radiology-report", f"{FAIL_MARKER} impression")

    assert response.status_code == 502
    error = response.json()["error"]
    assert error["code"] == "provider_unavailable"
    assert error["retryable"] is True
    # One attempt only: the chain was suppressed by the skill's own policy.
    assert len(stack["litellm"].addressed_as) == before + 1


def test_a_policy_timeout_becomes_a_504_rather_than_a_hang(stack: dict[str, Any]) -> None:
    started = time.time()

    response = ask(stack, "platform-chat", SLOW_MARKER)

    assert response.status_code == 504
    assert response.json()["error"]["code"] == "provider_timeout"
    assert time.time() - started < 8.0


def test_an_unknown_alias_upstream_is_refused_rather_than_retried(stack: dict[str, Any]) -> None:
    before = len(stack["litellm"].addressed_as)

    response = ask(stack, "clinical-chat", UNKNOWN_MARKER)

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "provider_request_rejected"
    assert len(stack["litellm"].addressed_as) == before + 1


def test_a_request_over_the_skill_limit_is_refused_before_the_wire(stack: dict[str, Any]) -> None:
    """`summarize-document` declares eight messages; nine never reach LiteLLM."""
    before = len(stack["litellm"].addressed_as)
    body = {
        "skill": "summarize-document",
        "messages": [{"role": "user", "content": f"line {index}"} for index in range(9)],
    }

    with client_for(stack) as client:
        response = client.post("/chat", json=body, headers=auth())

    assert response.status_code == 422
    assert len(stack["litellm"].addressed_as) == before


# -- the OpenAI door, over the same wire -----------------------------------------------------


def test_an_openai_interface_gets_an_answer_through_the_gateway(stack: dict[str, Any]) -> None:
    with client_for(stack) as client:
        listed = client.get("/v1/models", headers=auth())
        completion = client.post(
            "/v1/chat/completions",
            json={
                "model": "platform-chat",
                "messages": [{"role": "user", "content": "Hello"}],
            },
            headers=auth(),
        )

    assert listed.status_code == 200
    ids = [item["id"] for item in listed.json()["data"]]
    assert "platform-chat" in ids
    assert "radiology-report" in ids
    assert completion.status_code == 200
    assert completion.json()["choices"][0]["message"]["content"].startswith("fk-default ran on")
    assert completion.json()["model"] == "platform-chat"


def test_the_interface_never_sees_an_infrastructure_name_in_its_envelope(
    stack: dict[str, Any],
) -> None:
    """The routing decision stays inside the Gateway, in both OpenAI responses.

    Scoped deliberately to the envelope — ids, model field, metadata — and not to
    the answer text. The Gateway controls the paths a request travels; it cannot
    control what a model chooses to say, and a test that pretended otherwise would
    be asserting a privacy property the platform does not have.
    """
    with client_for(stack) as client:
        listed = client.get("/v1/models", headers=auth()).json()
        completion = client.post(
            "/v1/chat/completions",
            json={"model": "platform-chat", "messages": [{"role": "user", "content": "hi"}]},
            headers=auth(),
        ).json()

    envelope = json.dumps(
        {
            "models": listed,
            "completion": {key: value for key, value in completion.items() if key != "choices"},
        }
    )
    for forbidden in ("ollama", "fk-default", "gpt-oss", "litellm", "reasoning"):
        assert forbidden not in envelope

    assert completion["model"] == "platform-chat"
    assert listed["data"][0]["object"] == "model"


def test_streaming_is_refused_over_the_wire_too(stack: dict[str, Any]) -> None:
    response = ask(stack, "platform-chat", "hi", path="/v1/chat/completions")
    with client_for(stack) as client:
        streamed = client.post(
            "/v1/chat/completions",
            json={
                "model": "platform-chat",
                "messages": [{"role": "user", "content": "hi"}],
                "stream": True,
            },
            headers=auth(),
        )

    assert response.status_code == 200
    assert streamed.status_code == 501


# -- health, readiness, and the startup refusal ----------------------------------------------


def test_health_and_readiness_both_answer(stack: dict[str, Any]) -> None:
    with client_for(stack) as client:
        health = client.get("/health")
        ready = client.get("/health/ready")

    assert health.status_code == 200
    assert ready.status_code == 200
    assert ready.json()["ready"] is True
    providers = [item for item in health.json()["components"] if item["name"] == "providers"]
    assert providers, health.json()
    assert providers[0]["healthy"] is True, providers[0]


def test_health_names_no_provider_to_an_unauthenticated_probe(
    stack: dict[str, Any],
) -> None:
    """The probe holds no credential, so it gets verdicts: which component is down,
    never which backend or model. The named inventory is behind `GET /models`."""
    with client_for(stack) as client:
        body = client.get("/health").text

    assert "litellm" not in body
    assert "models.yaml" not in body
    assert "catalog" not in json.loads(body)


def test_the_catalogue_reports_the_real_transport(stack: dict[str, Any]) -> None:
    with client_for(stack) as client:
        payload = client.get("/models", headers=auth()).json()

    assert payload["providers_registered"] == ["litellm"]
    assert payload["providers_missing"] == []


def test_the_process_refuses_to_start_when_an_alias_is_missing(tmp_path: Any) -> None:
    """The startup failure, proved through the environment a container sets.

    A catalogue that names ``fk-default`` beside a LiteLLM file that does not know
    it is a deployment that cannot answer on that capability. It has to fail here,
    naming both files, rather than in front of a clinician.
    """
    incomplete = tmp_path / "litellm-config.yaml"
    incomplete.write_text(
        "model_list:\n  - model_name: fk-something-else\n    litellm_params:\n"
        "      model: ollama/x\n",
        encoding="utf-8",
    )
    saved = with_environment(MODELS_PATH=REPO_CATALOG, LITELLM_CONFIG=str(incomplete))
    try:
        with pytest.raises(ConfigurationError) as caught:
            build_production_app()
    finally:
        restore_environment(saved)

    assert "fk-default" in caught.value.message
    assert str(incomplete) in caught.value.details["litellm_config"]
