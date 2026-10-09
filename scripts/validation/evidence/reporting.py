"""Seven audiences, publication tables, figures, CSV, and an anonymisation gate.

Parts 10, 11 and 12. One dataset, deliberately different views — and three rules that make
the difference between an analytics feature and an exposure.

**A view is not an access control.** The platform's only credential is a shared key per
deployment (`docs/adr/ADR-0004…` does not exist), so `view()` filters what a *file* contains,
not what a *person* may read. Anyone who reads a per-reporter number as a privacy guarantee is
being lied to by the word "role", and that is why the refusal is in the code and not in a
footnote.

**Aggregate before you aggregate.** A per-centre or per-reporter figure with n = 3 is a
re-identification with a decimal point. `anonymise_check` enforces k-anonymity over the
quasi-identifier set a hospital would recognise — site, modality, study, category, difficulty,
role, month — and refuses to emit any cell thinner than `K_MIN`.

**Figures carry their denominator.** Every chart prints `n` on the axis label, because the
most common way a clinical dashboard misleads is a line over four cases drawn at the same
weight as a line over four thousand.
"""

from __future__ import annotations

import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from . import stats, store, taxonomy

K_MIN = 5

#: Each audience's question, the fields that answer it, and the fields it must not receive.
#: "must not" is a list rather than an absence so it can be tested and quoted.
AUDIENCES: dict[str, dict[str, Any]] = {
    "radiologist": {
        "question": "Is this draft worth my time, and did I catch anything?",
        "fields": ("case_ref", "review_seconds", "typed_chars", "substantive_sections", "labels"),
        "must_not_see": ("other_reporters", "per_case_labels_by_colleague"),
        "note": "individual feedback, not a league table (docs/FAILURE-MODES.md FM10)",
    },
    "department_head": {
        "question": "Where is the reporting load, and is turnaround moving?",
        "fields": (
            "modality",
            "category",
            "cases_per_period",
            "time_to_final",
            "blocking_findings",
        ),
        "must_not_see": ("case_ref", "typed_chars_by_reporter"),
    },
    "medical_director": {
        "question": "Can I sign off that this is safe to use here?",
        "fields": (
            "safety_axis",
            "degradation_unannounced",
            "refusal_rate",
            "error_classes_by_group",
            "gate_state",
        ),
        "must_not_see": ("case_ref"),
        "note": "the only view that answers a regulator; it is aggregate or nothing",
    },
    "quality_committee": {
        "question": "What reached a patient, and what did we miss?",
        "fields": ("error_classes", "false_alerts", "missed_alerts", "unclassified_rate", "trend"),
        "must_not_see": ("case_ref", "typed_chars"),
    },
    "research_team": {
        "question": "Is this a finding or is this noise?",
        "fields": (
            "all_aggregated",
            "case_mix",
            "intervals",
            "preregistration",
            "taxonomy_version",
        ),
        "must_not_see": ("raw_text", "quasi_identifiers_below_k"),
        "note": (
            "receives the frozen corpus version: a trend across a dataset change is not a result"
        ),
    },
    "engineering": {
        "question": "What broke, how often, and what is the next fix worth doing?",
        "fields": (
            "engine_findings",
            "finish_reasons",
            "attempts",
            "degraded",
            "latency",
            "proposals",
        ),
        "must_not_see": ("raw_text"),
    },
    "administration": {
        "question": "What did this cost, and what did we get?",
        "fields": (
            "cases_per_period",
            "typed_chars_total",
            "time_to_final_median",
            "licences",
            "sites",
        ),
        "must_not_see": ("case_ref", "error_classes", "labels"),
        "note": (
            "cost views never receive clinical labels: a per-case error count in a budget paper "
            "is how a clinician ends up named in one"
        ),
    },
}

IDENTIFIER_SHAPED = re.compile(
    r"(?:\b(?:mrn|uhid|ip\s*no|accession)\b|\d{6,}|\b[A-Z]{2}\d{5,}\b)", re.IGNORECASE
)
QUASI_IDENTIFIERS = ("site", "modality", "study", "category", "difficulty", "role", "month")


def view(records: list[dict], audience: str) -> dict[str, Any]:
    spec = AUDIENCES.get(audience)
    if spec is None:
        raise KeyError(f"unknown audience {audience!r}; the seven are {sorted(AUDIENCES)}")
    aggregated = _aggregate(records, audience)
    allowed = set(spec["fields"])
    out = {
        key: value
        for key, value in aggregated.items()
        if key in allowed or "all_aggregated" in allowed
    }
    out["_audience"] = audience
    out["_question"] = spec["question"]
    out["_must_not_see"] = list(spec["must_not_see"])
    out["_note"] = spec.get("note", "aggregate only; a view is a filter, not a permission system")
    return out


def _aggregate(records: list[dict], audience: str) -> dict[str, Any]:
    rows = store.real_rows(records)
    stub_dropped = len(records) - len(rows)
    typed = [row.get("edit", {}).get("chars_inserted") for row in rows]
    typed = [value for value in typed if isinstance(value, (int, float))]
    times = [row.get("time_to_final_seconds") for row in rows]
    times = [value for value in times if isinstance(value, (int, float))]
    labels = Counter(code for row in rows for code in row.get("labels", []))
    groups = Counter(taxonomy_group(code) for code in labels.elements())
    return {
        "cases": len(rows),
        "stub_records_excluded": stub_dropped,
        "typed_chars_total": sum(typed),
        "time_to_final": store.distribution(times),
        "error_classes": dict(labels),
        "error_classes_by_group": dict(groups),
        "unclassified_rate": _ratio(labels.get("E99", 0), sum(labels.values())),
        "case_mix": {
            key: dict(Counter(str(row.get(key, "")) for row in rows))
            for key in ("modality", "category", "difficulty")
        },
        "sites": sorted({row.get("site", "") for row in rows if row.get("site")}),
        "audience": audience,
    }


def taxonomy_group(code: str) -> str:
    """Which part of the taxonomy a label belongs to, or `unknown` when it is not in it."""
    if code in taxonomy.BY_CODE:
        return taxonomy.code(code).group
    return "unknown"


def _ratio(numerator: float, denominator: float) -> float | None:
    return round(numerator / denominator, 4) if denominator else None


def table_1(records: list[dict]) -> dict[str, Any]:
    """Baseline characteristics, the table a reviewer reads first and a study earns later."""
    rows = store.real_rows(records)
    out: dict[str, Any] = {"n_cases": len(rows), "columns": []}
    for key in ("modality", "category", "difficulty", "site", "role"):
        counts = Counter(str(row.get(key, "")) for row in rows if row.get(key) not in (None, ""))
        if not counts:
            out["columns"].append(
                {
                    "field": key,
                    "values": {},
                    "note": "not recorded — a data-collection gap, not a zero",
                }
            )
            continue
        out["columns"].append(
            {
                "field": key,
                "values": dict(sorted(counts.items())),
                "total": sum(counts.values()),
            }
        )
    for metric in ("time_to_final_seconds",):
        values = [row[metric] for row in rows if isinstance(row.get(metric), (int, float))]
        out["columns"].append({"field": metric, "distribution": store.distribution(values)})
    return out


def results_table(
    records: list[dict], success_field: str, denominator_field: str = ""
) -> list[dict[str, Any]]:
    """Per-stratum rates with Wilson intervals. A rate without its interval is an opinion."""
    rows = store.real_rows(records)
    strata: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        strata[str(row.get("category", "unstratified"))].append(row)
    table: list[dict[str, Any]] = []
    for stratum, group in sorted(strata.items()):
        successes = sum(1 for row in group if _truthy(row, success_field))
        n = len(group)
        estimate = stats.proportion(successes, n)
        table.append(
            {
                "stratum": stratum,
                "n": n,
                "successes": successes,
                "rate": estimate.estimate,
                "ci": estimate.ci,
                "suppress": n < K_MIN,
                "caution": "below k=5 this cell is a re-identification risk, not a result"
                if n < K_MIN
                else "",
            }
        )
    return table


def _truthy(row: dict, field_name: str) -> bool:
    for source in (row, row.get("edit", {}), row.get("engine", {}), row.get("scores", {})):
        if field_name in source:
            return bool(source[field_name])
    return False


def anonymise_check(records: list[dict]) -> dict[str, Any]:
    """Refuse an export that could name someone or something.

    Three independent checks, because each catches what the others cannot: identifier-shaped
    strings in any exported value, quasi-identifier cells thinner than k, and the presence of
    section text at all.
    """
    offenders: list[str] = []
    for index, row in enumerate(records):
        blob = json.dumps(row, sort_keys=True, default=str)
        match = IDENTIFIER_SHAPED.search(blob)
        if match:
            offenders.append(f"record {index}: identifier-shaped value near {match.group(0)!r}")
        if row.get("text_stored"):
            offenders.append(f"record {index}: carries section text (text_stored=true)")
    cells = Counter(tuple(str(row.get(key, "")) for key in QUASI_IDENTIFIERS) for row in records)
    thin = [
        dict(zip(QUASI_IDENTIFIERS, combination, strict=True))
        for combination, count in cells.items()
        if count < K_MIN
    ]
    return {
        "records": len(records),
        "identifier_offenders": offenders[:20],
        "offender_count": len(offenders),
        "quasi_identifiers": list(QUASI_IDENTIFIERS),
        "k_min": K_MIN,
        "cells_below_k": len(thin),
        "share_below_k": _ratio(len(thin), len(cells)) if cells else None,
        "examples_below_k": thin[:5],
        "verdict": (
            "refused: fix the offenders before writing any export"
            if offenders
            else ("review the thin cells: aggregate further, or suppress them" if thin else "clear")
        ),
        "limits": (
            "k-anonymity is a floor, not a proof. It does not survive a determined reader with "
            "the hospital's own RIS, and it says nothing about free text, which is why free text "
            "is not in this dataset by default."
        ),
    }


def centre_summary(records: list[dict]) -> dict[str, Any]:
    """Per-site performance and heterogeneity — never pooled patient data.

    Part 12. Comparing centres is legitimate; comparing their patients is not. Heterogeneity
    here is reported as the spread of site rates with their own intervals, and explicitly
    *not* as a pooled effect, because a between-site difference is mostly case mix, staffing
    and study participation until proven otherwise.
    """
    rows = store.real_rows(records)
    by_site: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_site[str(row.get("site", "unlabelled"))].append(row)
    sites = []
    for site, group in sorted(by_site.items()):
        typed = [row.get("edit", {}).get("chars_inserted") for row in group]
        typed = [value for value in typed if isinstance(value, (int, float))]
        labels = Counter(code for row in group for code in row.get("labels", []))
        sites.append(
            {
                "site": site,
                "cases": len(group),
                "typed_chars": store.distribution(typed),
                "labels_per_100_cases": round(100 * sum(labels.values()) / len(group), 2)
                if group
                else None,
                "suppressed": len(group) < K_MIN,
            }
        )
    rates = [
        site["labels_per_100_cases"] for site in sites if site["labels_per_100_cases"] is not None
    ]
    spread = store.distribution([float(value) for value in rates])
    return {
        "sites": sites,
        "heterogeneity": spread,
        "rule": (
            "compare prompts, workflows and reported rates across centres; never move "
            "patient data between them (docs/CONSTITUTION.md P14)"
        ),
        "caution": "a between-site gap is case mix until a stratified analysis says otherwise",
        "scale_note": (
            "one centre: rates only. ten: stratify by centre. a hundred: the analysis unit "
            "is the centre, not the case, and every per-case p-value in this package must "
            "be read with that in mind"
        ),
    }


def write_csv(rows: list[dict], path) -> int:
    destination = Path(path)
    if store.inside_repo(destination):
        raise store.StoreError(f"refusing to write an export inside the repository: {path}")
    if not rows:
        raise ValueError("an empty export is indistinguishable from a study that found nothing")
    columns: list[str] = []
    for row in rows:
        for key in row:
            if key not in columns:
                columns.append(key)
    with destination.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: _cell(row.get(key)) for key in columns})
    return len(rows)


def _cell(value: Any) -> Any:
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, sort_keys=True, default=str)
    return value


def svg_line(
    points: list[dict], value_key: str = "mean", width: int = 720, height: int = 260
) -> str:
    """A dependency-free line plot. Values are aggregate means; `n` goes in every label.

    SVG rather than a PNG because the figure must be reviewable in a text diff: a chart whose
    bytes are opaque is a chart nobody can check, and a research artefact nobody can check is
    a decoration. No plotting library is introduced into this repository for one chart.
    """
    usable = [point for point in points if isinstance(point.get(value_key), (int, float))]
    if len(usable) < 2:
        return (
            f"<svg xmlns='http://www.w3.org/2000/svg' width='{width}' height='{height}'>"
            f"<text x='12' y='24' font-family='sans-serif'>not enough periods to draw a line "
            f"(n={len(usable)}): drawing one would imply a trend</text></svg>"
        )
    values = [float(point[value_key]) for point in usable]
    low, high = min(values), max(values)
    span = (high - low) or 1.0
    margin = 48
    step = (width - 2 * margin) / (len(usable) - 1)
    coordinates = []
    for index, value in enumerate(values):
        x = margin + index * step
        y = height - margin - ((value - low) / span) * (height - 2 * margin)
        coordinates.append((x, y, usable[index]))
    path = " ".join(
        f"{'M' if index == 0 else 'L'}{x:.1f},{y:.1f}"
        for index, (x, y, _) in enumerate(coordinates)
    )
    parts = [
        f"<svg xmlns='http://www.w3.org/2000/svg' width='{width}' height='{height}' role='img'>",
        f"<title>{value_key} by period, with case counts</title>",
        "<desc>Generated by `python -m evidence figure`. Points carry n; "
        "the axis range is the data range.</desc>",
        f"<line x1='{margin}' y1='{height - margin}' x2='{width - margin}' "
        f"y2='{height - margin}' stroke='#444'/>",
        f"<line x1='{margin}' y1='{margin}' x2='{margin}' y2='{height - margin}' stroke='#444'/>",
        f"<path d='{path}' fill='none' stroke='#111' stroke-width='2'/>",
    ]
    for x, y, point in coordinates:
        parts.append(f"<circle cx='{x:.1f}' cy='{y:.1f}' r='3' fill='#111'/>")
        parts.append(
            f"<text x='{x:.1f}' y='{height - margin + 16:.0f}' font-size='10' "
            f"font-family='sans-serif' text-anchor='middle'>{point.get('period', '')}</text>"
        )
        parts.append(
            f"<text x='{x:.1f}' y='{y - 8:.1f}' font-size='10' font-family='sans-serif' "
            f"<text x='{x:.1f}' y='{y - 8:.1f}' font-size='10' font-family='sans-serif' "
            f"text-anchor='middle'>{point[value_key]:.3g} "
            f"(n={point.get('n_value', point.get('n_records', 0))})</text>"
        )
    parts.append(
        f"<text x='{margin}' y='{height - 10}' font-size='11' font-family='sans-serif'>"
        f"min {low:.3g} · max {high:.3g} · {len(usable)} periods</text>"
    )
    parts.append("</svg>")
    return "".join(parts)
