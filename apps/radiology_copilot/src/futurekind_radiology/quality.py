"""Quality checks on a draft, against the text that produced it.

Why this module exists: the dangerous failure in this workflow is not a malformed
answer, it is a *plausible* one. A draft that reads like a radiology report and
contains a measurement nobody dictated, or compares this study against a prior
report nobody supplied, passes every structural test and can reach a patient. The
product documents call those F10 and R-7 and say plainly that the screen cannot
see them (`docs/product/RADIOLOGY_WORKFLOW.md` §3, §4). So the application checks
what it can check mechanically, and names what it cannot.

Nine checks, with one property that makes them usable in a clinical path: each is
a **deterministic function of the submitted text**. No model grades the model, no
similarity threshold, no learned score. The same dictation and the same draft
always produce the same findings, which is the only kind of rule a department can
audit afterwards.

What they are not: a read of the images. Every check here compares words to words.
A draft can be perfectly grounded in its inputs and still be wrong about the
study, and nothing in this file can tell a reviewer that. That limitation is
carried inside the document, in `quality.scope` and `confidence.basis`, rather
than left in a README the signer will not re-read at 4pm.

Two severities. `block` means the draft asserts something the submitted text does
not support, and signing is refused until the words are corrected — the correction
is always a text edit, so a radiologist is never locked out of their own document.
`advisory` means worth a look, with the triggering words shown.
"""

from __future__ import annotations

import re
from typing import Literal

from .report import (
    SECTION_KEYS,
    ConfidenceAssessment,
    QualityFinding,
    QualityReport,
)
from .submission import StudySubmission

#: Where a claim about the patient lives. A number in the plan sections is an
#: intention ("review in 6 months"); a number in the descriptive sections is an
#: assertion about this study, and only the second kind can be checked against
#: what was dictated.
_ASSERTIVE_SECTIONS = ("findings", "impression")
_PLAN_SECTIONS = ("recommendations", "follow_up")

#: A measurement is a number carrying a unit. Deliberately narrow: bare digits
#: would flag "T2", "the 3rd ventricle" and "L4/L5" as fabrications, and a check
#: that cries wolf about anatomy is switched off within a week. The separator is a
#: space only, so "45-year-old" is not read as a claim about a lesion.
_MEASUREMENT = re.compile(
    r"\b(\d+(?:[.,]\d+)?)\s(mm|cm|ml|cc|hu|%|hours?|days?|weeks?|months?|years?)\b|"
    r"\b(\d+(?:[.,]\d+)?)(mm|cm|ml|cc|hu|%)\b",
    re.IGNORECASE,
)

#: A count of clinical findings is the same kind of assertion. "Two lesions" where
#: three were dictated is exactly the error the golden set weights most heavily.
_COUNT = re.compile(
    r"\b(\d{1,3})\s?(lesions?|foci|deposits?|metastases?|infarcts?|areas?|sites?)\b",
    re.IGNORECASE,
)

#: Phrases that only mean something because an earlier study exists — each one
#: asserts a comparison, not a description. Bare "interval" is deliberately absent:
#: "review at interval" is a plan, and a check that blocks plans produces a tool
#: the department routes around. Using one of these with no prior supplied invents
#: the patient's history.
_COMPARISON = (
    "unchanged",
    "no interval change",
    "interval progression",
    "stable since",
    "compared with",
    "compared to",
    "in comparison",
    "previously",
    "as before",
    "resolved",
    "worse than",
    "better than",
    "increased from",
    "decreased from",
    "prior study",
    "previous study",
    "earlier study",
    "earlier scan",
)

#: Certainty a hedged dictation cannot support. The golden set's `must_not_say`
#: column is largely this failure: a possible thing written as a settled one.
_ABSOLUTE = (
    "confirmed",
    "confirms",
    "definitive",
    "diagnostic of",
    "no doubt",
    "excluded",
    "excludes",
    "rules out",
    "ruled out",
    "undoubted",
    "certainly",
)

#: The hedges that make the above a change of meaning rather than a summary.
_HEDGED = (
    "not certain",
    "cannot be excluded",
    "possible",
    "possibly",
    "probable",
    "likely",
    "may",
    "might",
    "equivocal",
    "subtle",
    "suspicious",
    "uncertain",
    "suggests",
    "questionable",
    "indeterminate",
)

#: Markdown, bullets and preamble are a clinical failure, not a cosmetic one:
#: section-by-section review is the control standing between a draft and a
#: signature, and a section full of markup cannot be reviewed that way. A bullet is
#: only a bullet at the start of a line — "the left-sided lesion" must not read as
#: one, or every report in the department becomes a formatting violation.
_FORMAT_MARKERS = ("```", "**", "##", "<b>", "<br", "&nbsp;")
_BULLET = re.compile(r"^\s*[-*•]\s+\S", re.MULTILINE)

_PERSON_OR_ID = re.compile(
    r"\b(?:mr|mrs|ms|miss|dr)\.?\s+[A-Z][a-z]{2,}|\b\d{6,}\b|"
    r"\b(?:uhid|mrn|accession)\b",
    re.IGNORECASE,
)

#: An observation unit shorter than this is a fragment, not a clinical statement,
#: and testing it for presence produces noise.
_MIN_UNIT_CHARS = 8

#: Comparison is on the first five characters, so "hippocampus", "hippocampal" and
#: "hippocampi" count as one observation and a plural is not a missing finding.
_STEM_CHARS = 5

#: Words that appear in almost every dictation and prove nothing about coverage.
_STOPWORDS = frozenset(
    {
        "with",
        "without",
        "normal",
        "abnormal",
        "other",
        "small",
        "large",
        "mild",
        "marked",
        "moderate",
        "severe",
        "acute",
        "chronic",
        "right",
        "left",
        "both",
        "unilateral",
        "bilateral",
        "further",
        "above",
        "below",
        "within",
        "there",
        "where",
        "which",
        "these",
        "those",
        "this",
        "that",
        "were",
        "have",
        "also",
        "seen",
        "study",
        "studies",
        "images",
        "scan",
        "scans",
        "sequences",
        "sequence",
        "signal",
        "intensity",
        "appearance",
        "appears",
        "evidence",
        "significant",
        "no abnormal",
    }
)

#: In the order :func:`evaluate` runs them, because `checks_run` in the document is
#: that order and a reader comparing the two should not have to know which is which.
_CHECK_NAMES = (
    "dropped_observation",
    "unsupported_measurement",
    "invented_history",
    "unsupported_certainty",
    "format_breach",
    "invented_identifier",
    "self_reported_confidence",
    "unsupported_absence",
    "structure_coverage",
)

_SCOPE = (
    "Nine deterministic checks comparing this draft with the submitted indication, "
    "technique, dictation and previous reports. They can show that a statement is "
    "unsupported by the text supplied; they cannot show that a statement is true, and "
    "none of them has seen the images."
)


def _numbers_in(text: str) -> list[tuple[str, str]]:
    """Numeric claims as (value, kind), normalised so "6,0" and "6.0" are one value."""
    found = [
        ((match.group(1) or match.group(3)).replace(",", "."), "measurement")
        for match in _MEASUREMENT.finditer(text)
    ]
    found += [(match.group(1), "count") for match in _COUNT.finditer(text)]
    return found


def _grounded_values(grounding: str) -> set[str]:
    """Every number the submitted text states, as whole numeric tokens.

    Tokenised rather than substring-matched on purpose. ``"9" in "19 mm"`` is true, so
    a substring test let a drafted *9 mm* pass against a dictated *19 mm* — the near
    miss, right digit and wrong number, which is the error the golden set's
    `must_not_say` column weights most heavily. A check that waves that through is
    worse than no check, because it is trusted.

    A digit glued to a letter is excluded: in ``t2``, ``flair`` and ``l4`` it names a
    sequence or a vertebra, not an amount, and letting *2 mm* be grounded by "T2" would
    empty the check for every single-digit size. The residue this leaves is that ages
    and dates *are* bare numbers, so a submitted "45-year-old" grounds a drafted 45 mm
    and a prior reported "2026-06-02" grounds *02 mm*. That is stated in
    `tests/test_quality.py` rather than fixed by a rule that would then refuse the
    clinician who dictated "4.5 across" and was drafted as "4.5 cm".
    """
    return {
        match.group(1).replace(",", ".")
        for match in re.finditer(r"(?<![a-z])(\d+(?:[.,]\d+)?)", grounding)
    }


def _section_pairs(sections: dict[str, str], keys: tuple[str, ...]) -> list[tuple[str, str]]:
    return [(key, sections[key]) for key in keys if sections.get(key)]


def _check_measurements(
    sections: dict[str, str], submission: StudySubmission
) -> list[QualityFinding]:
    """Every number that describes this study must trace back to the submitted text."""
    grounding = _grounded_values(submission.grounding_text)
    findings: list[QualityFinding] = []

    for section, text in _section_pairs(sections, _ASSERTIVE_SECTIONS):
        for value, kind in _numbers_in(text):
            if value in grounding:
                continue
            findings.append(
                QualityFinding(
                    check="unsupported_measurement",
                    severity="block",
                    section=section,
                    message=(
                        f"A {kind} of {value} appears in the draft and nowhere in what was "
                        "submitted. Measurements and counts belong to the reporting "
                        "clinician: correct the number or supply the dictation it came from."
                    ),
                    evidence=value,
                )
            )

    for section, text in _section_pairs(sections, _PLAN_SECTIONS):
        for value, kind in _numbers_in(text):
            if value in grounding:
                continue
            findings.append(
                QualityFinding(
                    check="unsupported_measurement",
                    severity="advisory",
                    section=section,
                    message=(
                        f"A {kind} of {value} in {section} is not in the submitted text. "
                        "A plan may legitimately contain a number nobody dictated — an "
                        "interval, a dose — so this is shown, not blocked."
                    ),
                    evidence=value,
                )
            )
    return findings


def _comparison_phrases(sections: dict[str, str]) -> list[str]:
    combined = " ".join(text.lower() for _, text in _section_pairs(sections, SECTION_KEYS))
    return [phrase for phrase in _COMPARISON if phrase in combined]


def _check_history(
    sections: dict[str, str], submission: StudySubmission
) -> list[QualityFinding]:
    """Comparison language is a claim about an earlier report."""
    used = _comparison_phrases(sections)
    if not used or submission.has_priors:
        return []
    grounding = submission.grounding_text
    if any(phrase in grounding for phrase in used):
        return []
    return [
        QualityFinding(
            check="invented_history",
            severity="block",
            message=(
                f"The draft says “{used[0]}” but no previous report was supplied, so the "
                "comparison has nothing behind it. Either submit the earlier report or "
                "remove the comparison."
            ),
            evidence=used[0],
        )
    ]


def _observation_units(text: str) -> list[str]:
    units = re.split(r"[.;\n]", text)
    return [unit.strip() for unit in units if len(unit.strip()) >= _MIN_UNIT_CHARS]


def _check_coverage(
    sections: dict[str, str], submission: StudySubmission
) -> list[QualityFinding]:
    """Nothing the clinician dictated may disappear from the draft."""
    draft = " ".join(
        text.lower() for _, text in _section_pairs(sections, ("findings", "impression"))
    )
    missing: list[str] = []
    for unit in _observation_units(submission.findings):
        tokens = [
            token
            for token in re.findall(r"[a-z]{5,}", unit.lower())
            if token not in _STOPWORDS
        ]
        if tokens and not any(token[:_STEM_CHARS] in draft for token in tokens):
            missing.append(unit)
    if not missing:
        return []
    return [
        QualityFinding(
            check="dropped_observation",
            severity="block",
            section="findings",
            message=(
                f"{len(missing)} dictated observation(s) do not appear in the draft. Dropping "
                "an observation is as dangerous as inventing one, and a summary that reads well "
                "is how it happens."
            ),
            evidence=missing[0][:180],
        )
    ]


#: A certainty word inside a negation is not a claim of certainty. "A focal lesion
#: cannot be excluded" is the hedged statement the dictation asked for, and a check
#: that matched the word "excluded" in it would block the only correct sentence in
#: the report — which is exactly how a quality check earns a reputation for noise.
_NEGATED = re.compile(
    r"\b(?:not|cannot|can\s?not|no|without|difficult\s+to|hard\s+to|fails\s+to)\s+"
    r"(?:to\s+)?(?:be\s+)?([a-z]+)",
    re.IGNORECASE,
)


def _absolute_claims(impression: str) -> list[str]:
    """Certainty words in the impression that are not sitting inside a negation."""
    negated = {match.group(1).lower() for match in _NEGATED.finditer(impression)}
    hits: list[str] = []
    for word in _ABSOLUTE:
        if word not in impression:
            continue
        if word.split()[0] in negated:
            continue
        hits.append(word)
    return hits


def _check_certainty(
    sections: dict[str, str], submission: StudySubmission
) -> list[QualityFinding]:
    """A hedged dictation may not become a settled impression."""
    impression = (sections.get("impression") or "").lower()
    absolutes = _absolute_claims(impression)
    if not absolutes:
        return []
    grounding = submission.grounding_text
    if any(word in grounding for word in _ABSOLUTE):
        return []
    hedged = [word for word in _HEDGED if word in grounding]
    if not hedged:
        return []
    return [
        QualityFinding(
            check="unsupported_certainty",
            severity="block",
            section="impression",
            message=(
                f"The impression states “{absolutes[0]}” while the submitted text hedges "
                f"({hedged[0]!r}). A differential and a confirmation are different clinical "
                "documents."
            ),
            evidence=absolutes[0],
        )
    ]


def _check_format(sections: dict[str, str]) -> list[QualityFinding]:
    out: list[QualityFinding] = []
    for section, text in _section_pairs(sections, SECTION_KEYS):
        marker = next((m for m in _FORMAT_MARKERS if m in text), None)
        if marker is None and _BULLET.search(text):
            marker = "- (list item)"
        if marker:
            out.append(
                QualityFinding(
                    check="format_breach",
                    severity="block",
                    section=section,
                    message=(
                        "This section is not plain clinical prose, so it cannot be reviewed "
                        "section by section or printed as a report."
                    ),
                    evidence=marker.strip(),
                )
            )
    return out


def _check_identifiers(
    sections: dict[str, str], submission: StudySubmission
) -> list[QualityFinding]:
    """An invented name, number or identifier is a privacy breach inside a report."""
    grounding = submission.grounding_text
    for section, text in _section_pairs(sections, SECTION_KEYS):
        match = _PERSON_OR_ID.search(text)
        if not match:
            continue
        token = match.group(0)
        if token.lower() in grounding:
            continue
        return [
            QualityFinding(
                check="invented_identifier",
                severity="block",
                section=section,
                message=(
                    "The draft carries something that reads like an identity and was not "
                    "submitted. Reports are identified by the EHR, never by a name the model "
                    "invented."
                ),
                evidence=token[:60],
            )
        ]
    return []


def _check_self_reported(extra_sections: tuple[str, ...]) -> list[QualityFinding]:
    named = tuple(key for key in extra_sections if key.lower() in {"confidence", "certainty"})
    if not named:
        return []
    return [
        QualityFinding(
            check="self_reported_confidence",
            severity="advisory",
            message=(
                f"The model also returned {', '.join(named)}. A model's own confidence is not "
                "shown to the reviewer — the `confidence` block in this document is computed "
                "from the submitted text instead."
            ),
        )
    ]


def _check_absences(
    sections: dict[str, str],
    submission: StudySubmission,
    out_of_scope: tuple[tuple[str, str], ...],
) -> list[QualityFinding]:
    """A negative this exam was never asked to answer.

    Each rule is a pair: the claim as it appears in prose, and the subject that has
    to have been raised for the claim to belong in this report. A referrer who asks
    about pulmonary embolism gets an answer about it, and the answer is not an
    invention — so the subject is searched in the submitted text, not the sentence.
    """
    combined = " ".join(text.lower() for _, text in _section_pairs(sections, SECTION_KEYS))
    grounding = submission.grounding_text
    hits = [
        claim
        for claim, subject in out_of_scope
        if claim in combined and subject not in grounding
    ]
    if not hits:
        return []
    return [
        QualityFinding(
            check="unsupported_absence",
            severity="advisory",
            message=(
                f"The draft states “{hits[0]}”, which this exam is not designed to answer. A "
                "negative the study cannot support reads like reassurance."
            ),
        )
    ]


def _check_structure_coverage(
    sections: dict[str, str],
    submission: StudySubmission,
    checklist: tuple[tuple[str, tuple[str, ...]], ...],
) -> list[QualityFinding]:
    """What the protocol covers that neither the dictation nor the draft mentions.

    Advisory by design. An unmentioned structure may be normal and unremarkable, and
    this application does not own the department's reporting template — it can point
    at a gap, not call it an error.
    """
    draft = (sections.get("findings") or "").lower()
    dictated = submission.findings.lower()
    absent = [
        label
        for label, terms in checklist
        if not any(term in draft or term in dictated for term in terms)
    ]
    if not absent:
        return []
    return [
        QualityFinding(
            check="structure_coverage",
            severity="advisory",
            message=(
                f"{len(absent)} structure(s) this protocol normally reports appear in neither "
                f"the dictation nor the draft: {', '.join(absent)}. Advisory — a negative that "
                "was not dictated is still a negative the radiologist may state."
            ),
        )
    ]


def evaluate(
    sections: dict[str, str],
    submission: StudySubmission,
    *,
    checked_at: str,
    extra_sections: tuple[str, ...] = (),
    structure_checklist: tuple[tuple[str, tuple[str, ...]], ...] = (),
    out_of_scope_claims: tuple[tuple[str, str], ...] = (),
) -> QualityReport:
    """Run every check over one draft. Pure, ordered and total.

    `sections` is the document's own section mapping, so a reviewer's edit re-runs
    the same checks over the words that will actually be signed. The alternative is
    a quality verdict describing a version of the report nobody approved.
    """
    findings: list[QualityFinding] = []
    findings += _check_coverage(sections, submission)
    findings += _check_measurements(sections, submission)
    findings += _check_history(sections, submission)
    findings += _check_certainty(sections, submission)
    findings += _check_format(sections)
    findings += _check_identifiers(sections, submission)
    findings += _check_self_reported(extra_sections)
    findings += _check_absences(sections, submission, out_of_scope_claims)
    findings += _check_structure_coverage(sections, submission, structure_checklist)

    status: Literal["clear", "advisory", "blocking"] = (
        "blocking"
        if any(finding.severity == "block" for finding in findings)
        else ("advisory" if findings else "clear")
    )
    return QualityReport(
        status=status,
        findings=findings,
        checks_run=list(_CHECK_NAMES),
        checked_at=checked_at,
        scope=_SCOPE,
    )


_LABELS = {
    "supported": "Grounded in what was submitted",
    "review-carefully": "Read it against the dictation before signing",
    "not-safe-to-sign": "Resolve the flagged statements first",
}


def assess_confidence(
    quality: QualityReport,
    submission: StudySubmission,
    *,
    attempts: int = 1,
    finish_reason: str | None = None,
    degraded: bool = False,
) -> ConfidenceAssessment:
    """One word a reviewer can act on, plus the reasons behind it."""
    reasons: list[str] = []

    if quality.status == "blocking":
        level = "not-safe-to-sign"
        reasons.append(
            f"{len(quality.blocking)} blocking check(s): the draft asserts something the "
            "submitted text does not support."
        )
    elif quality.status == "advisory":
        level = "review-carefully"
        reasons.append(
            f"{len(quality.advisory)} advisory check(s) raised, each shown with the words "
            "that triggered it."
        )
    else:
        level = "supported"
        reasons.append("Every checkable claim in the draft traces back to the submitted text.")

    if degraded:
        reasons.append("A substituted model answered, which the skill policy forbids.")
    if attempts > 1:
        reasons.append(f"The answer took {attempts} attempts.")
    if finish_reason not in (None, "stop"):
        reasons.append(f"Generation ended with finish reason {finish_reason!r}, not a clean stop.")
    if not submission.has_technique:
        reasons.append(
            "No acquisition parameters were supplied, so the technique line is unchecked."
        )
    if not submission.has_priors:
        reasons.append(
            "No previous report was supplied, so nothing in this draft is a comparison."
        )

    return ConfidenceAssessment(
        level=level,
        label=_LABELS[level],
        reasons=reasons,
        basis=(
            "Computed by this application from the submitted text, the Gateway's reported "
            "provenance and the quality checks. Not the model's own estimate, and not a "
            "probability that the diagnosis is correct: no check here reads the images."
        ),
    )


__all__ = ["assess_confidence", "evaluate"]
