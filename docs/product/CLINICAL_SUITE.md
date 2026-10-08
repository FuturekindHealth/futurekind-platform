# FutureKind Clinical Suite

**Owns:** the design of each clinical application — its document shape, which sections a machine
may write, what it checks, what it costs to build, and in what order its features are worth doing.
**Does not own:** which applications exist and why (`../product/PRODUCT_BIBLE.md`), the words
(`../DOMAIN_MODEL.md`), skill fields (`../product/SKILL_LIBRARY.yaml`), screens and interaction
(`../design/DESIGN_SYSTEM.md`, `../design/UX_GUIDE.md`, `../product/UI_UX.md`), hospital-wide
step sequence (`../clinical/HOSPITAL_WORKFLOW.md`), safety gates (`../safety/CLINICAL_SAFETY.md`).
**Status:** one application in Alpha; everything else is design and carries a cost, not a promise.

---

## 1. What building an application actually costs

The unit of work is not a screen. From the only application that exists, the work is five
decisions, in this order:

| # | Decision | Radiology's answer | Why it has to be first |
| --- | --- | --- | --- |
| 1 | **Document shape** — the sections, and who owns each one | Six sections; `report.py::editable_section_keys` decides locking by who wrote the text (`../product/UI_UX.md` §4) | It fixes what a prompt can return and what a check can compare |
| 2 | **Profiles** — what this examination is expected to describe, and what it may not claim | `MRI_BRAIN_STRUCTURES`, fourteen structures with their synonyms, and `MRI_BRAIN_OUT_OF_SCOPE`, seven claims a brain study has no business making (`apps/radiology_copilot/src/futurekind_radiology/profiles.py:29-59`) | This is the only place a human decides coverage; a guessed checklist is how a check starts being ignored, which is why Alpha ships **one** profile (`profiles.py:11-13`) |
| 3 | **Checks and severities**, measured | Nine checks; each severity decided by how often it fires on a *correct* draft and how often it is the sole reason a correct draft cannot be signed (`ROADMAP.md` §4b) | An unmeasured blocking check trains clinicians to distrust refusals |
| 4 | **Prompt**, versioned | `radiology-report-draft/0.3.1`, 2,894 characters, every rule stated once (`../product/PROMPT_LIBRARY.md` §1) | Version must travel with the report or a good answer cannot be reproduced |
| 5 | **Handoff** — where the signed document lives | ERP `patient_reports` + PACS encapsulated PDF (`../integration/INTEGRATION_CARE_ERP_PACS.md:127`) | An application that cannot name its system of record is a demo |

Everything below is those five decisions, made on paper for each department. The **cost** column
in each table is in these units: a *profile* is a structure list plus a synonym list plus a
measured false-positive audit against correct reports; a *check* is a rule plus its measurement;
a *prompt change* is a version bump plus the golden re-run.

---

## 2. Radiology 2.0

The brief asked for fourteen things and said *do not implement blindly, prioritise*. The ranking
below is by (clinical consequence ÷ cost), and cost is counted in the units above.

| Feature | What it needs, concretely | Rank | Why, and the honest objection |
| --- | --- | --- | --- |
| **Normal templates per modality** | A profile per modality (§1 step 2), *not* a template — the template is the rendering of a profile a human ratified | **P0** | Highest consequence per unit of work: it makes `structure_coverage` real for CT, US and XR, which today can only judge MRI brain. Objection: eight modalities × a ratified structure list is clinical time, and a template invented by an engineer is the thing `profiles.py:11-13` refuses to do |
| **Structured findings** (typed laterality, negation, measurements, evidence anchors) | The document-model upgrade already scheduled: roadmap §3 item 9.1 mirrors the ERP's `ShadowStructuredDraft` | **P0** | This is the correct answer to *five* items on the brief's list at once — measurement helpers, comparison, laterality helpers, follow-up tracking, and half of the grading systems. `docs/product/README.md:119-124` already concedes the ERP's model is better than FutureKind's: a regex over prose misses `two lesions` and cannot say *which* lesion a measurement belonged to |
| **Measurement helpers** | A typed measurement inside the structured finding: value, unit, site, compared-to | **P1, after structured findings** | Worth doing once, in the model. Done as prose it means a second family of regexes — the brief forbids inventing hundreds of them, and `unsupported_measurement` already catches the prose case as well as prose can |
| **Comparison mode** | Two Studies, the prior report text in the submission, and the Comparison Viewer (`../product/UI_UX.md` §5) — S5 is unbuilt (`../product/RADIOLOGY_WORKFLOW.md` §1) | **P1** | The single highest-value screen for follow-up studies, and the only feature that turns `invented_history`'s advisory into a real answer. Blocked by nothing except that nobody has wired the prior report into the submission |
| **Multi-study review** (one patient, several studies side by side) | The ERP worklist keyed by StudyInstanceUID (`../product/RADIOLOGY_WORKFLOW.md` §"S1") and a queue that groups by patient | **P1** | Radiologists do this constantly and the screen cannot yet. Cost is in the queue, not the AI |
| **Follow-up tracking** | **A Task the ERP owns** (`../DOMAIN_MODEL.md` now defines Task and says the copilot may only propose one) | **P2** | The value is real — an interval nobody books is an interval nobody keeps — but it is an ERP feature wearing an AI name. Building a task engine in FutureKind would be a second system of record |
| **Incidental findings** | A profile field for "seen, not asked for" plus a route into Recommendations; the out-of-scope list already does the inverse job | **P1** | MRI's likely failure mode is named as "wrong protocol named, or an incidental finding dropped" (`RADIOLOGY_WORKFLOW.md` §2). Cheap once profiles exist; and `dropped_observation` covers the dictation side but not the *undictated* observation — an honest gap |
| **BI-RADS** | Exists in design and in cases: `SKILL_LIBRARY.yaml:605` and `:641`, `GOLDEN_DATASET.yaml:748`, `:884` | **P1, gated** | It is the only graded workflow with golden cases, and also the two-reader one (`PRODUCT_SPECIFICATION.md:138-140`). Gated because breast service does not exist at either site yet |
| **TI-RADS** | `SKILL_LIBRARY.yaml:432` — thyroid US, and `us-thyroid` is a live OPD workflow at CARE Diagnostics | **P1** | The cheapest grading system to realise: the modality is already the flagship outpatient one (`PRODUCT_SPECIFICATION.md:134-137`) |
| **Lung-RADS** | `SKILL_LIBRARY.yaml:250` (`ct-chest-lung-nodule`) | **P2** | Needs nodule-level structure before a category means anything, so it waits for structured findings |
| **PI-RADS, LI-RADS, Fazekas, Bosniak, SONAQ, NYHA** | **None of these exists anywhere in this repository** — no skill stanza, no profile, no golden case | **Not scheduled** | Naming the absence is the point: these are the brief's list, and the design has nothing for them. Each needs §1's five decisions from a clinician, and Prostate/Liver protocols need a profile before a category can be checked. Fazekas is the cheapest (it belongs to `mr-brain-dementia` `:334`, which exists as a skill and has a brain profile to extend) |
| **ASIA / GCS** | Already skills: `SKILL_LIBRARY.yaml:712` and `:663`, with the arithmetic-refusal rule written for GCS (`SKILL_EXAMPLES.md:344`) | **P1** | The refusal-on-bad-arithmetic behaviour is the family pattern §7 of the safety guide requires; it exists and should be reused, not re-derived |
| **Stroke workflow** | `ct-head-acute-stroke` `:189`, `ct-perfusion-stroke` `:213`, and `neuro-stroke-thrombolysis-check` `:687` which is `beta` **because the platform cannot verify an approval** | **P1, half-blocked** | The drafting half is shippable; the decision-support half is honestly blocked. This is the flagship demonstration at the neurotrauma site (`PRODUCT_SPECIFICATION.md:129-133`), so the block matters |
| **Trauma workflow** | `ct-head-trauma` `:201`, `xr-trauma-survey` `:553`, `ct-spine-trauma` `:285` | **P1** | Three critical skills, all `alpha`, all imaging-dictation-shaped — the same code path as today's product |
| **Neurosurgery correlation** | §9 below | **P1** | The owner's own specialty and the department that decides whether the platform stays |

**Not prioritised, deliberately:** more checks. Nine exist; the measured result of last night is
that a tenth would have added 17 flagged words per correct report to catch 85 % of a probe column
that is mostly invented *diagnoses* (`ROADMAP.md` §4.1). The next quality improvement in radiology
is structured findings, not prose policing.

### 2.1 The one-sentence plan

Get structured findings into the document model, because five features on that list are the same
feature once the model has fields; then two profiles (CT head, US abdomen) measured the way MRI
brain's was; then comparison mode, which is the only item that needs a screen and a prior report
traveling in the request.

---

## 3. Pathology Copilot

**Why it is second by design, not by taste:** it is already in the v1 definition
(`PRODUCT_SPECIFICATION.md:224`), and its skill is already authorised and called by nobody
(`core/gateway/models.yaml:68`).

### 3.1 The document

A surgical pathology report is one page with five parts, and the ordering is the diagnosis:

| Section | Written by | Locked on screen | Notes |
| --- | --- | --- | --- |
| Specimen and clinical history | The request, copied | **Always** | Same rule as the radiology indication: the machine must not paraphrase what was asked |
| Gross (macroscopy) | The prosector — usually a trainee | Never | The one section where the AI can only reformat. It is dictated or typed after the specimen is cut, so a draft here has no source to be grounded against until the gross description exists |
| Microscopy | The pathologist's dictation | Never | Where the product's value is: prose → structured |
| Diagnosis | The pathologist | Never | The report's *headline*, not its last paragraph. `SKILL_LIBRARY.yaml:974` states the shape: "structured report ending in a diagnosis line with margin status" |
| Comment / correlation and IHC | The pathologist | Never | The section where a category system is asserted, so it is where certainty drift is most dangerous |

### 3.2 Boundaries that are not negotiable

| Must never be AI | Reason |
| --- | --- |
| A **margin status** or a node count | Both are counts of things examined. A number the microscopist did not dictate is a stage, and a stage is a treatment |
| A **Bethesda category** or any reporting category | A category *mandates* a next step (`SKILL_LIBRARY.yaml:985`); proposing one from incomplete adequacy text is a decision about a patient |
| An **IHC panel suggestion** as advice | The panel is chosen against the morphology in front of the pathologist. A draft may list what was *reported*, never what *should be ordered* — ordering is out of scope (`../SPECIFICATION.md:140-144`) |
| A **frozen section** answer under time pressure | The intraoperative consult is the one act where a draft's latency changes what the surgeon does next, and the platform has no measured latency at all (`PRODUCT_SPECIFICATION.md:243`). Frozen sections get formatting help and nothing else |
| A **molecular or genetic** result | Reported by an external or a specialised lab: the object here is a *result received*, so the application must read it, not restate it |
| Case-level **sign-out** without a human transition | P11; and the ERP already refuses a machine signer (`../integration/INTEGRATION_CARE_ERP_PACS.md:252`) |

### 3.3 What transfers from radiology, and what does not

Six checks transfer as shape (`APPLICATION_MAP.md` §6). What must be re-authored before a
pathology report can be drafted here: a diagnosis-vs-microscopy grounding rule (the equivalent of
"no measurement nobody dictated" is "no entity nobody described"), a category-consistency rule,
and a specimen chain that the ERP does not document (`APPLICATION_MAP.md` §7). **The measurement
gap is the real cost**: no pathology golden case exists, so every severity decision the suite
would make is currently unmeasurable. First work item, before a prompt: 20 ratified surgical
pathology reports from the hospital's own records.

---

## 4. Physician Copilot — ward, OPD and internal medicine

**Document shapes** (one application, three documents — not three applications):

| Document | Sections | AI may draft | AI may never |
| --- | --- | --- | --- |
| Daily ward note | Interval, examination, lines/drains/ventilator, systems review, plan | The reformat of dictated text into the interval/plan shape | The plan. A plan is a decision, and `SKILL_LIBRARY.yaml:790` marks the note itself `moderate` precisely because the plan inside it is the clinician's |
| Problem list reconciliation | Active / resolved / new, with the evidence for each change | The pairing of a problem against documented evidence it found | Dropping a problem. A silent omission from a problem list is the ward equivalent of `dropped_observation`, and this application must ship that check on day one |
| Clinical summary | Reason, course, events, current state, discharge plan | Structure and continuity of prose | Any inference across an admission the record does not state |

**Differential diagnosis.** `SKILL_LIBRARY.yaml:1553` designs `differential-diagnosis-check`, and
it is the one skill in the library whose name tells you what it is for and whose status is `alpha`
while the measurement story for it is missing entirely. The suite's position: a differential
**check** is admissible as *a list of what the record already supports*, is never admissible as
advice on what to do, and must present itself in the same visual register as the evidence rather
than as a ranking — the automation-bias rule in `../safety/CLINICAL_SAFETY.md` §4. Nothing in
this repository has measured whether a machine-generated differential changes a resident's
management, and guessing at that is how the platform gets used by the person in a hurry at 3am.

**Medication review** is read-only by construction (`../DOMAIN_MODEL.md`, Medication): the note
may list what was given and flag what the record contradicts; it may not stop, start or change a
dose.

---

## 5. Theatre (OT) Copilot

| Stage | What the application does | What it must not do |
| --- | --- | --- |
| Pre-op | Draft the anaesthetic assessment from the record: history, airway, ASA-grade-relevant facts, drugs, allergies | Assign the ASA grade. It is an anaesthetist's judgement about risk, not a sum of fields |
| Checklist | **Nothing.** A surgical safety checklist is signed by humans at defined moments; an AI that pre-ticks a box destroys the only value the checklist has | Any write to a checklist state |
| Operative note | Structure dictated narrative into procedure / steps / bleeding / implants / specimens, with an implant list taken only from what was dictated | Invent an implant, a size, a laterality or a specimen label. Implants have no documented ERP object at all (`APPLICATION_MAP.md` §7), so today they are prose, and prose is where the wrong serial number goes |
| Post-op | Draft instructions and the handover, from the note and the record | Extend an interval or a dose beyond the record |
| Complication | Record the claim of relationship when a clinician makes one | Characterise causality |

The whole application is a *dictation problem with a legal document at the end*: its highest-value
feature is the implant and specimen list being extracted faithfully, which is exactly what
structured findings (§2) makes possible. Same dependency, same order.

---

## 6. Emergency, Critical Care, Discharge, Coding, Tumour Board

| Application | The document | What is genuinely new here | The boundary that decides the design | Rank |
| --- | --- | --- | --- | --- |
| **Emergency** | Triage note; pathway record; discharge instruction | The clock. Every other copilot's latency target is comfort; here a 20 s p95 is a patient waiting (`PRODUCT_SPECIFICATION.md:129-133`) | Time-critical decision support is `beta` until an approval can be verified — `neuro-stroke-thrombolysis-check` `SKILL_LIBRARY.yaml:696` says exactly that | **P1** (drafting only) |
| **Critical Care** | ICU bulletin; sedation and transfusion records; family briefing | It reads a timeline rather than a study, so it is the first copilot that needs #10's read-model before it is comfortable | A transfusion reaction is both a clinical act and a statutory notification (`SKILL_LIBRARY.yaml:1089`) — so the record is drafted and the *notification* is a human act | **P2** — needs ward data this repository has not documented |
| **Discharge** | Discharge summary; referral letter; follow-up plan | The lowest clinical risk per document and the largest recovered clinician-hours (`PRODUCT_SPECIFICATION.md:145-149`) | The letter is read by a doctor who was not there; every claim must carry its evidence. `medication-reconciliation` `:810` is `critical` and belongs to this document | **P1, and the cheapest second build** |
| **Coding** | ICD-10 and procedure suggestions; authorisation and appeal letters | Nothing about it needs a scanner, and the harm is financial-legal rather than clinical | The suggestion may never be the reason a service was billed (`PRODUCT_BIBLE.md` §6.4) | **P1** for revenue-side value, **P2** for clinical trust |
| **Tumour Board** | One board summary; staging note; plan; survivorship or palliative plan | Several clinicians are bound by one document, so the record must show who decided | It **cannot ship** before ADR-0005 (`SKILL_LIBRARY.yaml:1226`), and building it anyway would be a signature pretending to be a platform approval | **Design only** |

---

## 7. Patient-facing text

Three skills, one surface (`PRODUCT_BIBLE.md` §3.2, #12): the plain-language summary, the
pre-procedure instruction, and the fasting/medication instruction. Two rules make this different
from every other application in the suite:

1. **A clinician approves the exact words a patient will read.** Not the gist, not the template —
   the rendered text, because this is the only output in the suite whose reader has no other way
   to check it.
2. **Legibility is a check, not a style.** A sentence a fourth-reader cannot follow is a failed
   draft, and the check for it is measurable today (readability of the output vs the source).
   This is the one place where the suite should *add* a check, and it should be added with the
   same measurement discipline as the nine in radiology.

PCPNDT and foetal sex remain an absolute: the ERP's ultrasound safety core already drops any
suggestion that states fetal sex before display (`core/gateway/models.yaml:104-120`), and the
rule belongs to every patient-facing document in India, not only to ultrasound.

---

## 8. The consoles

| Console | The rule that keeps it honest | First three indicators worth printing |
| --- | --- | --- |
| **Hospital Command Center** | **No metric without a counted event and a written definition.** `turnaround-time-brief` `SKILL_LIBRARY.yaml:1591` and `cohort-extraction` `:1566` are the two skills that expose this: a TAT number needs a start event and an end event in the ERP, and a cohort needs ADR-0007. Printing "reports/hour" from an 18-second session is the mistake the validation dashboard already refuses to make (`ROADMAP.md` §4b) | Studies signed same day; median TAT by modality; drafts produced vs drafts signed unchanged |
| **Clinical QA and Peer Review** | It measures *people and process*, so it must be legible to the person being measured, and its numbers must be reproducible from stored rows. `scripts/validation/dashboard.py` already does exactly this for one department (`APPLICATION_MAP.md` row #14) | Blocking findings per 100 correct drafts (table 4's number); substantive amendment rate, once the classification named in `RADIOLOGY_WORKFLOW.md:381` exists; critical-value acknowledgement rate |

`quality-indicator-audit` `SKILL_LIBRARY.yaml:1454` and NABH-facing reporting belong here, and so
does the discipline the roadmap already states about accreditation: the platform can produce the
record; it cannot assert compliance, because compliance is a hospital's own signed claim.

---

## 9. The neurosurgery thread

Five applications in this suite meet the same patient, and the specialty that will decide whether
the platform is adopted is the owner's own. The brief asks for neurosurgery specifically, so here
is the same design seen as one thread rather than five features:

| Moment | What exists today | What is missing |
| --- | --- | --- |
| **Trauma, minutes after arrival** | `ct-head-trauma` `:201` and `xr-trauma-survey` `:553` are `alpha` critical skills; `neuro-traumatic-brain-injury-classification` `:675` too; GCS refuses bad arithmetic (`SKILL_EXAMPLES.md:344`) | The report is drafted after the patient has been to theatre. What a neurosurgeon needs at minute ten is the *dictation-to-text* path with the image already in front of them, which is S5's viewer — unbuilt (`RADIOLOGY_WORKFLOW.md` §1) |
| **Stroke, the hour window** | `ct-head-acute-stroke` `:189`, `ct-perfusion-stroke` `:213` | `neuro-stroke-thrombolysis-check` `:687` is `beta` on ADR-0005. The drafting half ships; the decision-support half honestly may not |
| **Tumour, the planning conversation** | `mr-brain-tumour` `:298`, and the brain profile's fourteen structures are already the right coverage list | **No vision, no pixels** — a platform principle (`SKILL_LIBRARY.yaml:14-16`), so operative planning help is text-and-number only: segment volumes reported by others, never proposed by the model |
| **Spine** | `mr-cervical-spine-myelopathy` `:346`, `mr-lumbar-spine-radicular` `:358`, `ct-spine-trauma` `:285`, ASIA `:712` | Three profiles that do not exist; a myelopathy report needs its own structure list before `structure_coverage` means anything |
| **Follow-up and correlation** | Comparison is a defined object now (`../DOMAIN_MODEL.md`); `prior-study-comparison` `:1541` is designed | This is where the suite pays off: the same patient across CT, MRI, angiography, the operative note, the ICU bulletin and the discharge summary is a **Timeline** (application #10) — and the Timeline is blocked on the identifier this document refuses to guess (`../DOMAIN_MODEL.md` Q2) |

**The prioritised neuro answer:** stroke drafting and the trauma pathway now; spine profiles next;
the cross-study correlation only after the identifier decision — because a neurosurgeon who sees
an incomplete timeline will not use it twice, and a wrong one is worse.

---

## 10. Before any of this runs on a patient

Every application in this suite passes the same five-gate entry checklist, owned by
`../safety/CLINICAL_SAFETY.md` §6. The suite's contribution is only the ordering, and it fits in
one line: **finish measuring radiology, then build the document that needs no new object —
discharge — then pathology, whose skill is already authorised and whose cases are not.**

*FutureKind · Genesis Night 3 · 2026-10-09. No feature in this document has been used by a
clinician. The two claims that would surprise a reader are true and checked: `pathology-review` is
already authorised in configuration, and none of PI-RADS, LI-RADS, Bosniak, SONAQ or Fazekas
appears anywhere in this repository.*
