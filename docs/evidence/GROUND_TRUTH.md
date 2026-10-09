# Ground Truth Specification

Part 2 of the sprint, and the file that decides what every other file in this directory is allowed
to say. The instruction was explicit: **design the framework, do not invent the data.** This is the
framework; the data is a clinical authority's to supply.

Implemented in
[`../../scripts/validation/evidence/groundtruth.py`](../../scripts/validation/evidence/groundtruth.py),
printed by `python -m evidence groundtruth`.

---

## 1. What "ground truth" means here, and what it does not

A ground-truth case is one whose expected answer a clinically qualified person has accepted, under
their own name, on a date, having not written it themselves. That is the whole definition, and each
of the four parts kills a different fake:

| Without | You get |
| --- | --- |
| a clinical person | An engineer's idea of a report, scored as though it were a department's |
| under their own name | A consensus nobody is accountable for |
| on a date | A standard that moved quietly between two comparisons |
| not written by them | The author grading their own homework — `../GOVERNANCE.md` G2 |

Ground truth is **not**: the model's output, a reference abstract, a textbook description of the
finding, or the majority label of a crowd.

## 2. The record

`GroundTruthCase` carries the case, the answer, the probes, the judgement and the ratification:

| Group | Fields |
| --- | --- |
| Identity | `case_id` (opaque, never a patient identifier), `site`, `source` |
| Classification | `specialty`, `modality`, `study`, `category` (normal / common / rare / emergency / medicolegal), `difficulty` 1–5, `risk` (low / moderate / high / critical), `indication` |
| The input | `dictation` — what the reporting clinician actually said, which is the AI's input |
| The answer | `expected_sections`, keyed by the section names the department requires |
| The probes | `must_not_say` — assertions that would be a *dangerous* answer even if the rest is right |
| The judgement | `error_labels` (taxonomy codes), `teaching_value`, `provenance` |
| Provenance of the answer | `provenance` ∈ `real_signed_report`, `derived_from_real_deidentified`, `synthetic_engineered` |
| Ratification | `ratified` ∈ `pending`, `ratified`, `rejected`; `ratified_by`, `ratified_role`, `ratified_on`, `author` |

`difficulty` is a number, not a string, and outside 1–5 the record is refused. A pass rate over easy
cases is a marketing number, and the difficulty distribution is therefore part of every comparison
([`RESEARCH.md`](RESEARCH.md) §3).

## 3. The refusals, in the words the code uses

`validate()` returns problems; `require_valid()` raises them as one `RecordError` naming the case.
Each of these is exercised by a test, and the self-ratification one is mutation-proved
([`HANDBOOK.md`](HANDBOOK.md) §6):

- `case_id is required: an anonymous case cannot be re-examined`
- `no dictation: there is nothing for a fidelity check to be about`
- `error label '<x>' is not an evidence.taxonomy code`
- `ratified must be one of ('pending', 'ratified', 'rejected')`
- `a ratified case needs a clinical role: author and ratifier must differ (GOVERNANCE.md G2)`
- `ratified needs a named person and a date, or it is an assertion`
- `the case's author cannot ratify it`

`RATIFYING_ROLES` is `consultant`, `clinical_authority`, `department_board`. **`engineering` is
deliberately absent.** The author of an evaluation case cannot be the authority that makes it true.

## 4. What is true of the corpus today

`python -m evidence groundtruth`, 2026-10-09, over all 100 cases in
[`../product/GOLDEN_DATASET.yaml`](../product/GOLDEN_DATASET.yaml):

```json
{"cases": 100, "ratified_and_valid": 0, "usable_as_evidence_about_care": 0.0,
 "with_validation_problems": 0,
 "by_provenance": {"real_signed_report": 0, "derived_from_real_deidentified": 0,
 "synthetic_engineered": 100}}
```

Read the two numbers together, because they mean different things and the difference is the design:

- **0 ratified** — none of it may be used to make a claim about care.
- **0 with validation problems** — every case is *structurally* sound. These are good cases, written
  with care, and they are exactly what an engineer is allowed to build instruments against.

`is_ground_truth()` is false for all 100. That is not a bug to fix in the code; it is the state of
the evidence, and this file will need rewriting when it changes.

## 5. Ratifying a case, as a procedure

1. A clinician picks cases from the department's own work, not from a list engineering prepared — the
   selection of *which* cases to ratify is itself a case-mix decision.
2. They receive the dictation and the expected answer, and correct the answer if it is wrong. A
   ratified case with an error in it is worse than an unratified one, because it now gets trusted.
3. They record `difficulty`, `risk`, `teaching_value`, and the `must_not_say` assertions that would
   have been dangerous in *their* reading of this case.
4. Someone else — not the author — sets `ratified: ratified`, `ratified_by`, `ratified_role`,
   `ratified_on`. Two names, one per role.
5. The file lives outside the repository if it contains real text
   ([`FRAMEWORK.md`](FRAMEWORK.md) §4). A ratified case derived from a real report is
   `derived_from_real_deidentified`, and the de-identification decision is recorded, not assumed.

## 6. What ratification costs, stated plainly

Roughly an hour per department for twenty cases, in the owner's own words: it is the same attention
the clinic already pays when a trainee's report is taught up. Nothing in this specification requires
a new role, a new system, or a research office. It requires a consultant to sign twenty files, which
is the gate [`EVIDENCE_ROADMAP.md`](EVIDENCE_ROADMAP.md) §2 prices first and
[`../safety/CLINICAL_SAFETY.md`](../safety/CLINICAL_SAFETY.md) §6 calls G1.

## 7. What this file refuses

- **No synthetic case may be described as ground truth,** including in a figure caption.
- **No case may be ratified by its author,** and the code will not accept one that is.
- **No patient identifier in `case_id`,** ever — `docs/product/GOLDEN_DATASET.yaml:19` states the
  discipline for case ids, and class `E11` exists because identifier tokens appear in drafts.
- **No silently changed expected answer.** Once a case is cited by a result, editing
  `expected_sections` invalidates every number computed against it; the version of the corpus belongs
  in the series key ([`IMPROVEMENT.md`](IMPROVEMENT.md) §5).

## 8. Drift check

The check that fails when this file drifts is `python -m evidence groundtruth`, which prints the
same four numbers as §4, plus `test_golden_corpus_is_explicitly_not_ground_truth`,
`test_author_cannot_ratify_their_own_case` and `test_ratified_needs_a_clinical_role` in
`test_evidence.py`. The quoted refusal strings in §3 are copied from `groundtruth.py`; if one is
reworded there, §3 becomes wrong and the tests still pass — which is why they are quoted rather than
paraphrased.
