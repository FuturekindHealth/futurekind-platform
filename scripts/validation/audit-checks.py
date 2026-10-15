#!/usr/bin/env python3
"""Audit the nine quality checks against the golden dataset, with no model involved.

Sprint 10 asks how radiologists interact with the product, and one half of that is
answerable today: the product's own gate can be run over the 100 reference reports the
repository already carries, which are by definition the answers the department says are
right. Two questions fall out, and neither needs a model, a GPU or a clinician's afternoon.

1. **Does the gate refuse a correct report?** Every case's expected answer is run through
   the engine as if it had just been drafted. A finding here is a false positive: a
   radiologist told the tool is checking their safety, and the tool objects to a report
   that is right. This is the failure that switches a quality check off in practice.
   `dropped_observation` is counted separately and never called a defect without looking:
   the dataset's `expected_findings` averages 8 words against a `dictated` input of 28,
   because that column is a *summary of the answer*, not a transcription of the dictation.
   A draft shaped like it trips a fidelity gate by construction, which says something about
   the dataset and something about the gate, and nothing yet about either being wrong.

2. **Does the gate notice a wrong report?** Each case's `must_not_say` entry is spliced
   into that case's expected findings — one assertion at a time — and the engine is asked
   whether anything now blocks. The verdict is a **paired delta**: the unmutated case is
   run first, and only a blocking check that was *not* already firing on that case counts
   as catching the probe. Without the pairing, a case that already blocks for another
   reason reports itself as detecting everything, which is how the first version of this
   script claimed 87% and meant nothing.

   Three outcomes, not two: **caught** (the probe raised a new blocking check), **missed**
   (nothing new fired and the case was clean, so the engine genuinely had the chance and
   did not take it), **inconclusive** (nothing new fired but the case was already blocking,
   so the probe is unmeasurable here). Only the first two are denominator. The base for the
   delta is `faithful_draft()` — the dictation carried in full — not the dataset's summary
   answer, because a summary answer blocks on the fidelity gate before any probe is reached.

3. **What would a tenth check buy?** The nine checks police the draft's relation to the text
   submitted: numbers, identities, comparisons, certainty, deletions. They are not blind by
   accident — a deterministic check cannot tell a legitimate synthesis from an invented one —
   but that leaves the dataset's own headline safety rule ("a normal study must not add a
   positive finding") unenforced. Two candidate rules are scored here against both
   populations above, so the ranking of that work is a measurement rather than an opinion.
   Nothing in this section is wired into the product.

The input text is synthetic and authored by an engineer (`ratified: pending` on all 100),
so every number here is a property of the checks and the dataset, not of clinical care.
Evidence strings are short quotes from that file; no patient text appears in this script's
output, and it must never be pointed at a real database — for that use
`scripts/validation/run-cases.py`.

Usage:  python3 scripts/validation/audit-checks.py [--out results.json] [--quiet]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DATASET = REPO / "docs" / "product" / "GOLDEN_DATASET.yaml"
sys.path.insert(0, str(REPO / "apps" / "radiology_copilot" / "src"))

from futurekind_radiology.profiles import profile_for  # noqa: E402 - the path above is why
from futurekind_radiology.quality import evaluate  # noqa: E402
from futurekind_radiology.report import QualityReport  # noqa: E402
from futurekind_radiology.submission import StudySubmission  # noqa: E402

#: The one check whose firing on a golden case is a disagreement with the dataset's shape
#: rather than proof of an engine defect. See the module docstring.
COVERAGE_CHECK = "dropped_observation"


def sections_of(case: dict) -> dict[str, str]:
    """The dataset's expected answer, in the shape a draft arrives in."""
    return {
        "clinical_indication": case["indication"],
        "technique": "",
        "findings": str(case.get("expected_findings", "")).strip(),
        "impression": str(case.get("expected_impression", "")).strip(),
        "recommendations": str(case.get("expected_recommendation", "")).strip(),
        "follow_up": "None.",
    }


def faithful_draft(case: dict) -> dict[str, str]:
    """The best a draft can be: every dictated observation carried, expected conclusion kept.

    Detection must be measured against a baseline the fidelity gate accepts. Splicing a probe
    into the dataset's 8-word summary answer blocks that case for dropping the dictation
    before the probe is even looked at, which left 268 of 310 probes unmeasurable in the first
    version of this script. Carrying the dictation instead takes the coverage check out of the
    argument: it has nothing to flag, so a blocking finding belongs to the probe.
    """
    draft = sections_of(case)
    draft["findings"] = str(case.get("dictated", "")).strip() or "Unremarkable study."
    return draft


def submission_of(case: dict) -> StudySubmission:
    return StudySubmission(
        clinical_indication=case["indication"],
        modality=case["modality"],
        study=case["study"],
        findings=str(case.get("dictated", "")).strip(),
    )


def run_engine(case: dict, sections: dict[str, str]) -> QualityReport:
    profile = profile_for(case["study"])
    return evaluate(
        sections,
        submission_of(case),
        checked_at="2026-10-08T00:00:00Z",
        structure_checklist=profile.structures if profile else (),
        out_of_scope_claims=profile.out_of_scope_claims if profile else (),
    )


def blocking_checks(quality: QualityReport) -> set[str]:
    return {f.check for f in quality.findings if f.severity == "block"}


# ------------------------------------------------------------------ 1. false positives


def audit_correct_reports(cases: list[dict]) -> dict:
    """Run the gate over the answers the dataset says are right."""
    per_check: Counter[str] = Counter()
    by_status: Counter[str] = Counter()
    defects: list[dict] = []
    coverage_only: list[str] = []
    examples: defaultdict[str, list[dict]] = defaultdict(list)

    for case in cases:
        quality = run_engine(case, sections_of(case))
        by_status[quality.status] += 1
        for finding in quality.findings:
            per_check[finding.check] += 1
            if len(examples[finding.check]) < 4:
                examples[finding.check].append(
                    {
                        "case": case["id"],
                        "category": case.get("category"),
                        "severity": finding.severity,
                        "section": finding.section,
                        "quote": (finding.evidence or finding.message)[:120],
                    }
                )
        fired = blocking_checks(quality)
        other = fired - {COVERAGE_CHECK}
        if other:
            defects.append(
                {
                    "case": case["id"],
                    "category": case.get("category"),
                    "difficulty": case.get("difficulty"),
                    "blocking": sorted(other),
                    "quotes": {
                        f.check: (f.evidence or f.message)[:120]
                        for f in quality.findings
                        if f.severity == "block" and f.check in other
                    },
                }
            )
        elif fired:
            coverage_only.append(case["id"])

    total = len(cases)
    return {
        "cases": total,
        "status_counts": dict(by_status),
        "per_check": dict(per_check.most_common()),
        "blocked_for_a_reason_other_than_coverage": len(defects),
        "blocked_for_coverage_only": len(coverage_only),
        "coverage_only_cases": coverage_only,
        "defects": defects,
        "examples": dict(examples),
    }


# ---------------------------------------------------------- 1b. the load each check carries


def _load_over(cases: list[dict], build) -> dict:
    """One corpus's per-check load: how often it fires, and what it costs.

    `sole_blocking_reason` is the number that decides a severity. A check that fires on
    correct reports only *alongside* another blocking finding is free — the report was being
    refused anyway. A check that is the only reason a correct report cannot be signed is the
    one that spends the radiologist's trust, and a night's worth of those is a tool the
    department routes around.
    """
    fired: defaultdict[str, Counter] = defaultdict(Counter)
    for case in cases:
        quality = run_engine(case, build(case))
        for finding in quality.findings:
            fired[finding.check][finding.severity] += 1
        blocking = {f.check for f in quality.findings if f.severity == "block"}
        for check in {f.check for f in quality.findings}:
            fired[check]["cases"] += 1
        if len(blocking) == 1:
            fired[next(iter(blocking))]["sole_blocking_reason"] += 1
    rows = {}
    for check, counts in fired.items():
        rows[check] = {
            "cases_with_the_finding": counts["cases"],
            "blocking_findings": counts["block"],
            "advisory_findings": counts["advisory"],
            "sole_reason_a_correct_report_could_not_be_signed": counts["sole_blocking_reason"],
        }
    ordered = dict(
        sorted(
            rows.items(),
            key=lambda kv: -kv[1]["sole_reason_a_correct_report_could_not_be_signed"],
        )
    )
    return {"cases": len(cases), "checks": ordered}


def audit_check_load(cases: list[dict]) -> dict:
    """The same measurement over both ways of building a correct draft.

    `summary_answer` is the dataset's own short answer, `faithful_answer` carries the whole
    dictation. The two differ in exactly one place — how much text the coverage check has to
    find — and saying that in the output is why this reads both rather than picking one.
    """
    return {
        "summary_answer": _load_over(cases, sections_of),
        "faithful_answer": _load_over(cases, faithful_draft),
    }


# ------------------------------------------------------------------ 2. detection


#: Where a model could put a forbidden assertion. Both are tried for every probe: choosing
#: the placement from a keyword would make this harness, not the engine, decide what was
#: measurable — `_check_certainty` reads only the impression, so a descriptive probe filed
#: under findings would go unseen for a reason that has nothing to do with the check.
PLACEMENTS = ("findings", "impression")


def splice(sentence: str, sections: dict[str, str], target: str) -> dict[str, str]:
    """Put one forbidden assertion into the report where a model would put it.

    This is a mutation of a synthetic answer, not a real draft, and it is labelled everywhere
    as such — but the engine cannot tell the difference, which is the point.
    """
    mutated = dict(sections)
    base = mutated[target] or "Unremarkable study."
    mutated[target] = f"{base} {sentence.strip().rstrip('.')}."
    return mutated


def audit_detection(cases: list[dict]) -> dict:
    """Splice every `must_not_say` probe in and take the paired delta against its own case."""
    caught = 0
    missed = 0
    inconclusive = 0
    caught_by: Counter[str] = Counter()
    misses: list[dict] = []
    inconclusive_probes: list[dict] = []
    probes = 0
    clean_baseline_probes = 0

    for case in cases:
        base = faithful_draft(case)
        already = blocking_checks(run_engine(case, base))
        for sentence in case.get("must_not_say") or []:
            probes += 1
            if not already:
                clean_baseline_probes += 1
            runs = [run_engine(case, splice(str(sentence), base, target)) for target in PLACEMENTS]
            newly = set().union(*(blocking_checks(run) for run in runs)) - already
            advisory = sorted({f.check for run in runs for f in run.advisory})
            if newly:
                caught += 1
                caught_by.update(newly)
            elif already:
                inconclusive += 1
                inconclusive_probes.append(
                    {
                        "case": case["id"],
                        "probe": str(sentence)[:120],
                        "already_blocking": sorted(already),
                        "advisory_raised": advisory,
                    }
                )
            else:
                missed += 1
                misses.append(
                    {
                        "case": case["id"],
                        "category": case.get("category"),
                        "difficulty": case.get("difficulty"),
                        "probe": str(sentence)[:120],
                        "advisory_only": advisory,
                    }
                )

    measurable = caught + missed
    return {
        "probes": probes,
        "caught": caught,
        "missed": missed,
        "inconclusive_already_blocking": inconclusive,
        "measurable": measurable,
        "detection_rate": round(caught / measurable, 3) if measurable else None,
        "clean_baseline_probes": clean_baseline_probes,
        "caught_by_check": dict(caught_by.most_common()),
        "misses": misses,
        "inconclusive_probes": inconclusive_probes,
        "misses_advisory": sum(1 for m in misses if m["advisory_only"]),
        "misses_silent": sum(1 for m in misses if not m["advisory_only"]),
    }


# ------------------------------------------------------------------ 3. a candidate check


#: Words that carry a clinical assertion in radiology prose and are recognisable by their
#: ending. This is a crude lexicon, and it is the point of measuring it: the useful unit for
#: a tenth check is the *diagnosis name*, not the word, because "any word the dictation did
#: not say" flags a correct summarised report as loudly as a hallucinating one.
_CLINICAL_SUFFIX = re.compile(
    r"\b[a-z]{4,}(?:itis|osis|opathy|ectasis|megaly|plegia|emia|oma|scherosis|"
    r"thrombosis|infarction|haemorrhage|hemorrhage|fracture|dislocation|stenosis|"
    r"occlusion|perforation|obstruction|herniation|haematoma|hematoma|abscess|"
    r"metastases|metastasis|malformation|aneurysm|angiopathy|leukomalacia|"
    r"sclerosis|atelectasis|diverticula|diverticulitis|cholecystitis|pancreatitis)\b",
    re.IGNORECASE,
)
_WORD = re.compile(r"[A-Za-z][A-Za-z-]{4,}")

#: Ordinary prose that is not a diagnosis and must not count as one.
_STOP_TEXT = (
    "the this that with without other normal unusual study findings finding report because "
    "therefore however although while there their which where about above below between "
    "further previously currently obviously potentially probably likely unlikely consistent "
    "suggesting indicative compatible concerning regarding requires recommended suggestion "
    "follow-up followup imaging examination assessment"
)
_STOP = frozenset(_STOP_TEXT.split())


def _stem(word: str) -> str:
    return word[:-1] if len(word) > 4 and word.endswith("s") else word


def grounded_stems(grounding: str) -> set[str]:
    return {_stem(w) for w in _WORD.findall(grounding.lower())}


def ungrounded_words(text: str, grounding: set[str]) -> list[str]:
    """Every word in the draft with no ancestor in the submitted text."""
    hits = set()
    for word in _WORD.findall(text):
        lowered = word.lower()
        if lowered in _STOP or _stem(lowered) in grounding:
            continue
        hits.add(lowered)
    return sorted(hits)


def ungrounded_diagnoses(text: str, grounding: set[str]) -> list[str]:
    """Only the words that name a disease."""
    return sorted(
        {
            w.group(0).lower()
            for w in _CLINICAL_SUFFIX.finditer(text)
            if _stem(w.group(0).lower()) not in grounding
        }
    )


def audit_candidate_checks(cases: list[dict]) -> dict:
    """Would a tenth check — an assertion the dictation never made — be worth building?

    Two candidate rules, scored against the same two populations the shipped engine was
    scored against: the 100 answers the dataset calls correct (a flag there is the noise the
    reviewer would have to live with) and the 310 hallucination probes (a flag there is the
    detection bought). Nothing here is wired into the product; this is the measurement that
    decides whether it should be, which is what Sprint 10 asked for.
    """
    noise: dict[str, list[int]] = {"words": [], "diagnoses": []}
    caught: dict[str, int] = {"words": 0, "diagnoses": 0}
    probes = 0
    examples: defaultdict[str, list[dict]] = defaultdict(list)

    for case in cases:
        grounding = grounded_stems(submission_of(case).grounding_text)
        draft = sections_of(case)
        prose = " ".join(draft[key] for key in ("findings", "impression", "recommendations"))
        for key, extract in (("words", ungrounded_words), ("diagnoses", ungrounded_diagnoses)):
            hits = extract(prose, grounding)
            noise[key].append(len(hits))
            if len(examples[key]) < 6 and hits:
                examples[key].append({"case": case["id"], "flagged": hits[:12]})
        for sentence in case.get("must_not_say") or []:
            probes += 1
            text = str(sentence)
            grounding_local = grounded_stems(submission_of(case).grounding_text + " " + prose)
            for key, extract in (("words", ungrounded_words), ("diagnoses", ungrounded_diagnoses)):
                if extract(text, grounding_local):
                    caught[key] += 1

    def summarise(key: str) -> dict:
        counts = noise[key]
        return {
            "mean_per_correct_report": round(sum(counts) / len(counts), 2) if counts else None,
            "reports_with_no_flag": sum(1 for c in counts if c == 0),
            "max_on_one_correct_report": max(counts) if counts else None,
            "probes_flagged": caught[key],
            "probes": probes,
            "probe_detection": round(caught[key] / probes, 3) if probes else None,
        }

    return {
        "word_level": summarise("words"),
        "diagnosis_level": summarise("diagnoses"),
        "examples_on_correct_reports": dict(examples),
    }


# ------------------------------------------------------------------ entry


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--dataset", type=Path, default=DATASET)
    parser.add_argument("--out", type=Path, help="write the full result as JSON")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    import yaml

    document = yaml.safe_load(args.dataset.read_text(encoding="utf-8"))
    cases = document["cases"]

    false_positives = audit_correct_reports(cases)
    detection = audit_detection(cases)
    candidate = audit_candidate_checks(cases)
    load = audit_check_load(cases)
    result = {
        "dataset": args.dataset.name,
        "cases": len(cases),
        "correct_reports_refused": false_positives,
        "must_not_say_detection": detection,
        "candidate_tenth_check": candidate,
        "check_load": load,
    }

    if not args.quiet:
        print(f"{len(cases)} cases from {args.dataset.name}\n")
        print("1. THE GATE ON A CORRECT REPORT")
        print(f"   statuses: {false_positives['status_counts']}")
        for check, count in false_positives["per_check"].items():
            print(f"     {check:26} {count}")
        print(
            f"   blocked by the fidelity gate alone (expected answer is a summary): "
            f"{false_positives['blocked_for_coverage_only']}/{len(cases)}"
        )
        print(
            f"   blocked for an engine reason — candidates for a defect: "
            f"{false_positives['blocked_for_a_reason_other_than_coverage']}/{len(cases)}"
        )
        for row in false_positives["defects"]:
            checks = ",".join(row["blocking"])
            print(f"     {row['case']:6} {row['category'] or '?':12} {checks:28} {row['quotes']}")

        print("\n2. THE GATE ON A KNOWN-BAD SENTENCE (`must_not_say`, paired delta)")
        print(
            f"   probes: {detection['probes']} · caught {detection['caught']} · missed "
            f"{detection['missed']} · inconclusive (case already blocking) "
            f"{detection['inconclusive_already_blocking']}"
        )
        print(
            f"   detection over the {detection['measurable']} measurable probes: "
            f"{detection['detection_rate']:.0%}"
            f" (of which {detection['clean_baseline_probes']} probes sat on a clean baseline)"
        )
        for check, count in detection["caught_by_check"].items():
            print(f"     {check:26} {count}")
        print(
            f"   of the misses: {detection['misses_advisory']} raised an advisory, "
            f"{detection['misses_silent']} raised nothing at all"
        )
        for miss in detection["misses"][:20]:
            print(f"     MISSED {miss['case']:6} {miss['probe'][:70]!r}")
        if len(detection["misses"]) > 20:
            print(f"     … and {len(detection['misses']) - 20} more, in --out")

        print("\n3. WHAT A TENTH CHECK WOULD BUY (a simulation, wired into nothing)")
        rules = (
            ("any ungrounded word", "word_level"),
            ("an ungrounded diagnosis name", "diagnosis_level"),
        )
        for label, key in rules:
            row = candidate[key]
            print(
                f"   rule: flag {label}\n"
                f"     noise  {row['mean_per_correct_report']} flagged term(s) per correct report, "
                f"{row['reports_with_no_flag']}/100 correct reports untouched, "
                f"worst report {row['max_on_one_correct_report']}\n"
                f"     gain   {row['probes_flagged']}/{row['probes']} probes flagged "
                f"= {row['probe_detection']:.0%}"
            )
        for key, rows in candidate["examples_on_correct_reports"].items():
            for row in rows[:3]:
                print(f"     on {row['case']:6} ({key}): {row['flagged']}")

        print("\n4. WHAT EACH CHECK COSTS ON A CORRECT DRAFT (severity decisions)")
        print(
            "   A check is worth its severity only if it is rarely the sole reason a correct\n"
            "   report is refused. `summary` builds findings from the dataset's short expected\n"
            "   answer; `faithful` carries the whole dictation, which is what a good model does."
        )
        header = f"   {'check':26} {'cases':>6} {'block':>6} {'advis':>6} {'sole':>5}"
        for key, label in (("summary_answer", "summary"), ("faithful_answer", "faithful")):
            print(f"   --- {label} answer, {load[key]['cases']} cases")
            print(header)
            for check, row in load[key]["checks"].items():
                print(
                    f"   {check:26} {row['cases_with_the_finding']:>6} "
                    f"{row['blocking_findings']:>6} {row['advisory_findings']:>6} "
                    f"{row['sole_reason_a_correct_report_could_not_be_signed']:>5}"
                )

    if args.out:
        args.out.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(f"\nfull detail -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
