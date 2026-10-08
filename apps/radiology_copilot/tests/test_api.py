"""The application's HTTP surface, driven through ASGI.

No port is opened here; the transport is in-process. What is being proved is the
contract a screen would depend on: the status codes, the one error envelope on
every failure, and the fact that a request body has no way to ask for a model.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx
import pytest

from futurekind_radiology.api import build_app, create_app
from futurekind_radiology.settings import CopilotSettings
from tests.conftest import RADIOLOGY_POLICY, completion, fixture_text, make_copilot, submission

SETTINGS = CopilotSettings(
    gateway_base_url="http://127.0.0.1:8100", gateway_api_key="fk-app-level-key"
)

DRAFT_BODY = {"submission": submission().model_dump()}


def app_for(*responses: Any):
    copilot, stub = make_copilot(*responses)
    return create_app(copilot, settings=SETTINGS), stub


def call(app, method: str, path: str, payload: Any = None) -> httpx.Response:
    async def run() -> httpx.Response:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://copilot", timeout=10.0
        ) as client:
            return await client.request(method, path, json=payload)

    return asyncio.run(run())


def review_body(report: dict[str, Any], **changes: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "report": report,
        "decision": "signed",
        "clinician": "Dr A. Nair",
    }
    payload.update(changes)
    return payload


# -- health --------------------------------------------------------------------------------------


def test_health_describes_the_service_and_never_the_credential() -> None:
    app, _ = app_for(completion(fixture_text("normal_ct_head.json")))

    response = call(app, "GET", "/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["skill"] == "radiology-report"
    assert body["gateway"]["gateway_base_url"] == "http://127.0.0.1:8100"
    assert body["gateway"]["gateway_api_key_configured"] is True
    assert "fk-app-level-key" not in response.text


def test_the_production_factory_builds_from_the_environment() -> None:
    app = build_app(CopilotSettings(gateway_base_url="http://gateway.internal:8100"))

    assert call(app, "GET", "/health").json()["gateway"]["gateway_base_url"] == (
        "http://gateway.internal:8100"
    )


# -- draft ---------------------------------------------------------------------------------------


def test_draft_returns_the_nine_part_document() -> None:
    app, stub = app_for(completion(fixture_text("normal_ct_head.json")))

    response = call(app, "POST", "/draft", DRAFT_BODY)

    assert response.status_code == 200
    assert tuple(response.json()) == (
        "clinical_indication",
        "technique",
        "findings",
        "impression",
        "recommendations",
        "metadata",
        "model_provenance",
        "skill",
        "policy",
    )
    assert stub.last_request["skill"] == "radiology-report"


def test_draft_reports_the_policy_it_ran_under_to_the_caller() -> None:
    app, _ = app_for(completion(fixture_text("normal_ct_head.json")))

    body = call(app, "POST", "/draft", DRAFT_BODY).json()

    assert body["policy"] == RADIOLOGY_POLICY
    assert body["skill"] == {"name": "radiology-report", "capability": "reasoning"}


def test_a_prose_answer_becomes_a_502_in_the_platform_envelope() -> None:
    app, _ = app_for(completion(fixture_text("prose_answer.txt")))

    response = call(app, "POST", "/draft", DRAFT_BODY)

    assert response.status_code == 502
    error = response.json()["error"]
    assert error["code"] == "model_output_unusable"
    assert error["retryable"] is True
    assert error["request_id"] == "fk-test-request-1"
    assert set(error) == {"code", "message", "retryable", "request_id", "details"}


def test_a_policy_the_gateway_did_not_uphold_is_a_503() -> None:
    app, _ = app_for(
        completion(
            fixture_text("normal_ct_head.json"),
            policy={**RADIOLOGY_POLICY, "allow_downgrade": True},
        )
    )

    response = call(app, "POST", "/draft", DRAFT_BODY)

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "policy_not_enforced"


def test_an_unreachable_gateway_is_a_503_the_screen_can_act_on() -> None:
    from futurekind_radiology.errors import GatewayRequestError

    app, _ = app_for(
        GatewayRequestError(
            "The Gateway could not be reached.",
            status_code=503,
            retryable=True,
        )
    )

    response = call(app, "POST", "/draft", DRAFT_BODY)

    assert response.status_code == 503
    assert response.json()["error"]["retryable"] is True


def test_a_request_that_sends_nothing_clinical_is_rejected() -> None:
    app, _ = app_for(completion(fixture_text("normal_ct_head.json")))

    response = call(app, "POST", "/draft", {"submission": {"modality": "CT"}})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_request"


def test_a_rejected_body_does_not_echo_the_clinical_text_back() -> None:
    """FastAPI's validation errors include the submitted value. A 422 screen is
    copied into tickets and screenshots, so a rejected dictation must not come
    back with it."""
    app, _ = app_for(completion(fixture_text("normal_ct_head.json")))

    response = call(
        app,
        "POST",
        "/draft",
        {"submission": {**submission().model_dump(), "findings": "x" * 20_000}},
    )

    assert response.status_code == 422
    payload = response.json()
    assert payload["error"]["code"] == "invalid_request"
    assert ("x" * 200) not in response.text
    assert "hemiparesis" not in response.text
    assert all("input" not in problem for problem in payload["error"]["details"]["problems"])


@pytest.mark.parametrize(
    "extra",
    [{"model": "qwen3:14b"}, {"provider": "litellm"}, {"allow_downgrade": True}],
)
def test_a_body_that_names_infrastructure_is_refused(extra: dict[str, Any]) -> None:
    """The Gateway refuses such a request too. Refusing it here as well means an
    application cannot be talked into building the dependency the platform forbids."""
    app, _ = app_for(completion(fixture_text("normal_ct_head.json")))

    response = call(app, "POST", "/draft", {**DRAFT_BODY, **extra})

    assert response.status_code == 422


# -- review --------------------------------------------------------------------------------------


def test_review_returns_the_document_with_the_signoff_inside_it() -> None:
    app, _ = app_for(completion(fixture_text("normal_ct_head.json")))
    draft = call(app, "POST", "/draft", DRAFT_BODY).json()

    response = call(app, "POST", "/review", review_body(draft))

    assert response.status_code == 200
    record = response.json()["metadata"]["review"]
    assert record["state"] == "signed"
    assert record["clinician"] == "Dr A. Nair"


def test_review_records_an_amendment_without_hiding_the_provenance() -> None:
    app, _ = app_for(completion(fixture_text("normal_ct_head.json")))
    draft = call(app, "POST", "/draft", DRAFT_BODY).json()

    revised = call(
        app,
        "POST",
        "/review",
        review_body(draft, amendments={"impression": "No acute intracranial haemorrhage."}),
    ).json()

    assert revised["impression"] == "No acute intracranial haemorrhage."
    assert revised["metadata"]["review"]["amendments"] == ["impression"]
    assert revised["model_provenance"]["model"] == "ollama/qwen3:14b"


def test_an_unnamed_review_is_refused_with_an_explanation() -> None:
    app, _ = app_for(completion(fixture_text("normal_ct_head.json")))
    draft = call(app, "POST", "/draft", DRAFT_BODY).json()

    response = call(app, "POST", "/review", review_body(draft, clinician="  "))

    assert response.status_code == 422
    assert "P3" in response.json()["error"]["message"]


# -- export --------------------------------------------------------------------------------------


def test_export_refuses_a_draft_no_one_has_signed() -> None:
    app, _ = app_for(completion(fixture_text("normal_ct_head.json")))
    draft = call(app, "POST", "/draft", DRAFT_BODY).json()

    response = call(app, "POST", "/export", {"report": draft, "format": "text"})

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "report_unsigned"


def test_the_whole_workflow_runs_over_the_door_a_screen_would_use() -> None:
    """Draft, review, export — the brief's workflow, in one test, through HTTP."""
    app, _ = app_for(completion(fixture_text("hypertensive_bleed.json")))

    draft = call(app, "POST", "/draft", DRAFT_BODY)
    signed = call(app, "POST", "/review", review_body(draft.json()))
    exported = call(app, "POST", "/export", {"report": signed.json(), "format": "text"})

    assert [draft.status_code, signed.status_code, exported.status_code] == [200, 200, 200]
    page = exported.json()["content"]
    assert page.startswith("RADIOLOGY REPORT\nSIGNED BY THE REPORTING RADIOLOGIST — Dr A. Nair")
    assert "IMPRESSION" in page
    assert "subfalcine herniation" in page


# -- the contract itself ---------------------------------------------------------------------------


def test_openapi_lists_the_three_workflow_operations() -> None:
    app, _ = app_for(completion(fixture_text("normal_ct_head.json")))

    document = call(app, "GET", "/openapi.json").json()

    assert {"/draft", "/review", "/export"} <= set(document["paths"])
    assert document["info"]["title"] == "FutureKind Radiology Copilot"


def test_the_contract_exposes_no_way_to_choose_infrastructure() -> None:
    app, _ = app_for(completion(fixture_text("normal_ct_head.json")))

    document = call(app, "GET", "/openapi.json").json()
    serialized = json.dumps(document["components"]["schemas"])

    for forbidden in ("fk-reasoning", "ollama", "api_base"):
        assert forbidden not in serialized
