"""What a clinician submits: the things the workflow starts with.

Indication, modality, study, technique and the dictated observations are the input
the clinical workflow names (`docs/product/RADIOLOGY_WORKFLOW.md` S4). A draft
without an exam name is not a document anyone can file, so the study label is not
optional either.

Previous reports are the fifth input, and the one that changes what a draft is
allowed to say. A radiologist reading an MRI brain is comparing it against
something; a model that has been given nothing to compare against and writes
"unchanged from prior" has invented the patient's history. That is why the prior
text is submitted here rather than implied, and why the quality check
(`quality.py`) treats comparison language as a claim about this field.

There is deliberately **no patient identifier field**. ``docs/DOMAIN_MODEL.md``
Q2 forbids inventing an identifier format here, and an MRN invented by an
application is exactly the defect that outlives every convenience attached to
it. The EHR owns that name, and the handoff is where it arrives.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator

#: An input bound for request hygiene, not a clinical rule. It sits well under the
#: Gateway's own ceiling, and the Gateway remains the authority: if a deployment
#: tightens the limit further, its ``invalid_request`` is surfaced unchanged.
MAX_FINDINGS_CHARS = 12_000

#: Priors are bounded hard and in two places, because they travel in the same
#: message as the dictation: a draft is refused by the Gateway if the prompt stops
#: fitting, and a silently dropped prior is worse than a rejected submission —
#: the model would write a report that reads as though it had compared something.
MAX_PREVIOUS_REPORTS = 5
MAX_PREVIOUS_REPORT_CHARS = 2_000


class PreviousReport(BaseModel):
    """One earlier report the department is comparing this study against.

    ``reported_on`` stays a free-text label rather than a date type: departments
    write "11/2024", "Mar 2023 (outside PACS)" and "18 days ago", and an
    application that rejected the last of those would be discarded rather than
    used. The quality check needs the text to exist, not to be parseable.
    """

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    reported_on: str = Field(
        min_length=1,
        max_length=60,
        description="When it was reported, as the department writes it.",
        examples=["2024-06-11", "4 months ago"],
    )
    modality: str = Field(
        min_length=1,
        max_length=40,
        description="CT, MR, US… A prior of a different modality is still a prior, and "
        "the draft must say which one it is comparing.",
        examples=["MRI"],
    )
    study: str = Field(
        min_length=1,
        max_length=120,
        description="The exam as it was reported.",
        examples=["MRI BRAIN WITH CONTRAST"],
    )
    report: str = Field(
        min_length=1,
        max_length=MAX_PREVIOUS_REPORT_CHARS,
        description="The findings and impression of that report, as signed. Raw clinical "
        "text, never written to a log.",
    )


class StudySubmission(BaseModel):
    """The clinical work-up a draft is requested for."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    clinical_indication: str = Field(
        min_length=1,
        max_length=1_000,
        description="Why the study was done, in the referrer's words.",
        examples=["62-year-old with sudden right hemiparesis, onset 3 hours"],
    )
    modality: str = Field(
        min_length=1,
        max_length=40,
        description="Imaging modality: CT, MR, US, XR, and so on. Left open, because a "
        "closed list here would reject a real exam rather than protect one.",
        examples=["CT"],
    )
    study: str = Field(
        min_length=1,
        max_length=120,
        description="The exam performed, as the department names it.",
        examples=["CT HEAD WITHOUT CONTRAST"],
    )
    findings: str = Field(
        min_length=1,
        max_length=MAX_FINDINGS_CHARS,
        description="The observations the reporting clinician dictates: what was seen, "
        "measurements, attributes of the study. This is raw clinical text and the "
        "application never writes it to a log.",
    )
    technique: str | None = Field(
        default=None,
        max_length=2_000,
        description="Acquisition parameters when the department supplies them. When "
        "absent, the draft states that the technique was not provided rather than "
        "guessing a protocol.",
    )
    previous_reports: list[PreviousReport] = Field(
        default_factory=list,
        max_length=MAX_PREVIOUS_REPORTS,
        description="Earlier reports this study is being compared against, if the "
        "department supplied any. Empty is a real answer, and it is a different one "
        "from 'not looked': a draft may then say nothing about interval change.",
    )

    @field_validator("previous_reports")
    @classmethod
    def _priors_fit_the_message(cls, priors: list[PreviousReport]) -> list[PreviousReport]:
        """Refuse an oversized prior block rather than trim it silently."""
        total = sum(len(p.report) for p in priors)
        if total > 6_000:
            raise ValueError(
                f"{total} characters of previous reports will not fit a draft request; "
                f"submit the {MAX_PREVIOUS_REPORTS} most relevant reports, within "
                f"{MAX_PREVIOUS_REPORT_CHARS} characters each."
            )
        return priors

    @property
    def has_technique(self) -> bool:
        return bool(self.technique)

    @property
    def has_priors(self) -> bool:
        return bool(self.previous_reports)

    @property
    def grounding_text(self) -> str:
        """Everything this submission put in front of the model, as one string.

        The quality checks measure the draft against this and nothing else: a
        measurement, a comparison or a history that is not here was not supplied,
        whatever the model believed.
        """
        parts = [
            self.clinical_indication,
            self.modality,
            self.study,
            self.findings,
            self.technique or "",
            *(f"{p.reported_on} {p.modality} {p.study} {p.report}" for p in self.previous_reports),
        ]
        return "\n".join(parts).lower()


__all__ = [
    "MAX_FINDINGS_CHARS",
    "MAX_PREVIOUS_REPORTS",
    "MAX_PREVIOUS_REPORT_CHARS",
    "PreviousReport",
    "StudySubmission",
]
