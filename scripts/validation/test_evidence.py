"""Tests for the evidence package.

Every test is a known answer, a refusal, or a guard against a specific mistake this
repository has already made once. The refusals matter more than the arithmetic: a statistics
library that computes correctly but reports confidently on four cases is worse than one that
refuses.

Run from `scripts/validation`:

    PYTHONPATH=. pytest test_evidence.py
"""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import date
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "apps" / "radiology_copilot" / "src"))

from futurekind_radiology.quality import _CHECK_NAMES  # noqa: E402
from futurekind_radiology.report import MODEL_SECTION_KEYS  # noqa: E402

from evidence import (  # noqa: E402  - the path above is why
    baseline,
    cli,
    edits,
    experiment,
    groundtruth,
    longitudinal,
    loops,
    regression,
    reporting,
    scoring,
    stats,
    store,
    taxonomy,
)

# ------------------------------------------------------------------ taxonomy


def test_every_class_names_an_observable_and_a_detector():
    for item in taxonomy.CLASSES:
        assert item.observable, f"{item.code} has no way to decide it"
        assert item.detected_by in ("engine", "human", "both"), item.code
        assert item.fix_target, item.code


def test_codes_are_unique_and_namespaced():
    codes = [item.code for item in taxonomy.CLASSES]
    assert len(codes) == len(set(codes))
    assert all(code.startswith("E") for code in codes)
    assert "E99" in codes, "the unclassified bucket is the taxonomy's own defect signal"


def test_engine_check_ids_match_the_product_exactly():
    """The drift guard `docs/CONCEPTUAL_DEBT.md` D6 asks for, on the other half of that pair.

    If the copilot adds, renames or removes a quality check, this fails: the taxonomy cannot
    quietly keep mapping an error class onto a check that no longer runs.
    """
    shipped = set(_CHECK_NAMES)
    assert shipped == set(taxonomy.ENGINE_CHECK_IDS)
    assert not taxonomy.unmapped_engine_checks()
    assert not taxonomy.unknown_engine_checks()


def test_engine_coverage_is_low_and_says_so():
    coverage = taxonomy.engine_coverage()
    assert coverage["engine_coverage"] < 0.5, (
        "a claim of engine coverage above half the classes is a claim to re-examine"
    )
    assert coverage["human_only_classes"] > 0


def test_no_class_claims_a_detector_it_cannot_have():
    """`detected_by` and `engine_checks` have to agree, or the coverage figure counts a wish.

    Three classes used to break this: `E02 invented_finding` was credited to `unsupported_absence`,
    which fires on an asserted *absence* and never on an invented positive — the exact thing the
    golden audit measured as undetectable (`docs/product/ROADMAP.md` table 4). Two others said a
    human decides them while naming the check that sometimes catches them. The first version of
    this file published 10 of 26; the honest number after the fix is 9 of 26, and it is pinned here
    so it can only move by a real detector being built and measured.
    """
    for item in taxonomy.CLASSES:
        if item.engine_checks:
            assert item.detected_by in ("engine", "both"), (
                f"{item.code} names {item.engine_checks} but says a human decides it"
            )
    assert taxonomy.code("E02").engine_checks == ()
    coverage = taxonomy.engine_coverage()
    assert coverage["with_engine_detector"] == 9
    assert coverage["engine_coverage"] == 0.346
    assert coverage["content_with_engine_detector"] == 8
    assert coverage["content_engine_coverage"] == 0.667


# ------------------------------------------------------------------ edits


def test_edit_distance_known_answers():
    assert edits.edit_distance("kitten", "sitting") == 3
    assert edits.edit_distance("", "abc") == 3
    assert edits.normalised_distance("abc", "abc") == 0.0
    assert edits.normalised_distance("abc", "xyz") == 1.0


def test_similarity_and_distance_disagree_on_purpose():
    """A rewritten sentence scores differently in each, and both numbers are reported."""
    before = "No haemorrhage. No mass effect."
    after = "There is no evidence of haemorrhage or of any mass effect whatsoever."
    assert edits.similarity(before, after) < 1.0
    report = edits.compare_section("findings", before, after)
    assert report.normalised_distance > 0.4
    assert report.substantive is False or "negation_scope_extended" in report.reasons


def test_negation_scope_extension_is_substantive():
    """The rule that catches "No haemorrhage." -> "No haemorrhage or mass effect".

    Token-set equality alone would call that style, and in radiology prose it is a second
    clinical assertion. The direction of the error is deliberate: under-counting clinical
    change flatters the product, over-counting only costs a reviewer's time.
    """
    substantive, reasons = edits.is_substantive("No haemorrhage.", "No haemorrhage or mass effect.")
    assert substantive
    assert "negation_scope_extended" in reasons


def test_measurement_and_side_changes_are_substantive():
    assert "measurement_changed" in edits.is_substantive("A 3 cm lesion.", "A 4 cm lesion.")[1]
    assert not edits.is_substantive("A 3 cm lesion.", "A 3 cm lesion.")[0]
    assert (
        "side_changed"
        in edits.is_substantive("Left basal ganglia infarct.", "Right basal ganglia infarct.")[1]
    )


def test_summaries_never_carry_text():
    """A PHI guard with a test, because a documented intention is not a control."""
    before = {"findings": "Small left renal cyst, 8 mm.", "impression": "Benign."}
    after = {"findings": "Small left renal cyst, 9 mm.", "impression": "Benign."}
    report = edits.compare_documents(before, after, ("findings", "impression"))
    payload = json.dumps(report.as_dict())
    assert "cyst" not in payload
    assert "renal" not in payload
    assert report.sections[0].detail == []


def test_sections_come_from_the_caller_not_the_module():
    """`docs/CONCEPTUAL_DEBT.md` S4: the instrument must not hold its own copy of the shape."""
    with pytest.raises(TypeError):
        edits.compare_documents({"findings": "a"}, {"findings": "b"})


def test_run_cases_and_the_product_agree_on_the_section_contract():
    """Closes S4/D6 with a comparison instead of a refactor.

    `run-cases.py` deliberately does not import the product, to keep its oracle independent
    (`scripts/validation/run-cases.py:299-303`). That independence is worth more than a shared
    constant — but only if a divergence fails loudly. This is where it fails.
    """
    spec = importlib.util.spec_from_file_location("run_cases_probe", HERE / "run-cases.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert set(module.EDITABLE) == set(MODEL_SECTION_KEYS)


# ------------------------------------------------------------------ scoring


def test_all_six_axes_are_always_present():
    case = scoring.score_case("N-01", "radiology-report")
    assert set(case.axes) == set(scoring.AXES)
    assert len(scoring.AXES) == 6


def test_missing_inputs_are_null_with_a_reason_not_zero():
    case = scoring.score_case("N-01", "radiology-report")
    nulls = case.null_axes()
    assert "clinical_correctness" in nulls and "user_satisfaction" in nulls
    for name, reason in nulls.items():
        assert reason and "0" not in reason[:2], name


def test_no_composite_score_exists_anywhere():
    """The rule a future release will try to break, encoded as an unconditional refusal."""
    with pytest.raises(scoring.CombinedScoreError):
        scoring.assert_not_combined()
    case = scoring.score_case("N-01", "radiology-report", structure_coverage=1.0)
    for forbidden in ("total", "score", "combined", "overall", "composite"):
        assert not hasattr(case, forbidden), forbidden
        assert forbidden not in case.as_dict()


def test_unannounced_degradation_forces_the_safety_floor():
    case = scoring.score_case(
        "N-01", "radiology-report", structure_coverage=1.0, degradation_unannounced=True
    )
    assert case.axes["safety"].value == 0.0
    assert "E20" in case.axes["safety"].evidence


def test_satisfaction_refuses_a_proxy():
    case = scoring.score_case("N-01", "radiology-report", review_seconds=42.0, typed_chars=90)
    assert case.axes["user_satisfaction"].value is None
    assert "proxies" in case.axes["user_satisfaction"].reason_if_null.lower()


# ------------------------------------------------------------------ statistics


def test_wilson_interval_known_answer():
    assert tuple(round(value, 4) for value in stats.wilson_interval(5, 10)) == (0.2366, 0.7634)


def test_wilson_never_leaves_the_unit_interval():
    low, high = stats.wilson_interval(0, 20)
    assert low >= 0.0
    assert 0.0 < high < 1.0, (
        "a zero-cell count must not produce an interval touching zero success forever"
    )


def test_mcnemar_known_answer():
    result = stats.mcnemar(15, 2)
    assert abs(result.p_value - 0.00235) < 1e-4
    assert result.n == 17


def test_mcnemar_with_no_discordance_says_indistinguishable():
    result = stats.mcnemar(0, 0)
    assert result.estimate is None
    assert "indistinguishable" in result.caution


def test_power_scales_as_it_should():
    """n quadruples, the detectable effect halves. The fact that makes small studies small."""
    assert abs(stats.mde_paired(200).estimate * 2 - stats.mde_paired(50).estimate) < 1e-3


def test_the_detectable_effect_is_pinned_to_an_absolute_number():
    """A ratio test passes with any constant in the quantile table, so pin the value.

    Both answers are computed by hand from `(z_alpha + z_beta) / sqrt(n)` at alpha 0.05:
    0.2802 at n=100 and 0.6265 at n=20 — the twenty-case pilot's real limitation, stated as
    a number rather than as a hope.
    """
    assert abs(stats.mde_paired(100).estimate - 0.2802) < 1e-4
    assert abs(stats.mde_paired(20).estimate - 0.6265) < 1e-4
    assert stats.mde_paired(100, power=0.9).estimate > stats.mde_paired(100).estimate


def test_sample_size_for_a_realistic_discordance_is_painfully_large():
    needed = stats.sample_size_for_mcnemar(0.25, 0.15).estimate
    assert needed > 1000, "if this ever gets small, check the discordance assumption first"


def test_bootstrap_is_reproducible():
    values = list(range(1, 21))
    first = stats.bootstrap_paired(values)
    second = stats.bootstrap_paired(values)
    assert first.ci_low == second.ci_low
    assert first.ci_low < first.estimate < first.ci_high


def test_holm_is_monotone_in_the_adjusted_values():
    adjusted = [row["adjusted"] for row in stats.holm([("a", 0.01), ("b", 0.04), ("c", 0.03)])]
    assert adjusted == sorted(adjusted)


def test_wilcoxon_refuses_a_sample_too_small_for_its_approximation():
    result = stats.wilcoxon_signed_rank([0.1, -0.2, 0.3, 0.4, -0.1])
    assert result.p_value is None
    assert "sign_test" in result.caution


def test_sign_test_direction():
    result = stats.sign_test([1, 1, 1, 1, 1, 1, -1])
    assert result.n == 7
    assert result.p_value is not None and result.p_value < 0.2


# ------------------------------------------------------------------ ground truth


def test_author_cannot_ratify_their_own_case():
    case = groundtruth.GroundTruthCase(
        case_id="X-01",
        specialty="radiology",
        modality="CT",
        study="CT HEAD",
        category="normal",
        difficulty=1,
        risk="low",
        provenance="synthetic_engineered",
        indication="headache",
        dictation="No haemorrhage.",
        expected_sections={"findings": "No haemorrhage."},
        author="engineering",
        ratified="ratified",
        ratified_by="engineering",
        ratified_role="consultant",
        ratified_on="2026-10-09",
    )
    problems = case.validate()
    assert any("cannot ratify" in problem for problem in problems)
    with pytest.raises(groundtruth.RecordError):
        groundtruth.require_valid(case)


def test_ratified_needs_a_clinical_role():
    case = groundtruth.from_golden(baseline.load_cases()[0])
    case.ratified = "ratified"
    case.ratified_by = "someone"
    case.ratified_on = "2026-10-09"
    case.ratified_role = "engineer"
    assert any("clinical role" in problem for problem in case.validate())


def test_golden_corpus_is_explicitly_not_ground_truth():
    cases = [groundtruth.from_golden(row) for row in baseline.load_cases()]
    summary = groundtruth.corpus_summary(cases)
    assert summary["cases"] == 100
    assert summary["ratified_and_valid"] == 0
    assert summary["usable_as_evidence_about_care"] == 0.0


def test_difficulty_is_a_scale_not_a_string():
    case = groundtruth.from_golden(baseline.load_cases()[0])
    case.difficulty = 9
    assert any("difficulty" in problem for problem in case.validate())


# ------------------------------------------------------------------ store and PHI


def test_store_refuses_a_path_inside_the_repository(tmp_path):
    inside = Path.cwd() / "evidence.jsonl"
    with pytest.raises(store.StoreError):
        store.append(inside, [])
    assert store.inside_repo(REPO / "core" / "gateway" / "models.yaml")


def test_store_refuses_text_without_the_flag(tmp_path):
    record = store.SessionRecord(
        case_ref="opaque-1",
        site="s",
        actor_label="r1",
        role="consultant",
        started_at=store.now(),
        text_stored=True,
    )
    with pytest.raises(store.StoreError):
        store.append(tmp_path / "e.jsonl", [record])
    assert store.append(tmp_path / "e.jsonl", [record], allow_text=True) == 1


def test_record_hashes_not_words(tmp_path):
    sections = store.record_sections({"findings": "A 6 mm left frontal cyst."})
    assert sections["findings"]["chars"] == len("A 6 mm left frontal cyst.")
    assert len(sections["findings"]["sha12"]) == 12
    assert "text" not in sections["findings"]


def test_read_rejects_a_foreign_schema(tmp_path):
    path = tmp_path / "e.jsonl"
    record = store.SessionRecord(
        case_ref="opaque-2", site="s", actor_label="r1", role="resident", started_at=store.now()
    )
    store.append(path, [record])
    path.write_text(json.dumps({"schema": "other/9"}) + "\n", encoding="utf-8")
    with pytest.raises(store.StoreError):
        store.read(path)


def test_stub_rows_are_filtered_before_any_claim(tmp_path):
    def build(stub: bool) -> dict:
        provenance = store.Provenance(skill="radiology-report", alias="fk-reasoning", stub=stub)
        record = store.SessionRecord(
            case_ref="opaque-3",
            site="s",
            actor_label="r1",
            role="consultant",
            started_at=store.now(),
            provenance=provenance,
        )
        return record.as_dict()

    rows = [build(True), build(False)]
    assert len(store.real_rows(rows)) == 1


def test_stage_durations_are_derived_not_assumed():
    record = store.SessionRecord(
        case_ref="opaque-4",
        site="s",
        actor_label="r1",
        role="consultant",
        started_at="2026-10-09T10:00:00+05:30",
        stages={
            "received": "2026-10-09T10:00:00+05:30",
            "drafted": "2026-10-09T10:00:20+05:30",
            "approved": "2026-10-09T10:01:00+05:30",
        },
    )
    assert record.stage_seconds()["received_to_drafted"] == 20.0
    assert record.time_to_final() == 60.0


# ------------------------------------------------------------------ regression gate


def _paired(rows: list[tuple[float, float]], key: str) -> list[dict]:
    return [
        {"case_ref": f"C-{index}", "baseline": {key: before}, "candidate": {key: after}}
        for index, (before, after) in enumerate(rows, start=1)
    ]


def test_safety_regression_blocks_the_release():
    rows = _paired([(0.0, 0.05)] * 30, "faithful_refusals")
    report = regression.compare(
        rows, {"safety": regression.endpoint("refusal rate", "faithful_refusals")}
    )
    assert not report.passed
    assert "blocked at: safety" in report.conclusion


def test_inconclusive_safety_gate_fails_closed():
    """One paired case is not a pass. The dangerous failure is a green light from nothing."""
    rows = _paired([(0.0, 0.0)], "faithful_refusals")
    report = regression.compare(
        rows, {"safety": regression.endpoint("refusal rate", "faithful_refusals")}
    )
    assert not report.passed
    assert "inconclusive" in report.gates[0].verdict


def test_a_report_of_no_pairs_never_reads_as_a_pass():
    """The second lock on the same door: green gates over nothing are not a green release."""
    gate = regression.GateResult(
        name="safety",
        passed=True,
        endpoint="refusal rate",
        baseline=0.0,
        candidate=0.0,
        delta=0.0,
        ci=[0.0, 0.0],
        p_value=1.0,
        n_pairs=0,
        mde=None,
        verdict="non-inferior",
        caution="",
    )
    assert regression.RegressionReport(gates=[gate], comparable_pairs=0).passed is False
    assert regression.RegressionReport(gates=[gate], comparable_pairs=1).passed is True


def test_within_tolerance_workflow_change_passes():
    rows = _paired([(100.0, 101.0)] * 40, "review_seconds")
    report = regression.compare(
        rows, {"workflow": regression.endpoint("review seconds", "review_seconds")}
    )
    assert report.passed
    assert report.gates[0].mde > 0, "the gate must publish what it could have detected"


def test_every_gate_prints_its_power():
    rows = _paired([(1.0, 1.0)] * 12, "typed_chars")
    report = regression.compare(rows, {"productivity": regression.endpoint("typed", "typed_chars")})
    assert "detect a standardised effect" in report.gates[0].caution


# ------------------------------------------------------------------ experimentation


def test_allocation_is_deterministic_and_balanced():
    refs = [f"C-{index}" for index in range(40)]
    first = experiment.allocate(refs)
    assert first == experiment.allocate(refs)
    counts = sorted(first.values())
    assert counts.count("A") == counts.count("B") == 20


def test_crossover_balances_arm_order():
    order = experiment.crossover_order([f"C-{index}" for index in range(20)])
    starts = [arms[0] for _, arms in order]
    assert starts.count("A") == starts.count("B")


def test_unregistered_experiment_refuses_analysis():
    prereg = stats.Preregistration(
        question="Does prompt B reduce substantive edits?",
        primary_endpoint="",
        comparison="A vs B",
        unit_of_analysis="case",
        n_planned=0,
        alpha=0.05,
        power=0.8,
        analysis="McNemar",
    )
    trial = experiment.Experiment(
        identifier="E-1",
        question="x",
        arm_a_label="A",
        arm_b_label="B",
        unit="case",
        endpoints=("substantive",),
        prereg=prereg,
    )
    result = trial.analyse(binary=("substantive",), continuous=())
    assert result["analysed"] is False
    assert len(result["problems"]) >= 2


def test_registered_binary_endpoint_analyses():
    prereg = stats.Preregistration(
        question="Does prompt B reduce substantive edits?",
        primary_endpoint="substantive",
        comparison="A vs B",
        unit_of_analysis="case",
        n_planned=40,
        alpha=0.05,
        power=0.8,
        analysis="McNemar exact",
        signed_by="owner",
    )
    rows = [
        {"case_ref": f"C-{i}", "arms": {"A": {"substantive": 1}, "B": {"substantive": 0}}}
        for i in range(12)
    ] + [
        {"case_ref": f"C-{i}", "arms": {"A": {"substantive": 0}, "B": {"substantive": 0}}}
        for i in range(20, 40)
    ]
    trial = experiment.Experiment(
        identifier="E-2",
        question="x",
        arm_a_label="A",
        arm_b_label="B",
        unit="case",
        endpoints=("substantive",),
        prereg=prereg,
        rows=rows,
    )
    result = trial.analyse(binary=("substantive",), continuous=())
    assert result["analysed"] is True
    assert result["endpoints"]["substantive"]["discordant"] == 12
    assert result["endpoints"]["substantive"]["primary"] is True


# ------------------------------------------------------------------ longitudinal


def test_period_keys_and_timezone_refusal():
    assert longitudinal.period_key("2026-10-09T10:00:00+05:30", "month") == "2026-10"
    assert longitudinal.period_key("2026-10-09T10:00:00+05:30", "quarter") == "2026-Q4"
    assert longitudinal.period_key("2026-01-04T10:00:00+05:30", "week").endswith("-W01")
    with pytest.raises(ValueError):
        longitudinal.period_key("2026-10-09T10:00:00", "month")


def test_mann_kendall_needs_four_points():
    assert longitudinal.mann_kendall([1.0, 2.0, 3.0])["sufficient"] is False
    trend = longitudinal.mann_kendall([1.0, 2.0, 2.5, 3.0, 4.0, 5.0, 5.5, 7.0])
    assert trend["tau"] > 0.9 and trend["p_value"] < 0.05


def test_case_mix_drift_is_detected():
    records = []
    for index in range(60):
        period = "2026-09" if index < 30 else "2026-10"
        category = "normal" if (index < 30 or index % 2 == 0) else "emergency"
        records.append({"started_at": f"{period}-15T10:00:00+05:30", "category": category})
    drift = longitudinal.case_mix_drift(records)
    assert drift["testable"] and drift["drift_detected"]


def test_the_four_questions_name_what_they_cannot_answer():
    questions = {question.question: question for question in longitudinal.four_questions()}
    assert len(questions) == 4
    for question in questions.values():
        assert question.why_not
        assert question.required_strata
    assert not any(question.measurable_today for question in questions.values())


# ------------------------------------------------------------------ improvement loops


def test_apply_is_refused():
    with pytest.raises(loops.AutoApplyError):
        loops.apply()


def test_edit_events_become_ranked_proposals():
    events = [
        {
            "case_ref": f"C-{index}",
            "section": "impression",
            "substantive": True,
            "reasons": ["assertion_changed"],
            "suggested_codes": ["E07"],
            "chars_removed": 4,
            "chars_inserted": 9,
            "prompt_version": "v",
        }
        for index in range(4)
    ]
    proposals = loops.prompt_proposals(events)
    assert proposals and proposals[0].kind == "prompt"
    assert proposals[0].status == "proposal"
    assert "frozen corpus" in proposals[0].validation


def test_harm_weighting_orders_danger_above_volume():
    noisy = loops.ImprovementProposal(
        identifier="a",
        kind="check",
        observation="",
        error_codes=("E15",),
        count=40,
        cases=(),
        harm_weight=loops.mean_harm(["E15"] * 40),
        proposed_change="",
        validation="",
        revalidatable=True,
    )
    dangerous = loops.ImprovementProposal(
        identifier="b",
        kind="prompt",
        observation="",
        error_codes=("E08",),
        count=2,
        cases=(),
        harm_weight=loops.mean_harm(["E08"] * 2),
        proposed_change="",
        validation="",
        revalidatable=True,
    )
    ordered = sorted([noisy, dangerous], key=loops._rank_key)
    assert ordered[0].identifier == "b", (
        "harm per event outranks frequency in the queue a human reads top-down"
    )
    assert loops.rank_harm(["E15"] * 40) > loops.rank_harm(["E08"] * 2), (
        "and the total still belongs to the noisy one: both numbers are true, and only "
        "one of them decides the order"
    )


def test_check_proposals_require_the_paired_cost():
    events = loops.override_events(
        [
            {
                "false_block_on_faithful": True,
                "check": "dropped_observation",
                "case_id": "N-01",
                "detail": "",
            }
        ]
        * 3
    )
    proposals = loops.check_proposals(events)
    assert proposals
    assert "newly blocked correct reports" in proposals[0].validation


def test_loop_state_admits_what_has_never_been_measured():
    state = loops.loop_state()
    assert state["prompt_loop"]["available"] is False
    assert state["check_loop"]["available"] is True
    assert "3 of 306" in state["check_loop"]["known_cost"]


# ------------------------------------------------------------------ audiences and research


def test_unknown_audience_is_an_error_not_a_default():
    with pytest.raises(KeyError):
        reporting.view([], "whoever")


def test_a_view_is_a_filter_not_a_permission():
    assert "permission" in reporting.view([], "department_head")["_note"]


def test_seven_audiences_each_have_a_question_and_a_boundary():
    assert len(reporting.AUDIENCES) == 7
    for name, spec in reporting.AUDIENCES.items():
        assert spec["question"], name
        assert spec["must_not_see"], (
            f"{name} sees everything, which is the finding this file denies"
        )


def test_anonymisation_catches_identifier_shaped_values():
    rows = [{"case_ref": "UHID123456", "site": "s", "category": "normal"}]
    verdict = reporting.anonymise_check(rows)
    assert verdict["offender_count"] == 1
    assert verdict["verdict"].startswith("refused")


def test_thin_cells_are_flagged_before_export():
    rows = [
        {
            "case_ref": f"C-{index}",
            "site": "s",
            "modality": "CT",
            "study": "CT HEAD",
            "category": "rare",
            "difficulty": 5,
            "role": "consultant",
            "month": "2026-10",
        }
        for index in range(3)
    ]
    verdict = reporting.anonymise_check(rows)
    assert verdict["cells_below_k"] >= 1
    assert verdict["k_min"] == 5


def test_svg_refuses_to_draw_a_trend_from_one_point():
    svg = reporting.svg_line([{"period": "2026-10", "mean": 1.0, "n_value": 5}])
    assert "not enough periods" in svg


def test_svg_prints_the_denominator():
    svg = reporting.svg_line(
        [
            {"period": "2026-09", "mean": 1.0, "n_value": 7},
            {"period": "2026-10", "mean": 1.2, "n_value": 9},
        ]
    )
    assert "(n=7)" in svg and "(n=9)" in svg


def test_csv_export_refuses_the_repository(tmp_path):
    with pytest.raises(store.StoreError):
        reporting.write_csv([{"a": 1}], REPO / "out.csv")
    assert reporting.write_csv([{"a": 1, "b": {"nested": True}}], tmp_path / "out.csv") == 1


def test_centre_summary_refuses_to_pool_patients():
    rows = [
        {
            "case_ref": f"C-{index}",
            "site": f"site-{index % 3}",
            "category": "common",
            "edit": {"chars_inserted": 10},
            "labels": ["E15"],
            "time_to_final_seconds": 90,
        }
        for index in range(9)
    ]
    summary = reporting.centre_summary(rows)
    assert len(summary["sites"]) == 3
    assert "never move patient data" in summary["rule"]
    assert any(site["suppressed"] for site in summary["sites"]) or len(rows) >= 15


# ------------------------------------------------------------------ the measured baseline


def test_baseline_composition_share_is_a_bound_and_says_so():
    summary = baseline.run()
    composition = summary["composition_share"]
    assert composition["n"] == 100
    assert 0.0 < composition["median"] <= 1.0
    assert any("overstates composition" in note for note in summary["limitations"])


def test_baseline_records_the_missing_measurements():
    """The finding that changes the study design: the reference answers have almost no numbers.

    If the corpus carries about 0.2 measurements per report, no study run on it can measure
    whether the product improves measurement accuracy. Recorded as data so the roadmap cannot
    lose it in prose.
    """
    summary = baseline.run()
    assert summary["measurements_per_reference"]["mean"] < 1.0
    assert summary["probes_per_case"]["mean"] > 3.0


def test_the_aggregate_reads_the_key_the_producer_writes(tmp_path):
    """The one test that catches a metric quietly reading a key nothing emits.

    `reporting._aggregate()` sums `edit["chars_inserted"]`, which is a field of
    `evidence.edits.EditReport`, not of a schema. Rename it on either side and every session reads
    as zero characters typed — a result, printed as a number, that means only that two modules
    stopped speaking. This test is the wire between them.
    """
    report = edits.compare_documents(
        {"findings": "A left frontal lesion is present."},
        {"findings": "A left frontal lesion is present, with surrounding oedema."},
        ("findings",),
    )
    assert report.chars_inserted > 0, "the fixture stopped exercising the field"
    record = store.SessionRecord(
        case_ref="opaque-contract",
        site="clinic-a",
        actor_label="consultant-1",
        role="consultant",
        started_at=store.now(),
        provenance=store.Provenance(skill="radiology-report", stub=False),
        edit=report.as_dict(),
    )
    path = tmp_path / "session.jsonl"
    assert store.append(path, [record]) == 1

    view = reporting.view(store.read(path), "administration")
    assert view["typed_chars_total"] == report.chars_inserted
    assert "error_classes" not in view, "a cost view received clinical labels"


def test_baseline_markdown_is_generated_and_dated():
    markdown = baseline.markdown_table(baseline.run())
    assert markdown.startswith("<!-- GENERATED")
    assert "do not hand-edit" in markdown
    # The date must be the run's own, not a year someone typed: an undated artefact cannot be
    # told apart from a stale one.
    assert date.today().isoformat() in markdown


# ------------------------------------------------------------------ cli


def test_the_cli_turns_each_refusal_into_an_exit_code(tmp_path, capsys):
    """The verbs are the interface, and an interface with no test is a documented rumour.

    Exit codes are decisions here: 0 means the instrument ran clean and 1 means it refused, with
    the reason on stderr in one line rather than a traceback to scroll past. An unknown audience
    never reaches the handler at all — `--audience` is an argparse `choices` list, so the shell
    refuses it with 2 and the seven readers are named in the usage line.
    """
    assert cli.main(["selftest"]) == 0
    assert cli.main(["taxonomy"]) == 0

    capsys.readouterr()
    assert cli.main(["check", "--store", str(REPO / "evidence.jsonl")]) == 1
    assert "refused:" in capsys.readouterr().err

    with pytest.raises(SystemExit) as raised:
        cli.main(["view", "--audience", "not_a_reader", "--store", str(tmp_path / "s.jsonl")])
    assert raised.value.code == 2


def test_the_cli_verbs_named_in_the_handbook_exist():
    """`docs/evidence/HANDBOOK.md` §2 promises ten verbs. If one is renamed, that table lies.

    Asked through the public parser rather than through argparse internals: a subcommand that
    does not exist exits 2 on `--help`, so this distinguishes the verbs from a typo.
    """
    parser = cli.build_parser()
    documented = {
        "baseline",
        "taxonomy",
        "groundtruth",
        "selftest",
        "loop-state",
        "view",
        "check",
        "tables",
        "figure",
        "regress",
    }
    for verb in sorted(documented):
        with pytest.raises(SystemExit) as raised:
            parser.parse_args([verb, "--help"])
        assert raised.value.code == 0, f"{verb} is documented but not a verb"
    with pytest.raises(SystemExit) as raised:
        parser.parse_args(["nonsense"])
    assert raised.value.code == 2
