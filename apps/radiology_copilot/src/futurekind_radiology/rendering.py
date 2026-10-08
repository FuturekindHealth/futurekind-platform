"""Clinical formatting: the same document, read four ways.

Formatting is a safety surface, not cosmetics. A report printed on paper must
make it impossible to miss that no one has signed it, must not reorder or drop a
section relative to the JSON the reviewer checked, and must carry the quality
findings that decided whether it could be signed at all — a printed report that
silently drops the advisory the radiologist read on screen is a different document
from the one that was approved.

Three formats, because the workflow has three readers: ``json`` for the system
that stores it, ``text`` for the printout and the referring clinician, and
``markdown`` for the screen. The section order in all three is the document
model's order, and the sign-off line is the first thing on the page either way.
"""

from __future__ import annotations

from .report import SECTION_KEYS, RadiologyReport

EXPORT_FORMATS = ("json", "text", "markdown")

#: The headings a printout shows. Kept short because it appears at the top of a
#: page a clinician glances at while talking to someone.
_HEADINGS = {
    "clinical_indication": "CLINICAL INDICATION",
    "technique": "TECHNIQUE",
    "findings": "FINDINGS",
    "impression": "IMPRESSION",
    "recommendations": "RECOMMENDATIONS",
    "follow_up": "FOLLOW-UP",
}

_UNSIGNED_BANNER = "DRAFT — NOT SIGNED. Not for clinical use."
_SIGNED_BANNER = "SIGNED BY THE REPORTING RADIOLOGIST"

_STATUS_WORDS = {
    "clear": "no issues raised",
    "advisory": "advisory notes",
    "blocking": "blocking findings",
}


def _status_line(report: RadiologyReport) -> str:
    review = report.metadata.review
    if review.state == "signed" and review.clinician:
        return f"{_SIGNED_BANNER} — {review.clinician}, {review.reviewed_at}"
    if review.state == "returned_for_correction":
        return f"RETURNED FOR CORRECTION — {review.clinician or 'unnamed reviewer'}"
    return _UNSIGNED_BANNER


def _quality_lines(report: RadiologyReport) -> list[str]:
    """The machine pass, in the same words the review screen showed."""
    quality = report.quality
    if not quality.findings:
        return [f"Quality checks: {_STATUS_WORDS[quality.status]} ({len(quality.checks_run)} run)"]
    lines = [
        f"Quality checks: {len(quality.findings)} "
        f"{_STATUS_WORDS[quality.status]} from {len(quality.checks_run)} checks"
    ]
    for finding in quality.findings:
        where = f" [{finding.section}]" if finding.section else ""
        lines.append(f"  ({finding.severity}){where} {finding.message}")
        if finding.evidence:
            lines.append(f"      quoted: {finding.evidence}")
    return lines


def _confidence_lines(report: RadiologyReport) -> list[str]:
    confidence = report.confidence
    lines = [f"Confidence: {confidence.level} — {confidence.label}"]
    lines += [f"  - {reason}" for reason in confidence.reasons]
    lines.append(f"  Basis: {confidence.basis}")
    return lines


def _provenance_lines(report: RadiologyReport) -> list[str]:
    provenance = report.model_provenance
    return [
        f"Skill: {report.skill.name} (capability {report.skill.capability})",
        f"Policy: clinical risk {report.policy.clinical_risk}, "
        f"audit {report.policy.audit_required}, "
        f"downgrade allowed {report.policy.allow_downgrade}, "
        f"approval required {report.policy.approval_required}",
        f"Model: {provenance.model} via {provenance.provider} "
        f"(selected by {provenance.selected_by}, {provenance.attempts} attempt"
        f"{'s' if provenance.attempts != 1 else ''}"
        f"{', DEGRADED' if provenance.degraded else ''})",
        f"Finish reason: {provenance.finish_reason or 'not reported'}",
        f"Tokens: {provenance.prompt_tokens} prompt / {provenance.completion_tokens} "
        f"completion / {provenance.total_tokens} total",
        f"Gateway latency: {provenance.latency_ms} ms",
        f"Gateway request id: {provenance.request_id}",
        f"Prompt: {report.metadata.prompt_version}",
        f"Generator: {report.metadata.generator}",
    ]


def _study_lines(report: RadiologyReport) -> list[str]:
    """What the draft was made from. A reader of a printed report is entitled to know
    whether it compared anything and under which study profile it was checked."""
    metadata = report.metadata
    lines = [
        f"Study     : {metadata.study}",
        f"Modality  : {metadata.modality}",
        f"Report id : {metadata.report_id}",
        f"Drafted   : {metadata.drafted_at}",
    ]
    if metadata.review.reviewed_at:
        lines.append(f"Reviewed  : {metadata.review.reviewed_at}")
    if metadata.profile:
        lines.append(f"Profile   : {metadata.profile}")
    lines.append(
        "Compared  : "
        + ("; ".join(metadata.compared_with) if metadata.compared_with else "no priors supplied")
    )
    return lines


def render_text(report: RadiologyReport) -> str:
    """The printout. Plain text, because paper is still how reports travel."""
    metadata = report.metadata
    lines = ["RADIOLOGY REPORT", _status_line(report), ""]
    lines += _study_lines(report)
    if metadata.extra_sections:
        returned = ", ".join(metadata.extra_sections)
        lines.append(
            f"Note      : the model also returned {returned}, "
            "which are not part of a signed report."
        )
    for key in SECTION_KEYS:
        lines += ["", _HEADINGS[key], report.section(key)]
    lines += ["", "-" * 42, ""]
    lines += _quality_lines(report)
    lines += [""] + _confidence_lines(report)
    lines += [""] + _provenance_lines(report)
    if metadata.review.comment:
        lines += ["", f"Reviewer comment: {metadata.review.comment}"]
    return "\n".join(lines).strip() + "\n"


def render_markdown(report: RadiologyReport) -> str:
    """The review screen. Same order, same headings, nothing added."""
    metadata = report.metadata
    lines = [
        "# Radiology report",
        "",
        f"**{_status_line(report)}**",
        "",
        f"- Study: {metadata.study}",
        f"- Modality: {metadata.modality}",
        f"- Report id: {metadata.report_id}",
        f"- Drafted: {metadata.drafted_at}",
        f"- Profile: {metadata.profile or 'none (nine general checks only)'}",
        "- Compared with: "
        + ("; ".join(metadata.compared_with) if metadata.compared_with else "no priors supplied"),
    ]
    for key in SECTION_KEYS:
        # The same heading text as the printout. Two renderings of one document
        # should not disagree about what a section is called.
        lines += ["", f"## {_HEADINGS[key]}", report.section(key)]
    lines += ["", "## Quality checks", ""]
    lines += [f"- {line.strip()}" for line in _quality_lines(report)]
    lines += ["", "## Confidence", ""]
    lines += [f"- {line.strip()}" for line in _confidence_lines(report)]
    lines += ["", "## Provenance", ""]
    lines += [f"- {line}" for line in _provenance_lines(report)]
    if metadata.review.comment:
        lines += ["", f"> Reviewer comment: {metadata.review.comment}"]
    return "\n".join(lines).strip() + "\n"


def render(report: RadiologyReport, *, output_format: str) -> str:
    """Render in one of the three supported formats.

    ``json`` is the document itself, so a reviewer who approved the screen view is
    looking at the same fields the export carries — there is no fourth rendering
    that could disagree with the other three.
    """
    if output_format == "json":
        return report.model_dump_json(indent=2) + "\n"
    if output_format == "text":
        return render_text(report)
    if output_format == "markdown":
        return render_markdown(report)
    raise ValueError(f"Unsupported export format {output_format!r}; use one of {EXPORT_FORMATS}")


__all__ = ["EXPORT_FORMATS", "render", "render_markdown", "render_text"]
