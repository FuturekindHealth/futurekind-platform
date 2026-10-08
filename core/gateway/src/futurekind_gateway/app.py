"""Application factory for the FutureKind Gateway.

Everything the Gateway needs is assembled here — configuration, model
catalogue, router, provider registry, metrics — and hung off ``app.state`` so
route handlers stay thin and tests can substitute any single piece.

Startup is deliberately non-fatal.  If the catalogue is missing or invalid the
process still serves ``/health`` and ``/health/ready`` and explains itself,
because a container that crash-loops over a YAML typo tells an operator less
than one that reports the exact line at fault.  Every request surface then
answers ``503 catalog_error`` until it is fixed.

There is exactly one refusal to start: an alias this Gateway will send that
LiteLLM does not recognise (:mod:`futurekind_gateway.litellm_config`). A typo in
one file degrades; a broken two-sided contract fails every request on that
capability, and a Gateway that boots into that is choosing the worst moment to
find out. ``docs/SPECIFICATION.md`` SPEC-07-03 records the rule; the log line
says which of the two files to correct.

The provider registry this factory builds is empty unless a caller supplies one
— ``create_app`` stays the test seam. Production wiring lives in
:func:`futurekind_gateway.main.build_production_app`, which registers
LiteLLMProvider and then calls this. That split is what keeps "which backends can
this build invoke" a deployment fact rather than an import side effect.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable, Sequence
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import __version__
from .api import ROUTERS
from .catalog import ModelCatalog
from .config import GatewaySettings, discover_litellm_config_path
from .errors import CatalogError, ConfigurationError, GatewayError
from .litellm_config import AliasReport, LiteLLMConfig, litellm_rows, verify_aliases
from .observability.logging import (
    REQUEST_ID_HEADER,
    configure_logging,
    get_logger,
    get_request_id,
    log_event,
    new_request_id,
    set_request_id,
)
from .observability.metrics import Metrics
from .providers import ProviderFactory, ProviderRegistry
from .routing import ModelRouter
from .service import GatewayService

DESCRIPTION = """
The single entry point for every AI request in the FutureKind platform.

### The rule this service enforces

Applications name a **skill** — what the clinician is doing. They never choose
infrastructure, and they never choose policy.

    Application → Gateway → LiteLLM → provider → model

The Gateway owns skills, policy, authorization, audit and clinical context.
LiteLLM owns model aliases, provider routing, retries, failover and cost
tracking, per `docs/adr/ADR-0002-Gateway-vs-LiteLLM.md`. No request field
accepts a model, provider or endpoint: a body that names one is rejected,
because accepting it would make every hardware change a breaking change for
clinical applications.

### Policy is configuration

Each skill declares its clinical risk level, its approval and audit
requirements, whether a lesser model may answer it, and the request limits it
runs under — in `core/gateway/models.yaml`, validated when the Gateway starts.
A high or critical risk skill that does not state these is refused at startup
rather than defaulted. The rules, and what each one does at request time, are in
`docs/architecture/gateway-policy.md`.

### Endpoints

| Endpoint | Purpose |
| --- | --- |
| `POST /chat` | Ask for a completion by skill. Authenticated. Policy-enforced. |
| `POST /v1/chat/completions` | The same request, in OpenAI's format. `model` is a skill. |
| `GET /v1/models` | The skills an OpenAI-format client may select. |
| `GET /models` | Skills with their policy, and the routing table beneath them. Authenticated. |
| `GET /health` | Component verdicts. Always 200 while running; names no provider, model or path. |
| `GET /health/ready` | Whether traffic should be routed here. 503 when not. |
| `GET /metrics` | Prometheus exposition. Authenticated — its labels name providers and models. |

### Build status

The Gateway skeleton is complete — configuration, catalogue, policy, routing, the
provider contract, the HTTP surface and observability — and **LiteLLM is wired as
its provider**. A well-formed request resolves its skill, enforces the policy that
skill declares, and is sent to LiteLLM under the alias the catalogue agrees with
`configs/litellm/config.yaml`. LiteLLM then chooses the weights, and retries and
failover stay on that side of the boundary per `ADR-0002`.

Without `FK_GATEWAY_LITELLM_BASE_URL` set, the provider cannot build and the
Gateway answers `503 configuration_error` — it never guesses an endpoint.
`stream: true` is refused with `501` until streaming has a specification
(SPEC-15-03).

### Privacy

Request and response text is never written to the Gateway's own logs. Log lines
carry skill, clinical risk, capability, model, provider, latency, token counts
and a hashed caller label — enough to audit and to capacity-plan, not enough to
reconstruct a consultation.
"""

OPENAPI_TAGS: list[dict[str, str]] = [
    {
        "name": "chat",
        "description": "The only endpoint applications are expected to call for AI work.",
    },
    {
        "name": "openai-compat",
        "description": (
            "The same rules in OpenAI's wire format, for an interface that can "
            "talk to nothing else. `model` means skill here, and no operation on "
            "this surface accepts or returns a model id, alias or provider."
        ),
    },
    {
        "name": "models",
        "description": "Catalogue introspection: what a capability currently resolves to.",
    },
    {"name": "health", "description": "Liveness and readiness for orchestrators."},
    {"name": "metrics", "description": "Prometheus exposition for monitoring."},
]


def build_catalog(
    settings: GatewaySettings,
    supplied: ModelCatalog | None,
) -> tuple[ModelCatalog | None, str | None]:
    """Return ``(catalog, error_message)`` without raising.

    A supplied catalogue wins outright, which is how a test injects one without
    touching the filesystem.
    """
    if supplied is not None:
        return supplied, None
    if settings.catalog_path is None:
        return None, (
            "no model catalogue available: set FK_GATEWAY_MODELS_PATH to a models.yaml "
            "or run from a repository checkout"
        )
    try:
        return ModelCatalog.load(settings.catalog_path), None
    except CatalogError as exc:
        return None, exc.message


def verify_alias_contract(
    settings: GatewaySettings, catalog: ModelCatalog | None
) -> AliasReport | None:
    """Prove that every alias this Gateway will send exists on LiteLLM's side.

    Returns ``None`` when there is nothing to prove — no catalogue, or no enabled
    row routed to LiteLLM — which is the state a test with a fake provider runs
    in. Otherwise it reads LiteLLM's configuration and refuses to start when an
    alias does not exist there, because the alternative is a ``502`` on the first
    clinical request that capability serves.

    Raises :class:`ConfigurationError` when the LiteLLM configuration cannot be
    read, is not configured at all, or does not answer to an alias the catalogue
    declares. A broken *catalogue* never reaches here: that stays non-fatal, as
    described above, and is reported by every traffic surface as ``503``.
    """
    if catalog is None:
        return None
    rows = litellm_rows(catalog)
    if not rows:
        return None
    # An explicit setting wins; discovery is the repository's own convenience, so
    # a checkout checks the file it actually ships and a container that mounts
    # nothing is refused instead of serving aliases nobody has agreed to.
    path = settings.litellm_config_path or discover_litellm_config_path()
    if path is None:
        raise ConfigurationError(
            "The model catalogue routes to LiteLLM but no LiteLLM configuration is "
            "available to check the aliases against",
            details={
                "capabilities": [entry.capability for entry in rows],
                "aliases": [entry.alias for entry in rows],
                "hint": (
                    "mount configs/litellm/config.yaml into the container, or set "
                    "FK_GATEWAY_LITELLM_CONFIG to its path — the two files must be "
                    "checked against each other before either is trusted"
                ),
            },
        )
    return verify_aliases(catalog, LiteLLMConfig.load(path))


def create_app(
    settings: GatewaySettings | None = None,
    *,
    catalog: ModelCatalog | None = None,
    provider_registry: ProviderRegistry | None = None,
    providers: Sequence[tuple[str, ProviderFactory]] = (),
    metrics: Metrics | None = None,
) -> FastAPI:
    """Assemble a Gateway application.

    Each keyword exists so a test can substitute exactly one collaborator and
    leave the rest real.
    """
    runtime_settings = settings or GatewaySettings.from_env()
    registry = provider_registry if provider_registry is not None else ProviderRegistry()
    for name, factory in providers:
        registry.register(name, factory)

    app_metrics = metrics if metrics is not None else Metrics()
    loaded, startup_error = build_catalog(runtime_settings, catalog)
    # The one fatal check in this process. See verify_alias_contract.
    alias_report = verify_alias_contract(runtime_settings, loaded)
    router = (
        ModelRouter(loaded, default_capability=runtime_settings.default_capability)
        if loaded is not None
        else None
    )
    service = (
        GatewayService(
            router=router,
            registry=registry,
            settings=runtime_settings,
            metrics=app_metrics,
        )
        if router is not None
        else None
    )
    logger = get_logger("futurekind.gateway")

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        configure_logging(
            level=runtime_settings.log_level,
            json_logs=runtime_settings.json_logs,
            service=runtime_settings.service_name,
        )
        log_event(
            logger,
            "info",
            "gateway_starting",
            version=__version__,
            host=runtime_settings.host,
            port=runtime_settings.port,
            catalog=loaded.source if loaded else None,
            models=loaded.size() if loaded else 0,
            providers_registered=list(registry.names()),
            require_auth=runtime_settings.require_auth,
        )
        if startup_error is not None:
            app_metrics.record_catalog_failure()
            log_event(logger, "error", "catalog_load_failed", detail=startup_error)
        elif loaded is not None:
            app_metrics.describe_catalog(loaded.entries)
        if alias_report is not None:
            log_event(
                logger,
                "info",
                "alias_contract_verified",
                aliases_checked=alias_report.checked,
                litellm_config=alias_report.config_source,
                drift=len(alias_report.drift),
            )
            # A drifted model string changes what the audit line claims, not where
            # the request goes, so it is reported and refused nothing.
            for entry in alias_report.drift:
                log_event(logger, "warning", "alias_model_drift", **entry)
        if runtime_settings.require_auth and not runtime_settings.authentication_configured:
            log_event(
                logger,
                "error",
                "authentication_misconfigured",
                detail=(
                    "authentication is required but no API keys are set, so POST /chat "
                    "will answer 503 until FK_GATEWAY_API_KEYS is configured"
                ),
            )
        try:
            yield
        finally:
            await registry.close_all()
            log_event(logger, "info", "gateway_stopped")

    app = FastAPI(
        title="FutureKind Gateway",
        version=__version__,
        description=DESCRIPTION,
        openapi_tags=OPENAPI_TAGS,
        contact={
            "name": "FutureKind Health",
            "url": "https://github.com/FuturekindHealth",
        },
        license_info={"name": "Apache-2.0"},
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    app.state.settings = runtime_settings
    app.state.catalog = loaded
    app.state.catalog_error = startup_error
    app.state.alias_report = alias_report
    app.state.router = router
    app.state.registry = registry
    app.state.metrics = app_metrics
    app.state.service = service

    # -- middleware ----------------------------------------------------------------------

    @app.middleware("http")
    async def request_context(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        """Bind a request id, time the request, and write one access log line."""
        incoming = request.headers.get(REQUEST_ID_HEADER)
        request_id = incoming.strip() if incoming and incoming.strip() else new_request_id()
        set_request_id(request_id)
        request.state.request_id = request_id
        started = time.perf_counter()

        try:
            response = await call_next(request)
        except Exception:
            log_event(
                logger,
                "error",
                "request_failed",
                method=request.method,
                path=request.url.path,
                duration_ms=int((time.perf_counter() - started) * 1000),
            )
            raise

        response.headers[REQUEST_ID_HEADER] = request_id
        log_event(
            logger,
            "info",
            "request_completed",
            request_id=request_id,
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            duration_ms=int((time.perf_counter() - started) * 1000),
            caller=getattr(request.state, "caller", None),
        )
        return response

    # -- error rendering -----------------------------------------------------------------

    def render(exc: GatewayError, *, level: str = "warning") -> JSONResponse:
        """One envelope for every failure the Gateway reports on purpose."""
        app_metrics.record_error(exc.code)
        log_event(
            logger,
            level,
            "gateway_error",
            code=exc.code,
            status=exc.status_code,
            detail=exc.message[:500],
            error_details=exc.details,
        )
        return JSONResponse(status_code=exc.status_code, content=exc.to_body(get_request_id()))

    @app.exception_handler(GatewayError)
    async def gateway_error_handler(request: Request, exc: GatewayError) -> JSONResponse:
        return render(exc)

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        """Fold request-body problems into the same envelope as domain errors.

        Pydantic's default output includes the rejected value. For a clinical
        gateway that value may be patient narrative, so only the location and
        the violated rule are reported.
        """
        summary = [
            {"location": list(error.get("loc", ())), "reason": error.get("msg", "invalid")}
            for error in exc.errors()
        ]
        wrapped = GatewayError(
            "The request body did not validate",
            code="invalid_request",
            status_code=422,
            details={"errors": summary},
        )
        return render(wrapped, level="info")

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        """Keep framework errors (unknown route, bad method) inside the same envelope."""
        wrapped = GatewayError(str(exc.detail), code="http_error", status_code=exc.status_code)
        return render(wrapped, level="info")

    @app.exception_handler(Exception)
    async def unhandled_handler(request: Request, exc: Exception) -> JSONResponse:
        """Never leak an internal exception body to a caller."""
        logger.exception("unhandled_exception", extra={"error_type": type(exc).__name__})
        app_metrics.record_error("internal_error")
        wrapped = GatewayError(
            "The Gateway failed unexpectedly; the request id in this response "
            "identifies the log entry",
            code="internal_error",
            status_code=500,
        )
        return JSONResponse(status_code=500, content=wrapped.to_body(request_id=get_request_id()))

    # -- routes --------------------------------------------------------------------------

    for component in ROUTERS:
        app.include_router(component)

    return app


__all__ = ["DESCRIPTION", "OPENAPI_TAGS", "build_catalog", "create_app", "verify_alias_contract"]
