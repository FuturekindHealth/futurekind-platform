"""Human review: the stage that makes the draft somebody's statement.

A sign-off needs a name. An amendment needs to be visible in the document without
erasing what the model wrote, and must never turn into a lock: a report that a
human has edited stays as automatable as it was before, because a flag that refuses
later automation is how a useful feature becomes a chore.
"""

from __future__ import annotations

import pytest

from futurekind_radiology.errors import ReviewError
from futurekind_radiology.report import SECTION_KEYS
from tests.conftest import FROZEN_STAMP, completion, drafted_report, fixture_text, make_copilot

DRAFT, _ = drafted_report()


def review(**kwargs):
    copilot, _ = make_copilot(completion(fixture_text("normal_ct_head.json")))
    return copilot.review(DRAFT, **kwargs)


def sign(**kwargs):
    return review(decision="signed", clinician="Dr A. Nair", **kwargs)


# -- the sign-off -------------------------------------------------------------------------------


def test_signing_names_the_clinician_and_the_moment() -> None:
    signed = sign()

    record = signed.metadata.review
    assert record.state == "signed"
    assert record.clinician == "Dr A. Nair"
    assert record.reviewed_at == FROZEN_STAMP
    assert record.amendments == []


def test_the_original_draft_is_never_touched() -> None:
    """The reviewer gets a new document; the draft they were shown still exists."""
    before = DRAFT.model_dump_json()

    sign(amendments={"impression": "Revised impression."})

    assert DRAFT.model_dump_json() == before
    assert DRAFT.metadata.review.state == "pending_review"


def test_a_signoff_without_a_name_is_refused() -> None:
    """P3: a clinical statement has an owner, and an unattributed one is not a
    sign-off no matter what the screen says."""
    with pytest.raises(ReviewError):
        review(decision="signed", clinician="   ")


def test_an_unknown_decision_is_refused() -> None:
    with pytest.raises(ReviewError) as caught:
        review(decision="approved", clinician="Dr A. Nair")

    assert caught.value.details["decision"] == "approved"


# -- amendments ---------------------------------------------------------------------------------


def test_an_amendment_replaces_the_section_and_says_which_one() -> None:
    revised = "Large haemorrhage. Immediate neurosurgical admission."

    signed = sign(amendments={"impression": revised})

    assert signed.impression == revised
    assert signed.metadata.review.amendments == ["impression"]


def test_the_models_authorship_survives_a_humans_edit() -> None:
    """The provenance block is what the model said it did, and an edit does not
    rewrite history — it is recorded next to it in the review."""
    original = DRAFT.model_provenance

    signed = sign(amendments={"findings": "Corrected measurement: 4.1 cm."})

    assert signed.model_provenance == original
    assert signed.findings == "Corrected measurement: 4.1 cm."


def test_several_sections_can_be_amended_at_once() -> None:
    signed = sign(
        amendments={
            "technique": "CT head without contrast, 5 mm slices.",
            "recommendations": "Repeat imaging at 24 hours.",
        }
    )

    assert signed.metadata.review.amendments == ["recommendations", "technique"]
    assert signed.technique == "CT head without contrast, 5 mm slices."


def test_amending_a_section_that_does_not_exist_is_refused() -> None:
    """An extra key would become an unnamed note nobody reviews or exports."""
    with pytest.raises(ReviewError) as caught:
        sign(amendments={"differential": "Meningioma."})

    assert caught.value.details["unknown_sections"] == ["differential"]
    assert tuple(caught.value.details["sections"]) == SECTION_KEYS


def test_a_refused_amendment_changes_nothing() -> None:
    before = DRAFT.model_dump_json()

    with pytest.raises(ReviewError):
        sign(amendments={"impression": "fine", "differential": "nope"})

    assert DRAFT.model_dump_json() == before


# -- returning for correction --------------------------------------------------------------------


def test_a_returned_report_explains_itself() -> None:
    returned = review(
        decision="returned_for_correction",
        clinician="Dr A. Nair",
        comment="The measurements do not match the scout image.",
    )

    assert returned.metadata.review.state == "returned_for_correction"
    assert returned.metadata.review.comment == (
        "The measurements do not match the scout image."
    )


def test_a_return_without_a_comment_is_refused() -> None:
    """A bare rejection gives the next draft nothing to fix."""
    with pytest.raises(ReviewError) as caught:
        review(decision="returned_for_correction", clinician="Dr A. Nair")

    assert caught.value.details["comment"] == "required"


def test_a_returned_report_can_be_signed_afterwards() -> None:
    copilot, _ = make_copilot(completion(fixture_text("normal_ct_head.json")))
    returned = copilot.review(
        DRAFT,
        decision="returned_for_correction",
        clinician="Dr A. Nair",
        comment="Impression too confident for a non-contrast study.",
    )

    signed = copilot.review(
        returned,
        decision="signed",
        clinician="Dr A. Nair",
        amendments={"impression": "No acute haemorrhage. Ischaemia not excluded."},
    )

    assert signed.metadata.review.state == "signed"
    assert signed.metadata.review.amendments == ["impression"]


def test_a_signed_report_can_be_reviewed_again() -> None:
    """Editing never locks the document: a correction after sign-off is a further
    named act, not a forbidden one."""
    copilot, _ = make_copilot(completion(fixture_text("normal_ct_head.json")))
    first = copilot.review(DRAFT, decision="signed", clinician="Dr A. Nair")

    second = copilot.review(
        first,
        decision="signed",
        clinician="Dr B. Rao",
        amendments={"recommendations": "Add urgent MRI."},
    )

    assert second.metadata.review.clinician == "Dr B. Rao"
    assert second.metadata.review.amendments == ["recommendations"]
    assert second.recommendations == "Add urgent MRI."
