#!/usr/bin/env python3
"""The dashboard's arithmetic, tested without a server, a model or a clinician.

`dashboard.py` is only useful if its numbers are the numbers a person would compute by hand,
and a live session cannot be re-run to prove that — it needs a radiologist. So every measure
in this file is checked against an expectation written out longhand here: four words added to
a section, one study abandoned, one blocking finding judged wrong. Where two tools could
disagree, the disagreement is the test: `words_added` counts spans through the instrument's
tokeniser and the expectation counts them through a plain `split`.

Run it with the rest of the repository's Python checks:

    /home/abinash/fkvenv/bin/python -m pytest scripts/validation/test-dashboard.py
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

DASHBOARD = Path(__file__).resolve().parent / "dashboard.py"
RUN_CASES = Path(__file__).resolve().parent / "run-cases.py"


def _load(name: str, path: Path):
    """Both instruments have hyphens in their names, which `import` cannot say."""
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


dashboard = _load("fk_dashboard", DASHBOARD)
_load("fk_validation_harness", RUN_CASES)

SECTIONS = dashboard.SECTIONS
DRAFT = {
    "technique": "MRI brain with and without contrast.",
    "findings": "The grey-white matter is normal. No mass is seen.",
    "impression": "Normal brain MRI.",
    "recommendations": "Clinical management of the headache.",
    "follow_up": "None.",
}


def edited(**changes: str) -> dict:
    out = dict(DRAFT)
    out.update(changes)
    return out


def session(tmp_path: Path) -> dashboard.Session:
    """A Session with no network, no case file and no log: only `close_study` is under test."""
    import collections
    import threading

    instance = object.__new__(dashboard.Session)
    instance.cases = [{"case_id": "s", "study": "MRI BRAIN", "modality": "MRI",
                       "clinical_indication": "45-year-old, headache", "dictation": "x",
                       "technique": "", "prior_report": "", "reported_on": "2026-10-08"}]
    instance.clinician = "Test"
    instance.gateway_log = None
    instance.keep_phrases = True
    instance.out_dir = tmp_path
    instance.rows, instance.phrases = [], []
    instance.drafts, instance.meta, instance.opened = {}, {}, {}
    instance.redrafts = collections.Counter()
    instance.lock = threading.Lock()
    instance.skill = ""
    instance.started_at = 1_790_000_000.0
    return instance


def session_with(*studies: tuple[str, dict, bool]) -> dashboard.Session:
    """Several closed studies in one session, for the readings that need a population."""
    import collections
    import threading

    instance = object.__new__(dashboard.Session)
    instance.cases = []
    instance.clinician = "Dr A. Nair"
    instance.gateway_log = None
    instance.keep_phrases = False
    instance.out_dir = Path("/tmp")
    instance.rows, instance.phrases = [], []
    instance.drafts, instance.meta, instance.opened = {}, {}, {}
    instance.redrafts = collections.Counter()
    instance.lock = threading.Lock()
    instance.skill = "radiology-report"
    instance.started_at = 1_790_000_000.0
    for case_id, after, approved in studies:
        instance.drafts[case_id] = {
            "quality": {"findings": []},
            "confidence": {"level": "supported"},
            "model_provenance": {"model": "ollama/qwen3:14b"},
            **DRAFT,
        }
        instance.meta[case_id] = {"generation_seconds": 2.0, "alias": "fk-reasoning",
                                  "gateway_latency_ms": 20, "request_id": None}
        instance._append_log = lambda row: None
        instance.rows.append(
            instance.close_study(
                case_id,
                {key: after.get(key, "") for key in SECTIONS},
                120.0,
                0.2,
                [],
                approved,
            )
        )
    return instance


def close(case_id: str, after: dict, *, approved: bool = True, verdicts=None) -> dict:
    instance = session(Path("/tmp"))
    instance.drafts[case_id] = {
        "quality": {"findings": []},
        "confidence": {"level": "supported"},
        "model_provenance": {"model": "ollama/qwen3:14b"},
        **DRAFT,
    }
    instance.meta[case_id] = {"generation_seconds": 1.5, "alias": "fk-reasoning",
                              "gateway_latency_ms": 20, "request_id": None}
    instance._append_log = lambda row: None
    return instance.close_study(case_id, {key: after.get(key, "") for key in SECTIONS},
                                 60.0, 0.2, list(verdicts or []), approved)


# -- spans --------------------------------------------------------------------------


def test_an_added_sentence_counts_its_words_and_nothing_else() -> None:
    spans = dashboard.span_table("no mass is seen", "no mass is seen. A 17 mm lesion present.")
    assert spans["inserted"] == ["a 17 mm lesion present"]
    assert spans["deleted"] == []


def test_a_long_deletion_is_still_counted_when_no_table_would_show_it() -> None:
    """The first version filtered spans before counting them, so a deleted sentence landed in
    the record as zero words removed — the reviewer's biggest act, unmeasured. A span longer
    than the phrase tables still counts as words; it simply does not appear as a phrase."""
    too_long = " ".join(f"word{i}" for i in range(dashboard.MAX_SPAN_WORDS + 5))
    spans = dashboard.span_table(f"{too_long} tail", "tail")
    empty = {kind: [] for kind in dashboard.SPAN_KINDS}
    counted = dict.fromkeys(SECTIONS, empty)
    counted["findings"] = spans
    assert dashboard._word_count(counted, "deleted") == dashboard.MAX_SPAN_WORDS + 5
    assert dashboard.is_phrase(spans["deleted"][0]) is False


def test_a_comma_moved_is_not_an_edit() -> None:
    assert dashboard.span_table("normal study, no mass", "normal study no mass")["deleted"] == []


# -- one study, measured ------------------------------------------------------------


def test_four_words_typed_are_four_words_added() -> None:
    row = close("s1", edited(findings=DRAFT["findings"] + " A new sentence here."))
    assert row["words_added"] == 4
    assert row["words_removed"] == 0
    assert row["sections_edited"] == "findings"
    assert row["edits"] == 1
    assert row["final_approval"] == "signed"


def test_typing_reduction_is_what_was_typed_over_what_was_produced() -> None:
    appended = " A new sentence here."
    produced = sum(len(text) for text in DRAFT.values())
    row = close("s1", edited(findings=DRAFT["findings"] + appended))
    assert row["typing_reduction_pct"] == round((1 - len(appended) / produced) * 100, 1)


def test_an_abandoned_study_contributes_time_and_nothing_else() -> None:
    """Diffing a draft against an empty final version would report every section rewritten
    and every word deleted, and would read as though the reviewer typed nothing when they in
    fact typed a report this instrument never saw."""
    row = close("s1", dict.fromkeys(SECTIONS, ""), approved=False)
    assert row["words_added"] == 0
    assert row["words_removed"] == 0
    assert row["sections_edited"] == ""
    assert row["edit_distance"] == 0.0
    assert row["typing_reduction_pct"] == 0.0
    assert row["review_seconds"] == 60.0
    assert row["started_from_scratch"] == 1


def test_the_alias_and_the_model_travel_with_the_row() -> None:
    row = close("s1", DRAFT)
    assert row["model_alias"] == "fk-reasoning"
    assert row["model"] == "ollama/qwen3:14b"
    assert row["skill"] == ""


# -- the summary --------------------------------------------------------------------


def rows_of_three_kinds() -> list[dict]:
    return [
        close("s1", edited(findings=DRAFT["findings"] + " A new sentence here.")),
        close("s2", dict.fromkeys(SECTIONS, ""), approved=False,
              verdicts=[{"severity": "advisory", "check": "structure_coverage",
                         "section": None, "verdict": "real_problem"}]),
        close("s3", edited(impression="No acute abnormality."),
              verdicts=[{"severity": "block", "check": "unsupported_measurement",
                         "section": "findings", "verdict": "not_a_problem"},
                        {"severity": "block", "check": "invented_history",
                         "section": "findings", "verdict": "real_problem"}]),
    ]


def test_acceptance_review_time_and_editing_are_recomputed_from_the_rows() -> None:
    measures = dashboard.metrics(rows_of_three_kinds())
    assert measures["studies_reviewed"] == 3
    assert measures["studies_signed"] == 2
    assert measures["acceptance_rate"] == round(2 / 3, 3)
    assert measures["median_review_time_seconds"] == 60.0
    assert measures["average_review_time_seconds"] == 60.0
    assert measures["section_rewrite_frequency"]["findings"] == round(1 / 3, 3)
    assert measures["section_rewrite_frequency"]["impression"] == round(1 / 3, 3)


def test_false_blocking_rate_comes_from_the_radiologist_and_nowhere_else() -> None:
    measures = dashboard.metrics(rows_of_three_kinds())
    assert measures["false_blocking_rate"]["by_radiologist_verdict"] == 0.5
    assert measures["false_blocking_rate"]["blocking_verdicts_recorded"] == 2
    assert "grading itself" in measures["false_blocking_rate"]["never_asked_fallback"]


def test_a_document_level_advisory_is_never_scored_as_ignored() -> None:
    """`structure_coverage` names no section, so there is no text the reviewer could have
    changed. Dividing it into the acted-on rate would report zero usefulness for a check the
    product raised on purpose."""
    rows = [close("s1", DRAFT, verdicts=[{"severity": "advisory", "check": "structure_coverage",
                                         "section": None, "verdict": "real_problem"}])]
    rows[0]["_advisory_with_section"] = 0
    rows[0]["_advisory_without_section"] = 1
    usefulness = dashboard.metrics(rows)["advisory_usefulness"]
    assert usefulness["rate"] is None
    assert usefulness["raised_against_the_document"] == 1
    assert usefulness["by_radiologist_verdict"] == 1.0


def test_confidence_is_averaged_in_the_order_the_product_labels_it() -> None:
    """Only the signed studies count: an abandoned one never reached an approval, so its
    draft confidence is not a statement about what was signed."""
    rows = rows_of_three_kinds()
    rows[0]["confidence_before_approval"] = "supported"
    rows[2]["confidence_before_approval"] = "not-safe-to-sign"
    confidence = dashboard.metrics(rows)["average_confidence_before_approval"]
    assert confidence["mean_ordinal"] == 1.0
    assert confidence["levels"] == {"supported": 1, "not-safe-to-sign": 1}
    assert confidence["reading"] == "review-carefully"


# -- the four lists -----------------------------------------------------------------


def test_the_phrase_that_was_deleted_appears_in_the_edits_and_the_mistakes() -> None:
    rows = [close("s1", edited(impression="No acute abnormality at all."))]
    phrases = rows[0]["_spans"]["impression"]["replaced"]
    tables = dashboard.rankings(rows, [
        {"study_id": "s1", "section": "impression", "kind": kind, "phrase": phrase,
         "engine_had_a_finding_there": False}
        for kind, table in rows[0]["_spans"]["impression"].items() for phrase in table
    ])
    assert phrases == ["normal brain mri"]
    assert tables["top_human_edits"][0]["what"] == "normal brain mri"
    assert any(row["what"] == "normal brain mri" for row in tables["top_ai_mistakes"])


def test_a_check_is_only_worth_building_where_the_engine_was_silent() -> None:
    """Every entry in the fourth list has `engine_findings_there` at zero: a rule for
    something the gate already raises would be a second name for one check."""
    tables = dashboard.rankings(
        [close("s1", edited(impression="No acute abnormality at all."))],
        [{"study_id": "s1", "section": "impression", "kind": "replaced",
          "phrase": "normal brain mri", "engine_had_a_finding_there": True}],
    )
    assert tables["top_checks_worth_building"] == []


def test_an_abandoned_study_is_an_ai_mistake_not_a_rounding_error() -> None:
    tables = dashboard.rankings(
        [close("s1", dict.fromkeys(SECTIONS, ""), approved=False)], []
    )
    kinds = [row["kind"] for row in tables["top_ai_mistakes"]]
    assert "abandoned — the draft was not a starting point" in kinds


def test_every_ranking_is_capped_at_twenty() -> None:
    rows = [close(f"s{i}", edited(findings=DRAFT["findings"] + f" Extra phrase number {i}."))
            for i in range(25)]
    tables = dashboard.rankings(rows, [
        {"study_id": row["study_id"], "section": "findings", "kind": "inserted",
         "phrase": span, "engine_had_a_finding_there": False}
        for row in rows for span in row["_spans"]["findings"]["inserted"]
    ])
    for name, table in tables.items():
        assert len(table) <= 20, name


# -- the alias join, which is the only Gateway fact this tool reads ------------------


def test_the_alias_survives_a_log_that_holds_several_lines_per_request(tmp_path: Path) -> None:
    log = tmp_path / "gateway.log"
    log.write_text(
        "event=request_completed request_id=abc\n"
        "event=skill_audit request_id=abc alias=fk-reasoning\n"
        "event=chat_completed request_id=abc alias=fk-reasoning\n",
        encoding="utf-8",
    )
    assert dashboard.alias_from_log(log, "abc") == "fk-reasoning"


def test_no_log_means_no_alias_and_no_crash(tmp_path: Path) -> None:
    assert dashboard.alias_from_log(tmp_path / "absent.log", "abc") == ""
    assert dashboard.alias_from_log(None, "abc") == ""
    assert dashboard.alias_from_log(tmp_path / "x.log", None) == ""


def test_a_request_id_that_never_appears_is_reported_absent(tmp_path: Path) -> None:
    log = tmp_path / "gateway.log"
    log.write_text("event=skill_audit request_id=other alias=fk-fast\n", encoding="utf-8")
    assert dashboard.alias_from_log(log, "abc") == ""


# -- the word counts and the readings built from them ---------------------------------------------


def test_the_row_carries_both_word_counts() -> None:
    """A percentage cannot answer "how many words did I not type today", so the absolute
    counts are recorded next to the ratio they come from."""
    draft_words = sum(len(text.split()) for text in DRAFT.values())
    row = close("s1", edited(findings=DRAFT["findings"] + " A new sentence here."))
    assert row["words_in_draft"] == draft_words
    assert row["words_signed"] == draft_words + 4


def test_an_abandoned_study_contributes_no_signed_words() -> None:
    row = close("s1", DRAFT, approved=False)
    assert row["words_signed"] == 0
    assert row["words_in_draft"] > 0


def test_productivity_is_the_signed_words_minus_the_typed_ones() -> None:
    """Longhand: two studies, the same draft in both, four words typed in the first and
    nothing in the second. The machine's words that survived are the signed total less the
    four the reviewer typed."""
    draft_words = sum(len(text.split()) for text in DRAFT.values())
    instance = session_with(
        ("s1", edited(findings=DRAFT["findings"] + " A new sentence here."), True),
        ("s2", DRAFT, True),
    )
    reading = dashboard.analysis(instance.rows, elapsed_seconds=600.0, clinician="Dr A. Nair")
    productivity = reading["productivity"]
    assert productivity["words_the_model_wrote"] == 2 * draft_words
    assert productivity["words_in_the_signed_reports"] == 2 * draft_words + 4
    assert productivity["words_the_reviewer_typed"] == 4
    assert productivity["words_not_typed"] == 2 * draft_words
    assert productivity["minutes_reviewing"] == 4.0  # 2 x 120s review + 2 x 0.2s approval
    assert productivity["words_not_typed_per_minute_reviewing"] == round(
        (2 * draft_words) / 4.0, 1
    )


def test_the_trust_reading_groups_by_the_badge_that_was_actually_shown() -> None:
    instance = session_with(("s1", DRAFT, True), ("s2", DRAFT, True))
    for row in instance.rows:
        row["confidence_before_approval"] = "review-carefully"
    reading = dashboard.analysis(instance.rows, elapsed_seconds=120.0, clinician="Dr A. Nair")
    group = reading["trust_analysis"]["by_confidence_level"]["review-carefully"]
    assert group == {
        "studies": 2,
        "signed": 2,
        "mean_edit_distance": 0.0,
        "mean_review_seconds": 120.0,
        "mean_words_added": 0.0,
    }
    assert "supported" not in reading["trust_analysis"]["by_confidence_level"]


def test_abandoning_a_draft_the_badge_called_supported_is_counted_apart() -> None:
    """The afternoon's most interesting row: the gate was satisfied and the radiologist was
    not. It is reported separately from the abandonment count rather than folded into it."""
    instance = session_with(("s1", DRAFT, True), ("s2", DRAFT, False))
    reading = dashboard.analysis(instance.rows, elapsed_seconds=60.0, clinician="Dr A. Nair")
    assert reading["acceptance_analysis"]["abandoned"] == 1
    assert reading["acceptance_analysis"]["abandoned_after_a_supported_draft"] == 1


def test_a_one_study_half_of_the_trend_does_not_crash() -> None:
    """With three studies the first half is one row and the means of one row are that row.
    With one study the first half is empty and every mean has to be None rather than a
    division by zero at the end of a real afternoon."""
    instance = session_with(("s1", DRAFT, True))
    reading = dashboard.analysis(instance.rows, elapsed_seconds=30.0, clinician="Dr A. Nair")
    assert reading["quality_trend"]["first_half"]["studies"] == 0
    assert reading["quality_trend"]["first_half"]["mean_edit_distance"] is None
    assert reading["quality_trend"]["second_half"]["studies"] == 1


def test_analysis_reads_a_row_written_before_the_word_columns_existed() -> None:
    """A resumed session directory holds `rows.jsonl` from the morning, whose rows predate
    these columns. The instrument must read them as no words, not refuse to open."""
    instance = session_with(("s1", DRAFT, True))
    for row in instance.rows:
        del row["words_in_draft"]
        del row["words_signed"]
    reading = dashboard.analysis(instance.rows, elapsed_seconds=10.0, clinician="Dr A. Nair")
    assert reading["productivity"]["words_the_model_wrote"] == 0
    assert reading["productivity"]["words_not_typed"] == 0


def test_write_files_writes_the_analysis_and_the_report(tmp_path: Path) -> None:
    """The report is the artefact the meeting reads, and it had no test at all: every section
    added to it was code that only ran when somebody looked. This closes the loop."""
    changed = edited(findings=DRAFT["findings"] + " A new sentence here.")
    instance = session_with(("s1", changed, True))
    instance.out_dir = tmp_path
    written = dashboard.write_files(instance)
    assert (tmp_path / "analysis.json").is_file()
    assert written["analysis_json"].endswith("analysis.json")
    report = (tmp_path / "report.md").read_text(encoding="utf-8")
    for heading in (
        "## Where the afternoon went",
        "## What the reviewer did with the draft",
        "## What the machine wrote that was kept",
        "## Trust, read from what the reviewer did",
        "## Across the afternoon",
    ):
        assert heading in report, heading
    assert "words the radiologist did not type" in report


def test_a_rate_is_not_reported_off_a_session_too_short_to_have_one() -> None:
    instance = session_with(("s1", DRAFT, True))
    reading = dashboard.analysis(instance.rows, elapsed_seconds=30.0, clinician="Dr A. Nair")
    assert reading["session_summary"]["studies_per_hour"] is None
    long_afternoon = dashboard.analysis(
        instance.rows, elapsed_seconds=3600.0, clinician="Dr A. Nair"
    )
    assert long_afternoon["session_summary"]["studies_per_hour"] == 1.0


def test_review_time_that_exceeds_the_wall_clock_says_so_out_loud() -> None:
    """`review_seconds` is reported by the screen and the room clock is measured here, so a
    script can claim four minutes of review inside ten seconds of wall clock. The instrument
    that prints "0.3 minutes in the room, 4.9 on the keyboard" without comment is the
    instrument that would quietly believe a fabricated afternoon."""
    instance = session_with(("s1", DRAFT, True))
    reading = dashboard.analysis(instance.rows, elapsed_seconds=10.0, clinician="Dr A. Nair")
    assert "exceeds the wall clock" in reading["session_summary"]["consistency_warning"]
    honest = dashboard.analysis(instance.rows, elapsed_seconds=3600.0, clinician="Dr A. Nair")
    assert honest["session_summary"]["consistency_warning"] == ""
