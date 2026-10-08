"""Reading a model answer as a report — and refusing to when it is not one.

The property this file protects: **a section is never invented.** Every path that
does not yield five non-empty sections of text raises, and the raise carries the
shape of the problem rather than the patient's story.
"""

from __future__ import annotations

import json

import pytest

from futurekind_radiology.errors import ModelOutputError
from futurekind_radiology.report import MODEL_SECTION_KEYS, parse_model_answer
from tests.conftest import fixture_text, golden


def test_a_golden_answer_reads_as_the_four_sections_the_model_owns() -> None:
    parsed = parse_model_answer(fixture_text("normal_ct_head.json"))

    assert tuple(parsed.sections) == MODEL_SECTION_KEYS
    expected = golden("normal_ct_head.json")
    for key in MODEL_SECTION_KEYS:
        assert parsed.sections[key] == expected[key]


def test_an_answer_wrapped_in_a_sentence_is_still_read() -> None:
    """A deployment that adds a preamble has still produced a report.

    Discarding it because of two sentences of chat would be its own clinical
    failure, so the object is extracted and every section is kept whole.
    """
    parsed = parse_model_answer(fixture_text("wrapped_answer.txt"))

    assert parsed.sections["impression"] == (
        "Non-displaced right temporal bone fracture extending to the sphenoid wing. "
        "No acute intracranial haemorrhage."
    )
    # This answer also restates the clinical indication, which was not asked for.
    assert parsed.extra_keys == ("clinical_indication",)


def test_a_fenced_block_is_stripped_by_the_scan() -> None:
    fenced = "```json\n" + fixture_text("normal_ct_head.json") + "\n```"
    parsed = parse_model_answer(fenced)

    assert parsed.sections["recommendations"].startswith("Clinical correlation.")


def test_prose_is_refused_not_reformatted() -> None:
    """The dangerous case is a clinically good answer that cannot be signed section
    by section. It is refused, and no report object exists for anyone to export."""
    with pytest.raises(ModelOutputError) as caught:
        parse_model_answer(fixture_text("prose_answer.txt"))

    assert caught.value.details["reason"] == "no_json_object"
    assert caught.value.code == "model_output_unusable"


def test_a_truncated_object_is_refused_not_repaired() -> None:
    cut = fixture_text("normal_ct_head.json")[:180]
    with pytest.raises(ModelOutputError) as caught:
        parse_model_answer(cut)

    assert caught.value.details["reason"] == "unterminated_json_object"


def test_invalid_json_is_refused_with_the_shape_of_the_problem() -> None:
    broken = '{"clinical_indication": "x", "technique": "y",}'
    with pytest.raises(ModelOutputError) as caught:
        parse_model_answer(broken)

    assert caught.value.details["reason"] == "invalid_json"
    assert "position" in caught.value.details


def test_a_missing_section_names_it_and_produces_nothing() -> None:
    answer = golden("normal_ct_head.json")
    del answer["impression"]

    with pytest.raises(ModelOutputError) as caught:
        parse_model_answer(json.dumps(answer))

    assert caught.value.details["missing"] == ["impression"]


@pytest.mark.parametrize("key", MODEL_SECTION_KEYS)
def test_each_section_is_required(key: str) -> None:
    answer = golden("normal_ct_head.json")
    del answer[key]

    with pytest.raises(ModelOutputError):
        parse_model_answer(json.dumps(answer))


@pytest.mark.parametrize("key", MODEL_SECTION_KEYS)
def test_an_empty_section_is_refused(key: str) -> None:
    """A blank section in a radiology report reads as a normal study."""
    answer = golden("normal_ct_head.json")
    answer[key] = "   "

    with pytest.raises(ModelOutputError) as caught:
        parse_model_answer(json.dumps(answer))

    assert caught.value.details == {"reason": "section_empty", "section": key}


def test_findings_dictated_as_an_array_are_kept_whole() -> None:
    answer = golden("normal_ct_head.json")
    answer["findings"] = ["Ventricles are normal in size.", "No midline shift."]

    parsed = parse_model_answer(json.dumps(answer))

    assert parsed.sections["findings"] == (
        "Ventricles are normal in size.\nNo midline shift."
    )


@pytest.mark.parametrize("value", [7, None, True, {"detail": "x"}, 4.5])
def test_a_section_that_is_not_text_is_refused_rather_than_coerced(value: object) -> None:
    """Coercion would write wording the model never wrote into a clinical document."""
    answer = golden("normal_ct_head.json")
    answer["impression"] = value  # type: ignore[assignment]

    with pytest.raises(ModelOutputError) as caught:
        parse_model_answer(json.dumps(answer))

    assert caught.value.details["reason"] == "section_not_text"


def test_extra_keys_are_recorded_and_not_dropped_in_silence() -> None:
    answer = golden("normal_ct_head.json")
    answer["differential_diagnosis"] = "Ischaemic stroke, haemorrhage excluded."

    parsed = parse_model_answer(json.dumps(answer))

    assert parsed.extra_keys == ("differential_diagnosis",)
    assert "differential_diagnosis" not in parsed.sections


def test_an_answer_wrapped_in_an_array_is_read_as_the_object_it_contains() -> None:
    """Documented behaviour, not an aspiration: the scan finds the object.

    The alternative — refusing because a deployment put the report inside an
    array — would throw away a complete draft for a formatting accident.
    """
    wrapped = json.dumps([golden("normal_ct_head.json")])

    parsed = parse_model_answer(wrapped)

    assert parsed.sections["impression"] == golden("normal_ct_head.json")["impression"]


# -- the privacy property ----------------------------------------------------------------------


def test_a_refusal_never_quotes_the_answer() -> None:
    """The failure text is the one thing guaranteed to be logged and shown.

    The fixture carries an identifiable clinical story; none of it may reappear in
    the exception's message or details.
    """
    prose = fixture_text("prose_answer.txt")

    with pytest.raises(ModelOutputError) as caught:
        parse_model_answer(prose)

    rendered = caught.value.message + json.dumps(caught.value.details)
    for phrase in ("middle cerebral artery", "insular cortex", "thrombolysis", "restricted"):
        assert phrase not in rendered
    assert "answer_chars" in caught.value.details


def test_a_missing_section_refusal_names_keys_only() -> None:
    answer = golden("hypertensive_bleed.json")
    del answer["findings"]

    with pytest.raises(ModelOutputError) as caught:
        parse_model_answer(json.dumps(answer))

    rendered = caught.value.message + json.dumps(caught.value.details)
    for phrase in ("basal ganglia", "subfalcine", "4.5 cm"):
        assert phrase not in rendered
