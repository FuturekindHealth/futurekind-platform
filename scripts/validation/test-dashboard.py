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
