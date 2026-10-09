"""The canonical error taxonomy: one code per kind of thing that can go wrong.

Why this file exists before any other measurement. A bug report that says "the impression
was wrong" cannot be counted, trended, or assigned an owner; a bug labelled `E07` can be
all three. The taxonomy is the join key between clinical reality and every number in this
system, so it is written first and versioned (`evidence.__init__.TAXONOMY_VERSION`).

Three rules, each testable:

1. **Every code names an observable.** If nothing could decide whether a case carries the
   code, the code is decoration and does not ship. `definition` is written so that two
   readers given the same report would answer the same way — and `inter_reader` records how
   close that claim actually is when it is tested.
2. **Every code has a detector, even when the detector is a human.** `detected_by` is
   `engine`, `human` or `both`. The ratio is the platform's honesty metric: engine coverage
   over the classes that matter most is low, and a system that reports a detection rate
   without that denominator is the thing `docs/FAILURE-MODES.md` FM4 describes.
3. **`E99` is a defect signal, not a dump.** A label landing on `E99` means the taxonomy is
   wrong. If `E99` exceeds a few percent of labels in any period, the taxonomy — not the
   model — is what needs the release.

Namespace: `E`. `F` already means workflow break in `docs/clinical/HOSPITAL_WORKFLOW.md`,
`S` safety register in `docs/safety/CLINICAL_SAFETY.md`, `D` debt rows, `FM` failure modes,
`N`/`M` invariants, `G` entry gates. One prefix, one meaning —
`docs/DOMAIN_MODEL.md` owns the register.
"""

from __future__ import annotations

from dataclasses import dataclass

Engine = str  # "engine" | "human" | "both"


@dataclass(frozen=True)
class ErrorClass:
    code: str
    name: str
    group: str
    definition: str
    detected_by: Engine
    #: Quality-check ids from `futurekind_radiology.quality` that fire on this class.
    #: Empty means the engine is blind here — which is a measurement target, not a gap to hide.
    engine_checks: tuple[str, ...]
    #: Where a fix belongs. `model` is deliberately rare: the platform can change a prompt,
    #: a check, a screen, a policy or a workflow, and it can swap what runs behind an alias,
    #: but "the model is wrong" is not an action someone here can take.
    fix_target: str
    #: The default severity *for the record*, not for the product's gate. `label` means the
    #: class is descriptive; only engine checks block, and blocking is owned by
    #: `apps/radiology_copilot/src/futurekind_radiology/quality.py`.
    default_severity: str
    #: How the class is observed, in one phrase a reviewer can apply without a meeting.
    observable: str
    #: Set once inter-reader agreement has actually been measured. None means never tested.
    inter_reader: float | None = None


def _c(
    code: str,
    name: str,
    group: str,
    definition: str,
    detected_by: Engine,
    engine_checks: tuple[str, ...],
    fix_target: str,
    default_severity: str,
    observable: str,
) -> ErrorClass:
    return ErrorClass(
        code,
        name,
        group,
        definition,
        detected_by,
        engine_checks,
        fix_target,
        default_severity,
        observable,
    )


CLASSES: tuple[ErrorClass, ...] = (
    # ---------------------------------------------------------------- content: what the report says
    _c(
        "E01",
        "missing_finding",
        "content",
        "A finding the reference answer or the source document contains is absent from the draft.",
        "both",
        ("dropped_observation", "structure_coverage"),
        "prompt",
        "label",
        "diff against the reference, then a human confirms the absence is clinical, not stylistic",
    ),
    _c(
        "E02",
        "invented_finding",
        "content",
        "Content asserted that the submitted input does not support and does not contradict.",
        "human",
        (),
        "check",
        "label",
        "a reviewer states which submitted line they looked for and did not find",
    ),
    _c(
        "E03",
        "wrong_measurement",
        "content",
        "A number or unit that is present in the input but transcribed or computed incorrectly.",
        "both",
        ("unsupported_measurement",),
        "screen",
        "label",
        "compare each value against the source measurement, not against the draft's own text",
    ),
    _c(
        "E04",
        "wrong_laterality",
        "content",
        "Left/right/upper/lower reversed or dropped where the input specifies it.",
        "human",
        (),
        "prompt",
        "label",
        "read every side word in the draft against the dictation",
    ),
    _c(
        "E05",
        "wrong_anatomy",
        "content",
        "A structure is named that the study cannot show, or a named structure is the wrong one.",
        "human",
        (),
        "prompt",
        "label",
        "does the modality and protocol in the request make this structure visible?",
    ),
    _c(
        "E06",
        "wrong_chronology",
        "content",
        "Acute/chronic/interval-change is asserted without the comparison the claim needs.",
        "both",
        ("invented_history",),
        "check",
        "label",
        "is there a prior study named in the input for every temporal claim?",
    ),
    _c(
        "E07",
        "unsupported_diagnosis",
        "content",
        "A diagnostic conclusion stated with more certainty than the findings carry.",
        "both",
        ("unsupported_certainty",),
        "prompt",
        "label",
        "could the stated conclusion be wrong while every finding above it stays true?",
    ),
    _c(
        "E08",
        "unsafe_recommendation",
        "content",
        "Advice that would cause harm if followed, or that omits the action a guideline requires.",
        "human",
        (),
        "policy",
        "label",
        "a clinician decides; this is the one class where the label cannot be delegated to text",
    ),
    _c(
        "E09",
        "missing_followup",
        "content",
        "A surveillance or follow-up interval the reference answer states is absent or unstated.",
        "both",
        ("structure_coverage",),
        "screen",
        "label",
        "is there an interval a reader could act on, and is it the recommended one?",
    ),
    _c(
        "E10",
        "model_confidence_as_evidence",
        "content",
        "The model's own certainty, or any self-asserted reliability, used as if it were evidence.",
        "engine",
        ("self_reported_confidence",),
        "prompt",
        "block",
        "does any number in the output trace to the model describing itself?",
    ),
    _c(
        "E11",
        "invented_identifier",
        "content",
        "A name, hospital number or accession-like token appears that the submission "
        "never contained.",
        "engine",
        ("invented_identifier",),
        "check",
        "block",
        "every identifier-shaped string in the draft, matched against the submitted set",
    ),
    _c(
        "E12",
        "unsupported_negative",
        "content",
        'An absence is asserted ("no X") where the input neither supports nor rules it out.',
        "engine",
        ("unsupported_absence",),
        "check",
        "advisory",
        "each negation traced to a line of the dictation or a stated limitation",
    ),
    # ---------------------------------------------------------------- form: how it is written
    _c(
        "E13",
        "format_breach",
        "form",
        "Sections, order, labels or the AI watermark are not what the department's "
        "format requires.",
        "engine",
        ("format_breach", "structure_coverage"),
        "screen",
        "block",
        "parse the draft against the section tuple, and check the watermark is present",
    ),
    _c(
        "E14",
        "truncated",
        "form",
        "The answer stopped because the token budget ran out, so a section is incomplete.",
        "engine",
        (),
        "policy",
        "block",
        "`finish_reason == length`; the check belongs to transport, not to the prose",
    ),
    _c(
        "E15",
        "style_or_readability",
        "form",
        "Clinically true, but phrased so a reader slows down: hedging, duplication, "
        "sentence length.",
        "human",
        (),
        "prompt",
        "label",
        "a reader marks the sentence they had to re-read",
    ),
    # ---------------------------------------------------------------- process: the work
    _c(
        "E16",
        "false_alert",
        "process",
        "The gate blocked or warned on a draft a clinician judged correct.",
        "both",
        (),
        "check",
        "label",
        "count of refusals on faithful drafts; the golden audit already measures this shape",
    ),
    _c(
        "E17",
        "missed_alert",
        "process",
        "A real problem reached review without any flag, and a human caught it.",
        "human",
        (),
        "check",
        "label",
        "`run-cases.py`'s paired oracle: content deleted by a reviewer from a section "
        "the engine left alone",
    ),
    _c(
        "E18",
        "workflow_interruption",
        "process",
        "The tool cost time or attention it did not need to: repeated confirmation, "
        "lost focus, dead ends.",
        "human",
        (),
        "screen",
        "label",
        "observed in the session: seconds in a state that produced no work",
    ),
    _c(
        "E19",
        "unactionable_refusal",
        "process",
        "The system said no without saying what to do instead.",
        "both",
        (),
        "screen",
        "label",
        "could the reader state the next action from the message alone?",
    ),
    _c(
        "E20",
        "degradation_unannounced",
        "process",
        "A lesser class answered where a promised class was required, and the output "
        "did not say so.",
        "engine",
        (),
        "policy",
        "block",
        "`degraded == true` with no reader-visible statement; P13 makes this the "
        "platform's worst class",
    ),
    _c(
        "E21",
        "unavailable",
        "process",
        "The AI path failed and the workflow continued without it; nothing was claimed "
        "to be drafted.",
        "both",
        (),
        "workflow",
        "label",
        "transport outcome `no_result`; correct behaviour, still a workflow fact worth counting",
    ),
    # ---------------------------------------------------------------- evidence: the measurement
    _c(
        "E22",
        "unattributable",
        "evidence",
        "An act occurred that cannot be assigned to a named person.",
        "both",
        (),
        "policy",
        "label",
        "no per-person credential exists yet, so tonight this class is uncountable by design",
    ),
    _c(
        "E23",
        "unretained",
        "evidence",
        "A record that should have survived did not, so a later question is unanswerable.",
        "both",
        (),
        "workflow",
        "label",
        "the conformance question that cannot be answered two years later; ADR-0003 is its blocker",
    ),
    _c(
        "E24",
        "unmeasurable_claim",
        "evidence",
        "A number was reported without its instrument, denominator, or the fact that "
        "the input was synthetic.",
        "both",
        (),
        "workflow",
        "block",
        "the paired-delta rule: if the baseline is not stated, the rate is not a measurement",
    ),
    _c(
        "E25",
        "misclassified_label",
        "evidence",
        "The taxonomy was applied wrongly, including by this system's own mapping.",
        "human",
        (),
        "workflow",
        "label",
        "a second reader disagrees with the first; measured by inter-reader agreement, not assumed",
    ),
    _c(
        "E99",
        "unclassified",
        "evidence",
        "No class above describes what happened.",
        "human",
        (),
        "workflow",
        "label",
        "a rate above a few percent is a defect in this file, not in the product",
    ),
)

BY_CODE: dict[str, ErrorClass] = {c.code: c for c in CLASSES}
GROUPS: tuple[str, ...] = ("content", "form", "process", "evidence")

#: The nine engine checks the copilot ships today, read from
#: `apps/radiology_copilot/src/futurekind_radiology/quality.py`. Held here as a set so the
#: consistency test below can fail when the product adds a check and this file does not know
#: about it — a two-authority defect in the making (`docs/CONCEPTUAL_DEBT.md` D6).
ENGINE_CHECK_IDS: frozenset[str] = frozenset(
    {
        "dropped_observation",
        "unsupported_measurement",
        "invented_history",
        "unsupported_certainty",
        "format_breach",
        "invented_identifier",
        "self_reported_confidence",
        "unsupported_absence",
        "structure_coverage",
    }
)


def code(c: str) -> ErrorClass:
    try:
        return BY_CODE[c]
    except KeyError as exc:  # a wrong code in a label is an error, not a default
        raise KeyError(f"unknown error code {c!r}; {len(BY_CODE)} codes are defined") from exc


def engine_coverage() -> dict[str, float | int]:
    """How much of the taxonomy the deterministic engine can see at all.

    This is deliberately a published number rather than a private one. The platform's
    hallucination-detection claim is a claim about E02, E03, E07 and E08 — the classes an
    engine is mostly blind to — and a detection rate quoted without this denominator is the
    defect `docs/FAILURE-MODES.md` FM4 names.
    """
    total = len(CLASSES)
    with_engine = sum(1 for c in CLASSES if c.engine_checks)
    content = [c for c in CLASSES if c.group == "content"]
    content_with_engine = sum(1 for c in content if c.engine_checks)
    human_only = sum(1 for c in CLASSES if c.detected_by == "human")
    return {
        "classes": total,
        "with_engine_detector": with_engine,
        "engine_coverage": round(with_engine / total, 3),
        "content_classes": len(content),
        "content_with_engine_detector": content_with_engine,
        "content_engine_coverage": round(content_with_engine / len(content), 3),
        "human_only_classes": human_only,
    }


def unmapped_engine_checks() -> set[str]:
    """Engine checks the product runs that no error class claims responsibility for."""
    claimed = {chk for c in CLASSES for chk in c.engine_checks}
    return ENGINE_CHECK_IDS - claimed


def unknown_engine_checks() -> set[str]:
    """Codes citing a check the product does not have. Fails loudly, unlike a stale count."""
    claimed = {chk for c in CLASSES for chk in c.engine_checks}
    return claimed - ENGINE_CHECK_IDS
