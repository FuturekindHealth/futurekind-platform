"""The prompt, and the version of it a report can be traced back to.

The output contract is a strict JSON object with five keys, and nothing else. That
is a clinical decision as much as a parsing one: the sections are the ones a
radiologist signs, so a model that answers in flowing prose has not produced a
draft even when it produced correct medicine — it has produced something a
reviewer cannot check section by section.

The authority for this text is `docs/product/PROMPT_LIBRARY.md` §1, which carries
the same prompt verbatim and the seven clauses every prompt in this library must
carry. Changing one without the other is the fork this file's existence is meant
to prevent.

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
#:
#: 0.3.1 states each rule once. The technique rule was in three places and the
#: indication rule in two, and the closing line named the five sections a third
#: time after the JSON contract had already listed them. What is instructed is
#: unchanged; what the model has to read to be instructed by it is smaller.
#: 0.3.0 (Sprint 9) adds the `follow_up` key and states the rule that a number is
#: the clinician's, not the model's. 0.2.0 made the clinical indication
#: non-model-owned after a live run rewrote a referrer's question.
PROMPT_VERSION = "radiology-report-draft/0.3.1"

#: The five sections the model writes. The clinical indication is not among them:
#: it is the referrer's question, recorded from the submission, and a model that
#: restates it has been given the chance to change it.
REPORT_SECTIONS = MODEL_SECTION_KEYS

_SYSTEM_PROMPT = """You are assisting a radiologist draft a report for one imaging study.

You are not the author of the report. A named clinician reviews every section
before it is used, and a statement you add that is not in the observations below
could reach a patient. So:

- Write only what the supplied observations support. Do not add a finding, a
  sign or a diagnosis that was not described.
- A size, count or index must appear in the observations or in a previous report
  supplied below. Never state a number of your own, and never round a described
  lesion into a measured one.
- Carry every observation the clinician dictated into your findings section, in
  report prose. Dropping one is as dangerous as inventing one.
- If the observations are incomplete, negative or uncertain, say so in the
  section that owns it rather than filling the gap.
- Describe only what this study shows. Do not state that something is unchanged,
  resolved, new or stable compared with an earlier scan unless that earlier report
  is supplied below.
- If the technique was not supplied, write "Technique not provided." Do not name a
  scanner, a sequence or a contrast protocol that was not given.
- The clinical indication has already been recorded by the clinician. Do not
  restate, summarise or reinterpret it.
- Do not invent a patient name, number or any identifier that is not supplied.
- Use plain clinical prose inside each section. No markdown, no bullet symbols,
  no headings.
- Write the impression as the clinical conclusion, not a restatement of the
  findings. A finding the observations hedge as possible, subtle or uncertain stays
  hedged in the impression; do not settle it.
- Recommendations are what to do now. Follow-up is when to look again, and what
  with. Keep them apart, because a surveillance interval buried in a paragraph of
  referrals is an interval nobody books.
- If there is genuinely nothing to say in a section, write "None." there. Do not
  leave it empty and do not omit it.

Reply with one JSON object and nothing outside it: no preamble, no explanation
after the closing brace. It must contain exactly these five keys, each with a
string value:

{sections}"""


def _prior_block(submission: StudySubmission) -> str:
    """The earlier reports, or the explicit statement that there are none.

    Both halves matter. A supplied prior is the only legitimate source of a
    comparison, and the absence of one has to be *said* to the model — silence
    reads as permission, and "unchanged from prior" in a report nobody compared is
    the invention the quality check would later have to refuse.
    """
    if not submission.previous_reports:
        return (
            "Previous reports: none supplied. There is nothing here to compare against, so "
            "describe only what this study shows."
        )
    lines = ["Previous reports supplied for comparison:"]
    for prior in submission.previous_reports:
        lines += [
            f"— Reported {prior.reported_on}: {prior.modality} {prior.study}",
            prior.report,
        ]
    return "\n".join(lines)


def _user_prompt(submission: StudySubmission) -> str:
    """The clinical turn: what was submitted, labelled by whose words each part is.

    This turn states no rules. Every instruction lives in the system turn, so a
    radiologist reading one place finds the whole contract rather than three partial
    reminders of it — and the technique and indication rules had crept in here as
    well, doubling what the system turn already says.
    """
    technique = submission.technique if submission.has_technique else "Not supplied"
    return f"""Study: {submission.study}
Modality: {submission.modality}
Clinical indication (the referrer's own words):
{submission.clinical_indication}
Technique: {technique}

{_prior_block(submission)}

Observations dictated by the reporting clinician:
{submission.findings}

Draft the structured report for this study."""


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
