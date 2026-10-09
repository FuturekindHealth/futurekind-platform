"""FutureKind evidence — the instruments that turn clinical work into data.

This package measures. It does not route, decide, or store anything on the request
path: nothing here is imported by the Gateway, and nothing here may be, because the
AI boundary is the one the platform's principles guard
(`docs/CONSTITUTION.md` P16, `docs/BLUEPRINT.md` §2.1).

What exists and why:

| Module | The question it answers |
| --- | --- |
| `taxonomy` | Which error is this? A defect with no named class is decoration. |
| `edits` | What did the human actually change, and was it substance or style? |
| `scoring` | How good was this artefact, on six axes kept apart? |
| `groundtruth` | What must a case record carry before any of the above can be trusted? |
| `stats` | Is the difference real, and how much data would it take to know? |
| `store` | Where does a session record live without becoming a PHI incident? |
| `baseline` | How much work is a report, measured from the corpus we already have? |
| `regression` | Did this change make anything worse? Four gates, one exit code. |
| `experiment` | Prompt A versus prompt B, designed before it is run. |
| `longitudinal` | Is it improving — and of what confounding is that statement innocent? |
| `loops` | Edits and overrides, classified and ranked into a *proposal* a person decides on. |
| `audience` | Seven readers, seven views, and an honest note on what "view" does not mean. |
| `research` | Tables, statistics, figures, CSV, and an anonymisation gate that refuses. |

Two rules bind every module here, and they are inherited rather than invented:

**A metric that can be gamed is reported with the gaming named beside it**
(`docs/FAILURE-MODES.md` FM10, `docs/CONCEPTUAL_DEBT.md` §2.2).

**No measurement is presented as evidence about care unless it was taken on a
ratified case with a clinician in the loop.** The instruments run today against
synthetic, engineer-authored, unratified cases and a stub model, and their output
says so in the data, not in a footnote (`docs/safety/CLINICAL_SAFETY.md` §5).
"""

from __future__ import annotations

__all__ = ["TAXONOMY_VERSION", "SCHEMA_VERSION"]

#: Bumped when a code is added, removed or redefined in `taxonomy`. A stored record
#: that names an older taxonomy is comparable only after the diff between versions is
#: read, which is why the number travels inside every record.
TAXONOMY_VERSION = 1

#: Bumped with any change to `store`'s session-record shape.
SCHEMA_VERSION = 1
