"""Six axes of quality, kept apart on purpose.

A composite score is the most attractive and most destructive artefact in this space: one
number is easy to quote, easy to regress against, and impossible to act on, because it hides
*which* thing got worse. The golden dataset already states the rule at
`docs/product/GOLDEN_DATASET.yaml:54` — averaging hides both signal and danger — and this
module is that sentence made executable.

So: six axes, each with its own evidence source, direction, and reason for being null. There
is no `total`, no weighted sum, no "FutureKind score". `assert_not_combined()` exists so
that a future contributor who adds one finds a failing test rather than a quiet agreement.

The axes, and who is allowed to supply each one:

**`clinical_correctness`** — Is the medicine right? A clinician against a ratified
reference. Not computable tonight: needs labels and ratification.

**`writing_quality`** — Is it readable and in the department's format? Engine plus a
reader's re-read marks. Partly computable.

**`workflow_quality`** — Did it fit the work, or interrupt it? Session timings and
refusals. Not computable tonight: needs a human session.

**`safety`** — What reached a patient unchecked? Engine blocks plus post-hoc labels.
Partly computable.

**`efficiency`** — How much human work was removed? `evidence.edits` plus timers. Not
computable tonight: needs a final report.

**`user_satisfaction`** — Do they want to keep using it? The person, attested. Not
computable, and no proxy is allowed to stand in for it.

"Partly" means the deterministic half is computed and the human half is null. A null axis
carries a `reason`, because an absent number explained is a plan, and an absent number
unexplained is a dashboard with a hole in it.
"""

from __future__ import annotations

from dataclasses import dataclass, field

AXES: tuple[str, ...] = (
    "clinical_correctness",
    "writing_quality",
    "workflow_quality",
    "safety",
    "efficiency",
    "user_satisfaction",
)

#: Each axis's evidence source. Kept as data so a claim about an axis can be traced to the
#: kind of observation that produced it, which is the distinction
#: `docs/safety/CLINICAL_SAFETY.md` §5 makes between attestation and verification.
AXIS_SOURCES: dict[str, str] = {
    "clinical_correctness": "human label against a ratified reference answer",
    "writing_quality": "engine format checks + a reader's re-read marks",
    "workflow_quality": "session timers + refusal and interruption labels",
    "safety": "engine blocks, post-hoc false-alert labels, provenance fields",
    "efficiency": "edit classification and typing measures",
    "user_satisfaction": "the clinician, asked directly",
}

#: What would make each axis regressive. Written before any data, so nobody fits a story to
#: the numbers afterwards — the same discipline `run-cases.py` applies to its ranking.
REGRESSION_TRIGGERS: dict[str, str] = {
    "clinical_correctness": "any new E02/E07/E08 label on a case that previously had none",
    "writing_quality": "format_breach or a rising style-only edit rate",
    "workflow_quality": "review seconds rising with no change in draft content",
    "safety": "an unannounced degradation, or a block removed without its measurement",
    "efficiency": "human typed characters rising while draft length stays equal",
    "user_satisfaction": "the person says so, or stops using it",
}


class CombinedScoreError(RuntimeError):
    """Raised when anything tries to collapse the axes into one number."""


def assert_not_combined(*_args, **_kwargs) -> None:
    """The hook a future contributor will call by accident. It always fails.

    Deliberately the only function in this package that raises unconditionally: the cost of
    forgetting why a composite score is forbidden is higher than the cost of an odd-looking
    guard, and the reason is written in this docstring rather than in a document nobody
    opens before merging.
    """
    raise CombinedScoreError(
        "six axes stay six axes: a composite hides which one regressed "
        "(docs/product/GOLDEN_DATASET.yaml:54, docs/evidence/METRICS.md)"
    )


@dataclass
class AxisScore:
    name: str
    value: float | None
    scale: str
    evidence: tuple[str, ...] = ()
    reason_if_null: str | None = None
    supplied_by: str = ""


@dataclass
class CaseScore:
    """One case, six axes, and no way to average them by accident."""

    case_id: str
    skill: str
    axes: dict[str, AxisScore] = field(default_factory=dict)

    def __post_init__(self) -> None:
        missing = [axis for axis in AXES if axis not in self.axes]
        if missing:
            raise ValueError(f"a case score must state every axis, even as null: {missing}")

    def null_axes(self) -> dict[str, str]:
        return {
            name: axis.reason_if_null or "no reason recorded"
            for name, axis in self.axes.items()
            if axis.value is None
        }

    def as_dict(self) -> dict:
        return {
            "case_id": self.case_id,
            "skill": self.skill,
            "axes": {
                name: {
                    "value": axis.value,
                    "scale": axis.scale,
                    "supplied_by": axis.supplied_by or AXIS_SOURCES[name],
                    "evidence": list(axis.evidence),
                    "reason_if_null": axis.reason_if_null,
                }
                for name, axis in self.axes.items()
            },
        }


def _null(name: str, reason: str) -> AxisScore:
    return AxisScore(name=name, value=None, scale="0–1", reason_if_null=reason)


def score_case(
    case_id: str,
    skill: str,
    *,
    structure_coverage: float | None = None,
    engine_findings: tuple[str, ...] = (),
    blocking_checks: tuple[str, ...] = (),
    style_only_edit_rate: float | None = None,
    degradation_unannounced: bool = False,
    clinical_labels: dict[str, int] | None = None,
    review_seconds: float | None = None,
    typed_chars: int | None = None,
    satisfaction_rating: float | None = None,
) -> CaseScore:
    """Score what can be scored, and be explicit about the rest.

    Every argument is an observation someone already has or does not have yet. Nothing here
    estimates a missing clinical label, and nothing here treats an engine finding as a
    clinical judgement — the two confusions that would make the whole system theatre.
    """
    axes: dict[str, AxisScore] = {}

    if clinical_labels is None:
        axes["clinical_correctness"] = _null(
            "clinical_correctness",
            "no clinician labels: needs a ratified reference and a second reader (gate G1)",
        )
    else:
        harmful = sum(
            clinical_labels.get(code, 0)
            for code in ("E02", "E07", "E08", "E03", "E04", "E05", "E06")
        )
        axes["clinical_correctness"] = AxisScore(
            name="clinical_correctness",
            value=round(1.0 / (1.0 + harmful), 4),
            scale="0–1, 1 = no clinically consequential label",
            evidence=tuple(f"{code}:{n}" for code, n in sorted(clinical_labels.items())),
            supplied_by="human labels mapped through evidence.taxonomy",
        )

    if structure_coverage is None:
        axes["writing_quality"] = _null("writing_quality", "no parsed draft to score")
    else:
        axes["writing_quality"] = AxisScore(
            name="writing_quality",
            value=round(structure_coverage, 4),
            scale="0–1, share of required sections present and parseable",
            evidence=tuple(sorted(f"check:{f}" for f in engine_findings))
            or ("no engine findings",),
            supplied_by="engine format and structure checks"
            + (" + style-only edit rate" if style_only_edit_rate is not None else ""),
        )

    if review_seconds is None:
        axes["workflow_quality"] = _null(
            "workflow_quality", "no human session: timers and interruption labels are absent"
        )
    else:
        axes["workflow_quality"] = AxisScore(
            name="workflow_quality",
            value=round(review_seconds, 2),
            scale="seconds in review; lower is better only while edits stay substantive",
            evidence=(f"review_seconds={round(review_seconds, 2)}",),
        )

    safety_penalties = [f for f in engine_findings if f in blocking_checks]
    if degradation_unannounced:
        safety_penalties = ["E20", *safety_penalties]
    axes["safety"] = AxisScore(
        name="safety",
        value=0.0
        if degradation_unannounced
        else (1.0 if not safety_penalties else round(1.0 / (1.0 + len(safety_penalties)), 4)),
        scale="0–1, 1 = nothing unsafe reached review; E20 forces the floor",
        evidence=tuple(safety_penalties) or ("no blocking finding",),
        reason_if_null=None,
    )

    if typed_chars is None:
        axes["efficiency"] = _null(
            "efficiency", "no final report to diff against the draft (needs a human session)"
        )
    else:
        axes["efficiency"] = AxisScore(
            name="efficiency",
            value=typed_chars,
            scale="characters the human typed; lower is better *only* beside the "
            "substantive-section count",
            evidence=(f"typed_chars={typed_chars}",),
            supplied_by="evidence.edits.typing_reduction",
        )

    if satisfaction_rating is None:
        axes["user_satisfaction"] = _null(
            "user_satisfaction",
            "not asked; adoption and edit-retention are proxies and are refused as substitutes",
        )
    else:
        axes["user_satisfaction"] = AxisScore(
            name="user_satisfaction",
            value=round(satisfaction_rating, 2),
            scale="1–5 attested by the clinician who used it",
            evidence=("self-reported, attested not verified",),
        )

    return CaseScore(case_id=case_id, skill=skill, axes=axes)
