#!/usr/bin/env python3
"""The radiologist-in-the-loop dashboard: twenty MRI brain studies, one afternoon.

Sprint 11 is evidence, not features, so this file changes nothing it measures. It is a
client of the endpoints the Radiology Copilot already exposes — `POST /draft`, `/check`,
`/review`, `/export` and `GET /health` — proxied behind one local origin so the browser
talks to exactly one process. Nothing here imports the application, the Gateway or a model,
and no metric can nudge a draft, a prompt or a policy: the instrument watches, the
radiologist decides. When the session ends it prints four ranked lists and stops. That is
the whole of its authority.

**The radiologist is the source of truth, so the numbers only they can give are asked for.**
Machine-derived measures — edit distance, words added, review seconds — come from what the
reviewer typed. Two measures no script can derive, *was this blocking finding a real
problem* and *was this advisory worth showing*, are asked as one tap per finding and stored
as their verdicts. A false-blocking rate this tool inferred from text would be this tool
grading its own homework.

WHAT IS WRITTEN, and where:

* `rows.csv` / `rows.json` — seconds, counts, check names, verdicts. No clinical text.
  These are what to hand to a meeting or paste into a conversation.
* `phrases.csv` / `phrases.json` and the four ranking files — the short spans the reviewer
  deleted or replaced, which are report fragments. They exist because "most frequently
  deleted AI phrases" is a stated requirement. The session directory is refused outright if
  it lies inside a git working tree (the `_inside_repo` guard in `run-cases.py`, reused).
* `rows.jsonl` — append-only, one line per closed study, so an afternoon survives a
  closed tab. Reopening the same directory resumes the session.

Usage:

    python scripts/validation/dashboard.py \
        --case-file ~/fk-validation/cases.jsonl \
        --clinician "Dr Abinash" \
        --gateway-log ~/fk-validation/gateway.log \
        --port 8300

Then open http://127.0.0.1:8300. `/report` is the printable end-of-session report.
"""

from __future__ import annotations

import argparse
import csv
import difflib
import importlib.util
import json
import re
import statistics
import sys
import threading
import time
import urllib.parse
from collections import Counter, defaultdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
RUN_CASES = HERE / "run-cases.py"
SCREEN = HERE / "dashboard.html"
COPILOT_DEFAULT = "http://127.0.0.1:8200"

#: The columns the brief names, in the brief's order, then the four a session alone shows:
#: `redrafts` is the difference between "edited" and "unusable", `started_from_scratch` is
#: the honest name for a study the reviewer abandoned, and the last two are the measures the
#: brief asks to be calculated rather than derived by hand afterwards.
COLUMNS = (
    "study_id",
    "skill",
    "model_alias",
    "model",
    "generation_seconds",
    "review_seconds",
    "approval_seconds",
    "edits",
    "words_added",
    "words_removed",
    "sections_edited",
    "checks_triggered",
    "blocking_findings",
    "advisory_findings",
    "final_approval",
    "redrafts",
    "started_from_scratch",
    "edit_distance",
    "typing_reduction_pct",
    "confidence_before_approval",
    "false_hallucinations",
    "verdicts_recorded",
    # The two absolute word counts, added because every percentage in this file is a ratio
    # and a percentage cannot answer "how many words did I not have to type today". They are
    # the machine's draft and the document that was signed, in words, for the same study.
    "words_in_draft",
    "words_signed",
)

#: Confidence is a word, not a number; the mean of the words needs an order, and this is the
#: order the product's own labels state it in.
CONFIDENCE_ORDINAL = {"supported": 2, "review-carefully": 1, "not-safe-to-sign": 0}
CONFIDENCE_NAME = {2: "supported", 1: "review-carefully", 0: "not-safe-to-sign"}

SPAN_KINDS = ("replaced", "deleted", "inserted")

#: How a span is called a *phrase* rather than noise: long enough to mean something, short
#: enough to be one clinical thought. The cap is generous on purpose — a whole invented
#: sentence is 15 words, and "the reviewer deleted this sentence" is the row a prompt author
#: needs most.
MIN_SPAN_CHARS = 4
MAX_SPAN_WORDS = 25


def load_harness():
    """Load `run-cases.py` by path — its name has a hyphen, so `import` cannot reach it.

    Reuse is the point rather than the convenience. If the dashboard measured edit distance
    one way and the CLI measured it another, the session would produce two numbers for one
    act and the sprint would turn into a debate about which tool was right.
    """
    spec = importlib.util.spec_from_file_location("fk_validation_harness", RUN_CASES)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


HARNESS = load_harness()
SECTIONS = HARNESS.EDITABLE


# --------------------------------------------------------------------------- spans


def normalise(span: str) -> str:
    """The phrase as a table key: lower case, one space, no trailing punctuation."""
    return re.sub(r"\s+", " ", span.lower()).strip(" .,;:")


def is_phrase(span: str) -> bool:
    words = span.split()
    return len(span.strip()) >= MIN_SPAN_CHARS and 1 <= len(words) <= MAX_SPAN_WORDS


def span_table(before: str, after: str) -> dict[str, list[str]]:
    """The exact words the reviewer replaced, deleted and typed, as short spans.

    `difflib` runs over the word list, so a span is a phrase and not a character run, and an
    edit that only moved a comma produces nothing. These three tables *are* "most frequently
    edited phrases" and "most frequently deleted AI phrases"; everything else in a session is
    a count of them.
    """
    left, right = HARNESS._words(before), HARNESS._words(after)
    out: dict[str, list[str]] = {kind: [] for kind in SPAN_KINDS}
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, left, right).get_opcodes():
        if tag == "equal":
            continue
        if tag == "replace":
            out["replaced"].append(" ".join(left[i1:i2]))
            out["inserted"].append(" ".join(right[j1:j2]))
        elif tag == "delete":
            out["deleted"].append(" ".join(left[i1:i2]))
        elif tag == "insert":
            out["inserted"].append(" ".join(right[j1:j2]))
    # Nothing is filtered here: `words_added` and `words_removed` count every span, including
    # the long ones a phrase table would drop. Filtering the spans before counting them is how
    # a 15-word deletion lands in the record as zero words removed.
    return {kind: [span for span in out[kind] if len(span.strip()) >= 2] for kind in SPAN_KINDS}


def alias_from_log(log_path: Path | None, request_id: str | None) -> str:
    """The alias this draft routed through, read off the Gateway's own audit line.

    The response envelope names the model that answered and never the alias — naming a model
    is not an input this platform accepts (ADR-0002) — so reporting the alias back would mean
    changing the Gateway, which this sprint forbids. The `skill_audit` line it already writes
    carries `request_id=` and `alias=` together, so the join happens here. No log, no alias.
    """
    if not log_path or not request_id or not log_path.exists():
        return ""
    try:
        lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ""
    # Return the first line that carries BOTH, not the first line that carries the id: the
    # Gateway writes several lines per request, and an early version of this function stopped
    # at the first one it found and reported no alias at all.
    for line in reversed(lines):
        if f"request_id={request_id}" in line:
            found = re.search(r"\balias=(\S+)", line)
            if found:
                return found.group(1)
    return ""


class ProductError(Exception):
    """The copilot refused. Its code travels, its clinical text never does."""

    def __init__(self, status: int, body: dict) -> None:
        self.status = status
        self.code = str((body.get("error") or {}).get("code", "unspecified"))
        super().__init__(f"copilot refused with {status} ({self.code})")


# --------------------------------------------------------------------------- session


class Session:
    """One afternoon: the case list, the drafts, the rows, and the files they become."""

    def __init__(
        self,
        cases: list[dict],
        clinician: str,
        out_dir: Path,
        copilot_base: str,
        gateway_log: Path | None = None,
        keep_phrases: bool = True,
    ) -> None:
        if HARNESS._inside_repo(out_dir.resolve()):
            raise SystemExit(
                f"refusing to write a session inside a git working tree: {out_dir}\n"
                "Phrase tables quote report text. Keep the session out of the repository."
            )
        self.cases = cases
        self.clinician = clinician
        self.out_dir = out_dir
        self.gateway_log = gateway_log
        self.keep_phrases = keep_phrases
        self.copilot = HARNESS.Copilot(copilot_base)
        self.skill = self._skill()
        self.rows: list[dict] = []
        self.phrases: list[dict] = []
        self.drafts: dict[str, dict] = {}
        self.meta: dict[str, dict] = {}
        self.redrafts: Counter[str] = Counter()
        self.opened: dict[str, float] = {}
        self.lock = threading.Lock()
        self.started_at = time.time()
        out_dir.mkdir(parents=True, exist_ok=True)

    # -- the product calls

    def _skill(self) -> str:
        try:
            return str(self.copilot.health().get("skill", ""))
        except Exception:  # noqa: BLE001 - a missing label is not a failed measurement
            return ""

    def generate(self, case_id: str, note: str = "") -> dict:
        case = self._case(case_id)
        body: dict[str, Any] = {"submission": HARNESS.submission_of(case)}
        if note:
            body["extra_instructions"] = {"reviewer_note": note}
        started = time.perf_counter()
        status, draft = self.copilot._post("/draft", body)
        elapsed = time.perf_counter() - started
        if status != 200:
            raise ProductError(status, draft)
        provenance = draft.get("model_provenance", {})
        with self.lock:
            if case_id in self.drafts:
                self.redrafts[case_id] += 1
            self.drafts[case_id] = draft
            self.meta[case_id] = {
                "generation_seconds": round(elapsed, 2),
                "gateway_latency_ms": provenance.get("latency_ms"),
                "request_id": provenance.get("request_id"),
                "alias": alias_from_log(self.gateway_log, provenance.get("request_id")),
            }
            self.opened.setdefault(case_id, time.time())
        return draft

    def recheck(self, case_id: str, sections: dict[str, str]) -> dict:
        """Ask the gate about the text as it now stands, which is what the screen does."""
        report = {**self._draft(case_id), **{key: sections.get(key, "") for key in SECTIONS}}
        status, checked = self.copilot.check(report, HARNESS.submission_of(self._case(case_id)))
        if status != 200:
            raise ProductError(status, checked)
        return checked

    def sign(self, case_id: str, sections: dict[str, str]) -> tuple[int, dict]:
        """Hand the edited text to the product's own gate, which may refuse it."""
        return self.copilot.review(
            self._draft(case_id),
            HARNESS.submission_of(self._case(case_id)),
            {key: sections.get(key, "") for key in SECTIONS},
            self.clinician,
        )

    def export_signed(self, signed: dict, fmt: str = "text") -> tuple[int, dict]:
        return self.copilot._post("/export", {"report": signed, "format": fmt})

    # -- the record

    def close_study(
        self,
        case_id: str,
        sections: dict[str, str],
        review_seconds: float,
        approval_seconds: float,
        verdicts: list[dict],
        approved: bool,
    ) -> dict:
        """Fold one reviewed study into the session. Every number in this file is born here."""
        draft = self._draft(case_id)
        before = {key: str(draft.get(key, "") or "") for key in SECTIONS}
        after = {key: str(sections.get(key, "") or "") for key in SECTIONS}
        if not approved:
            # A study the reviewer abandoned is not a study they edited. Diffing the draft
            # against an empty final version would report every section as rewritten and
            # every word as deleted, and the typing reduction would read as though they had
            # typed nothing at all when in fact they typed a report this instrument never saw.
            # So the text contributes nothing, and the time and the verdicts still count.
            after = dict(before)
        edited = [key for key in SECTIONS if after[key].strip() != before[key].strip()]
        spans = {key: span_table(before[key], after[key]) for key in SECTIONS}
        human = HARNESS.human_measures(before, after, edited)
        findings = draft.get("quality", {}).get("findings", [])
        blocking = [f for f in findings if f.get("severity") == "block"]
        advisory = [f for f in findings if f.get("severity") == "advisory"]
        flagged_sections = {str(f.get("section")) for f in findings if f.get("section")}

        meta = self.meta[case_id]
        if not meta["alias"]:
            # The Gateway writes its audit line just after the response arrives, so at draft
            # time the log can be a few milliseconds short. A review takes minutes, and by the
            # time the study closes the line is certainly there — leaving the column blank for
            # every fast local session would be the instrument losing data it can still get.
            meta["alias"] = alias_from_log(self.gateway_log, meta.get("request_id"))
        row: dict[str, Any] = {
            "study_id": case_id,
            "skill": self.skill,
            "model_alias": meta["alias"],
            "model": str(draft.get("model_provenance", {}).get("model", "")),
            "generation_seconds": meta["generation_seconds"],
            "review_seconds": round(review_seconds, 1),
            "approval_seconds": round(approval_seconds, 2),
            "edits": len(edited),
            "words_added": _word_count(spans, "inserted"),
            "words_removed": _word_count(spans, "deleted") + _word_count(spans, "replaced"),
            "sections_edited": ",".join(edited),
            "checks_triggered": ",".join(sorted({f.get("check", "") for f in findings})),
            "blocking_findings": len(blocking),
            "advisory_findings": len(advisory),
            "final_approval": "signed" if approved else "rejected",
            "redrafts": self.redrafts[case_id],
            "started_from_scratch": 0 if approved else 1,
            "edit_distance": round(1 - human["overall_similarity"], 3),
            # 0.0, not 100.0: a draft thrown away saved the reviewer no typing, whatever the
            # arithmetic on an unchanged section would otherwise say.
            "typing_reduction_pct": _typing_reduction(before, after) if approved else 0.0,
            "confidence_before_approval": str(draft.get("confidence", {}).get("level", "")),
            "false_hallucinations": HARNESS.engine_gaps(
                {"finding_sections": sorted(flagged_sections)}, human
            )["false_hallucinations"],
            "verdicts_recorded": len(verdicts),
            "words_in_draft": sum(len(text.split()) for text in before.values()),
            "words_signed": sum(len(text.split()) for text in after.values()) if approved else 0,
            # Not columns: the evidence the rankings are built from.
            "_blocking_checks": sorted({f.get("check", "") for f in blocking}),
            "_advisory_checks": sorted({f.get("check", "") for f in advisory}),
            "_verdicts": verdicts,
            "_advisory_acted_on": sorted(
                {f.get("check", "") for f in advisory if f.get("section") in edited}
            ),
            # An advisory raised against the document as a whole — the structure checklist is
            # one — has no section, so "did the reviewer act on it" has no answer in the text.
            # Counting those as ignored would report a usefulness of zero for checks the
            # product designed to be advisory-only.
            "_advisory_with_section": len([f for f in advisory if f.get("section")]),
            "_advisory_without_section": len([f for f in advisory if not f.get("section")]),
            "_blocking_untouched": sorted(
                {
                    f.get("check", "")
                    for f in blocking
                    if f.get("section") in SECTIONS
                    and before[f["section"]].strip() == after[f["section"]].strip()
                }
            ),
            "_spans": spans,
        }

        with self.lock:
            # One study, one row. A second sign-off on the same study — a double click, a
            # reopened tab, a resumed directory — is a correction of the first, not a second
            # observation. Appending would quietly move the acceptance rate and inflate every
            # mean, and the replay that found this was four rows of four studies.
            self.rows = [existing for existing in self.rows if existing["study_id"] != case_id]
            self.phrases = [p for p in self.phrases if p["study_id"] != case_id]
            self.rows.append(row)
            for key in SECTIONS:
                for kind in SPAN_KINDS:
                    for span in spans[key][kind]:
                        self.phrases.append(
                            {
                                "study_id": case_id,
                                "section": key,
                                "kind": kind,
                                "phrase": span,
                                "engine_had_a_finding_there": key in flagged_sections,
                            }
                        )
            self._append_log(row)
        return row

    def _append_log(self, row: dict) -> None:
        numbers = {key: row[key] for key in COLUMNS}
        with (self.out_dir / "rows.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(numbers) + "\n")
        # One line per study, replaced the same way on resume: the rankings are built from
        # these spans, and losing them to a restarted server would cost an afternoon re-run.
        entries = [p for p in self.phrases if p["study_id"] == row["study_id"]]
        with (self.out_dir / "phrases.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"study_id": row["study_id"], "phrases": entries}) + "\n")

    def resume(self) -> None:
        """Re-read both logs so a reopened directory continues the same afternoon.

        Append-only on disk, keyed by study in memory: the last line for a study is that
        study's record, which is what makes a re-signed report correct rather than doubled.
        """
        log = self.out_dir / "rows.jsonl"
        if log.exists():
            by_study: dict[str, dict] = {}
            for line in log.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                stored = json.loads(line)
                stored.setdefault("_verdicts", [])
                stored.setdefault(
                    "_spans", {key: {kind: [] for kind in SPAN_KINDS} for key in SECTIONS}
                )
                by_study[stored["study_id"]] = stored
            self.rows = list(by_study.values())
        phrase_log = self.out_dir / "phrases.jsonl"
        if phrase_log.exists():
            latest: dict[str, list] = {}
            for line in phrase_log.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    entry = json.loads(line)
                    latest[entry["study_id"]] = entry["phrases"]
            self.phrases = [
                phrase for entries in latest.values() for phrase in entries
            ]

    def done_ids(self) -> set[str]:
        with self.lock:
            return {row["study_id"] for row in self.rows}

    def _case(self, case_id: str) -> dict:
        return next(case for case in self.cases if case["case_id"] == case_id)

    def _draft(self, case_id: str) -> dict:
        with self.lock:
            if case_id not in self.drafts:
                raise KeyError(f"no draft has been generated for {case_id}")
            return self.drafts[case_id]


def _word_count(spans: dict[str, dict[str, list[str]]], kind: str) -> int:
    """Words, not spans: a reviewer who typed four words somewhere counts four words."""
    return sum(len(span.split()) for key in SECTIONS for span in spans[key][kind])


def _typing_reduction(before: dict[str, str], after: dict[str, str]) -> float:
    """1 − (what the reviewer typed ÷ what the draft produced), as a percentage.

    Typing *less* than the draft produced is the saving the product claims, so only added
    characters count against it; a deletion is a saving too, and a rewrite that keeps the
    length is measured by `edit_distance` rather than here.
    """
    produced = sum(len(text) for text in before.values())
    typed = sum(max(0, len(after[key]) - len(before[key])) for key in SECTIONS)
    if not produced:
        return 0.0
    return round((1 - typed / produced) * 100, 1)


# --------------------------------------------------------------------------- metrics


def _mean(values: list[float]) -> float | None:
    return round(statistics.fmean(values), 3) if values else None


def _median(values: list[float]) -> float | None:
    return round(statistics.median(values), 3) if values else None


def _percentiles(values: list[float]) -> dict:
    if not values:
        return {"n": 0}
    ordered = sorted(values)
    return {
        "n": len(ordered),
        "mean": _mean(values),
        "median": _median(values),
        "min": round(ordered[0], 2),
        "max": round(ordered[-1], 2),
        "p95": _percentile(ordered, 0.95),
    }


def _percentile(ordered: list[float], fraction: float) -> float:
    """Nearest-rank, no interpolation: with twenty studies the interpolated value is a lie."""
    return round(ordered[min(int(len(ordered) * fraction), len(ordered) - 1)], 2)


def metrics(rows: list[dict]) -> dict:
    """Every summary the brief asks for, from the rows and nothing else."""
    signed = [row for row in rows if row["final_approval"] == "signed"]
    review = [float(row["review_seconds"]) for row in rows]
    verdict_rows = [v for row in rows for v in row.get("_verdicts", [])]
    blocking_verdicts = [v for v in verdict_rows if v.get("severity") == "block"]
    advisory_verdicts = [v for v in verdict_rows if v.get("severity") == "advisory"]

    rewrite: dict[str, list[int]] = {}
    for row in rows:
        edited = [key for key in (row["sections_edited"] or "").split(",") if key]
        for key in SECTIONS:
            rewrite.setdefault(key, []).append(1 if key in edited else 0)

    confidence = [CONFIDENCE_ORDINAL.get(row["confidence_before_approval"]) for row in signed]
    confidence = [value for value in confidence if value is not None]
    blocking_total = sum(int(row["blocking_findings"]) for row in rows)
    attributable = sum(int(row.get("_advisory_with_section", 0)) for row in rows)
    without_section = sum(int(row.get("_advisory_without_section", 0)) for row in rows)
    acted = sum(1 for row in rows for _ in row.get("_advisory_acted_on", []))

    return {
        "studies_reviewed": len(rows),
        "studies_signed": len(signed),
        "acceptance_rate": round(len(signed) / len(rows), 3) if rows else None,
        "typing_reduction_pct": {
            "mean": _mean([float(row["typing_reduction_pct"]) for row in signed]),
            "median": _median([float(row["typing_reduction_pct"]) for row in signed]),
            "distribution": _percentiles([float(row["typing_reduction_pct"]) for row in signed]),
        },
        "edit_distance": {
            "mean": _mean([float(row["edit_distance"]) for row in rows]),
            "median": _median([float(row["edit_distance"]) for row in rows]),
            "distribution": _percentiles([float(row["edit_distance"]) for row in rows]),
        },
        "review_seconds": _percentiles(review),
        "average_review_time_seconds": _mean(review),
        "median_review_time_seconds": _median(review),
        "generation_seconds": _percentiles([float(row["generation_seconds"]) for row in rows]),
        "approval_seconds": _percentiles([float(row["approval_seconds"]) for row in rows]),
        "blocking_findings": {
            "total": blocking_total,
            "per_study": _percentiles([float(row["blocking_findings"]) for row in rows]),
        },
        "advisory_findings": {
            "total": sum(int(row["advisory_findings"]) for row in rows),
            "per_study": _percentiles([float(row["advisory_findings"]) for row in rows]),
        },
        "false_blocking_rate": {
            "by_radiologist_verdict": (
                round(
                    sum(1 for v in blocking_verdicts if v.get("verdict") == "not_a_problem")
                    / len(blocking_verdicts),
                    3,
                )
                if blocking_verdicts
                else None
            ),
            "blocking_verdicts_recorded": len(blocking_verdicts),
            "never_asked_fallback": "an inferred rate would be this tool grading itself",
            "untouched_sections_still_signed": sum(
                1 for row in rows for _ in row.get("_blocking_untouched", [])
            ),
        },
        "advisory_usefulness": {
            "shown": sum(int(row["advisory_findings"]) for row in rows),
            "attributable_to_a_section": attributable,
            "raised_against_the_document": without_section,
            "acted_on": acted,
            "rate": round(acted / attributable, 3) if attributable else None,
            "rate_note": (
                "over advisories that name a section; a document-level advisory has no text "
                "to change, so it is reported separately rather than scored as ignored"
                if not attributable
                else ""
            ),
            "by_radiologist_verdict": (
                round(
                    sum(1 for v in advisory_verdicts if v.get("verdict") == "real_problem")
                    / len(advisory_verdicts),
                    3,
                )
                if advisory_verdicts
                else None
            ),
        },
        "section_rewrite_frequency": {
            key: round(sum(flags) / len(rows), 3) if rows else None
            for key, flags in rewrite.items()
        },
        "average_confidence_before_approval": {
            "mean_ordinal": _mean(confidence),
            "reading": CONFIDENCE_NAME.get(
                int(round(statistics.fmean(confidence))) if confidence else 0, ""
            ),
            "levels": dict(Counter(row["confidence_before_approval"] for row in signed)),
        },
        "words": {
            "added_total": sum(int(row["words_added"]) for row in rows),
            "removed_total": sum(int(row["words_removed"]) for row in rows),
            "added_per_study": _mean([float(row["words_added"]) for row in rows]),
            "removed_per_study": _mean([float(row["words_removed"]) for row in rows]),
        },
        "redrafts": sum(int(row["redrafts"]) for row in rows),
        "studies_abandoned": sum(int(row["started_from_scratch"]) for row in rows),
        "false_hallucinations_total": sum(int(row["false_hallucinations"]) for row in rows),
        "checks_triggered_frequency": dict(
            Counter(
                check
                for row in rows
                for check in (row["checks_triggered"] or "").split(",")
                if check
            ).most_common()
        ),
    }


# --------------------------------------------------------------------------- analysis


def _share(part: float, whole: float) -> float | None:
    return round(part / whole, 3) if whole else None


def _words(row: dict, key: str) -> int:
    """A row resumed from a session written before this column existed has no word count.
    Read it as zero rather than crashing an afternoon's work over a schema change."""
    return int(row.get(key) or 0)


def analysis(rows: list[dict], *, elapsed_seconds: float, clinician: str) -> dict:
    """The readings a finished afternoon is asked to produce, from the recorded rows only.

    Twenty studies is not a sample that carries a confidence interval, so each block says what
    it measured and what it cannot. `trust` here is what the reviewer *did* against what the
    badge said — never what they believed, which no instrument records — and the trend is by
    closing order, not by clock, because a study reopened the next morning is one row.
    """
    signed = [row for row in rows if row["final_approval"] == "signed"]
    abandoned = [row for row in rows if row["final_approval"] != "signed"]
    review = [float(row["review_seconds"]) for row in rows]
    generation = [float(row["generation_seconds"]) for row in rows]
    approval = [float(row["approval_seconds"]) for row in rows]
    hands_on_keyboard = sum(review) + sum(approval)

    slowest = sorted(rows, key=lambda row: -float(row["review_seconds"]))[:3]
    section_edits = Counter(
        key for row in rows for key in (row["sections_edited"] or "").split(",") if key
    )
    drafted = sum(_words(row, "words_in_draft") for row in rows)
    final = sum(_words(row, "words_signed") for row in rows)
    typed_by_hand = sum(int(row["words_added"]) for row in rows)

    trust: dict[str, dict] = {}

    for level in CONFIDENCE_ORDINAL:
        group = [row for row in rows if row["confidence_before_approval"] == level]
        if not group:
            continue
        trust[level] = {
            "studies": len(group),
            "signed": sum(1 for row in group if row["final_approval"] == "signed"),
            "mean_edit_distance": _mean([float(row["edit_distance"]) for row in group]),
            "mean_review_seconds": _mean([float(row["review_seconds"]) for row in group]),
            "mean_words_added": _mean([float(int(row["words_added"])) for row in group]),
        }

    half = len(rows) // 2
    halves = {}
    for label, part in (("first_half", rows[:half]), ("second_half", rows[half:])):
        halves[label] = {
            "studies": len(part),
            "mean_blocking_findings": _mean([float(row["blocking_findings"]) for row in part]),
            "mean_advisory_findings": _mean([float(row["advisory_findings"]) for row in part]),
            "mean_edit_distance": _mean([float(row["edit_distance"]) for row in part]),
            "mean_review_seconds": _mean([float(row["review_seconds"]) for row in part]),
            "mean_typing_reduction_pct": _mean(
                [float(row["typing_reduction_pct"]) for row in part]
            ),
        }

    minutes_room = round(elapsed_seconds / 60, 1)
    minutes_hands = round(hands_on_keyboard / 60, 1)
    return {
        "session_summary": {
            "clinician": clinician,
            "studies": len(rows),
            "signed": len(signed),
            "abandoned": len(abandoned),
            "minutes_in_the_room": minutes_room,
            "minutes_reviewing": minutes_hands,
            "minutes_generating": round(sum(generation) / 60, 1),
            "share_of_measured_time_watching_the_model": _share(
                sum(generation), hands_on_keyboard + sum(generation)
            ),
            # A rate off an 18-second denominator is not a rate, it is noise dressed as one.
            "studies_per_hour": (
                round(len(rows) / (elapsed_seconds / 3600), 2) if elapsed_seconds >= 600 else None
            ),
            "consistency_warning": (
                (
                    "review time reported by the screen exceeds the wall clock of this "
                    "session, so the durations were supplied rather than lived — a scripted "
                    "run, not an afternoon"
                )
                if minutes_hands > minutes_room
                else ""
            ),
            "note": (
                "minutes_in_the_room is wall clock from launch to the last study closed and "
                "includes every pause; the review and generation totals do not"
            ),
        },
        "time_analysis": {
            "generation_seconds": _percentiles(generation),
            "review_seconds": _percentiles(review),
            "approval_seconds": _percentiles(approval),
            "slowest_reviews": [
                {
                    "study_id": row["study_id"],
                    "review_seconds": row["review_seconds"],
                    "blocking_findings": row["blocking_findings"],
                    "edit_distance": row["edit_distance"],
                }
                for row in slowest
            ],
        },
        "edit_analysis": {
            "drafts_accepted_untouched": sum(
                1 for row in signed if int(row["edits"]) == 0
            ),
            "sections_edited_total": sum(int(row["edits"]) for row in rows),
            "most_edited_section": (section_edits.most_common(1)[0][0] if section_edits else None),
            "edits_by_section": dict(section_edits),
            "words_added_total": typed_by_hand,
            "words_removed_total": sum(int(row["words_removed"]) for row in rows),
        },
        "acceptance_analysis": {
            "signed": len(signed),
            "abandoned": len(abandoned),
            "abandoned_after_a_supported_draft": sum(
                1
                for row in abandoned
                if row["confidence_before_approval"] == "supported"
            ),
            "redrafts": sum(int(row["redrafts"]) for row in rows),
            "studies_needing_a_redraft": sum(1 for row in rows if int(row["redrafts"]) > 0),
        },
        "trust_analysis": {
            "by_confidence_level": trust,
            "reading": (
                "what the reviewer did after each badge, not what they thought of it. A "
                "supported draft that was rewritten anyway is the interesting row: it means "
                "the gate passed something the radiologist did not trust"
            ),
            "blocking_findings_signed_without_a_verdict": sum(
                1 for row in rows for _ in row.get("_blocking_untouched", [])
            ),
        },
        "quality_trend": {
            **halves,
            "note": (
                "by closing order across one afternoon; two studies either way is a hint, "
                "not a result"
            ),
        },
        "reviewer_statistics": {
            "reviewers_in_this_session": 1,
            "clinician": clinician,
            "limit": (
                "one name is typed at launch, so per-reviewer comparison needs a name per "
                "study — recorded when a second reader joins the afternoon"
            ),
        },
        "productivity": {
            "words_the_model_wrote": drafted,
            "words_in_the_signed_reports": final,
            "words_the_reviewer_typed": typed_by_hand,
            "words_not_typed": max(final - typed_by_hand, 0),
            "words_not_typed_note": (
                "signed-report words that were not added by hand, so they came from the draft; "
                "an abandoned study contributes its typing but no signed words, which is why "
                "this is never larger than the drafts"
            ),
            "minutes_reviewing": round(hands_on_keyboard / 60, 1),
            "words_not_typed_per_minute_reviewing": (
                round((final - typed_by_hand) / (hands_on_keyboard / 60), 1)
                if hands_on_keyboard
                else None
            ),
        },
    }


# --------------------------------------------------------------------------- rankings


#: Where a repeated edit points. Kept as data so the mapping is readable, reviewable and
#: wrong in a way a person can disagree with — which is the only kind of claim a validation
#: report should make about a prompt it did not write.
PROMPT_POINTS_AT = {
    "impression": "the conclusion clause: what may be settled, and what must stay a differential",
    "findings": "the fidelity clause: carry every dictated observation, add nothing to them",
    "recommendations": "the action clause: who to refer to, and what not to advise",
    "follow_up": "the interval clause: state a time or state nothing",
    "technique": "the honesty clause about acquisition parameters never supplied",
}


def _tally(phrases: list[dict], kind: str) -> list[dict]:
    counts: dict[str, dict] = {}
    for entry in phrases:
        if entry["kind"] != kind or not is_phrase(entry["phrase"]):
            continue
        key = normalise(entry["phrase"])
        row = counts.setdefault(
            key,
            {
                "phrase": key,
                "times": 0,
                "sections": Counter(),
                "studies": set(),
                "engine_flagged_that_section": 0,
            },
        )
        row["times"] += 1
        row["sections"][entry["section"]] += 1
        row["studies"].add(entry["study_id"])
        row["engine_flagged_that_section"] += 1 if entry["engine_had_a_finding_there"] else 0
    ranked = sorted(counts.values(), key=lambda row: (-row["times"], row["phrase"]))
    return [
        {
            "phrase": row["phrase"],
            "times": row["times"],
            "sections": dict(row["sections"]),
            "studies": len(row["studies"]),
            "engine_flagged_that_section": row["engine_flagged_that_section"],
        }
        for row in ranked
    ]


def _shape(span: str) -> str:
    """What kind of sentence-fragment this is, without claiming to know its meaning."""
    text = span.lower()
    if re.search(r"\d", text):
        return "carries a number"
    if re.search(r"\b(normal|unremarkable|no |not |absent|clear)\b", text):
        return "states a negative or a normal"
    if re.search(r"\b(mild|small|tiny|minimal|possible|likely|suggest|consid|uncertain)\b", text):
        return "hedges or diminishes"
    if re.search(r"\b(refer|review|correlat|follow|advis|recommend|urgently|clinic)\b", text):
        return "names an action"
    return "describes a finding"


def rankings(rows: list[dict], phrases: list[dict]) -> dict:
    """The four lists the brief asks for at the end, generated from the session alone."""
    deleted = _tally(phrases, "deleted")
    replaced = _tally(phrases, "replaced")
    inserted = _tally(phrases, "inserted")

    verdict_counts: dict[tuple[str, str], Counter] = defaultdict(Counter)
    for row in rows:
        for verdict in row.get("_verdicts", []):
            verdict_counts[(verdict.get("severity", ""), verdict.get("check", ""))][
                verdict.get("verdict", "")
            ] += 1

    # 1. AI mistakes, ranked. Evidence, in the order a reviewer would want to see it: what
    #    the radiologist rejected, what they deleted, what they had to add themselves, and
    #    what the engine said nothing about.
    mistakes: list[dict] = []
    for (severity, check), tally in verdict_counts.items():
        mistakes.append(
            {
                "what": f"{severity} finding `{check}`",
                "kind": "rejected_by_radiologist" if tally.get("not_a_problem") else "confirmed",
                "times": sum(tally.values()),
                "refused_times": tally.get("not_a_problem", 0),
                "real_times": tally.get("real_problem", 0),
            }
        )
    mistakes.extend(
        {
            "what": row["phrase"],
            "kind": "text the reviewer deleted",
            "times": row["times"],
            "sections": row["sections"],
            "engine_flagged_that_section": row["engine_flagged_that_section"],
        }
        for row in deleted
    )
    mistakes.extend(
        {
            "what": row["phrase"],
            "kind": "text the reviewer rewrote",
            "times": row["times"],
            "sections": row["sections"],
            "engine_flagged_that_section": row["engine_flagged_that_section"],
        }
        for row in replaced
    )
    mistakes.extend(
        {
            "what": row["phrase"],
            "kind": "text the reviewer had to supply",
            "times": row["times"],
            "sections": row["sections"],
        }
        for row in inserted
    )
    for row in rows:
        if int(row["started_from_scratch"]):
            mistakes.append(
                {
                    "what": f"study {row['study_id']}",
                    "kind": "abandoned — the draft was not a starting point",
                    "times": 1,
                    "blocking_findings": row["blocking_findings"],
                }
            )
        for _ in range(int(row["redrafts"])):
            mistakes.append(
                {"what": f"study {row['study_id']}", "kind": "redrafted", "times": 1}
            )
    mistakes.sort(key=lambda item: -int(item["times"]))

    # 2. Human edits: the acts themselves, with the section they happened in.
    human_edits = [
        {"what": row["phrase"], "kind": kind, "times": row["times"], "sections": row["sections"]}
        for kind, table in (("replaced", replaced), ("deleted", deleted), ("added", inserted))
        for row in table
    ]
    human_edits.sort(key=lambda item: -int(item["times"]))

    # 3. Prompt opportunities: a frequent edit in a section points at that section's clause.
    #    No suggestion is written here; the evidence and the clause it lands on is all this
    #    knows, because "do not optimise anything automatically" is the instruction.
    by_section: dict[str, list[dict]] = defaultdict(list)
    for kind, table in (("deleted", deleted), ("replaced", replaced), ("added", inserted)):
        for row in table:
            for section, count in row["sections"].items():
                by_section[section].append(
                    {
                        **row,
                        "kind": kind,
                        "in_section": section,
                        "section_count": count,
                    }
                )
    prompts = []
    for section, entries in by_section.items():
        entries.sort(key=lambda row: -row["section_count"])
        for entry in entries[:20]:
            prompts.append(
                {
                    "observed": entry["phrase"],
                    "section": section,
                    "times": entry["section_count"],
                    "kind": entry["kind"],
                    "points_at": PROMPT_POINTS_AT.get(section, "this section's clause"),
                    "engine_had_a_finding_there": entry.get("engine_flagged_that_section", 0),
                }
            )
    prompts.sort(key=lambda row: -row["times"])

    # 4. Deterministic checks worth building: only where the engine said nothing *and* the
    #    reviewer still acted. A check for something nobody edits is a check for its own sake.
    silent = [row for row in deleted + replaced if not row.get("engine_flagged_that_section")]
    shapes: dict[str, dict] = {}
    for entry in silent:
        for section, count in entry["sections"].items():
            shape = _shape(entry["phrase"])
            key = f"{shape} in {section}"
            row = shapes.setdefault(
                key,
                {"pattern": key, "times": 0, "examples": [], "engine_findings_there": 0},
            )
            row["times"] += count
            if len(row["examples"]) < 3:
                row["examples"].append(entry["phrase"])
    checks = sorted(shapes.values(), key=lambda row: -row["times"])

    return {
        "top_ai_mistakes": mistakes[:20],
        "top_human_edits": human_edits[:20],
        "top_prompt_opportunities": prompts[:20],
        "top_checks_worth_building": checks[:20],
    }


# --------------------------------------------------------------------------- export


def _numbers(row: dict) -> dict:
    """The row as it leaves this process: the recorded columns, and nothing else.

    The underscore keys are the evidence the rankings are built from — spans, verdicts, the
    section the engine flagged. They stay in memory and in `rows.jsonl`'s absence by design:
    what a meeting reads is numbers, and what a session keeps is text fragments.
    """
    return {key: row[key] for key in COLUMNS if key in row}


def _report_payload(session: Session) -> dict:
    return {
        "metrics": metrics(session.rows),
        "rankings": rankings(session.rows, session.phrases),
        "analysis": analysis(
            session.rows,
            elapsed_seconds=time.time() - session.started_at,
            clinician=session.clinician,
        ),
    }


def write_files(session: Session) -> dict[str, str]:
    """Numbers always, phrases when asked for, and a printed report either way."""
    rows = [_numbers(row) for row in session.rows]
    out = session.out_dir
    payload = _report_payload(session)
    measures, tables, reading = (
        payload["metrics"],
        payload["rankings"],
        payload["analysis"],
    )

    _write_csv(out / "rows.csv", COLUMNS, rows)
    (out / "rows.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")
    (out / "metrics.json").write_text(json.dumps(measures, indent=2), encoding="utf-8")
    (out / "analysis.json").write_text(json.dumps(reading, indent=2), encoding="utf-8")

    written = {
        "rows_csv": str(out / "rows.csv"),
        "rows_json": str(out / "rows.json"),
        "metrics_json": str(out / "metrics.json"),
        "analysis_json": str(out / "analysis.json"),
    }
    for name, table in tables.items():
        if not table:
            continue
        keys = tuple(dict.fromkeys(key for row in table for key in row))
        flat = [{key: _cell(row.get(key)) for key in keys} for row in table]
        _write_csv(out / f"{name}.csv", keys, flat)
        (out / f"{name}.json").write_text(json.dumps(table, indent=2), encoding="utf-8")
        written[name] = str(out / f"{name}.csv")

    if session.keep_phrases and session.phrases:
        _write_csv(
            out / "phrases.csv",
            ("study_id", "section", "kind", "phrase", "engine_had_a_finding_there"),
            session.phrases,
        )
        (out / "phrases.json").write_text(json.dumps(session.phrases, indent=2), encoding="utf-8")
        written["phrases_csv"] = str(out / "phrases.csv")

    report = render_report(measures, tables, session, reading)
    (out / "report.md").write_text(report, encoding="utf-8")
    written["report_md"] = str(out / "report.md")
    return written


def _cell(value: Any) -> Any:
    if isinstance(value, (dict, list, tuple, set)):
        return json.dumps(sorted(value) if isinstance(value, set) else value, default=str)
    return value


def _write_csv(path: Path, columns: tuple[str, ...] | tuple, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(columns), extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def render_report(measures: dict, tables: dict, session: Session, reading: dict) -> str:
    lines = [
        f"# Radiology Copilot validation session — {session.clinician}",
        "",
        f"{measures['studies_reviewed']} studies reviewed, {measures['studies_signed']} signed, "
        f"{measures['studies_abandoned']} abandoned, "
        f"{measures['redrafts']} redrafts requested.",
        "",
        "## What the afternoon measured",
        "",
        "| Measure | Value |",
        "| --- | --- |",
    ]
    for label, value in (
        ("Typing reduction, mean %", measures["typing_reduction_pct"]["mean"]),
        ("Typing reduction, median %", measures["typing_reduction_pct"]["median"]),
        ("Edit distance, mean", measures["edit_distance"]["mean"]),
        ("Acceptance rate", measures["acceptance_rate"]),
        ("Average review time, s", measures["average_review_time_seconds"]),
        ("Median review time, s", measures["median_review_time_seconds"]),
        ("Generation time, mean s", measures["generation_seconds"]["mean"]),
        ("Generation time, p95 s", measures["generation_seconds"]["p95"]),
        ("Blocking findings, total", measures["blocking_findings"]["total"]),
        (
            "False blocking rate, by the radiologist",
            measures["false_blocking_rate"]["by_radiologist_verdict"],
        ),
        ("Advisory findings, shown", measures["advisory_usefulness"]["shown"]),
        ("Advisory usefulness (acted on)", measures["advisory_usefulness"]["rate"]),
        (
            "Advisories called real by the radiologist",
            measures["advisory_usefulness"]["by_radiologist_verdict"],
        ),
        (
            "Confidence before approval, mean",
            measures["average_confidence_before_approval"]["reading"],
        ),
        (
            "Text the reviewer removed that the engine had not flagged",
            measures["false_hallucinations_total"],
        ),
    ):
        lines.append(f"| {label} | {value if value is not None else '—'} |")
    lines += ["", "### Section rewrite frequency", ""]
    for key, share in measures["section_rewrite_frequency"].items():
        lines.append(f"- `{key}`: {share}")

    session_summary = reading["session_summary"]
    productivity = reading["productivity"]
    lines += [
        "",
        "## Where the afternoon went",
        "",
        f"- {session_summary['minutes_in_the_room']} minutes in the room, "
        f"{session_summary['minutes_reviewing']} of them on the keyboard, "
        f"{session_summary['minutes_generating']} watching the model write "
        f"({session_summary['share_of_measured_time_watching_the_model']} of measured time)",
        f"- {session_summary['studies_per_hour'] or 'not enough session to rate'} studies an "
        f"hour, {session_summary['studies']} studies for {session_summary['clinician']}",
        f"- p95 review {reading['time_analysis']['review_seconds'].get('p95', '—')} s, "
        f"p95 generation {reading['time_analysis']['generation_seconds'].get('p95', '—')} s",
        "",
        "| Slowest reviews | seconds | blocking findings | edit distance |",
        "| --- | --- | --- | --- |",
    ]
    for row in reading["time_analysis"]["slowest_reviews"]:
        lines.append(
            f"| {row['study_id']} | {row['review_seconds']} | "
            f"{row['blocking_findings']} | {row['edit_distance']} |"
        )

    edits = reading["edit_analysis"]
    acceptance = reading["acceptance_analysis"]
    lines += [
        "",
        "## What the reviewer did with the draft",
        "",
        f"- {edits['drafts_accepted_untouched']} of {measures['studies_signed']} signed "
        f"drafts accepted untouched",
        f"- most edited section: `{edits['most_edited_section'] or '—'}`; "
        f"{edits['words_added_total']} words typed by hand, "
        f"{edits['words_removed_total']} of the machine's words removed",
        f"- {acceptance['abandoned']} abandoned, "
        f"{acceptance['abandoned_after_a_supported_draft']} of them after the badge said "
        f"*supported* — the row worth reading first",
        f"- {acceptance['studies_needing_a_redraft']} studies needed a redraft "
        f"({acceptance['redrafts']} redrafts in all)",
        "",
        "## What the machine wrote that was kept",
        "",
        f"- {productivity['words_the_model_wrote']} words drafted, "
        f"{productivity['words_in_the_signed_reports']} words signed, "
        f"{productivity['words_the_reviewer_typed']} words typed by hand",
        f"- **{productivity['words_not_typed']} words the radiologist did not type**, at "
        f"{productivity['words_not_typed_per_minute_reviewing']} per minute of reviewing",
        f"- {productivity['words_not_typed_note']}",
        "",
        "## Trust, read from what the reviewer did",
        "",
        "| Badge before approval | studies | signed | mean edit distance | mean review s | "
        "mean words added |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for level, values in reading["trust_analysis"]["by_confidence_level"].items():
        lines.append(
            f"| {level} | {values['studies']} | {values['signed']} | "
            f"{values['mean_edit_distance']} | {values['mean_review_seconds']} | "
            f"{values['mean_words_added']} |"
        )
    lines += ["", f"*{reading['trust_analysis']['reading']}*", "", "## Across the afternoon", ""]
    for label in ("first_half", "second_half"):
        part = reading["quality_trend"][label]
        count = part["studies"]
        lines.append(
            f"- {label.replace('_', ' ')} ({count} "
            f"{'study' if count == 1 else 'studies'}): blocking "
            f"{part['mean_blocking_findings']}, advisory {part['mean_advisory_findings']}, "
            f"edit distance {part['mean_edit_distance']}, review "
            f"{part['mean_review_seconds']} s, typing reduction "
            f"{part['mean_typing_reduction_pct']}%"
        )
    lines.append(f"*{reading['quality_trend']['note']}*")
    if session_summary["consistency_warning"]:
        lines += ["", f"**Warning:** {session_summary['consistency_warning']}."]

    for title, key in (
        ("Top AI mistakes", "top_ai_mistakes"),
        ("Top human edits", "top_human_edits"),
        ("Top prompt opportunities", "top_prompt_opportunities"),
        ("Top deterministic checks worth building", "top_checks_worth_building"),
    ):
        lines += ["", f"## {title}", ""]
        rows = tables[key]
        if not rows:
            lines.append("Nothing recorded yet.")
            continue
        columns = tuple(dict.fromkeys(name for row in rows for name in row))
        lines.append("| " + " | ".join(columns) + " |")
        lines.append("| " + " | ".join(["---"] * len(columns)) + " |")
        for row in rows:
            cells = [str(_cell(row.get(name, ""))).replace("|", "/") for name in columns]
            lines.append("| " + " | ".join(cells) + " |")
    lines += [
        "",
        "## What this report does not do",
        "",
        "It ranks evidence and stops. No prompt, no check, no policy and no model was changed "
        "by the session or by this file, and the rankings are the radiologist's to disagree "
        "with. The engine is not scored here: the source of truth for this sprint is the "
        "person who signed the reports.",
    ]
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------- server


def make_handler(session: Session):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        server_version = "fk-validation-dashboard/1"

        def log_message(self, fmt: str, *args: Any) -> None:
            """Access logs off: the paths carry study ids and the referer would say more."""

        # -- plumbing

        def _send(self, status: int, body: bytes | str, content_type: str) -> None:
            """One place that turns a payload into a response.

            `str` is accepted and encoded because the first version of the report route handed
            the writer a string, `len()` counted characters while the socket wrote bytes, and
            the browser sat waiting for a body that never finished arriving.
            """
            payload = body.encode("utf-8") if isinstance(body, str) else body
            self.send_response(status)
            self.send_header("content-type", content_type)
            self.send_header("content-length", str(len(payload)))
            self.send_header("cache-control", "no-store")
            self.end_headers()
            self.responded = True
            self.wfile.write(payload)

        def _json(self, status: int, payload: dict) -> None:
            self._send(status, json.dumps(payload, default=str).encode(), "application/json")

        def _body(self) -> dict:
            length = int(self.headers.get("content-length") or 0)
            raw = self.rfile.read(length) if length else b"{}"
            return json.loads(raw or b"{}")

        # -- routes
        #
        # Every route runs inside a guard. A validation instrument that dies mid-session takes
        # the radiologist's afternoon with it, and an unhandled exception in a plain
        # BaseHTTPRequestHandler closes the socket with no response at all — the browser tab
        # shows nothing and the reviewer has no idea the measurement was lost.

        #: Whether a response has already started on this connection.
        responded = False

        def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler's name
            self.responded = False
            try:
                self._get()
            except Exception as error:  # noqa: BLE001 - a broken measurement must not hang the tab
                self._safe_error(error)

        def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler's name
            self.responded = False
            try:
                self._post()
            except Exception as error:  # noqa: BLE001 - a broken measurement must not hang the tab
                self._safe_error(error)

        def _safe_error(self, error: Exception) -> None:
            if self.responded:
                # The headers are already on the wire; a second response would be body content
                # that looks like a response, which is how a truncated page becomes a hang.
                return
            if isinstance(error, ProductError):
                # The refusal is reported; the report text never is.
                self._json(error.status, {"error": {"code": error.code}, "signable": False})
            elif isinstance(error, (KeyError, ValueError, TypeError)):
                self._json(400, {"error": f"{type(error).__name__}: {error}"})
            else:
                self._json(500, {"error": f"{type(error).__name__}: {error}"})

        def _get(self) -> None:
            path = urllib.parse.urlparse(self.path).path
            if path in ("/", "/index.html"):
                if not SCREEN.exists():
                    self._json(500, {"error": f"{SCREEN} is missing beside this script"})
                    return
                self._send(200, SCREEN.read_bytes(), "text/html; charset=utf-8")
            elif path == "/api/state":
                self._json(200, _state(session))
            elif path == "/api/report":
                self._json(200, _report_payload(session))
            elif path == "/report":
                payload = _report_payload(session)
                page = render_report(
                    payload["metrics"], payload["rankings"], session, payload["analysis"]
                )
                self._send(200, _report_html(page), "text/html; charset=utf-8")
            elif path == "/api/rows":
                self._json(200, {"rows": [_numbers(row) for row in session.rows]})
            else:
                self._json(404, {"error": "no such route"})

        def _post(self) -> None:
            path = urllib.parse.urlparse(self.path).path
            body = self._body()
            study_id = body.get("study_id", "")
            if path == "/api/generate":
                draft = session.generate(study_id, body.get("note", ""))
                self._json(200, {"draft": _strip(draft), "meta": session.meta[study_id]})
            elif path == "/api/check":
                checked = session.recheck(study_id, body["sections"])
                self._json(
                    200,
                    {
                        "quality": checked.get("quality", {}),
                        "confidence": checked.get("confidence", {}),
                    },
                )
            elif path == "/api/sign":
                # Approval time is measured here, not reported by the browser: the call is the
                # act, and a client-supplied duration would be a number the instrument cannot
                # check. On a local socket it rounds to 0.0, which is the honest reading.
                started = time.perf_counter()
                status, signed = session.sign(study_id, body["sections"])
                elapsed = time.perf_counter() - started
                if status != 200:
                    self._json(status, {"error": signed.get("error", {}), "signable": False})
                    return
                row = session.close_study(
                    study_id,
                    body["sections"],
                    float(body.get("review_seconds", 0)),
                    elapsed,
                    body.get("verdicts", []),
                    approved=True,
                )
                self._json(200, {"signed": True, "row": _numbers(row)})
            elif path == "/api/reject":
                row = session.close_study(
                    study_id,
                    body.get("sections", {}),
                    float(body.get("review_seconds", 0)),
                    0.0,
                    body.get("verdicts", []),
                    approved=False,
                )
                self._json(200, {"row": _numbers(row)})
            elif path == "/api/export":
                self._json(200, {"written": write_files(session)})
            else:
                self._json(404, {"error": "no such route"})

    return Handler


def _strip(draft: dict) -> dict:
    return {key: draft.get(key, "") for key in ("clinical_indication", *SECTIONS)} | {
        "quality": draft.get("quality", {}),
        "confidence": draft.get("confidence", {}),
        "metadata": draft.get("metadata", {}),
        "model_provenance": draft.get("model_provenance", {}),
    }


def _state(session: Session) -> dict:
    done = session.done_ids()
    return {
        "clinician": session.clinician,
        "skill": session.skill,
        "copilot": session.copilot.base,
        "studies": [
            {
                "study_id": case["case_id"],
                "study": case["study"],
                "state": "done" if case["case_id"] in done else "todo",
            }
            for case in session.cases
        ],
        "reviewed": len(done),
        "total": len(session.cases),
        "elapsed_seconds": round(time.time() - session.started_at),
    }


def _report_html(markdown: str) -> str:
    """The end-of-session report as one printable page. Markdown in, no renderer needed.

    Written by hand because nothing here may come from a CDN: the machine this runs on is a
    hospital machine, and a stylesheet that has to leave it to render a report is a report
    that cannot be read offline.
    """
    out: list[str] = []
    table: list[list[str]] = []

    def flush() -> None:
        if not table:
            return
        rows = [
            "<tr>" + "".join(f"<{tag}>{cell}</{tag}>" for cell in row) + "</tr>"
            for index, row in enumerate(table)
            for tag in ("th" if index == 0 else "td",)
        ]
        out.append("<table>" + "".join(rows) + "</table>")
        table.clear()

    for line in markdown.splitlines():
        if line.startswith("|"):
            if set(line.replace("|", "").strip()) <= {"-", " "}:
                continue
            table.append([cell.strip() for cell in line.strip().strip("|").split("|")])
            continue
        flush()
        if line.startswith("#"):
            level = min(len(line) - len(line.lstrip("#")), 4)
            out.append(f"<h{level}>{line.lstrip('# ')}</h{level}>")
        elif line.startswith("- "):
            out.append(f"<p>• {line[2:]}</p>")
        elif line.strip():
            out.append(f"<p>{line}</p>")
    flush()
    return (
        "<!doctype html><meta charset=utf-8><title>Validation session report</title>"
        "<style>body{font:15px/1.5 system-ui;max-width:1100px;margin:2rem auto;padding:0 1rem;"
        "color:#111}table{border-collapse:collapse;width:100%;font-size:13px}"
        "td,th{border:1px solid #ccc;padding:4px 6px;text-align:left;vertical-align:top}"
        "th{background:#f2f2f2}h2{margin-top:2rem}</style>" + "\n".join(out)
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--case-file", required=True)
    parser.add_argument("--clinician", required=True, help="the name that goes on the reports")
    parser.add_argument("--copilot", default=COPILOT_DEFAULT)
    parser.add_argument(
        "--gateway-log",
        help="the Gateway's log file, read to report the alias the draft routed through",
    )
    parser.add_argument("--out", default=str(Path.home() / "fk-validation" / "session"))
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--port", type=int, default=8300)
    parser.add_argument(
        "--no-phrases",
        action="store_true",
        help="do not write the phrase tables at all; the phrase rankings are then empty too",
    )
    args = parser.parse_args(argv)

    cases = HARNESS.read_cases(args.case_file)[: args.limit]
    if not cases:
        print("the case file is empty", file=sys.stderr)
        return 1
    out_dir = Path(args.out).expanduser()
    session = Session(
        cases=cases,
        clinician=args.clinician,
        out_dir=out_dir,
        copilot_base=args.copilot,
        gateway_log=Path(args.gateway_log).expanduser() if args.gateway_log else None,
        keep_phrases=not args.no_phrases,
    )
    session.resume()
    if not session.skill:
        print(
            f"WARNING: the copilot at {args.copilot} is not answering /health. "
            "Nothing can be measured until it is.",
            file=sys.stderr,
        )

    handler = make_handler(session)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), handler)
    print(f"Radiology Copilot validation session: http://127.0.0.1:{args.port}")
    print(f"{len(cases)} studies · reviewer {args.clinician} · rows to {out_dir / 'rows.jsonl'}")
    print("The dashboard only measures. It changes no draft, no prompt and no policy.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        written = write_files(session)
        print("\nStopped. Wrote:")
        for name, path in written.items():
            print(f"  {name:26} {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
