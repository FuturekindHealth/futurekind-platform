"""HTTP tests for ``POST /chat``.

These exercise the assembled application, not a mock of it: authentication,
limit enforcement, routing, provider dispatch and the error envelope all run
for real through FastAPI's request pipeline.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from futurekind_gateway.app import create_app
from futurekind_gateway.catalog import ModelCatalog
from futurekind_gateway.config import GatewaySettings
from futurekind_gateway.providers import ProviderRegistry
from futurekind_gateway.providers.base import (
    ProviderRequestRejectedError,
    ProviderUnavailableError,
)
from tests.conftest import (
    GATEWAY_ROOT,
    REPO_CATALOG,
    TEST_API_KEY,
    FakeProvider,
    make_catalog,
    make_policy_catalog,
    make_settings,
)

BODY: dict[str, Any] = {
    "capability": "default",
    "messages": [{"role": "user", "content": "Summarise the impression."}],
}
AUTH = {"Authorization": f"Bearer {TEST_API_KEY}"}


def registry_with(provider: FakeProvider) -> ProviderRegistry:
    registry = ProviderRegistry()
    registry.register("fake", lambda: provider)
    return registry


def build_client(
    *,
    catalog: ModelCatalog | None = None,
    registry: ProviderRegistry | None = None,
    settings: GatewaySettings | None = None,
) -> TestClient:
    return TestClient(
        create_app(
            settings or make_settings(),
            catalog=catalog if catalog is not None else make_catalog(),
            provider_registry=registry if registry is not None else registry_with(FakeProvider()),
        )
    )


# -- authentication ---------------------------------------------------------------------------


def test_a_request_without_a_credential_is_rejected() -> None:
    client = build_client()

    response = client.post("/chat", json=BODY)

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthenticated"


def test_an_unknown_credential_is_rejected() -> None:
    client = build_client()

    response = client.post("/chat", json=BODY, headers={"Authorization": "Bearer wrong-key"})

    assert response.status_code == 401
    assert "not recognised" in response.json()["error"]["message"]


def test_the_bearer_scheme_is_matched_case_insensitively() -> None:
    client = build_client()

    response = client.post("/chat", json=BODY, headers={"authorization": "bearer " + TEST_API_KEY})

    assert response.status_code == 200


def test_an_api_key_header_is_accepted_as_well_as_a_bearer_token() -> None:
    client = build_client()

    response = client.post("/chat", json=BODY, headers={"X-FK-Api-Key": TEST_API_KEY})

    assert response.status_code == 200


def test_authentication_required_with_no_keys_configured_refuses_traffic() -> None:
    """Fail closed: an AI gateway must never fall open because a key was forgotten."""
    client = build_client(settings=make_settings(api_keys=()))

    response = client.post("/chat", json=BODY)

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "authentication_not_configured"


def test_authentication_can_be_switched_off_explicitly() -> None:
    client = build_client(settings=make_settings(require_auth=False))

    assert client.post("/chat", json=BODY).status_code == 200


# -- the successful request --------------------------------------------------------------------


def test_a_valid_request_returns_the_completion_and_the_routing_decision() -> None:
    client = build_client()

    response = client.post("/chat", json=BODY, headers=AUTH)

    assert response.status_code == 200
    payload = response.json()
    assert payload["content"] == "answer"
    assert payload["capability"] == "default"
    assert payload["model"] == "fake-large"
    assert payload["provider"] == "fake"
    assert payload["selected_by"] == "capability"
    assert payload["attempts"] == 1
    assert payload["degraded"] is False
    assert payload["usage"] == {"prompt_tokens": 3, "completion_tokens": 5, "total_tokens": 8}
    assert payload["latency_ms"] >= 0


def test_every_response_carries_a_request_id_and_the_body_repeats_it() -> None:
    client = build_client()

    response = client.post("/chat", json=BODY, headers=AUTH)

    assert response.headers["X-Request-Id"]
    assert response.json()["request_id"] == response.headers["X-Request-Id"]


def test_a_supplied_request_id_is_honoured_not_replaced() -> None:
    """Callers correlate their own traces with Gateway logs, so the id must survive."""
    client = build_client()

    response = client.post("/chat", json=BODY, headers={**AUTH, "X-Request-Id": "care-erp-4711"})

    assert response.headers["X-Request-Id"] == "care-erp-4711"
    assert response.json()["request_id"] == "care-erp-4711"


def test_a_capability_can_be_omitted_to_use_the_default_route() -> None:
    client = build_client()

    response = client.post(
        "/chat",
        json={"messages": [{"role": "user", "content": "hello"}]},
        headers=AUTH,
    )

    assert response.json()["selected_by"] == "default"
    assert response.json()["capability"] == "default"


def test_a_fallback_served_over_the_wire_is_reported_as_degraded() -> None:
    provider = FakeProvider(ProviderUnavailableError("first down", provider="fake"))
    client = build_client(registry=registry_with(provider))

    response = client.post(
        "/chat",
        json={"capability": "fast", "messages": [{"role": "user", "content": "x"}]},
        headers=AUTH,
    )

    assert response.status_code == 200
    assert response.json()["attempts"] == 2
    assert response.json()["degraded"] is True
    assert [request.model for request in provider.requests] == ["fk-fast", "fk-default"]


# -- an unwired transport ---------------------------------------------------------------------


def test_a_route_whose_transport_is_not_wired_reports_the_provider_name() -> None:
    """An empty registry is a deployment fact, and the answer must name it.

    ``create_app`` registers no provider — that is the test seam, and the process
    entrypoint is what wires LiteLLM. So the shipped catalogue, which routes every
    capability to ``litellm``, resolves cleanly and then says precisely which
    transport is missing rather than failing somewhere deep in a request.
    """
    client = build_client(
        catalog=ModelCatalog.load(REPO_CATALOG),
        registry=ProviderRegistry(),
    )

    response = client.post("/chat", json=BODY, headers=AUTH)

    assert response.status_code == 501
    error = response.json()["error"]
    assert error["code"] == "provider_not_implemented"
    assert error["details"]["provider"] == "litellm"
    assert error["details"]["registered_providers"] == []
    assert "hint" in error["details"]


def test_streaming_is_declared_but_refused_rather_than_ignored() -> None:
    client = build_client()

    response = client.post("/chat", json={**BODY, "stream": True}, headers=AUTH)

    assert response.status_code == 501
    assert response.json()["error"]["code"] == "feature_not_implemented"


# -- validation --------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "payload",
    [
        {"capability": "default"},
        {"capability": "default", "messages": []},
        {"messages": [{"role": "patient", "content": "x"}]},
        {"messages": [{"role": "user", "content": ""}]},
        {"messages": "not-a-list"},
        {"capability": "default", "messages": [{"role": "user", "content": "x"}], "surprise": 1},
        {"messages": [{"role": "user", "content": "x"}], "temperature": 5},
        {"messages": [{"role": "user", "content": "x"}], "max_tokens": 0},
        {"messages": [{"role": "user", "content": "x"}], "capability": "   "},
        {"messages": [{"role": "user", "content": "x"}], "skill": "   "},
    ],
    ids=[
        "no-messages",
        "empty-messages",
        "bad-role",
        "blank-content",
        "messages-not-list",
        "unknown-field",
        "temperature-too-high",
        "zero-max-tokens",
        "blank-capability",
        "blank-skill",
    ],
)
def test_malformed_requests_are_rejected_before_routing(payload: dict[str, Any]) -> None:
    client = build_client()

    response = client.post("/chat", json=payload, headers=AUTH)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_request"


def test_a_validation_failure_does_not_echo_the_submitted_text() -> None:
    """Pydantic reports the offending value by default. Here that value may be a
    patient narrative, so the envelope must carry the rule, not the text."""
    secret = "MRN 4471 — 62-year-old with right hemiparesis"
    client = build_client()

    response = client.post(
        "/chat",
        json={"messages": [{"role": "user", "content": secret}], "temperature": 9},
        headers=AUTH,
    )

    assert response.status_code == 422
    assert secret not in response.text


def test_an_unknown_capability_is_a_404_with_the_alternatives() -> None:
    client = build_client()

    response = client.post(
        "/chat",
        json={"capability": "vision", "messages": [{"role": "user", "content": "x"}]},
        headers=AUTH,
    )

    assert response.status_code == 404
    error = response.json()["error"]
    assert error["code"] == "unknown_capability"
    assert "default" in error["details"]["known_capabilities"]


def test_a_request_that_names_a_model_is_rejected() -> None:
    """ADR-0002: model selection belongs to LiteLLM, so the API must not accept it."""
    client = build_client()

    response = client.post(
        "/chat",
        json={"model": "qwen3:14b", "messages": [{"role": "user", "content": "x"}]},
        headers=AUTH,
    )

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "invalid_request"
    locations = [tuple(item["location"]) for item in error["details"]["errors"]]
    assert ("body", "model") in locations, "the model field should be rejected as unknown"


def test_a_skill_is_the_way_an_application_asks_for_work() -> None:
    client = build_client()

    response = client.post(
        "/chat",
        json={"skill": "clinical-chat", "messages": [{"role": "user", "content": "x"}]},
        headers=AUTH,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["skill"] == "clinical-chat"
    assert payload["capability"] == "default"
    assert payload["selected_by"] == "skill"
    assert payload["model"] == "fake-large"


def test_an_unknown_skill_is_a_404() -> None:
    client = build_client()

    response = client.post(
        "/chat",
        json={"skill": "MRI_READ", "messages": [{"role": "user", "content": "x"}]},
        headers=AUTH,
    )

    assert response.status_code == 404
    error = response.json()["error"]
    assert error["code"] == "unknown_skill"
    assert "clinical-chat" in error["details"]["known_skills"]


def test_a_disabled_capability_is_refused_rather_than_rerouted() -> None:
    client = build_client()

    response = client.post(
        "/chat",
        json={"capability": "retired", "messages": [{"role": "user", "content": "x"}]},
        headers=AUTH,
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "routing_failed"


# -- operator limits -----------------------------------------------------------------------------


def test_the_message_count_limit_is_enforced() -> None:
    client = build_client(settings=make_settings(max_messages=2))

    response = client.post(
        "/chat",
        json={"capability": "default", "messages": [{"role": "user", "content": "x"}] * 3},
        headers=AUTH,
    )

    assert response.status_code == 422
    assert response.json()["error"]["details"]["limit"] == "max_messages"


def test_the_message_size_limit_is_enforced() -> None:
    client = build_client(settings=make_settings(max_content_chars=20))

    response = client.post(
        "/chat",
        json={"capability": "default", "messages": [{"role": "user", "content": "y" * 21}]},
        headers=AUTH,
    )

    assert response.status_code == 422
    assert response.json()["error"]["details"]["limit"] == "max_content_chars"


def test_the_completion_length_ceiling_is_enforced() -> None:
    client = build_client(settings=make_settings(max_completion_tokens=64))

    response = client.post(
        "/chat",
        json={
            "capability": "default",
            "messages": [{"role": "user", "content": "x"}],
            "max_tokens": 4096,
        },
        headers=AUTH,
    )

    assert response.status_code == 422
    assert response.json()["error"]["details"]["allowed"] == 64


# -- policy -------------------------------------------------------------------------------------


def policy_client(**overrides: Any) -> TestClient:
    """A client wired to the catalogue whose skills carry real policy."""
    return build_client(catalog=make_policy_catalog(), **overrides)


def test_the_answer_reports_the_policy_it_ran_under() -> None:
    """An application has to be able to tell a clinician that this still needs signing."""
    response = policy_client().post(
        "/chat",
        json={"skill": "clinical-chat", "messages": [{"role": "user", "content": "x"}]},
        headers=AUTH,
    )

    assert response.status_code == 200
    assert response.json()["policy"] == {
        "clinical_risk": "moderate",
        "approval_required": False,
        "audit_required": True,
        "allow_downgrade": True,
    }


def test_a_request_that_names_no_skill_reports_itself_as_unassessed() -> None:
    """The default policy is inert, not optimistic: nobody rated this request, and the
    response says so rather than borrowing some skill's risk level."""
    response = policy_client().post(
        "/chat",
        json={"messages": [{"role": "user", "content": "x"}]},
        headers=AUTH,
    )

    assert response.json()["policy"]["clinical_risk"] == "unspecified"


def test_a_skill_that_requires_approval_refuses_before_anything_runs() -> None:
    client = policy_client()

    response = client.post(
        "/chat",
        json={
            "skill": "critical-care-summary",
            "messages": [{"role": "user", "content": "Summarise for the ward round."}],
        },
        headers=AUTH,
    )

    assert response.status_code == 403
    error = response.json()["error"]
    assert error["code"] == "approval_required"
    assert error["details"]["clinical_risk"] == "critical"
    assert error["retryable"] is False


def test_an_unapproved_high_risk_skill_still_runs() -> None:
    """Approval is a declared decision per skill, not a penalty for risk alone."""
    response = policy_client().post(
        "/chat",
        json={"skill": "radiology-report", "messages": [{"role": "user", "content": "x"}]},
        headers=AUTH,
    )

    assert response.status_code == 200
    assert response.json()["policy"]["allow_downgrade"] is False


def test_a_skill_can_narrow_the_message_ceiling() -> None:
    """`patient-leaflet` declares max_messages 2 against a platform default of 100."""
    response = policy_client().post(
        "/chat",
        json={"skill": "patient-leaflet", "messages": [{"role": "user", "content": "x"}] * 3},
        headers=AUTH,
    )

    assert response.status_code == 422
    details = response.json()["error"]["details"]
    assert details["limit"] == "max_messages"
    assert details["allowed"] == 2
    assert details["skill"] == "patient-leaflet"


def test_a_skill_ceiling_cannot_be_widened_by_the_skill_that_uses_it() -> None:
    """`patient-leaflet` would allow 32000 characters; the platform's own limit still binds."""
    client = build_client(
        catalog=make_policy_catalog(),
        settings=make_settings(max_content_chars=20),
    )

    response = client.post(
        "/chat",
        json={"skill": "clinical-chat", "messages": [{"role": "user", "content": "y" * 21}]},
        headers=AUTH,
    )

    assert response.status_code == 422
    assert response.json()["error"]["details"]["allowed"] == 20


def test_an_unroutable_request_is_reported_before_its_policy_limits_are() -> None:
    """Routing has to come first, because the limits live on the skill being routed to."""
    response = policy_client().post(
        "/chat",
        json={"skill": "no-such-skill", "messages": [{"role": "user", "content": "x"}] * 400},
        headers=AUTH,
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "unknown_skill"


def test_a_request_cannot_relax_the_policy_being_applied_to_it() -> None:
    """Rule 7 of gateway-routing.md: policy is the operator's, never the caller's."""
    client = policy_client()

    for field in ("allow_downgrade", "audit_required", "clinical_risk", "approval_required"):
        response = client.post(
            "/chat",
            json={
                "skill": "radiology-report",
                "messages": [{"role": "user", "content": "x"}],
                field: False if field != "clinical_risk" else "low",
            },
            headers=AUTH,
        )

        assert response.status_code == 422, f"{field} must not be accepted from a caller"
        locations = [
            tuple(item["location"]) for item in response.json()["error"]["details"]["errors"]
        ]
        assert ("body", field) in locations


def test_the_shipped_catalogue_governs_its_own_shipped_skills() -> None:
    """models.yaml is the clinical configuration; assert what it actually decides."""
    client = build_client(catalog=ModelCatalog.load(REPO_CATALOG))

    skills = {item["name"]: item for item in client.get("/models", headers=AUTH).json()["skills"]}

    assert skills["radiology-report"]["clinical_risk"] == "high"
    assert skills["radiology-report"]["allow_downgrade"] is False
    assert skills["radiology-report"]["approval_required"] is False
    assert skills["summarize-document"]["audit_required"] is False
    assert skills["clinical-chat"]["clinical_risk"] == "moderate"


# -- provider and catalogue failures --------------------------------------------------------------


def test_a_provider_failure_becomes_a_502_with_its_code() -> None:
    provider = FakeProvider(ProviderRequestRejectedError("blocked", provider="fake"))
    client = build_client(registry=registry_with(provider))

    response = client.post("/chat", json=BODY, headers=AUTH)

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "provider_request_rejected"


def test_an_exhausted_chain_is_a_retryable_502() -> None:
    provider = FakeProvider(
        ProviderUnavailableError("a", provider="fake"),
        ProviderUnavailableError("b", provider="fake"),
    )
    client = build_client(registry=registry_with(provider))

    response = client.post(
        "/chat",
        json={"capability": "fast", "messages": [{"role": "user", "content": "x"}]},
        headers=AUTH,
    )

    body = response.json()["error"]
    assert response.status_code == 502
    assert body["retryable"] is True
    assert body["details"]["attempted"] == ["fast", "default"]


def test_a_missing_catalogue_is_a_503_that_names_the_path() -> None:
    missing = GATEWAY_ROOT / "definitely-not-here.yaml"
    client = TestClient(
        create_app(
            make_settings().with_overrides(catalog_path=missing),
            provider_registry=ProviderRegistry(),
        )
    )

    response = client.post("/chat", json=BODY, headers=AUTH)

    assert response.status_code == 503
    error = response.json()["error"]
    assert error["code"] == "catalog_error"
    assert missing.name in error["details"]["reason"]


def test_no_catalogue_path_at_all_is_reported_rather_than_served_empty() -> None:
    client = TestClient(
        create_app(
            make_settings().with_overrides(catalog_path=None),
            provider_registry=ProviderRegistry(),
        )
    )

    response = client.post("/chat", json=BODY, headers=AUTH)

    assert response.status_code == 503
    assert "FK_GATEWAY_MODELS_PATH" in response.json()["error"]["details"]["reason"]


# -- misc ---------------------------------------------------------------------------------------


def test_an_unknown_path_uses_the_same_error_envelope() -> None:
    client = build_client()

    response = client.get("/not-a-real-endpoint")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "http_error"
