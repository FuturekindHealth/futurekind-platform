# Prompt Library — versioned prompts by specialty

**Deliverable 4 of Genesis Night. Status: one prompt in this file runs in code; five are
designs.** Say which is which, or the file becomes a list of intentions.

| Specialty | Prompt id | Version | Where it lives | Runs today |
| --- | --- | --- | --- | --- |
| Radiology | `radiology-report-draft` | `0.2.0` | `apps/radiology_copilot/src/futurekind_radiology/prompt.py:26,33-62` | **Yes** |
| Pathology | `pathology-report-draft` | `0.1.0` | design only | No |
| Acute medicine | `clinical-summary-draft` | `0.1.0` | design only | No |
| Emergency | `ed-impression-draft` | `0.1.0` | design only | No |
| Surgical | `operative-note-draft` | `0.1.0` | design only | No |
| Paediatric | `paediatric-note-draft` | `0.1.0` | design only | No |

## 0. The seven clauses every prompt in this library carries

Repeated in all six because they are not style — each one closes a hole a real run or a
real system found. A new prompt that drops one needs an ADR, not a review comment.

1. **Authorship denial.** "You are not the author of the report. A named clinician reviews
   every section." Stated first because a model that believes it is the author writes the
   way an author writes — conclusively.
2. **No invention.** No finding, measurement, sign or diagnosis that the supplied text
   does not support. (Radiology, live.)
3. **No dropping.** Every dictated observation must be carried into the findings section.
   Sprint 7 added this after the parse-and-read tests showed a model compressing a
   six-organ dictation into three — silently, and *correctly-sounding*. Dropping is the
   mirror of inventing and is more common.
4. **Gap declaration.** Where the input is incomplete, write it in the section that owns
   it (`"Technique not provided."`, `"None."`) instead of filling the gap. An empty section
   is refused by the parser, so this clause is also what stops a 502.
5. **The referrer's question is not yours.** Never restate, summarise or reinterpret the
   clinical indication. This is the live defect: prompt `0.1.x` asked the model for five
   sections *including* the indication, and a live run in Sprint 7 showed it rewriting the
   referrer's question into its own words. The fix was structural, not verbal — the
   indication is taken from the submission and is not a model-owned key
   (`report.py::MODEL_SECTION_KEYS` is four, not five).
6. **No identifiers.** Never invent a name, number, MRN, UHID or accession. The
   application supplies identifiers in metadata; the model never sees and never writes
   them (workflow D3).
7. **One machine-readable object, nothing outside it.** No preamble, no prose after the
   closing brace, no markdown. This is a clinical requirement dressed as a parsing one: a
   flowing-prose answer cannot be reviewed section by section, and section-by-section
   review is the only thing standing between a draft and a signature.

**And one thing the library does not yet have.** There is no house-style document. The
trees that were going to hold it — `genesis/report_style.md`,
`agents/radiology/style-guide.md` — were zero-byte files and files containing the letters
`ai`, and were deleted on 2026-10-08 (see `ROADMAP.md` §10). `prompt.py:9-13` says so
plainly: there is no house style to encode.
There is therefore **no house style anywhere in this repository** — no institutional
voice, no measurement vocabulary, no department convention about "no opinion in the
findings section" versus "opinion allowed". These prompts are currently the *only* style
authority, which is why the clauses above are so few: they are the minimum that makes a
draft checkable, not a description of how CARE Diagnostics writes a report. Writing the
style guide is a clinician's task and it is on the roadmap.

---

## 1. Radiology — `radiology-report-draft/0.2.0` (running)

**Purpose.** Turn one reporting clinician's dictated observations for one imaging study
into a sectioned draft a radiologist can review line by line and sign.

**Skill and policy.** `radiology-report` → capability `reasoning` → alias `fk-reasoning` →
`ollama/qwen3:14b`. Policy `{clinical_risk: high, approval_required: false,
audit_required: true, allow_downgrade: false}`, ceiling 1024 completion tokens, 90 s
timeout (`core/gateway/models.yaml:54-66`).

**System prompt** (verbatim from `prompt.py:33-62`; `{sections}` is filled with the four
JSON keys at call time):

```text
You are assisting a radiologist draft a report for one imaging study.

You are not the author of the report. A named clinician reviews every section
before it is used, and a statement you add that is not in the observations below
could reach a patient. So:

- Write only what the supplied observations support. Do not add a finding, a
  measurement, a sign or a diagnosis that was not described.
- Carry every observation the clinician dictated into your findings section, in
  report prose. Dropping one is as dangerous as inventing one.
- If the observations are incomplete, negative or uncertain, say so in the
  section that owns it rather than filling the gap.
- If the technique was not supplied, write "Technique not provided." in the
  technique section. Do not name a scanner, a sequence or a contrast protocol
  that was not given.
- The clinical indication has already been recorded by the clinician. Do not
  restate, summarise or reinterpret it.
- Do not invent a patient name, number or any identifier that is not supplied.
- Use plain clinical prose inside each section. No markdown, no bullet symbols,
  no headings.
- Write the impression as the clinical conclusion, not a restatement of the
  findings.
- If there is genuinely nothing to recommend, write "None." in the
  recommendations section. Do not leave it empty and do not omit it.

Reply with one JSON object and nothing outside it: no preamble, no explanation
after the closing brace. It must contain exactly these four keys, each with a
string value:

{sections}
```

**User turn** (`prompt.py:65-81`): `Study`, `Modality`, the recorded `Clinical indication`
labelled *"already recorded — context for you, not yours to rewrite"*, `Technique` (or the
literal `Not supplied — write "Technique not provided."`), and the dictated observations
under the header *"Observations dictated by the reporting clinician"*.

**Constraints the application enforces, not just asks for.** A prompt instruction is a
hope; these are code, and this list is the honest boundary between the two:

| Rule | Enforcement |
| --- | --- |
| Exactly four authored sections | `parse_model_answer` reports `missing_sections`; a draft with a missing key is not offered for signing |
| Extra keys are not merged | recorded in `metadata.extra_sections` and discarded |
| Section values are strings or lists of strings | numbers and objects are refused (`_section_text`) |
| No truncation | `finish_reason == "length"` → `ReportTruncatedError`; a cut-off impression is the most dangerous artefact the product can make |
| Indication is not model-owned | taken from the submission in `_assemble`, never from the answer |
| A supplied technique beats the model's | `technique_from` records `department` or `model`, and the department line wins |
| Governance precedes parsing | `_check_governance` runs *before* `_parse` — an unaudited or degraded answer is refused even if its JSON is perfect |

**Output schema.**

```json
{ "technique": "string", "findings": "string", "impression": "string", "recommendations": "string" }
```

**Known failure modes** (all observed here or designed against):

| # | Failure | Evidence / status |
| --- | --- | --- |
| R-1 | Rewrites the clinical indication | **Observed live in Sprint 7.** Fixed structurally, clause 5 remains as a second line of defence |
| R-2 | Answers in prose, or adds "Here is the report:" before the brace | fixtures `prose_answer.txt`, `wrapped_answer.txt`; parser refuses and the UI shows the reason |
| R-3 | Drops a dictated organ to tighten the prose | observed in parsing tests; clause 3 plus the Fidelity score in `GOLDEN_DATASET.yaml` |
| R-4 | Names a plausible scanner/protocol when technique was not supplied | clause 4; `N-04`, `N-11` probe it |
| R-5 | States an absence the study cannot exclude ("no pulmonary embolism") | the whole `must_not_say` column; strongest in CTPA and MRI cases |
| R-6 | Runs out of tokens mid-impression | `max_completion_tokens: 1024`; F4 in the workflow catalogue |
| R-7 | Invents a measurement (a 14 mm nodule where the dictation said "small") | the highest-weighted `must_not_say` pattern; a clinician must type every number |

**Evaluation criteria.** The six-step rubric in `GOLDEN_DATASET.yaml` (Structure, Safety,
Fidelity, Conclusion, Action, Latency), against 100 cases; thresholds proposed as
emergency 100% safety/structure and ≥95% conclusion, medicolegal 100% safety and fidelity.
**Unrun.** The set is authored but `ratified: pending` on all 100, and the only measurement
taken so far is 27–30 ms against a stub LiteLLM, not a model.

---

## 2. Pathology — `pathology-report-draft/0.1.0` (design)

**Purpose.** Turn a pathologist's dictated macroscopic and microscopic description into a
report whose diagnosis line and margin status are separately checkable.

**Skill.** `pathology-review` — the **only other clinical skill authorised in
`models.yaml` today** (`clinical_risk: high`, `audit_required: true`), so this prompt has a
place to run as soon as it is written.

**System prompt.**

```text
You are assisting a histopathologist draft a report for one specimen.

You are not the author. A named pathologist signs this report, and a diagnosis you
state becomes the treatment decision someone else makes. So:

- Report only what the supplied macroscopic and microscopic description supports.
- Never output a malignant diagnosis from a description that does not describe
  malignancy. If the description is suspicious but not diagnostic, the diagnosis
  line says what it is and what is required to settle it.
- Carry every measurement, margin and node count from the dictation exactly. A
  node count you change is a stage you change.
- If a margin, a depth, a grade or a count is not in the description, write
  "not stated" for that element. Do not infer it from what is usual.
- Special studies, immunohistochemistry and molecular results are reported as
  given, or stated as not performed. Never report a stain you were not given.
- The clinical history is context supplied by the clinician. Do not restate it and
  do not use it to close a diagnostic gap.
- Do not name a patient, a block number, a slide number or an accession that was
  not supplied.

Reply with one JSON object and nothing outside it:

{
  "specimen": "...",
  "macroscopy": "...",
  "microscopy": "...",
  "diagnosis": "...",
  "margin_status": "...",
  "staging_elements": { "T": "...", "N": "...", "M": "..." },
  "recommendations": "..."
}
```

**Constraints, and where they must be enforced in code.** `staging_elements` is the
difference between this and a prose report: a team can check `pN1a` against "2 of 18
nodes" and cannot check a paragraph. So the application — not the prompt — must refuse a
`stage_group` assembled while any element is `not stated`, and must refuse a
`diagnosis` line containing a grade or stage whose components are absent. The node-count
thresholds (N1a 1–3, N1b 4–6) belong in configuration the clinician owns, not in a
prompt, because editions change and a prompt edit is invisible.

**Output schema.** the seven keys above; `staging_elements` values are `string` and may be
`"not stated"`; `margin_status` is one of `clear | close | involved | not stated`.

**Known failure modes.**

| # | Failure | Why it is the one that matters |
| --- | --- | --- |
| P-1 | Grades a tumour the description did not grade | grade is a treatment input |
| P-2 | Reports a margin as clear because the specimen "usually" has one | the classic inference-to-fact |
| P-3 | Rounds a node count or re-derives a total | changes stage group silently |
| P-4 | Adds immunohistochemistry the block never had | a result nobody ran |
| P-5 | Converts " favour reactive" into "reactive" | removes the uncertainty the report exists to carry |
| P-6 | Restates the clinical history into the diagnosis line | the same defect as R-1, in a higher-stakes field |

**Evaluation criteria.** No pathology case exists in `GOLDEN_DATASET.yaml` — it is 100
*imaging* studies. This prompt cannot be scored until a pathology block is added (expected
10–15 cases, drafted from reported specimens, ratified by a pathologist). That is a
Roadmap item and contradiction #11 in the sprint report, not a footnote.

---

## 3. Acute medicine — `clinical-summary-draft/0.1.0` (design)

**Purpose.** Produce the inter-impression / shift-handover summary of one admission, and
name the actions a human still owns.

**Skill.** `clinical-summary` (high risk) with `ward-round-daily-note` (moderate) as the
lighter variant of the same prompt skeleton.

**System prompt.**

```text
You are assisting a hospital doctor draft a summary of one admission for handover.

You are not the decision-maker. A named doctor reads this summary and is responsible
for the patient. So:

- Use only the problems, treatments and results supplied. Do not add a diagnosis the
  data does not contain, and do not remove a problem because it looks minor.
- Every unresolved item stays unresolved. A pending culture is written as pending.
  Do not describe a likely organism.
- Write the plan by problem. Do not merge problems into a narrative.
- Any action that must happen in the next 24 hours goes in `due_within_24h` with the
  data that makes it due. If you are unsure whether an action is due, put it in
  `needs_human_decision` with the question, not in the plan.
- Never write a dose, a rate or a drug choice as a recommendation. Name the decision
  and who owns it.
- Do not restate the referral question. Do not invent identifiers.
- If nothing is due, `due_within_24h` is an empty array. Never omit the key.

Reply with one JSON object and nothing outside it:

{
  "problems": [ { "problem": "...", "status": "...", "active_plan": "...", "evidence": "..." } ],
  "due_within_24h": [ { "action": "...", "because": "...", "owner": "..." } ],
  "needs_human_decision": [ { "question": "...", "data_available": "...", "data_missing": "..." } ],
  "escalation": "...",
  "not_covered": "..."
}
```

**Constraints.** The `owner` field on every due action is the product requirement: a
handover item with no owner is an item nobody performs, and P3 says a named human owns
every clinical statement. `needs_human_decision` exists so uncertainty has somewhere to
live other than the plan.

**Known failure modes.** (M-1) inventing a source of sepsis because one is common;
(M-2) dropping a community problem — epilepsy on the GP list vanishing is the
`problem-list-reconciliation` case; (M-3) writing "continue current management" as an
action; (M-4) converting a rising creatinine trend into a resolved statement; (M-5)
recommending antibiotics with a dose; (M-6) a summary that reads as discharge-ready when
cultures are pending.

**Evaluation criteria.** Structure and Safety as for radiology; Fidelity is *problem
coverage* — the number of supplied problems appearing, and the number appearing that were
not supplied, scored both ways. Action is measured by whether every 24-hour item carries
an owner. No golden cases exist for this specialty yet.

---

## 4. Emergency — `ed-impression-draft/0.1.0` (design)

**Purpose.** Structure an emergency-department assessment into an impression with an
explicit disposition question, for a clinician to accept, correct or ignore.

**Skill.** `ed-triage-note`, `ed-chest-pain-pathway`, `ed-paediatric-fever-pathway` — one
prompt with per-pathway fragments held in configuration, not three prompts, because three
copies of the safety clauses drift.

**System prompt.**

```text
You are assisting an emergency clinician form an impression and a disposition question.

You are not the clinician. A named clinician decides disposition, and a decision you
make in text will be read as if it were made. So:

- Work only from the observations, scores and results supplied. Do not add an
  examination finding that was not described.
- State a score only with its components. If a score is given without components,
  report it as given and put the components you were not told in `missing`.
- Trend numbers are the finding. If two values of the same analyte were supplied,
  name the direction and both values. Never report a single value as a trend.
- Disposition is a question you put to the clinician, with the data that decides it.
  Do not write "discharge" or "admit" as a decision.
- Never give a drug, a dose, or a time to re-dose.
- The time-critical possibilities are listed as possibilities with the test that
  settles each one. Do not exclude a diagnosis because the picture is usual.
- "Not documented" is not "absent". Where a red flag cannot be assessed from the
  data, say which data is missing.
- Do not restate the referral question. Do not invent identifiers or arrival times.

Reply with one JSON object and nothing outside it:

{
  "impression": "...",
  "supporting": [ "..." ],
  "against": [ "..." ],
  "time_critical_possibilities": [ { "possibility": "...", "settled_by": "...", "currently": "..."} ],
  "disposition_question": "...",
  "missing": [ "..." ],
  "safety_net": [ "..." ]
}
```

**Constraints.** `time_critical_possibilities` is required and may be an empty array only
when the supplied data excludes them, with the excluding test named. `safety_net` is the
only field a patient will ever see (via `ed-discharge-instructions`) and it is written in
the same document so the two cannot diverge.

**Known failure modes.** (E-1) a single troponin reported as "rising"; (E-2) HEART score
accepted without components (the B2 arithmetic rule, in a setting where it kills); (E-3)
"reassuring" as an impression; (E-4) excluding PE from a normal D-dimer when the pretest
probability was high; (E-5) naming a paediatric fever "viral" at 42 days old; (E-6) a
safety net that omits the return-immediately list.

**Evaluation criteria.** Emergency cases in `GOLDEN_DATASET.yaml` are 20 of 100 and the
threshold is already written: **100% safety, 100% structure, ≥95% conclusion.** For this
specialty add a rule the radiology rubric does not have: an answer that names a
disposition (admit/discharge) rather than a disposition *question* fails the case
outright, whatever else it got right.

---

## 5. Surgical — `operative-note-draft/0.1.0` (design)

**Purpose.** Turn a surgeon's dictation of a procedure into an operative note in the
department's field order, with every unspoken field visibly empty.

**Skill.** `operative-note-draft` (high risk), with `post-operative-instruction`
(moderate) and `procedural-sedation-record` as companions.

**System prompt.**

```text
You are assisting a surgeon turn a dictated procedure into an operative note.

The note is a legal record of what was done. A model that completes a sentence the
surgeon did not dictate creates a record of an act that may not have happened. So:

- Transcribe and structure. Do not add a step, a finding, a device, an implant or a
  specimen that was not dictated.
- Fields the dictation does not cover are written "not stated". Never infer blood
  loss, tourniquet time, antibiotic prophylaxis, swabs, counts, or complications
  from what is typical for the procedure.
- Preserve the surgeon's own words for findings and for the critical steps. Do not
  improve the prose of a description.
- If the dictation and the stated procedure disagree, do not resolve it — write the
  disagreement into `inconsistencies` for the surgeon to settle before signing.
- Never write an indication you were not told, and never restate the one supplied.
- Do not add a postoperative plan. That is a different document with a different
  author.
- Do not invent identifiers, times, or the names of assistants.

Reply with one JSON object and nothing outside it:

{
  "procedure": "...",
  "indication": "...",
  "approach": "...",
  "findings": "...",
  "procedure_steps": "...",
  "specimens": "...",
  "blood_loss": "...",
  "complications": "...",
  "implants_devices": "...",
  "closure": "...",
  "inconsistencies": [ "..." ]
}
```

**Constraints.** `indication` is filled by the application from the booking, never by the
model (the radiology lesson, applied). `blood_loss`, `specimens` and `complications` may
hold `"not stated"`, and the UI must render that as an unfilled field the surgeon must
acknowledge — an operative note is the one document where a plausible default is a false
statement. `inconsistencies` must block signing until resolved.

**Known failure modes.** (S-1) a haemorrhage appended because the procedure was for
bleeding; (S-2) "no complications" where the dictation was silent; (S-3) an implant size
completed from a brand's usual range; (S-4) swabs/counts asserted present; (S-5) the
technique of a named assistant inferred from a training scenario; (S-6) a findings
paragraph rewritten into cleaner prose, losing the surgeon's hedging.

**Evaluation criteria.** Fidelity here is *verbatim fidelity*, graded tighter than
radiology: any added operative act, device or count is an automatic fail regardless of
clinical plausibility. Structure and Safety as elsewhere. No golden cases exist; the right
source is 20 dictated notes already in the ERP with their signed originals.

---

## 6. Paediatric — `paediatric-note-draft/0.1.0` (design)

**Purpose.** Draft paediatric and neonatal documents where the age, the weight and the
threshold all change with a number the model must never estimate.

**Skill.** `neonatal-delivery-transition-note` (critical), `paediatric-growth-note`,
`paediatric-asthma-action-plan`, `immunisation-catchup-plan`.

**System prompt.**

```text
You are assisting a clinician draft a paediatric or neonatal document.

Children are not small adults: the thresholds that make a finding dangerous are
computed from age, gestation and weight. So:

- Every threshold you apply, state the age or gestation it was applied to.
- Never estimate a weight, a gestation, an age in days, or a centile. If it is not
  supplied, it goes in `missing` and any conclusion that depends on it is withheld.
- A drug, dose or route is never recommended. If the standard of care involves one,
  name the decision and the person who makes it.
- Do not convert a narrative description into a numeric score.
  "Drowsy, few words" is not V3.
- For a neonate in the first 90 days, fever is a management question regardless of
  how well the child looks. Say so if the supplied data is in that window.
- Never report reassurance about safeguarding, non-accidental injury or a
  bruising pattern from the data given. If the pattern is unusual, describe it and
  name who must see it.
- Where a parent or carer will read the output, it is a separate field with plain
  language and a return-immediately list — never a shortened version of the clinical
  text.
- Do not restate the referral question. Do not invent identifiers, dates of birth or
  a hospital number.

Reply with one JSON object and nothing outside it:

{
  "age_context": "...",
  "findings": "...",
  "thresholds_applied": [ { "threshold": "...", "applied_to": "..." } ],
  "impression": "...",
  "actions_for_clinician": [ "..." ],
  "missing": [ "..." ],
  "family_facing": "..."
}
```

**Constraints.** `thresholds_applied` is required and non-empty unless the document needs
no threshold; it is the field that makes a paediatric answer auditable, because "septic
screen" is only right relative to a stated age. `family_facing` is separated precisely so
a screen can render the plain-language text without ever rendering the clinical one to a
parent.

**Known failure modes.** (A-1) a GCS verbal component inferred from a description (the
B2 case, in a child); (A-2) fever thresholds applied at the wrong day-count; (A-3) a
centile asserted for a single weight measurement with no prior; (A-4) bruising described
as "innocent" — the model's most dangerous instinct in paediatrics; (A-5) an immunisation
interval invented rather than read from the supplied calendar; (A-6) a family summary that
silently deletes a red flag to avoid alarming a parent.

**Evaluation criteria.** Paediatric cases *do* exist in the golden set — the skeletal
survey for non-accidental injury, a burn with depth assessment, metabolic and ciliary
disease on MRI — but all of them are imaging studies. There is no neonatal transition
case, no dosing case and no growth-chart case, and `GOLDEN_DATASET.yaml` already lists
"paediatric dosing and low-dose protocols" among its own stated gaps at the foot of the
file. The safeguarding cases in particular must be reviewed and ratified by a clinician,
not left as an engineer's guess about which bruising pattern is suspicious.

---

## 7. Versioning and change protocol

A prompt is clinical configuration. It is versioned like an artefact and it changes like
a decision.

**Identifier.** `<skill-purpose>/<semver>`, e.g. `radiology-report-draft/0.2.0`. Stored on
every generated document (`RadiologyReport.metadata.prompt_version`), so a report says
which words produced it — the same obligation as model provenance under P8, and the reason
the constant lives next to the text rather than in a config file someone can edit without
changing what was said.

**Bump rules.**

| Change | Bump | Requires |
| --- | --- | --- |
| Wording of an existing clause | patch | golden re-run; document the sentence changed |
| A clause added or removed | **minor** | golden re-run **and** a note in this file stating which failure mode it closes |
| A section key added, renamed or dropped | **major** | an ADR. It changes what a signed report contains |
| Anything relaxing a prohibition | **major** | an ADR naming the principle in conflict, per `docs/CONSTITUTION.md` §6. "It was inconvenient" is not an input |

**Three things a prompt must never be.**

1. **Not the enforcement point.** Clause text is a request; `copilot.py` and `report.py`
   are the enforcement. Any rule that matters gets a test, and if it cannot have a test it
   is a hope and must be labelled as one. The table in §1 is exactly that mapping.
2. **Not configurable by a caller.** A client may not send a system prompt, override the
   version, or name a model (`422`, ADR-0002 rule 1). The one legitimate steer is
   `extra_instructions` on a redraft — appended to the *system* turn by the reviewing
   clinician, recorded, and available only in a human-initiated re-draft (`prompt.py:96-101`).
   Everything else about the prompt is chosen by the deployment, never the request.
3. **Not a place for patient data.** The user turn carries the dictated observations
   because that is the task, and the submission schema has no identifier field at all
   (`submission.py` — deliberate, and DOMAIN_MODEL Q2 answered by absence). Prompt text is
   never written to a log (`docs/CONSTITUTION.md` P10). The Gateway's `skill_audit` line
   (`core/gateway/src/futurekind_gateway/service.py:335-355`) carries `request_id`, `skill`,
   `capability`, `clinical_risk`, `approval_required`, `alias`, `answered`, `provider`,
   `model` and `downgrades_allowed` — and its own comment states what is deliberately
   absent: *"Deliberately absent: prompt and completion text."* A prompt version number may
   be logged; a prompt body may not.

**What is missing from this library, stated as work.**

- No house style exists (the `genesis/` style file was empty and is deleted), so none of these prompts encodes
  how this hospital writes a report. Six prompts written by an engineer are a placeholder
  for a clinician's style guide.
- Only one of six has ever been executed. The other five have no measured latency, no
  token-budget evidence, and their 1024-token ceilings are inherited guesses.
- Only radiology has golden cases; pathology, medicine, emergency, surgery and paediatrics
  have none, so five of these six prompts cannot currently be *failed*, which means they
  cannot be passed either.
- Nothing here addresses **prompt injection** beyond clause-level instructions. That is a
  threat-model question (`docs/security/THREAT_MODEL.md` §3), not a wording question, and a
  prompt cannot solve it.
