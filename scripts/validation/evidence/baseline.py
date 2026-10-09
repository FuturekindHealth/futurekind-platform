"""What a report costs to write, measured from the corpus the repository already has.

This is the only *real* number the evidence system can produce before a model runs or a
clinician sits down, and it is the one every later claim depends on: how much of a radiology
report is composition. A product that drafts cannot save more composition than exists, so the
quantity below is the ceiling on the platform's whole value proposition.

It is computable now because the golden dataset carries both halves of the pair — what was
dictated, and what the department says the answer should be — for all 100 cases.

Three limitations are printed with the output rather than filed away:

1. **The reference answers are summaries, not transcriptions.** `expected_findings` averages
   about eight words against a `dictation` of about twenty-eight
   (`docs/product/GOLDEN_DATASET.yaml:26-31`). Measured composition against a terse summary
   therefore *overstates* how much writing there is to do, and understates how much of the
   real report is transcription. The number is a bound, labelled as one.
2. **The corpus is synthetic and unratified.** All 100 cases are `ratified: pending` and
   authored by engineering, so this describes a department's *idea* of a report, not its
   reports. `evidence.groundtruth` refuses to call any of it ground truth.
3. **It is imaging only.** No modality outside CT/MRI/US/XR/CTA/CTP/MG appears, so nothing here
   transfers to pathology, discharge or a ward document.

The output is aggregate counts and distributions. No case text is emitted, and the same
command reproduces every number.
"""

from __future__ import annotations

import statistics
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any

import yaml

from .edits import MEASUREMENT, NEGATIONS, _shared_chars, _tokens
from .groundtruth import corpus_summary, from_golden

DATASET = Path(__file__).resolve().parents[3] / "docs" / "product" / "GOLDEN_DATASET.yaml"
SECTIONS = ("findings", "impression", "recommendations")


def load_cases(path: Path = DATASET) -> list[dict]:
    with path.open(encoding="utf-8") as handle:
        return list(yaml.safe_load(handle)["cases"])


def _reference_text(row: dict) -> str:
    parts = [
        row.get("expected_findings", "") or "",
        row.get("expected_impression", "") or "",
        row.get("expected_recommendation", "") or "",
    ]
    return " ".join(part for part in parts if part).strip()


def per_case(row: dict) -> dict[str, Any]:
    dictation = (row.get("dictated", "") or "").strip()
    reference = _reference_text(row)
    shared = _shared_chars(dictation, reference)
    reference_len = len(reference)
    measurement_tokens = [m.group(0) for m in MEASUREMENT.finditer(reference) if m.group(0).strip()]
    numbers_only = [
        token for token in measurement_tokens if any(character.isdigit() for character in token)
    ]
    negations = sorted(_tokens(reference) & NEGATIONS)
    return {
        "case_id": row.get("id", ""),
        "modality": row.get("modality", ""),
        "category": row.get("category", ""),
        "difficulty": int(row.get("difficulty", 3)),
        "dictation_chars": len(dictation),
        "dictation_words": len(dictation.split()),
        "reference_chars": reference_len,
        "reference_words": len(reference.split()),
        "composition_share": round(1 - (shared / reference_len), 4) if reference_len else None,
        "measurements_in_reference": len(numbers_only),
        "negation_words_in_reference": len(negations),
        "must_not_say": len(row.get("must_not_say", []) or []),
        "has_teaching_point": bool((row.get("teaching_points", "") or "").strip()),
    }


def summarise(cases: list[dict]) -> dict[str, Any]:
    rows = [per_case(row) for row in cases]
    composition = [r["composition_share"] for r in rows if r["composition_share"] is not None]
    dictation_words = [r["dictation_words"] for r in rows]
    reference_words = [r["reference_words"] for r in rows]
    measurements = [r["measurements_in_reference"] for r in rows]
    probes = [r["must_not_say"] for r in rows]

    def describe(values: list[float]) -> dict[str, Any]:
        numbers = [float(v) for v in values]
        if not numbers:
            return {"n": 0}
        ordered = sorted(numbers)
        return {
            "n": len(numbers),
            "mean": round(statistics.fmean(numbers), 4),
            "median": round(statistics.median(numbers), 4),
            "p25": ordered[max(0, len(ordered) // 4)],
            "p75": ordered[min(len(ordered) - 1, (3 * len(ordered)) // 4)],
            "min": round(min(numbers), 4),
            "max": round(max(numbers), 4),
        }

    by_category: dict[str, dict[str, Any]] = {}
    for category in ("normal", "common", "rare", "emergency", "medicolegal"):
        subset = [r for r in rows if r["category"] == category]
        by_category[category] = {
            "cases": len(subset),
            "composition_share_median": describe([r["composition_share"] for r in subset]).get(
                "median"
            ),
            "reference_words_mean": describe([r["reference_words"] for r in subset]).get("mean"),
            "measurements_mean": describe([r["measurements_in_reference"] for r in subset]).get(
                "mean"
            ),
        }

    return {
        "cases": len(rows),
        "measured_on": date.today().isoformat(),
        "corpus": str(DATASET.relative_to(DATASET.parents[2])),
        "composition_share": describe(composition),
        "dictation_words": describe(dictation_words),
        "reference_words": describe(reference_words),
        "measurements_per_reference": describe(measurements),
        "probes_per_case": describe(probes),
        "modality_counts": dict(Counter(r["modality"] for r in rows)),
        "category_counts": dict(Counter(r["category"] for r in rows)),
        "difficulty_counts": dict(sorted(Counter(r["difficulty"] for r in rows).items())),
        "by_category": by_category,
        "teaching_points_present": sum(1 for r in rows if r["has_teaching_point"]),
        "ground_truth_state": corpus_summary([from_golden(row) for row in cases]),
        "limitations": [
            "expected answers are summaries, so composition_share overstates composition and "
            "understates transcription: it is a bound, not a measurement of real reports",
            "all 100 cases are synthetic and engineer-authored, and none is ratified, so "
            "nothing here is evidence about care",
            "imaging only: no value transfers to pathology, discharge or ward documents",
            "the real ceiling needs signed reports with their dictation, which the retention "
            "decision (ADR-0003) and the entry-point walk both currently block",
        ],
    }


def markdown_table(summary: dict[str, Any]) -> str:
    """A generated table, marked as generated. Rule 2 of `docs/README.md` §10: a number in
    prose is allowed only when it is dated and produced by a command — this function is that
    command's output half."""
    composition = summary["composition_share"]
    dictation = summary["dictation_words"]
    reference = summary["reference_words"]
    lines = [
        "<!-- GENERATED by `python -m evidence baseline` — do not hand-edit the numbers. -->",
        "",
        f"Measured {summary['measured_on']} over {summary['cases']} cases in "
        f"`{summary['corpus']}`. Synthetic, unratified, imaging only.",
        "",
        "| Quantity | n | mean | median | p25 | p75 | min | max |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for label, block in (
        ("composition share of the reference report", composition),
        ("dictated words per case", dictation),
        ("reference report words per case", reference),
        ("measurements in the reference report", summary["measurements_per_reference"]),
        ("hallucination probes per case", summary["probes_per_case"]),
    ):
        lines.append(
            f"| {label} | {block.get('n', 0)} | {block.get('mean', '—')} | "
            f"{block.get('median', '—')} | {block.get('p25', '—')} | {block.get('p75', '—')} | "
            f"{block.get('min', '—')} | {block.get('max', '—')} |"
        )
    lines += [
        "",
        "| Category | cases | composition share (median) | mean ref words | mean measurements |",
        "| --- | --- | --- | --- | --- |",
    ]
    for category, block in summary["by_category"].items():
        lines.append(
            f"| {category} | {block['cases']} | {block['composition_share_median']} | "
            f"{block['reference_words_mean']} | {block['measurements_mean']} |"
        )
    lines += ["", "**Limitations, part of the number:**"]
    lines += [f"- {note}" for note in summary["limitations"]]
    return "\n".join(lines) + "\n"


def run() -> dict[str, Any]:
    return summarise(load_cases())
