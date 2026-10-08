"""HTTP tests for ``GET /models`` and ``GET /models/{capability}``.

Both are operator doors now: the routing table names providers and model ids, so
it is authenticated like ``POST /chat`` is. These tests carry a credential
everywhere and check, once each, that its absence is a 401.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from futurekind_gateway.app import create_app
from futurekind_gateway.catalog import ModelCatalog
from futurekind_gateway.providers import ProviderRegistry
from tests.conftest import REPO_CATALOG, TEST_API_KEY, FakeProvider, make_catalog, make_settings

AUTH = {"Authorization": f"Bearer {TEST_API_KEY}"}


def client_for(
    *,
    catalog: ModelCatalog | None = None,
    registry: ProviderRegistry | None = None,
) -> TestClient:
    if registry is None:
        registry = ProviderRegistry()
        registry.register("fake", lambda: FakeProvider())
    return TestClient(
        create_app(
            make_settings(),
            catalog=catalog if catalog is not None else make_catalog(),
            provider_registry=registry,
        )
    )


def payload(client: TestClient, path: str = "/models") -> dict:
    """Read one operator endpoint with the credential it now requires."""
    response = client.get(path, headers=AUTH)
    assert response.status_code == 200, response.text
    return response.json()


def test_models_lists_every_capability_with_its_chain() -> None:
    body = payload(client_for())

    assert body["default_capability"] == "default"
    assert body["count"] == 4
    capabilities = [item["capability"] for item in body["models"]]
    assert capabilities == ["default", "fast", "reasoning", "retired"]
    reasoning = next(item for item in body["routes"] if item["capability"] == "reasoning")
    assert reasoning["chain"] == ["reasoning", "fast", "default"]


def test_models_reports_no_filesystem_location() -> None:
    """Where the catalogue file sits is a deployment detail, not a fact about a request."""
    assert "catalog_source" not in payload(client_for())


def test_models_lists_application_intents_separately_from_the_routing_table() -> None:
    skills = payload(client_for())["skills"]

    assert [item["name"] for item in skills] == [
        "clinical-chat",
        "summarize-document",
        "retired-skill",
    ]
    assert set(skills[0]) == {
        "name",
        "capability",
        "description",
        "enabled",
        "clinical_risk",
        "approval_required",
        "audit_required",
        "allow_downgrade",
    }


def test_a_skill_card_carries_no_infrastructure_anywhere() -> None:
    """If a model, alias or provider ever appears here, the ADR-0002 boundary has leaked."""
    skills = payload(client_for())["skills"]

    for card in skills:
        assert not {"model", "provider", "fallbacks", "api_base", "alias"} & set(card)


def test_a_skill_card_reports_governance_but_not_tuning() -> None:
    """A caller must be able to see that an answer needs sign-off, and must not be
    taught where the request limits sit."""
    card = payload(client_for())["skills"][0]

    assert card["clinical_risk"] == "moderate"
    assert set(card) >= {"approval_required", "audit_required", "allow_downgrade"}
    assert not {
        "max_messages",
        "max_content_chars",
        "max_completion_tokens",
        "request_timeout_seconds",
    } & set(card)


def test_disabled_capabilities_are_listed_but_never_routed() -> None:
    body = payload(client_for())

    retired = next(item for item in body["models"] if item["capability"] == "retired")
    assert retired["enabled"] is False
    assert "retired" not in [item["capability"] for item in body["routes"]]


def test_models_reports_which_providers_this_build_can_actually_invoke() -> None:
    wired = payload(client_for())
    bare = payload(client_for(registry=ProviderRegistry()))

    assert wired["providers_registered"] == ["fake"]
    assert wired["providers_missing"] == []
    assert bare["providers_registered"] == []
    assert bare["providers_missing"] == ["fake"]


def test_one_capability_can_be_resolved_directly() -> None:
    body = payload(client_for(), "/models/reasoning")

    assert body["model"]["model"] == "fake-thinker"
    assert body["route"]["chain"] == ["reasoning", "fast", "default"]
    assert body["provider_implemented"] is True
    assert body["default_capability"] == "default"


def test_a_capability_no_provider_is_registered_for_is_reported_honestly() -> None:
    body = payload(client_for(registry=ProviderRegistry()), "/models/fast")

    assert body["provider_implemented"] is False


def test_an_unknown_capability_is_a_404() -> None:
    response = client_for().get("/models/vision", headers=AUTH)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "unknown_capability"


def test_a_disabled_capability_is_a_400_not_a_silent_fallback() -> None:
    response = client_for().get("/models/retired", headers=AUTH)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "routing_failed"


def test_the_shipped_catalogue_is_served_over_http_exactly_as_written() -> None:
    body = payload(client_for(catalog=ModelCatalog.load(REPO_CATALOG)))

    by_capability = {item["capability"]: item for item in body["models"]}
    assert by_capability["default"]["model"] == "ollama/gpt-oss:20b"
    assert by_capability["fast"]["model"] == "ollama/gemma3:12b"
    assert by_capability["reasoning"]["model"] == "ollama/qwen3:14b"
    # Every shipped row now goes through the platform's one transport, and this
    # client wired only a fake, so LiteLLM is what the operator is told is missing.
    assert by_capability["default"]["provider"] == "litellm"
    assert body["providers_missing"] == ["litellm"]


def test_the_routing_table_is_not_a_public_door() -> None:
    """``GET /v1/models`` is the application-facing view of what may be asked for.

    Both doors take a credential. ``GET /models`` answers *which infrastructure*
    would answer, so any host that could reach the port without a key would read the
    deployment — which is the defect this closes.
    """
    client = client_for()

    for path in ("/models", "/models/reasoning"):
        response = client.get(path)

        assert response.status_code == 401, f"{path} answered without a credential"
        assert response.json()["error"]["code"] == "unauthenticated"


def test_a_wrong_credential_is_refused_the_same_way() -> None:
    response = client_for().get("/models", headers={"Authorization": "Bearer not-a-real-key"})

    assert response.status_code == 401


def test_a_broken_catalogue_turns_introspection_into_a_503() -> None:
    app = create_app(
        make_settings().with_overrides(catalog_path=REPO_CATALOG.parent / "absent.yaml"),
        provider_registry=ProviderRegistry(),
    )

    response = TestClient(app).get("/models", headers=AUTH)

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "catalog_error"


def test_the_api_key_is_never_returned_by_any_endpoint() -> None:
    client = client_for()
    body = client.get("/models", headers=AUTH).text + client.get(
        "/models/reasoning", headers=AUTH
    ).text

    assert TEST_API_KEY not in body
