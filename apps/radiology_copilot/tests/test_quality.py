"""The quality engine: nine checks, each proved on its own terms.

Every check here exists because of a named failure in the product documents — an
invented measurement (R-7 / F10), a dropped observation (clause 3 / R-3), a
comparison with a scan nobody supplied, a hedged finding written as a settled one
(the golden set's `must_not_say` column). Each test therefore asserts both halves:
that the failure is caught, and that the innocent version of the same sentence is
not. A check that only ever fires is worse than no check, because the department
learns to sign through it.

Nothing in this file calls the Gateway or a model. The checks are pure functions of
the draft and the submission, which is what makes them testable at all — and what
makes them worth trusting over a prose answer that sounds fine.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from futurekind_radiology.profiles import MRI_BRAIN, profile_for
from futurekind_radiology.quality import assess_confidence, evaluate
from futurekind_radiology.report import QualityFinding
from futurekind_radiology.submission import StudySubmission

INDICATION = "45-year-old, chronic headache, no neurological deficit"
DICTATION = (
    "Normal grey-white matter. No mass. Normal ventricular size. No white matter "
    "lesions. Pituitary normal. No sinus disease."
)
CLEAN = {
    "clinical_indication": INDICATION,
    "technique": "MRI brain with and without contrast.",
    "findings": (
        "The grey-white matter is normal. No mass is seen. The ventricles are normal in "
        "size. No white matter lesions are identified. The pituitary is normal. The "
        "paranasal sinuses are clear. The basal ganglia and thalami are unremarkable. No "
        "midline shift. The cortex and sulci are normal for age. The brainstem and "
        "cerebellum are normal, and the hippocampi preserve their internal architecture. No "
        "abnormal restricted diffusion. No abnormal enhancement. The orbital apices and "
        "optic nerves are unremarkable. The visualised skull vault shows normal marrow "
        "signal."
    ),
    "impression": "Normal brain MRI. No structural lesion to account for the headache.",
    "recommendations": "Clinical management of the headache.",
    "follow_up": "None.",
}


def study(**changes: object) -> StudySubmission:
    payload: dict[str, object] = {
        "clinical_indication": INDICATION,
        "modality": "MRI",
        "study": "MRI BRAIN WITH AND WITHOUT CONTRAST",
        "findings": DICTATION,
        "technique": "MRI brain with and without contrast.",
    }
    payload.update(changes)
    return StudySubmission(**payload)


def check(sections: dict[str, str], **changes: object):
    """Run the engine the way the copilot does, with the MRI brain profile on."""
    return evaluate(
        sections,
        study(**changes),
        checked_at="2026-10-08T09:30:00Z",
        structure_checklist=MRI_BRAIN.structures,
        out_of_scope_claims=MRI_BRAIN.out_of_scope_claims,
    )


def ids(quality) -> set[str]:
    return {finding.check for finding in quality.findings}


# -- the clean case, and determinism -------------------------------------------------------------


def test_a_grounded_draft_raises_nothing() -> None:
    quality = check(CLEAN)

    assert quality.findings == []
    assert quality.status == "clear"
    assert len(quality.checks_run) == 9


def test_the_same_draft_and_dictation_always_give_the_same_verdict() -> None:
    """Repeatability is the whole reason these are rules and not a model's opinion:
    a quality verdict a department cannot reproduce cannot be audited afterwards."""
    first, second = check(CLEAN), check(CLEAN)

    assert first == second


def test_the_scope_statement_travels_with_the_result() -> None:
    assert "none of them has seen the images" in check(CLEAN).scope


def test_the_checks_a_signed_report_names_are_the_checks_that_ran() -> None:
    """`checks_run` is a claim about the engine, so it is tested against the engine.

    One draft that raises all nine. A report states on its face which checks were run
    on it, and a list that has drifted from the order the code runs — or from a check
    that was renamed, added or quietly dropped — would be a false statement inside a
    clinical document. The literal below is deliberately written out rather than
    imported from the module: the test is the claim, not a mirror of the code.
    """
    sections = {
        **CLEAN,
        "findings": (
            "The grey-white matter is normal. No mass is seen. The ventricles are normal "
            "in size. No white matter lesions are identified. The paranasal sinuses are "
            "clear. The basal ganglia and thalami are unremarkable. No midline shift. The "
            "cortex and sulci are normal for age. The brainstem and cerebellum are normal, "
            "and the hippocampi preserve their internal architecture. No abnormal "
            "restricted diffusion. No abnormal enhancement. The orbital apices and optic "
            "nerves are unremarkable. The visualised skull vault shows normal marrow "
            "signal. A 27 mm right frontal lesion is present, unchanged from the prior "
            "study. **The appearance is new.** Mrs Alvarez has MRN 4482190. No pulmonary "
            "embolism."
        ),
        "impression": "Normal brain MRI. This is diagnostic of multiple sclerosis.",
    }
    quality = evaluate(
        sections,
        study(
            findings=(
                "Normal grey-white matter. No mass. Normal ventricular size. No white "
                "matter lesions. A subtle right frontal abnormality is possible. The "
                "thymus is enlarged. No sinus disease."
            )
        ),
        checked_at="2026-10-08T09:30:00Z",
        extra_sections=("confidence",),
        structure_checklist=MRI_BRAIN.structures,
        out_of_scope_claims=MRI_BRAIN.out_of_scope_claims,
    )

    assert quality.checks_run == [
        "dropped_observation",
        "unsupported_measurement",
        "invented_history",
        "unsupported_certainty",
        "format_breach",
        "invented_identifier",
        "self_reported_confidence",
        "unsupported_absence",
        "structure_coverage",
    ]
    assert ids(quality) == set(quality.checks_run)

    seen: list[str] = []
    for finding in quality.findings:
        if finding.check not in seen:
            seen.append(finding.check)
    assert seen == quality.checks_run
    assert quality.status == "blocking"


# -- 1. dropped observations ----------------------------------------------------------------------


def test_a_compressed_summary_that_loses_two_observations_is_refused() -> None:
    """R-3: the model tightened a six-organ dictation into three and sounded better
    for it. Silence about the pituitary is not a stylistic choice."""
    draft = {**CLEAN, "findings": "Normal grey-white matter. No mass. Ventricles normal."}

    quality = check(draft)

    assert "dropped_observation" in ids(quality)
    assert quality.status == "blocking"


def test_a_paraphrased_observation_counts_as_carried_through() -> None:
    """The check is about content, not wording: "the pituitary is normal" is the
    dictated "pituitary normal", and blocking that would block reporting."""
    assert "dropped_observation" not in ids(check(CLEAN))


def test_a_plural_is_not_a_missing_observation() -> None:
    """Hippocampus and hippocampi are the same structure. Comparison is on the stem
    for exactly this reason."""
    draft = {**CLEAN, "findings": CLEAN["findings"] + " The hippocampi are normal."}

    assert "dropped_observation" not in ids(check(draft))


# -- 2. invented measurements ---------------------------------------------------------------------


def test_a_size_nobody_dictated_blocks_the_draft() -> None:
    draft = {**CLEAN, "findings": CLEAN["findings"] + " A 27 mm hypodense lesion is seen."}

    quality = check(draft)

    blocked = [f for f in quality.findings if f.check == "unsupported_measurement"]
    assert blocked[0].severity == "block"
    assert blocked[0].evidence == "27"


def test_a_measurement_from_the_dictation_passes() -> None:
    draft = {
        **CLEAN,
        "findings": CLEAN["findings"] + " An 18 mm rim-enhancing collection is present.",
    }

    quality = check(draft, findings=DICTATION + " 18 mm rim-enhancing left temporal collection.")

    assert "unsupported_measurement" not in ids(quality)


def test_sequence_names_and_ordinal_anatomy_are_not_measurements() -> None:
    """T2, FLAIR and "the 3rd ventricle" are not numeric claims about the patient, and
    a check that flags them is switched off by the end of the first week."""
    draft = {
        **CLEAN,
        "findings": (
            CLEAN["findings"]
            + " The 3rd ventricle is normal on T2 and FLAIR; the lesion measures 5 mm."
        ),
    }

    quality = check(draft, findings=DICTATION + " The lesion measures 5 mm.")

    assert "unsupported_measurement" not in ids(quality)


def test_a_count_that_disagrees_with_the_dictation_is_caught() -> None:
    """A count is a measurement of the same kind.

    Only the adjacent form is caught ("2 lesions"), and spelled-out numbers are not
    ("two lesions"). That is a real limit of a regex over digits and it is stated
    here rather than hidden: widening the window to cover "2 white matter lesions"
    would also catch "3 months later, no lesions", and a check that blocks a correct
    sentence is a check that gets switched off.
    """
    draft = {**CLEAN, "findings": "There are 2 lesions in the white matter."}

    quality = check(draft, findings="Three white matter lesions. No mass. Pituitary normal.")

    assert "unsupported_measurement" in ids(quality)


def test_the_right_digit_with_the_wrong_number_blocks() -> None:
    """The near miss, which is the one a substring test waved through.

    `"9" in "19 mm"` is true, so a draft that shrank a dictated 19 mm shift to 9 mm
    used to pass. That is not a rounding difference — it is the error the golden set's
    `must_not_say` column weights most heavily, in the form a reviewer is least likely
    to catch because the digit is right. Numbers are therefore compared as whole
    tokens on both sides.
    """
    draft = {**CLEAN, "findings": CLEAN["findings"] + " Midline shift of 9 mm is present."}

    quality = check(draft, findings=DICTATION + " Midline shift measures 19 mm.")

    blocked = [f for f in quality.findings if f.check == "unsupported_measurement"]
    assert [f.evidence for f in blocked] == ["9"]
    assert blocked[0].severity == "block"


def test_a_sequence_name_does_not_ground_a_measurement() -> None:
    """The exclusion that keeps the check worth having.

    Radiology text is full of digits that are not amounts — T1, T2, FLAIR, L4/L5 — and
    a bare *2* taken from "axial T2" would ground every invented "2 mm" focus the model
    ever writes. A digit glued to a letter therefore says nothing about size.
    """
    draft = {**CLEAN, "findings": CLEAN["findings"] + " A 2 mm enhancing focus is present."}

    quality = check(
        draft,
        technique="MRI brain with and without contrast; axial T2, FLAIR and DWI sequences.",
    )

    blocked = [f for f in quality.findings if f.check == "unsupported_measurement"]
    assert [f.evidence for f in blocked] == ["2"]


def test_an_age_in_the_indication_is_the_residue_the_token_rule_leaves() -> None:
    """Stated, not hidden: a bare number in the submitted text *does* ground a drafted
    measurement, so the "45" of a 45-year-old lets a drafted 45 mm through.

    Narrowing this further means comparing number-and-unit pairs, which then blocks the
    clinician who dictated "4.5 across" and was drafted as "4.5 cm" — a false refusal on
    a correct report, and the failure mode that gets a whole check switched off. The
    token rule stays and the residue is written where somebody will read it.
    """
    draft = {**CLEAN, "findings": CLEAN["findings"] + " A 45 mm collection is present."}

    quality = check(draft)

    assert "unsupported_measurement" not in ids(quality)


def test_a_number_in_the_plan_is_advisory_not_blocking() -> None:
    """'Review in 12 months' is a decision about the future, not an assertion about
    this study, and no dictated text contains it. Blocking it would block follow-up."""
    draft = {**CLEAN, "follow_up": "Repeat imaging in 12 months."}

    quality = check(draft)

    flagged = [f for f in quality.findings if f.check == "unsupported_measurement"]
    assert [f.severity for f in flagged] == ["advisory"]
    assert quality.status == "advisory"


# -- 3. invented history --------------------------------------------------------------------------


def test_a_comparison_with_nothing_supplied_blocks() -> None:
    draft = {**CLEAN, "impression": "No structural lesion. Findings unchanged from prior."}

    quality = check(draft)

    assert "invented_history" in ids(quality)
    assert quality.status == "blocking"


def test_the_same_sentence_passes_when_a_previous_report_was_supplied() -> None:
    priors = [
        {
            "reported_on": "4 months ago",
            "modality": "MRI",
            "study": "MRI BRAIN WITH CONTRAST",
            "report": "No structural lesion. Normal pituitary.",
        }
    ]

    draft = {**CLEAN, "impression": "No structural lesion, unchanged from 4 months ago."}

    assert "invented_history" not in ids(check(draft, previous_reports=priors))


def test_a_comparison_the_clinician_dictated_is_their_statement_not_the_models() -> None:
    draft = {**CLEAN, "impression": "No structural lesion. Unchanged."}

    assert "invented_history" not in ids(check(draft, findings=DICTATION + " Unchanged."))


def test_an_interval_in_a_plan_is_not_read_as_a_comparison() -> None:
    """'Review at interval' is a plan. Bare 'interval' was taken out of the comparison
    list for this reason: a check that blocks follow-up wording is a check the
    department routes around."""
    draft = {**CLEAN, "follow_up": "Review at interval if the headache pattern changes."}

    assert "invented_history" not in ids(check(draft))


def test_a_differential_is_not_a_comparison_with_an_earlier_study() -> None:
    """Golden case R-11: "fits this pattern better than atherosclerosis".

    That sentence is the case's whole teaching point — a concentric halo in a forty-year-old
    is vasculitis, and the impression has to say what it fits better than. It compares two
    diseases, not two studies, and the engine used to refuse it because "better than" sat in
    the comparison list. Running the checks over `GOLDEN_DATASET.yaml` found it; the fix is
    that a comparison phrase must say *when*, not merely that something is unlike something
    else.
    """
    draft = {
        **CLEAN,
        "impression": (
            "Large-vessel vasculitis such as Takayasu arteritis fits this pattern in this "
            "age group better than atherosclerosis."
        ),
    }

    assert "invented_history" not in ids(check(draft))


def test_a_previously_healed_fracture_dates_a_lesion_and_does_not_need_a_prior() -> None:
    """Golden case ML-06: "previously healed thoracic fractures".

    Bare "previously" was in the comparison list, so a report dating a rib fracture as old
    was refused as an invented history — on a medicolegal case, where the distinction
    between an acute and a healed injury *is* the finding. A comparison that names what was
    seen before is still caught, in the test below.
    """
    draft = {
        **CLEAN,
        "findings": CLEAN["findings"] + " Previously healed rib fractures are noted.",
    }

    assert "invented_history" not in ids(check(draft))


def test_a_lesion_reported_as_previously_seen_still_needs_the_earlier_study() -> None:
    """The half that must not be lost with the two words removed above."""
    draft = {
        **CLEAN,
        "findings": CLEAN["findings"] + " The lesion is as previously described.",
    }

    assert "invented_history" in ids(check(draft))


def test_comparing_a_lesion_with_the_brain_beside_it_is_not_a_refusal() -> None:
    """The measured case. One of eleven ordinary dictated sentences the old list refused.

    "Hypointense compared with the surrounding white matter" compares two structures inside
    the study being reported. Refusing it with no prior supplied told the radiologist the
    machine had found an invented history where there is only standard prose — and this check
    catches none of the dataset's 306 hallucination probes either way, so the refusal bought
    nothing. It is advisory now: still on the page, no longer in the way.
    """
    draft = {
        **CLEAN,
        "findings": CLEAN["findings"]
        + " The lesion is hypointense compared with the surrounding white matter.",
    }

    quality = check(draft)
    flagged = [f for f in quality.findings if f.check == "invented_history"]
    assert [f.severity for f in flagged] == ["advisory"], flagged
    assert quality.status != "blocking"


def test_a_lesion_that_is_poorly_resolved_is_not_a_lesion_that_has_resolved() -> None:
    """Small lesions are "poorly resolved on this sequence" every day, and the check read
    that as a claim that something had resolved since an earlier study."""
    draft = {
        **CLEAN,
        "findings": CLEAN["findings"] + " A small cortical lesion is poorly resolved.",
    }

    quality = check(draft)
    assert [f.severity for f in quality.findings if f.check == "invented_history"] == ["advisory"]


def test_a_comparison_word_that_names_the_earlier_exam_is_still_refused() -> None:
    """Demoting the ambiguous phrases must not demote the sentence that is not ambiguous.

    "Compared with" alone is anatomy; "compared with the prior study" is a history claim, and
    it is caught by the temporal list, not by the advisory one.
    """
    draft = {
        **CLEAN,
        "findings": CLEAN["findings"]
        + " The lesion is unchanged compared with the prior study.",
    }

    quality = check(draft)
    assert [f.severity for f in quality.findings if f.check == "invented_history"] == ["block"]


# -- 4. certainty escalation ----------------------------------------------------------------------


def test_a_hedged_finding_written_as_a_confirmation_blocks() -> None:
    draft = {**CLEAN, "impression": "Neurocysticercosis confirmed."}

    quality = check(draft, findings=DICTATION + " A possible calcified granuloma.")

    assert "unsupported_certainty" in ids(quality)
    assert quality.status == "blocking"


def test_cannot_be_excluded_is_a_hedge_not_a_claim() -> None:
    """The single most important false positive to avoid in radiology: a negative the
    study cannot support is a hedge, and matching the word 'excluded' inside it would
    refuse the correct sentence."""
    draft = {**CLEAN, "impression": "Normal brain MRI. Demyelination cannot be excluded."}
    dictated = DICTATION + " Possible demyelination."

    assert "unsupported_certainty" not in ids(check(draft, findings=dictated))


def test_a_confident_dictation_may_be_restated_confidently() -> None:
    draft = {**CLEAN, "impression": "The headache has a confirmed structural cause."}

    quality = check(draft, findings="A 9 mm pituitary lesion. Confirmed cause of headache.")

    assert "unsupported_certainty" not in ids(quality)


# -- 5. claims outside this exam's reach ----------------------------------------------------------


def test_a_brain_study_does_not_exclude_a_pe() -> None:
    draft = {**CLEAN, "impression": "Normal brain MRI. No pulmonary embolism."}

    quality = check(draft)

    assert "unsupported_absence" in ids(quality)
    assert quality.status == "advisory"


def test_a_referrer_who_asked_about_it_gets_an_answer_about_it() -> None:
    draft = {**CLEAN, "impression": "Normal brain MRI. No pulmonary embolism."}

    quality = check(
        draft,
        clinical_indication=(
            "45-year-old, chronic headache and calf pain. Exclude pulmonary embolism."
        ),
    )

    assert "unsupported_absence" not in ids(quality)


def test_a_study_with_no_profile_makes_no_claims_about_structures() -> None:
    """An MRI knee is drafted and signed under the nine general checks and nothing
    invented about a protocol nobody here has described."""
    assert profile_for("MRI KNEE WITHOUT CONTRAST") is None


# -- 6. formatting ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "marker",
    ["**bright** signal", "\n- first finding\n- second finding", "```json", "## Head"],
)
def test_markup_in_a_section_refuses_the_draft(marker: str) -> None:
    """Section-by-section review is the control between a draft and a signature."""
    draft = {**CLEAN, "findings": CLEAN["findings"] + marker}

    assert "format_breach" in ids(check(draft))


def test_plain_prose_with_a_dash_in_a_sentence_is_not_markup() -> None:
    draft = {**CLEAN, "findings": CLEAN["findings"] + " The lesion is left-sided."}

    assert "format_breach" not in ids(check(draft))


# -- 7. identifiers -----------------------------------------------------------------------------


def test_a_name_the_model_invented_is_a_privacy_event_not_a_typo() -> None:
    draft = {**CLEAN, "impression": "Normal study. Mrs Fernandes has no lesion."}

    assert "invented_identifier" in ids(check(draft))


def test_a_number_of_six_digits_is_not_reported_by_this_application() -> None:
    draft = {**CLEAN, "findings": CLEAN["findings"] + " Compare with 481902."}

    assert "invented_identifier" in ids(check(draft))


def test_the_referrers_own_name_in_the_indication_is_not_invented() -> None:
    draft = {**CLEAN, "impression": "As Dr Rao requested, no structural lesion."}

    quality = check(draft, clinical_indication="Referred by Dr Rao for chronic headache")

    assert "invented_identifier" not in ids(quality)


def test_a_protocol_named_after_a_machine_is_not_a_person() -> None:
    """Golden cases C-02 and R-09. The title pattern used to be matched case-insensitively,
    which read "MR spectroscopy" and "MR angiography" as *Mr Spectroscopy* and refused three
    of the hundred golden reports for naming the sequences they were asked to name. A study
    name is not an identity, and a check that refuses correct studies is a check the
    department routes around — a lower-case title in the prose is the price paid for that,
    and the cheaper of the two failures."""
    draft = {
        **CLEAN,
        "technique": "MRI brain with MR spectroscopy and MR angiography.",
        "findings": CLEAN["findings"] + " MR spectroscopy shows a reduced NAA peak.",
    }

    assert "invented_identifier" not in ids(check(draft))


# -- 8. a model grading itself ----------------------------------------------------------------


def test_a_models_own_confidence_is_recorded_and_refused() -> None:
    quality = evaluate(
        CLEAN,
        study(),
        checked_at="2026-10-08T09:30:00Z",
        extra_sections=("confidence",),
    )

    flagged = [f for f in quality.findings if f.check == "self_reported_confidence"]
    assert flagged[0].severity == "advisory"
    assert "computed" in flagged[0].message


# -- 9. what the protocol covers ------------------------------------------------------------


def test_a_structure_neither_dictated_or_drafting_is_pointed_at_without_refusing() -> None:
    draft = {key: value for key, value in CLEAN.items() if key != "findings"}
    draft["findings"] = "Normal grey-white matter. No mass. Ventricles normal."
    submitted = study(findings="Normal grey-white matter. No mass.")

    quality = evaluate(
        draft,
        submitted,
        checked_at="2026-10-08T09:30:00Z",
        structure_checklist=MRI_BRAIN.structures,
    )

    assert "structure_coverage" in {f.check for f in quality.findings}
    assert quality.status != "blocking"


def test_an_always_firing_advisory_does_not_print_the_whole_template() -> None:
    """The twelve-item wall. Measured, then capped.

    Running the engine over the golden set's eight MRI brain cases (`audit-checks.py`,
    `check_load`) showed this advisory firing on all eight and naming 9 to 12 of the
    protocol's fourteen structures each time — a four-sentence dictation never mentions the
    pituitary. A finding that reprints the template is read as decoration, and it pushed the
    rest of the panel off the screen. The count stays exact; the list stops at six.
    """
    draft = {key: value for key, value in CLEAN.items() if key != "findings"}
    draft["findings"] = "Unremarkable."
    submitted = study(findings="Unremarkable.")

    quality = evaluate(
        draft,
        submitted,
        checked_at="2026-10-08T09:30:00Z",
        structure_checklist=MRI_BRAIN.structures,
    )

    message = next(f.message for f in quality.findings if f.check == "structure_coverage")
    listed = message.split(": ", 1)[1].split(". Advisory")[0]
    names = listed.replace(" and 8 more", "").split(", ")
    assert listed.endswith("and 8 more"), listed
    assert len(names) == 6, listed
    assert message.startswith("14 structure(s)"), message


def test_a_full_structures_list_raises_nothing() -> None:
    for label, terms in MRI_BRAIN.structures:
        assert terms, label
    assert profile_for("MRI BRAIN WITH CONTRAST") is MRI_BRAIN


# -- the confidence assessment --------------------------------------------------------------------


def test_confidence_refuses_the_word_confidence_for_a_blocking_draft() -> None:
    quality = check({**CLEAN, "findings": "A 27 mm lesion."})

    assessment = assess_confidence(quality, study())

    assert assessment.level == "not-safe-to-sign"
    assert "blocking" in assessment.reasons[0]


def test_confidence_names_the_inputs_that_are_missing() -> None:
    assessment = assess_confidence(check(CLEAN), study(technique=None, previous_reports=[]))

    assert any("acquisition parameters" in reason for reason in assessment.reasons)
    assert any("previous report" in reason for reason in assessment.reasons)


def test_a_slow_or_retried_answer_lowers_confidence_in_words_not_scores() -> None:
    """A number invented here would be read as a probability. Reasons are sentences a
    reviewer can act on: one more attempt is not 3% less trustworthy."""
    assessment = assess_confidence(
        check(CLEAN),
        study(),
        attempts=3,
        finish_reason="length",
    )

    assert any("3 attempts" in reason for reason in assessment.reasons)
    assert any("finish reason" in reason for reason in assessment.reasons)


def test_a_quality_finding_carries_its_words_for_the_reviewer_not_for_a_log() -> None:
    finding = QualityFinding(
        check="unsupported_measurement",
        severity="block",
        section="findings",
        message="A measurement of 27 is nowhere in the submitted text.",
        evidence="27",
    )

    assert finding.evidence == "27"


# -- malformed submissions ------------------------------------------------------------------------


def test_a_sixth_previous_report_is_refused_rather_than_silently_dropped() -> None:
    """Truncating the priors would produce a report that reads as though it compared
    everything and in fact compared the first five."""
    priors = [
        {
            "reported_on": f"202{i}-01-01",
            "modality": "MRI",
            "study": "MRI BRAIN",
            "report": "Normal.",
        }
        for i in range(6)
    ]

    with pytest.raises(ValidationError):
        study(previous_reports=priors)


def test_priors_that_would_not_fit_the_message_are_refused() -> None:
    """Four full reports is more text than a draft request can carry. The alternative —
    sending the two that fit — would produce a report that reads as though it had
    compared all four."""
    priors = [
        {
            "reported_on": f"202{4 - i}-06-11",
            "modality": "MRI",
            "study": "MRI BRAIN",
            "report": "N" * 1_900,
        }
        for i in range(4)
    ]

    with pytest.raises(ValidationError) as caught:
        study(previous_reports=priors)

    assert "will not fit" in str(caught.value)


def test_a_prior_missing_its_date_is_refused() -> None:
    with pytest.raises(ValidationError):
        study(previous_reports=[{"modality": "MRI", "study": "MRI BRAIN", "report": "Normal."}])


def test_the_submission_takes_no_extra_clinical_fields() -> None:
    """An unknown key is a field nobody validates or exports — and in this application
    the most likely unknown key is a patient identifier, which it must not hold."""
    with pytest.raises(ValidationError):
        study(patient_name="A. Nair")


def test_grounding_text_carries_the_priors_into_the_check() -> None:
    priors = [
        {
            "reported_on": "2024-06-11",
            "modality": "MRI",
            "study": "MRI BRAIN",
            "report": "A 12 mm left temporal cyst.",
        }
    ]

    assert "12 mm" in study(previous_reports=priors).grounding_text
