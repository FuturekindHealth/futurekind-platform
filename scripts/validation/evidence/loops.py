"""The improvement loops: human edits and human overrides, turned into proposals.

Parts 6 and 7 of the evidence system. Both loops have the same shape — observe, classify,
aggregate, rank, propose, revalidate — and both have the same failure mode in the wild: the
loop that closes itself. Auto-optimising a prompt from edit statistics is how a system
drifts toward what is easy to write rather than what is safe to sign, and the platform has
already decided that this is not allowed:

> **No automatic optimisation of a clinical parameter.** `docs/INVARIANTS.md` N14,
> `docs/CONSTITUTION.md` P13, and the validation dashboard's own authority ceiling:
> "no metric can nudge a draft, a prompt or a policy."

So every function here ends at a *proposal object* with evidence attached, and `apply()`
raises. That is not a stub of unfinished work; it is the design. A human reads the proposal,
edits the prompt or the check, and the loop's last stage — revalidation against the frozen
corpus — is what they then have to pass. The spreadsheet this replaces is the one where
someone ranks "bad outputs" by memory at 21:00.

What the loop can and cannot see tonight: the edit side needs a human session, and there has
never been one. The override side is measurable today — the golden audit already pairs
mutations against faithful drafts — so the loop's check half has a working input and its
prompt half has a schema waiting for data. Stated as such rather than demoed with fake rows.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from . import taxonomy


class AutoApplyError(RuntimeError):
    """Raised by anything that tries to close the loop without a human."""


def _rank_key(item: ImprovementProposal) -> tuple[float, int, str]:
    """Harm weight first, then frequency, then the identifier so ties are reproducible."""
    return (-item.harm_weight, -item.count, item.identifier)


@dataclass
class ImprovementProposal:
    identifier: str
    kind: str  # "prompt" | "check"
    observation: str
    error_codes: tuple[str, ...]
    count: int
    cases: tuple[str, ...]
    harm_weight: float
    proposed_change: str
    validation: str
    #: A proposal that cannot be revalidated on the current corpus is worth less than one
    #: that can, and saying so is the difference between a queue and a graveyard.
    revalidatable: bool
    status: str = "proposal"
    decided_by: str = ""
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "identifier": self.identifier,
            "kind": self.kind,
            "observation": self.observation,
            "error_codes": list(self.error_codes),
            "count": self.count,
            "cases": list(self.cases),
            "harm_weight": round(self.harm_weight, 3),
            "proposed_change": self.proposed_change,
            "validation": self.validation,
            "revalidatable": self.revalidatable,
            "status": self.status,
            "decided_by": self.decided_by,
            "notes": list(self.notes),
        }


def apply(*_args: Any, **_kwargs: Any) -> None:
    """The line the loop is not allowed to cross, made executable."""
    raise AutoApplyError(
        "prompts, checks, severities and thresholds change by a commit a person writes. "
        "This module stops at the proposal (docs/INVARIANTS.md N14, docs/CONSTITUTION.md P13)."
    )


#: Harm weighting for the ranking step: a repeated cosmetic problem is a big number and a
#: small deal; a rare unsafe recommendation is the reverse. Weights are published here so the
#: ranking can be argued about as data rather than as a mood.
HARM_WEIGHTS: dict[str, float] = {
    "E08": 8.0,
    "E02": 7.0,
    "E07": 6.0,
    "E03": 6.0,
    "E04": 6.0,
    "E05": 6.0,
    "E06": 5.0,
    "E20": 9.0,
    "E01": 4.0,
    "E09": 4.0,
    "E12": 3.0,
    "E17": 8.0,
    "E16": 3.0,
    "E19": 2.0,
    "E18": 2.0,
    "E13": 1.5,
    "E15": 1.0,
    "E14": 2.0,
    "E24": 5.0,
    "E25": 3.0,
    "E22": 6.0,
    "E23": 6.0,
    "E21": 1.0,
    "E10": 4.0,
    "E11": 5.0,
    "E99": 1.0,
}


def rank_harm(codes: Iterable[str]) -> float:
    """Total harm weight of a group of labels.

    Used when the *volume* of a pattern matters (a quality committee asking how many events
    reached patients this quarter).
    """
    total = 0.0
    for code in codes:
        total += HARM_WEIGHTS.get(code, HARM_WEIGHTS["E99"])
    return total


def mean_harm(codes: Iterable[str]) -> float:
    """Harm per event — the number that decides which proposal someone reads first.

    Ranking on the total is the mistake this function exists to prevent: forty cosmetic edits
    would outrank two unsafe recommendations, which is precisely the ordering that lets the
    dangerous thing wait a quarter. Volume breaks the tie, underneath it.
    """
    values = list(codes)
    return rank_harm(values) / len(values) if values else 0.0


def classify_edit_events(records: list[dict]) -> list[dict[str, Any]]:
    """Turn stored session records into edit events, with a suggested error class.

    Reads `evidence.edits` output from the session record; the suggestion is a *hint* for a
    human label, never a label. A machine that assigns E02 from a deletion is the
    self-grading homework `docs/safety/CLINICAL_SAFETY.md` §5 forbids — but it can order the
    pile so the dangerous-looking stuff reaches a person first.
    """
    events: list[dict[str, Any]] = []
    for record in records:
        edit = record.get("edit", {}) or {}
        for section in edit.get("per_section", []) or []:
            if section.get("unchanged") or not section.get("blocks"):
                continue
            reasons = tuple(section.get("reasons") or ())
            suggested: list[str] = []
            if "measurement_changed" in reasons:
                suggested.append("E03")
            if "side_changed" in reasons:
                suggested.append("E04")
            if "negation_changed" in reasons or "negation_scope_extended" in reasons:
                suggested.append("E12")
            if "assertion_changed" in reasons:
                suggested.append("E07")
            if not section.get("substantive"):
                suggested.append("E15")
            events.append(
                {
                    "case_ref": record.get("case_ref", ""),
                    "section": section.get("section", ""),
                    "substantive": bool(section.get("substantive")),
                    "chars_removed": section.get("chars_removed", 0),
                    "chars_inserted": section.get("chars_inserted", 0),
                    "suggested_codes": suggested,
                    "reasons": list(reasons),
                    "needs_human_label": True,
                    "prompt_version": record.get("provenance", {}).get("prompt_version", ""),
                }
            )
    return events


def prompt_proposals(events: list[dict], min_count: int = 3) -> list[ImprovementProposal]:
    """Aggregate edit events into the prompt changes worth reading.

    Grouping is by (section, suggested class, reason signature) rather than by free text:
    the shape of an edit is what a prompt author can act on, and a group of 12 deletions in
    `impression` with an assertion change is a different instruction from 12 deletions in
    `technique`.
    """
    grouped: dict[tuple[str, str, tuple[str, ...]], list[dict]] = defaultdict(list)
    for event in events:
        for code in event["suggested_codes"] or ["E99"]:
            grouped[(event["section"], code, tuple(sorted(event["reasons"])))].append(event)
    proposals: list[ImprovementProposal] = []
    for (section, code, reasons), items in grouped.items():
        if len(items) < min_count:
            continue
        cases = tuple(sorted({item["case_ref"] for item in items}))
        proposals.append(
            ImprovementProposal(
                identifier=f"P-{section}-{code}",
                kind="prompt",
                observation=(
                    f"{len(items)} human edits in `{section}` suggesting {code}; "
                    f"reasons: {', '.join(reasons) if reasons else 'style-only under this rule'}"
                ),
                error_codes=(code,),
                count=len(items),
                cases=cases,
                harm_weight=mean_harm([code] * len(items)),
                proposed_change=(
                    f"review the `{section}` instruction in the running prompt against "
                    "`docs/safety/CLINICAL_SAFETY.md` §4 obligations; a clause change is "
                    "a minor bump, and any relaxed prohibition is a major bump plus an ADR"
                ),
                validation=(
                    "re-run the frozen corpus: substantive-edit rate for this section must "
                    "fall while blocking findings do not rise, on the same case mix"
                ),
                revalidatable=bool(cases),
                notes=["suggested codes are hints for a human label, not labels"],
            )
        )
    return sorted(proposals, key=_rank_key)


def override_events(audit_rows: list[dict]) -> list[dict[str, Any]]:
    """From the golden audit's output: a correct report the engine objected to, and vice versa.

    `audit_rows` is the paired result set from `scripts/validation/audit-checks.py`: one entry
    per (case, mutation) with the baseline's firing set beside the mutated one. Both
    directions matter, and they are opposite defects: a false block teaches the department to
    distrust the gate, a missed probe teaches the team to overstate it.
    """
    events: list[dict[str, Any]] = []
    for row in audit_rows:
        if row.get("false_block_on_faithful"):
            events.append(
                {
                    "kind": "false_positive",
                    "check": row.get("check", ""),
                    "case_ref": row.get("case_id", ""),
                    "codes": ("E16",),
                    "detail": row.get("detail", ""),
                }
            )
        if row.get("probe_missed"):
            events.append(
                {
                    "kind": "missed",
                    "check": row.get("check", ""),
                    "case_ref": row.get("case_id", ""),
                    "codes": ("E17",),
                    "detail": row.get("probe", ""),
                }
            )
    return events


def check_proposals(events: list[dict], min_count: int = 2) -> list[ImprovementProposal]:
    """Rank deterministic-check work, using the cost the audit already measured.

    The rule that keeps this honest: a proposal to *loosen* a check must show the detection
    it would give up, and a proposal to tighten must show the false blocks it would add. One
    side alone is the mistake that made `dropped_observation` block 87 of 100 correct reports.
    """
    counts = Counter((event["kind"], event["check"]) for event in events)
    proposals: list[ImprovementProposal] = []
    for (kind, check), count in counts.items():
        if count < min_count or not check:
            continue
        code = "E16" if kind == "false_positive" else "E17"
        cases = tuple(
            sorted(
                {
                    event["case_ref"]
                    for event in events
                    if event["check"] == check and event["kind"] == kind
                }
            )
        )
        proposals.append(
            ImprovementProposal(
                identifier=f"C-{check}-{kind}",
                kind="check",
                observation=f"{check}: {count} {kind.replace('_', ' ')} events",
                error_codes=(code,),
                count=count,
                cases=cases,
                harm_weight=mean_harm([code] * count),
                proposed_change=(
                    "adjust the rule's scope, not its severity: severity is set by measured cost "
                    "(docs/product/PROMPT_LIBRARY.md §9)"
                    if kind == "false_positive"
                    else (
                        "add a deterministic signal for this pattern, "
                        "then pair it against the faithful corpus"
                    )
                ),
                validation=(
                    "paired re-run over all 100 cases: newly blocked probes on one side, "
                    "newly blocked correct reports on the other, both reported — "
                    "one of them alone is a marketing number"
                ),
                revalidatable=True,
                notes=[
                    "a check's default_severity in evidence.taxonomy describes how the label "
                    "reads, not whether the product blocks; blocking is owned by quality.py"
                ],
            )
        )
    return sorted(proposals, key=_rank_key)


def loop_state() -> dict[str, Any]:
    """What each half of the loop can actually do today. Written to be re-run, not remembered."""
    return {
        "prompt_loop": {
            "input": "human session edit events",
            "available": False,
            "why_not": "no clinician session has ever been recorded",
            "first_step": "run-cases.py session over 20 cases with one reporter, outside the tree",
        },
        "check_loop": {
            "input": "paired golden audit",
            "available": True,
            "measured": "9 checks, 100 faithful drafts, 310 probes",
            "known_cost": (
                "detection is 3 of 306 measurable probes, and one faithful report still "
                "blocks (E-03); see docs/product/ROADMAP.md table 4"
            ),
            "guard": "proposals only — apply() raises (N14)",
        },
        "taxonomy": taxonomy.engine_coverage(),
    }
