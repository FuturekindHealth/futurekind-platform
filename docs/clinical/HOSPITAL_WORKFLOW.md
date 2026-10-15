# FutureKind Hospital Workflow

**Owns:** the hospital as one journey — every node a patient passes through, what record each node
creates, where an application above the platform may help, and where AI may never act.
**Does not own:** the radiology department's own twelve steps and thirty failures
(`../product/RADIOLOGY_WORKFLOW.md`, which this document references and does not restate), the
applications (`../product/PRODUCT_BIBLE.md`, `../product/CLINICAL_SUITE.md`), the objects
(`../DOMAIN_MODEL.md`), safety gates (`../safety/CLINICAL_SAFETY.md`).
**Status:** mapped against two named hospitals. Every node carries its evidence, and where there is
none it says so.

---

## 1. The evidence rule, stated before the map

This map is drawn from what the integration record actually documents, and the record documents
**radiology in detail and everything else by accident**. Concretely:

| Evidence grade | Meaning | Marked in the tables as |
| --- | --- | --- |
| **[V] / [A]** | Verified in the ERP or PACS source, or asserted from it, with a citation in `../integration/AI_ENTRY_POINTS_CARE_ERP.md` | `source` |
| **Documented** | A table, screen or endpoint named in `../integration/INTEGRATION_CARE_ERP_PACS.md` | `source` |
| **Assumed** | The node exists in every hospital; this repository has **no** named table, screen or endpoint for it | `assumed — walk it before estimating` |

The assumed list is long and it is the most useful thing in this document: registration and order
detail, ward and bed management, ICU flowsheets, theatre as a clinical object, implants, pharmacy
administration, discharge, referrals, follow-up and recall, NABH indicators, infection control,
mortality review and turnaround time. See §8 for what walking them costs.

**And one finding that changes the framing.** The hospital does not need this map to tell it where
AI can help: it already has AI in **eighteen HTTP entry points** across radiology, patient
messaging, clinical notes, billing insight, accounting OCR, bank-statement parsing, ID-card OCR,
echocardiography, fetal ultrasound, voice composition and a nightly batch
(`../integration/AI_ENTRY_POINTS_CARE_ERP.md:72-92`). Exactly **one** of those eighteen passes
through the Gateway (`:74`, governed in Sprint 8 and still uncommitted). The question tonight is
not *whether* AI acts in this hospital; it is whether the acting happens behind one boundary with
policy and provenance, or in seventeen places without either.

---

## 2. The journey

```
 Arrive ─► Triage ─► Register + Order ─┬─► Imaging ─────► Report ──► Sign ──► Deliver ─┐
                                       ├─► Laboratory ──► Result ──────────────────────┤
                                       ├─► Bed / Ward ──► Daily note ─► Problem list ──┤
                                       ├─► Theatre ─────► Op note ─► Specimen ─► Path ─┤
                                       ├─► ICU ─────────► Bulletin ─► Drug review ─────┤
                                       └─► ED decision ─► Discharge instructions ──────┤
                                                                                        ▼
                     Follow-up ◄── Recall ◄── Discharge summary + referral ◄── Combine
                        │                                                              ▲
                        └─► Next study, next admission ────────────────────────────────┘
                              every arrow above is an Approval and an Audit record
```

Radiology's own version of the middle of this diagram — S0 to S11, with what is built and what is
not — is `../product/RADIOLOGY_WORKFLOW.md` §1. This document does not restate it, and every node
below that touches imaging says *see S4–S6*.

---

## 3. Every node, what it may use, and what it may never do

Skills are cited by id from `../product/SKILL_LIBRARY.yaml`. "Never" rows are the consolidated
list in §5, not local inventions.

| Node | Who acts | Record created | AI may help with | AI may never do | Evidence |
| --- | --- | --- | --- | --- | --- |
| **Arrival and triage** | Triage nurse, ED physician | Triage category, vitals | Structure the triage note (`ed-triage-note` `:725`); surface the pathway the category mandates (`ed-chest-pain-pathway` `:737`, `ed-paediatric-fever-pathway` `:749`) | **Assign the category.** A triage level is a clinical decision with a queue and a liability behind it | assumed (no triage table documented) |
| **Registration and order** | Reception, referrer | Patient identity (UHID, `patients.patientId`, no MRN column — `../integration/INTEGRATION_CARE_ERP_PACS.md:305`), the order | Nothing. This is the one node where the platform's scope line is explicit: scheduling, ordering and billing are out of scope (`../SPECIFICATION.md:140-144`) | Create, alter or interpret an order | documented |
| **Imaging acquisition** | Radiographer | Study, series, protocol, dose | Study-quality observations for a human to act on (`radiology-study-quality-check` `:154`) | Choose a protocol or a dose. Both are the department's act | documented (`radiology_studies`, S1–S2) |
| **Imaging reporting** | Radiologist | Report | The whole drafting loop, built: dictation → draft → nine checks → named sign-off → export (see S4–S6) | Sign, amend silently, or deliver | **built** |
| **Laboratory routine** | Biomedical scientist, lab physician | Result panel, critical value | Summarise a panel for a human (`laboratory-panel-summary` `:1019`); draft the critical-value review record (`laboratory-critical-value-review` `:1031`, `beta`) | **Declare a critical value or send the notification.** A timed clinical act needs a named human and a retention the platform does not have | assumed |
| **Ward day** | Resident, consultant | Daily note, vitals, fluid balance | Structure the note (`ward-round-daily-note` `:786`); reconcile the problem list (`problem-list-reconciliation` `:798`); reconcile medications (`medication-reconciliation` `:810`) | Write the plan. Change a dose. Drop a problem silently | assumed |
| **Drug review** | Consultant, clinical pharmacologist | Review record | Interaction and dose-adjustment drafts (`drug-interaction-review` `:1281`, `renal-and-hepatic-dose-adjustment` `:1293`, `high-alert-medication-check` `:1305`, `antimicrobial-stewardship-review` `:1317`) | Order, dispense, stop or substitute (`../SPECIFICATION.md:140-144`; Medication is read-only, `../DOMAIN_MODEL.md`) | assumed |
| **Theatre** | Surgeon, anaesthetist, scrub | Checklist, operative note, implants, specimens | Structure the dictated note (`operative-note-draft` `:835`); draft the pre-anaesthetic assessment text (`pre-anaesthetic-assessment` `:847`) | **Tick a checklist item.** Assign an ASA grade. Invent an implant, a serial number or a laterality | assumed (theatre is not documented as a clinical object; "OT" appears in the integration record only as a DICOM modality) |
| **ICU** | Intensivist | Bulletin, lines, ventilator settings, sedation | Draft the bulletin from the record (`intensive-care-bulletin` `:823`); the sedation record (`procedural-sedation-record` `:1094`) | Change a ventilator or infusion setting. Characterise a complication's cause | assumed |
| **Specimen to pathology** | Prosector, pathologist | Specimen, gross, micro, diagnosis, IHC | Formatting the gross and micro dictation; drafting the report's structure (see `../product/CLINICAL_SUITE.md` §3) | A margin status, a node count, a category, a panel choice, or a frozen-section answer under time pressure | assumed (no specimen chain documented) |
| **Blood and transfusion** | Clinician, lab | Request, issue, reaction record | Draft the reaction record (`transfusion-reaction-record` `:1081`, `beta`) | Decide to transfuse. Complete a statutory notification | assumed |
| **Multidisciplinary board** | Several clinicians | Board plan | Draft the summary of what the board decided (`tumour-board-summary` `:1218`, `beta`) | **Be the plan.** Several clinicians are bound by one document, and the platform cannot yet verify one approval | assumed |
| **Discharge** | Discharging clinician | Summary, medication list, follow-up plan | Draft the summary and the referral letter (`discharge-summary` `:1343`, `referral-letter` `:1355`) | Finalise a discharge. Decide fitness (`fitness-for-duty-assessment` `:1393`) | assumed |
| **Patient communication** | Clinician, front desk | Instruction, letter, explainer | Draft in plain language, approved word by word (`patient-explainer` `:1467`, `pre-procedure-instructions` `:1491`) | Send anything to a patient unsupervised; state fetal sex (PCPNDT — the ERP already drops it, `core/gateway/models.yaml:104-120`) | partially documented (`/ai/patient-message`, `AI_ENTRY_POINTS_CARE_ERP.md:79`) |
| **Recall and follow-up** | Department, nurse | Recall, Task | Propose the recall from a signed interval (`breast-lesion-recall-decision` `:650`) | Own the task or decide its timing — the ERP owns Tasks (`../DOMAIN_MODEL.md`) | assumed |
| **Coding and claims** | Coder, billing office | Codes, claim | Suggest codes from the signed document (`icd10-coding-suggestion` `:1406`, `procedure-coding-suggestion` `:1418`) | Be the reason a service was billed (`../product/PRODUCT_BIBLE.md` §6.4) | documented as an existing ungoverned path (`/ai/billing-insights`, accounting OCR — `:79`, `:90`) |
| **Quality, audit, mortality and infection review** | Quality team, infection control | Indicator, review, action | Aggregate and draft the review document (`quality-indicator-audit` `:1454`, `healthcare-associated-infection-review` `:1144`) | Assert compliance. A NABH claim is a hospital's signed statement | assumed |
| **Teaching and training** | Department | Teaching file | Summarise for teaching (`/ai/teaching-*` already exists, ungoverned, `:79`) | Produce a teaching answer that reads like a patient statement | documented (as an ungoverned path) |

---

## 4. Where the help is, ranked across the whole hospital

Not ranked by specialty. Ranked by what the hospital actually spends.

| Rank | Where AI helps | Why it is the top of the list | What it must be built on |
| --- | --- | --- | --- |
| 1 | **Turning dictated or typed prose into a structured document** | Every department does it, it is the hours, and it is the one thing an LLM is genuinely good at (`../product/PRODUCT_SPECIFICATION.md:259-260`) | The drafting loop, per `CLINICAL_SUITE.md` §1 |
| 2 | **Continuity across a record** — a summary, a discharge, a board sheet | The composite documents are where clinicians lose half a day, and where omission is the risk | Problem list, Medication and Report objects; `dropped_observation`'s discipline |
| 3 | **Comparison against what was there before** | The sentence "unchanged from prior" is refused today because it is unverifiable without a prior (`../DOMAIN_MODEL.md`, Comparison) | Two studies in the request; the Timeline blocked on ADR-0007 |
| 4 | **Catch-and-carry checks on a draft** — numbers, certainty, omissions, categories | Deterministic, measurable, and already proven to refuse correct reports when unmeasured (`../product/ROADMAP.md` §4b) | Each department's own measured check set |
| 5 | **Patient-facing wording** | Low clinical risk per document, real harm per misunderstanding | A clinician approving the exact words, plus a legibility check (`../product/CLINICAL_SUITE.md` §7) |
| 6 | **Administrative drafting** — letters, appeals, authorisations | The ungoverned paths already do this today; governing them is the win, not the drafting | Same envelope, same provenance, one boundary |

**And what no rank contains:** deciding, ordering, dispensing, notifying, triaging, grading risk,
ticking a box, signing, or being the reason anything was billed. That is not a gap in ambition; it
is §5.

---

## 5. The consolidated never list

P11 states the principle (`../CONSTITUTION.md:285-287`: the AI "may not be the final author … may
not sign, may not order, may not dispense"). Applied across the hospital it produces this list,
which is the only place in the documentation where all of it appears together — the node tables
above reference it rather than each inventing their own boundary.

| AI may never | Because | Where it is enforced today |
| --- | --- | --- |
| Sign, countersign or verify a document | P3, P11; a clinical final state must have a human transition | The ERP refuses a signer role of `typist|ai|system|bot` (`../integration/INTEGRATION_CARE_ERP_PACS.md:252`) |
| Order, dispense, administer, stop or change a dose | Out of platform scope | `../SPECIFICATION.md:140-144`; Medication is read-only by definition |
| Send, deliver, notify or release | A notification is a clinical act with a time and an owner | The Gateway **refuses** a skill that declares `approval_required` rather than pretending (`../product/README.md:111-115`); ADR-0005 pending |
| Assign a triage category, an ASA grade, a stage, a score or a reporting category | Each is a decision whose form is a number | Prompt rules refuse arithmetic that does not add (`SKILL_EXAMPLES.md:344`); the application refuses the sign-off |
| Tick a safety checklist item | Its only value is a human confirming at a moment | No implementation may write checklist state (`../product/CLINICAL_SUITE.md` §5) |
| Choose a protocol, a dose or an IHC panel | They are the department's act, made with the patient in front of them | Node table, §3 |
| State fetal sex | Statutory | The ERP's safety core drops it before display (`core/gateway/models.yaml:104-120`) |
| Be the reason a service was billed | Financial and legal consequence without clinical benefit | `PRODUCT_BIBLE.md` §6.4 |
| Present recalled text as a guideline | No citation capability exists | `citation_available: false` labelling (`../product/SKILL_EXAMPLES.md:488`); ADR-0006 |
| Persist patient text where the clinician cannot see it | Storage outside the record is an uncounted copy | `../security/THREAT_MODEL.md` §3, asserted by test |
| Decide when a day, a case or a session ends | That is a workflow act | §6 |

---

## 6. Who owns the workflow — and this answers `../DOMAIN_MODEL.md` Q5

**The EHR owns the workflow. FutureKind owns the request and nothing that outlives it.**

That is not a new position; it is what the built product already does — stateless operations, the
document travelling through the caller, the Report stored in the ERP (`../ARCHITECTURE.md:268-271`)
— applied here to the whole map, including the departments that will find it inconvenient. Four
consequences, all of them refusals:

1. **No workflow engine in FutureKind.** Stages, timers, escalations and queue order belong to the
   ERP. A second queue is a second truth about who is waiting, and the divergence is patient harm,
   not tidiness.
2. **No state that survives the response.** Not a draft cache, not a session, not a task, not a
   "pending review" flag. The one exception is the document the clinician is signing, which lives
   in the browser holding it and nowhere else.
3. **Delivery is the ERP's outbox.** `integration_outbox` with `pending/sent/dead` already exists
   (`../integration/INTEGRATION_CARE_ERP_PACS.md:129`); an application that builds its own retry or
   its own delivery log creates the duplicate-report incident the workflow catalogue calls F14.
4. **A handoff is a version, not a copy.** `sequenceNumber`/`totalVersions` and `X-Report-Version`
   are already how the ERP does it (`:254`, `:310`).

What FutureKind *does* own at every node: the skill identity, the policy that governed the request,
the provenance of the answer, and the right to refuse. Those four are the platform's, and this map
does not move them.

---

## 7. Where the journey breaks between departments

No new failure taxonomy: the catalogue in `../product/RADIOLOGY_WORKFLOW.md` §"failures" already
names the classes, and each of these cross-department breaks is one of them wearing another
department's clothes.

| Break | Catalogue entry | How it appears outside radiology |
| --- | --- | --- |
| A statement with no source | F10, F19, F20 | A discharge summary asserting a complication nobody documented; a board plan with a drug no one prescribed |
| A machine-authored signature | F13 | The typist who dictates the operative note becomes the signer |
| A document delivered twice, or the wrong version | F14 | A amended ICU bulletin re-sent as a new record |
| Text leaving the building | F18 | Accounting OCR of a bill with an address on it, today, ungoverned (`../integration/AI_ENTRY_POINTS_CARE_ERP.md:90`) |
| Certainty rising between draft and final | F21 | "possible PE" in the radiologist's dictation becoming "no PE" in the ED note |
| A silent substitution | F5 | A `fast` model answering where a `reasoning` one was configured — impossible today only because no fallback chain is declared, so `degraded` is always false (`../architecture/gateway-routing.md:163-166`) |
| An unread refusal, and a clinician who has learned to ignore the red box | the automation-bias requirements in `../product/RADIOLOGY_WORKFLOW.md` §4 | A radiologist who signs past a blocking finding because it fired on the last three studies too |

---

## 8. The walking task

Before any non-radiology node in §3 is estimated, scheduled or designed further, the ERP has to be
walked the way the radiology path was: one document listing every entry point, its deepest model
call, its guard, whether it handles images, and how big the seam is. The template exists and it is
two days of reading — `../integration/AI_ENTRY_POINTS_CARE_ERP.md` produced 18 rows, 6 evidence
grades and one migrated path in a single pass.

This is the cheapest item in the entire family plan, and until it is done for wards, theatre, ICU
and discharge, §3's `assumed` rows are the honest answer to a question nobody has asked the hospital
yet.

*FutureKind · Genesis Night 3 · 2026-10-09.*
