"""Did this change make anything worse? Four gates, one exit code.

Part 13 of the evidence system, and the item with the highest value-to-effort ratio in it: a
release that cannot answer "is anything worse" turns every improvement into a bet. The gates
are deliberately asymmetric — a candidate must be **non-inferior**, not better, on safety and
workflow, and may be better on efficiency only if it does not buy the gain by making people
stop reading.

**Safety** — endpoints: unannounced degradation, refused faithful drafts, engine blocks
removed. Regression means *any increase, at any n*. A safety regression is not a
percentage, it is an incident with a delay.

**Quality** — clinically consequential error labels per case. Regression means the upper
bootstrap bound of the delta is above 0. Paired, so a case that was already hard stays
hard in both arms.

**Workflow** — review seconds, interruption labels, refusals without a next step.
Regression means a median rise beyond tolerance. Time moved from typing to reading is
fine; time moved to friction is not.

**Productivity** — human typed characters. Regression means a rise while substantive edits
stay flat: the gain that disappears into re-reading is not a gain (FM10).

Two rules that make the verdict mean something:

**Minimum detectable effect is printed with every gate.** A pass on twenty cases often means
"this study could not have detected anything", and stating that is the difference between a
gate and a ritual (`evidence.stats.mde_paired`).

**The baseline must be a real run, and a stub run cannot be compared with a real one.** Mixing
provenance classes is the quietest way to "improve" a metric: replace the model with a stub and
latency falls flat while nothing clinical changed.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from . import stats

#: Relative tolerance for the two gates where small movement is noise, not harm. A quality
#: change of 2% on 40 cases is not evidence; a safety change of any size is.
TOLERANCE = {"workflow": 0.10, "productivity": 0.10}


@dataclass
class GateResult:
    name: str
    passed: bool
    endpoint: str
    baseline: float | None
    candidate: float | None
    delta: float | None
    ci: list[float]
    p_value: float | None
    n_pairs: int
    mde: float | None
    verdict: str
    caution: str

    def as_dict(self) -> dict:
        return self.__dict__ | {"gate": self.name}


@dataclass
class RegressionReport:
    gates: list[GateResult] = field(default_factory=list)
    comparable_pairs: int = 0
    excluded: dict[str, int] = field(default_factory=dict)
    conclusion: str = ""

    @property
    def passed(self) -> bool:
        return all(gate.passed for gate in self.gates) and self.comparable_pairs > 0

    def as_dict(self) -> dict:
        return {
            "passed": self.passed,
            "comparable_pairs": self.comparable_pairs,
            "excluded": dict(self.excluded),
            "conclusion": self.conclusion,
            "gates": [gate.as_dict() for gate in self.gates],
        }


def _paired_values(rows: list[dict], extract: Callable[[dict], Any]) -> list[tuple[float, float]]:
    pairs: list[tuple[float, float]] = []
    for row in rows:
        before, after = extract(row.get("baseline")), extract(row.get("candidate"))
        if isinstance(before, (int, float)) and isinstance(after, (int, float)):
            pairs.append((float(before), float(after)))
    return pairs


def compare(
    paired_rows: list[dict],
    endpoints: dict[str, Callable[[dict], Any]],
    alpha: float = 0.05,
) -> RegressionReport:
    """Run every gate over the same paired cases.

    `paired_rows` is a list of `{"case_ref", "baseline": {...}, "candidate": {...}}`. The
    pairing is the caller's responsibility and is the whole method: two independent samples
    of the same corpus are not a paired design, and pretending otherwise is how a regression
    suite starts reporting improvements that are just case-mix.
    """
    report = RegressionReport()
    for name, extract in endpoints.items():
        pairs = _paired_values(paired_rows, extract)
        n = len(pairs)
        if n < 2:
            report.gates.append(
                GateResult(
                    name=name,
                    passed=False,
                    endpoint=getattr(extract, "endpoint", name),
                    baseline=None,
                    candidate=None,
                    delta=None,
                    ci=[],
                    p_value=None,
                    n_pairs=n,
                    mde=None,
                    verdict="inconclusive: fewer than two paired observations",
                    caution="an inconclusive safety gate blocks a release; it does not clear one",
                )
            )
            continue
        deltas = [after - before for before, after in pairs]
        boot = stats.bootstrap_paired(deltas, alpha=alpha)
        estimate = boot.estimate
        baseline_mean = stats.mean([b for b, _ in pairs])
        candidate_mean = stats.mean([a for _, a in pairs])
        report.comparable_pairs = max(report.comparable_pairs, n)
        passed = _gate_verdict(name, estimate, boot.ci_high, baseline_mean)
        report.gates.append(
            GateResult(
                name=name,
                passed=passed,
                endpoint=getattr(extract, "endpoint", name),
                baseline=round(baseline_mean, 4),
                candidate=round(candidate_mean, 4),
                delta=round(estimate, 4) if estimate is not None else None,
                ci=[round(boot.ci_low, 4), round(boot.ci_high, 4)],
                p_value=None,
                n_pairs=n,
                mde=round(stats.mde_paired(n).estimate or 0.0, 4),
                verdict="non-inferior"
                if passed
                else "regression or underpowered — treat as regression",
                caution=(
                    f"this n can only detect a standardised effect of about "
                    f"{round(stats.mde_paired(n).estimate or 0.0, 2)}; "
                    "smaller real harm is invisible here, so 'passed' is not 'no harm'"
                ),
            )
        )
    report.excluded["rows_without_a_pair_for_any_endpoint"] = (
        len(paired_rows) - report.comparable_pairs
    )
    if not report.gates:
        report.conclusion = "no endpoints given: the gate ran and proved nothing"
    elif report.passed:
        report.conclusion = (
            f"non-inferior on {len(report.gates)} gates over {report.comparable_pairs} "
            "paired cases, within the power stated on each row"
        )
    else:
        failed = [gate.name for gate in report.gates if not gate.passed]
        report.conclusion = f"blocked at: {', '.join(failed)}"
    return report


def _gate_verdict(
    name: str, delta: float | None, ci_high: float | None, baseline_mean: float | None
) -> bool:
    """Safety and quality must not get worse; workflow and productivity get a *relative* tolerance.

    An absolute tolerance on seconds is meaningless — one second of review is nothing on a
    nine-minute report and everything on a nine-second one — so the tolerance is a share of the
    baseline. Safety and quality get no tolerance at all, because "worse but within 10%" is not
    a sentence anyone wants to read in a release note.
    """
    if delta is None or ci_high is None:
        return False
    if name in ("safety", "quality"):
        return ci_high <= 0.0
    tolerance = TOLERANCE.get(name, 0.10)
    if baseline_mean:
        return ci_high <= tolerance * abs(baseline_mean)
    return ci_high <= tolerance


def endpoint(name: str, key: str) -> Callable[[dict], Any]:
    """A named extractor, so a gate's endpoint is written once and quoted by name.

    The name travels on the function because a regression report that says "gate 3 failed"
    is not a decision-support artefact; one that says `review_seconds` is.
    """

    def extract(row: Any) -> Any:
        if row is None:
            return None
        return row.get(key)

    extract.endpoint = name  # type: ignore[attr-defined]
    return extract


DEFAULT_ENDPOINTS: dict[str, Callable[[dict], Any]] = {
    "safety": endpoint("refusal rate on faithful drafts", "faithful_refusals"),
    "quality": endpoint("clinically consequential labels per case", "harmful_labels"),
    "workflow": endpoint("review seconds", "review_seconds"),
    "productivity": endpoint("characters typed by the human", "typed_chars"),
}
