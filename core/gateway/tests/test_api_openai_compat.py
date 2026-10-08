"""The OpenAI-compatible door: same rules, different vocabulary.

These tests exist to prove one sentence: an interface that can only speak OpenAI
gets the platform's full enforcement, not a cheaper path around it. Every case
here has a ``POST /chat`` twin in ``test_api_chat.py``, and the point of writing
them twice is that they cannot drift — if the doors ever disagree about who may
ask, what a policy costs, or what leaves the process, a test fails here.
"""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from futurekind_gateway.app import create_app
from futurekind_gateway.catalog import ModelCatalog
from futurekind_gateway.config import GatewaySettings
from futurekind_gateway.providers import ProviderRegistry
from tests.conftest import (
    TEST_API_KEY,
    FakeProvider,
    make_catalog,
    make_policy_catalog,
    make_settings,
)

AUTH = {"Authorization": f"Bearer {TEST_API_KEY}"}


def body(**overrides: Any) -> dict[str, Any]:
    request: dict[str, Any] = {
        "model": "clinical-chat",
        "messages": [{"role": "user", "content": "Summarise the impression."}],
    }
    request.update(overrides)
    return request


def build_client(
    *,
    catalog: ModelCatalog | None = None,
    provider: FakeProvider | None = None,
    settings: GatewaySettings | None = None,
) -> TestClient:
    chosen = provider or FakeProvider()
    registry = ProviderRegistry()
    registry.register("fake", lambda: chosen)
    return TestClient(
        create_app(
            settings or make_settings(),
            catalog=catalog if catalog is not None else make_catalog(),
            provider_registry=registry,
        )
    )


def policy_client(provider: FakeProvider | None = None) -> TestClient:
    return build_client(catalog=make_policy_catalog(), provider=provider)


# -- the door itself -------------------------------------------------------------------------


def test_the_compat_door_requires_a_credential() -> None:
    """No key, no AI — the same rule as ``POST /chat``, on a door built for hire.

    ``GET /models`` used to be readable without one; SPEC-06-01 is now enforced on
    that door too. This surface was built authenticated from its first commit: it is
    the address an interface is given, so it never inherited the older door's defect.
    """
    client = build_client()

    assert client.get("/v1/models").status_code == 401
    assert client.post("/v1/chat/completions", json=body()).status_code == 401


def test_a_broken_catalogue_never_answers_an_anonymous_caller_with_a_path(
    tmp_path: Any,
) -> None:
    """Dependency order is a security property, not a detail.

    FastAPI resolves a route's dependencies in the order they are declared. When the
    catalogue could not load, ``get_router`` raises a ``CatalogError`` naming the file
    it failed to read — so a route that declares the catalogue before the credential
    answers an **unauthenticated** request with an absolute server path, and the
    inventory rule is bypassed by the one deployment state that guarantees the error.
    Every door declares ``AuthenticatedCaller`` ahead of any state that can quote a
    path, and this test is what keeps the four doors in that order.
    """
    missing = tmp_path / "absent-models.yaml"
    client = TestClient(
        create_app(
            make_settings().with_overrides(catalog_path=missing),
            provider_registry=ProviderRegistry(),
        )
    )

    for path in ("/v1/models", "/models", "/metrics"):
        response = client.get(path)

        assert response.status_code == 401, f"{path} answered {response.status_code}, not 401"
        assert "absent-models.yaml" not in response.text
        assert str(tmp_path) not in response.text

    completion = client.post("/v1/chat/completions", json=body())

    assert completion.status_code == 401
    assert "absent-models.yaml" not in completion.text


def test_an_authorized_caller_still_gets_the_path_when_the_catalogue_is_broken(
    tmp_path: Any,
) -> None:
    """The refusal is about the caller, not about hiding the fault from operators.

    With a credential the same request answers 503 and names the file, because a path
    in an operator's own authenticated response is how a mis-deployment gets fixed.
    """
    missing = tmp_path / "absent-models.yaml"
    client = TestClient(
        create_app(
            make_settings().with_overrides(catalog_path=missing),
            provider_registry=ProviderRegistry(),
        )
    )

    response = client.get("/models", headers=AUTH)

    assert response.status_code == 503
    assert "absent-models.yaml" in response.text


def test_the_model_list_is_skills_and_nothing_else() -> None:
    payload = build_client().get("/v1/models", headers=AUTH).json()

    assert payload["object"] == "list"
    assert [item["id"] for item in payload["data"]] == [
        "clinical-chat",
        "summarize-document",
    ]
    assert payload["data"][0]["object"] == "model"
    assert payload["data"][0]["owned_by"] == "futurekind-gateway"


def test_a_disabled_skill_is_not_offered_to_an_interface() -> None:
    ids = [item["id"] for item in build_client().get("/v1/models", headers=AUTH).json()["data"]]

    assert "retired-skill" not in ids


def test_the_offering_exposes_no_infrastructure() -> None:
    """The reason this endpoint exists rather than LiteLLM's own /v1/models.

    An interface's model picker is where a clinician chooses. If a deployment id,
    a provider or an alias appeared here, the picker would become the model selector
    ``ADR-0002`` removed — and ``GET /models``'s internals would leak into a browser.
    """
    serialized = str(build_client().get("/v1/models", headers=AUTH).json())

    for forbidden in ("fake-large", "fake-small", "fk-default", "ollama", "provider"):
        assert forbidden not in serialized


# -- a completion through the compat door ----------------------------------------------------


def test_a_completion_comes_back_in_openais_shape() -> None:
    client = build_client()

    response = client.post("/v1/chat/completions", json=body(), headers=AUTH)

    assert response.status_code == 200
    payload = response.json()
    assert payload["object"] == "chat.completion"
    assert payload["model"] == "clinical-chat"
    assert len(payload["choices"]) == 1
    assert payload["choices"][0]["message"]["role"] == "assistant"
    assert payload["choices"][0]["message"]["content"] == "answer"
    assert payload["choices"][0]["finish_reason"] == "stop"
    assert payload["usage"] == {
        "prompt_tokens": 3,
        "completion_tokens": 5,
        "total_tokens": 8,
    }


def test_the_response_id_is_the_request_id_an_audit_line_is_found_with() -> None:
    """A screenshot from an interface has to be enough to find the record (P8)."""
    response = build_client().post("/v1/chat/completions", json=body(), headers=AUTH)

    assert response.json()["id"] == response.headers["X-Request-Id"]


def test_the_skill_never_reaches_the_backend_but_the_alias_does() -> None:
    """Both halves of the boundary in one assertion pair.

    The application's word for its intent stops at the Gateway; what continues is
    the alias LiteLLM agreed to. A backend that could see "clinical-chat" would
    know what a clinician was doing, which is not its business.
    """
    provider = FakeProvider()

    build_client(provider=provider).post("/v1/chat/completions", json=body(), headers=AUTH)

    assert provider.requests[0].model == "fk-default"
    assert "clinical-chat" not in str(provider.requests[0].to_dict())


def test_sampling_knobs_travel_and_unknown_ones_are_dropped() -> None:
    """Open WebUI sends a long tail of fields; none of them reach a model unfed.

    Ignored means not forwarded. A parameter this platform has not reviewed must
    not be able to ride through on a client's goodwill.
    """
    provider = FakeProvider()

    response = build_client(provider=provider).post(
        "/v1/chat/completions",
        json=body(
            temperature=0.1,
            max_tokens=32,
            stop="END",
            n=1,
            user="clinician-7",
            seed=13,
            presence_penalty=0.5,
        ),
        headers=AUTH,
    )

    assert response.status_code == 200
    sent = provider.requests[0]
    assert sent.temperature == 0.1
    assert sent.max_tokens == 32
    assert sent.stop == ("END",)
    assert sent.extra == {}


# -- the rules are the same rules -------------------------------------------------------------


def test_an_unknown_skill_is_a_404_that_lists_the_real_names() -> None:
    response = build_client().post(
        "/v1/chat/completions", json=body(model="gpt-oss:20b"), headers=AUTH
    )

    assert response.status_code == 404
    error = response.json()["error"]
    assert error["code"] == "unknown_skill"
    assert "clinical-chat" in error["details"]["known_skills"]


def test_streaming_is_refused_at_the_door_rather_than_misanswered() -> None:
    """SPEC-15-03 keeps streaming unspecified; so this door says no in one voice."""
    response = build_client().post(
        "/v1/chat/completions", json=body(stream=True), headers=AUTH
    )

    assert response.status_code == 501
    assert response.json()["error"]["code"] == "feature_not_implemented"


def test_a_skill_that_requires_an_approval_refuses_through_this_door_too() -> None:
    response = policy_client().post(
        "/v1/chat/completions",
        json=body(model="critical-care-summary"),
        headers=AUTH,
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "approval_required"


def test_the_skills_own_limits_apply_to_an_openai_formatted_request() -> None:
    """`patient-leaflet` allows two messages; OpenAI's format does not buy a third."""
    response = policy_client().post(
        "/v1/chat/completions",
        json=body(
            model="patient-leaflet",
            messages=[
                {"role": "user", "content": "one"},
                {"role": "user", "content": "two"},
                {"role": "user", "content": "three"},
            ],
        ),
        headers=AUTH,
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_request"


def test_a_request_over_the_skills_token_ceiling_is_refused() -> None:
    response = policy_client().post(
        "/v1/chat/completions",
        json=body(model="patient-leaflet", max_tokens=9_000),
        headers=AUTH,
    )

    assert response.status_code == 422
    assert "max_completion_tokens" in str(response.json()["error"]["details"])


def test_the_compat_door_writes_the_same_audit_line() -> None:
    """One record per audited request, whichever door it used (P9).

    The alias and the model that answered are both in it: the pairing an audit of
    a clinical answer needs, and the one an application cannot forge because it is
    never told either name.
    """
    from tests.test_service import audited_events, capture_service_logs

    with capture_service_logs() as collected:
        build_client().post("/v1/chat/completions", json=body(), headers=AUTH)

    line = audited_events(collected).pop()
    assert line.skill == "clinical-chat"
    assert line.alias == "fk-default"
    assert line.model == "fake-large"
    assert line.answered is True
    assert line.clinical_risk == "moderate"


def test_an_array_content_part_is_refused_not_silently_dropped() -> None:
    """OpenAI permits multimodal content parts. Accepting one and losing the image
    would be a silent clinical data loss, so the request is refused instead."""
    response = build_client().post(
        "/v1/chat/completions",
        json=body(
            messages=[
                {
                    "role": "user",
                    "content": [{"type": "text", "text": "look at this scan"}],
                }
            ]
        ),
        headers=AUTH,
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_request"


def test_an_empty_message_is_refused_the_same_way_as_on_chat() -> None:
    response = build_client().post(
        "/v1/chat/completions",
        json=body(messages=[{"role": "user", "content": ""}]),
        headers=AUTH,
    )

    assert response.status_code == 422
