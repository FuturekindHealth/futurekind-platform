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
from tests.conftest import (
    RADIOLOGY_POLICY,
    REQUIRED_OUTPUT,
    completion,
    fixture_text,
    make_copilot,
    submission,
    submission_for,
)

SETTINGS = CopilotSettings(
    gateway_base_url="http://127.0.0.1:8100", gateway_api_key="fk-app-level-key"
)

STUDY = submission()
DRAFT_BODY = {"submission": STUDY.model_dump()}


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
        # A signature re-runs the checks, and the checks need the study text back:
        # the document deliberately does not carry a copy of it.
        "submission": STUDY.model_dump(),
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


def test_draft_returns_the_twelve_part_document() -> None:
    app, stub = app_for(completion(fixture_text("normal_ct_head.json")))

    response = call(app, "POST", "/draft", DRAFT_BODY)

    assert response.status_code == 200
    assert tuple(response.json()) == REQUIRED_OUTPUT
    assert stub.last_request["skill"] == "radiology-report"


def test_draft_reports_the_quality_pass_and_a_computed_confidence() -> None:
    """The two new blocks arrive on the same call, because a draft without them is a
    draft nobody can decide whether to trust."""
    app, _ = app_for(completion(fixture_text("normal_ct_head.json")))

    body = call(app, "POST", "/draft", DRAFT_BODY).json()

    assert body["quality"]["status"] in ("clear", "advisory", "blocking")
    assert body["quality"]["checks_run"]
    assert body["quality"]["scope"]
    assert body["confidence"]["level"] in ("supported", "review-carefully", "not-safe-to-sign")
    assert "images" in body["confidence"]["basis"]


def test_check_re_ran_on_edited_text_moves_the_verdict_and_nothing_else() -> None:
    """The screen calls this after every keystroke. It must be able to clear a block
    and it must not be able to sign, invent provenance or reformat the medicine."""
    app, stub = app_for(completion(fixture_text("normal_ct_head.json")))
    draft = call(app, "POST", "/draft", DRAFT_BODY).json()
    draft["findings"] = "A 27 mm hypodense lesion nobody dictated."

    checked = call(app, "POST", "/check", {"report": draft, "submission": STUDY.model_dump()})

    assert checked.status_code == 200
    body = checked.json()
    assert body["quality"]["status"] == "blocking"
    assert body["confidence"]["level"] == "not-safe-to-sign"
    assert body["findings"] == draft["findings"]
    assert body["metadata"]["review"]["state"] == "pending_review"
    assert body["model_provenance"] == draft["model_provenance"]
    # Re-checking asks the Gateway for nothing.
    assert len(stub.requests) == 1


def test_the_reporting_screen_is_served_by_the_same_process() -> None:
    """"Open the copilot" has to mean a URL, or the product is an API and a
    radiologist has none."""
    app, _ = app_for(completion(fixture_text("normal_ct_head.json")))

    response = call(app, "GET", "/")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    page = response.text
    assert "Radiology Copilot" in page
    for endpoint in ("/draft", "/check", "/review", "/export"):
        assert f"'{endpoint}'" in page or f'"{endpoint}"' in page


def test_nothing_the_application_answers_can_be_cached_by_anything() -> None:
    """Two radiologists share a workstation, and a department that puts this behind its own
    proxy must not be able to leave one patient's draft in it. The rule covers the refusals
    too: a 422 that names which check blocked a signature is the artefact most likely to be
    screenshotted into a ticket, and it is also a response."""
    app, _ = app_for(completion(fixture_text("normal_ct_head.json")))

    draft = call(app, "POST", "/draft", DRAFT_BODY)
    assert draft.status_code == 200
    refused = call(app, "POST", "/draft", {"submission": {"clinical_indication": ""}})
    unsigned = call(app, "POST", "/export", {"report": draft.json(), "format": "text"})

    check_body = {"report": draft.json(), "submission": STUDY.model_dump()}
    responses = {
        "screen": call(app, "GET", "/"),
        "health": call(app, "GET", "/health"),
        "draft": draft,
        "check": call(app, "POST", "/check", check_body),
        "review_rejected_for_no_name": call(
            app, "POST", "/review", {**review_body(draft.json()), "clinician": "   "}
        ),
        "refused_422": refused,
        "export_before_signature": unsigned,
    }
    for name, response in responses.items():
        assert response.headers["cache-control"] == "no-store", (name, response.status_code)
        assert response.headers["x-content-type-options"] == "nosniff", name


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
    """Draft, review, export — the brief's workflow, in one test, through HTTP.

    The bleed case is used rather than the normal head because its answer carries
    measurements, and the numbers in a signed report are the thing the checks exist
    to trace back to the dictation.
    """
    app, _ = app_for(completion(fixture_text("hypertensive_bleed.json")))
    study = {"submission": submission_for("hypertensive_bleed.json").model_dump()}

    draft = call(app, "POST", "/draft", study)
    signed = call(
        app,
        "POST",
        "/review",
        review_body(draft.json(), submission=study["submission"]),
    )
    exported = call(app, "POST", "/export", {"report": signed.json(), "format": "text"})

    assert [draft.status_code, signed.status_code, exported.status_code] == [200, 200, 200]
    page = exported.json()["content"]
    assert page.startswith("RADIOLOGY REPORT\nSIGNED BY THE REPORTING RADIOLOGIST — Dr A. Nair")
    assert "IMPRESSION" in page
    assert "subfalcine herniation" in page


def test_a_draft_of_a_different_study_than_it_claims_is_not_signable_over_http() -> None:
    """The same workflow, with the pairing broken: the numbers in the answer belong to
    another patient's dictation, and the door refuses the signature rather than
    exporting a report whose measurements came from nowhere."""
    app, _ = app_for(completion(fixture_text("hypertensive_bleed.json")))

    draft = call(app, "POST", "/draft", DRAFT_BODY)
    signed = call(app, "POST", "/review", review_body(draft.json()))

    assert draft.status_code == 200
    assert draft.json()["quality"]["status"] == "blocking"
    assert signed.status_code == 422
    assert signed.json()["error"]["code"] == "review_invalid"
    assert "27 mm" not in signed.text and "4.5" not in signed.text


# -- the contract itself ---------------------------------------------------------------------------


def test_openapi_lists_the_four_workflow_operations() -> None:
    app, _ = app_for(completion(fixture_text("normal_ct_head.json")))

    document = call(app, "GET", "/openapi.json").json()

    assert {"/draft", "/check", "/review", "/export"} <= set(document["paths"])
    assert document["info"]["title"] == "FutureKind Radiology Copilot"


def test_the_contract_exposes_no_way_to_choose_infrastructure() -> None:
    app, _ = app_for(completion(fixture_text("normal_ct_head.json")))

    document = call(app, "GET", "/openapi.json").json()
    serialized = json.dumps(document["components"]["schemas"])

    for forbidden in ("fk-reasoning", "ollama", "api_base"):
        assert forbidden not in serialized
