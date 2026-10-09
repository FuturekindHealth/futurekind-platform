"""What a human changed, and whether it was substance or style.

The platform's central claim is that it saves a clinician's time without taking their
judgement. That claim lives or dies here, because the only honest reading of a draft a
human rewrote is *how much of the work was the human's, and which part.*

Three design decisions, each of which changes a number:

**1. Text does not leave the function unless the caller asks for it.** Every summary here
carries lengths, counts and offsets — never the words. `include_text` exists for a
reviewer looking at one case on their own machine, and a test asserts the default output
contains no substring of the input (`docs/CONSTITUTION.md` P10; prompt and completion text
never enter a log or an export).

**2. "Substantive" is a rule, not a feeling.** A change is substantive when it alters a
number or unit, a side or position, a negation, or an assertion-strength word — the four
token classes that can change what a clinician does next. Anything else is style. The token
lists are data, so the rule can be argued about in a pull request instead of in a meeting.
The rule is deliberately conservative: it will call some clinically important rewordings
style, and that is stated as a limitation rather than hidden inside a percentage.

**3. Typing reduction has three definitions and they disagree.** Reporting the flattering
one would be the vanity-metric failure `docs/FAILURE-MODES.md` FM10 describes, so all three
are computed and named: what the human typed relative to the draft, relative to writing the
report from nothing, and the *ceiling* the corpus allows. Reading a draft costs time that
none of the three measures, and the report says so.

Levenshtein and difflib ratios are both returned because they answer different questions:
edit distance counts operations, `SequenceMatcher` counts shared structure, and a reviewer
who replaced one long sentence produces very different numbers in each. Neither is the truth;
both are cheaper than an opinion.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher

#: Token classes that make an edit substantive. Lower-cased comparison; word-boundary
#: matching only, so "left" inside "lateral" does not fire (the defect that made the
#: product's own `invented_identifier` narrow, `docs/product/PROMPT_LIBRARY.md`).
SIDES = frozenset(
    {
        "left",
        "right",
        "bilateral",
        "unilateral",
        "upper",
        "lower",
        "superior",
        "inferior",
        "proximal",
        "distal",
        "medial",
        "lateral",
        "anterior",
        "posterior",
        "ipsilateral",
        "contralateral",
        "right-sided",
        "left-sided",
    }
)
NEGATIONS = frozenset(
    {
        "no",
        "not",
        "without",
        "negative",
        "absent",
        "none",
        "normal",
        "unremarkable",
        "intact",
        "clear",
        "excluded",
        "resolved",
        "maintained",
        "preserved",
    }
)
ASSERTIONS = frozenset(
    {
        "consistent",
        "consistently",
        "suggest",
        "suggestive",
        "probable",
        "likely",
        "possible",
        "cannot",
        "definite",
        "definitely",
        "certain",
        "certainly",
        "confirmed",
        "excludes",
        "exclude",
        "indeterminate",
        "equivocal",
        "suspect",
        "suspicious",
        "consider",
        "recommended",
        "recommendation",
    }
)

#: Words that carry no clinical content, so extending a negation past one of them is style.
#: Deliberately tiny and deliberately incomplete: it is a bias, stated, not a claim to
#: understand radiology English.
NEGATION_SCOPE_STOP = frozenset(
    {
        "with",
        "within",
        "without",
        "and",
        "the",
        "also",
        "seen",
        "noted",
        "normal",
        "mildly",
        "moderately",
        "further",
        "additional",
        "associated",
    }
)

#: A number or a unit is the most consequential token class in a radiology report, so it is
#: matched by pattern rather than by list: nothing finite could hold every unit.
MEASUREMENT = re.compile(
    r"(?<![\w.])(\d+(?:\.\d+)?)\s?"
    r"(mm|cm|mms?|ums?|nm|ml|l|hu|gb|tb|mmhg|kg|months?|years?|weeks?|days?|hours?|minutes?)?"
    r"(?![\w])",
    re.IGNORECASE,
)
_WORD = re.compile(r"[A-Za-z][A-Za-z'-]*")


@dataclass
class SectionEdit:
    """One section, before and after a human had done with it."""

    section: str
    unchanged: bool
    similarity: float
    edit_distance: int
    normalised_distance: float
    chars_before: int
    chars_after: int
    chars_inserted: int
    chars_removed: int
    substantive: bool
    reasons: tuple[str, ...] = ()
    blocks: int = 0
    #: Filled only when the caller passed `include_text`. Never in an aggregate.
    detail: list[dict] = field(default_factory=list)


@dataclass
class EditReport:
    sections: list[SectionEdit]
    overall_similarity: float
    overall_normalised_distance: float
    total_edit_distance: int
    sections_edited: int
    substantive_sections: int
    insertion_sections: int
    deletion_sections: int
    chars_inserted: int
    chars_removed: int
    blocks: int
    words_added: int
    words_removed: int

    def as_dict(self) -> dict:
        """A summary that is safe to aggregate, export and quote."""
        return {
            "overall_similarity": self.overall_similarity,
            "overall_normalised_distance": self.overall_normalised_distance,
            "total_edit_distance": self.total_edit_distance,
            "sections_edited": self.sections_edited,
            "substantive_sections": self.substantive_sections,
            "insertion_sections": self.insertion_sections,
            "deletion_sections": self.deletion_sections,
            "chars_inserted": self.chars_inserted,
            "chars_removed": self.chars_removed,
            "blocks": self.blocks,
            "words_added": self.words_added,
            "words_removed": self.words_removed,
            "per_section": [
                {
                    "section": s.section,
                    "unchanged": s.unchanged,
                    "similarity": s.similarity,
                    "normalised_distance": s.normalised_distance,
                    "substantive": s.substantive,
                    "reasons": list(s.reasons),
                    "chars_inserted": s.chars_inserted,
                    "chars_removed": s.chars_removed,
                    "blocks": s.blocks,
                }
                for s in self.sections
            ],
        }


def edit_distance(a: str, b: str) -> int:
    """Levenshtein distance by row, O(len(a)*len(b)) with two rows of memory.

    Report sections are hundreds of characters, not megabytes, so the quadratic bound is
    the right trade: no dependency, no surprise failure, and every value reproducible on a
    machine that has never seen this corpus.
    """
    if a == b:
        return 0
    if not a or not b:
        return len(a) or len(b)
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        current = [i]
        for j, cb in enumerate(b, start=1):
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (ca != cb)))
        previous = current
    return previous[-1]


def normalised_distance(a: str, b: str) -> float:
    """Distance scaled by the longer string: 0.0 identical, 1.0 nothing in common."""
    longest = max(len(a), len(b))
    return round(edit_distance(a, b) / longest, 4) if longest else 0.0


def similarity(a: str, b: str) -> float:
    """`SequenceMatcher` ratio: shared structure, which is what a reader perceives."""
    return round(SequenceMatcher(None, a, b).ratio(), 4)


def _tokens(text: str) -> set[str]:
    return {t.lower() for t in _WORD.findall(text)}


def is_substantive(before: str, after: str) -> tuple[bool, tuple[str, ...]]:
    """Would this change alter what a clinician does next?

    Compares the *sets* of consequential tokens the two versions carry, so re-typing a
    sentence around the same clinical content stays style.

    One rule is not token-set equality and needs naming: in radiology prose a negation
    scopes over everything that follows it, so adding two words to "No haemorrhage." can
    assert the absence of a second thing without changing the word "no". `NEGATION_SCOPE`
    therefore treats added content words in a negated section as substantive. It will still
    over-call on stylistic additions inside a negated sentence, and that is the cheaper
    direction of error: a measure that under-counts clinical change is the one that flatters
    the product.
    """
    if before.strip() == after.strip():
        return False, ()
    reasons: list[str] = []

    before_numbers = {m.group(0).lower() for m in MEASUREMENT.finditer(before)}
    after_numbers = {m.group(0).lower() for m in MEASUREMENT.finditer(after)}
    if before_numbers != after_numbers:
        reasons.append("measurement_changed")

    bt, at = _tokens(before), _tokens(after)
    for name, vocabulary in (("side", SIDES), ("negation", NEGATIONS), ("assertion", ASSERTIONS)):
        if (bt & vocabulary) != (at & vocabulary):
            reasons.append(f"{name}_changed")

    if bt & NEGATIONS:
        added_content = {
            word for word in (at - bt) if len(word) > 3 and word not in NEGATION_SCOPE_STOP
        }
        if added_content:
            reasons.append("negation_scope_extended")

    return bool(reasons), tuple(reasons)


def diff_blocks(before: str, after: str, include_text: bool = False) -> list[dict]:
    """The changed runs, in order — the shape a prompt author needs to see.

    Each block is (tag, length in the before, length in the after). `include_text` adds the
    words themselves and must never be used inside an aggregate: one flagged case is a
    reviewer's screen, not a dataset column.
    """
    out: list[dict] = []
    for tag, i1, i2, j1, j2 in SequenceMatcher(None, before, after).get_opcodes():
        if tag == "equal":
            continue
        entry = {"op": tag, "before_len": i2 - i1, "after_len": j2 - j1}
        if include_text:
            entry["before_text"] = before[i1:i2]
            entry["after_text"] = after[j1:j2]
        out.append(entry)
    return out


def compare_section(
    section: str, before: str, after: str, include_text: bool = False
) -> SectionEdit:
    before = before or ""
    after = after or ""
    unchanged = before.strip() == after.strip()
    substantive, reasons = is_substantive(before, after)
    blocks = diff_blocks(before, after, include_text=include_text)
    return SectionEdit(
        section=section,
        unchanged=unchanged,
        similarity=similarity(before, after),
        edit_distance=edit_distance(before, after),
        normalised_distance=normalised_distance(before, after),
        chars_before=len(before),
        chars_after=len(after),
        chars_inserted=max(0, len(after) - len(before)),
        chars_removed=max(0, len(before) - len(after)),
        substantive=substantive,
        reasons=reasons,
        blocks=len(blocks),
        detail=blocks if include_text else [],
    )


def compare_documents(
    before: dict[str, str], after: dict[str, str], sections: tuple[str, ...]
) -> EditReport:
    """All sections of one document, using the caller's section tuple.

    `sections` is a parameter rather than a constant on purpose. The instrument has been
    caught holding its own copy of the product's section contract
    (`docs/CONCEPTUAL_DEBT.md` S4/D6), which is how a measurement grades the wrong shape.
    A caller passes `report.SECTION_KEYS` or the case file's columns; this module never
    decides the list itself.
    """
    edits = [
        compare_section(key, before.get(key, ""), after.get(key, before.get(key, "")))
        for key in sections
    ]
    joined_before = " ".join(before.get(key, "") for key in sections)
    joined_after = " ".join(after.get(key, before.get(key, "")) for key in sections)
    edited = [e for e in edits if not e.unchanged]
    before_words = len(_WORD.findall(joined_before))
    after_words = len(_WORD.findall(joined_after))
    return EditReport(
        sections=edits,
        overall_similarity=similarity(joined_before, joined_after),
        overall_normalised_distance=normalised_distance(joined_before, joined_after),
        total_edit_distance=sum(e.edit_distance for e in edits),
        sections_edited=len(edited),
        substantive_sections=sum(1 for e in edited if e.substantive),
        insertion_sections=sum(1 for e in edited if e.chars_inserted > e.chars_removed),
        deletion_sections=sum(1 for e in edited if e.chars_removed > e.chars_inserted),
        chars_inserted=sum(e.chars_inserted for e in edits),
        chars_removed=sum(e.chars_removed for e in edits),
        blocks=sum(e.blocks for e in edits),
        words_added=max(0, after_words - before_words),
        words_removed=max(0, before_words - after_words),
    )


def _typed_chars(before: str, after: str) -> tuple[int, int]:
    """(characters the human typed, characters of the original that survived).

    Derived from the opcodes, not from length differences: a reviewer who deletes a
    sentence and writes a different one has typed the second sentence's length, and the
    first one's length never survived. Length arithmetic would call that zero work.
    """
    typed = survived = 0
    for tag, i1, i2, j1, j2 in SequenceMatcher(None, before, after).get_opcodes():
        if tag in ("insert", "replace"):
            typed += j2 - j1
        if tag in ("equal", "replace"):
            survived += i2 - i1
    return typed, survived


def _shared_chars(a: str, b: str) -> int:
    """Characters of `b` that also appear, in place, in `a`.

    Only `equal` opcodes count. A `replace` is not shared content — it is the work — and
    counting it is how a transcription measure quietly becomes a flattering one.
    """
    shared = 0
    for tag, _i1, _i2, j1, j2 in SequenceMatcher(None, a, b).get_opcodes():
        if tag == "equal":
            shared += j2 - j1
    return shared


def typing_reduction(
    draft: dict[str, str],
    final: dict[str, str],
    reference: dict[str, str],
    dictation: str,
    sections: tuple[str, ...],
) -> dict[str, float | None]:
    """Four quantities behind one phrase, because the phrase is used to justify a product.

    `draft_retention` — the share of the draft's characters that survived into the signed
    report. This is the number a vendor quotes, and it *rises* when the model says more and
    the reviewer is busier, which is precisely the automation-bias signal it must not be
    allowed to hide (`docs/safety/CLINICAL_SAFETY.md` §4). It is reported beside
    `substantive_sections` for that reason, never alone.

    `human_typed_chars` — what the clinician actually produced. The cost side of the claim,
    and the only one of these that is an observation rather than a ratio.

    `composition_avoided` — one minus typed over the reference report's length: how much of
    the writing a person did not have to do. Bounded to [0, 1] and marked clamped when the
    reviewer wrote more than the reference, which happens and is information.

    `composition_share` — the ceiling. How much of the reference report is *not* already in
    the dictation. A product cannot save more composition than exists, and this number is
    computable today from a corpus with no model and no clinician (`evidence.baseline`).
    """
    reference_len = sum(len(reference.get(key, "") or "") for key in sections)
    draft_len = sum(len(draft.get(key, "") or "") for key in sections)
    if not reference_len or not draft_len:
        return {
            "draft_retention": None,
            "human_typed_chars": None,
            "composition_avoided": None,
            "composition_share": None,
            "clamped": False,
        }

    typed = survived = 0
    for key in sections:
        section_typed, section_survived = _typed_chars(draft.get(key, ""), final.get(key, ""))
        typed += section_typed
        survived += section_survived

    avoided = 1 - (typed / reference_len)
    clamped = avoided < 0
    composition_avoided = min(1.0, max(0.0, avoided))

    # The ceiling is measured character-wise against the dictation, the same instrument as
    # `composition_avoided`, so the two are comparable.
    joined_reference = " ".join(reference.get(key, "") or "" for key in sections)
    shared = _shared_chars(dictation or "", joined_reference)
    composition_share = 1 - (shared / reference_len) if joined_reference else None

    return {
        "draft_retention": round(survived / draft_len, 4),
        "human_typed_chars": typed,
        "composition_avoided": round(composition_avoided, 4),
        "composition_share": round(composition_share, 4) if composition_share is not None else None,
        "clamped": clamped,
    }
