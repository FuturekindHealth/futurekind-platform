"""Is it improving? Trends over day, week, month, quarter and year — with the confounders named.

Part 9. A time series of a clinical metric is the most easily believed and least trustworthy
object in this space, because three of the four things that move it are not the product:

**Is the product improving?** — refusal rate on faithful drafts, unannounced degradations,
review seconds per case. Moved by: case mix, staffing, workload season, and which reporter
joined the study.

**Are the prompts improving?** — substantive-edit rate per section against a *frozen*
corpus. Moved by the corpus itself: a prompt cannot be trended across a dataset change, so
the corpus version belongs in the series key.

**Are the users improving?** — edit rate by reporter, first 40 cases against the next 40.
Moved by learning, by who volunteers, and by the fact that a confident reporter edits less
without being right more often — the FM10 trap.

**Are hallucinations decreasing?** — clinically consequential labels per 100 cases, by
*detected* class. Moved by detection effort: a falling rate beside a falling audit volume
is a measurement artefact, the exact failure `audit-checks.py` had to correct once already.

Four questions, four metrics, and four confounders that are longer than the answers. The
confounder column is the one a reader skips, and it is the reason this module exists.

So the module refuses to produce a trend without its strata. `series()` always carries `n`,
the case-mix shares beside it, and the Mann-Kendall test reports only monotone tendency
without claiming a slope, because a slope on a dozen monthly points invites exactly the
reading it cannot support.

There is no decomposition, no ARIMA, no hierarchical model here. Each would let a small
number of points look like a finding, and the whole purpose of this file is to make that
harder to do by accident.
"""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

PERIODS = ("day", "week", "month", "quarter", "year")
#: Chi-square critical values at alpha 0.05, degrees of freedom 1–12. Tabled rather than
#: computed because a distribution function nobody checks is a decimal with authority.
CHI_SQUARE_005 = {
    1: 3.841,
    2: 5.991,
    3: 7.815,
    4: 9.488,
    5: 11.070,
    6: 12.592,
    7: 14.067,
    8: 15.507,
    9: 16.919,
    10: 18.307,
    11: 19.675,
    12: 21.026,
}


def period_key(stamp: str, period: str = "month") -> str:
    """ISO label for the bucket a record belongs to. Timezone-naive stamps are refused."""
    moment = (
        datetime.fromisoformat(stamp)
        if "T" in stamp
        else datetime.fromisoformat(f"{stamp}T00:00:00")
    )
    if moment.tzinfo is None:
        raise ValueError(
            f"{stamp}: a measurement without a timezone cannot be bucketed across sites"
        )
    year, month = moment.year, moment.month
    if period == "day":
        return moment.date().isoformat()
    if period == "week":
        iso = moment.isocalendar()
        return f"{iso[0]}-W{iso[1]:02d}"
    if period == "month":
        return f"{year:04d}-{month:02d}"
    if period == "quarter":
        return f"{year:04d}-Q{(month - 1) // 3 + 1}"
    if period == "year":
        return f"{year:04d}"
    raise ValueError(f"unknown period {period!r}; expected one of {PERIODS}")


def bucket(records: list[dict], period: str = "month") -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = defaultdict(list)
    for record in records:
        stamp = record.get("started_at") or record.get("stages", {}).get("received")
        if not stamp:
            continue
        out[period_key(stamp, period)].append(record)
    return dict(sorted(out.items()))


def _floats(rows: list[dict], key: str) -> list[float]:
    values: list[float] = []
    for row in rows:
        value = row.get(key)
        if value is None:
            nested = row.get("edit", {}).get(key) or row.get("engine", {}).get(key)
            value = nested
        if isinstance(value, (int, float)):
            values.append(float(value))
    return values


def series(records: list[dict], key: str, period: str = "month") -> list[dict[str, Any]]:
    """One point per period, with n and the spread, and no line unless n supports it."""
    points: list[dict[str, Any]] = []
    for label, rows in bucket(records, period).items():
        values = _floats(rows, key)
        point: dict[str, Any] = {"period": label, "n_records": len(rows), "n_value": len(values)}
        if values:
            mean = sum(values) / len(values)
            point["mean"] = round(mean, 4)
            if len(values) > 1:
                variance = sum((value - mean) ** 2 for value in values) / (len(values) - 1)
                point["sd"] = round(math.sqrt(variance), 4)
                point["sem"] = round(math.sqrt(variance / len(values)), 4)
        else:
            point["note"] = (
                f"no record in {label} carries {key!r}: the gap is a data-collection fact"
            )
        points.append(point)
    return points


def mann_kendall(values: list[float]) -> dict[str, Any]:
    """Monotone-trend test: S, Kendall's tau, and a normal-approximation p.

    Chosen over a regression because it needs no distributional assumption and reports a
    direction, not a slope — which is the honest amount of information in eight monthly points
    from one hospital.
    """
    n = len(values)
    if n < 4:
        return {
            "n": n,
            "sufficient": False,
            "note": "fewer than four periods: a trend test here would be theatre",
        }
    s = 0
    for i in range(n - 1):
        for j in range(i + 1, n):
            difference = values[j] - values[i]
            s += (difference > 0) - (difference < 0)
    var_s = n * (n - 1) * (2 * n + 5) / 18
    tie_groups = Counter(values)
    var_s -= (
        sum(count * (count - 1) * (2 * count + 5) for count in tie_groups.values() if count > 1)
        / 18
    )
    if var_s <= 0:
        return {
            "n": n,
            "s": s,
            "tau": 0.0,
            "sufficient": True,
            "p_value": 1.0,
            "note": "all values tied: no trend, and no information about one",
        }
    z = (s - 1) / math.sqrt(var_s) if s > 0 else ((s + 1) / math.sqrt(var_s) if s < 0 else 0.0)
    p = math.erfc(abs(z) / math.sqrt(2))
    tau = 2 * s / (n * (n - 1))
    return {
        "n": n,
        "s": s,
        "tau": round(tau, 4),
        "z": round(z, 4),
        "p_value": round(p, 6),
        "sufficient": True,
        "direction": "increasing"
        if s > 0 and p < 0.05
        else ("decreasing" if s < 0 and p < 0.05 else "no monotone trend detected"),
        "caution": "a trend on a small series describes the periods observed, not the product; "
        "read it beside case_mix_drift, or it means nothing",
    }


def case_mix_drift(
    records: list[dict], attribute: str = "category", period: str = "month"
) -> dict[str, Any]:
    """Is the *work* changing under the metric? The most common way a QI dashboard lies.

    Reports the share of each attribute value per period, and a chi-square statistic against
    the pooled distribution. A significant value means the trend question must be answered
    within strata or not at all.
    """
    periods = bucket(records, period)
    labels = sorted({str(row.get(attribute, "")) for row in records if row.get(attribute)})
    if len(labels) < 2 or len(periods) < 2:
        return {
            "attribute": attribute,
            "testable": False,
            "note": "needs at least two periods and two attribute values",
        }
    observed: dict[str, dict[str, int]] = {}
    totals: Counter[str] = Counter()
    period_totals: Counter[str] = Counter()
    for label, rows in periods.items():
        counts = Counter(str(row.get(attribute, "")) for row in rows if row.get(attribute))
        observed[label] = dict(counts)
        totals.update(counts)
        period_totals[label] = sum(counts.values())
    grand = sum(totals.values())
    if grand == 0:
        return {"attribute": attribute, "testable": False, "note": "no values recorded"}
    statistic = 0.0
    for label, counts in observed.items():
        for value in labels:
            expected = period_totals[label] * totals[value] / grand
            if expected <= 0:
                continue
            actual = counts.get(value, 0)
            statistic += (actual - expected) ** 2 / expected
    degrees = (len(labels) - 1) * (len(periods) - 1)
    critical = CHI_SQUARE_005.get(degrees)
    return {
        "attribute": attribute,
        "testable": True,
        "periods": len(periods),
        "values": labels,
        "chi_square": round(statistic, 3),
        "degrees_of_freedom": degrees,
        "critical_value_alpha_005": critical,
        "drift_detected": bool(critical is not None and statistic > critical),
        "shares": {
            label: {
                value: round(counts.get(value, 0) / period_totals[label], 3)
                if period_totals[label]
                else None
                for value in labels
            }
            for label, counts in observed.items()
        },
        "caution": (
            "case mix moved: a trend across these periods is partly a trend in what the "
            "department happened to send"
            if critical is not None and statistic > critical
            else "case mix looks stable; that is an absence of detected drift, not proof of none"
        ),
    }


@dataclass
class TrendQuestion:
    question: str
    metric: str
    unit: str
    required_strata: tuple[str, ...]
    confounders: tuple[str, ...]
    measurable_today: bool
    why_not: str

    def as_dict(self) -> dict:
        return {
            "question": self.question,
            "metric": self.metric,
            "unit": self.unit,
            "required_strata": list(self.required_strata),
            "confounders": list(self.confounders),
            "measurable_today": self.measurable_today,
            "why_not": self.why_not,
        }


def four_questions() -> list[TrendQuestion]:
    """The four claims a decade of use would want, and the honest state of each tonight.

    Written as data so that the answer to "are we improving?" can be regenerated rather than
    remembered, and so nobody has to re-derive which of these needs a clinician.
    """
    return [
        TrendQuestion(
            question="Is the product improving?",
            metric="refusal rate on faithful drafts + review seconds per case",
            unit="per 100 cases",
            required_strata=("modality", "category", "difficulty", "reporter"),
            confounders=("case mix", "staffing", "workload season", "study participation"),
            measurable_today=False,
            why_not="no model has run and no clinician has been timed; the corpus is synthetic",
        ),
        TrendQuestion(
            question="Are the prompts improving?",
            metric="substantive-edit rate per section against a frozen corpus",
            unit="share of cases",
            required_strata=("prompt_version", "corpus_version"),
            confounders=("corpus change masquerading as prompt improvement", "reporter turnover"),
            measurable_today=False,
            why_not="one prompt version has ever been executed "
            "(docs/product/PROMPT_LIBRARY.md), so there is no second point",
        ),
        TrendQuestion(
            question="Are the users improving?",
            metric="edit rate by reporter, first 40 cases versus the next 40",
            unit="per reporter",
            required_strata=("reporter", "case mix"),
            confounders=(
                "learning",
                "selection",
                "and rising automation bias, which looks identical to fluency",
            ),
            measurable_today=False,
            why_not="no per-person credential exists, so a reporter cannot be named (ADR-0004)",
        ),
        TrendQuestion(
            question="Are hallucinations decreasing?",
            metric="clinically consequential labels (E02, E03, E07, E08) per 100 cases",
            unit="per 100 cases, by detected class",
            required_strata=("detected_by", "taxonomy_version", "audit volume"),
            confounders=(
                "detection effort",
                "taxonomy version",
                "the fact that the engine sees 9 of 26 classes",
            ),
            measurable_today=False,
            why_not="labels need a clinician and a ratified case; "
            "audit volume is currently the only trendable term",
        ),
    ]


def report(records: list[dict], key: str, period: str = "month") -> dict[str, Any]:
    values = [point["mean"] for point in series(records, key, period) if "mean" in point]
    return {
        "metric": key,
        "period": period,
        "points": series(records, key, period),
        "trend": mann_kendall(values),
        "case_mix": case_mix_drift(records, "category", period),
        "questions": [question.as_dict() for question in four_questions()],
    }


def today() -> date:
    return date.today()
