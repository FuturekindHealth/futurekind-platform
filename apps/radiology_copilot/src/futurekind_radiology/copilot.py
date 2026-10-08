"""The workflow itself: draft, human review, export.

Three operations and no state. Each takes a document and returns a new one, so
nothing in this application holds clinical data between requests — which is what
lets a hospital run it as a stateless service and keep the record where
``docs/DOMAIN_MODEL.md`` says a Report belongs: in the EHR.

The order of checks in :meth:`RadiologyCopilot.draft` is the safety property.
Governance is read *before* the answer is parsed, so a draft cannot be produced
under a policy that would not have allowed it.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any, Literal

from pydantic import BaseModel

from . import __version__
from .errors import (
    DegradedAnswerError,
    GatewayRequestError,
    ModelOutputError,
    PolicyNotEnforcedError,
    ReportTruncatedError,
    ReviewError,
    SkillMismatchError,
    UnsignedExportError,
)
from .gateway import RADIOLOGY_SKILL, GatewayClient, GatewayCompletion
from .prompt import PROMPT_VERSION, build_messages
from .rendering import EXPORT_FORMATS, render
from .report import (
    SECTION_KEYS,
    ModelProvenance,
    ParsedAnswer,
    PolicyRef,
    RadiologyReport,
    ReportMetadata,
    ReviewRecord,
    SkillRef,
    format_utc,
    parse_model_answer,
    utc_now,
)
from .submission import StudySubmission

ReviewDecision = Literal["signed", "returned_for_correction"]

#: The four governance fields a completion must report for a radiology draft.
_POLICY_FIELDS = ("clinical_risk", "approval_required", "audit_required", "allow_downgrade")

#: What this document format was written against. A radiology draft is only safe
#: to produce where every request leaves a record, no lesser model may answer, and
#: the platform's own approval gate is not being asked of it: this Alpha records a
#: clinician's sign-off *inside the document*, which is not a platform **Approval**
#: and must not be presented as one. When the approvals ADR is written, this line
#: is where this application hands its review over instead of refusing.
_REQUIRED_POLICY = (
    ("audit_required", True),
    ("allow_downgrade", False),
    ("approval_required", False),
)

#: ``high`` is today's declaration. ``critical`` is accepted because a hospital may
#: decide radiology reporting is the most consequential thing it runs.
_REQUIRED_RISK_LEVELS = ("high", "critical")

_EXTENSIONS = {"json": "json", "text": "txt", "markdown": "md"}


def _policy_of(completion: GatewayCompletion) -> PolicyRef:
    """Read the four governance fields the completion must report.

    No defaults here. A completion that reports three of four is a version
    mismatch, and guessing the fourth is guessing the rule a report is filed
    under.
    """
    reported = completion.policy
    missing = [key for key in _POLICY_FIELDS if key not in reported]
    if missing:
        raise GatewayRequestError(
            "The Gateway reported an incomplete policy, so this application cannot say "
            "what governance the draft was written under.",
            details={"missing": missing, "reported": sorted(reported)},
            request_id=completion.request_id,
            status_code=502,
        )
    return PolicyRef(
        clinical_risk=str(reported["clinical_risk"]),
        approval_required=bool(reported["approval_required"]),
        audit_required=bool(reported["audit_required"]),
        allow_downgrade=bool(reported["allow_downgrade"]),
    )


class ExportResult(BaseModel):
    """One rendered document, ready to hand off."""

    output_format: str
    filename: str
    content: str
    report_id: str
    signed_by: str | None = None
    signed_at: str | None = None
    amended_sections: list[str] = []


class RadiologyCopilot:
    """Drafts, reviews and exports one skill's reports."""

    def __init__(self, gateway: GatewayClient, *, now: Callable[[], Any] = utc_now) -> None:
        self._gateway = gateway
        self._now = now

    # -- draft ------------------------------------------------------------------------------

    async def draft(
        self,
        submission: StudySubmission,
        *,
        extra_instructions: Mapping[str, str] | None = None,
    ) -> RadiologyReport:
        """Ask the Gateway for a structured draft of one study.

        ``extra_instructions`` carries a reviewer's steering for a redraft. They
        join the system turn, where the rules live, and are never a way to reach
        the model itself: the skill, the capability and the alias stay the
        Gateway's to decide.
        """
        messages = build_messages(submission, extra_instructions=extra_instructions)
        completion = await self._gateway.complete(skill=RADIOLOGY_SKILL, messages=messages)

        policy = self._check_governance(completion)
        if completion.ran_out_of_tokens:
            raise ReportTruncatedError(
                "The model ran out of tokens before it finished the report, so no draft "
                "was produced. Shorten the dictated findings or split the study and ask again.",
                request_id=completion.request_id,
                details={"finish_reason": completion.finish_reason},
            )

        parsed = self._parse(completion)
        return self._assemble(submission, completion, parsed, policy)

    def _parse(self, completion: GatewayCompletion) -> ParsedAnswer:
        """Read the answer, and name the request it came from if it cannot be read.

        A refusal the clinician cannot correlate with an audit line is a rumour.
        The Gateway already recorded this request; the request id is the only thing
        that connects the two, and the parse itself has no business knowing it.
        """
        try:
            return parse_model_answer(completion.content)
        except ModelOutputError as exc:
            exc.request_id = completion.request_id
            raise

    def _check_governance(self, completion: GatewayCompletion) -> PolicyRef:
        """Refuse a completion this document may not be built from.

        Returns the policy it did pass, so the one reading of the governance
        fields is also what gets written into the document.
        """
        if completion.skill != RADIOLOGY_SKILL:
            raise SkillMismatchError(
                f"The completion is reported as skill {completion.skill!r}, not "
                f"{RADIOLOGY_SKILL!r}, so it is not a radiology draft.",
                request_id=completion.request_id,
            )

        policy = _policy_of(completion)
        breached = [
            {"field": field, "reported": getattr(policy, field), "required": required}
            for field, required in _REQUIRED_POLICY
            if getattr(policy, field) is not required
        ]
        if breached:
            raise PolicyNotEnforcedError(
                "radiology-report is not running under the policy this document was written "
                "against, so no draft was produced. The Gateway must be corrected, not the "
                "clinician.",
                request_id=completion.request_id,
                details={"breached": breached},
            )
        if policy.clinical_risk not in _REQUIRED_RISK_LEVELS:
            raise PolicyNotEnforcedError(
                f"The Gateway reports radiology-report at clinical risk {policy.clinical_risk!r}. "
                "This application was written against a high-risk skill and will not draft "
                "beneath that.",
                request_id=completion.request_id,
                details={"clinical_risk": policy.clinical_risk, "required": "high or critical"},
            )
        if completion.degraded:
            raise DegradedAnswerError(
                "A lesser model answered a high-risk skill. The policy forbids the downgrade, "
                "so the answer is refused rather than shown as a draft.",
                request_id=completion.request_id,
                details={
                    "model": completion.model,
                    "attempts": completion.attempts,
                    "selected_by": completion.selected_by,
                },
            )
        return policy

    def _assemble(
        self,
        submission: StudySubmission,
        completion: GatewayCompletion,
        parsed: ParsedAnswer,
        policy: PolicyRef,
    ) -> RadiologyReport:
        """Put the document together, giving each section to the side that owns it.

        The indication and the department's own technique line are inputs, so they
        enter the report from the submission and never from the answer: a model that
        restates why the study was done has changed the question. The findings,
        impression and recommendations are the drafting work, and those come from
        the model.
        """
        usage = completion.usage or {}
        return RadiologyReport(
            clinical_indication=submission.clinical_indication,
            technique=submission.technique or parsed.sections["technique"],
            findings=parsed.sections["findings"],
            impression=parsed.sections["impression"],
            recommendations=parsed.sections["recommendations"],
            metadata=ReportMetadata(
                report_id=completion.request_id,
                study=submission.study,
                modality=submission.modality,
                dictated_findings=submission.findings,
                technique_from="department" if submission.has_technique else "model",
                drafted_at=format_utc(self._now()),
                prompt_version=PROMPT_VERSION,
                generator=f"futurekind-radiology-copilot/{__version__}",
                extra_sections=list(parsed.extra_keys),
            ),
            model_provenance=ModelProvenance(
                request_id=completion.request_id,
                model=completion.model,
                provider=completion.provider,
                selected_by=completion.selected_by,
                attempts=completion.attempts,
                degraded=completion.degraded,
                finish_reason=completion.finish_reason,
                prompt_tokens=int(usage.get("prompt_tokens", 0)),
                completion_tokens=int(usage.get("completion_tokens", 0)),
                total_tokens=int(usage.get("total_tokens", 0)),
                latency_ms=completion.latency_ms,
            ),
            skill=SkillRef(name=RADIOLOGY_SKILL, capability=completion.capability),
            policy=policy,
        )

    # -- human review ----------------------------------------------------------------------

    def review(
        self,
        report: RadiologyReport,
        *,
        decision: ReviewDecision,
        clinician: str,
        comment: str | None = None,
        amendments: Mapping[str, str] | None = None,
    ) -> RadiologyReport:
        """Record what a named clinician did, and return the document they produced.

        Accepting and amending are one act: the reviewer edits what needs editing
        and signs. An amendment never locks anything — a signed report can be
        reviewed again, and re-exported — because a document that refused further
        automation once a human had touched it would make the next draft worse.
        """
        name = clinician.strip()
        if not name:
            raise ReviewError(
                "A review must name the clinician who made it. P3 puts a name on every "
                "clinical statement, and an unattributed one is not a sign-off.",
                details={"clinician": "empty"},
            )
        if decision not in ("signed", "returned_for_correction"):
            raise ReviewError(
                f"Unknown review decision {decision!r}; use 'signed' or "
                "'returned_for_correction'.",
                details={"decision": decision},
            )
        note = comment.strip() if comment else ""
        if decision == "returned_for_correction" and not note:
            raise ReviewError(
                "A report returned for correction must say what is wrong with it, or the "
                "redraft repeats the same mistake.",
                details={"comment": "required"},
            )

        unknown = sorted(set(amendments or {}) - set(SECTION_KEYS))
        if unknown:
            raise ReviewError(
                f"Not report sections, so not amendable: {', '.join(unknown)}.",
                details={"unknown_sections": unknown, "sections": list(SECTION_KEYS)},
            )

        edits = {key: value.strip() for key, value in (amendments or {}).items()}
        amended = report.with_sections(**edits)
        history = sorted(
            dict.fromkeys([*amended.metadata.review.amendments, *sorted(edits)])
        )

        return amended.model_copy(
            update={
                "metadata": amended.metadata.model_copy(
                    update={
                        "review": ReviewRecord(
                            state=decision,
                            clinician=name,
                            reviewed_at=format_utc(self._now()),
                            comment=note or None,
                            amendments=history,
                        )
                    }
                )
            }
        )

    # -- export ----------------------------------------------------------------------------

    def export(self, report: RadiologyReport, *, output_format: str = "text") -> ExportResult:
        """Render the document for handoff, provided a clinician has signed it.

        The refusal is the point. The workflow the department runs puts review
        before export, and an application that exports an unsigned draft has a
        different workflow from the one the hospital agreed to.
        """
        if output_format not in EXPORT_FORMATS:
            raise ReviewError(
                f"Unsupported export format {output_format!r}; use one of "
                f"{', '.join(EXPORT_FORMATS)}.",
                details={"format": output_format, "supported": list(EXPORT_FORMATS)},
            )
        if not report.is_signed:
            review = report.metadata.review
            raise UnsignedExportError(
                "This report has not been signed by a radiologist, so it will not export.",
                details={
                    "state": review.state,
                    "clinician": review.clinician,
                    "report_id": report.metadata.report_id,
                },
            )
        return ExportResult(
            output_format=output_format,
            # No study name or modality in the filename: filenames reach shell
            # history, backups and mail attachments, and a clinical file's identity
            # should not depend on carrying patient text into all of them.
            filename=f"radiology-report-{report.metadata.report_id}.{_EXTENSIONS[output_format]}",
            content=render(report, output_format=output_format),
            report_id=report.metadata.report_id,
            signed_by=report.metadata.review.clinician,
            signed_at=report.metadata.review.reviewed_at,
            amended_sections=list(report.metadata.review.amendments),
        )


__all__ = ["ExportResult", "RadiologyCopilot", "ReviewDecision"]
