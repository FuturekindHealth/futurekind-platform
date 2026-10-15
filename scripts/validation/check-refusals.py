"""Prove that the evidence refusals refuse, by breaking each one and running its test.

`docs/safety/CLINICAL_SAFETY.md` §6 gate G3 demands "a refusal path, a test, and a check that
the test fails when the path is removed". This is that check for the instruments in
`evidence/`. A guard that no test can see is not a guard, and the only way to know whether a
test can see it is to remove it and watch.

The mutations are applied to the working tree, one at a time, and each file is restored from a
pristine copy before the next one runs. Three things make that safe enough to keep in the
repository:

* it refuses to start if any file it will touch has uncommitted changes, because a harness that
  overwrites someone's work in progress is a defect regardless of what it proves;
* it re-checks the file's hash immediately before every write, so an edit made while it runs
  stops the run instead of being silently restored over;
* it never defaults a count to zero. `failed`, `passed` and `error` are parsed independently from
  ANSI-stripped output, because a verdict that falls back to a plausible number is how a fake
  green run is produced. The baseline must pass before a mutation is trusted to have been caught.

Usage:

    python scripts/validation/check-refusals.py            # all of them
    python scripts/validation/check-refusals.py --list     # what it would break
    python scripts/validation/check-refusals.py store      # only ids containing "store"

Exit codes are decisions: 0 every refusal proved itself, 1 something survived or the tree was not
restored, 2 the harness refused to start.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
VALIDATION = REPO / "scripts" / "validation"
ANSI = re.compile(r"\x1b\[[0-9;]*m")


@dataclass(frozen=True)
class Mutation:
    #: Stable id so a failure names the guard, not the line.
    identifier: str
    claim: str
    path: str
    old: str
    new: str
    test: str


#: The two unconditional raises, spelled out here so the mutation table stays readable. If either
#: message is reworded, this harness reports SOURCE-MISS rather than silently proving nothing —
#: which is the correct outcome: the guard moved, so the proof has to be re-read.
COMPOSITE_RAISE = (
    "    raise CombinedScoreError(\n"
    '        "six axes stay six axes: a composite hides which one regressed "\n'
    '        "(docs/product/GOLDEN_DATASET.yaml:54, docs/evidence/METRICS.md)"\n'
    "    )"
)
AUTO_APPLY_RAISE = (
    "    raise AutoApplyError(\n"
    '        "prompts, checks, severities and thresholds change by a commit a person '
    'writes. "\n'
    '        "This module stops at the proposal (docs/INVARIANTS.md N14, '
    'docs/CONSTITUTION.md P13)."\n'
    "    )"
)


MUTATIONS: tuple[Mutation, ...] = (
    Mutation(
        "store-path",
        "an evidence store may live inside the public repository",
        "evidence/store.py",
        "    if inside_repo(path):\n        raise StoreError(",
        "    if False:\n        raise StoreError(",
        "test_store_refuses_a_path_inside_the_repository",
    ),
    Mutation(
        "store-text",
        "clinical text may be stored without an explicit decision",
        "evidence/store.py",
        "    if any(r.text_stored for r in records) and not allow_text:",
        "    if False:",
        "test_store_refuses_text_without_the_flag",
    ),
    Mutation(
        "composite-score",
        "a composite score may be computed from the six axes",
        "evidence/scoring.py",
        COMPOSITE_RAISE,
        "    return",
        "test_no_composite_score_exists_anywhere",
    ),
    Mutation(
        "loop-applies",
        "the improvement loop may apply its own proposal",
        "evidence/loops.py",
        AUTO_APPLY_RAISE,
        "    return",
        "test_apply_is_refused",
    ),
    Mutation(
        "gate-under-two",
        "a gate over fewer than two paired cases may be analysed anyway",
        "evidence/regression.py",
        "        if n < 2:",
        "        if False:",
        "test_inconclusive_safety_gate_fails_closed",
    ),
    Mutation(
        "gate-from-nothing",
        "green gates over zero pairs may clear a release",
        "evidence/regression.py",
        "        return all(gate.passed for gate in self.gates) and self.comparable_pairs > 0",
        "        return all(gate.passed for gate in self.gates)",
        "test_a_report_of_no_pairs_never_reads_as_a_pass",
    ),
    Mutation(
        "csv-in-repo",
        "a CSV export may land inside the repository",
        "evidence/reporting.py",
        "    if store.inside_repo(destination):",
        "    if False:",
        "test_csv_export_refuses_the_repository",
    ),
    Mutation(
        "line-from-one-point",
        "a trend line may be drawn from a single period",
        "evidence/reporting.py",
        "    if len(usable) < 2:",
        "    if False:",
        "test_svg_refuses_to_draw_a_trend_from_one_point",
    ),
    Mutation(
        "thin-cell",
        "a cell thinner than k may still be exported",
        "evidence/reporting.py",
        "        if count < K_MIN",
        "        if count < 0",
        "test_thin_cells_are_flagged_before_export",
    ),
    Mutation(
        "self-ratification",
        "a case's author may ratify their own case",
        "evidence/groundtruth.py",
        "            if self.author and self.ratified_by == self.author:",
        "            if False:",
        "test_author_cannot_ratify_their_own_case",
    ),
    Mutation(
        "power-is-free",
        "more statistical power may cost the same sample size",
        "evidence/stats.py",
        "    table = {0.8: 0.841621234, 0.9: 1.281551566,",
        "    table = {0.8: 0.841621234, 0.9: 0.841621234,",
        "test_the_detectable_effect_is_pinned_to_an_absolute_number",
    ),
    Mutation(
        "wrong-quantile",
        "the power table may carry any constant",
        "evidence/stats.py",
        "    table = {0.8: 0.841621234,",
        "    table = {0.8: 0.674489750,",
        "test_the_detectable_effect_is_pinned_to_an_absolute_number",
    ),
    Mutation(
        "negation-scope",
        "extending a negation's scope may pass as a stylistic edit",
        "evidence/edits.py",
        '            reasons.append("negation_scope_extended")',
        "            pass",
        "test_negation_scope_extension_is_substantive",
    ),
    Mutation(
        "engine-drift",
        "the taxonomy may map a class onto a check the product no longer runs",
        "evidence/taxonomy.py",
        '        "format_breach",\n        "invented_identifier",',
        '        "invented_identifier",',
        "test_engine_check_ids_match_the_product_exactly",
    ),
)


#: Files the path-guard mutations legitimately create while proving they can be bypassed.
#: `test_store_refuses_a_path_inside_the_repository` asks for a path *inside* the tree, so with
#: the guard removed the write happens; the harness cleans up after its own experiments and
#: nothing else. Named explicitly rather than "delete whatever appeared", which would eat a
#: person's real store if they were mid-run.
DEBRIS = ("evidence.jsonl", "out.csv")


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def unrecoverable(paths: set[str]) -> list[str]:
    """Files whose committed content this harness could not restore into.

    Compared against `HEAD` with newlines normalised, not through `git status`: a status check
    reports a file as modified on mtime alone, which this harness causes itself on the second run,
    and Windows git keeps the working tree in CRLF while the repository holds LF. The rule being
    enforced is simple — if a break here crashed mid-run, `git checkout` must be able to put the
    file back exactly as it is now. An uncommitted file fails that test, so the harness refuses it.
    """
    problems = []
    for rel in sorted(paths):
        repo_rel = str((VALIDATION / rel).relative_to(REPO))
        shown = subprocess.run(
            ["git", "show", f"HEAD:{repo_rel}"],
            cwd=REPO,
            capture_output=True,
            check=False,
        )
        if shown.returncode != 0:
            problems.append(f"{repo_rel}: not committed, so a crash could not be undone")
            continue
        disk = (VALIDATION / rel).read_bytes().replace(b"\r\n", b"\n")
        if disk != shown.stdout:
            problems.append(f"{repo_rel}: differs from HEAD, and this harness would overwrite it")
    return problems


def run_test(name: str) -> tuple[int, int, int, str]:
    """Return (returncode, passed, failed_or_error, output) with the counts parsed apart."""
    # A restored file can keep the mutated file's mtime and size on a Windows mount, and CPython
    # then reuses the stale .pyc: the previous mutation would still be in force for the baseline.
    for cache in ("__pycache__", "evidence/__pycache__"):
        shutil.rmtree(VALIDATION / cache, ignore_errors=True)
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "-p",
            "no:cacheprovider",
            f"test_evidence.py::{name}",
        ],
        cwd=VALIDATION,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    out = ANSI.sub("", proc.stdout + proc.stderr)
    failed = sum(int(m) for m in re.findall(r"(\d+) failed", out))
    errors = sum(int(m) for m in re.findall(r"(\d+) error", out))
    passed = sum(int(m) for m in re.findall(r"(\d+) passed", out))
    return proc.returncode, passed, failed + errors, out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="check-refusals", description=__doc__.splitlines()[0])
    parser.add_argument(
        "filter", nargs="?", default="", help="only mutations whose id contains this"
    )
    parser.add_argument("--list", action="store_true", help="print the mutations and stop")
    args = parser.parse_args(argv)

    selected = [m for m in MUTATIONS if args.filter.lower() in m.identifier.lower()]
    if args.list:
        for mutation in selected:
            print(f"{mutation.identifier:20} {mutation.claim}")
        print(f"{len(selected)} of {len(MUTATIONS)} mutations")
        return 0
    if not selected:
        print(f"no mutation id contains {args.filter!r}; try --list", file=sys.stderr)
        return 2

    targets = {m.path for m in selected}
    blocked = unrecoverable(targets)
    if blocked:
        print(
            "refusing to run: these files are not identical to HEAD, so a crash here could not be"
            " undone by the harness:\n"
            + "\n".join(f"  {p}" for p in blocked)
            + "\nCommit them first, then run it.",
            file=sys.stderr,
        )
        return 2

    # Prove the baseline is green before breaking anything, or a caught mutation may be a test
    # that was already failing for an unrelated reason.
    code, passed, failed, out = run_test("test_codes_are_unique_and_namespaced")
    if code != 0 or passed != 1:
        print("refusing to run: a known-green baseline test is not green", file=sys.stderr)
        print(out[-400:], file=sys.stderr)
        return 2

    staging = Path(tempfile.mkdtemp(prefix="fk-refusals-"))
    preexisting = {
        path for base in (VALIDATION, REPO) for path in base.glob("*") if path.name in DEBRIS
    }
    try:
        for rel in targets:
            source = VALIDATION / rel
            source.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(source, staging / rel.replace("/", "__"))

        verdicts = []
        for mutation in selected:
            rel = mutation.path
            pristine = (staging / rel.replace("/", "__")).read_text(encoding="utf-8")
            if mutation.old not in pristine:
                verdicts.append((mutation, "SOURCE-MISS", "the guard's text is not in the file"))
                continue

            code, passed, failed, out = run_test(mutation.test)
            if code != 0 or passed != 1:
                verdicts.append(
                    (mutation, "BASELINE-BROKE", f"the test was not green first: {out[-160:]}")
                )
                continue

            target = VALIDATION / rel
            if sha(pristine) != sha(target.read_text(encoding="utf-8")):
                verdicts.append((mutation, "TREE-CHANGED", "the file moved while the harness ran"))
                break
            target.write_text(pristine.replace(mutation.old, mutation.new, 1), encoding="utf-8")
            try:
                code, passed, failed, out = run_test(mutation.test)
                caught = code != 0 and (failed >= 1 or "error" in out.lower())
                verdicts.append(
                    (
                        mutation,
                        "CAUGHT" if caught else "SURVIVED",
                        f"rc={code} passed={passed} failed={failed}",
                    )
                )
            finally:
                shutil.copy(staging / rel.replace("/", "__"), target)

        for mutation, verdict, detail in verdicts:
            head = f"{verdict:15} {mutation.identifier:20} {mutation.claim}"
            print(f"{head}  [{mutation.test}]  {detail}")

        survivors = [v for v in verdicts if v[1] != "CAUGHT"]
        print(f"\n{len(verdicts) - len(survivors)} of {len(verdicts)} refusals proved")

        drift = [
            rel
            for rel in targets
            if (staging / rel.replace("/", "__")).read_bytes() != (VALIDATION / rel).read_bytes()
        ]
        if drift:
            print("NOT RESTORED — restore these from git immediately:", ", ".join(sorted(drift)))
        return 1 if survivors or drift else 0
    finally:
        shutil.rmtree(staging, ignore_errors=True)
        for base in (VALIDATION, REPO):
            for name in DEBRIS:
                created = base / name
                if created.exists() and created not in preexisting:
                    created.unlink()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
