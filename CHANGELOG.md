# Changelog

All notable changes to FutureKind Platform will be documented in this file.

The format is based on Keep a Changelog.

---

## [Unreleased]

Nothing below is tagged; the feature branch carries all of it.

### Genesis Night 5 — the evidence system (2026-10-09)

The brief was that the repository has enough architecture, enough philosophy and enough
documentation, and now needs **measurement** rather than more prose. The constraint held:
`core/gateway`, `apps/radiology_copilot`, `configs/`, `compose.yaml` and `docs/adr/` were not
touched. What exists tonight is an instrument package — 15 stdlib-only modules, 4,114 lines,
under `scripts/validation/evidence/` — that turns clinical work into data, the twelve documents
that say how to use it, and a CI job that runs all of it.

**Nothing was measured against a model, a patient or a clinician, because nothing is connected
to one yet.** The honest output of this sprint is the size of the gap, not a result across it:
the ground-truth store reports `ratified_and_valid: 0` and `usable_as_evidence_about_care: 0.0`.
That zero is the gate working rather than a placeholder — a case is counted only if it passes
`validate()` *and* carries a ratification, and `validate()` checks the whole chain, including
that an author cannot ratify their own case (`check-refusals.py`'s `self-ratification` mutation
proves that rule can fail). Every figure below was produced by running a command tonight, and
each is reproducible with the command printed beside it.

#### Added

- **`scripts/validation/evidence/`** — the instruments. `taxonomy.py` 26 error classes with the
  engine's real reach over them; `edits.py` Levenshtein and SequenceMatcher opcodes, section-
  and phrase-level rewrite detection; `scoring.py` six separate axes with no `total`, no
  weighted sum and no "FutureKind score" — clinical correctness, writing quality, workflow
  quality, safety, efficiency, user satisfaction — and an `assert_not_combined()` that raises
  unconditionally, because the golden dataset's own rule (`docs/product/GOLDEN_DATASET.yaml:54`:
  averaging hides both signal and danger) is worth more as a failing test than as a sentence;
  `stats.py` Wilson interval, exact McNemar, sign test, Wilcoxon signed rank (declines to give a
  p-value below n=10 and points at the sign test),
  percentile bootstrap with a published seed, paired Cohen's d with the Hedges small-sample
  correction,
  Holm step-down, and the two power formulas the study designs need; `groundtruth.py` and
  `store.py` the gold-standard record, with PHI discipline as code rather than as policy —
  hashes and lengths by default, `text_stored` only under `allow_text`, k-anonymity floor of 5
  on the quasi-identifier combination, and an `inside_repo()` refusal that stops any evidence
  store being written into the git tree; `baseline.py`, `regression.py`, `experiment.py`,
  `longitudinal.py`, `loops.py`, `reporting.py`, `cli.py`.
- **`scripts/validation/test_evidence.py`** — 71 tests, all passing, including the ones that
  pin the refusals rather than the features: the composite score cannot be requested, a loop can
  propose but never apply, a store path inside the repository is refused, an inconclusive
  regression fails closed, and every CLI refusal arrives as an exit code rather than a traceback.
- **`scripts/validation/check-refusals.py`** — the mutation harness, because a refusal nobody has
  seen fire is a belief. Fourteen mutations, each deleting one guard — `thin-cell` removes the
  k-anonymity floor, `store-path` allows an evidence store inside the repository,
  `composite-score` lets the six axes be averaged, `loop-applies` lets the improvement loop apply
  its own proposal, `self-ratification` lets a case's author ratify it, and nine more — and every
  one of the fourteen was caught. `check-refusals.py --list` prints the set, and every row names
  the single test that must fail when its guard goes. It refuses to
  start if any target file differs from `HEAD`, proves a known-green baseline first, re-checks
  each file's sha256 immediately before writing it, restores from a staging copy, and cleans
  only the debris it created.
- **`.github/workflows/ci.yml` job `validation`** — ruff at the Gateway's rule set over
  `evidence/` and its tests, then both validation test files named explicitly. The reason this
  job exists is a defect: pytest's default collection pattern wants `test_*.py`, so the
  dashboard's 28 tests had **never run anywhere**, and the 71 new ones would have joined them.
  The job also runs `python -m evidence selftest`, runs `check-refusals.py` so every refusal is
  proved to be able to fail on every push rather than on whoever remembers, regenerates the
  baseline, and greps the
  output for the two sentences that stop it being read as evidence about care.
- **`docs/evidence/`** — thirteen documents, one per subject, indexed as §11 of
  [`docs/README.md`](docs/README.md) with an owns/stops-at row each: `FRAMEWORK.md` (the study
  design across six collector roles), `HANDBOOK.md` (what a clinician does, minute by minute),
  `PROTOCOL.md` (the evaluation protocol), `ERROR_TAXONOMY.md` (the 26 classes and the generated
  coverage block), `METRICS.md` (every metric, its disposition, and the deletion register),
  `GROUND_TRUTH.md` (the gold-standard specification), `BENCHMARK.md` (the clinical benchmark
  framework), `RESEARCH.md` (publication output, anonymisation, what may be exported),
  `EXPERIMENTATION.md` (A/B arms and the statistics that decide them), `IMPROVEMENT.md` (the two
  closed loops, and why neither is allowed to apply its own proposals), `ANALYTICS.md` (seven
  audiences, seven different views, and why a view is not a permission system),
  `EVIDENCE_ROADMAP.md` (the sequence), and `BASELINE.md` (generated — do not hand-edit).
- **The baseline, from the 100 golden studies** (`python -m evidence baseline`, 2026-10-09):
  composition share mean **0.914**, median **0.9446**; 28.34 words dictated versus 38.33 in the
  reference; **3.1 probes per case**; teaching point present in 100 of 100. The finding that
  matters is the one that closes a claim rather than supporting one: **0.23 measurements per
  reference report, median 0, p75 0** — and for the `rare` and `medicolegal` categories,
  exactly **0.0**. The current corpus cannot measure measurement accuracy at all, so no
  accuracy metric may be quoted from it, and `BASELINE.md` says so in its own limitations list.

#### Changed

- `docs/product/README.md` and `docs/product/ROADMAP.md` now state the four suites and the fact
  that all of them run in CI, with the date and the command that re-counts them. Both edits are
  line-neutral, because nine tracked documents cite `docs/product/README.md` by line number and
  a shifted table row is a broken citation, not a cosmetic one.
- `docs/CONCEPTUAL_DEBT.md` D2 rewritten, and `docs/PHILOSOPHY.md`'s matching bullet corrected.
  Both previously asserted that `SPECIFICATION.md:929` "still says 482" and that
  `DOMAIN_MODEL.md:1207` "said 380". **Measured tonight, neither line contains a number, and no
  file in the repository states 482 as a count.** The register about drifted citations had
  drifted citations in it; the row now says so, and names the command that counts the nine
  tracked markdown files carrying a test figure.

#### Fixed (found by checking, not by a failing test)

- `stats.cohens_d` described itself as Hedges-corrected and was not. At n=20 the uncorrected
  statistic overstates the effect by 4.17% (`1 - 3/(4·19-1) = 0.96`), which is exactly the sample
  size a first study will have.
- The error taxonomy had two opposite errors in one table. `E02 invented_finding` was mapped onto
  `unsupported_absence` — a check that fires when a draft asserts an absence the input does not
  support, which is the other direction, so the engine has no detector for an invented finding and
  the published coverage was inflated by one class. `E03 wrong_measurement` and `E07
  unsupported_diagnosis` did cite real, correctly-directed checks (`unsupported_measurement`,
  `unsupported_certainty`) while their `detected_by` field still said `human`, so the same table
  under-reported the engine on two classes it can see. Corrected figures, published in
  `docs/evidence/ERROR_TAXONOMY.md` as generated JSON: **engine coverage 9 of 26 (0.346)**, over
  the 12 content classes **8 (0.667)**, 9 classes reachable only by a human. A test now pins all
  four numbers, and `unknown_engine_checks()`/`unmapped_engine_checks()` both return empty.
- `baseline.py`'s docstring enumerated the corpus's modalities; `HRCT` made that list false, so
  the enumeration is gone and the modality line is generated from the measurement instead.
- `docs/evidence/BASELINE.md` — the file whose own first line forbids hand-editing the numbers had
  been filled by pasting a command's output through a shell, which silently turned every `·` in
  the new modality line into a `.`. Both generated documents are now written from the generator's
  bytes and compared against it: `BASELINE.md` is byte-identical to `python -m evidence baseline
  --markdown`, and `ERROR_TAXONOMY.md`'s block is verbatim apart from one trailing newline. The
  rule a file states should be enforced by how the file is made, not by the reader's good manners.
- `experiment.py` carried a comment promising a `williams_order` that does not exist. It now
  states plainly that the design is two arms.
- `reporting.centre_summary` wrote a cross-site rule wider than **P14** allows. P14 forbids
  cross-hospital inference and any shared model of a patient, so a hospital-to-hospital
  benchmark is a governance amendment, not a field in a table; the rule text now says that.

**Self-review, part 14 of the brief.** The three ways this system can lie are recorded rather
than argued away: a rate that improves because its denominator moved (every row of
`METRICS.md` §2 carries its denominator and how it is gamed, and `case_mix` travels beside every
rate so an easier case mix cannot read as an improvement); a loop that ships its own proposal
(`loops.apply()` raises, and the mutation harness deletes that guard to prove it fails); a
composite score that lets an efficiency gain pay for a safety regression (`assert_not_combined()`
raises unconditionally, likewise mutated). `METRICS.md` §6 records the eight deletions with their
reasons — edit distance as a quality score, the phrase-rewrite count, "hallucination rate" as an
engine output, the AI-trust index, rework as a rate, model-reported confidence, draft similarity
as a stand-alone headline, and "tests passing" as an evidence metric. They are written down
because a deletion that is not written down comes back as a feature.

**What this sprint does not do.** It does not answer "does FutureKind help clinicians?" — it
makes the question answerable, and it says what has to exist before an answer is honest: a
ratifier for the golden set, a study running on a real model with real clinicians, and the three
gaps stage 4 names at [`docs/BLUEPRINT.md`](docs/BLUEPRINT.md):62 — audit emitted but not
retained, no Hospital object, identity as one shared key — which are the same four unwritten
ADRs (`docs/CONCEPTUAL_DEBT.md` D1: 0003, 0004, 0005, 0007) the platform keeps citing as
authority for borders it cannot enforce in code.



A thinking sprint on purpose: no code, no configuration, no test and no compose file
changed. Seven new documents, six extended, and one commit that corrected five statements
in the existing set which had measured the repository once and were still written in the
present tense. **No measurement was taken tonight against a model, a patient or a
clinician** — the verification here is that every claim was re-run against the tree.

#### Added

- **[`docs/PHILOSOPHY.md`](docs/PHILOSOPHY.md)** — the reasons the constitution deliberately
  withholds, and a test for telling a fundamental assumption from an accident of 2026:
  *does removing this change who is responsible, or only how it is done?* Nine assumptions
  pass; the entire technology stack fails it. The disappearance test is the sharper half —
  of the five assets that survive the code (vocabulary, refusal list, evaluation format, the
  accountability argument, the record of rejections) not one is a Python file.
- **[`docs/BLUEPRINT.md`](docs/BLUEPRINT.md)** — Gate, Instrument, Suite, Evidence: the four
  stages, with the test that says each happened. The organising finding is that the
  platform's **southern border (toward the model) is drawn in code and fails loudly, while
  its northern border (retention, identity, the never-list, ratification) is drawn in prose
  and cannot fail at all.** Also: every boundary judged, the two-user ecosystem rule, the
  competitive verdict (the moat is the buyer's ability to check — and the honest weakness,
  that FutureKind cannot sell liability transfer), founder notes and eight lessons.
- **[`docs/CONCEPTUAL_DEBT.md`](docs/CONCEPTUAL_DEBT.md)** — sixteen debt-of-ideas rows, each
  with the command that measured it; three mechanisms that explain most of them (restatement
  without generation, a claim with no instrument, a placeholder as authority); four things
  that look like debt and must be defended; ten ranked deletions. The register's heaviest row
  is 131 references to five ADRs that do not exist.
- **[`docs/FAILURE-MODES.md`](docs/FAILURE-MODES.md)** — twelve ways this dies, ranked by
  probability times irreversibility, each with an earliest warning sign a person who is not
  the author can check; seven success signals in the order they would appear; five kill
  criteria, written now while they cost nothing.
- **[`docs/INVARIANTS.md`](docs/INVARIANTS.md)** — sixteen things that will never be built,
  each paired with the *reasonable* pressure that will ask for it, and thirteen things that
  must not be lost, each with the first sign of its own disappearance.
- **[`docs/GOVERNANCE.md`](docs/GOVERNANCE.md)** — starts from a measured absence: no code of
  conduct, no CLA, no trademark policy, and no file in the repository contains the word
  "foundation". Four seats, the clinical veto (G1), segregation of duties between authoring
  and ratifying an evaluation case (G2), the free/paid line, a conformance checklist that
  turns a licence argument into an evaluation, and the triggers at which a foundation stops
  being paperwork.
- **[`docs/FIRST-WEEK.md`](docs/FIRST-WEEK.md)** — the sprint's real question: an engineer
  arrives in 2032 and has a week. Five days with one written answer each, the seven things
  that must survive any rewrite, eleven files in reading order, four traps that have each
  already caught someone here, and the first pull request.

#### Extended, in the document that already owned the subject

- `DOMAIN_MODEL.md` §11 — **ownership of truth**: for each class of fact, which file defines
  it, which may restate it, and what fails when they disagree. Tonight exactly one class has
  a failing mechanism (the alias check at boot); the other nine have none. §12 names the
  three objects stage 4 needs — **Hospital, Actor, Record** — with their banned synonyms fixed
  before they can proliferate.
- `safety/CLINICAL_SAFETY.md` §11 — the gradient as one law (*act early on drafts, at the last
  moment on decisions, never on consequences*) and the table of intentional silences, each
  with what it costs the clinician.
- `product/PRODUCT_BIBLE.md` §9 — the two-user rule: share vocabulary, policy, the review
  pattern and the evidence format; refuse the rest until a second application is real.
- `business/COMMERCIAL_ROADMAP.md` §10 — assurance is what is actually for sale, and the two
  motions that follow from it.
- `VISION-2035.md` — the 2029 and 2032 rows its own dependency table was missing.
- `docs/README.md` — the synthesis and governance layer (§8), three honesty rules became four,
  and the "no second document" rule applied to this sprint's own eighteen named outputs.

#### Fixed

- **Five statements that were true once** (`52bf45f`): the naming authority's "zero
  occurrences" proof, `services/ai/litellm` "exists as an empty directory", grounding "has no
  occurrence at all", a synonym sweep reported as applied while `ARCHITECTURE.md:150` still
  reads *Model Router*, and two stale test counts. Every edit line-neutral, because these two
  files are cited by line number from elsewhere in the set.

#### What this sprint made worse, stated plainly

Seven more documents entered a repository whose central registered defect is that it has more
claims than instruments. `CONCEPTUAL_DEBT.md` §5 says so, `docs/README.md` rule 4 now requires
every future document to name the check that fails when it drifts, and the honest defence is
that six of the seven files exist to make the other thirty checkable — but that defence is
exactly the one a documentation surplus always makes. The next sprint should add an
instrument, not an argument.

#### Genesis Night 3 — the clinical operating system, designed (2026-10-09)

Design work, deliberately: the brief was everything **above** the platform, and the platform was
left alone. **No code, configuration, test or compose file changed.** Nine new documents, three
extended, and the decisions that let the next application be authored rather than argued about.

#### Added

- **[`docs/README.md`](docs/README.md)** — the ownership index of the whole document set: what each
  document is responsible for and where it must stop. It exists because P18 makes a second owner of
  one concept a defect, and because a set this size will drift without one.
- **[`docs/product/PRODUCT_BIBLE.md`](docs/product/PRODUCT_BIBLE.md)** — the family: fourteen
  applications in three kinds (copilot, surface, console), four tests every one must pass, the
  shared-component inventory, and the refusals. Four of the brief's twenty products merged
  (Multidisciplinary into Tumour Board, Audit Timeline into a view of Clinical Timeline, Patient
  Summary into documents, Referral Intelligence split into the letter and the cohort question);
  three refused outright — Scribe (no speech path exists and adding one is a platform change),
  Clinical Search (an EHR capability, and a second index would be a second copy of patient text),
  and the Knowledge Assistant (no citation capability, so no application may present recalled text
  as a guideline).
- **[`docs/product/CLINICAL_SUITE.md`](docs/product/CLINICAL_SUITE.md)** — each application's design
  as five decisions: document shape, profiles, measured checks, versioned prompt, system of record.
  Radiology 2.0 ranked against what the repository actually holds, which produced the honest finding
  that **PI-RADS, LI-RADS, Bosniak, SONAQ and Fazekas appear nowhere** — no skill, no profile, no
  case — while BI-RADS, TI-RADS, Lung-RADS-style, ASIA and GCS already do.
- **[`docs/architecture/APPLICATION_MAP.md`](docs/architecture/APPLICATION_MAP.md)** — what one
  application consists of (five specialty-specific files, eight that are the pattern), and the
  falsifiable rule it is drawn to: `SPEC-12-04`, a credential and a skill name, no platform change,
  never a LiteLLM key.
- **[`docs/clinical/HOSPITAL_WORKFLOW.md`](docs/clinical/HOSPITAL_WORKFLOW.md)** — arrival to
  follow-up with every node marked: what AI may help with, what it may never do, and whether the
  claim rests on a documented record or an assumption. The consolidated never-list lives here and
  nowhere else.
- **[`docs/design/DESIGN_SYSTEM.md`](docs/design/DESIGN_SYSTEM.md)** and
  **[`docs/design/UX_GUIDE.md`](docs/design/UX_GUIDE.md)** — one language across fourteen
  applications: the ten tokens and the four semantic colours read out of the built screen, the
  keyboard map, the eleven patterns, review-and-approval as one pattern for every department, then
  the screen inventory, role behaviour, cross-application handoff and the three-part shape of every
  failure sentence.
- **[`docs/safety/CLINICAL_SAFETY.md`](docs/safety/CLINICAL_SAFETY.md)** — the difference between
  being tricked and being believed: what each risk rung forces a product to show, what the product
  may and may not claim about a document, six automation-bias obligations, **five gates before an
  application touches a patient**, the contraindications, and an eight-row safety register.
- **[`docs/business/COMMERCIAL_ROADMAP.md`](docs/business/COMMERCIAL_ROADMAP.md)** — six motions,
  which application suits which, and the commercial refusals. Local-first and P14 decide the shape
  before any market talk: no hosted inference, no multi-tenant analytics, no per-study billing.
- **[`docs/VISION-2035.md`](docs/VISION-2035.md)** — the hospital in 2035 as workflow, not
  technology: what disappears, what becomes easier, what becomes newly dangerous (deskilling,
  automation drift, metric gaming), and the three questions that decide whether any of it happened.

#### Decided

- **R4, adopted: an Agent gets no directory.** It is the name for the four authoring files an
  application already ships — prompt, profiles, document shape and ownership, specialty check lists.
  `agents/` was deleted on 2026-10-08 and does not come back; the collision R4 named is resolved by
  describing what exists rather than by adding a layer.
- **R5, adopted — and its cost stated.** The engineering vocabulary moves to *audit issue*, leaving
  *findings* to the clinical sense. The rename is **not** doc-only: `quality.findings` is the
  machine's objection in the same file as the clinician's `findings` section
  (`apps/radiology_copilot/src/futurekind_radiology/report.py:288-306`, `:376`), so it is listed in
  `ROADMAP.md` §10 as a change that needs a feature to carry it, with an interim naming rule.
- **Q5 answered in design: the EHR owns the workflow.** FutureKind owns the request and nothing that
  outlives it — no engine, no timers, no queue, no second store. Four refusals follow, in
  `HOSPITAL_WORKFLOW.md` §6.
- **Q2 and the identifier: a position, not an answer.** The application holds the Patient Context and
  the Gateway never receives one, which is what `submission.py:15` already enforces. The identifier
  *format* stays a clinical decision, and that is why the Timeline is designed only as a read-model.
- **`ROADMAP.md` §12:** the family sequence in four waves, with a promotion rule that puts ratified
  cases and measured checks before any new screen, and an explicit list of what is in no wave.

#### Found, because writing the map meant reading the configuration

- **Not one of the six authorised skills is `critical`, and none can be.** Declaring
  `approval_required` on a critical skill makes every request a `403`; omitting it fails catalogue
  load. So 37 designed critical skills are either unauthorisable or authored down to `high` — the
  radiology skill among them, on an engineer's judgement that has never been confirmed (Q6).
- **Three authorised skills are called by nothing:** `pathology-review`, `clinical-chat` and
  `summarize-document`. A skill a script can reach and a clinician cannot is the platform's own
  ungoverned path, and the map says so with a deletion item attached.
- **The evaluation base covers one department.** All 100 golden cases are imaging (36 CT, 20 US,
  17 XR, 17 MRI, 5 CTA, 3 MG, 1 HRCT, 1 CTP), so thirteen of fourteen applications have no ratified
  evidence at all — which is the real first cost of the family, not code.
- **The ERP is documented for radiology only.** Registration, wards, ICU, theatre, implants,
  discharge, beds, NABH indicators and turnaround time have no named table or screen in this
  repository, so eight applications currently rest on assumption. The two-day fix is the inventory
  walk whose template already exists.
- **The eighteen ungoverned paths now have a taker.** `APPLICATION_MAP.md` §3.1 maps each of the
  ERP's eighteen AI entry points to the application that absorbs it, the refusal that does not, or
  the deletion that should: **eight become an application's job, eight are refused or deleted with a
  named reason, two stay as operator tooling that never belonged on a clinical surface.** The four
  reasons behind the refusals — vision, a job model, speech, non-clinical documents — are each a
  `SPECIFICATION.md` §17 entry, so nothing is left ungoverned by accident.
- **One drifted pointer, fixed:** the substantive-rewrite metric was cited as "§5 of the workflow"
  in `ROADMAP.md`; §5 is API requirements and the content is `RADIOLOGY_WORKFLOW.md:381`, inside S11.
- **A gap named rather than papered over:** the built screen carries five `aria-*`/`role` attributes
  across more than a thousand lines. The colour-plus-word rule holds; the semantics do not, and each
  new application is required to add them instead of copying the deficit.

Suite unchanged and re-verified: **775 tests** (492 Gateway, 255 copilot, 28 dashboard), 0 failures;
`ruff check src tests` clean in both packages; **407 `path:line` citations** now resolving, up from
213 at the start of the night; relative links resolve; no CRLF in `.py` or `.sh`. **Nothing in this
section was measured against a real model or a radiologist** — the first gate in
`CLINICAL_SAFETY.md` §6 is still the one afternoon in `ROADMAP.md` §4.2.

### Genesis Night 2 — the clinician experience (2026-10-08)

The platform was assumed finished and left alone. Everything here is the reporting screen, the
quality engine's severities, the prompt's size and the validation instrument, chosen by asking
of each change whether it takes attention away from the person reading the images.

#### Fixed

- **A locked box holding the machine's own sentence.** `technique` was read-only on the screen
  while `copilot._assemble` lets the model write it whenever the department supplies no
  protocol — so the radiologist could not correct a guess about their own study.
  `report.py::editable_section_keys` is now the single rule: indication always locked (it is
  the referrer's words), technique locked only when the department wrote it, the four prose
  sections always editable, and every locked box says whose words it holds and where to change
  them.
- **`invented_history` refused ordinary comparison prose.** Measured by running the engine over
  eleven sentences a radiologist dictates into a brain report with no prior supplied: four were
  refused wrongly, including "hypointense compared with the surrounding white matter" and "a
  small cortical lesion is poorly resolved on this sequence". The phrase list split in two —
  claims that name a time or the earlier exam still block; the five that cannot be told apart
  by their own spelling advise, with a message asking which one it is. Detection is unchanged
  at 3 of 306 measurable probes, so the check catches nothing either way and refuses less.
- **A 498-character advisory.** `structure_coverage` fired on all eight MRI brain cases in the
  golden set and named 9 to 12 of the protocol's fourteen structures each time. The count stays
  exact; the list stops at six.
- **A refused clipboard write reported success.** Found by running the screen: the status line
  printed "copied to the clipboard" while the browser had rejected the write.
- **Clinical responses were cacheable.** Only the HTML page said `no-store`; `/draft`,
  `/check`, `/review`, `/export`, `/health` and the refusals said nothing, so a department
  proxy or a shared workstation could keep a patient's report — and a 422 naming the check that
  blocked a signature is the artefact most likely to be screenshotted into a ticket.
  `api.py::no_response_is_cacheable` is now one rule for the surface, tested on seven paths.
- **A non-JSON answer surfaced the browser's parse error.** A proxy error page or a dead worker
  produced "Unexpected token 'I'…" on a clinical screen. It now names the status, says nothing
  was filed and says what to try next — and the raw body is never printed, because that is where
  a traceback could carry submitted text.
- **A 422 promised field names it never showed**, and the network message promised a Retry
  button that only appears at page load. Both now say what is actually on the screen.
- **`test-dashboard.py` could report green while running nothing.** Executing it directly only
  defined its functions and exited 0, and `pytest scripts/validation/` collects no file whose
  name has a hyphen, so that also exits 0. It now runs itself, prints `28 of 28`, and treats an
  empty collection as a failure — proven by breaking an assertion and by renaming every test.

#### Changed

- **The reporting screen works the way a radiologist reads.** `Ctrl/⌘+Enter` drafts then signs,
  `Alt+R` re-checks, `Ctrl/⌘+Shift+C` copies the signed report for the RIS, `Ctrl+P` prints it,
  `Alt+N` starts the next study, `Alt+D`/`Alt+M` give the reading room dark and wide modes,
  `Esc` dismisses a failure; tab order skips what cannot be typed in; textareas grow to their
  content; a finding that names a section is a button that focuses it and selects the quoted
  words; the provenance collapses to the one line that is read; and the printout opens the
  audit block the screen hides.
- **Nothing is prefilled with clinical text.** The inputs carried a worked example — somebody's
  headache and somebody's protocol — on a form where a real study could be reported under them.
- **Graceful degradation for the ways AI fails.** A running clock with a Cancel that keeps the
  dictation, the service's state decided on load, per-failure guidance drawn from the codes the
  envelope already carries, a stale failure cleared when a later action succeeds, and a
  signature refusal that leaves the words on the screen and names what refused them.
- **The prompt states each rule once.** 3,097 → 2,894 characters (~723 tokens): the technique
  instruction had been said three times, the indication twice, and the closing line enumerated
  the five sections after the JSON contract had listed them. All twelve rules remain. Version
  `0.3.1`, with `PROMPT_LIBRARY.md` §1 moved verbatim with it.

#### Added

- **`scripts/validation/audit-checks.py` table 4** — per check, how often it fires on a correct
  draft and how often it is the sole reason such a draft cannot be signed. That second number
  is what decides a severity, and it reclassified `dropped_observation`: 0 of 100 faithful
  drafts, so its 86 refusals were the audit corpus's shape, and it stays blocking.
- **`analysis()` in the dashboard** — session summary, time, edit, acceptance, trust, trend,
  reviewer and productivity readings, plus two absolute word counts per study, because every
  existing measure is a ratio and a ratio cannot answer "how many words did I not type today".
  Trust is what the reviewer did after each badge, never a score pretending to know what they
  thought. Running it found three things: a rate of 394 studies an hour off an 18-second
  session, "1 studies", and "0.3 minutes in the room, 4.9 of them on the keyboard" — so a
  session under ten minutes reports no rate, and impossible durations are labelled as
  scripted.
- **`test_screen.py`** — 19 tests that the screen applies the document's rules rather than
  inventing its own, and that its promises about patient text hold: no browser storage, no
  clinical text interpolated into markup, nothing fetched from another machine, a guidance
  entry for every refusal the application can raise, and a positive control on each so an
  absence-check cannot pass vacuously. `render_report` and `write_files` had no test at all
  until now.

Suite at the end of the night: 492 Gateway + 255 copilot + 28 dashboard = 775 tests, 0 failures;
ruff clean; 213 citations and 50 relative links resolving. **Nothing was measured against a real
model or a radiologist** — the prompt's behaviour, the typing reduction and the false-positive
rate on genuine model output all still wait on the afternoon in `ROADMAP.md` §4.2.

### Sprint 11 — the radiologist in the loop (2026-10-08)

Evidence, not features. The Gateway, LiteLLM, policy, routing, the architecture, compose and
the rest of the documentation were left alone, and nothing in this sprint changes a draft, a
prompt or a check. One screen was added so that twenty MRI brain studies can be run past one
radiologist in one afternoon, and the instrument measures the radiologist rather than scoring
the model.

#### Added

- **`scripts/validation/dashboard.py` and `dashboard.html`** — a local session the reviewer
  works in: dictation on the left as the source of truth, the five draft sections editable on
  the right, and every quality finding with **Real problem / Not a problem** buttons, because
  a false-blocking rate this tool inferred from text would be the tool grading itself. It is a
  client of the four endpoints over HTTP behind one origin, and it proxies them rather than
  importing them. Each study records the brief's columns — skill, model alias, generation,
  review and approval seconds, edits, words added and removed, sections edited, checks
  triggered, blocking and advisory findings, final approval — plus redraft requests and
  abandonments, and exports `rows.csv` / `rows.json` (numbers), `metrics.json`, `phrases.csv`
  (report fragments, written outside the repository by the same guard as Sprint 10's export)
  and the end-of-session report with four Top-20 tables: AI mistakes, human edits, prompt
  opportunities, and deterministic checks worth building — the last one populated only where
  the engine said nothing and the reviewer still acted.
- **`scripts/validation/test-dashboard.py`** — 18 tests for the arithmetic, with no server and
  no model: four words typed are four words added, an abandoned study contributes its time and
  nothing else, a document-level advisory is never scored as ignored, and a re-signed study
  counts once.

#### Verified

A scripted session over the live copilot and Gateway against a stand-in model held all 41 of
its hand-computed expectations, and the rendered screen was driven in a browser: five
textareas, the blocking status line, three findings with working verdict buttons, the live
re-check clearing blocks as the text changed, sign-off advancing to the next study, and the
routing line reporting `fk-reasoning · ollama/qwen3:14b`. The in-app browser on this machine
exposes no visible surface, so the screen was verified through its accessibility snapshot and
computed layout, not by eye.

Seven defects the instrument found in itself, all fixed here: a session run twice
double-counted every mean; a phrase filter ran before the word count, so a deleted sentence
scored as zero words removed; an abandoned study was diffed as though it had been edited;
`/report` handed the socket writer a string, truncating the page and hanging the browser; the
alias lookup stopped at the first log line carrying the request id and reported nothing; a
restart lost the phrase evidence the four rankings are built from; and a clicked verdict
rebuilt the whole findings strip, throwing the reviewer's scroll position away twenty times an
afternoon.

**739 tests — 492 Gateway, 229 copilot (both in CI) and 18 on the dashboard
(`scripts/validation/`, not wired into CI).**

### Sprint 10 — measured against reality, as far as this machine allows (2026-10-08)

No architecture, no Gateway, no prompt redesign: the brief was to find out how the product
behaves, and the two things available to measure here were the quality gate itself and the
instrument that will one day measure a model.

#### Added

- **`scripts/validation/audit-checks.py`** — the nine checks run over all 100 authored goldens
  and over each of their 310 `must_not_say` hallucination probes, with no model, no GPU and no
  clinician. Two questions, both answerable today: does the gate refuse a correct report, and
  does it notice a wrong one. Detection is a **paired** baseline→mutation delta — the first
  version of this script was unpaired and reported 87%, which was arithmetic about the
  baseline rather than about the probes.
- **`scripts/validation/run-cases.py`** — the twenty-case harness: `export` the signed MRI
  studies out of the existing studio database, `smoke` one draft to learn throughput before
  committing an afternoon, `run` the machine stages, `session` the radiologist's review with
  the clock running, `report` the table, the summary and the ranking. It is a client of the
  four HTTP endpoints and imports nothing from the application. Clinical text is never written
  to disk — identifiers are dropped on the way out and the export refuses a destination
  inside a git working tree — so the results file holds counts, lengths, ratios and timings
  only. Self-tested against a stand-in model over the live stack; four defects it found in
  itself are fixed in the same commit (an editor opened with no terminal, a study label that
  matched no profile, an epoch integer passed off as a date, and a refusal recorded without
  its reason).

#### Fixed

- **`invented_identifier` read "MR spectroscopy" as *Mr Spectroscopy*.** Its title pattern was
  case-insensitive, so the protocol names of three of the hundred golden reports were privacy
  events. The name form now requires the capitalisation a person's name actually has; the
  identifier form (`MRN`, `accession no`, a six-digit run) stays case-insensitive because that
  is how identifiers are typed. A lower-case "mr smith" is consequently missed — the cheaper
  failure, since an engine that refuses correct studies is a study signed through.
- **`invented_history` refused a differential and a lesion date.** Bare `previously`, `better
  than` and `worse than` were treated as comparisons with an earlier study, so R-11's "fits
  this pattern better than atherosclerosis" and ML-06's "previously healed" fractures both
  blocked with no prior supplied. The phrase list now requires a comparison that *dates* the
  finding: "unchanged", "no interval change" and "as previously described" still block, and a
  test holds each half open.

#### Measured

- Correct golden reports refused by the gate: **5 of 100 before the two fixes above, 1 after**
  (`E-03`, whose 72 mL perfusion mismatch is arithmetic on two dictated volumes — correct, and
  recoverable by rewriting the section, which is the human-downgrade path working as designed).
- `must_not_say` probes newly blocked: **3 of 306 measurable (1%)**, every one by
  `unsupported_measurement`; 269 of the 303 misses raise nothing at all. The nine checks
  enforce traceability of numbers, identities, comparisons, certainty and deletions. They do
  not detect an invented diagnosis, and a tenth check that could is not available: a word-level
  version catches 85% of probes and flags 17 words on every correct report, and a
  disease-name-only version catches 11% while still touching 41 of 100 correct answers — all 41
  of them legitimate naming. The radiologist is the check; the gate's job is to say which
  sentences trace to what was submitted.
- A separate disagreement between the dataset and the gate: `dropped_observation` blocks 87 of
  the 100 expected answers, because `expected_findings` averages 8 words against a `dictated`
  input of 28. The column is a summary of the answer, not a transcription of the dictation. It
  is reported as a property of the dataset and of the fidelity gate together, not as a defect
  of either.

#### Not measured

Real-model latency, draft quality against a real dictation, edit distance, time to final
report, typing reduction, acceptance: there is no Ollama, no LiteLLM and no radiologist on this
machine, and four dev rows are not twenty cases. The procedure that produces those numbers is
`docs/product/ROADMAP.md` §4.2.

**721 tests — 492 Gateway, 229 copilot (46 of them on the quality engine, 6 over real
sockets).**

### Sprint 9 — the first clinical product (2026-10-08)

Not a platform sprint. The Gateway, LiteLLM, policy, routing, the provider interfaces,
compose, the ADRs and the constitution were frozen for this work and none of them changed:
no bug in them blocked the product. Everything here is above the boundary, in
`apps/radiology_copilot/`, and it is the first thing in this repository a clinician can use.

#### Added

- **`quality.py` — nine deterministic checks** over a draft, each a comparison of the draft's
  text with the text the clinician submitted: `dropped_observation`,
  `unsupported_measurement`, `invented_history`, `unsupported_certainty`,
  `unsupported_absence`, `format_breach`, `invented_identifier`,
  `self_reported_confidence`, `structure_coverage`. No model grades the model, no thresholds,
  no learned score — the same dictation and the same draft always give the same verdict, which
  is the only kind of rule a department can audit afterwards. The module's own docstring
  states the limit it cannot escape: every check compares words to words, and none of them
  has seen the images.
- **`profiles.py` — the MRI brain study profile**: fourteen structures with the synonyms that
  count as mentioning them, and the negatives a brain study cannot support. One profile,
  because five more would be a guess about five departments. A profile can only ever raise an
  advisory finding, never block a report for a structure nobody described.
- **`RadiologyReport.follow_up` and `RadiologyReport.confidence`** in the document itself.
  Follow-up is kept apart from recommendations because they are different acts — what to do
  now, and when to look again — and an interval buried in a paragraph of referrals is an
  interval nobody books. Confidence is computed from the checks, the provenance and the
  completeness of the input, and a model that returns its own `confidence` key has it named
  and withheld.
- **Previous reports as input** (`submission.py`): up to five, each under 2 000 characters,
  under 6 000 in total, each needing its date. A comparison in the draft is only legitimate
  against one of these, and the absence of them is stated to the model rather than left
  silent.
- **`static/index.html`, served at `GET /`** — the screen a radiologist works in: the
  submission and its priors on the left, the six editable sections in the middle, the quality
  findings, confidence and provenance on the right. One static file inside the package: no
  CDN, no framework, no font fetched from anywhere, no localStorage and no session, and it
  calls the same four endpoints an integration would.
- **`POST /check`** — the same nine checks over the text as it stands, with no Gateway call
  and nothing stored, so the findings move while the clinician types.
- `tests/test_quality.py` (45 tests): every check proved caught *and* the innocent version of
  the same sentence proved not caught; three MRI brain golden fixtures derived from the
  golden set's own dictations; malformed-input cases (six priors, oversized priors, a prior
  with no date, a `patient_name` field); determinism; the plan-versus-assertive severity
  split; and one draft that raises all nine checks in the documented order.

#### Changed

- **Sign-off is now a gate, not a formality.** `POST /review` requires the submission the
  draft was made from, re-runs the nine checks over the amended text, and refuses a signature
  while any finding is `block` (`422`, carrying check names and section names only — never the
  clinical text). A section the clinician rewrote has its findings downgraded to advisory:
  the image, not the dictation, is their source, and this application does not overrule the
  person who owns the report. Nothing is locked — a corrected sentence clears the block, a
  returned draft needs no submission, and a signed report can still be amended and re-exported.
- **Prompt `radiology-report-draft/0.3.0`.** The same running prompt, versioned up rather than
  forked: every number must appear in the observations or a supplied prior; no comparison
  unless the prior is in the request; a hedged finding stays hedged; follow-up apart from
  recommendations; `"None."` in a section with nothing to say. `docs/product/PROMPT_LIBRARY.md`
  §1 carries the new text verbatim, with the enforcement of each clause mapped to the check or
  the parse error that backs it.
- **A measurement is compared as a whole number, not as a substring.** `"9" in "19 mm"` is
  true, so a draft that shrank a dictated 19 mm midline shift to 9 mm passed
  `unsupported_measurement` — the near miss, right digit and wrong number, which is exactly
  the error the golden set's `must_not_say` column weighs most. Numbers are tokenised on both
  sides now, and a digit inside a sequence name (`T2`) grounds nothing. The residue the rule
  leaves is written down rather than smoothed over: a bare age or date in the submitted text
  still grounds a drafted size, and the test that says so explains why tightening it further
  would refuse correct reports.
- The quality pass and the confidence grade render in **all three export formats**, so a
  printed report states what was checked on it — the only part of this design a reader who
  never opens the API can verify.
- The product documents now say what is built instead of what was designed:
  `RADIOLOGY_WORKFLOW.md` §S4–S6 and its failure catalogue (F19–F23 are the failures code can
  now catch), `UI_UX.md` §6 with the interim screen recorded as interim, `ROADMAP.md` §3 with
  the plan that was not followed kept visible rather than overwritten, and
  `docs/product/README.md`'s summary numbers.

#### Verified

Measured on this tree, counted from `--junit-xml` rather than from a summary line:
**717 tests — 492 Gateway, 225 copilot (45 of them on the quality engine, 6 over real
sockets) — zero failures, zero errors, zero skips.** ruff clean on both packages; 213
in-tree `path:line` citations resolve; 50 relative documentation links resolve; no CRLF in
any `.sh` or `.py`; no zero-byte tracked file; no infrastructure identifier in any tracked
or staged file.

The workflow was then walked in a browser against a running Gateway and a stub LiteLLM —
two real processes, real sockets, nothing mocked in the application:

* Draft: `200`, six editable sections, `quality` with one advisory `structure_coverage`
  finding, `confidence` = `review-carefully`, Approve **enabled** (an advisory does not
  stop a signature), provenance naming `ollama/qwen3:14b`, prompt `0.3.0`, profile
  "MRI brain", `Compared with: no priors`.
* One invented sentence typed into Findings — *"A 27 mm right frontal lesion is present,
  unchanged from the MRI of 4 months ago"*: `unsupported_measurement` and
  `invented_history` both **block**, `not-safe-to-sign`, the Approve control disabled, the
  banner changed, and Return-for-correction left enabled.
* `POST /review` on the same document: `422` with
  `{"blocking": [{"check": "unsupported_measurement", "section": "findings"},
  {"check": "invented_history", "section": null}], "sections": ["findings"]}` — and the
  response body contains neither `27` nor the words "frontal lesion".
* The words corrected: the block cleared, the report signed, and the text export carried
  the signed banner, FOLLOW-UP, the quality findings and the confidence grade.
* With a previous report supplied, the same comparison sentence passed and provenance
  printed `Compared with: 2026-06-02 — MRI MRI BRAIN WITH CONTRAST`.

**Not measured here:** any real model on any hospital hardware. The answering side of that
last run was a stub, and it is the only honest reason the draft came back in 5 ms.

#### What this sprint did not solve

No real-model latency number — the only timing in this repository is still 27–30 ms against a
stub. No ERP integration, no PACS modification, no clinician authentication (the signer's name
is typed, which is the F-A defect and it is unchanged), no audit retention, no streaming. The
golden dataset is still `ratified: pending` on all 100 cases. The checks read text, so a
plausible finding nobody dictated is still invisible, and `quality.scope` says so on the screen
rather than leaving it to a README.

### Sprint 8 — release readiness (2026-10-08)

No feature, no architecture change: every entry below closes a blocker raised by the
engineering review before the first public push.

#### Changed

- **Security — the inventory is no longer public.** `GET /models` and
  `GET /models/{capability}` now require the credential `POST /chat` has always
  required; `GET /metrics` likewise, because its label values name providers and
  model ids. `GET /health` and `GET /health/ready` stay reachable without a key — a
  container runtime cannot hold one — and publish verdicts only: no catalogue path,
  no provider names, no upstream error text. Closes constitution register rows 1–3.
- **Security — `.env.example` ships no credential and no host.** Placeholder secrets
  become `<generated: openssl rand -hex 32>` with the command stated; the real LAN
  addresses of the reference clinic are gone, and the unread `OLLAMA_SECONDARY` with
  them.
- **Deployment — one compose tree.** `compose/compose.core.yaml` and its
  empty-alias LiteLLM config are deleted; `compose.yaml` is the only file describing
  an installation.
- **Version — one declaration per artefact.** The root `VERSION` file is deleted, the
  platform manifest holds a release-line name and no number, and
  `[tool.hatch.version]` reads each package's `__init__.py`, which is the number the
  wheel, `GET /health` and the served OpenAPI document all report.
- **Claims matched to the system.** OpenTelemetry tracing, Prometheus, Grafana,
  Langfuse and cost/budget tracking are marked planned or absent in
  `core/gateway/README.md`, `configs/futurekind.yaml` and `docs/ARCHITECTURE.md`,
  which now opens with a table of which boxes are built.
- `docs/adr/adr/ADR-0001-Local-First-AI.md` flattened to `docs/adr/`, repairing the
  two architecture links that pointed through the doubled segment.
- Skill counts corrected to the six authorised stanzas; the 121-skill design
  catalogue remains design.

#### Removed

- The placeholder clinical layer: 34 files under `genesis/` and `agents/` (14 of them
  zero bytes, the rest keyboard noise, five named `New Text Document.txt`). The
  clinical doctrine they were meant to hold is scheduled work, not an empty file.
- `core/gateway/openapi.yaml`, a hand-written four-path stub that contradicted the
  served `/openapi.json`.
- `services/.gitignore` (a copy of the root file) and the empty directories that
  advertised unbuilt components.

#### Added

- `LICENSE` (Apache-2.0, matching what both `pyproject.toml` files declared),
  `README.md` and `SECURITY.md` — the front door and the disclosure channel, both of
  which were previously empty.
- CI (`.github/workflows/ci.yml`): both Python suites, both lints, YAML and compose
  validation, the alias-contract check between the two catalogue files, relative-link
  validation, and a repository-hygiene gate for the identifiers and placeholder files
  this pass removed.
- Issue templates for bugs and skill proposals, a pull-request template, and an
  issue-form config that routes security reports to private disclosure.
- `py.typed` is unchanged; no static type checker is configured for either package,
  and the README says so rather than leaving it implied.

#### Verified

492 Gateway tests and 160 copilot tests, zero failures and zero skips; ruff clean on
both packages; 54 relative documentation links resolve; no zero-byte or
placeholder-path tracked file; no private address, hostname or credential-shaped
string in any shipped file. `compose.yaml` and `core/gateway/Dockerfile` remain
**parse-verified only** — no container daemon was available on any machine used for
this work, so the compose path has still never been booted.

## [0.1.0-genesis] - 2026-08-03

### Added
- Initial repository
- Project vision
- Version file
