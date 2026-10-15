"""Study profiles: what one exam is expected to describe, and what it cannot answer.

A profile is not a prompt and not a template. It is the two things a quality check
can only get from a human who has decided them: which structures this protocol is
supposed to cover, and which clinical questions this study is not able to answer.
Both come from `docs/product/RADIOLOGY_WORKFLOW.md` §2 (MRI: long, multi-parameter,
protocol-dependent; likely failure "wrong protocol named, or an incidental finding
dropped") and from the eight MRI brain cases in `docs/product/GOLDEN_DATASET.yaml`,
whose dictated text is the evidence for the structure list below.

Alpha carries **one** profile, for the workflow this product actually runs: MRI
brain. Adding five more now would be a guess about five departments, and a guessed
checklist is how a quality check starts being ignored.

Nothing here supplies the technique line. A protocol description this application
invented would enter the report as though the department had stated it — the
technique is submitted by a human or the draft says it was not provided.
"""

from __future__ import annotations

from dataclasses import dataclass

#: One structure a report is expected to account for, with the words that count as
#: mentioning it. Synonyms and stems, because "the hippocampi are normal" and
#: "right hippocampal sclerosis" are both a mention and "hippocampus" is neither.
StructureTerm = tuple[str, tuple[str, ...]]

MRI_BRAIN_STRUCTURES: tuple[StructureTerm, ...] = (
    ("cerebral white matter", ("white matter",)),
    ("lateral ventricles and temporal horns", ("ventric",)),
    ("basal ganglia and thalami", ("basal ganglia", "thalam")),
    ("midline", ("midline", "shift")),
    ("cortex and sulci", ("sulc", "cort")),
    ("brainstem", ("brainstem", "brain stem")),
    ("cerebellum", ("cerebell",)),
    ("hippocampi and mesial temporal lobes", ("hippocamp", "mesial temporal")),
    ("diffusion", ("diffusion", "dwi", "restriction")),
    ("contrast enhancement", ("enhanc",)),
    ("pituitary and sella", ("pituitary", "sella")),
    ("orbits and optic pathways", ("optic", "orbit")),
    ("paranasal sinuses and mastoids", ("sinus", "mastoid")),
    ("skull vault and marrow", ("marrow", "skull")),
)

#: Claims a brain study has no business making, each as (the claim as written, the
#: subject that must have been raised for it to belong here). A referrer who asks
#: about pulmonary embolism gets an answer about it; a model that volunteers the
#: reassurance does not. "Fracture" is absent on purpose — a brain MRI does see the
#: skull, and a rule that fires on a legitimate sentence is a rule that gets ignored.
MRI_BRAIN_OUT_OF_SCOPE: tuple[tuple[str, str], ...] = (
    ("no pulmonary embolism", "pulmonary embolism"),
    ("pulmonary embolism excluded", "pulmonary embolism"),
    ("no aortic dissection", "aortic dissection"),
    ("no myocardial infarction", "myocardial infarction"),
    ("no intra-abdominal", "intra-abdominal"),
    ("no renal pathology", "renal"),
    ("no retroperitoneal", "retroperitoneal"),
)

#: Studies this profile covers, matched on the label the department typed.
MRI_BRAIN_STUDY_TERMS = ("mri brain", "mr brain", "brain mri", "mr brain with contrast")


@dataclass(frozen=True)
class StudyProfile:
    """Named, matched, and limited to what a check can defend.

    `structures` and `out_of_scope_claims` feed advisory checks only. A profile can
    never block a report for not covering a structure, because the dictation is the
    clinician's and the absence of a sentence about the pituitary is usually a
    normal pituitary, not an omission.
    """

    name: str
    matches: tuple[str, ...]
    structures: tuple[StructureTerm, ...]
    out_of_scope_claims: tuple[tuple[str, str], ...]

    def applies_to(self, study: str) -> bool:
        label = study.lower()
        return any(term in label for term in self.matches)


MRI_BRAIN = StudyProfile(
    name="MRI brain",
    matches=MRI_BRAIN_STUDY_TERMS,
    structures=MRI_BRAIN_STRUCTURES,
    out_of_scope_claims=MRI_BRAIN_OUT_OF_SCOPE,
)

#: The profiles this build knows. Order matters only in that the first match wins.
PROFILES: tuple[StudyProfile, ...] = (MRI_BRAIN,)


def profile_for(study: str) -> StudyProfile | None:
    """The profile for one submitted study label, or None.

    None is the honest answer for a study no clinician has described to this
    project yet, and it is not an error: an MRI knee drafts and signs with the same
    nine checks and no structure list.
    """
    return next((profile for profile in PROFILES if profile.applies_to(study)), None)


__all__ = [
    "MRI_BRAIN",
    "MRI_BRAIN_OUT_OF_SCOPE",
    "MRI_BRAIN_STRUCTURES",
    "PROFILES",
    "StudyProfile",
    "profile_for",
]
