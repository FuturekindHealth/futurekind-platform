"""Shared test furniture: a deterministic clock, a stub Gateway, golden fixtures.

Nothing in ``tests/`` except ``test_end_to_end.py`` starts a process, opens a port
or asks a model anything. The clinical behaviour under test is this application's
own — parsing, refusing, reviewing, rendering — and it has to be provable from a
fixture rather than from whatever a deployment happens to say today.
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from futurekind_radiology.copilot import RadiologyCopilot
from futurekind_radiology.gateway import GatewayCompletion
from futurekind_radiology.report import RadiologyReport
from futurekind_radiology.submission import StudySubmission

FIXTURE_DIR = Path(__file__).parent / "fixtures"

#: One frozen instant, so every timestamp in every golden output is comparable.
FROZEN_MOMENT = datetime(2026, 10, 8, 9, 30, tzinfo=UTC)
FROZEN_STAMP = "2026-10-08T09:30:00Z"

#: The policy the shipped catalogue declares for this skill (``models.yaml:54-66``).
#: Tests mutate one key at a time out of this, so a policy change is always explicit.
RADIOLOGY_POLICY = {
    "clinical_risk": "high",
    "approval_required": False,
    "audit_required": True,
    "allow_downgrade": False,
}


def fixture_text(name: str) -> str:
    return (FIXTURE_DIR / name).read_text(encoding="utf-8")


def golden(name: str) -> dict[str, str]:
    """A golden answer, as the five-section dict the model wrote."""
    return json.loads(fixture_text(name))


def completion(content: str, **overrides: Any) -> GatewayCompletion:
    """A completion shaped exactly like ``POST /chat`` answers for this skill."""
    payload: dict[str, Any] = {
        "request_id": "fk-test-request-1",
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
        "usage": {"prompt_tokens": 640, "completion_tokens": 210, "total_tokens": 850},
        "latency_ms": 4200,
    }
    payload.update(overrides)
    return GatewayCompletion(**payload)


class StubGateway:
    """Answers as the Gateway would, and records what was asked of it.

    Deliberately not a subclass of ``GatewayClient``: the copilot's dependency is
    a method signature, and keeping the stub independent means a test cannot pass
    by accident when that signature changes in a way the copilot never notices.
    """

    def __init__(self, *responses: GatewayCompletion | Exception) -> None:
        self.responses = list(responses)
        self.requests: list[dict[str, Any]] = []

    async def complete(self, *, skill: str, messages: Any, temperature: Any = None) -> Any:
        self.requests.append({"skill": skill, "messages": messages, "temperature": temperature})
        if not self.responses:
            raise AssertionError("StubGateway ran out of scripted answers")
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    @property
    def last_request(self) -> dict[str, Any]:
        assert self.requests, "nothing was asked of the Gateway"
        return self.requests[-1]


def make_copilot(*responses: GatewayCompletion | Exception) -> tuple[RadiologyCopilot, StubGateway]:
    stub = StubGateway(*responses)
    return RadiologyCopilot(stub, now=lambda: FROZEN_MOMENT), stub


def submission(**overrides: Any) -> StudySubmission:
    payload: dict[str, Any] = {
        "clinical_indication": "62-year-old with sudden right hemiparesis, onset 3 hours",
        "modality": "CT",
        "study": "CT HEAD WITHOUT CONTRAST",
        "findings": (
            "No haemorrhage. Preserved grey-white differentiation. Ventricles and sulci "
            "normal for age. No midline shift."
        ),
    }
    payload.update(overrides)
    return StudySubmission(**payload)


def drafted_report(
    *, content: str | None = None, **overrides: Any
) -> tuple[RadiologyReport, StubGateway]:
    """A report that has been drafted through the copilot, but not reviewed.

    Sync on purpose: the suite drives the coroutine with ``asyncio.run`` rather
    than depending on an asyncio plugin, which is how the Gateway's own tests do it.
    """
    text = fixture_text("normal_ct_head.json") if content is None else content
    copilot, stub = make_copilot(completion(text, **overrides))
    return asyncio.run(copilot.draft(submission())), stub


@pytest.fixture
def draft_report() -> RadiologyReport:
    """The golden draft, assembled for the review and rendering tests."""
    report, _ = drafted_report()
    return report


@pytest.fixture
def signed_report(draft_report: RadiologyReport) -> RadiologyReport:
    copilot, _ = make_copilot(completion(fixture_text("normal_ct_head.json")))
    return copilot.review(draft_report, decision="signed", clinician="Dr A. Nair")
