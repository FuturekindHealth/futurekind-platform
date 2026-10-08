"""The prompt is a clinical instrument, so its shape is tested like one.

Three properties: it demands exactly the five sections and nothing outside them; it
carries what the clinician supplied without paraphrasing it; and it smuggles no
infrastructure — no alias, no model name, no provider — because an application may
not reach past the Gateway even in prose addressed to the model (P17).
"""

from __future__ import annotations

import re

from futurekind_radiology.prompt import PROMPT_VERSION, build_messages
from futurekind_radiology.report import MODEL_SECTION_KEYS
from tests.conftest import submission


def turns(submission_payload=None, **extra) -> list[dict[str, str]]:
    messages = build_messages(submission_payload or submission(), **extra)
    return messages


def system(messages: list[dict[str, str]]) -> str:
    return messages[0]["content"]


def user(messages: list[dict[str, str]]) -> str:
    return messages[1]["content"]


def test_the_conversation_is_a_system_rule_book_and_one_clinical_turn() -> None:
    messages = turns()

    assert [message["role"] for message in messages] == ["system", "user"]
    assert all(message["content"].strip() for message in messages)


def test_every_section_the_model_owns_is_demanded_by_name() -> None:
    text = system(turns())

    for key in MODEL_SECTION_KEYS:
        assert f'"{key}"' in text


def test_the_four_keys_are_the_whole_demand() -> None:
    """A fifth key in the demand would be a section nobody reviews — and the
    indication is deliberately not asked for, because it is not the model's to write."""
    demanded = re.findall(r'^\s*"([a-z_]+)": "\.\.\."', system(turns()), flags=re.MULTILINE)

    assert tuple(demanded) == MODEL_SECTION_KEYS
    assert "clinical_indication" not in system(turns())


def test_the_model_is_told_not_to_restate_the_indication() -> None:
    assert "restate, summarise or reinterpret" in system(turns()).lower()
    assert "not yours to rewrite" in user(turns()).lower()


def test_dropping_a_dictated_observation_is_named_as_a_risk() -> None:
    """Inventing a finding and losing one are the same error, and the prompt says so
    in the same breath."""
    assert "dropping one is as dangerous as inventing one" in system(turns()).lower()


def test_the_answer_is_required_to_be_json_and_nothing_else() -> None:
    text = system(turns()).lower()

    assert "reply with one json object and nothing outside it" in text
    assert "no preamble" in text


def test_inventing_a_finding_is_prohibited_in_words() -> None:
    text = system(turns()).lower()

    assert "do not add a finding" in text
    assert "you are not the author" in text


def test_an_absent_technique_is_declared_absent_rather_than_guessed() -> None:
    messages = turns()

    assert 'Not supplied' in user(messages)
    assert "Technique not provided." in system(messages)


def test_a_supplied_technique_reaches_the_model_verbatim() -> None:
    study = submission(technique="MRI 1.5T, axial T1 and T2, no contrast.")
    messages = turns(study)

    assert "MRI 1.5T, axial T1 and T2, no contrast." in user(messages)


def test_the_dictation_is_passed_through_without_rewriting() -> None:
    study = submission(findings="A 12 mm calcified meningioma at the right sphenoid wing.")
    messages = turns(study)

    assert "A 12 mm calcified meningioma at the right sphenoid wing." in user(messages)


def test_the_clinical_context_travels_with_the_findings() -> None:
    study = submission()
    messages = turns(study)
    text = user(messages)

    assert study.study in text
    assert study.modality in text
    assert study.clinical_indication in text
    assert study.findings in text


def test_a_reviewers_steering_joins_the_rules_not_the_clinical_text() -> None:
    """The reviewer owns the instruction; the dictation stays the dictation, so a
    redraft note cannot be mistaken for something seen on the images."""
    messages = turns(extra_instructions={"focus": "Comment on the posterior fossa."})

    assert "Comment on the posterior fossa." in system(messages)
    assert "Comment on the posterior fossa." not in user(messages)


def test_no_infrastructure_name_can_enter_the_prompt() -> None:
    messages = turns()
    text = " ".join(message["content"] for message in messages).lower()

    for forbidden in (
        "fk-reasoning",
        "ollama",
        "qwen",
        "litellm",
        "temperature",
        "allow_downgrade",
    ):
        assert forbidden not in text


def test_the_prompt_is_versioned_so_a_report_can_be_traced_to_it() -> None:
    # 0.3.0: the follow-up section, the number-is-the-clinician's rule, and the
    # explicit "no priors supplied" statement. docs/product/PROMPT_LIBRARY.md §1
    # carries the same text, and a bump here without a bump there is a fork.
    assert PROMPT_VERSION == "radiology-report-draft/0.3.0"
    assert PROMPT_VERSION.count(".") == 2
