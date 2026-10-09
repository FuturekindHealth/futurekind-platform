# Clinical Evidence Framework

Genesis Night 5, 2026-10-09. The instruments are in
[`scripts/validation/evidence/`](../../scripts/validation/evidence/); this directory is what
makes them usable by a person who does not read the code.

FutureKind has architecture, philosophy and documentation. It has never had evidence: no real
model has been measured here, no radiologist has been timed, and not one case in the corpus is
ratified. This framework does not fix that. What it does is make the fix *expressible* — so
that when the one afternoon in [`product/ROADMAP.md`](../product/ROADMAP.md) §4.2 finally
happens, the numbers it produces are already designed, already sized, and already have a place
to live that is not a spreadsheet.

**The question everything here answers:** can FutureKind prove that it makes clinicians faster,
safer and more accurate? Three words, three separate measurement problems, and no permission to
collapse them.

---

## 0. The twelve named outputs, and where each lives

The brief named twelve documents. Rule 3 of [`README.md`](../README.md) §10 forbids a second
file for one subject, so each is stated once, here:

| Named output | File | Owns |
| --- | --- | --- |
| Clinical Evidence Framework | this file | What evidence is here, what it is not, and the states a number may be in |
| Validation Handbook | [`HANDBOOK.md`](HANDBOOK.md) | How to run the instruments, in order, on a machine that is not this one |
| Evaluation Protocol | [`PROTOCOL.md`](PROTOCOL.md) | The study: participants, sampling, sizes, the pre-registered questions, and what each can conclude |
| Error Taxonomy | [`ERROR_TAXONOMY.md`](ERROR_TAXONOMY.md) | The 26 classes, generated from the code that defines them |
| Metric Definitions | [`METRICS.md`](METRICS.md) | Every metric, its formula, its denominator, how it is gamed — and the ones that were deleted |
| Ground Truth Specification | [`GROUND_TRUTH.md`](GROUND_TRUTH.md) | What a case must carry before it can be an expected answer, and who may say so |
| Clinical Benchmark Framework | [`BENCHMARK.md`](BENCHMARK.md) | Per-department benchmarks and the gate that promotes one |
| Research Handbook | [`RESEARCH.md`](RESEARCH.md) | Publication tables, statistics, figures, export, and the anonymisation gate |
| Experimentation Guide | [`EXPERIMENTATION.md`](EXPERIMENTATION.md) | A/B design: allocation, registration, analysis, multiplicity |
| Continuous Improvement Framework | [`IMPROVEMENT.md`](IMPROVEMENT.md) | Both feedback loops, the regression gates, and the longitudinal questions |
| Hospital Analytics Guide | [`ANALYTICS.md`](ANALYTICS.md) | Seven readers, what each sees, what each must never see, and multi-centre scaling |
| FutureKind Evidence Roadmap | [`EVIDENCE_ROADMAP.md`](EVIDENCE_ROADMAP.md) | The order in which the evidence gets built, with the cost of each step |

One extra file, [`BASELINE.md`](BASELINE.md), is not an output: it is the generated artefact of
`python -m evidence baseline --markdown`, and it is the only table in this directory that no
human is allowed to edit.

## 1. What is built, and what it can currently prove

Fifteen modules, no third-party statistics or machine-learning library — PyYAML appears once, to
read the corpus this repository already ships. The standard library was chosen deliberately: a
hospital that installs this offline must be able to run its own measurements, and a measurement
that needs a package nobody has on the clinic machine is a measurement that will not happen.

Measured on 2026-10-09 on the Python 3.12 environment [`HANDBOOK.md`](HANDBOOK.md) §1 sets up —
not a machine path, because a measurement that only reproduces on one laptop is not a
measurement. Reproduce with the commands in that section:

| Claim | Value | Command |
| --- | --- | --- |
| Evidence tests | 71, all passing | `python -m pytest -q scripts/validation/test_evidence.py` |
| Dashboard tests, now in CI | 28 | `python -m pytest -q scripts/validation/test-dashboard.py` |
| Instrument self-tests | 9 of 9 | `PYTHONPATH=scripts/validation python -m evidence selftest` |
| Refusals mutation-proved | 14 of 14 | [`HANDBOOK.md`](HANDBOOK.md) §6 |
| Error classes | 26 across content, form, process, evidence | `python -m evidence taxonomy` |
| Classes with an engine detector | 9 of 26 — 34.6%, and 8 of 12 content classes | same, `engine_coverage` |
| Score axes | 6, with no composite permitted | `evidence/scoring.py` `assert_not_combined()` |
| Ratified cases in the corpus | **0 of 100** | `python -m evidence groundtruth` |

The two numbers that decide the sprint are the last two. An error taxonomy in which most classes
are detected by a human rather than the engine is an honest one, not a broken one — a radiology
report's *meaning* is not pattern-matchable, and [`product/ROADMAP.md`](../product/ROADMAP.md)
§4.1 already measured that a hypothetical tenth check catches 85% of hallucination probes only by
flagging 17 words on every correct report. But 0 of 100 ratified cases means **every number this
system can produce today is a number about the instruments, not about care.** That is stated in
the data, not in a footnote: `evidence.baseline` prints it as one of the four limitations
attached to its own table, and `evidence.groundtruth` returns
`usable_as_evidence_about_care: 0.0`.

## 2. Where this sits in the four stages

[`BLUEPRINT.md`](../BLUEPRINT.md) §1 (`docs/BLUEPRINT.md:57`) describes the platform's evolution in
four stages and says
stage 4, Evidence, is "**Not started, and this is the whole game**": audit is emitted but not
retained, there is no Hospital object, and identity is one shared key. Night 5 builds the
instruments stage 2's test asks for; it does not reach stage 4.

| Stage, as [`BLUEPRINT.md`](../BLUEPRINT.md) §1 defines it | Its own test | State after Night 5 |
| --- | --- | --- |
| 1 — Gate: one boundary a model request cannot avoid | A caller cannot name a model; the Gateway refuses to boot on an unknown alias | Done, guarded by tests — unchanged tonight |
| 2 — Instrument: every safety claim carries a measurement | A radiologist's time-to-sign and edit rate are measured *by them*, not inferred by the tool | **The instruments for that test now exist and are tested.** The measured half is still empty: no model has run here and no clinician has been timed |
| 3 — Suite: many applications on one language | A second specialty ships without touching the platform | Designed — fourteen applications, one implementation |
| 4 — Evidence: the artefact a hospital produces for a regulator | Any of the six medicolegal questions in `safety/CLINICAL_SAFETY.md:165` answered from stored data in under a minute | **Not reached, and nothing tonight claims otherwise.** The store, the record shape and the audiences are new; retention and identity are not |

One thing Night 5 does change is the evidence system's own position against the clinical gates in
[`safety/CLINICAL_SAFETY.md`](../safety/CLINICAL_SAFETY.md) §6. G3 demands "a refusal path, a
test, and a check that the test fails when the path is removed" — the evidence refusals meet that
clause: 14 of 14 guards were broken one at a time on 2026-10-09 and each break failed a named test
([`HANDBOOK.md`](HANDBOOK.md) §6). G1 (`docs/safety/CLINICAL_SAFETY.md:136`, ratified cases for
that department), G2, G4 and G5 are untouched and cannot be moved by code. G5 — a named clinical
owner for each skill's risk — is the row §6 itself calls "the one the whole family is waiting on",
and no instrument in this directory changes that.

The jump from Instrument to Evidence is one afternoon of the owner's life, not a sprint of code.
It is scheduled in [`PROTOCOL.md`](PROTOCOL.md) §4 and priced in
[`EVIDENCE_ROADMAP.md`](EVIDENCE_ROADMAP.md) §2.

## 3. The three states a measurement may be in

Every quantity in this directory is in exactly one of these states, and a document that does not
say which one is the defect, not the number:

1. **Measured** — produced by a command, on data that exists, dated. Quotable. Example: median
   composition share 0.9446 over 100 synthetic cases, 2026-10-09.
2. **Computable but unrun** — the instrument is finished and tested against synthetic input, but
   the real input does not exist yet. Quotable *only* as a capability. Example: time saved per
   report; review seconds; edit distance between an AI draft and a signed report.
3. **Not computable** — no instrument exists, or the input can never exist under the current
   design. Example: inter-reviewer agreement, until two named clinicians independently review the
   same case, which requires per-person credentials that [`ARCHITECTURE.md`](../ARCHITECTURE.md)
   records as unbuilt (ADR-0004).

The failure this rule is aimed at is state-2 numbers being quoted in state-1 tense.
[`CONSTITUTION.md`](../CONSTITUTION.md) P13 and [`INVARIANTS.md`](../INVARIANTS.md) N14 both
exist because a system that overstates its own certainty is worse than one that does nothing.

## 4. What a session record is, and the eight facts it carries

Part 1 of the brief asked what the framework must collect: case, time, skill, model alias, draft,
review, approval, export. That is the shape of `evidence.store.SessionRecord`, and nothing wider:

| Collected | Field | Notes on what it is *not* |
| --- | --- | --- |
| Case | `case_ref` | An opaque reference resolvable offline. Not a name, MRN, UHID or accession — `evidence/taxonomy.py` class `E11` exists precisely because identifier tokens leak into drafts |
| Site | `site` | Needed for the multi-centre chapter; also the quasi-identifier that k-anonymity has to protect |
| Who | `actor_label`, `role` | A label, not a credential. Authentication does not exist (ADR-0004), so "who reviewed this" is attested, never verified — class `E22` |
| Time | `started_at`, `stages{}`, derived `stage_seconds`, `time_to_final_seconds` | ISO stamps with a timezone. A naive timestamp is refused at `period_key()`, because a trend across mixed timezones is not a trend |
| Skill and model alias | `provenance.skill`, `.alias`, `.model`, `.capability`, `.prompt_version`, `.profile`, `.attempts`, `.degraded`, `.stub` | Filled from the response's own `model_provenance`, which is what the copilot already returns (`scripts/validation/run-cases.py:288`). `stub=True` rows are filtered out of every claim by `real_rows()` |
| Draft, review, approval, export | `stages` keys `received`, `drafted`, `checked`, `reviewed`, `approved`, `exported` | Durations are derived from stamps, never passed in — a study that records "seconds spent reviewing" as an input has recorded an opinion |
| The document | `sections{}`: `chars`, `words`, `sha12` per section | **Hashes and lengths by default.** Full text is stored only when the caller passes `allow_text`, and a record carrying text sets `text_stored: true` so it can never be exported quietly |
| Engine and edit measures | `engine{}`, `edit{}` | Findings, blocks, advisories, per-section diffs |
| Clinical judgement | `labels[]`, `scores{}` | Taxonomy codes and the six axes, never a composite |

Two refusals are load-bearing and both are tested by breaking them
([`HANDBOOK.md`](HANDBOOK.md) §6):

- **The store refuses to live inside the repository.** `store.append()` raises on any path under
  `git rev-parse --show-toplevel`. A draft becomes patient text the moment it is about a patient,
  and this tree is public. This turns the prose rule in [`product/ROADMAP.md`](../product/ROADMAP.md)
  §4.2 — "the case file must live outside any git working tree" — into a call that fails.
- **A record with text and no explicit consent raises.** Storage of clinical text is a decision,
  not a side effect of calling a function.

## 5. The gold-standard frame, per case

Part 2 of the brief: for every case, the artefacts below must be able to exist, and the framework
must say which of them it has. Design, not invention. They split across two records on purpose —
the **case** holds what the answer is, the **session** holds what anyone wrote on the way to it:

| Artefact | Lives in | Field | Refusal or rule |
| --- | --- | --- | --- |
| The dictation the AI was given | case | `dictation` | A case with no dictation raises: there is nothing for a fidelity check to be about |
| Final approved report | case | `expected_sections` | Must name the sections the department expects; a report with no expected structure cannot be scored for coverage |
| The hallucination probes | case | `must_not_say` | The assertions that would be a dangerous answer even if the rest is right |
| AI draft | session | `sections{}` at stage `drafted` | A hash and lengths by default, so the draft never sits in a git tree |
| Human draft before seeing the AI | session | order-dependent; not yet a field | **Open gap.** Without it the order effect — the difference between correcting a draft and writing one — cannot be separated from the drafting itself. §7 names this as the framework's own missing finding |
| Reviewer comments | session | `edit{}` diffs, `labels[]` | A comment is a diff plus a class, not free prose, or it becomes the thing nobody reads |
| Error labels | case or session | `error_labels[]` | Must be `E`-prefixed taxonomy codes, or the label is prose |
| Difficulty, specialty, risk | case | `difficulty` (1–5), `specialty`, `risk` (low/moderate/high/critical) | Difficulty outside 1–5 raises; a pass rate over easy cases is a marketing number |
| Teaching value | case | `teaching_value` | Present in all 100 corpus cases, which is why they are teaching cases rather than evidence |
| Provenance of the answer | case | `provenance` ∈ real_signed_report, synthetic_engineered, derived_from_real_deidentified | The three states a clinical answer can honestly be in |
| Ratification | case | `ratified`, `ratified_by`, `ratified_role`, `ratified_on`, `author` | **The gate.** `engineering` is not a ratifying role — only consultant, clinical_authority or department_board can ratify; the author cannot ratify their own case ([`GOVERNANCE.md`](../GOVERNANCE.md) G2); and `ratified` without a named person and a date raises, because then it is an assertion |

`is_ground_truth()` is therefore false for all 100 cases in the golden dataset, and
`corpus_summary()` says so as a number: `ratified_and_valid: 0`,
`usable_as_evidence_about_care: 0.0`, `by_provenance: {synthetic_engineered: 100}`.

## 6. What this directory refuses to hold

- **No patient text, ever, in the repository.** Not in a document, not in a test fixture, not in
  an example row. The examples in these files are synthetic and say so.
- **No composite score.** Six axes, kept apart, forever ([`METRICS.md`](METRICS.md) §5).
- **No applied improvement.** The loops produce ranked *proposals*; `loops.apply()` raises
  ([`IMPROVEMENT.md`](IMPROVEMENT.md) §4).
- **No comparison of patient data across centres.** Only rates, prompts, workflows and case mix
  ([`ANALYTICS.md`](ANALYTICS.md) §6, P14).
- **No number without its denominator, its n, and its state** (§3).

## 7. What this framework is still missing

Stated because a framework that lists only its own completed parts is a marketing document.
Each line was checked against the tree on 2026-10-09, and the first one is the reason the rest
can stay open.

1. **Nothing produces a session record yet.** `grep -rln "from evidence" apps/ core/
   scripts/` returns one file: `scripts/validation/test_evidence.py`. The instruments have no
   producer. `run-cases.py session` already collects nearly every fact —
   `draft_seconds`, `review_seconds`, `accepted`, per-section similarity, typing measures, model
   provenance (`scripts/validation/run-cases.py:546`) — but it writes its own row shape. The
   bridge is small and deliberately not written tonight: a converter written before the first
   real session would be a guess about which fields the afternoon actually needs, and a guess
   encoded as code is how an unused abstraction becomes permanent.
2. **The harness records durations; the record wants timestamps.** `cmd_session` stores
   `draft_seconds` and `review_seconds` (`run-cases.py:549-551`), while
   `SessionRecord.stage_seconds()` derives durations from ISO stamps. Deriving stamps back from
   durations would be inventing data, so the fix belongs in the harness at the moment the
   afternoon is run, not in a conversion that fabricates the input.
3. **No field for the human draft written before the AI was seen.** Without it, the order effect
   — correcting a draft versus composing one — cannot be separated from drafting, and every
   "time saved" number stays ambiguous about who did the work. Added to the study sheet in
   [`PROTOCOL.md`](PROTOCOL.md) §3 as a required column, not to the schema as an unused field.
4. **`actor_label` is a label, not a credential.** Inter-reviewer agreement therefore cannot be
   attributed to a person at all, only to a claimed role. `docs/ARCHITECTURE.md:308` is the row
   of the as-built inventory that lists Authentication, Authorization, Permissions,
   Notifications, Secrets, SDK and CLI as **Not built**, with the Gateway's only credential a
   shared API key (ADR-0004). Class `E22` `unattributable` is the honest label for every session
   recorded this way.
5. **No ratification surface.** Ratification is a validated field with refusals, and nothing else
   — no import path, no screen, no queue. A clinical authority currently ratifies a case by
   editing a file, which is workable for 20 cases and not workable for 2,000.
6. **No centre identifier decided.** `site` exists as a string. What names a centre, who issues
   the name, and whether it is the hospital or the installation, is the same undecided question
   as patient identifiers — `docs/DOMAIN_MODEL.md:1283` records Q2 as a position, not an answer,
   and it stays the owner's to decide.

## 8. Drift check

Rule 4 of [`README.md`](../README.md) §10 asks every document to name the check that fails when it
drifts. For this file it is the pair of commands in [`HANDBOOK.md`](HANDBOOK.md) §1 — the test run
and the ground-truth summary. If the numbers in §1 no longer match what the commands print, the
table is stale, and the second row of that table is the one most likely to move: it counts tests,
and a test count is a mechanism's shadow ([`CONCEPTUAL_DEBT.md`](../CONCEPTUAL_DEBT.md) D2, which
is why this table is dated and names its command instead of asking to be believed).

The line citations in §4 point at files whose content the tests pin: `run-cases.py:288` is
asserted by nothing, so treat it as a pointer to re-open, not as a verified fact.
