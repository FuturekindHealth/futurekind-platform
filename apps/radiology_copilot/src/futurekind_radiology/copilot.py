"""The workflow itself: draft, quality check, human review, export.

Four operations and no state. Each takes a document and returns a new one, so
nothing in this application holds clinical data between requests — which is what
lets a hospital run it as a stateless service and keep the record where
``docs/DOMAIN_MODEL.md`` says a Report belongs: in the EHR.

The order of stages in :meth:`RadiologyCopilot.draft` is the safety property, and
each one is why it comes before the ones after it:

1. **Governance** — an answer that arrived under the wrong policy is refused before
   its medicine is read, so a draft cannot be produced under a policy that would
   not have allowed it.
2. **Truncation** — a cut-off answer is refused before it is parsed, because a
   half-written impression is the one artefact that reads as complete.
3. **Parsing** — the sections must exist and be prose.
4. **Quality** — the sections are compared with what was submitted. This is the
   stage that catches the failure a screen cannot: an invented measurement, a
   comparison with a prior nobody supplied.
5. **Confidence** — computed from all of the above, never from the model.

Signing re-runs stage 4 on the words that will actually be signed. A verdict about
a version of the report nobody approved is not a quality control, it is a stamp.
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
from .profiles import profile_for
from .prompt import PROMPT_VERSION, build_messages
from .quality import assess_confidence, evaluate
from .rendering import EXPORT_FORMATS, render
from .report import (
    SECTION_KEYS,
    ConfidenceAssessment,
    ModelProvenance,
    ParsedAnswer,
    PolicyRef,
    QualityReport,
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


def _human_takes_the_section(quality: QualityReport, edited: list[str]) -> QualityReport:
    """Downgrade blocking findings in a section the clinician has just rewritten.

    The check compares the draft with what was *submitted*, and a radiologist
    typing a measurement reads the image, not the dictation — so the machine has
    no authority to call that number wrong. What it can still do is say so on the
    page, in the same document, forever: the finding stays, at advisory, and the
    `amendments` list names who made the section theirs.

    Sections nobody edited keep their blocking severity. That is the case this
    exists for: accepting a model's invented measurement unchanged, and then
    signing it, is the failure the product must refuse.
    """
    if not edited:
        return quality
    downgraded = [
        finding.model_copy(
            update={
                "severity": "advisory",
                "message": (
                    finding.message
                    + " This section was rewritten by the reporting clinician, so the "
                    "check is advisory: the image, not the dictation, is the source here."
                ),
            }
        )
        if finding.severity == "block" and finding.section in edited
        else finding
        for finding in quality.findings
    ]
    status: Literal["clear", "advisory", "blocking"] = (
        "blocking"
        if any(finding.severity == "block" for finding in downgraded)
        else ("advisory" if downgraded else "clear")
    )
    return quality.model_copy(update={"findings": downgraded, "status": status})


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
        """Ask the Gateway for a structured draft of one study, and check it.

        ``extra_instructions`` carries a reviewer's steering for a redraft. They
        join the system turn, where the rules live, and are never a way to reach
        the model itself: the skill, the capability and the alias stay the
        Gateway's to decide.

        A draft with a blocking quality finding is still returned. Withholding it
        would leave the radiologist staring at an empty screen with no idea what was
        wrong and nothing to correct; what it cannot do is be signed.
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
        report = self._assemble(submission, completion, parsed, policy)
        return self.check(report, submission)

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

    def _quality_pass(
        self,
        sections: dict[str, str],
        submission: StudySubmission,
        *,
        extra_sections: tuple[str, ...],
        attempts: int,
        finish_reason: str | None,
        degraded: bool,
        edited: list[str] | None = None,
    ) -> tuple[QualityReport, ConfidenceAssessment]:
        """One run of the checks and the assessment, from the same eight inputs.

        Both come out together because they are the same judgement twice: the
        confidence must be derived from the findings this pass actually produced, not
        from a second reading that could disagree with the first.

        `edited` names the sections a clinician has just rewritten, so a finding in
        one of them stops being a refusal — see :func:`_human_takes_the_section`.
        """
        profile = profile_for(submission.study)
        quality = evaluate(
            sections,
            submission,
            checked_at=format_utc(self._now()),
            extra_sections=extra_sections,
            structure_checklist=profile.structures if profile else (),
            out_of_scope_claims=profile.out_of_scope_claims if profile else (),
        )
        quality = _human_takes_the_section(quality, edited or [])
        confidence = assess_confidence(
            quality,
            submission,
            attempts=attempts,
            finish_reason=finish_reason,
            degraded=degraded,
        )
        return quality, confidence

    def check(
        self, report: RadiologyReport, submission: StudySubmission
    ) -> RadiologyReport:
        """Re-run the quality pass over the text the document carries now.

        This is what the review screen calls after every edit, and what signing
        calls before it accepts a name. The submission is required rather than
        reconstructed from the document: a prior report's text is deliberately not
        copied into a signed report, and a check that silently ran without it would
        flag the 18 mm abscess that came from that prior as an invention.

        Only `quality` and `confidence` change. The review state, the provenance and
        the sections are untouched, so re-checking an edited draft cannot alter what
        it says or who wrote it.
        """
        quality, confidence = self._quality_pass(
            report.sections(),
            submission,
            extra_sections=tuple(report.metadata.extra_sections),
            attempts=report.model_provenance.attempts,
            finish_reason=report.model_provenance.finish_reason,
            degraded=report.model_provenance.degraded,
        )
        return report.model_copy(update={"quality": quality, "confidence": confidence})

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
        impression, recommendations and follow-up are the drafting work, and those
        come from the model.
        """
        usage = completion.usage or {}
        sections = {
            "clinical_indication": submission.clinical_indication,
            "technique": submission.technique or parsed.sections["technique"],
            "findings": parsed.sections["findings"],
            "impression": parsed.sections["impression"],
            "recommendations": parsed.sections["recommendations"],
            "follow_up": parsed.sections["follow_up"],
        }
        quality, confidence = self._quality_pass(
            sections,
            submission,
            extra_sections=parsed.extra_keys,
            attempts=completion.attempts,
            finish_reason=completion.finish_reason,
            degraded=completion.degraded,
        )
        profile = profile_for(submission.study)
        return RadiologyReport(
            **sections,
            quality=quality,
            confidence=confidence,
            metadata=ReportMetadata(
                report_id=completion.request_id,
                study=submission.study,
                modality=submission.modality,
                dictated_findings=submission.findings,
                technique_from="department" if submission.has_technique else "model",
                compared_with=[
                    f"{prior.reported_on} — {prior.modality} {prior.study}"
                    for prior in submission.previous_reports
                ],
                profile=profile.name if profile else None,
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
        submission: StudySubmission | None = None,
    ) -> RadiologyReport:
        """Record what a named clinician did, and return the document they produced.

        Accepting and amending are one act: the reviewer edits what needs editing
        and signs. An amendment never locks anything — a signed report can be
        reviewed again, and re-exported — because a document that refused further
        automation once a human had touched it would make the next draft worse.

        The checks run again on the amended text before a signature is recorded, and
        a blocking finding stops the sign-off (`decision == "signed"`). Not the
        amendment, and not the return-for-correction: a radiologist can always fix
        the words or send it back. What they cannot do is attest to a report this
        application can show is unsupported by what they submitted, and then have the
        record say they did.

        ``submission`` is required for a signature for that reason: the checks
        compare the draft with what was submitted, and after an edit there is no
        other text to compare it with.
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

        if submission is not None:
            quality, confidence = self._quality_pass(
                amended.sections(),
                submission,
                extra_sections=tuple(amended.metadata.extra_sections),
                attempts=amended.model_provenance.attempts,
                finish_reason=amended.model_provenance.finish_reason,
                degraded=amended.model_provenance.degraded,
                edited=sorted(edits),
            )
            amended = amended.model_copy(
                update={"quality": quality, "confidence": confidence}
            )
        elif decision == "signed":
            raise ReviewError(
                "A signature needs the submission that produced this draft, so the quality "
                "checks can be re-run on the text being signed rather than on the one the "
                "model first returned.",
                details={"submission": "required_for_signing"},
            )

        if decision == "signed" and amended.quality.blocking:
            blocking = amended.quality.blocking
            raise ReviewError(
                f"{len(blocking)} statement(s) in this report are unsupported by the text "
                "submitted, so it cannot be signed. Correct the wording, or send it back for "
                "correction — the checks re-run on every edit.",
                details={
                    # Check ids and section names, never the offending clinical text: a
                    # refusal is the artefact most likely to be logged.
                    "blocking": [
                        {"check": finding.check, "section": finding.section}
                        for finding in blocking
                    ],
                    "sections": sorted(
                        {finding.section for finding in blocking if finding.section}
                    ),
                },
            )

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
