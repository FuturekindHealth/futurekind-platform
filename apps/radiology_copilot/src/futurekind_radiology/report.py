"""The clinical document this application produces, and how it is read back.

Twelve things at the top level: the six sections a radiologist signs, then the
quality pass and the confidence assessment that make a draft checkable, then the
three governance blocks that make it defensible — how it was made, under which
skill, under which policy — and the metadata holding the study and the review. The
document is the deliverable, so it is also the handoff: the EHR will one day
receive exactly these fields.

Parsing is **fail closed**. A model that answers in prose, omits a section or
writes `"impression": ""` produces an error, never a report. The alternative is a
document that looks complete, and in radiology a plausible empty section is how a
haemorrhage goes unmentioned.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .errors import ModelOutputError

#: The six sections of the report, in signing order. This tuple is the authority:
#: the prompt states it, the parser enforces it, the renderer prints it and the
#: quality checks read it — and a drift between those five is the bug this single
#: definition prevents.
SECTION_KEYS = (
    "clinical_indication",
    "technique",
    "findings",
    "impression",
    "recommendations",
    "follow_up",
)

#: The five sections the model is asked to write. The indication is not one of
#: them: it is the referrer's statement, submitted by the clinician, and a model
#: that paraphrases it has changed the clinical question being answered. Ownership
#: of every section is stated in :mod:`copilot._assemble`.
#:
#: `recommendations` and `follow_up` are separate because a radiologist does two
#: different acts with them: what to do now, and when to look again. One field
#: invites the second to be swallowed by the first, and an interval that never gets
#: written is how a surveillance study is not done at all.
MODEL_SECTION_KEYS = ("technique", "findings", "impression", "recommendations", "follow_up")

#: The four sections whose whole purpose is to be drafted from the dictation and corrected
#: afterwards. The clinical indication is never among them: it is the referrer's question, and
#: a reviewer who wants it different edits the box they typed it into.
REVIEWER_EDITABLE_SECTIONS = ("findings", "impression", "recommendations", "follow_up")


def editable_section_keys(technique_from: str) -> tuple[str, ...]:
    """Which sections a review screen may accept an edit for.

    Locking follows **who owns the words**, not which section they sit in, and the technique
    line is the case that proves the difference. When the department supplied its acquisition
    parameters, that text is the department's statement and a screen that let it be retyped
    would let it be retyped wrongly; the box to change is the one it came from. When nothing
    was supplied, the line is the model's — it wrote "Technique not provided" — and the
    clinician at the console is the only person who knows whether the study had a protocol.
    A screen that locks the model's own sentence locks the radiologist out of their report.
    """
    if technique_from == "model":
        return ("technique", *REVIEWER_EDITABLE_SECTIONS)
    return REVIEWER_EDITABLE_SECTIONS


ReviewState = Literal["pending_review", "signed", "returned_for_correction"]

#: The two outcomes a quality check can have. `block` refuses a signature until the
#: words change; `advisory` is shown and left to the clinician. Nothing else,
#: because a third level in a clinical tool becomes the one everyone ignores.
Severity = Literal["block", "advisory"]


def format_utc(moment: datetime) -> str:
    """One timestamp format for the whole document, always UTC."""
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def utc_now() -> datetime:
    return datetime.now(UTC)


# -- reading the model's answer ---------------------------------------------------------------


def _extract_object(text: str) -> str:
    """The first complete JSON object in an answer, or a refusal naming why.

    Scanning rather than ``json.loads`` on the whole string is deliberate: a small
    deployment answers with the object *inside* a sentence, and the medicine in it
    may be perfectly good. Throwing that away would be its own kind of clinical
    failure. What is *not* done is repair — a truncated object is refused, not
    closed by guesswork.
    """
    start = text.find("{")
    if start == -1:
        raise ModelOutputError(
            "The model answered in prose, not in the required JSON object.",
            details={"reason": "no_json_object", "answer_chars": len(text)},
        )

    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(text)):
        character = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
            continue
        if character == '"':
            in_string = True
        elif character == "{":
            depth += 1
        elif character == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]

    raise ModelOutputError(
        "The model's JSON object was never closed, so the answer is incomplete.",
        details={"reason": "unterminated_json_object", "answer_chars": len(text)},
    )


def _section_text(key: str, value: Any) -> str:
    """One section as clinical text, or a refusal.

    A list of strings is accepted and joined, because local models frequently
    dictate findings as an array; every item is kept, so nothing is lost. Anything
    else — a number, an object, a boolean — is refused rather than coerced,
    because coercion invents wording the model did not write.
    """
    if isinstance(value, str):
        text = value.strip()
    elif isinstance(value, list) and all(isinstance(item, str) for item in value):
        text = "\n".join(item.strip() for item in value if item.strip())
    else:
        raise ModelOutputError(
            f"The '{key}' section of the model's answer is not text.",
            details={"reason": "section_not_text", "section": key, "found": type(value).__name__},
        )
    if not text:
        raise ModelOutputError(
            f"The '{key}' section came back empty. A signed report may not contain a "
            "blank section, so no draft was produced.",
            details={"reason": "section_empty", "section": key},
        )
    return text


class ParsedAnswer(BaseModel):
    """A model answer that was readable as a report, and what else it carried."""

    sections: dict[str, str]
    extra_keys: tuple[str, ...] = ()

    model_config = ConfigDict(frozen=True)


def parse_model_answer(content: str) -> ParsedAnswer:
    """Read the five authored sections out of a completion. Never fabricates one.

    The clinical indication is not read here. It is the submitted question, and the
    document carries it from the submission (``copilot._assemble``), so a model
    cannot rewrite the reason the study was done.
    """
    try:
        payload = json.loads(_extract_object(content))
    except json.JSONDecodeError as exc:
        # ``exc.msg`` and ``exc.pos`` describe the shape of the failure. The
        # offending text is patient data, so it is not repeated here.
        raise ModelOutputError(
            "The model's answer is not valid JSON, so no report could be read from it.",
            details={"reason": "invalid_json", "json_error": exc.msg, "position": exc.pos},
        ) from exc

    missing = [key for key in MODEL_SECTION_KEYS if key not in payload]
    if missing:
        raise ModelOutputError(
            f"The model's answer is missing {', '.join(missing)}. "
            "No draft was produced from an incomplete report.",
            details={
                "reason": "missing_sections",
                "missing": missing,
                "expected": list(MODEL_SECTION_KEYS),
            },
        )

    return ParsedAnswer(
        sections={key: _section_text(key, payload[key]) for key in MODEL_SECTION_KEYS},
        extra_keys=tuple(sorted(str(key) for key in payload if key not in MODEL_SECTION_KEYS)),
    )


# -- the document -------------------------------------------------------------------------------


class SkillRef(BaseModel):
    """Which application intent produced this document."""

    name: str
    capability: str


class PolicyRef(BaseModel):
    """The governance the draft was written under, as the Gateway reported it.

    Four booleans and a risk level, and no numeric limit — the Gateway's own
    reporting rule (SPEC-06-09) carried into the document.
    """

    clinical_risk: str
    approval_required: bool
    audit_required: bool
    allow_downgrade: bool


class ModelProvenance(BaseModel):
    """How this draft came to exist. P8 makes it mandatory rather than decorative.

    A reviewer is entitled to know that a lesser model answered, that generation
    stopped early, or that the answer took three attempts.
    """

    request_id: str = Field(description="The Gateway request id; correlates with its audit line.")
    model: str = Field(description="The weights that answered. Reported, never accepted as input.")
    provider: str
    selected_by: str
    attempts: int
    degraded: bool
    finish_reason: str | None = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    latency_ms: int = 0


class ReviewRecord(BaseModel):
    """The human stage of the workflow, recorded inside the document.

    This is the sign-off act, not a platform **Approval** record: there is no
    approvals service yet (``gateway-policy.md:213`` — "Approval is a refusal, not
    a workflow"), so an application that claimed to have stored one would be
    inventing an audit trail.
    """

    state: ReviewState = "pending_review"
    clinician: str | None = None
    reviewed_at: str | None = None
    comment: str | None = None
    amendments: list[str] = Field(
        default_factory=list,
        description="Sections the clinician rewrote. An amendment never hides the "
        "model's original authorship: provenance stays, and the document says "
        "which parts a human changed.",
    )


class QualityFinding(BaseModel):
    """One check outcome, phrased for the radiologist who has to act on it."""

    model_config = ConfigDict(str_strip_whitespace=True)

    check: str
    severity: Severity
    section: str | None = None
    message: str
    evidence: str | None = Field(
        default=None,
        description="The offending words, quoted from the draft. A check that says "
        "'a measurement is unsupported' without saying which one asks the reviewer "
        "to hunt through a report while a patient waits.",
    )


class QualityReport(BaseModel):
    """The machine pass over one draft: status, findings, and the honest scope.

    Produced by :mod:`quality`, which is the only place the rules live. This is the
    schema, so the document can be read back without importing the checker.
    """

    status: Literal["clear", "advisory", "blocking"]
    findings: list[QualityFinding] = Field(default_factory=list)
    checks_run: list[str] = Field(default_factory=list)
    checked_at: str
    scope: str

    @property
    def blocking(self) -> list[QualityFinding]:
        return [finding for finding in self.findings if finding.severity == "block"]

    @property
    def advisory(self) -> list[QualityFinding]:
        return [finding for finding in self.findings if finding.severity == "advisory"]


class ConfidenceAssessment(BaseModel):
    """How well this draft's own text is supported. Not a clinical probability.

    Computed by :mod:`quality` from the submitted text, the provenance the Gateway
    reported and the quality pass. It is never the model's opinion of itself: an
    answer that returned its own confidence had that value recorded and discarded,
    because a model's certainty does not track its correctness and showing it on
    screen would train a radiologist to trust the wrong number.
    """

    level: Literal["supported", "review-carefully", "not-safe-to-sign"]
    label: str
    reasons: list[str] = Field(default_factory=list)
    basis: str


class ReportMetadata(BaseModel):
    """Study facts and document state, kept apart from the clinical prose."""

    report_id: str
    study: str
    modality: str
    dictated_findings: str = Field(
        min_length=1,
        description="What the reporting clinician actually dictated, next to the findings "
        "section the model wrote from it. A reviewer comparing the two is doing "
        "the work this document exists to support, and the comparison needs both "
        "sides of it (P13).",
    )
    technique_from: Literal["department", "model"] = Field(
        description="Who owns the technique line: the department when it supplied the "
        "parameters, the model when it only had to say they were not provided."
    )
    compared_with: list[str] = Field(
        default_factory=list,
        description="The previous reports this study was drafted against, named by date and "
        "study only. The full text of a prior report stays out of the signed document: "
        "a reviewer needs to know a comparison was made and against what, and a second "
        "copy of an old report inside a new one is how a patient history starts to "
        "spread through a system no one intended.",
    )
    profile: str | None = Field(
        default=None,
        description="The study profile the quality checks used, if any. Naming it matters: "
        "an MRI brain drafted under no profile was checked by nine rules, an MRI knee "
        "by the same nine and no structure list — and a reviewer should be able to tell "
        "which report they are looking at.",
    )
    drafted_at: str
    prompt_version: str
    generator: str
    extra_sections: list[str] = Field(
        default_factory=list,
        description="Keys the model returned outside the five it was asked for. Dropped "
        "from the document, named here, because silent loss in a clinical pipeline "
        "is the thing to avoid — not the extra key itself.",
    )
    review: ReviewRecord = Field(default_factory=ReviewRecord)


class RadiologyReport(BaseModel):
    """The structured report: six sections, the quality pass, confidence, provenance."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    clinical_indication: str
    technique: str
    findings: str
    impression: str
    recommendations: str
    follow_up: str
    quality: QualityReport
    confidence: ConfidenceAssessment
    metadata: ReportMetadata
    model_provenance: ModelProvenance
    skill: SkillRef
    policy: PolicyRef

    @property
    def is_signed(self) -> bool:
        return self.metadata.review.state == "signed"

    @property
    def review_state(self) -> ReviewState:
        return self.metadata.review.state

    def section(self, key: str) -> str:
        return getattr(self, key)

    def sections(self) -> dict[str, str]:
        """The six signed sections as one mapping, in signing order.

        The quality checks and the review screen both work on this, and both have to
        see the same thing the signer sees — so there is exactly one way to ask the
        document for its own text.
        """
        return {key: getattr(self, key) for key in SECTION_KEYS}

    def with_sections(self, **updates: str) -> RadiologyReport:
        """A copy with amended sections. The original is never mutated.

        The document's history belongs to whoever stores it, so the application
        hands back a new copy rather than keeping drafts alive in memory.
        """
        unknown = sorted(set(updates) - set(SECTION_KEYS))
        if unknown:
            raise ValueError(f"Not report sections: {', '.join(unknown)}")
        return self.model_copy(update=dict(updates))


__all__ = [
    "MODEL_SECTION_KEYS",
    "ConfidenceAssessment",
    "ParsedAnswer",
    "PolicyRef",
    "QualityFinding",
    "QualityReport",
    "RadiologyReport",
    "ReportMetadata",
    "ReviewRecord",
    "ModelProvenance",
    "SECTION_KEYS",
    "Severity",
    "SkillRef",
    "format_utc",
    "parse_model_answer",
    "utc_now",
]
