# Metric Definitions

Part 3 of the sprint asked for every metric to be reviewed, the weak ones deleted and the missing
ones added. Part 14 asked whether each one can be gamed. This file is both answers in one place:
sixteen candidate metrics named in the brief, each with its disposition, its implementation, its
denominator, its gaming route, and the decision.

Written 2026-10-09. Where a metric is implemented, the named symbol is in
[`../../scripts/validation/evidence/`](../../scripts/validation/evidence/) and is exercised by
`test_evidence.py`; where it is not, the table says so rather than implying it.

**A disposition is not a verdict on the idea.** Six of these were deleted or renamed, and each of
those six is a claim somebody has made in public about an AI scribe. They are deleted because a
number that cannot survive a reader who wants it to mean something else is not a measurement.

---

## 1. The four states, again, because every row below uses them

| State | Meaning in the rows | Quotable as |
| --- | --- | --- |
| **M** | Measured on data that exists | A number, with its date and command |
| **C** | Computable: the instrument is built and tested, the input does not exist yet | A capability, never a result |
| **N** | Not computable under the current design, with the reason named | An open question |
| **D** | Deleted or renamed after review | History, in §6 |

## 2. The dispositions

| Candidate metric | Disposition | Implementation | Denominator | How it is gamed | State |
| --- | --- | --- | --- | --- | --- |
| Time saved | **Kept, but only as an interval.** `store.SessionRecord.time_to_final()` is derived from `received → approved` stamps; a duration passed in as data is refused by design | `evidence/store.py` `stage_seconds`, `time_to_final` | per case, then the distribution (`store.distribution`) not the mean | Drafting faster by reviewing less. It is only "saved" against a human-draft-first baseline, which the framework does not yet collect ([`FRAMEWORK.md`](FRAMEWORK.md) §7.3) | C |
| Typing reduction | **Kept as four quantities, refused as one.** `edits.typing_reduction()` returns `draft_retention`, `human_typed_chars`, `composition_avoided`, `composition_share`, and `clamped` | `evidence/edits.py` `typing_reduction` | characters, and the reference report's length | Publishing only `composition_share` (0.9446 median on the corpus) reads as a product that removes 94% of writing; it measures a summary's share of a summary | M |
| Acceptance rate | **Kept, bound.** `run-cases.py` records `accepted` and `signed_after_edits`; it is quoted only beside `substantive_sections` | `evidence/edits.py` `EditReport.substantive_sections` | cases with a review outcome | Accept fewer drafts by asking the AI only for easy cases — which is why every rate here travels with `case_mix` | C |
| Edit distance | **Demoted to a component.** `total_edit_distance` and `normalised_distance` exist; the brief's "edit distance as a quality score" is deleted (§6) | `evidence/edits.py` `edit_distance`, `normalised_distance`, `similarity` | characters per section | A terse wrong draft is closer to the reference than a long right one, so distance rewards brevity and punishes completeness | C |
| Section rewrites | **Kept — and only the substantive half.** `sections_edited` is a step toward the number that means something; `substantive_sections` is the one used in every gate | `evidence/edits.py` `compare_documents` | sections, over `MODEL_SECTION_KEYS` supplied by the caller | Cosmetic reformatting inflates `sections_edited`; `is_substantive()` exists to refuse that, and its reasons are stored so the decision can be re-read | C |
| Phrase rewrites | **Deleted** (§6). Per-section `reasons` carry the same information with a name attached | `evidence/edits.py` `SectionEdit.reasons` | — | Any count of "phrases" is a count of tokenisation choices, not of clinical events | — |
| Hallucination rate | **Renamed** (§6) to *clinically consequential labels per 100 cases*, by class `E02`/`E07`/`E08` | `evidence/reporting.py` `_aggregate` → `error_classes`, `error_classes_by_group` | 100 labelled cases, and the audit volume beside it | The rate falls whenever auditing falls. [`product/ROADMAP.md`](../product/ROADMAP.md) §4.1 measured detection at 3 of 306 probes, so an engine-derived "hallucination rate" would be a measurement of the auditor | N for the engine, C with human labels |
| False blocking | **Kept.** `E16 false_alert`, found by the paired oracle — a faithful draft that still blocks | `evidence/taxonomy.py` `E16`; endpoints in `regression.DEFAULT_ENDPOINTS["safety"]` | faithful drafts (100 in the corpus) | Report it as a rate over probes instead of over faithful drafts, where the denominator is chosen so the number looks small | M, at 1 of 100 |
| False advisory | **Kept with a condition.** Advisory counts are quoted only with the *sole-reason* count, because an advisory that is never the only thing on screen costs nothing | `evidence/reporting.py` `_aggregate["error_classes"]`, engine findings in `SessionRecord.engine` | cases carrying that advisory | Deleting advisories lowers the number without improving anything, so the regression gate treats removed blocks as a safety event, not a productivity win | C |
| AI trust | **Deleted as a metric** (§6). It survives only as a direct question in the study sheet | — | — | A trust index is the cleanest route to the FM10 failure: a reporter who trusts edits less, and is not right more often, looks like a product success | — |
| Report completeness | **Kept** as `structure_coverage` plus the case's declared `expected_sections` | `futurekind_radiology.quality` check, mapped to `E01`/`E09`/`E13` | sections the department requires | A report can be structurally complete and clinically empty, which is why this axis never stands alone | M for structure, N for meaning |
| Clinical usefulness | **Refused as an instrument.** It is a clinician's judgement, so it is collected as the `clinical_correctness` axis or not at all | `evidence/scoring.py` `AXIS_SOURCES["clinical_correctness"]` | ratified cases | Any proxy — word count, similarity, length of impression — turns a proxy into a claim about care | N |
| Review burden | **Kept** as `review_seconds` and `E18 workflow_interruption` | `evidence/store.py` stage deltas; `evidence/taxonomy.py` `E18` | cases, and the report's own length | Time moved from typing to reading is not burden; time moved to friction is. The workflow gate therefore uses a *relative* tolerance on the baseline, never an absolute one | C |
| Rework | **Deleted as a rate** (§6). The events that would compose it are kept as labels | — | — | "Rework" has no agreed denominator: per case, per section, per reporter, per report. A metric whose denominator is negotiable is not a metric | — |
| Confidence | **Inverted.** The model's self-reported confidence is error class `E10`, not a signal — `self_reported_confidence` is one of the nine engine checks | `evidence/taxonomy.py` `E10`; `ENGINE_CHECK_IDS` | drafts that state a confidence | Reading it as reassurance is the failure the check exists to catch. Human confidence stays a survey item | M |
| Inter-reviewer agreement | **Not computable, and no proxy is allowed.** It needs two named independent reviews; identity is one shared key | — | pairs of independent reviews of the same case | Anonymous agreement computed from unattributed labels would be a kappa with no subjects in it | N |

## 3. The four regression endpoints

`regression.DEFAULT_ENDPOINTS` is the smallest set that can say "nothing got worse", one per
dimension, each paired on the same cases:

| Gate | Endpoint | Regression means | Tolerance |
| --- | --- | --- | --- |
| safety | `faithful_refusals` — refusal rate on faithful drafts | any increase, at any n | none: `ci_high <= 0.0` |
| quality | `harmful_labels` — clinically consequential labels per case | upper bootstrap bound of the delta above 0 | none: same rule |
| workflow | `review_seconds` | median rise beyond 10% of the baseline | relative, `TOLERANCE["workflow"]` |
| productivity | `typed_chars` | rise while substantive edits stay flat | relative, `TOLERANCE["productivity"]` |

Two rules that are easy to lose and are therefore encoded: an inconclusive gate blocks the release
rather than clearing it, and every gate prints its own minimum detectable effect.
`mde_paired(20) = 0.6265` on 2026-10-09 — the twenty-case pilot can only ever see a shift of
about two-thirds of a standard deviation, and saying so is the difference between a gate and a
ritual.

## 4. What is deliberately *not* a metric here

- Nothing per-reporter, beyond a label they can see themselves. `FAILURE-MODES.md` FM10 is about
  turning a measurement into a league table, and `reporting.AUDIENCES["radiologist"]` states it as
  "individual feedback, not a league table".
- No token counts, no prompt length, no latency percentiles presented as clinical quality. Latency
  belongs to engineering's view only.
- No "AI contribution percentage". The quantity exists — `composition_share` — and it is a bound on
  a summary, not a share of work done.

## 5. Six axes, and no composite

`scoring.AXES` is exactly six: `clinical_correctness`, `writing_quality`, `workflow_quality`,
`safety`, `efficiency`, `user_satisfaction`. Each carries its own source
(`AXIS_SOURCES`), its own regression trigger (`REGRESSION_TRIGGERS`), and its own null reason when
the input is missing. `CaseScore.__post_init__` requires all six; `score_case()` returns nulls with
reasons rather than zeros; and `assert_not_combined()` raises unconditionally — the only function
in the package that always fails, kept failing by mutation
([`HANDBOOK.md`](HANDBOOK.md) §6).

A composite is not a presentation shortcut. It is a different claim: that the axes are commensurable,
which `docs/product/GOLDEN_DATASET.yaml:54` refuses in the corpus's own scoring note, and which no
amount of weighting arithmetic establishes.

## 6. What was deleted, and why

Recorded because a deletion that is not written down comes back as a new feature.

| Deleted | Replaced by | Reason |
| --- | --- | --- |
| Edit distance as a quality score | `substantive_sections`, and distance as a component only | It rewards brevity and punishes completeness |
| Phrase-rewrite count | `SectionEdit.reasons`, named | A count of tokenisation choices, not of clinical events |
| "Hallucination rate" as an engine output | labels per 100 cases by class, with audit volume beside it | Detection is measured at 3 of 306 probes; the rate would report the auditor |
| AI-trust index | one direct question in the study sheet | An index over editing behaviour makes FM10 a product goal |
| Rework rate | the `E`-class events underneath it | No agreed denominator, so every result was negotiable |
| Model self-reported confidence as a signal | error class `E10`, and an engine check that refuses it | Reading it as reassurance is the harm |
| Draft similarity as a stand-alone headline | `case_mix` beside every rate | A similar draft of the wrong thing is a safe-looking wrong thing |
| "Tests passing" as an evidence metric | the endpoints above | Counting instruments is not measuring care; `CONCEPTUAL_DEBT.md` D2 already owns that defect |

## 7. Drift check

The check that fails when this file drifts is the pair `python -m pytest -q test_evidence.py` and
`python scripts/validation/check-refusals.py`: §2's "Implementation" column names symbols that the
tests import and exercise, §3's tolerances and endpoint keys are read from
`regression.TOLERANCE` and `regression.DEFAULT_ENDPOINTS`, and §5's axis list is `scoring.AXES`. A
renamed symbol fails a test; a renamed *claim* here does not, which is why the numeric values in
§3 are stated with their command and date instead of as constants.
