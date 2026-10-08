"""Clinical formatting: what a reviewer sees is what a department files.

The property that matters is that no rendering can lose, reorder or rename a
section relative to the document that was reviewed, and that a printout cannot be
mistaken for a signed report. So the assertions here are about order, headings and
the one banner line at the top of the page.
"""

from __future__ import annotations

import json

import pytest

from futurekind_radiology.rendering import EXPORT_FORMATS, render
from futurekind_radiology.report import SECTION_KEYS, RadiologyReport
from tests.conftest import FROZEN_STAMP, completion, drafted_report, fixture_text, make_copilot

DRAFT, _ = drafted_report()

HEADINGS = ("CLINICAL INDICATION", "TECHNIQUE", "FINDINGS", "IMPRESSION", "RECOMMENDATIONS")


def signed():
    copilot, _ = make_copilot(completion(fixture_text("normal_ct_head.json")))
    return copilot.review(DRAFT, decision="signed", clinician="Dr A. Nair")


def test_the_three_formats_are_the_whole_set() -> None:
    assert EXPORT_FORMATS == ("json", "text", "markdown")


def test_the_printout_prints_the_sections_in_signing_order() -> None:
    page = render(DRAFT, output_format="text")
    positions = [page.index(heading) for heading in HEADINGS]

    assert positions == sorted(positions)


def test_the_headings_are_the_section_names_a_radiologist_expects() -> None:
    page = render(DRAFT, output_format="text")

    assert tuple(heading for heading in HEADINGS if heading in page) == HEADINGS


@pytest.mark.parametrize("key", SECTION_KEYS)
def test_no_rendering_loses_a_section(key: str) -> None:
    body = DRAFT.section(key)

    for output_format in ("text", "markdown"):
        assert body in render(DRAFT, output_format=output_format)


def test_an_unsigned_page_says_so_on_the_first_line() -> None:
    page = render(DRAFT, output_format="text").splitlines()

    assert page[0] == "RADIOLOGY REPORT"
    assert page[1] == "DRAFT — NOT SIGNED. Not for clinical use."


def test_a_signed_page_carries_the_name_that_owns_it() -> None:
    page = render(signed(), output_format="text")

    assert f"SIGNED BY THE REPORTING RADIOLOGIST — Dr A. Nair, {FROZEN_STAMP}" in page
    assert "Not for clinical use." not in page
    assert f"Reviewed  : {FROZEN_STAMP}" in page


def test_the_header_of_a_returned_report_says_where_it_is() -> None:
    copilot, _ = make_copilot(completion(fixture_text("normal_ct_head.json")))
    returned = copilot.review(
        DRAFT,
        decision="returned_for_correction",
        clinician="Dr A. Nair",
        comment="Measurements do not match the scout image.",
    )

    page = render(returned, output_format="text")

    assert "RETURNED FOR CORRECTION — Dr A. Nair" in page
    assert "Measurements do not match the scout image." in page


def test_the_study_and_the_document_are_identifiable_at_the_top_of_the_page() -> None:
    page = render(DRAFT, output_format="text")

    assert "Study     : CT HEAD WITHOUT CONTRAST" in page
    assert "Modality  : CT" in page
    assert "Report id : fk-test-request-1" in page
    assert f"Drafted   : {FROZEN_STAMP}" in page


def test_the_provenance_block_is_on_the_page_not_only_in_the_json() -> None:
    """A printed report still has to answer which model answered and whether a
    human signed it (P8)."""
    page = render(DRAFT, output_format="text")

    for line in (
        "Skill: radiology-report (capability reasoning)",
        "Policy: clinical risk high, audit True, downgrade allowed False, "
        "approval required False",
        "Model: ollama/qwen3:14b via litellm (selected by skill, 1 attempt)",
        "Finish reason: stop",
        "Tokens: 640 prompt / 210 completion / 850 total",
        "Gateway latency: 4200 ms",
        "Gateway request id: fk-test-request-1",
    ):
        assert line in page, line


def test_a_degraded_answer_is_stamped_on_the_page() -> None:
    """This draft should not exist — the copilot refuses one — but a document that
    somehow carries it must not be able to hide that."""
    degraded = DRAFT.model_copy(
        update={"model_provenance": DRAFT.model_provenance.model_copy(update={"degraded": True})}
    )

    assert ", DEGRADED)" in render(degraded, output_format="text")
    assert "- Model: ollama/qwen3:14b via litellm (selected by skill, 1 attempt, DEGRADED)" in (
        render(degraded, output_format="markdown")
    )


def test_the_markdown_uses_the_same_headings_as_the_printout() -> None:
    screen = render(DRAFT, output_format="markdown")

    for heading in HEADINGS:
        assert f"## {heading}" in screen
    assert "## Provenance" in screen


def test_the_json_format_is_the_document_itself() -> None:
    """No fourth rendering that could disagree with the other three."""
    payload = json.loads(render(DRAFT, output_format="json"))

    assert tuple(payload) == (
        "clinical_indication",
        "technique",
        "findings",
        "impression",
        "recommendations",
        "metadata",
        "model_provenance",
        "skill",
        "policy",
    )
    assert RadiologyReport.model_validate(payload) == DRAFT


def test_sections_a_model_added_beyond_the_five_are_named_not_silently_dropped() -> None:
    answer = json.loads(fixture_text("normal_ct_head.json"))
    answer["differential_diagnosis"] = "Ischaemic stroke."
    report, _ = drafted_report(content=json.dumps(answer))

    page = render(report, output_format="text")

    assert report.metadata.extra_sections == ["differential_diagnosis"]
    assert "the model also returned differential_diagnosis" in page
    assert "Ischaemic stroke." not in page


def test_an_unknown_format_is_refused() -> None:
    with pytest.raises(ValueError):
        render(DRAFT, output_format="fhir")
