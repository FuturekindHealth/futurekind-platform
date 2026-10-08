# FutureKind Application Map

**Owns:** which applications exist, what each one calls, what each one reads and writes, where
each one's record lives, and what has to change in configuration for a new one to appear.
**Does not own:** the words (`../DOMAIN_MODEL.md`), the product family and its prioritisation
(`../product/PRODUCT_BIBLE.md`), individual skills (`../product/SKILL_LIBRARY.yaml`), screens
(`../product/UI_UX.md`, `../design/UX_GUIDE.md`), platform requirements (`../SPECIFICATION.md`),
sequence (`../product/ROADMAP.md`).
**Status:** one application built and running; thirteen mapped.

---

## 1. The rule this map is drawn to

`SPEC-12-04` (`../SPECIFICATION.md:668-669`) is the whole contract, and it is short enough to
quote:

> **SPEC-12-04: a new Application.** Obtain a credential, name a skill. SHALL NOT require a
> platform change, and SHALL NOT be given a LiteLLM key.

So an application is added with three things and nothing else:

| | What it is | Where it lives |
| --- | --- | --- |
| 1 | **A credential** — the Gateway API key the application sends as `Authorization: Bearer` | Its own environment, never in a repository. `FK_RADIOLOGY_GATEWAY_API_KEY` is the built example (`apps/radiology_copilot/README.md:202`) |
| 2 | **A skill name** in every request | Its client module — `gateway.py` in the built example |
| 3 | **A document shape** it owns, and the checks it runs over that document | Its `report.py` and `quality.py` |

Two consequences that are easy to violate while trying to be helpful:

- **An application may not add a platform field to carry its own need.** `SPEC-12-06`
  (`../SPECIFICATION.md:675-677`) makes a new public request field an ADR first. Fourteen
  applications will want fourteen fields; the platform has refused every one so far and the
  reason is recorded in `ADR-0002`'s removal of `model`.
- **A second copy of a clinical record is not an implementation detail.** The copilot is
  stateless and the ERP is the system of record (`../ARCHITECTURE.md:268-271`). Every
  application below names the store it writes into, and an application that cannot name one is
  not an application yet — it is a demo.

---

## 2. What one application consists of

Taken from the only application that exists, `apps/radiology_copilot/src/futurekind_radiology/`
(the tree is drawn in `../ARCHITECTURE.md:249-264`). Fourteen files, of which **five are
specialty-specific and eight are the pattern** — that ratio is the entire business case for a
family rather than fourteen products.

| File | Role | Reused by the next application as… |
| --- | --- | --- |
| `api.py` | One HTTP surface: the four operations, the screen, `/health`, one error envelope, nothing cacheable | **A copy with the model names changed.** The middleware and the envelope are the pattern |
| `submission.py` | What the clinician supplied, with **no patient identifier field** by rule (`apps/radiology_copilot/src/futurekind_radiology/submission.py:15`) | A copy. The rule is universal; the fields are not |
| `copilot.py` | The four operations, stateless | **Rewritten per application** — the operations differ (pathology has a specimen, a physician note has a problem list) |
| `prompt.py` | The system turn, versioned so a report names its prompt | **Rewritten.** This is Agent authoring, and it is the slowest file in the product |
| `gateway.py` | Skill-only request; strips anything that could name a model | **A copy.** One line changes: which skill |
| `report.py` | The document, its sections, its ownership rule | **Rewritten.** Section names come from the department's document |
| `profiles.py` | Which study gets which structure checklist | **Rewritten per specialty**, or emptied where no checklist is honest |
| `quality.py` | Deterministic text-grounding checks, two severities, computed confidence | **Partly copied.** The *shapes* (ungrounded measurement, dropped source statement, certainty drift, truncation) are universal; the phrase and structure lists are radiology English and must not be ported silently — see §6 |
| `rendering.py` | The same document as text / markdown / json, one order | A copy with a heading set |
| `errors.py`, `settings.py`, `__main__.py`, `static/` | Envelope codes, env, entrypoint, the working screen | A copy, then the screen re-designed per `../design/DESIGN_SYSTEM.md` |

The **Agent** of `../DOMAIN_MODEL.md` is the name for the four files marked *Rewritten* —
`prompt.py`, `profiles.py`, `report.py`, `quality.py`'s specialty lists. It has no directory,
and it never appears in a request (`../CONSTITUTION.md:391-396`).

---

## 3. The map

"Skills named today" means present in `core/gateway/models.yaml`, the only file the platform
loads. Everything else is what the application *would* name, cited to its design entry in
`SKILL_LIBRARY.yaml`.

| # | Application | Process and door | Skills named today | Skills it would add | Reads (canonical objects) | Writes to | Screens | State |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | **Radiology Copilot** | `apps/radiology_copilot/`, port 8200, screen served from the same origin (`../ARCHITECTURE.md:250`) | `radiology-report` `core/gateway/models.yaml:54`, `usg-advisory-suggestions` `:104` | the modality stanzas in `SKILL_LIBRARY.yaml:188-660` | Study, Observation (as dictation), Impression, Recommendation, Comparison | ERP `radiology_report_drafts.structured_json`, then `patient_reports` (`../integration/INTEGRATION_CARE_ERP_PACS.md:19-25`) | `UI_UX.md` §1–§7 | **Built (Alpha)** |
| 2 | **Pathology Copilot** | new `apps/pathology_copilot/` | **`pathology-review` `core/gateway/models.yaml:68` — authorised and unused** | `cytopathology-report` `SKILL_LIBRARY.yaml:982`, `haematology-bone-marrow-report` `:994`, `cervical-screening-report` `:1006` | Specimen, Observation (gross + micro), Diagnosis, Comparison, Medication(read) | The ERP's pathology record — **not documented in this repository** (§7) | `CLINICAL_SUITE.md` §3 | Design |
| 3 | **Physician Copilot** | new `apps/physician_copilot/` | none (`clinical-chat` `:80` is authorised and unused, and is *not* a document skill) | `ward-round-daily-note` `:786`, `problem-list-reconciliation` `:798`, `medication-reconciliation` `:810`, `clinical-summary` `:774` | Problem list, Medication(read), Procedure(read), Report | Ward notes in the ERP | `CLINICAL_SUITE.md` §4 | Design |
| 4 | **Emergency Copilot** | new `apps/emergency_copilot/` | none | `ed-triage-note` `:725`, `ed-chest-pain-pathway` `:737`, `ed-paediatric-fever-pathway` `:749`, `ed-discharge-instructions` `:761`, `neuro-glasgow-coma-scale` `:663` | Observation, Score, Task | ED record in the ERP | `CLINICAL_SUITE.md` §4 | Design |
| 5 | **Critical Care Copilot** | new `apps/critical_care_copilot/` | none | `intensive-care-bulletin` `:823`, `procedural-sedation-record` `:1094`, `transfusion-reaction-record` `:1081`, `neuro-critical-care-family-briefing` `:1119` | Medication(read), Procedure, Task, Notification | ICU flowsheet in the ERP | `CLINICAL_SUITE.md` §4 | Design |
| 6 | **Theatre Copilot** | new `apps/theatre_copilot/` | none | `pre-anaesthetic-assessment` `:847`, `operative-note-draft` `:835`, `post-operative-instruction` `:859`, `stroke-rehabilitation-handover` `:1107` | Procedure, Implant(**no documented object** — §7), Complication | OT record in the ERP | `CLINICAL_SUITE.md` §5 | Design |
| 7 | **Discharge Copilot** | new `apps/discharge_copilot/` | `summarize-document` `:90` is authorised and unused — the closest thing to a starting point | `discharge-summary` `:1343`, `referral-letter` `:1355`, `ed-discharge-instructions` `:761` | Report, Medication(read), Recommendation, FollowUp, Task | Discharge record; referral letters | `CLINICAL_SUITE.md` §6 | Design |
| 8 | **Coding Assistant** | new `apps/coding_assistant/` | none | `icd10-coding-suggestion` `:1406`, `procedure-coding-suggestion` `:1418`, `prior-authorisation-letter` `:1430`, `claim-appeal-draft` `:1442` | Diagnosis, Procedure, Report | A claim draft a human coder edits; **never the claim itself** (`PRODUCT_BIBLE.md` §6.4) | `CLINICAL_SUITE.md` §6 | Design |
| 9 | **Tumour Board Copilot** | new `apps/tumour_board_copilot/` | none | `tumour-board-summary` `:1218`, `tumour-staging-note` `:1231`, `oncology-treatment-plan` `:1243`, `survivorship-care-plan` `:1256`, `palliative-care-plan` `:1268` | Diagnosis, Stage, Report, Task (one per member action) | The board record | `CLINICAL_SUITE.md` §6 | Design, **cannot ship before ADR-0005** |
| 10 | **Clinical Timeline** (+ Audit view) | a view in the ERP, or one read-only service | none — it calls no skill | none; the comparison it enables is `prior-study-comparison` `:1541`, which is a skill and must not be confused with the surface | Every object above, ordered | Nothing | `UX_GUIDE.md` §4 | Design, **blocked on ADR-0007** |
| 11 | **Patient-Facing Text** | a view inside the Discharge and Emergency copilots | none | `patient-explainer` `:1467` (merged with `plain-language-report` `:1479`), `pre-procedure-instructions` `:1491`, `fasting-and-medication-instruction` `:1503` | Report, Recommendation, Instruction | A printed or messaged leaflet, after a clinician approves it | `CLINICAL_SUITE.md` §7 | Design |
| 12 | **Hospital Command Center** | console; reads, drafts nothing | none | `turnaround-time-brief` `:1591`, `quality-indicator-audit` `:1454`, `cohort-extraction` `:1566` *(blocked)* | Counts over Study, Report, Approval, Task | Nothing clinical | `CLINICAL_SUITE.md` §8 | Design, **blocked on ADR-0007** |
| 13 | **Clinical QA and Peer Review** | console, and one instrument that already exists | none | `quality-indicator-audit` `:1454`, plus peer review of Reports | Rows the review instrument already writes (`scripts/validation/dashboard.py`) | Nothing clinical; QA findings are **audit issues**, not Reports | `CLINICAL_SUITE.md` §8 | **Prototype built** |
| 14 | **Medical Scribe** | the ERP's microphone, not a FutureKind process | none — and it must not gain one | the polish step only, on text | Dictation as text | The dictation field of whichever copilot is open | `CLINICAL_SUITE.md` §7 | **Refused as an application** (`PRODUCT_BIBLE.md` §3.4) |

---

### 3.1 The eighteen ungoverned paths, and which application takes each one over

The family's first customer-visible job is not new AI; it is consolidation. The ERP has eighteen
numbered HTTP entry points that reach a model (`../integration/AI_ENTRY_POINTS_CARE_ERP.md:72-91`),
and exactly one of them goes through the Gateway (`:74`, Sprint 8, still uncommitted in that
working tree — `docs/product/README.md:22`). Each row is what an application must be able to say
when it takes the path over.

| # | Today's path | What it does | Taken over by | What must be true first |
| --- | --- | --- | --- | --- |
| 1 | `:74` | Ultrasound chip suggestions | **#1 Radiology**, already | Merge the ERP branch; the skill is authorised (`core/gateway/models.yaml:104`) |
| 2 | `:75` | Deterministic accept of a suggestion | **#1 Radiology** | No model call, so nothing to govern — but the accept must stay a human act |
| 3 | `:76` | Eight radiology actions, model chosen per request | **#1 Radiology**, as named skills | One stanza per action in `models.yaml`, or the actions collapse into `radiology-report` deliberately |
| 4 | `:77` | Multi-review, permission bug and provider from the request body | **#13 Clinical QA** (peer review) | The permission bug is a security fix, not an AI decision; a caller-named provider must go (P16) |
| 5 | `:78` | Test, verify and pipeline self-test | **No application** — these are operator tools | Keep them outside the clinical surface; they name models, which is correct for a test harness |
| 6 | `:79` | Patient message, radiology impression, clinical note, billing insight, teaching, transcribe-polish | **#7 Discharge**, **#3 Physician**, **#8 Coding**, **#11 Patient-Facing** | Each becomes its own skill; the shared `generateAiForTask` seam is the reason one migration can cover many |
| 7 | `:80` | Transcription through a vendor API with the key in a query string | **Refused** as an application (`PRODUCT_BIBLE.md` §3.4) | The credential is the emergency, not the AI. There is no speech path in the platform to migrate to |
| 8 | `:81` | Local speech-to-text, raw fetch | **Refused**, same reason | Same |
| 9 | `:82` | Image comparison, provider named by the client | **No application** — the platform has no vision capability | Either it stays outside with an explicit decision recorded, or a `vision` capability is proposed as a platform change, which tonight's brief forbids |
| 10 | `:83` | Prompt-library test | **No application** | Authoring tooling; belongs beside `PROMPT_LIBRARY.md`, governed as a developer path |
| 11 | `:84` | Reporting query, draft, polish, image review, RAG | **#10 Timeline** and **#12 Knowledge** — both blocked | RAG needs ADR-0006; the image route needs the vision decision above |
| 12 | `:85` | Dead `ai-enhance` route, zero front-end callers | **Deleted** | A route nothing calls is not a migration, it is a removal |
| 13 | `:86` | Voice report composer, raw fetch bypassing the provider package | **#1 Radiology** (dictation is its input) | The microphone stays; the fetch goes through a skill |
| 14 | `:87` | Report composer with a vision trial | **#1 Radiology** for text; vision as in row 9 | Same split |
| 15 | `:88` | Nightly batch generation | **No application** | Batch is a job model the platform does not have; this is the gap the ERP already fills outside |
| 16 | `:89` | Fetal USG and echocardiography drafts | **#1 Radiology**, as two profiles | `us-obstetric-*` `SKILL_LIBRARY.yaml:480-536` and `echocardiogram-report` `:1157` exist as designs; PCPNDT rules travel with the fetal one |
| 17 | `:90` | Accounting, invoice, bank-statement and ID-card OCR | **#8 Coding**'s boundary, and mostly **not ours** | Non-clinical documents with personal data; the ask is credentials and logging, not a copilot |
| 18 | `:91` | Knowledge-base search for AI callers | **#12**, blocked | ADR-0006, and its token scope already forbids clinical writes (`../integration/INTEGRATION_CARE_ERP_PACS.md:52-56`) |

**What this table is for.** It turns the family plan into a migration order with a customer-visible
result, and the count is the point: of eighteen paths, **eight become an application's job** (1, 2,
3, 4, 6, 13, 14, 16), **eight are refused or deleted with a named reason** (7, 8, 9, 11, 12, 15, 17,
18), and **two stay as operator tooling that should never have sat on a clinical surface** (5, 10).
The four reasons behind the refusals are vision, a job model, speech, and documents that are not
clinical — each of them an entry in `../SPECIFICATION.md` §17 or a capability the constitution has
not been amended to allow, rather than a gap nobody looked at. That is what makes this a plan and
not a list: nothing is left ungoverned by accident.

---

## 4. Three authorised skills that nothing calls

`core/gateway/models.yaml` carries six stanzas. One is called by an application in this
repository (`radiology-report`, by the copilot); one is wired into the ERP's ultrasound chip but
sits uncommitted in that working tree, so no clinician can reach it yet
(`docs/product/README.md:22`). Three are configured, reachable and **called by nothing**:

| Skill | Line | Risk | What it shows |
| --- | --- | --- | --- |
| `pathology-review` | `core/gateway/models.yaml:68` | high | A pathology report can be requested *today* and would be routed, audited and ceiling-capped. The gap is not the platform; it is a prompt, a document shape, a check set and cases |
| `clinical-chat` | `:80` | moderate | A conversational surface is governed but unbuilt. It is also the one skill that produces no document, so it is the easiest to misuse — see the safety rule in `../safety/CLINICAL_SAFETY.md` §5 |
| `summarize-document` | `:90` | low | The only authorised skill with `audit_required: false` (`:100`), which is a decision worth re-reading before any application starts summarising patient text with it |

**A skill reachable in configuration with no application is an exposure, not a capability.** The
credential that can name `pathology-review` can be used by a script. `SECURITY.md` and the
threat model already treat ungoverned paths as the enemy; three authorised-but-unused skills
are the platform's own version of one. The map's answer is either to build the application or to
disable the stanza, and it is a decision for the platform owner (`PRODUCT_BIBLE.md` §8).

---

## 5. Dependency graph

```
   ADR-0005 approvals ─────────┬─> 9 beta skills (SKILL_LIBRARY.yaml:138, :1226)
   (what an approval records)  ├──> Tumour Board (#9)
                                └──> every copilot's honest claim, incl. #1 today
                                     └─ substitute in force: copilot + ERP both sign
                                        (docs/product/README.md:111-115)

   ADR-0003 retention ─────────┬─> Audit view of #10, Medicolegal summary
                                └──> #13's indicator history
                                     └─ substitute: provenance stored on the document

   ADR-0007 Hospital + Patient Context ──> #10, #12, and any cohort
                                     └─ substitute: none. Do not guess an identifier
                                        (../DOMAIN_MODEL.md Q2)

   ADR-0006 retrieval + citation ──> Knowledge surface, "per guideline" sentences
                                     └─ rule meanwhile: no application may cite a
                                        guideline it cannot name
```

Nothing in the graph is a missing model, a missing capability or a missing service. That is the
same finding the skill library reached for its 121 entries (`../product/SKILL_LIBRARY.yaml:17-20`),
and it is why this map is configuration, authoring and interface work rather than architecture
work.

---

## 6. Porting a check set, which is not free

`quality.py` is the most valuable reusable asset in the repository and the easiest to port
wrong. Its nine checks (`apps/radiology_copilot/src/futurekind_radiology/quality.py:226-236`)
divide cleanly in two. Six are **shape**: the draft dropped something the source said
(`dropped_observation`), a number nobody dictated (`unsupported_measurement`), a hedge that
became a claim (`unsupported_certainty`), an absence asserted beyond the text
(`unsupported_absence`), the model grading itself (`self_reported_confidence`, refused on sight),
and a section that is not prose (`format_breach`). Truncation sits with these in spirit, though
it is checked at the transport before parsing (`../ARCHITECTURE.md:273-274`). Every one of them
applies to any document written from dictation, in any department.
Three are **radiology English**: `invented_history`, whose two phrase lists are the vocabulary of
interval change and prior exams (`quality.py:78-93`), `invented_identifier`, whose patterns are
the identifier formats this particular hospital uses (`quality.py:497-501`), and
`structure_coverage`, which reads a table of the structures an MRI brain study should mention
(`profiles.py`).

The rule for the next copilot is the one `ROADMAP.md` §4b proved necessary: **measure each check
against correct documents before assigning it a severity.** `invented_history` refused four
ordinary dictated sentences in eleven; a port that skipped that measurement would ship an engine
that refuses nothing, and a check which never fires is worse than no check, because it is
trusted.

---

## 7. Where this map is assumption, not evidence

The integration record documents radiology and only radiology: `radiology_studies`,
`radiology_report_drafts.structured_json`, `patient_reports` with its signature and version
columns, `integration_outbox`, `feature_flags`
(`../integration/INTEGRATION_CARE_ERP_PACS.md:19-25`, `:127-129`, `:254`, `:305-311`).
It contains **no named table or screen** for registration and orders, wards, ICU, theatre as a
clinical object, discharge, pharmacy administration, implants, beds, infection control, NABH
indicators or turnaround time.

Applications #3–#8, #12 and #13 therefore map onto records whose existence is assumed. Before
any of them is estimated or scheduled, the ERP has to be walked and written down the way the
radiology path was — the entry-point inventory in `../integration/AI_ENTRY_POINTS_CARE_ERP.md`
is the template, and its 18 numbered entry points are the proof that the walk is a day's work,
not a project.

---

## 8. The reuse test

One table, one question. A reviewer checks a new application against this list; **every "no"
is a duplicate concept and P18 (`../CONSTITUTION.md:413-414`) says it does not enter the
codebase.**

| Question | The one place that owns the answer |
| --- | --- |
| What does this sentence mean? | `../DOMAIN_MODEL.md` |
| Which skill is this, at what risk, needing what approval? | `../product/SKILL_LIBRARY.yaml`, then `core/gateway/models.yaml` when authorised |
| What may the AI never do here? | `../safety/CLINICAL_SAFETY.md`, enforced by the platform per P11 (`../CONSTITUTION.md:285-287`) |
| What does a screen look like and how does it fail? | `../design/DESIGN_SYSTEM.md` for the language, `../design/UX_GUIDE.md` for the pattern, `../product/UI_UX.md` for radiology's screens |
| Where does the signed document live? | This map, column "Writes to" |
| In what order is any of it built? | `../product/ROADMAP.md` |
| What is it worth, and to whom? | `../business/COMMERCIAL_ROADMAP.md` |

*FutureKind · Genesis Night 3 · 2026-10-09.*
