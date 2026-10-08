"""The prompt, and the version of it a report can be traced back to.

The output contract is a strict JSON object with five keys, and nothing else.
That is a clinical decision as much as a parsing one: the sections are the ones a
radiologist signs, so a model that answers in flowing prose has not produced a
draft even when it produced correct medicine — it has produced something a
reviewer cannot check section by section.

What is *not* here matters too. ``genesis/report_style.md`` and
``agents/radiology/style-guide.md`` were empty placeholders and are deleted from this
repository, so there is no house style to encode: no institutional voice, no
measurement table, no department-specific vocabulary. This prompt states the minimum
that makes an AI draft checkable, and says plainly that the style authority has not
been written.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .report import MODEL_SECTION_KEYS
from .submission import StudySubmission

#: Bump when the wording below changes, so a stored report says which prompt
#: produced it. Provenance is not only about which model answered (P8).
PROMPT_VERSION = "radiology-report-draft/0.2.0"

#: The four sections the model writes. The clinical indication is not among them:
#: it is the referrer's question, recorded from the submission, and a model that
#: restates it has been given the chance to change it.
REPORT_SECTIONS = MODEL_SECTION_KEYS

_SYSTEM_PROMPT = """You are assisting a radiologist draft a report for one imaging study.

You are not the author of the report. A named clinician reviews every section
before it is used, and a statement you add that is not in the observations below
could reach a patient. So:

- Write only what the supplied observations support. Do not add a finding, a
  measurement, a sign or a diagnosis that was not described.
- Carry every observation the clinician dictated into your findings section, in
  report prose. Dropping one is as dangerous as inventing one.
- If the observations are incomplete, negative or uncertain, say so in the
  section that owns it rather than filling the gap.
- If the technique was not supplied, write "Technique not provided." in the
  technique section. Do not name a scanner, a sequence or a contrast protocol
  that was not given.
- The clinical indication has already been recorded by the clinician. Do not
  restate, summarise or reinterpret it.
- Do not invent a patient name, number or any identifier that is not supplied.
- Use plain clinical prose inside each section. No markdown, no bullet symbols,
  no headings.
- Write the impression as the clinical conclusion, not a restatement of the
  findings.
- If there is genuinely nothing to recommend, write "None." in the
  recommendations section. Do not leave it empty and do not omit it.

Reply with one JSON object and nothing outside it: no preamble, no explanation
after the closing brace. It must contain exactly these four keys, each with a
string value:

{sections}"""


def _user_prompt(submission: StudySubmission) -> str:
    technique = (
        submission.technique
        if submission.has_technique
        else 'Not supplied — write "Technique not provided."'
    )
    return f"""Study: {submission.study}
Modality: {submission.modality}
Clinical indication (already recorded — context for you, not yours to rewrite):
{submission.clinical_indication}
Technique: {technique}

Observations dictated by the reporting clinician:
{submission.findings}

Draft the structured report for this study: findings, impression, recommendations,
and the technique line only if it was not supplied above."""


def build_messages(
    submission: StudySubmission,
    *,
    extra_instructions: Mapping[str, Any] | None = None,
) -> list[dict[str, str]]:
    """The conversation handed to the Gateway for one draft.

    ``extra_instructions`` is the reviewer's way to steer a redraft — "focus on
    the posterior fossa" — without the platform inventing a second prompt. It is
    appended to the system turn, where the rules live, rather than to the user
    turn, which carries the clinical content.
    """
    sections = "\n".join(f'  "{key}": "...",' for key in REPORT_SECTIONS).rstrip(",")
    system = _SYSTEM_PROMPT.format(sections=sections)
    for note in (extra_instructions or {}).values():
        text = str(note).strip()
        if text:
            system = f"{system}\n\nAdditional instruction from the reviewing clinician: {text}"
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": _user_prompt(submission)},
    ]


__all__ = ["PROMPT_VERSION", "REPORT_SECTIONS", "build_messages"]
