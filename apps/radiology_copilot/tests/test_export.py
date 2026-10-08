"""Export: the last step, and the one with a gate in front of it.

The workflow the brief specifies is submit → draft → review → export, in that
order, so an export of an unsigned draft is refused rather than warned about. What
is *not* done is locking anything after the fact: a signed report can be exported
again in any format, and a report amended after sign-off stays exportable.
"""

from __future__ import annotations

import pytest

from futurekind_radiology.errors import ReviewError, UnsignedExportError
from tests.conftest import FROZEN_STAMP, completion, drafted_report, fixture_text, make_copilot

DRAFT, _ = drafted_report()


def copilot():
    return make_copilot(completion(fixture_text("normal_ct_head.json")))[0]


def signed():
    return copilot().review(DRAFT, decision="signed", clinician="Dr A. Nair")


@pytest.mark.parametrize("output_format", ["json", "text", "markdown"])
def test_a_signed_report_exports_in_every_format(output_format: str) -> None:
    result = copilot().export(signed(), output_format=output_format)

    assert result.output_format == output_format
    assert result.content.strip()
    assert result.signed_by == "Dr A. Nair"
    assert result.signed_at == FROZEN_STAMP
    assert result.report_id == "fk-test-request-1"


def test_an_unsigned_draft_does_not_export() -> None:
    with pytest.raises(UnsignedExportError) as caught:
        copilot().export(DRAFT)

    assert caught.value.code == "report_unsigned"
    assert caught.value.status_code == 409
    assert caught.value.details["state"] == "pending_review"
    assert "signed by a radiologist" in caught.value.message


def test_a_returned_report_does_not_export() -> None:
    returned = copilot().review(
        DRAFT,
        decision="returned_for_correction",
        clinician="Dr A. Nair",
        comment="Impression overstates a non-contrast study.",
    )

    with pytest.raises(UnsignedExportError) as caught:
        copilot().export(returned)

    assert caught.value.details["state"] == "returned_for_correction"
    # The name of the reviewer who sent it back is not a signature.
    assert caught.value.details["clinician"] == "Dr A. Nair"


def test_the_filename_carries_the_document_not_the_patient() -> None:
    """Filenames reach shell history, backups and mail attachments. The report id
    is enough to find the study; the study's name is not something to duplicate."""
    result = copilot().export(signed(), output_format="text")

    assert result.filename == "radiology-report-fk-test-request-1.txt"
    assert "CT HEAD" not in result.filename
    assert "hemiparesis" not in result.filename


def test_the_extension_matches_the_format() -> None:
    for output_format, extension in (("json", "json"), ("text", "txt"), ("markdown", "md")):
        result = copilot().export(signed(), output_format=output_format)
        assert result.filename.endswith(f".{extension}")


def test_export_can_be_repeated_and_reformatted_after_signoff() -> None:
    """Re-export is a normal act: a department prints it, then sends it, then files
    the JSON. A lock on the second export would only teach people to skip review."""
    first = copilot().export(signed(), output_format="text")
    second = copilot().export(signed(), output_format="json")

    assert first.content != second.content
    assert second.content.startswith("{")


def test_a_reexport_reflects_an_amendment_made_after_signing() -> None:
    service = copilot()
    amended = service.review(
        signed(),
        decision="signed",
        clinician="Dr B. Rao",
        amendments={"recommendations": "Add MRI with contrast."},
    )

    result = service.export(amended, output_format="text")

    assert "Add MRI with contrast." in result.content
    assert result.amended_sections == ["recommendations"]
    assert result.signed_by == "Dr B. Rao"


def test_an_unsupported_format_is_named_with_what_exists() -> None:
    with pytest.raises(ReviewError) as caught:
        copilot().export(signed(), output_format="pdf")

    assert caught.value.details["supported"] == ["json", "text", "markdown"]
