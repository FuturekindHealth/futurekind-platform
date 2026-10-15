"""A case record worth trusting: what ground truth has to contain before it is truth.

The repository already carries 100 reference reports and every one is
`ratified: pending`, `authored_by: engineering`. That is not a flaw in the dataset; it is
the dataset telling the truth about itself. The consequence is that no number computed
against it can be evidence about care — only about the instrument
(`docs/safety/CLINICAL_SAFETY.md` §5).

This module makes that state *machine-visible* rather than a header comment, so a case
cannot be used as ground truth without saying who made it, who signed it, and what it is
good for deciding. It is Part 2 of the evidence system, and its rule is the rule the brief
gave: **design the framework, do not invent data.** A record that fails validation is
refused, not scored at zero.

Fields, and why each is mandatory:

| Field | Without it |
| --- | --- |
| `provenance` | A synthetic case becomes a real one by forgetting which it is |
| `ratified_by` | Engineering grades its own homework; segregation of duties is `GOVERNANCE.md` G2 |
| `specialty`, `modality` | Cross-department numbers get averaged into one meaningless column |
| `difficulty`, `risk` | A pass rate over easy cases is a marketing number |
| `teaching_value` | The trainee use-case cannot be studied if it is not recorded |
| `error_labels` | Corrections are unlocatable; see `evidence.taxonomy` |
| `expected_*` sections | Nothing to compare a draft against, so every quality claim is untethered |
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

PROVENANCE = ("real_signed_report", "synthetic_engineered", "derived_from_real_deidentified")
RISK = ("low", "moderate", "high", "critical")
CATEGORIES = ("normal", "common", "rare", "emergency", "medicolegal")
RATIFICATION = ("pending", "ratified", "rejected")
#: Who may ratify a case. `engineering` is deliberately absent: the author of an
#: evaluation case cannot be the authority that makes it true.
RATIFYING_ROLES = ("consultant", "clinical_authority", "department_board")


class RecordError(ValueError):
    """A case record that cannot be trusted. Raised, never defaulted."""


@dataclass
class GroundTruthCase:
    case_id: str
    specialty: str
    modality: str
    study: str
    category: str
    difficulty: int
    risk: str
    provenance: str
    indication: str
    dictation: str
    expected_sections: dict[str, str]
    must_not_say: tuple[str, ...] = ()
    teaching_value: str = ""
    error_labels: tuple[str, ...] = ()
    ratified: str = "pending"
    ratified_by: str = ""
    ratified_role: str = ""
    ratified_on: str = ""
    author: str = ""
    site: str = ""
    #: A case is comparable only to cases with the same shape. This is the field that makes
    #: a multi-centre claim honest: it names what the centre contributed, never a patient.
    source: str = field(default="")

    def validate(self) -> list[str]:
        problems: list[str] = []
        if not self.case_id or not self.case_id.strip():
            problems.append("case_id is required: an anonymous case cannot be re-examined")
        if self.provenance not in PROVENANCE:
            problems.append(f"provenance must be one of {PROVENANCE}; got {self.provenance!r}")
        if self.category not in CATEGORIES:
            problems.append(f"category must be one of {CATEGORIES}; got {self.category!r}")
        if self.risk not in RISK:
            problems.append(f"risk must be one of {RISK}; got {self.risk!r}")
        if not 1 <= self.difficulty <= 5:
            problems.append("difficulty is a 1–5 scale; anything else is a free-text opinion")
        if not self.expected_sections:
            problems.append("a case with no expected answer is a prompt, not ground truth")
        if not self.dictation.strip():
            problems.append("no dictation: there is nothing for a fidelity check to be about")
        for code in self.error_labels:
            if not code.startswith("E"):
                problems.append(f"error label {code!r} is not an evidence.taxonomy code")
        if self.ratified not in RATIFICATION:
            problems.append(f"ratified must be one of {RATIFICATION}")
        if self.ratified == "ratified":
            if self.ratified_role not in RATIFYING_ROLES:
                problems.append(
                    "a ratified case needs a clinical role: author and ratifier must differ "
                    "(GOVERNANCE.md G2)"
                )
            if not self.ratified_by or not self.ratified_on:
                problems.append("ratified needs a named person and a date, or it is an assertion")
            if self.author and self.ratified_by == self.author:
                problems.append("the case's author cannot ratify it")
        return problems

    def is_ground_truth(self) -> bool:
        """True only when the record may be used as evidence about care."""
        return not self.validate() and self.ratified == "ratified"

    def as_dict(self) -> dict:
        return {
            "case_id": self.case_id,
            "specialty": self.specialty,
            "modality": self.modality,
            "study": self.study,
            "category": self.category,
            "difficulty": self.difficulty,
            "risk": self.risk,
            "provenance": self.provenance,
            "indication": self.indication,
            "dictation": self.dictation,
            "expected_sections": dict(self.expected_sections),
            "must_not_say": list(self.must_not_say),
            "teaching_value": self.teaching_value,
            "error_labels": list(self.error_labels),
            "ratified": self.ratified,
            "ratified_by": self.ratified_by,
            "ratified_role": self.ratified_role,
            "ratified_on": self.ratified_on,
            "author": self.author,
            "site": self.site,
            "source": self.source,
        }


def require_valid(case: GroundTruthCase) -> GroundTruthCase:
    problems = case.validate()
    if problems:
        raise RecordError(f"{case.case_id}: " + "; ".join(problems))
    return case


def from_golden(row: dict) -> GroundTruthCase:
    """Read a `GOLDEN_DATASET.yaml` case into the schema, honestly.

    The dataset has no `specialty`, no `risk` and no `provenance` key, and it is
    unratified on every case, so every record built here comes out *not* ground truth. That
    is the function working: it converts a header comment into a field that a report cannot
    accidentally ignore.
    """
    expected = {
        "findings": row.get("expected_findings", "") or "",
        "impression": row.get("expected_impression", "") or "",
        "recommendations": row.get("expected_recommendation", "") or "",
    }
    return GroundTruthCase(
        case_id=row.get("id", ""),
        specialty="radiology",
        modality=row.get("modality", ""),
        study=row.get("study", ""),
        category=row.get("category", ""),
        difficulty=int(row.get("difficulty", 3)),
        risk="high" if row.get("category") in ("emergency", "medicolegal") else "moderate",
        provenance="synthetic_engineered",
        indication=row.get("indication", ""),
        dictation=row.get("dictated", "") or "",
        expected_sections=expected,
        must_not_say=tuple(row.get("must_not_say", ()) or ()),
        teaching_value=row.get("teaching_points", "") or "",
        ratified="ratified" if row.get("ratified") == "yes" else "pending",
        author=row.get("author", "engineering"),
        source="docs/product/GOLDEN_DATASET.yaml",
    )


def corpus_summary(cases: list[GroundTruthCase]) -> dict:
    """How much ground truth the project actually has. Usually the answer is zero, on purpose."""
    total = len(cases)
    ratified = sum(1 for c in cases if c.is_ground_truth())
    invalid = sum(1 for c in cases if c.validate())
    return {
        "cases": total,
        "ratified_and_valid": ratified,
        "usable_as_evidence_about_care": round(ratified / total, 4) if total else None,
        "with_validation_problems": invalid,
        "by_provenance": {key: sum(1 for c in cases if c.provenance == key) for key in PROVENANCE},
        "note": (
            "a case counted here as unratified can still measure an instrument; it cannot "
            "measure care (docs/safety/CLINICAL_SAFETY.md §5)"
        ),
        "as_at": date.today().isoformat(),
    }
