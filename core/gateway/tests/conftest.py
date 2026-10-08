"""Shared fixtures and test doubles for the Gateway suite.

Providers are fakes defined here and nowhere in ``src`` — the point of the
skeleton is that the Gateway can be fully exercised without a real backend,
through the same ``Provider`` contract a real implementation will satisfy.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from futurekind_gateway.catalog import ModelCatalog
from futurekind_gateway.config import GatewaySettings
from futurekind_gateway.providers import ProviderRegistry
from futurekind_gateway.providers.base import (
    ChatRequest,
    ChatResult,
    Provider,
    ProviderHealth,
    TokenUsage,
)

TEST_API_KEY = "test-gateway-key"
GATEWAY_ROOT = Path(__file__).resolve().parents[1]
REPO_CATALOG = GATEWAY_ROOT / "models.yaml"

FAKE_CATALOG_DOCUMENT: dict[str, Any] = {
    "skills": {
        "clinical-chat": {"capability": "default", "clinical_risk": "moderate"},
        "summarize-document": {
            "capability": "fast",
            "description": "Condense a document.",
            "clinical_risk": "low",
        },
        "retired-skill": {"capability": "default", "clinical_risk": "low", "enabled": False},
    },
    "models": {
        "default": {"provider": "fake", "model": "fake-large", "alias": "fk-default"},
        "fast": {
            "provider": "fake",
            "model": "fake-small",
            "fallbacks": ["default"],
            "alias": "fk-fast",
        },
        "reasoning": {
            "provider": "fake",
            "model": "fake-thinker",
            "fallbacks": ["fast"],
            "alias": "fk-reasoning",
        },
        "retired": {"provider": "fake", "model": "fake-old", "enabled": False},
    },
}

#: Skills whose policy has teeth, kept out of ``FAKE_CATALOG_DOCUMENT`` so the
#: routing and API tests keep their simple three-skill shape.  ``reasoning``
#: falls back to ``fast`` in the document above, which is what makes a policy that
#: suppresses the chain observable rather than merely asserted.
POLICY_CATALOG_SKILLS: dict[str, Any] = {
    "radiology-report": {
        "capability": "reasoning",
        "clinical_risk": "high",
        "allow_downgrade": False,
    },
    "critical-care-summary": {
        "capability": "reasoning",
        "clinical_risk": "critical",
        "allow_downgrade": False,
        "approval_required": True,
    },
    "patient-leaflet": {
        "capability": "fast",
        "clinical_risk": "low",
        "audit_required": False,
        "max_messages": 2,
        "max_completion_tokens": 128,
        "request_timeout_seconds": 2.0,
    },
}


def policy_document(**overrides: Any) -> dict[str, Any]:
    """The fake catalogue, plus the skills that carry real policy."""
    merged = {key: dict(value) for key, value in FAKE_CATALOG_DOCUMENT.items()}
    merged["skills"] = {**merged["skills"], **POLICY_CATALOG_SKILLS}
    merged.update(overrides)
    return merged


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """No test may inherit Gateway configuration from the developer's shell."""
    for key in list(os.environ):
        if key.startswith("FK_GATEWAY_"):
            monkeypatch.delenv(key, raising=False)


def make_settings(**overrides: Any) -> GatewaySettings:
    base = GatewaySettings(
        host="127.0.0.1",
        port=8100,
        catalog_path=None,
        default_capability="default",
        require_auth=True,
        api_keys=(TEST_API_KEY,),
        request_timeout_seconds=5.0,
        json_logs=False,
    )
    return base.with_overrides(**overrides)


def make_catalog(document: dict[str, Any] | None = None) -> ModelCatalog:
    return ModelCatalog.from_document(document or FAKE_CATALOG_DOCUMENT, source="test-catalog")


def make_policy_catalog() -> ModelCatalog:
    """A catalogue carrying the governed skills, for policy-specific tests."""
    return ModelCatalog.from_document(policy_document(), source="test-policy-catalog")


class FakeProvider(Provider):
    """Answers from a scripted queue and records every request it received."""

    name = "fake"

    def __init__(self, *responses: Any, healthy: bool = True) -> None:
        self.responses: list[Any] = list(responses)
        self.requests: list[ChatRequest] = []
        self.closed = 0
        self._healthy = healthy

    async def chat(self, request: ChatRequest) -> ChatResult:
        self.requests.append(request)
        if self.responses:
            outcome = self.responses.pop(0)
        else:
            outcome = ChatResult(
                content="answer",
                model=request.model,
                provider=self.name,
                usage=TokenUsage(prompt_tokens=3, completion_tokens=5),
                finish_reason="stop",
            )
        if isinstance(outcome, Exception):
            raise outcome
        if callable(outcome):
            outcome = outcome(request)
        return outcome

    async def health(self) -> ProviderHealth:
        return ProviderHealth(
            provider=self.name,
            healthy=self._healthy,
            detail="fake provider, always in-process",
        )

    async def close(self) -> None:
        self.closed += 1


@pytest.fixture
def provider() -> FakeProvider:
    return FakeProvider()


@pytest.fixture
def registry(provider: FakeProvider) -> ProviderRegistry:
    """A registry with the fake bound to the provider name the test catalogue uses."""
    instance = ProviderRegistry()
    instance.register("fake", lambda: provider)
    return instance


@pytest.fixture
def catalog() -> ModelCatalog:
    return make_catalog()


@pytest.fixture
def settings() -> GatewaySettings:
    return make_settings()


@pytest.fixture
def app_factory(settings: GatewaySettings, catalog: ModelCatalog, registry: ProviderRegistry):
    """Build an application wired to the test catalogue and fake provider."""

    def _build(**overrides: Any):  # noqa: ANN202
        from futurekind_gateway.app import create_app

        local_settings = overrides.pop("settings", settings)
        local_catalog = overrides.pop("catalog", catalog)
        local_registry = overrides.pop("registry", registry)
        return create_app(
            local_settings,
            catalog=local_catalog,
            provider_registry=local_registry,
            **overrides,
        )

    return _build


@pytest.fixture
def client(app_factory) -> Iterator[Any]:  # noqa: ANN001
    """Authenticated client against the fully wired test application."""
    from fastapi.testclient import TestClient

    with TestClient(app_factory()) as test_client:
        yield test_client


@pytest.fixture
def auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {TEST_API_KEY}"}
