"""HTTP tests for ``GET /health``, ``GET /health/ready`` and ``GET /metrics``.

The first two are the only endpoints a probe can reach without a credential, so
what they must *not* say is as important as what they do: no provider inventory,
no routing table, no filesystem path. ``/metrics`` lost its public door for the
same reason — its label values name providers and model ids.
"""

from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from futurekind_gateway.api import routes_health
from futurekind_gateway.app import create_app
from futurekind_gateway.observability.metrics import Metrics
from futurekind_gateway.providers import ProviderRegistry
from futurekind_gateway.providers.base import (
    ChatRequest,
    ChatResult,
    Provider,
    ProviderHealth,
)
from tests.conftest import REPO_CATALOG, TEST_API_KEY, FakeProvider, make_catalog, make_settings

AUTH = {"Authorization": f"Bearer {TEST_API_KEY}"}


class DownProvider(Provider):
    """Registered but unreachable, so /health must report the fault — as a verdict,
    without quoting the backend or naming it to an unauthenticated reader."""

    name = "fake"

    async def chat(self, request: ChatRequest) -> ChatResult:  # pragma: no cover
        raise AssertionError("health checks must not invoke chat")

    async def health(self) -> ProviderHealth:
        return ProviderHealth(
            provider="fake", healthy=False, detail="cannot reach http://internal-host:9000"
        )


def registry_of(*providers: Provider) -> ProviderRegistry:
    registry = ProviderRegistry()
    for provider in providers:
        registry.register(provider.name, lambda provider=provider: provider)
    return registry


def build_client(**overrides) -> TestClient:  # noqa: ANN003
    settings = overrides.pop("settings", make_settings())
    registry = overrides.pop("registry", registry_of(FakeProvider()))
    collector = overrides.pop("metrics", None)
    app = create_app(
        settings,
        catalog=make_catalog(),
        provider_registry=registry,
        metrics=collector or Metrics(),
    )
    return TestClient(app)


def assert_sample(body: str, selector: str, expected: float | None = None) -> None:
    """Find one Prometheus sample, tolerating ``1`` and ``1.0`` value rendering."""
    match = re.search(re.escape(selector) + r"[ \t]+([0-9.eE+\-]+)", body)
    assert match, f"sample {selector!r} missing from exposition"
    if expected is not None:
        assert float(match.group(1)) == pytest.approx(expected)


# -- /health ------------------------------------------------------------------------------------


def test_health_lists_every_component_and_reports_ok() -> None:
    payload = build_client().get("/health").json()

    assert [item["name"] for item in payload["components"]] == [
        "catalogue",
        "providers",
        "authentication",
    ]
    assert payload["status"] == "ok"
    assert payload["service"] == "futurekind-gateway"
    assert payload["version"]
    assert payload["authentication"] is True


def test_health_is_200_but_degraded_when_no_provider_is_implemented() -> None:
    """The skeleton's real state: alive, honest about not being able to serve models."""
    response = build_client(registry=registry_of()).get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "degraded"
    providers = next(item for item in payload["components"] if item["name"] == "providers")
    assert providers["healthy"] is False
    assert "501" in providers["detail"]


def test_health_surfaces_an_unhealthy_provider_as_a_verdict_not_a_quote() -> None:
    payload = build_client(registry=registry_of(DownProvider())).get("/health").json()

    providers = next(item for item in payload["components"] if item["name"] == "providers")
    assert providers["healthy"] is False
    assert "1 of 1 providers unhealthy" in providers["detail"]
    assert payload["status"] == "degraded"


def test_health_never_quotes_an_upstream_address_or_backend_error() -> None:
    """The probe that reads this holds no credential, so the backend's own words —
    which name hosts — belong in the log, not in this response."""
    body = build_client(registry=registry_of(DownProvider())).get("/health").text

    assert "internal-host" not in body
    assert "cannot reach" not in body


def test_health_reports_misconfigured_authentication_as_degraded() -> None:
    payload = build_client(settings=make_settings(api_keys=())).get("/health").json()

    authentication = next(
        item for item in payload["components"] if item["name"] == "authentication"
    )
    assert authentication["healthy"] is False
    assert payload["status"] == "degraded"


def test_health_needs_no_credential() -> None:
    assert build_client().get("/health").status_code == 200


def test_health_still_answers_when_the_catalogue_failed_to_load() -> None:
    """A container with a bad models.yaml must explain itself, not vanish."""
    app = create_app(
        make_settings().with_overrides(catalog_path=REPO_CATALOG.parent / "missing.yaml"),
        provider_registry=registry_of(),
    )

    response = TestClient(app).get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "degraded"
    catalogue = next(item for item in payload["components"] if item["name"] == "catalogue")
    assert catalogue["healthy"] is False
    assert catalogue["detail"] == routes_health.CATALOGUE_UNAVAILABLE


def test_health_publishes_no_catalogue_path_no_providers_and_no_routing() -> None:
    """The leak this endpoint used to have: `catalog.source` answered with the
    absolute path of models.yaml, and `providers` named what the build had wired.

    A probe needs a verdict, not an inventory — the inventory is `GET /models`,
    which now requires a credential for exactly that reason.
    """
    payload = build_client().get("/health").json()

    assert set(payload) == {
        "status",
        "service",
        "version",
        "checked_at",
        "components",
        "authentication",
    }
    assert "catalog" not in payload
    assert "providers" not in payload

    body = build_client().get("/health").text
    assert "test-catalog" not in body
    assert ".yaml" not in body


# -- /health/ready -------------------------------------------------------------------------------


def test_ready_when_the_catalogue_and_credentials_are_in_place() -> None:
    payload = build_client().get("/health/ready").json()

    assert payload["ready"] is True
    assert payload["reasons"] == []
    assert payload["checked_at"]


def test_not_ready_when_authentication_has_no_keys() -> None:
    response = build_client(settings=make_settings(api_keys=())).get("/health/ready")

    assert response.status_code == 503
    reasons = response.json()["error"]["details"]["reasons"]
    assert any("API keys" in reason for reason in reasons)


def test_not_ready_when_the_catalogue_is_unusable() -> None:
    app = create_app(
        make_settings().with_overrides(catalog_path=REPO_CATALOG.parent / "missing.yaml"),
        provider_registry=registry_of(),
    )

    response = TestClient(app).get("/health/ready")

    assert response.status_code == 503
    assert "catalogue" in response.json()["error"]["details"]["reasons"][0]


def test_ready_does_not_require_a_provider_implementation() -> None:
    """Readiness means 'configured honestly', not 'every backend wired up'. The 501
    from /chat already tells operators which provider is missing."""
    assert build_client(registry=registry_of()).get("/health/ready").status_code == 200


def test_ready_when_authentication_is_explicitly_disabled() -> None:
    assert build_client(settings=make_settings(require_auth=False)).get(
        "/health/ready"
    ).status_code == 200


# -- /metrics -------------------------------------------------------------------------------------


def test_metrics_require_a_credential_because_their_labels_name_backends() -> None:
    """/metrics used to be public on the theory that a counter is not a secret.

    The exposition's label values are the routing table — provider, model id,
    capability — so an unauthenticated scrape read the deployment. Prometheus
    sends a bearer token on a scrape; the Gateway now expects one.
    """
    client = build_client()

    unauthenticated = client.get("/metrics")

    assert unauthenticated.status_code == 401
    assert unauthenticated.text.count("fk_gateway_") == 0

    authenticated = client.get("/metrics", headers=AUTH)
    assert authenticated.status_code == 200
    assert authenticated.headers["content-type"].startswith("text/plain")
    assert "fk_gateway_requests_total" in authenticated.text


def test_metrics_count_the_traffic_they_served() -> None:
    client = build_client()
    client.post(
        "/chat",
        json={"capability": "default", "messages": [{"role": "user", "content": "x"}]},
        headers=AUTH,
    )

    body = client.get("/metrics", headers=AUTH).text
    assert_sample(
        body, 'fk_gateway_requests_total{capability="default",outcome="success",provider="fake"}'
    )
    assert_sample(body, 'fk_gateway_tokens_total{capability="default",direction="prompt"}', 3)
    assert_sample(body, 'fk_gateway_tokens_total{capability="default",direction="completion"}', 5)
    assert "fk_gateway_request_latency_seconds_count" in body


def test_metrics_count_routing_failures_by_code() -> None:
    client = build_client()
    client.post(
        "/chat",
        json={"capability": "vision", "messages": [{"role": "user", "content": "x"}]},
        headers=AUTH,
    )

    assert_sample(
        client.get("/metrics", headers=AUTH).text,
        'fk_gateway_errors_total{code="unknown_capability"}',
    )


def test_metrics_publish_the_routing_table() -> None:
    collector = Metrics()
    client = build_client(metrics=collector)
    collector.describe_catalog(make_catalog().entries)

    assert 'fk_gateway_catalog_models{capability="fast"' in client.get(
        "/metrics", headers=AUTH
    ).text


def test_health_and_metrics_agree_on_who_must_authenticate() -> None:
    """The two unauthenticated doors are exactly the two probes can reach.

    Anything else that describes the deployment — its metrics, its routing table —
    requires a credential. This is the boundary the whole change rests on, so it is
    asserted as one fact rather than left to be inferred from the tests above.
    """
    client = build_client()

    for path in ("/health", "/health/ready"):
        assert client.get(path).status_code == 200, f"{path} should answer a probe"

    for path in ("/metrics", "/models"):
        assert client.get(path).status_code == 401, f"{path} must not answer without a credential"


def test_in_flight_requests_return_to_zero_once_served() -> None:
    """The start/end pairing must not leak, or capacity dashboards drift forever."""
    collector = Metrics()
    client = build_client(metrics=collector)
    client.post(
        "/chat",
        json={"capability": "default", "messages": [{"role": "user", "content": "x"}]},
        headers=AUTH,
    )

    assert_sample(client.get("/metrics", headers=AUTH).text, "fk_gateway_requests_in_flight", 0)
