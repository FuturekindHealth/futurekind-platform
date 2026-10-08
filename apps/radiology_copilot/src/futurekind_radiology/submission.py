"""What a clinician submits: the three things the workflow starts with.

Indication, modality and findings are the input the clinical workflow names. The
study label is carried alongside them because a report without an exam name is
not a document anyone can file.

There is deliberately **no patient identifier field**. ``docs/DOMAIN_MODEL.md``
Q2 forbids inventing an identifier format here, and an MRN invented by an
application is exactly the defect that outlives every convenience attached to
it. The EHR owns that name, and the handoff is where it arrives.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

#: An input bound for request hygiene, not a clinical rule. It sits well under the
#: Gateway's own ceiling, and the Gateway remains the authority: if a deployment
#: tightens the limit further, its ``invalid_request`` is surfaced unchanged.
MAX_FINDINGS_CHARS = 12_000


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

    @property
    def has_technique(self) -> bool:
        return bool(self.technique)


__all__ = ["MAX_FINDINGS_CHARS", "StudySubmission"]
