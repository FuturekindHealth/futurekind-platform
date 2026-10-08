"""Prometheus metrics for the Gateway.

Every metric is created against a caller-owned :class:`CollectorRegistry`, never
the process-global default.  That keeps one Gateway instance's numbers
isolating cleanly from another's, which matters both for tests and for running
more than one app in a process.

Metric names are prefixed ``fk_gateway_`` so they cannot collide with the
metrics LiteLLM itself exports when both are scraped by the same Prometheus.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

#: Latency buckets covering sub-second routing through multi-minute clinical generations.
LATENCY_BUCKETS: tuple[float, ...] = (
    0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 20.0, 30.0, 60.0, 120.0,
)

NAMESPACE = "fk_gateway"


class Metrics:
    """The Gateway's metric surface."""

    def __init__(self, registry: CollectorRegistry | None = None) -> None:
        self.registry = registry if registry is not None else CollectorRegistry()

        self.requests_total = Counter(
            f"{NAMESPACE}_requests_total",
            "Chat requests handled by the Gateway, by capability, provider and outcome.",
            ["capability", "provider", "outcome"],
            registry=self.registry,
        )
        self.request_latency_seconds = Histogram(
            f"{NAMESPACE}_request_latency_seconds",
            "End-to-end Gateway latency for chat requests.",
            ["capability"],
            buckets=LATENCY_BUCKETS,
            registry=self.registry,
        )
        self.provider_attempts_total = Counter(
            f"{NAMESPACE}_provider_attempts_total",
            "Provider invocations, including fallback attempts.",
            ["provider", "model", "outcome"],
            registry=self.registry,
        )
        self.errors_total = Counter(
            f"{NAMESPACE}_errors_total",
            "Errors surfaced by the Gateway, by stable error code.",
            ["code"],
            registry=self.registry,
        )
        self.tokens_total = Counter(
            f"{NAMESPACE}_tokens_total",
            "Tokens reported by providers, by capability and direction.",
            ["capability", "direction"],
            registry=self.registry,
        )
        self.in_flight = Gauge(
            f"{NAMESPACE}_requests_in_flight",
            "Chat requests currently being served.",
            registry=self.registry,
        )
        self.catalog_models = Gauge(
            f"{NAMESPACE}_catalog_models",
            "Entries in the loaded model catalogue.",
            ["capability", "provider", "model"],
            registry=self.registry,
        )
        self.catalog_load_failures_total = Counter(
            f"{NAMESPACE}_catalog_load_failures_total",
            "Times the model catalogue failed to load.",
            registry=self.registry,
        )

    # -- recording helpers ---------------------------------------------------------------

    def record_attempt(self, *, provider: str, model: str, outcome: str) -> None:
        self.provider_attempts_total.labels(provider=provider, model=model, outcome=outcome).inc()

    def record_error(self, code: str) -> None:
        self.errors_total.labels(code=code).inc()

    def record_tokens(self, *, capability: str, prompt_tokens: int, completion_tokens: int) -> None:
        if prompt_tokens:
            self.tokens_total.labels(capability=capability, direction="prompt").inc(prompt_tokens)
        if completion_tokens:
            self.tokens_total.labels(capability=capability, direction="completion").inc(
                completion_tokens
            )

    def start_request(self) -> None:
        self.in_flight.inc()

    def end_request(self) -> None:
        self.in_flight.dec()

    def observe_request(
        self, *, capability: str, provider: str, outcome: str, seconds: float
    ) -> None:
        self.requests_total.labels(capability=capability, provider=provider, outcome=outcome).inc()
        self.request_latency_seconds.labels(capability=capability).observe(seconds)

    def describe_catalog(self, entries: Iterable[Any]) -> None:
        """Publish the routing table as labelled gauges, replacing any previous view."""
        self.catalog_models.clear()
        for entry in entries:
            self.catalog_models.labels(
                capability=entry.capability,
                provider=entry.provider,
                model=entry.model,
            ).set(1 if entry.enabled else 0)

    def record_catalog_failure(self) -> None:
        self.catalog_models.clear()
        self.catalog_load_failures_total.inc()

    # -- exposition ---------------------------------------------------------------------

    def render(self) -> tuple[bytes, str]:
        """Return the Prometheus text exposition and its content type."""
        return generate_latest(self.registry), CONTENT_TYPE_LATEST


__all__ = ["LATENCY_BUCKETS", "NAMESPACE", "Metrics"]
