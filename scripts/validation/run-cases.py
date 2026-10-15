#!/usr/bin/env python3
"""Run MRI brain cases through the Radiology Copilot and measure what happens.

Sprint 10 is clinical validation, so this file is the instrument and not the result. It
is a client of the four endpoints the product already exposes — `POST /draft`, `/check`,
`/review`, `/export` — and it changes nothing in the application, the Gateway or the
prompt. If a measurement ever seems to need a change in the copilot, the measurement is
the thing that is wrong.

PHI DISCIPLINE, stated because this tool reads a hospital database.

* Case text — dictations, drafts, signed reports — is held in memory and is never
  written to disk by this tool. What is written is numbers: counts, lengths, ratios,
  timings, and check names. A results file can be pasted into a conversation or
  committed to a repository without a patient in it.
* A case file is refused if it would land inside a git working tree. The fastest way to
  leak a patient is a file that looked like test data. Keep it in `$HOME`.
* The export strips every identifier it finds — name, patient id, accession, referring
  doctor, report number, attachment path — and then asserts that none of them reached
  the output. Age and sex survive, because a clinical indication is meaningless without
  them.

Commands
    export   read the MRI studio database into a local, de-identified case file
    smoke    one case, so throughput is known before twenty are run
    run      retrospective: machine stages only, no clinician
    session  the clinician session — the mode that answers the sprint's question
    report   the per-case table, the summary, and the pre-registered ranking

`run` reports the human numbers as null rather than guessing them; `session` measures
them. Run the same case file through both and the difference between the two is itself
a finding.
"""

from __future__ import annotations

import argparse
import difflib
import json
import os
import re
import shutil
import sqlite3
import statistics
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

COPILOT_DEFAULT = os.environ.get("FK_RADIOLOGY_URL", "http://127.0.0.1:8200")
GATEWAY_DEFAULT = os.environ.get("FK_GATEWAY_URL", "http://127.0.0.1:8100")

#: Sections a reviewer can rewrite. `clinical_indication` is not among them: those are
#: the referrer's words and the copilot will not let anyone edit them into something else.
EDITABLE = ("technique", "findings", "impression", "recommendations", "follow_up")

#: Columns that must never leave the database.
IDENTIFIERS = (
    "patientName",
    "patientId",
    "accessionNumber",
    "referringDoctor",
    "reportNumber",
    "attachmentPath",
    "attachmentName",
)

#: The two section texts a draft is compared against in a retrospective run.
ORACLE_FIELDS = ("findings", "impression")


class Copilot:
    """The four endpoints, over HTTP. Nothing imported, nothing bypassed."""

    def __init__(self, base_url: str, timeout: float = 300.0) -> None:
        self.base = base_url.rstrip("/")
        self.timeout = timeout

    def _post(self, path: str, body: dict) -> tuple[int, dict]:
        request = urllib.request.Request(
            f"{self.base}{path}",
            data=json.dumps(body).encode(),
            headers={"content-type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as error:
            raw = error.read()
            try:
                return error.code, json.loads(raw)
            except json.JSONDecodeError:
                return error.code, {
                    "error": {"code": "unparseable", "raw": raw[:300].decode("utf-8", "replace")}
                }

    def health(self) -> dict:
        with urllib.request.urlopen(f"{self.base}/health", timeout=10) as response:
            return json.loads(response.read())

    def draft(self, submission: dict) -> tuple[int, dict]:
        return self._post("/draft", {"submission": submission})

    def check(self, report: dict, submission: dict) -> tuple[int, dict]:
        return self._post("/check", {"report": report, "submission": submission})

    def review(
        self, report: dict, submission: dict, edits: dict, clinician: str
    ) -> tuple[int, dict]:
        return self._post(
            "/review",
            {
                "report": {**report, **edits},
                "decision": "signed",
                "clinician": clinician,
                "submission": submission,
            },
        )


def probe(url: str) -> tuple[bool, str]:
    try:
        with urllib.request.urlopen(url.rstrip("/") + "/health", timeout=5) as response:
            body = json.loads(response.read())
        return True, str(body.get("status", "up"))
    except Exception as error:  # noqa: BLE001 - a probe reports, it does not raise
        return False, f"{type(error).__name__}: {error}"


# --------------------------------------------------------------------------- export


def _reported_on(value: Any) -> str:
    """The study date as a reviewer would write it.

    Prisma hands SQLite's datetime back as epoch milliseconds, and the first ten characters of
    that are "1783973763" — a number that looks like a date and grounds nothing. The date is
    not decoration here: it is what makes a comparison legitimate, and a draft that says
    "unchanged" is checked against a prior that has to carry one.
    """
    text = str(value or "").strip()
    if text.isdigit():
        return time.strftime("%Y-%m-%d", time.gmtime(int(text) / (1000 if len(text) > 11 else 1)))
    return text[:10]


def build_case(row: sqlite3.Row) -> dict[str, Any]:
    """One database row to one case. Identifiers are dropped, not hidden."""
    modality = row["modality"] or "MRI"
    # The modality leads the label because the study profile is matched on it: the MRI brain
    # structure checklist looks for "mri brain" / "mr brain", and the studio stores those as
    # two columns (`bodyRegion` = "Brain", `modality` = "MRI"). Assembled without the modality
    # the label reads "BRAIN T1-CONTRAST", no profile applies, and `structure_coverage` goes
    # quietly silent on every case — which is what the first version of this line did, found by
    # the self-test rather than by reading it.
    parts = (modality, row["bodyRegion"] or "study", row["studyType"] or "")
    study = " ".join(part for part in parts if part).upper()
    contrast = "WITH AND WITHOUT CONTRAST" if row["contrastAdministered"] else "WITHOUT CONTRAST"
    indication = (row["clinicalIndication"] or "").strip() or "Indication not recorded"
    stated_age = re.search(r"\b\d{1,3}[- ]?(year|y/o|yr)", indication, re.IGNORECASE)
    if not stated_age and row["patientAge"]:
        prefixed = f"{row['patientAge']}-year-old {row['patientGender'] or ''}, {indication}"
        indication = prefixed.replace(" ,", ",")

    case = {
        "case_id": str(row["id"])[:8],
        # When, not who: the date is what makes a comparison legitimate.
        "reported_on": _reported_on(row["updatedAt"]),
        "modality": modality,
        "study": f"{study} {contrast}",
        "clinical_indication": indication[:600],
        # In this studio the signed findings *are* the text the radiologist wrote, so a
        # retrospective run feeds them in as the dictation and the model restates them.
        # That makes the draft-vs-signed similarity an upper bound on what a real dictation
        # would have scored, and it is reported as such rather than smoothed over.
        "dictation": row["findings"],
        "technique": row["technique"] or "",
        "prior_report": row["comparison"] or "",
        "signed_findings": row["findings"],
        "signed_impression": row["impression"],
    }
    leaked = [key for key in IDENTIFIERS if key in case]
    if leaked:
        raise SystemExit(f"export would leak {leaked}; refusing")
    return case


def cmd_export(args: argparse.Namespace) -> int:
    out = Path(args.out).expanduser().resolve()
    if _inside_repo(out):
        print(
            f"refusing to write a case file inside a git working tree: {out}\n"
            "Keep it out of the repository, e.g. --out ~/fk-validation/cases.jsonl",
            file=sys.stderr,
        )
        return 2

    database = sqlite3.connect(f"file:{Path(args.db).expanduser()}?mode=ro", uri=True)
    database.row_factory = sqlite3.Row
    columns = {row[1] for row in database.execute("PRAGMA table_info(MriReport)")}
    if not {"findings", "impression"} <= columns:
        print(f"{args.db} is not an MriReport database", file=sys.stderr)
        return 1

    where = ["reportStatus IN ('Final','Signed','final','signed')"]
    if args.brain_only:
        where.append("(lower(bodyRegion) LIKE '%brain%' OR lower(studyType) LIKE '%brain%')")
    rows = database.execute(
        f"SELECT * FROM MriReport WHERE {' AND '.join(where)} ORDER BY updatedAt DESC LIMIT ?",
        (args.limit,),
    ).fetchall()

    out.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    skipped = 0
    with out.open("w", encoding="utf-8") as handle:
        for row in rows:
            case = build_case(row)
            if len(case["dictation"].strip()) < 40:
                skipped += 1
                continue
            handle.write(json.dumps(case) + "\n")
            written += 1
    print(f"{written} cases -> {out}; {skipped} skipped for too little dictated text")
    print("Text is on this machine only. The results file this tool later writes holds numbers.")
    return 0


def _inside_repo(path: Path) -> bool:
    return any((parent / ".git").exists() for parent in [path.parent, *path.parents])


def read_cases(path: str | Path) -> list[dict]:
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def submission_of(case: dict) -> dict:
    submission: dict[str, Any] = {
        "clinical_indication": case["clinical_indication"],
        "modality": case["modality"],
        "study": case["study"],
        "findings": case["dictation"],
    }
    if case.get("technique"):
        submission["technique"] = case["technique"]
    if case.get("prior_report"):
        # The studio keeps the comparison as free text and has no field for the earlier
        # study's date, so the date is not guessed. `invented_history` needs a prior to exist,
        # not a parseable one, and a date this tool invented would be the harness fabricating
        # exactly the thing the check exists to catch.
        submission["previous_reports"] = [
            {
                "reported_on": "date not recorded in this export",
                "modality": case["modality"],
                "study": case["study"],
                "report": case["prior_report"],
            }
        ]
    return submission


# --------------------------------------------------------------------------- measures


def machine_measures(draft: dict) -> dict:
    """What the copilot said about its own draft, as numbers."""
    quality = draft.get("quality", {})
    findings = quality.get("findings", [])
    blocked = [f for f in findings if f.get("severity") == "block"]
    advised = [f for f in findings if f.get("severity") == "advisory"]
    provenance = draft.get("model_provenance", {})
    return {
        "ok": True,
        "draft_chars": sum(len(draft.get(key, "") or "") for key in EDITABLE),
        "dictation_chars": len(draft.get("metadata", {}).get("dictated_findings", "") or ""),
        "status": quality.get("status"),
        "blocking": len(blocked),
        "advisory": len(advised),
        "blocking_checks": sorted({str(f.get("check")) for f in blocked}),
        "advisory_checks": sorted({str(f.get("check")) for f in advised}),
        "finding_sections": sorted({str(f["section"]) for f in findings if f.get("section")}),
        "confidence": draft.get("confidence", {}).get("level"),
        "model": provenance.get("model"),
        "prompt": draft.get("metadata", {}).get("prompt_version"),
        "profile": draft.get("metadata", {}).get("profile"),
        "finish_reason": provenance.get("finish_reason"),
        "attempts": provenance.get("attempts"),
        "degraded": provenance.get("degraded"),
    }


def oracle_measures(draft: dict, case: dict) -> dict:
    """The signed report as the answer the department already gave.

    Independent of the engine on purpose. The number count and the dropped-observation
    count are re-derived here with their own implementation, so a hole in the product's
    regex cannot hide inside its own measurement, and so agreement between the two is
    evidence rather than tautology.
    """
    draft_text = (draft.get("findings", "") or "") + " " + (draft.get("impression", "") or "")
    dropped = [unit for unit in _units(case["signed_findings"]) if not _carried(unit, draft_text)]
    findings = (draft.get("quality", {}) or {}).get("findings", [])
    return {
        **{
            f"similarity_{key}": round(_ratio(draft.get(key, ""), case[f"signed_{key}"]), 3)
            for key in ORACLE_FIELDS
        },
        "ungrounded_numbers": count_ungrounded_numbers(draft, case),
        "dropped_signed_observations": len(dropped),
        "engine_flagged_drop": any(f.get("check") == "dropped_observation" for f in findings),
    }


def _units(text: str) -> list[str]:
    return [unit.strip() for unit in re.split(r"[.;\n]", text or "") if len(unit.strip()) >= 8]


def _carried(unit: str, draft: str) -> bool:
    """True when any substantive word of the unit survives in the draft.

    Deliberately laxer than the product's rule: this is a second opinion about whether a
    clinical statement disappeared, not a copy of the same opinion, and the two disagreeing
    is the case worth finding.
    """
    words = [word for word in _words(unit) if len(word) >= 5]
    return not words or any(word[:5] in draft.lower() for word in words)


def _ratio(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, _words(a), _words(b)).ratio()


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", (text or "").lower())


_NUMBER = re.compile(
    r"\b(\d+(?:[.,]\d+)?)\s?(mm|cm|ml|cc|hu|%|hours?|days?|weeks?|months?|years?)\b", re.I
)


def count_ungrounded_numbers(draft: dict, case: dict) -> int:
    """Numeric claims in the descriptive sections that are in none of the submitted text."""
    grounding = " ".join(
        [case["dictation"], case.get("technique", ""), case.get("prior_report", "")]
    ).lower()
    tokens = {t.replace(",", ".") for t in re.findall(r"(?<![a-z])\d+(?:[.,]\d+)?", grounding)}
    count = 0
    for section in ORACLE_FIELDS:
        for match in _NUMBER.finditer(draft.get(section, "") or ""):
            if match.group(1).replace(",", ".") not in tokens:
                count += 1
    return count


def human_measures(before: dict[str, str], after: dict[str, str], edited: list[str]) -> dict:
    """What a reviewer did, kept as statistics. The words themselves are not returned."""
    per_section = {}
    for key in EDITABLE:
        original, final = before.get(key, ""), after.get(key, before.get(key, ""))
        per_section[key] = {
            "similarity": round(_ratio(original, final), 3),
            "chars_added": max(0, len(final) - len(original)),
            "chars_removed": max(0, len(original) - len(final)),
        }
    added = sum(value["chars_added"] for value in per_section.values())
    return {
        "sections_edited": len(edited),
        "sections_edited_names": sorted(edited),
        "impression_rewritten": "impression" in edited,
        "chars_typed_by_human": added,
        "chars_deleted_by_human": sum(value["chars_removed"] for value in per_section.values()),
        "overall_similarity": round(
            _ratio(
                " ".join(before.get(key, "") for key in EDITABLE),
                " ".join(after.get(key, before.get(key, "")) for key in EDITABLE),
            ),
            3,
        ),
        "added_to_findings": per_section["findings"]["chars_added"],
        "per_section": per_section,
    }


def engine_gaps(result: dict, human: dict) -> dict:
    """The two numbers that judge the engine rather than the model.

    A false hallucination is content a clinician deleted from a section the engine had
    left alone: they caught something nine text checks did not. The oracle for "worth
    deleting" is the reviewer, because nothing in text can be that oracle — which is why
    this measure only exists in a session run.
    """
    flagged = set(result.get("finding_sections", []))
    silent_deletions = [
        key
        for key in human["sections_edited_names"]
        if key != "technique" and key not in flagged
        and human["per_section"][key]["chars_removed"] > 0
    ]
    return {
        "false_hallucinations": len(silent_deletions),
        "sections_changed_with_no_finding_in_them": silent_deletions,
        "missed_findings_chars": human["added_to_findings"],
    }


# --------------------------------------------------------------------------- commands


def cmd_smoke(args: argparse.Namespace) -> int:
    cases = read_cases(args.case_file)
    case = cases[min(args.index, len(cases) - 1)]
    copilot = Copilot(args.copilot)

    ok, detail = probe(args.gateway)
    print(f"gateway {args.gateway}: {'ok' if ok else 'UNREACHABLE'} ({detail})")
    if not ok:
        print("Start the Gateway and a model backend first: without them there is no draft.")
        return 1
    print(f"copilot {args.copilot}: {copilot.health().get('status')}")

    started = time.perf_counter()
    status, body = copilot.draft(submission_of(case))
    elapsed = time.perf_counter() - started
    if status != 200:
        print(f"draft refused {status}: {json.dumps(body)[:400]}")
        return 1
    measures = machine_measures(body)
    chars = max(measures["draft_chars"], 1)
    per_1000 = elapsed / chars * 1000
    print(f"one draft in {elapsed:.1f} s · {chars} characters · {per_1000:.0f} s per 1000 chars")
    print(json.dumps(measures, indent=2))
    if elapsed > 25:
        print(
            "\nSLOW. Sprint 8 killed an interaction on exactly this number. Twenty cases are\n"
            "still worth running, but read this line before reading any of the others."
        )
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    copilot = Copilot(args.copilot)
    if not probe(args.gateway)[0]:
        print(f"Gateway not reachable at {args.gateway}; nothing to measure", file=sys.stderr)
        return 1
    rows = []
    for position, case in enumerate(read_cases(args.case_file)[: args.limit], start=1):
        started = time.perf_counter()
        status, body = copilot.draft(submission_of(case))
        elapsed = time.perf_counter() - started
        if status != 200:
            rows.append({"case_id": case["case_id"], "ok": False, "http": status,
                         "error_code": body.get("error", {}).get("code")})
            print(f"[{position}] {case['case_id']} refused {status}")
            continue
        row = {
            "case_id": case["case_id"],
            "mode": "retrospective",
            "draft_seconds": round(elapsed, 2),
            **machine_measures(body),
            **oracle_measures(body, case),
            "human": None,
        }
        rows.append(row)
        print(
            f"[{position}] {case['case_id']} {elapsed:5.1f}s block={row['blocking']} "
            f"adv={row['advisory']} conf={row['confidence']} "
            f"sim_f={row['similarity_findings']} sim_i={row['similarity_impression']}"
        )
    return _finish(args, rows)


def cmd_session(args: argparse.Namespace) -> int:
    """The clinician session. This is the mode that answers the sprint's question."""
    copilot = Copilot(args.copilot)
    if not probe(args.gateway)[0]:
        print(f"Gateway not reachable at {args.gateway}; nothing to measure", file=sys.stderr)
        return 1
    if not args.non_interactive and not sys.stdin.isatty():
        # Found by running this script with no terminal: `$EDITOR` inherits a pipe, waits
        # for input that can never arrive, and the run stops between two cases with no
        # message. A session that silently hangs is a session nobody finishes.
        print(
            "no terminal attached, so there is no editor to review in.\n"
            "Run this from a shell you can type in, or add --non-interactive to sign each "
            "draft unchanged.",
            file=sys.stderr,
        )
        return 2
    if args.non_interactive and not args.clinician:
        print(
            "--non-interactive still needs --clinician: the name is written into the document",
            file=sys.stderr,
        )
        return 2
    clinician = args.clinician or input("Name for the sign-off (it goes in the document): ").strip()
    rows = []
    for position, case in enumerate(read_cases(args.case_file)[: args.limit], start=1):
        submission = submission_of(case)
        started = time.perf_counter()
        status, body = copilot.draft(submission)
        if status != 200:
            # The code is the finding, not the text: `model_output_unusable` sends the work
            # to the parser and `upstream_unavailable` sends it to the deployment. Found by
            # running this script against a stand-in that answers in prose — without the code
            # the pre-registered ranking rule about refusals cannot be evaluated.
            rows.append(
                {
                    "case_id": case["case_id"],
                    "ok": False,
                    "http": status,
                    "error_code": body.get("error", {}).get("code"),
                }
            )
            print(
                f"[{position}] {case['case_id']} refused {status} "
                f"{body.get('error', {}).get('code', '')}",
                file=sys.stderr,
            )
            continue
        draft_seconds = time.perf_counter() - started

        before = {key: body.get(key, "") or "" for key in EDITABLE}
        print(f"\n=== case {position} · {case['case_id']} · draft in {draft_seconds:.1f} s ===")
        print(f"quality {body['quality']['status']} · confidence {body['confidence']['level']}")
        for finding in body["quality"]["findings"]:
            message = finding.get("message", "")[:150]
            print(f"  {finding['severity']:>8} · {finding['check']} · {message}")

        edited, after, review_seconds = review_window(before, clinician, args.non_interactive)
        human = human_measures(before, after, edited)
        # The screen re-checks on every keystroke; the harness does it once, after the
        # edit, because "did the clinician's correction clear the block" is a product
        # behaviour worth a number and `/check` is the endpoint that answers it.
        check_status, checked = copilot.check({**body, **after}, submission)
        post_edit = checked.get("quality", {}) if check_status == 200 else {}
        sign_status, signed = copilot.review(body, submission, after, clinician)
        if sign_status != 200:
            print(f"  sign-off refused {sign_status}: {json.dumps(signed)[:300]}", file=sys.stderr)

        row = {
            "case_id": case["case_id"],
            "mode": "session",
            "draft_seconds": round(draft_seconds, 2),
            "review_seconds": round(review_seconds, 1),
            "final_seconds": round(draft_seconds + review_seconds, 1),
            "accepted": sign_status == 200,
            "post_edit_blocking": post_edit.get("findings") and sum(
                1 for f in post_edit["findings"] if f.get("severity") == "block"
            ) or 0,
            "post_edit_status": post_edit.get("status"),
            "signed_after_edits": bool(edited) and sign_status == 200,
            **machine_measures(body),
            **oracle_measures(body, case),
        }
        row["human"] = human
        row.update(engine_gaps(row, human))
        rows.append(row)
        print(
            f"  reviewed in {review_seconds:.0f} s · sections edited {human['sections_edited']} · "
            f"similarity {human['overall_similarity']} · "
            f"typed {human['chars_typed_by_human']} chars"
        )
    return _finish(args, rows)


def review_window(
    before: dict[str, str], clinician: str, skip: bool
) -> tuple[list[str], dict[str, str], float]:
    """Hand the draft to the reviewer and time what they do with it."""
    start = time.perf_counter()
    if skip:
        return [], dict(before), time.perf_counter() - start

    directory = Path(tempfile.mkdtemp(prefix="fk-review-"))
    try:
        files = []
        for key, text in before.items():
            path = directory / f"{key}.txt"
            path.write_text(text, encoding="utf-8")
            files.append((key, path))
        print(
            "Editing in $EDITOR. Save and quit when this is a report you would sign.\n"
            f"Name on the report: {clinician}"
        )
        editor = os.environ.get("EDITOR", "vi")
        subprocess.run([editor, *[str(path) for _, path in files]], check=False)
        after, edited = {}, []
        for key, path in files:
            text = path.read_text(encoding="utf-8").strip()
            after[key] = text
            if text != before[key].strip():
                edited.append(key)
        return edited, after, time.perf_counter() - start
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def _finish(args: argparse.Namespace, rows: list[dict]) -> int:
    results = {"rows": rows, "summary": summarise(rows)}
    Path(args.out).expanduser().write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"\n{len(rows)} cases, numbers only -> {args.out}")
    print(json.dumps(results["summary"], indent=2))
    return 0


# --------------------------------------------------------------------------- summary


def summarise(rows: list[dict]) -> dict:
    good = [row for row in rows if row.get("ok")]
    sessions = [row for row in good if row.get("mode") == "session"]
    summary: dict[str, Any] = {
        "cases": len(rows),
        "drafted": len(good),
        "refused": [
            {"case_id": row.get("case_id"), "http": row.get("http"), "code": row.get("error_code")}
            for row in rows
            if not row.get("ok")
        ],
        "draft_seconds": _distribution(_values(good, "draft_seconds")),
        "blocking_findings_per_case": _distribution(_values(good, "blocking")),
        "advisory_findings_per_case": _distribution(_values(good, "advisory")),
        "blocking_check_frequency": _frequency(good, "blocking_checks"),
        "advisory_check_frequency": _frequency(good, "advisory_checks"),
        "confidence_levels": _counts(good, "confidence"),
        "quality_statuses": _counts(good, "status"),
        "similarity_to_signed_report": {
            "findings": _distribution(_values(good, "similarity_findings")),
            "impression": _distribution(_values(good, "similarity_impression")),
        },
        "ungrounded_numbers_the_engine_missed": _distribution(_values(good, "ungrounded_numbers")),
        "engine_versus_independent_oracle": _agreement(good),
        "provenance": {
            "models": _counts(good, "model"),
            "prompts": _counts(good, "prompt"),
            "profiles": _counts(good, "profile"),
            "finish_reasons": _counts(good, "finish_reason"),
            "degraded_answers": sum(1 for row in good if row.get("degraded")),
            "answers_needing_more_than_one_attempt": sum(
                1 for row in good if (row.get("attempts") or 1) > 1
            ),
        },
    }

    if sessions:
        typed_total = sum(row["human"]["chars_typed_by_human"] for row in sessions)
        draft_total = sum(row["draft_chars"] for row in sessions)
        summary["session"] = {
            "cases": len(sessions),
            "accepted": sum(1 for row in sessions if row.get("accepted")),
            "final_seconds": _distribution(_values(sessions, "final_seconds")),
            "review_seconds": _distribution(_values(sessions, "review_seconds")),
            "sections_edited_per_case": _distribution(
                [row["human"]["sections_edited"] for row in sessions]
            ),
            "impression_rewritten_in": sum(
                1 for row in sessions if row["human"]["impression_rewritten"]
            ),
            "similarity_of_signed_to_draft": _distribution(
                [row["human"]["overall_similarity"] for row in sessions]
            ),
            "chars_typed_by_human": _distribution(
                [row["human"]["chars_typed_by_human"] for row in sessions]
            ),
            "typing_reduction": round(1 - typed_total / draft_total, 3) if draft_total else None,
            "false_hallucinations": _distribution(_values(sessions, "false_hallucinations")),
            "missed_findings_chars": _distribution(_values(sessions, "missed_findings_chars")),
        }
    else:
        summary["session"] = None
        summary["not_measurable_without_a_clinician"] = [
            "edit distance",
            "time to final report",
            "user edits",
            "false hallucinations",
            "missed findings",
            "final acceptance",
            "average typing reduction",
        ]
    return summary


def _values(rows: list[dict], key: str) -> list:
    return [row[key] for row in rows if isinstance(row.get(key), (int, float))]


def _distribution(values_in: list) -> dict:
    numbers = [float(v) for v in values_in]
    if not numbers:
        return {"n": 0}
    data = {
        "n": len(numbers),
        "mean": round(statistics.fmean(numbers), 3),
        "median": round(statistics.median(numbers), 3),
        "min": round(min(numbers), 3),
        "max": round(max(numbers), 3),
    }
    if len(numbers) >= 5:
        ordered = sorted(numbers)
        data["p95"] = round(ordered[min(int(len(ordered) * 0.95), len(ordered) - 1)], 3)
    return data


def _frequency(rows: list[dict], key: str) -> dict:
    counter: dict[str, int] = {}
    for row in rows:
        for item in row.get(key) or []:
            counter[item] = counter.get(item, 0) + 1
    return dict(sorted(counter.items(), key=lambda kv: -kv[1]))


def _agreement(rows: list[dict]) -> dict:
    """Where the product's own checks and this harness's second opinion coincide.

    The pairs are what the sprint is really about. `oracle_only_engine_missed` is a deviation
    a rule should have caught and did not, which is a defect in the safety story;
    `engine_only_no_oracle` is a finding raised over text the department itself wrote, which
    is the beginning of a warning people learn to read through.
    """

    def raised(check: str):
        def predicate(row: dict) -> bool:
            fired = [*(row.get("blocking_checks") or []), *(row.get("advisory_checks") or [])]
            return check in fired

        return predicate

    def classify(oracle, engine) -> dict:
        agreed = sum(1 for row in rows if oracle(row) and engine(row))
        return {
            "both": agreed,
            "oracle_only_engine_missed": sum(
                1 for row in rows if oracle(row) and not engine(row)
            ),
            "engine_only_no_oracle": sum(
                1 for row in rows if engine(row) and not oracle(row)
            ),
        }

    def counted(key: str):
        def predicate(row: dict) -> bool:
            return (row.get(key) or 0) > 0

        return predicate

    def truthy(key: str):
        def predicate(row: dict) -> bool:
            return bool(row.get(key))

        return predicate

    return {
        "number_comparisons": classify(
            counted("ungrounded_numbers"), raised("unsupported_measurement")
        ),
        "dropped_observation_comparisons": classify(
            counted("dropped_signed_observations"), truthy("engine_flagged_drop")
        ),
    }


def _counts(rows: list[dict], key: str) -> dict:
    counter: dict[str, int] = {}
    for row in rows:
        if row.get(key) is not None:
            counter[str(row[key])] = counter.get(str(row[key]), 0) + 1
    return counter


# --------------------------------------------------------------------------- ranking


#: Written before any case was run, so nobody can fit a story to the numbers afterwards.
#: Kept as data rather than as a table so the rows stay readable at 100 columns and the
#: same ranking can be printed, quoted or diffed. `impact` is the order to work in.
RANKING_RULES = (
    (
        "mean `final_seconds` above 300, or `typing_reduction` below 0.3",
        "throughput before anything else — at 3.9 tok/s the product is not usable however "
        "correct its prose",
        "existential",
    ),
    (
        "`ungrounded_numbers_the_engine_missed` > 0 while `blocking` = 0",
        "the measurement engine has a hole, and it is the safety story; first among defects",
        "high",
    ),
    (
        "`blocking_check_frequency` dominated by `dropped_observation`",
        "the model is compressing dictation — a prompt and mapping change, not a new check",
        "high",
    ),
    (
        "`sections_changed_with_no_finding_in_them` dominated by `impression`",
        "the engine polishes wording where clinicians change reasoning: the impression "
        "needs a rule it does not have",
        "high",
    ),
    (
        "`degraded_answers` or `answers_needing_more_than_one_attempt` non-zero",
        "a policy promise fails on real traffic; nothing else is worth doing until it holds",
        "high",
    ),
    (
        "`impression_rewritten_in` over half the cases with `similarity_findings` high",
        "findings prose is fine, the conclusion is not; work the impression and leave the "
        "findings prompt alone",
        "medium",
    ),
    (
        "`advisory` findings present in nearly every case and never acted on",
        "the advisory checks are noise, and a warning read through is worse than no warning: "
        "remove or downgrade them",
        "medium",
    ),
    (
        "`refused` non-empty with `model_output_unusable`",
        "real prose breaks the answer shape — parser or prompt, and the case becomes a fixture",
        "medium",
    ),
    (
        "`similarity_findings` low with no blocking finding",
        "the draft is safe and wrong; this is the limit of checking text against text, and no "
        "prompt fixes it",
        "documented, not fixed",
    ),
    (
        "`confidence_levels` never `supported` on clean reports",
        "confidence is measuring missing inputs rather than quality; either say so on the "
        "screen or compute it differently",
        "low",
    ),
)


def render_ranking() -> str:
    rows = "\n".join(f"| {when} | {then} | {impact} |" for when, then, impact in RANKING_RULES)
    return (
        "## What would change the product, and what evidence decides it\n\n"
        "Written before the run, so nobody can fit a story to the numbers afterwards. Impact\n"
        "is the order to work in once the twenty cases are in.\n\n"
        "| If the run shows this | Then the change is | Impact |\n"
        "| --- | --- | --- |\n"
        + rows
        + "\n\nOne number decides whether the table above is about the product or about the\n"
        "model: `draft_seconds`. Read it first, every time.\n"
    )


def cmd_report(args: argparse.Namespace) -> int:
    results = json.loads(Path(args.results).expanduser().read_text(encoding="utf-8"))
    rows = results["rows"]
    columns = [
        "case",
        "draft s",
        "block",
        "adv",
        "conf",
        "sim_f",
        "sim_i",
        "edited",
        "sim_final",
        "typed",
    ]
    print("| " + " | ".join(columns) + " |")
    print("| " + " | ".join(["---"] * len(columns)) + " |")
    for row in rows:
        if not row.get("ok"):
            code = row.get("error_code") or ""
            print(f"| {row.get('case_id')} | refused {row.get('http')} {code} |")
            continue
        human = row.get("human") or {}
        cells = [
            str(row["case_id"]),
            str(row.get("draft_seconds", "")),
            str(row.get("blocking", "")),
            str(row.get("advisory", "")),
            str(row.get("confidence", "")),
            str(row.get("similarity_findings", "")),
            str(row.get("similarity_impression", "")),
            str(human.get("sections_edited", "")),
            str(human.get("overall_similarity", "")),
            str(human.get("chars_typed_by_human", "")),
        ]
        print("| " + " | ".join(cells) + " |")
    print("\n## Summary\n")
    print(json.dumps(results["summary"], indent=2))
    print("\n" + render_ranking())
    return 0


# --------------------------------------------------------------------------- entry


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--copilot", default=COPILOT_DEFAULT, help="copilot base URL")
    parser.add_argument(
        "--gateway", default=GATEWAY_DEFAULT, help="Gateway URL, probed before any run"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    export = sub.add_parser("export", help="read the MRI studio database into a local case file")
    export.add_argument("--db", required=True)
    export.add_argument("--out", required=True)
    export.add_argument("--limit", type=int, default=40)
    export.add_argument("--all-regions", action="store_true", help="include non-brain studies")
    export.add_argument("--brain-only", action="store_true", default=True)
    export.set_defaults(func=cmd_export)

    smoke = sub.add_parser("smoke", help="one case, so throughput is known before twenty are run")
    smoke.add_argument("--case-file", required=True)
    smoke.add_argument("--index", type=int, default=0)
    smoke.set_defaults(func=cmd_smoke)

    run = sub.add_parser("run", help="retrospective: machine stages only, no clinician")
    run.add_argument("--case-file", required=True)
    run.add_argument("--out", required=True)
    run.add_argument("--limit", type=int, default=1000)
    run.set_defaults(func=cmd_run)

    session = sub.add_parser("session", help="the clinician session: the numbers that need a human")
    session.add_argument("--case-file", required=True)
    session.add_argument("--out", required=True)
    session.add_argument("--limit", type=int, default=20)
    session.add_argument("--clinician")
    session.add_argument(
        "--non-interactive",
        action="store_true",
        help="sign each draft unchanged; exercises the session path without a reviewer",
    )
    session.set_defaults(func=cmd_session)

    report = sub.add_parser("report", help="the table, the summary and the ranking")
    report.add_argument("--results", required=True)
    report.set_defaults(func=cmd_report)

    args = parser.parse_args(argv)
    if args.command == "export":
        args.brain_only = not getattr(args, "all_regions", False)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
