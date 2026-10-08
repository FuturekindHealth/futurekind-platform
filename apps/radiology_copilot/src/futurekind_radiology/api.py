"""The application's own HTTP surface: three operations, one document.

``POST /draft`` → ``POST /review`` → ``POST /export`` is the workflow a
radiology department runs, in the order the clinician works through it. The
report travels *through* the caller in each request rather than being stored
here: the application is stateless by design, and the EHR is the record.

Trust model, stated plainly because it is unfinished work: these endpoints
authenticate nobody. The Gateway authenticates *this* application (its key never
leaves the environment it was set in), and the clinician's identity arrives in the
review body as a name the department already trusts. Binding that name to a real
session is ADR-0004's job and does not exist yet, so this service belongs behind
the hospital's own authentication, not in front of it.
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from . import SKILL_NAME, __version__
from .copilot import ExportResult, RadiologyCopilot, ReviewDecision
from .errors import RadiologyError
from .gateway import GatewayClient
from .report import RadiologyReport
from .settings import CopilotSettings
from .submission import StudySubmission


class DraftRequest(BaseModel):
    """What the clinician submits, plus any steering for a redraft."""

    model_config = ConfigDict(extra="forbid")

    submission: StudySubmission
    extra_instructions: dict[str, str] | None = Field(
        default=None,
        description="Reviewer notes for a redraft, keyed arbitrarily, e.g. "
        '{"focus": "comment on the posterior fossa"}. They join the system turn and '
        "cannot name a model, a provider or a policy.",
    )


class ReviewRequest(BaseModel):
    """The human stage: a named clinician accepts, amends or returns the draft."""

    model_config = ConfigDict(extra="forbid")

    report: RadiologyReport
    decision: ReviewDecision
    clinician: str = Field(
        min_length=1,
        max_length=200,
        description="The person accountable for this version of the report (P3).",
    )
    comment: str | None = Field(default=None, max_length=4_000)
    amendments: dict[str, str] | None = Field(
        default=None,
        description="Section name to replacement text. Only the five report sections are "
        "amendable; anything else is refused rather than filed as an unnamed note.",
    )


class ExportRequest(BaseModel):
    """Ask for the signed document in one format."""

    model_config = ConfigDict(extra="forbid")

    report: RadiologyReport
    format: Literal["json", "text", "markdown"] = "text"


DESCRIPTION = """The first clinical application on FutureKind: a radiology reporting
copilot for one skill, `radiology-report`.

A clinician submits an indication, a modality and their findings. This application
asks the Gateway for a structured draft — it never names a model, a provider or an
endpoint — refuses any answer that is not a complete report, holds it for a named
radiologist to review and amend, and exports only what a human has signed.

The nine things it returns are the five clinical sections plus `metadata`,
`model_provenance`, `skill` and `policy`: the medicine, and the record of how it
was produced and under what governance."""


def create_app(copilot: RadiologyCopilot, *, settings: CopilotSettings | None = None) -> FastAPI:
    """The door, with the workflow injected.

    The copilot arrives built rather than being built here, for the same reason it
    does at the Gateway: a test that wants a different upstream should not have to
    change the environment of a running process.
    """
    resolved = settings or CopilotSettings.from_env()
    app = FastAPI(
        title="FutureKind Radiology Copilot",
        version=__version__,
        description=DESCRIPTION,
        contact={"name": "FutureKind"},
    )

    @app.exception_handler(RadiologyError)
    async def refusal(request: Request, exc: RadiologyError) -> JSONResponse:
        """Every refusal in the platform's one error envelope."""
        return JSONResponse(status_code=exc.status_code, content=exc.to_body())

    @app.exception_handler(RequestValidationError)
    async def malformed(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        """A body that does not fit the contract, in the same envelope.

        FastAPI's default shape here is ``{"detail": [...]}``, and its entries
        carry ``input`` — the submitted value, which for this application is
        dictated clinical text. So the values are dropped and the field names
        stay: one error shape on every endpoint, and no route by which a rejected
        request prints a patient.
        """
        problems = [
            {key: value for key, value in item.items() if key not in {"input", "ctx"}}
            for item in exc.errors()[:5]
        ]
        body = {
            "error": {
                "code": "invalid_request",
                "message": "The request body does not fit this endpoint's contract.",
                "retryable": False,
                "request_id": None,
                "details": {"problems": problems},
            }
        }
        return JSONResponse(status_code=422, content=body)

    @app.get("/health", tags=["operations"])
    async def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "service": "futurekind-radiology-copilot",
            "version": __version__,
            "skill": SKILL_NAME,
            "gateway": resolved.redacted(),
        }

    @app.post(
        "/draft",
        response_model=RadiologyReport,
        tags=["workflow"],
        summary="Draft a structured report for one study",
        description=(
            "Sends the submission to the Gateway under skill `radiology-report` and "
            "returns the nine-part report. Nothing here chooses infrastructure: the "
            "request the Gateway receives names only the skill.\n\n"
            "A prose answer, a missing section or a truncated report is a `502`, not a "
            "half-written document. An answer that arrived under the wrong policy is a "
            "`503`."
        ),
        responses={
            422: {"description": "The body does not fit this endpoint, in the platform envelope."},
            502: {"description": "No usable draft: upstream failure, prose, or truncation."},
            503: {"description": "The skill's policy or the Gateway itself is not as required."},
        },
    )
    async def draft(payload: DraftRequest) -> RadiologyReport:
        return await copilot.draft(
            payload.submission, extra_instructions=payload.extra_instructions
        )

    @app.post(
        "/review",
        response_model=RadiologyReport,
        tags=["workflow"],
        summary="Record a named clinician's decision",
        description=(
            "`signed` with optional `amendments`, or `returned_for_correction` with a "
            "comment that says what is wrong.\n\n"
            "Amending does not lock the document: a signed report can be reviewed and "
            "re-exported, and the model's authorship stays in `model_provenance` while "
            "`metadata.review.amendments` names the sections a human rewrote."
        ),
        responses={422: {"description": "No clinician named, or an unknown section amended."}},
    )
    async def review(payload: ReviewRequest) -> RadiologyReport:
        return copilot.review(
            payload.report,
            decision=payload.decision,
            clinician=payload.clinician,
            comment=payload.comment,
            amendments=payload.amendments,
        )

    @app.post(
        "/export",
        response_model=ExportResult,
        tags=["workflow"],
        summary="Render the signed report for handoff",
        description=(
            "Three formats: `json` for the system that stores it, `text` for print, "
            "`markdown` for screen. Refuses `409` unless a clinician has signed — review "
            "comes before export in the department's workflow, and an application that "
            "exported past that would be running a different workflow."
        ),
        responses={409: {"description": "The report has not been signed."}},
    )
    async def export(payload: ExportRequest) -> ExportResult:
        return copilot.export(payload.report, output_format=payload.format)

    return app


def build_app(settings: CopilotSettings | None = None) -> FastAPI:
    """Assemble the production app from the environment."""
    resolved = settings or CopilotSettings.from_env()
    gateway = GatewayClient(
        base_url=resolved.gateway_base_url,
        api_key=resolved.gateway_api_key,
        timeout_seconds=resolved.request_timeout_seconds,
    )
    return create_app(RadiologyCopilot(gateway), settings=resolved)


__all__ = ["ExportRequest", "DraftRequest", "ReviewRequest", "build_app", "create_app"]
