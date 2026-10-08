"""The OpenAPI document the Gateway publishes for itself.

These checks exist because the repository's hand-written
``core/gateway/openapi.yaml`` declared four paths with a ``summary`` each and no
``responses`` at all — a contract that would validate as OpenAPI 3.1 in name
only.  The served document is now the testable one, so the same class of gap
fails a build here.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from futurekind_gateway import __version__
from futurekind_gateway.app import create_app
from futurekind_gateway.policy import POLICY_KEYS
from futurekind_gateway.providers import ProviderRegistry
from tests.conftest import FakeProvider, make_catalog, make_settings


@pytest.fixture(scope="module")
def spec() -> dict:
    client = TestClient(create_app())
    document = client.get("/openapi.json")
    assert document.status_code == 200
    return document.json()


@pytest.fixture(scope="module")
def wired_spec() -> dict:
    """A spec built from a fully wired app, so every component schema is reachable."""
    registry = ProviderRegistry()
    registry.register("fake", lambda: FakeProvider())
    app = create_app(make_settings(), catalog=make_catalog(), provider_registry=registry)
    return TestClient(app).get("/openapi.json").json()


REQUIRED_PATHS = (
    "/chat",
    "/v1/chat/completions",
    "/v1/models",
    "/models",
    "/models/{capability}",
    "/health",
    "/health/ready",
    "/metrics",
)


def test_the_document_identifies_the_gateway_and_its_version(spec: dict) -> None:
    assert spec["info"]["title"] == "FutureKind Gateway"
    assert spec["info"]["version"] == __version__
    assert spec["openapi"].startswith("3.1")


def test_the_document_publishes_the_package_version(spec: dict) -> None:
    """No hand-maintained version string: the contract reports what the code says."""
    assert spec["info"]["version"] == __version__


@pytest.mark.parametrize("path", REQUIRED_PATHS)
def test_every_advertised_endpoint_exists(spec: dict, path: str) -> None:
    assert path in spec["paths"]


@pytest.mark.parametrize("path", REQUIRED_PATHS)
def test_every_operation_declares_responses(spec: dict, path: str) -> None:
    """The rule OpenAPI 3.1 requires and the hand-written file did not meet."""
    for operation in spec["paths"][path].values():
        assert operation.get("responses"), f"{path} declares an operation with no responses"
        assert "200" in operation["responses"] or "default" in operation["responses"]


@pytest.mark.parametrize("path", REQUIRED_PATHS)
def test_every_operation_is_summarised_and_described(spec: dict, path: str) -> None:
    for operation in spec["paths"][path].values():
        assert operation.get("summary"), f"{path} has an undocumented operation"
        assert operation.get("description"), f"{path} has an operation without a description"


def test_chat_documents_its_failure_modes(wired_spec: dict) -> None:
    responses = wired_spec["paths"]["/chat"]["post"]["responses"]

    for status in ("401", "404", "422", "501", "502", "503", "504"):
        assert status in responses, f"/chat does not document {status}"


def test_the_failure_envelope_is_a_named_schema(wired_spec: dict) -> None:
    schema = wired_spec["paths"]["/chat"]["post"]["responses"]["501"]["content"]["application/json"]

    assert "ErrorResponse" in schema["schema"]["$ref"]
    body = wired_spec["components"]["schemas"]["ErrorBodySchema"]
    assert {"code", "message", "retryable", "request_id"} <= set(body["properties"])


def test_authentication_is_declared_in_the_contract(spec: dict) -> None:
    schemes = spec["components"]["securitySchemes"]

    assert "HTTPBearer" in schemes or "bearerAuth" in schemes
    chat = spec["paths"]["/chat"]["post"]
    assert chat.get("security"), "POST /chat is documented as requiring no credential"


@pytest.mark.parametrize("path", ["/health", "/health/ready"])
def test_probe_endpoints_are_documented_as_public(spec: dict, path: str) -> None:
    """Only the two a container runtime or load balancer can reach without a key."""
    operation = next(iter(spec["paths"][path].values()))

    assert operation.get("security") in (None, []), f"{path} is documented as authenticated"


@pytest.mark.parametrize("path", ["/models", "/models/{capability}", "/metrics", "/v1/models"])
def test_every_inventory_endpoint_is_documented_as_requiring_a_credential(
    spec: dict, path: str
) -> None:
    """The contract must not advertise a free read of the routing table.

    `/models` and `/metrics` name providers, model ids and chains; `/v1/models`
    lists the skills an application may name. All four are doors an authorised
    caller opens, so a reader of the OpenAPI document learns that from the
    document rather than from a pentest.
    """
    operation = next(iter(spec["paths"][path].values()))

    assert operation.get("security"), f"{path} is documented as needing no credential"


def string_form(schema: dict) -> dict:
    """Unwrap a nullable field: pydantic puts the constraints inside ``anyOf``."""
    if "anyOf" in schema:
        return next(option for option in schema["anyOf"] if option.get("type") == "string")
    return schema


def test_the_request_body_offers_skill_and_capability_but_never_a_model(spec: dict) -> None:
    """The contract itself must not offer infrastructure selection (ADR-0002)."""
    schema = spec["components"]["schemas"]["ChatRequestSchema"]
    properties = schema["properties"]

    assert {"skill", "capability", "messages", "stream", "parameters"} <= set(properties)
    assert "model" not in properties
    assert "provider" not in properties
    assert "api_base" not in properties
    assert string_form(properties["skill"])["minLength"] == 1
    assert properties["messages"]["minItems"] == 1
    assert schema["additionalProperties"] is False


def test_the_catalogue_response_separates_intents_from_the_routing_table(spec: dict) -> None:
    list_schema = spec["components"]["schemas"]["ModelListResponseSchema"]["properties"]
    assert {"skills", "models", "routes"} <= set(list_schema)

    skill_card = spec["components"]["schemas"]["SkillCardSchema"]["properties"]
    assert not {"model", "provider", "fallbacks", "alias", "api_base"} & set(skill_card)
    assert "capability" in skill_card


def test_the_response_reports_provenance_without_accepting_it(spec: dict) -> None:
    """Model ids may be *reported* — a clinician must see what answered — but the
    request cannot carry one. These two schemas are the boundary, made explicit."""
    response = spec["components"]["schemas"]["ChatResponseSchema"]["properties"]
    request = spec["components"]["schemas"]["ChatRequestSchema"]["properties"]

    assert "model" in response
    assert "model" not in request


def test_the_request_body_documents_the_role_of_each_selector(spec: dict) -> None:
    properties = spec["components"]["schemas"]["ChatRequestSchema"]["properties"]

    # The skill description must name real intents, so a reader learns the vocabulary
    # from the contract rather than from the catalogue file.
    assert "radiology-report" in properties["skill"]["description"]
    assert "prefer" in properties["capability"]["description"].lower()


def test_the_role_enum_is_closed(spec: dict) -> None:
    message = spec["components"]["schemas"]["ChatMessageSchema"]

    assert set(message["properties"]["role"]["enum"]) == {"system", "user", "assistant"}


def test_the_response_reports_the_routing_decision(spec: dict) -> None:
    properties = spec["components"]["schemas"]["ChatResponseSchema"]["properties"]

    expected = {"capability", "provider", "model", "selected_by", "attempts", "degraded"}
    assert expected <= set(properties)


def test_the_response_reports_the_policy_that_ran(spec: dict) -> None:
    """An application must be able to tell a clinician that an answer still needs
    signing off, from the completion itself and not from a second call."""
    properties = spec["components"]["schemas"]["ChatResponseSchema"]["properties"]
    policy = spec["components"]["schemas"]["SkillPolicySchema"]["properties"]

    assert "policy" in properties
    assert set(policy) == {
        "clinical_risk",
        "approval_required",
        "audit_required",
        "allow_downgrade",
    }


def test_no_policy_field_is_accepted_from_a_caller(spec: dict) -> None:
    """Rule 7 of gateway-routing.md, made of JSON rather than prose: a caller may not
    relax the rules applied to it."""
    request = spec["components"]["schemas"]["ChatRequestSchema"]["properties"]

    assert not set(request) & POLICY_KEYS
    assert spec["components"]["schemas"]["ChatRequestSchema"]["additionalProperties"] is False


def test_skill_cards_and_completions_describe_policy_the_same_way(spec: dict) -> None:
    """One vocabulary for a clinical rule, or the two views drift and an application
    reads a different answer from the one the operator configured."""
    schemas = spec["components"]["schemas"]
    inherited = {
        key
        for key in schemas["SkillCardSchema"]["properties"]
        if key in schemas["SkillPolicySchema"]["properties"]
    }

    assert inherited == set(schemas["SkillPolicySchema"]["properties"])


def test_swagger_ui_is_served_for_humans() -> None:
    client = TestClient(create_app())

    docs = client.get("/docs")
    redoc = client.get("/redoc")

    assert docs.status_code == 200
    assert "text/html" in docs.headers["content-type"]
    assert redoc.status_code == 200


def test_the_description_states_the_architecture_rule(spec: dict) -> None:
    """The served description must teach the rule, not just decorate the page."""
    # Whitespace collapsed: the Markdown source wraps mid-phrase, the reader sees one line.
    description = " ".join(spec["info"]["description"].lower().split())

    assert "skill" in description, "the application-facing selector is undocumented"
    assert "never choose infrastructure" in description
    assert "litellm" in description, "ADR-0002 ownership is not stated in the contract"
    assert "alias" in description, "the contract does not say LiteLLM is addressed by alias"
    assert "post /v1/chat/completions" in description, "the OpenAI door is undocumented"
    assert "never written" in description, "the no-prompt-logging rule is not stated"


def test_tags_are_declared_and_used(spec: dict) -> None:
    declared = {tag["name"] for tag in spec["tags"]}

    assert declared == {"chat", "openai-compat", "models", "health", "metrics"}
    used = {
        tag
        for path in spec["paths"].values()
        for operation in path.values()
        for tag in operation.get("tags", [])
    }
    assert used <= declared
