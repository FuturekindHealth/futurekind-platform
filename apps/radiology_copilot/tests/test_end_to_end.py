"""End to end over real sockets: clinician's request → copilot → Gateway → LiteLLM.

Nothing in this file is mocked. Three HTTP servers run in-process on loopback
ports — the copilot, the production Gateway, and a stub that plays LiteLLM — and
every assertion is made on bytes that travelled over a socket between them.

Only the last hop is simulated, and it is simulated honestly: the stub reads the
repository's own ``configs/litellm/config.yaml`` and answers from whichever
deployment the alias names, which is precisely the decision ADR-0002 hands to
LiteLLM. There is no Ollama here and none is needed to prove the plumbing.

Run it with the rest of the suite: ``pytest`` and it starts the servers itself.
"""

from __future__ import annotations

import asyncio
import os
import socket
import sys
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
import uvicorn
import yaml
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from futurekind_radiology.api import build_app
from futurekind_radiology.settings import CopilotSettings
from tests.conftest import REQUIRED_OUTPUT

REPO = Path(__file__).resolve().parents[3]
GATEWAY_ROOT = REPO / "core" / "gateway"
GATEWAY_CATALOG = GATEWAY_ROOT / "models.yaml"
LITELLM_CONFIG = REPO / "configs" / "litellm" / "config.yaml"
FIXTURES = Path(__file__).parent / "fixtures"

# The copilot talks to the Gateway over HTTP, never by importing it. This test is
# the one exception, and for a different reason: it is the *operator* starting the
# Gateway, the way ``compose`` would.
sys.path.insert(0, str(GATEWAY_ROOT / "src"))

from futurekind_gateway.main import build_production_app  # noqa: E402

GATEWAY_KEY = "fk-radiology-application-key"
LITELLM_KEY = "fk-e2e-master-key"

#: A marker the stub reacts to, carried into the prompt by the legitimate redraft
#: channel. It is how the prose-refusal path is proved without a broken model.
PROSE_MARKER = "[[answer-in-prose]]"


class StubLiteLLM:
    """The delegated decision, read out of the shipped file: alias in, backend out."""

    def __init__(self, config_path: Path) -> None:
        document = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        self.targets: dict[str, str] = {
            row["model_name"]: row["litellm_params"]["model"] for row in document["model_list"]
        }
        self.addressed_as: list[str] = []
        self.authorisation: list[str | None] = []
        self.prompts: list[str] = []
        self.app = self._build()

    def _answer(self, prompt: str) -> tuple[str, str]:
        if PROSE_MARKER in prompt:
            return (
                (FIXTURES / "prose_answer.txt").read_text(encoding="utf-8"),
                "stop",
            )
        # The canned answer is chosen by what the clinician dictated, so the
        # golden cases exercise the same routing without a second stub.
        if "hemiparesis" in prompt:
            return (FIXTURES / "normal_ct_head.json").read_text(encoding="utf-8"), "stop"
        return (FIXTURES / "hypertensive_bleed.json").read_text(encoding="utf-8"), "stop"

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
            self.prompts.append(prompt)

            backend = self.targets.get(alias)
            if backend is None:
                return JSONResponse(
                    {"error": {"message": f"Unknown model: {alias}"}}, status_code=404
                )
            content, finish_reason = self._answer(prompt)
            return JSONResponse(
                {
                    "id": "chatcmpl-e2e",
                    "object": "chat.completion",
                    "created": int(time.time()),
                    "model": backend,
                    "choices": [
                        {
                            "index": 0,
                            "message": {"role": "assistant", "content": content},
                            "finish_reason": finish_reason,
                        }
                    ],
                    "usage": {"prompt_tokens": 610, "completion_tokens": 205, "total_tokens": 815},
                }
            )

        return app


class RunningServer:
    """One uvicorn server on its own thread, stopped when the fixture ends."""

    def __init__(self, app: FastAPI, port: int) -> None:
        self.port = port
        self.base_url = f"http://127.0.0.1:{port}"
        self.server = uvicorn.Server(
            uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
        )
        self.thread = threading.Thread(target=self.server.run, daemon=True)

    def start(self, timeout: float = 20.0) -> RunningServer:
        self.thread.start()
        deadline = time.time() + timeout
        while not self.server.started and time.time() < deadline:
            time.sleep(0.02)
        if not self.server.started:
            raise RuntimeError(f"server on port {self.port} never became ready")
        return self

    def stop(self) -> None:
        self.server.should_exit = True
        self.thread.join(timeout=20.0)


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


@pytest.fixture(scope="module")
def stack() -> Iterator[dict[str, Any]]:
    """Three servers, two credentials, one real request path."""
    stub = StubLiteLLM(LITELLM_CONFIG)
    stub_server = RunningServer(stub.app, free_port()).start()

    gateway_port = free_port()
    saved: dict[str, str | None] = {}
    gateway_values = {
        "FK_GATEWAY_MODELS_PATH": str(GATEWAY_CATALOG),
        "FK_GATEWAY_LITELLM_CONFIG": str(LITELLM_CONFIG),
        "FK_GATEWAY_LITELLM_BASE_URL": stub_server.base_url,
        "FK_GATEWAY_LITELLM_API_KEY": LITELLM_KEY,
        "FK_GATEWAY_API_KEYS": GATEWAY_KEY,
        "FK_GATEWAY_HOST": "127.0.0.1",
        "FK_GATEWAY_PORT": str(gateway_port),
        "FK_GATEWAY_REQUEST_TIMEOUT_SECONDS": "30",
        "FK_GATEWAY_JSON_LOGS": "false",
    }
    for key, value in gateway_values.items():
        saved[key] = os.environ.get(key)
        os.environ[key] = value

    copilot_server: RunningServer | None = None
    gateway_server: RunningServer | None = None
    try:
        gateway_server = RunningServer(build_production_app(), gateway_port).start()

        copilot_server = RunningServer(
            build_app(
                CopilotSettings(
                    gateway_base_url=gateway_server.base_url,
                    gateway_api_key=GATEWAY_KEY,
                    request_timeout_seconds=30.0,
                )
            ),
            free_port(),
        ).start()

        yield {
            "copilot": copilot_server,
            "gateway": gateway_server,
            "litellm": stub,
        }
    finally:
        if copilot_server is not None:
            copilot_server.stop()
        if gateway_server is not None:
            gateway_server.stop()
        stub_server.stop()
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def post(stack: dict[str, Any], path: str, payload: dict[str, Any]) -> httpx.Response:
    async def run() -> httpx.Response:
        async with httpx.AsyncClient(base_url=stack["copilot"].base_url, timeout=60.0) as client:
            return await client.post(path, json=payload)

    return asyncio.run(run())


def draft_payload(**changes: Any) -> dict[str, Any]:
    submission = {
        "clinical_indication": "62-year-old with sudden right hemiparesis, onset 3 hours",
        "modality": "CT",
        "study": "CT HEAD WITHOUT CONTRAST",
        "findings": (
            "No haemorrhage. Preserved grey-white differentiation. The ventricles and "
            "sulci are normal for age. No midline shift."
        ),
    }
    submission.update(changes)
    return {"submission": submission}


# -- the headline -------------------------------------------------------------------------------


def test_one_clinical_request_travels_the_whole_platform(stack: dict[str, Any]) -> None:
    response = post(stack, "/draft", draft_payload())

    assert response.status_code == 200, response.text
    report = response.json()
    assert tuple(report) == REQUIRED_OUTPUT

    # The two blocks Sprint 9 added travel the same two HTTP hops as the sections,
    # so a screen reading the wire sees the checks and the computed confidence
    # rather than having to ask for them separately.
    assert report["quality"]["status"] in ("clear", "advisory", "blocking")
    assert report["quality"]["checks_run"]
    assert report["confidence"]["level"] in (
        "supported",
        "review-carefully",
        "not-safe-to-sign",
    )

    assert report["skill"] == {"name": "radiology-report", "capability": "reasoning"}
    assert report["policy"] == {
        "clinical_risk": "high",
        "approval_required": False,
        "audit_required": True,
        "allow_downgrade": False,
    }

    provenance = report["model_provenance"]
    assert provenance["provider"] == "litellm"
    assert provenance["model"] == "ollama/qwen3:14b"
    assert provenance["selected_by"] == "skill"
    assert provenance["attempts"] == 1
    assert provenance["degraded"] is False
    assert provenance["request_id"]

    # The report content came from the deployment the alias named, through two
    # HTTP hops, and the sections survived both of them. The technique the
    # department did not supply stays declared as absent, and the indication is
    # the submitted sentence rather than a restatement of it.
    assert report["impression"].startswith("No acute intracranial haemorrhage")
    assert report["technique"] == "Technique not provided."
    assert report["clinical_indication"] == draft_payload()["submission"]["clinical_indication"]
    assert report["metadata"]["dictated_findings"] == draft_payload()["submission"]["findings"]


def test_the_skill_was_addressed_by_alias_and_by_nothing_else(stack: dict[str, Any]) -> None:
    """The alias contract, measured at the far end of a clinical request.

    The Gateway asked LiteLLM for ``fk-reasoning``. The skill name and the weights
    id both stopped at the boundary, which is the property ADR-0002 exists to hold.
    """
    before = len(stack["litellm"].addressed_as)

    post(stack, "/draft", draft_payload())

    assert stack["litellm"].addressed_as[before:] == ["fk-reasoning"]


def test_the_dictation_reached_the_model_that_answered(stack: dict[str, Any]) -> None:
    """The clinical content is the request. If it were dropped on the way, every
    other guarantee here would be about an empty document."""
    before = len(stack["litellm"].prompts)

    post(stack, "/draft", draft_payload(findings="A 6 mm hypodensity in the right caudate head."))

    prompt = stack["litellm"].prompts[before]
    assert "6 mm hypodensity" in prompt
    assert "radiology-report" not in prompt


def test_the_draft_is_not_exportable_until_a_clinician_signs_it(stack: dict[str, Any]) -> None:
    report = post(stack, "/draft", draft_payload()).json()

    refused = post(stack, "/export", {"report": report, "format": "text"})
    assert refused.status_code == 409
    assert refused.json()["error"]["code"] == "report_unsigned"

    signed = post(
        stack,
        "/review",
        {
            "report": report,
            "decision": "signed",
            "clinician": "Dr A. Nair",
            # Signing re-runs the checks, so the submission travels with the
            # signature over the wire exactly as the screen sends it.
            "submission": draft_payload()["submission"],
        },
    )
    assert signed.status_code == 200

    exported = post(stack, "/export", {"report": signed.json(), "format": "text"})
    assert exported.status_code == 200
    page = exported.json()["content"]
    assert page.startswith("RADIOLOGY REPORT\nSIGNED BY THE REPORTING RADIOLOGIST — Dr A. Nair")
    assert "IMPRESSION" in page
    assert "ollama/qwen3:14b" in page


def test_an_answer_in_prose_is_refused_across_the_wire(stack: dict[str, Any]) -> None:
    """The fail-closed parse is not an artefact of the stubbed client.

    The deployment answered with a paragraph of good medicine. It is still refused,
    because a section nobody can review separately is not a draft.
    """
    payload = draft_payload()
    payload["extra_instructions"] = {"probe": PROSE_MARKER}

    response = post(stack, "/draft", payload)

    assert response.status_code == 502, response.text
    error = response.json()["error"]
    assert error["code"] == "model_output_unusable"
    assert error["request_id"]
    # The refusal names the shape of the problem and quotes none of the answer.
    assert "middle cerebral artery" not in response.text
    assert "thrombolysis" not in response.text


def test_the_copilot_holds_the_gateway_key_and_the_upstream_holds_its_own(
    stack: dict[str, Any],
) -> None:
    """Two boundaries, two secrets.

    The copilot presents the application's credential to the Gateway; the Gateway
    presents the master key to LiteLLM; neither sees the other's, and the master
    key appears in no prompt this application built.
    """
    post(stack, "/draft", draft_payload())

    assert stack["litellm"].authorisation[-1] == f"Bearer {LITELLM_KEY}"
    assert LITELLM_KEY not in " ".join(stack["litellm"].prompts)
    assert GATEWAY_KEY not in " ".join(stack["litellm"].prompts)

    async def probe() -> httpx.Response:
        async with httpx.AsyncClient(base_url=stack["gateway"].base_url, timeout=30.0) as client:
            return await client.post(
                "/chat",
                json={
                    "skill": "radiology-report",
                    "messages": [{"role": "user", "content": PROSE_MARKER}],
                },
            )

    # Without the application's key the Gateway answers 401, so the copilot's
    # credential is the only one that ever opened a radiology request here.
    assert asyncio.run(probe()).status_code == 401
