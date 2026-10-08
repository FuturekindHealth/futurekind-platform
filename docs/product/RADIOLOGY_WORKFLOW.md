# Radiology Copilot — the complete clinical workflow

**FutureKindAI Health Alpha · flagship product · deployment targets: CARE Diagnostics and
Hope Neurotrauma & Multispeciality Hospital**

This document traces one patient from arrival to a signed report sitting in the HIS,
the ERP and the PACS, and specifies every step in the twelve attributes a deployment
needs to be able to audit it: **User, Input, Output, AI action, Doctor action, Approval,
Audit, Possible failures, Recovery, Latency, UI, API.**

It is a product and integration design, not an architecture proposal. The platform
below it — Gateway → LiteLLM → provider — is accepted as built
(`ADR-0002`, `docs/SPECIFICATION.md` §5–§7) and is not redesigned here.

---

## 0. The five decisions this workflow rests on

Each one was forced by something already running in the two hospitals, not chosen for
elegance. They are stated up front because they contradict the obvious design.

**D1 — FutureKind does not become a reporting studio. It becomes the drafting and
sign-off engine inside the studios that already exist.**
`usg-reports` (CARE USG Studio, deployed at the reference clinic) already has a worklist, a
structured composer, PDF printing, secure share links, an append-only audit table and a
DICOM-SR write-back to Orthanc. `care-erp` (CARE ERP) already owns the order,
the accession, the patient identity, the report record and the callback that delivers a
signed report to Hope. Rebuilding any of that would be the classic way a platform dies:
a second system of record. FutureKind supplies the *draft*, the *document* and the
*gate*, and hands the result to the ERP endpoint that already exists.

**D2 — For structured studies the AI proposes items; it does not write the report.**
The USG studio's existing AI path already enforces this and it is better than a prose
draft: the model returns pathology chips keyed to organs, "the AI never writes to the
report", and the radiologist accepts per item (`ai-draft/route.ts:17-18`,
`UsgAiDraftPanel.tsx:122-141`). FutureKind adopts that as the default for
organ-by-organ studies (ultrasound, mammography, cardiac) and reserves prose drafting
for dictated modalities (CT, MRI, X-ray), where the radiologist dictates findings and
the model structures them. A per-item accept/reject is auditable in a way a paragraph
never is — `DOMAIN_MODEL.md` Observation exists to make reports decomposable
individually, and the chips implement it without waiting for that entity to be ratified.

**D3 — The patient identifier never enters the AI path, and the study identifier is the
only key that does.**
The ERP has no MRN column; the real keys are `patients.patientId` (a UHID like
`P-00010`, `patients.ts:7`) and `radiology_studies.accessionNumber`
(`ACC-YYYYMMDD-MOD-NNN`, unique, `radiology.ts:11,16,72`). The AI request carries the
accession and the `StudyInstanceUID` as *document references* and the clinical narrative
as text; it never carries the UHID, the name or the phone number, because the Gateway
sees care text, not care identities (`SPECIFICATION.md` §6.4, Constitution P10). This
also answers `DOMAIN_MODEL.md` Q2 without inventing an identifier format: the answer is
"none inside the AI path".

**D4 — Human approval is mandatory, and in Alpha it is enforced twice, in the wrong
place on purpose.**
`radiology-report` runs with `approval_required: false` in `core/gateway/models.yaml:54-66`
because the Gateway *refuses* any skill that declares it: there is no approvals service,
so `policy.py:305-320` raises `403 approval_required` rather than pretend
(`gateway-policy.md:213` — "Approval is a refusal, not a workflow"). Meanwhile the
customer requirement and Constitution P11 make sign-off non-negotiable. The honest Alpha
design is therefore two gates the hospital can see today — the copilot refuses to export
unsigned (`copilot.py::export`, `409`), and the ERP refuses to deliver a report that has
not been signed and verified (`patientReports.ts:6-13`, `draft → pending_verification →
verified → delivered`) — with `ADR-0005` the one decision that moves the gate into the
platform. Nothing here claims the platform verifies an approval. That claim would be a
falsifiable signature, which is what `DOMAIN_MODEL.md:364-365` warns about.

The sharpest form of this contradiction is the **critical-skill deadlock**, and it is worth
stating because it decides which skills can ever ship: a `critical` skill declaring
`approval_required: false` fails catalogue load (`policy.py:242-252`, "a critical skill may
not run without sign-off"), and one declaring `true` fails every request at runtime
(`403`). So of the 121 designed skills, **the 37 marked `critical` are unreachable by either
declaration** — safely unreachable, which is the right failure direction, and the reason
`radiology-report` itself is declared `high` rather than `critical`. ADR-0005 is not a
feature request; it is the only key that opens that class. (Full analysis with the
line-by-line table: `SKILL_EXAMPLES.md` §A6.) Note also that this makes the `clinical_risk`
value in a stanza a **capability decision, not only a clinical one**: had `radiology-report`
been declared `critical` instead of `high` (`models.yaml:62`), the flagship skill would not
load at all — which is exactly the kind of coupling `DOMAIN_MODEL.md` Q6 asks the clinical
owner to confirm rather than inherit from an engineer.

**D5 — The PACS write path goes through the ERP, because the PACS has no authentication
at all.**
`orthanc.json:6-7,24` sets `AuthenticationEnabled: false`, `RemoteAccessAllowed: true`
and CORS `Access-Control-Allow-Origin: "*"`, and `docker-compose.production.yml:10`
publishes `8042:8042` raw on the NAS. So `/dicom-web`, `/wado` and the whole native REST
API are anonymous read **and write** to anyone on the LAN or Tailscale. FutureKind will
not write to an unauthenticated store of record; it hands the signed report to the ERP,
which already archives an Encapsulated PDF into Orthanc
(`pacsArchive.ts:217,224-231` ← `internal-radiology.ts:1319`, SOP class
`1.2.840.10008.5.1.4.1.1.104.1`). Closing that anonymous door is a deployment
prerequisite, listed in `docs/security/THREAT_MODEL.md`, not a FutureKind feature.

---

## 1. The spine: twelve steps (S0–S11), patient arrival to peer review

Steps are the same for every modality; where they differ, §2 gives the per-modality
table. Times are **targets**, and the measured column states honestly what has been
measured: only the platform plumbing, against a stub backend, on one machine.

### S0 — Registration and order (ERP)

| Attribute | Specification |
| --- | --- |
| User | Front-desk staff at Hope; referral coordinator or walk-in at CARE Diagnostics |
| Input | Patient identity (new: create UHID; existing: search by name, phone or `patientId`), the referring doctor's order, the requested study, clinical indication in the referrer's words, booking slot |
| Output | One `orders` row with `orderNumber`, one `radiology_studies` row with a unique `accessionNumber` (`ACC-YYYYMMDD-MOD-NNN`), and a worklist entry keyed by `StudyInstanceUID` |
| AI action | **None.** No model is called before acquisition. Optional: an indication-completeness check that flags "Chest PA" ordered for "follow-up" with no question stated — a `fast` capability suggestion, never a block |
| Doctor action | None at this step |
| Approval | Not applicable — no clinical statement exists yet |
| Audit | ERP writes its own order trail. FutureKind records nothing |
| Possible failures | Duplicate patient created (name/phone search misses), wrong modality ordered, indication blank, study booked for the wrong site |
| Recovery | Duplicate-merge path in the ERP; blank indication is the one case the platform can surface, and it must surface it as a *prompt to the staff*, not as a refusal — the acquisition may still be clinically necessary |
| Latency | Under 60 s human work; no AI in the path |
| UI | Existing ERP registration screen. Nothing new. One added field prominence: **clinical indication is required to be non-blank before a study can be booked**, with an explicit override that is recorded |
| API | ERP `GET /api/patients?search=` (`routes/patients.ts:85,97-104`); order creation via existing ERP routes; `GET /api/radiology/worklist?date=&status=&modality=` (`routes/radiology.ts:335`) |

### S1 — Modality worklist reaches the console

| Attribute | Specification |
| --- | --- |
| User | Technical staff at the modality console; the puller as an automated user |
| Input | The ERP order; console identity (modality, room, AETitle) |
| Output | The patient and study list on the console, with the indication visible to the radiographer |
| AI action | None |
| Doctor action | None |
| Approval | None |
| Audit | ERP worklist read is logged; the file-drop itself is not |
| Possible failures | Study never appears at the console; appears on the wrong modality; indication missing so the radiographer does not know what to protocol for; MWL silently stale because the watched folder fill failed |
| Recovery | Manual pull from the console (`GET /api/internal/radiology/mwl-orders`, `internal-radiology.ts:2168`); the indication is also printed on the physical requisition — the workflow must degrade to paper without losing the indication, because the indication is what the AI draft needs at S4 |
| Latency | Order-to-console under 2 minutes |
| UI | Console-side, out of FutureKind's scope. FutureKind's queue view (S4) must show the same list independently so a missing MWL entry is visible to the reporting radiologist, not only to the technologist |
| API | Today: ERP writes MWL files into a watched folder (`care-pacs/docker-compose.yml:79-80`) — a shared-directory contract, not an API. Replacement in the roadmap: DICOM MWL-SOP or a REST pull at the console |

### S2 — Acquisition

| Attribute | Specification |
| --- | --- |
| User | Radiographer / sonographer / MHT |
| Input | Patient, protocol chosen from the indication, prior studies for comparison |
| Output | DICOM study arriving in Orthanc with `StudyInstanceUID`, series, dose records; for ultrasound, live images and the operator's spoken or typed observations |
| AI action | None during acquisition. **Deliberately.** An AI that advises on protocol in real time would need either a live image feed or a vision capability; neither exists (`README-ROUTING.md` lists vision as unfinished work), and the consent, latency and liability are not Alpha's |
| Doctor action | For ultrasound, the reporting clinician is usually present and forms the findings there and then |
| Approval | None |
| Audit | PACS arrival event lands in the ERP through `/api/internal/radiology/orthanc-webhook` (`internal-radiology.ts:1778`) or `/radiology/dicom-event` (`:1727`) |
| Possible failures | Retained or incomplete study, wrong patient protocol, dose index out of range, study arrives with no matching order, series dropped, movement artefact making the study non-reportable |
| Recovery | Repeat acquisition with the reason recorded; the `radiology-study-quality-check` skill produces the recall or re-protocol advice at S4 rather than at the console |
| Latency | Modality-dependent, 10–45 minutes. Not a FutureKind number |
| UI | Console-side |
| API | DICOM C-STORE into Orthanc; ERP webhook to mark `STUDY_RECEIVED` (`radiologyWorklist.ts:7-8,38`) |

### S3 — Study appears in the reporting queue

| Attribute | Specification |
| --- | --- |
| User | Reporting radiologist; the queue is the unit's front door |
| Input | Study arrival, accession, indication, patient history available in the ERP, priors |
| Output | An ordered queue: critical first, then time-since-acquisition, then modality |
| AI action | `radiology-worklist-triage` (`fast`, moderate risk, **no approval needed and none obtained** — it reorders a list and writes nothing clinical). It reads indication text only |
| Doctor action | Picks the study. The promotion is advisory; a nurse or consultant escalation path exists outside the AI for anything genuinely time-critical |
| Audit | Every triage run is audited with the study count and the promotions it made, never with clinical text |
| Possible failures | Critical study buried; triage invents urgency from an ambiguous indication; queue pulls stale data because the ERP call failed |
| Recovery | Queue falls back to pure acquisition-time order within 3 seconds of any triage failure, and shows *"ordering without AI"* in the header — never silently. A failed AI path must never stop a radiologist reporting |
| Latency | Queue render under 1 s; triage under 2 s for 50 studies |
| UI | Study Queue (see `docs/product/UI_UX.md` §2). Colour, icon and text all carry the priority, so a colour-blind radiologist on a sunlit screen still sees it |
| API | `GET /api/internal/reporting-studio/worklist` (`internal-reporting-studio.ts:263`) and `GET /api/radiology/worklist` (`radiology.ts:335`); FutureKind `/triage` for the ordering |

### S4 — Dictation and the AI draft

This is the step the product exists for.

| Attribute | Specification |
| --- | --- |
| User | Reporting radiologist (CT, MRI, X-ray, Mammography) or sonographer-clinician (ultrasound) |
| Input | Clinical indication (from S0, never re-typed), modality and study name, technique if the department holds it, the clinician's dictated or typed observations, and any previous report the department supplies for comparison (≤5, ≤2 000 characters each, ≤6 000 in total). For ultrasound: the organ-by-organ composer state instead of prose |
| Output | The twelve-part report document: six clinical sections (`clinical_indication`, `technique`, `findings`, `impression`, `recommendations`, `follow_up`), `quality`, `confidence`, `metadata`, `model_provenance`, `skill`, `policy` — with status `pending_review` |
| AI action | `POST /chat {"skill": "radiology-report", …}` → Gateway resolves skill → capability `reasoning` → alias `fk-reasoning` → LiteLLM chooses the deployment → `ollama/qwen3:14b`. The model authors `findings`, `impression`, `recommendations`, `follow_up` and (only when no technique was supplied) the technique declaration. The `clinical_indication` and a supplied `technique` are taken from the submission, never from the answer. `quality` and `confidence` are computed by the copilot, not authored by the model — nine deterministic text-grounding checks and one computed grade, so nothing here is the model grading itself |
| Doctor action | Starts the draft, then reads it section by section. Nothing is accepted by a single button that also signs |
| Approval | **None granted here.** The document leaves this step explicitly unsigned, and the UI must not let a keyboard shortcut imply otherwise |
| Audit | Three Gateway lines, none carrying text: `skill_audit` (`{request_id, skill, capability, clinical_risk, approval_required, alias, answered, provider, model, downgrades_allowed}`, `service.py:342-355`), `chat_completed` (`{… attempts, degraded, latency_ms, prompt_tokens, completion_tokens, content_chars}`, `service.py:448-465`) and `request_completed` (`{… status, duration_ms, caller}`, where `caller` is an 8-hex digest of the credential, never the key — `app.py:349-357`, `deps.py:67-73`), plus a copilot-side record of prompt version and the section text the model returned. **No prompt or completion text in any Gateway log** — the copilot stores the document because the document is the clinical artefact, not a log |
| Possible failures | See §3: prose instead of JSON, a missing or empty section, `finish_reason == "length"`, a degraded substitution, an unreachable Gateway, a refused policy, a timeout, a study the model has no useful text for |
| Recovery | Every failure produces a *visible empty draft with the reason*, not a partial document and not a silent retry. The radiologist dictates directly into the fields — that path is always available and is the reason the product is an assist and not a dependency. Re-draft is allowed with a reviewer note (`extra_instructions`) |
| Latency | Target 8 s to first useful draft, 20 s p95, hard ceiling the skill's own 90 s policy timeout (`models.yaml:66`). **Measured today: 27–30 ms end-to-end against a stub LiteLLM; a real `qwen3:14b` on the hospital's machine has never been timed here, and that number is the single most important unknown in this document** |
| UI | AI Draft pane beside the report composer, section-by-section, never a full-screen replacement. Dictation stays editable while the draft is in flight |
| API | FutureKind `POST /draft`; internally copilot → Gateway `/chat`; alias contract verified at Gateway startup against `configs/litellm/config.yaml` (SPEC-07-03) |

### S5 — Comparison viewer and verification of the draft against the images

| Attribute | Specification |
| --- | --- |
| User | Reporting radiologist |
| Input | The draft sections, the study in OHIF, the prior study, and — for the copilot — the prior **report text** submitted with the study as `previous_reports`. The copilot compares against that text only; it never sees pixels |
| Output | A verified draft: sections edited to match what the images actually show, and the report still unsigned |
| AI action | `prior-study-comparison` on request — describes change per lesion between the current dictation and the prior *report text*, never the prior pixels. `differential-diagnosis-check` on request for cases the reporter is uncertain about. Both are designs (`docs/product/SKILL_LIBRARY.yaml`); the drafting path is the only one that runs |
| Doctor action | Looks at the images. This step exists to make the AI draft a starting point rather than an answer to be rubber-stamped |
| Approval | None yet |
| Audit | Section-level edits are recorded as `metadata.review.amendments` at S6; the viewer launch itself is recorded by the ERP |
| Possible failures | Radiologist approves without looking (automation bias — the central risk of this product); OHIF will not launch; prior study not retrievable; the AI comparison silently misattributes a lesion to the wrong side |
| Recovery | See §4, which treats automation bias as a design requirement, not a training problem |
| Latency | Viewer first-paint under 3 s on LAN; prior-study text fetch under 1 s |
| UI | Comparison Viewer, Images pane left / report right, 60:40 split, side-by-side priors |
| API | Viewer launch is the ERP's existing template — `{OHIF_BASE_URL}/viewer?StudyInstanceUIDs={uid}` (`networkDefaults.ts:93-94`, base = the installation's `OHIF_BASE_URL`); image fetch over `/dicom-web` (`care-pacs/ohif/enterprise/default.conf:43-45` → `orthanc:8042`); priors via ERP `GET /api/patient-reports/patient/:patientId` (`patient-reports.ts:1396`) |

### S6 — Sign-off (the human approval step)

| Attribute | Specification |
| --- | --- |
| User | The reporting radiologist, individually authenticated |
| Input | The verified document, **the submission it was drafted from** (no submission, no signature — the checks have nothing to compare the edited text against), the clinician's name and registration number, optional amendments, optional comment |
| Output | The same document with `metadata.review.state = "signed"`, `clinician`, `reviewed_at`, `amendments`, and the quality pass and confidence recomputed over the amended text; then exported |
| AI action | **None, by construction.** No model call can sign. There is no endpoint that accepts an approval from an AI path, and the copilot's review body has no field an automated caller could satisfy with a boolean. A blocking quality finding also refuses the sign-off — `{"blocking": [{check, section}], "sections": […]}`, check names and section names only, never the clinical text |
| Doctor action | Signs. Amending is normal, expected, and never locks the document — a signed report can be reviewed again and re-exported. A section they rewrote has its findings downgraded to advisory, because the image rather than the dictation is their source of truth; the downgrade follows the section they edited, not a flag that says a human has been involved |
| Approval | This is the approval. Two implementations, deliberately: the copilot writes it into the document (`copilot.py::review`) and the ERP writes its own signature and verification columns (`patient-reports.ts:2371,2574` — `sign`, `verify`, with `signedByName`, `signedAt`, `verifiedByName`, `verifiedAt`, `patientReports.ts:38-46`) |
| Audit | Copilot: who, when, which sections a human rewrote. ERP: signature id, registration number, and a role check that refuses to sign as `typist|ai|system|bot` (`radiologyD1FinalWriter.ts:76`) — that ERP guard is exactly the rule this product needs, and it is already written |
| Possible failures | Single shared credential pretending to be an individual signature (see the note below); signature recorded in one system and not the other; withdrawal after a report has been delivered; two reviewers editing one document |
| Recovery | The ERP already supports `withdraw-signature` and `amend` (`patient-reports.ts:2869,1555`); a withdrawal after delivery is an amendment with a reason, not a deletion, and both systems keep their own trail keyed by the same `report_id` |
| Latency | Under 2 s. Sign-off must never feel expensive, or people will batch it |
| UI | Approval Screen: the six sections, the quality findings and the computed confidence above them, the diff against the model's original text, the name and registration pre-filled from the session, one confirm that states what is being attested. While any finding is blocking, the confirm is disabled |
| API | FutureKind `POST /review` then `POST /export`; ERP `POST /api/internal/reporting-studio/finalize` (`internal-reporting-studio.ts:736-750`) |

> **The blocking identity defect.** The USG studio authenticates with **one shared PIN**
> for the whole clinic (`usg-reports/src/lib/auth.ts:10-27`, login accepts a `pin` plus a
> device-trust flag, `app/api/auth/login/route.ts:7-19`), has no role table at all, and
> stores the radiologist's identity as *clinic-level settings*
> (`usgDoctorName/usgDoctorQual/usgDoctorRegNo`, `schema.prisma:91-93`) rather than per
> report. The MRI studio has **no authentication whatsoever** — no middleware, no session
> table, `next-auth` declared and never imported. So "a named human owns every clinical
> statement" (P3) is currently unprovable in both studios: the name on the report is a
> setting, not a login. Individual authentication of the signer is a **hard prerequisite
> for Beta**, ahead of any new AI capability. This is the single most important line in
> this document for the security review, and it is a hospital-side identity change, not a
> FutureKind feature — which is why the roadmap puts it in the Beta gate.

### S7 — Delivery into the HIS/ERP as the record of truth

The ERP is the system of record. FutureKind is the system of drafting. Nothing in this
step should make the platform the place a report is looked for.

| Attribute | Specification |
| --- | --- |
| User | The reporting radiologist's sign-off triggers it; the ERP receives it |
| Input | The exported signed document plus the ERP `report_id` / `accessionNumber` pair it belongs to |
| Output | The report in the ERP at state `delivered`, visible to the referring clinician; an outbox event so any subscribed external system learns the same thing |
| AI action | **None.** An AI path has no credential that can mark a report delivered — the ERP's own writer refuses a signer identity matching `typist\|ai\|system\|bot` (`radiologyD1FinalWriter.ts:76`) |
| Doctor action | None beyond S6. Delivery must be automatic on signature, or it will be forgotten |
| Approval | Consumes the S6 approval; grants no new one |
| Audit | ERP audit row (report id, status transition, actor, timestamp) + the copilot's own export record keyed by the same `report_id`. The two are reconciled by identifier, never by timestamp |
| Possible failures | Signature in the copilot but not the ERP (delivery call fails mid-way); delivered to the wrong patient because the accession was typed rather than carried from S0; duplicate delivery of an amended report; outbox event accepted and the report not stored |
| Recovery | Delivery is idempotent on `report_id` + `sequenceNumber`; a failed delivery leaves the report `verified` and retried, never lost, and the queue screen shows it as undelivered rather than silently retrying. The ERP's outbox already models this (`services/integration/outbox.ts:94-97` — 30 s doubling to a 1 h cap, `pending → sent \| dead`) |
| Latency | Under 3 s p95 from signature to `delivered`; the referring clinician must not be able to refresh and see nothing |
| UI | A delivery line on the Approval Screen stating where the report went and to whom; an *undelivered* badge on the Study Queue that is impossible to miss |
| API | ERP `POST /api/internal/reporting-studio/finalize` (`internal-reporting-studio.ts:736-750`) then the existing status transition to `delivered`. FutureKind does not need a new delivery endpoint — it needs the export to be called with the ERP's identifiers attached |

**The decision this step encodes.** FutureKind hands over a *rendered document*, not a
database write. That is deliberate: the ERP owns the report lifecycle, the version chain
and the audit trail, and it already has all three. A platform that wrote into
`patient_reports` directly would own a second lifecycle, and two lifecycles for one
clinical document is how reports get lost.

### S8 — Archive into PACS so the report travels with the images

| Attribute | Specification |
| --- | --- |
| User | System, on delivery |
| Input | The signed report rendered to PDF, plus the DICOM identifiers of the study it describes |
| Output | One Encapsulated PDF Storage instance (`1.2.840.10008.5.1.4.1.1.104.1`, `Modality: OT`) in Orthanc, in a new report series minted for that study |
| AI action | None |
| Doctor action | None |
| Approval | Requires the S6 signature — an unsigned draft must never be archived, because a PACS series cannot be quietly corrected, only superseded |
| Audit | The archive response's instance id and the revision label written into the series description |
| Possible failures | Orthanc unreachable; archive succeeds but the PDF is an older revision; the same revision archived twice; a study with no `StudyInstanceUID` (bedside and portable films at this hospital) |
| Recovery | The ERP already labels the revision inside the series description — `Radiology Report PDF v{sequence}/{total}` with `SUPERSEDED` or `(amended)` appended (`pacsArchive.ts:205-210`), so an archived old revision is honest rather than misleading. Re-archive on demand by identifier; never delete a PACS series from a reporting tool |
| Latency | Under 10 s after delivery, asynchronous, and never on the radiologist's critical path |
| UI | A *filed to PACS* tick on the report; nothing more. Radiologists should not be asked to care |
| API | ERP `POST {Orthanc}/tools/create-dicom` with `Tags` + base64 `Content` (`pacsArchive.ts:224-234`) |

**Already solved, do not rebuild.** This is the reason D5 says the platform touches no
DICOM. The archived-PDF path exists, is tested (`pacsArchive.d8.test.ts`) and knows how
to label its own versions.

### S9 — The referring clinician and the patient read it

| Attribute | Specification |
| --- | --- |
| User | Referring clinician (ward, OPD, emergency); patient/family on request |
| Input | Patient identifier (UHID `P-000NN` at this hospital — there is no MRN), accession, or the link they were given |
| Output | The delivered report, current revision, with the version history adjacent rather than buried |
| AI action | `patient-explainer` or `plain-language-report` on an explicit patient-side request — a *different skill*, a lower-risk capability tier, and its own watermark |
| Doctor action | Reads, and acts. Referring-clinician acknowledgement is recorded where the host wants it; FutureKind does not invent a read-receipt |
| Approval | None to read. Any patient-facing release is an ERP-side decision with its own consent rules — the platform must not be able to release a report on its own authority |
| Audit | Who viewed which revision. Patient-facing generations are audited at the same weight as clinical ones |
| Possible failures | A patient reads a superseded revision; a plain-language version is mistaken for the clinical one; an emergency report is read by a relative before the clinician has explained it |
| Recovery | Current-revision-only deep links; every patient-facing render carries "this is an explanation of the clinical report, which is the authoritative document" and the signing radiologist's name |
| Latency | Read path under 1 s; patient explanation is a draft and may take the model's normal time |
| UI | Patient View. Two panes, never one: the clinical text and the explanation, with the clinical text marked authoritative |
| API | ERP `GET /api/patient-reports/patient/:patientId` (`patient-reports.ts:1396`); FutureKind `patient-explainer` via `/chat` |

### S10 — Critical results and recalls (the step that has a clock on it)

A finding that must be acted on tonight is not a report that was delivered slightly
earlier. It is a different clinical act, and the design must admit that.

| Attribute | Specification |
| --- | --- |
| User | Reporting radiologist (initiator); on-call/referring clinician (recipient) |
| Input | The signed report plus the criticality the reporter declares, or that `radiology-critical-value-alert` / a modality pathway skill flags in the draft |
| Output | A timestamped notification to a named human, and a record of who was told and when |
| AI action | Flags candidate critical findings **in the draft**. It never raises the notification and never decides that something is critical |
| Doctor action | Confirms or rejects the flag, names the recipient, states the callback window. That decision is the whole medicolegal event |
| Approval | The notification itself must be attributable to a named human on the platform record — this is precisely the case ADR-0005 must settle, and it is why `laboratory-critical-value-review` is the one skill in `SKILL_LIBRARY.yaml` marked `blocked_by: ADR-0005` |
| Audit | Notification raised, delivered, acknowledged — three separate timestamps, not one |
| Possible failures | The model under-flags (a bleed described as "no acute intracranial abnormality" because the dictation was thin); the flag is auto-accepted without reading; no one available to notify; the recipient never calls back and nothing escalates |
| Recovery | Escalation ladder to a duty manager after the callback window; an unacknowledged critical result appears on the next shift's queue, not only the originator's |
| Latency | Notification within 30 minutes of signature by hospital rule, and the system must show the countdown rather than leave it to memory |
| UI | A critical-result banner that survives report closure — visible on the queue and on the next shift's screen until acknowledged |
| API | Needs a new `critical-notification` resource with acknowledgement state. **This is the one place in the workflow where the platform must hold state, because the obligation outlives the report** |

### S11 — Quality and peer review

| Attribute | Specification |
| --- | --- |
| User | Department lead / quality officer |
| Input | A sampled or flagged set of signed reports, with their `model_provenance` and `amendments` attached |
| Output | A scored review, and — the point — department-level numbers about the AI's behaviour |
| AI action | `quality-indicator-audit` as an assist for the human reviewer; `radiology-study-quality-check` remains the pre-report technical adequacy path at S2 and is a different question. Peer review of AI-assisted work by another AI is not peer review |
| Doctor action | Reviews a sample, records disagreements |
| Approval | None; this step audits approvals rather than granting them |
| Audit | Review outcome against the original `request_id`, so a bad draft can be traced to the alias, model, prompt version and attempts that produced it |
| Possible failures | Only the interesting cases sampled, so systematic errors are invisible; the metric measured is report speed rather than report accuracy; amendments are counted without distinguishing an AI wording fix from a clinical correction |
| Recovery | Random sampling as the base rate with flagged sampling on top; `metadata.review.amendments` is already section-level, so it can be split into cosmetic vs substantive by rule rather than by hand |
| Latency | Not a latency-sensitive path |
| UI | Audit Timeline, and the metrics view described in `UI_UX.md` §8 |
| API | Needs `GET /reports/{report_id}` and a list/aggregate endpoint. Today the copilot can only answer about a report it is handed |

**The number this product must earn.** Percentage of AI drafts whose `impression` a
radiologist rewrites, and how often that rewrite *changes the diagnosis* rather than the
phrasing. The first is a style metric and will look flattering; the second is the only
one that tells the hospital whether the AI is safe. `amendments` records the sections a
human touched, so the platform can compute the first for free today and needs a
classification rule for the second.

---

## 2. Modality variations

One skill does not fit five modalities, and pretending otherwise is how a product gets
an "other" category in its own configuration. The differences below are what drive
separate skill ids in `SKILL_LIBRARY.yaml`.

| | **X-ray** | **Ultrasound** | **CT** | **MRI** | **Mammography** |
| --- | --- | --- | --- | --- | --- |
| Who dictates | Radiographer drafts, radiologist signs | Sonographer-clinician reports at the bedside | Radiologist | Radiologist | Reader, then second reader |
| When the report is written | Minutes, high volume, same session | **During** the scan | After acquisition, often same sitting | After acquisition, next day at busy times | Two-pass, deliberately delayed |
| Findings source | Radiologist text over a small image set | Structured organ-by-organ composer, not prose | Scrollable whole-organ series, measured and compared | Long sequences, multi-parameter, protocol-dependent | Standardised descriptors, density, plus priors |
| Draft shape | Short, positive-and-negative template | Per-organ partial drafts, one per section | Structured with measurements | Structured, longest, most protocol text | BI-RADS-category-shaped |
| Capability | `fast` | `fast` for per-chip, `default` for the summary | `reasoning` | `reasoning` | `reasoning` |
| Latency budget | 3 s — a 40-film day dies on latency | 3 s per chip, streamed | 20 s | 45 s, often backgrounded | 60 s; latency is not the constraint |
| Timeout policy | 30 s | 30 s per item | 90 s | 90 s | 90 s |
| Approval | Single reader | Single reporter, and this is the weakest identity in the hospital (see S6 note) | Single reporter | Single reporter | **Two readers** — the only modality where the workflow itself is double-blind |
| Audit emphasis | Volume: draft-acceptance rate drifts fastest here | Whether the human changed what the chip produced | Measurements: a size the model invented is a serious error | Protocol correctness | The second reader's disagreement is the quality signal |
| PACS artefact | Encapsulated PDF on the plain-film study | Encapsulated PDF or DICOM SR (both exist in the ERP today, `usgExtractionHierarchy.ts:24-32`) | Encapsulated PDF | Encapsulated PDF | Encapsulated PDF + exam/prior comparison set |
| Likely failure | Rubber-stamping at throughput | Drafting a finding the operator did not see | Silent number fabrication | Wrong protocol named, or an incidental spine finding dropped | A category the descriptors do not support |
| Skills | `xr-chest`, `xr-extremity-fracture`, `xr-abdomen-obstruction`, `xr-trauma-survey` | `us-abdomen`, `us-kidney-urinary`, `us-thyroid`, and the rest of the US group | `ct-head-acute-stroke`, `ct-chest-pulmonary-embolism`, `ct-abdomen-acute`, `ct-abdomen-oncology-staging` | `mr-brain-epilepsy`, `mr-cervical-spine-myelopathy`, `mr-lumbar-spine-radicular`, `mr-joint-knee-shoulder` | `mg-screening`, `mg-diagnostic`, `mg-density-notice`, `breast-lesion-recall-decision` |

**Where a single skill would have been wrong.** Ultrasound at this hospital is not a
report generated once — it is per-organ AI chips the operator accepts item by item
(`usg-reports/src/lib/aiDraft.ts`). That pattern is the model for D2 ("the AI never
writes the report, it proposes into a field") and it is why `us-*` skills are
`fast`/per-item while `ct-*` and `mr-*` are `reasoning`/whole-report. The roadmap takes
ultrasound first precisely because the workflow already exists and only its AI path is
wrong.

---

## 3. Failure catalogue

Every row is a failure that can happen tonight. Recovery is a requirement, not an
aspiration: a failure with no recovery is a step where the product can lose a clinical
document.

| # | Failure | Where | What the user sees | Recovery / required behaviour |
| --- | --- | --- | --- | --- |
| F1 | Model returns prose instead of one JSON object | S4 | Empty draft, reason "model output could not be parsed" | Keep the dictation intact; offer re-draft once; never partially populate |
| F2 | A required section is missing or empty | S4 | The named missing sections, out of the five the model is asked for | Draft is not offered for signing until sections exist; `parse_model_answer` records them explicitly |
| F3 | Extra sections the skill did not ask for | S4 | Nothing visible; recorded in `metadata.extra_sections`. A returned `confidence` or `certainty` key raises an advisory finding naming it | Discard and record, never silently merge (`report.py` treats extras as data, not text). A model's own confidence is never shown: the `confidence` block is computed |
| F4 | `finish_reason == "length"` — the answer ran out of tokens | S4 | "Output truncated — not a draft" | Hard refuse. A truncated impression is the most dangerous possible artefact in this product |
| F5 | Degraded substitution (a lesser model answered) | S4 | Explicit degraded label in provenance, and the copilot refuses to export it | `allow_downgrade: false` in the skill policy; P13 says label it, this product says block it |
| F6 | Gateway unreachable | S4 | "AI unavailable" banner; the composer is fully usable | Manual dictation path always available; queue falls back as in S3 |
| F7 | Policy not enforced (missing skill/policy block) | S4 | 503 and no document | Already fail-closed in `copilot.py::_check_governance` before parsing |
| F8 | Timeout at the skill ceiling (90 s) | S4 | Reason: timed out, with the elapsed time shown | Offer retry once with lower temperature, then stop; no silent infinite retry |
| F9 | Study text contains nothing for the model to describe | S4 | Empty draft, "no findings were dictated" | Correct behaviour. The product must not invent |
| F10 | Hallucinated finding or invented measurement | S5 | **Partly visible now, and the rest is measured as invisible.** A number that is in neither the submission nor a supplied prior raises `unsupported_measurement`, which blocks sign-off; a finding that was never dictated but is clinically plausible is not detectable from text, and `quality.scope` says so on the screen. Sprint 10 put a number on that sentence: run against the golden set's 310 `must_not_say` probes, the gate newly blocked **3 of the 306 measurable probes** — all three measurements — and 269 of the misses raised nothing at all | Sprint 9 moved this from a §4 hope to an executed check. Measurements in assertive prose are refused, not warned about; §4 still carries section-by-section acceptance and the prior diff, because the images remain the only oracle |
| F11 | Restated clinical indication replacing the clinician's own | S4 | Was the Sprint 7 live defect | Structural: `clinical_indication` is taken from the submission, never from the answer |
| F12 | Automation bias — sign without reading | S6 | Looks like success | §4 requirements; measure the amendment rate, not the throughput. Sprint 9 adds the mechanical half: signing requires the submission, the checks re-run over the amended text, and a blocking finding refuses the signature — so the cheapest way through the gate is to read the flagged sentence |
| F13 | Shared credential used to sign | S6 | Nothing | Blocking for Beta. Individual authentication of the signer |
| F14 | Amended report delivered as a duplicate | S7 | Two reports | Idempotency key on `report_id` + `sequenceNumber`; the ERP version chain already labels supersession |
| F15 | PACS archive fails after delivery | S8 | Report is signed and delivered, not filed | Retry with backoff, show the *not filed* state; never block the reporter |
| F16 | Critical finding flagged, no one reachable | S10 | Escalation owed | Ladder to duty manager; unacknowledged items migrate to the next shift queue |
| F17 | Prompt injection through the dictation or an attached document | S4 | Possibly a confident wrong report | Threat model §3: the dictation is untrusted input to a clinical act; skill instructions are fixed server-side and `extra_instructions` is only ever human-supplied |
| F18 | PHI leaves the installation | S4/S7 | Nothing — invisible by design | Threat model §4: local-only default, no cross-hospital path without a P14 amendment, no prompt or completion text in any log |
| F19 | A dictated observation compressed out of the findings | S4 | `dropped_observation`, **blocking**, quoting the observation that went missing | Sprint 9. Dropping is the mirror of inventing and was the more common failure; the findings must carry every dictated observation. A clinician who meant to drop one corrects the dictation or the section — the sign-off does not proceed quietly |
| F20 | "Unchanged from prior" with no prior in the record | S4 | `invented_history`, **blocking** | Either submit the earlier report text or describe only this study. A comparison needs a second study, and a draft cannot invent one. `_prior_block()` tells the model the same thing before it answers |
| F21 | An equivocal dictation settled into a definite impression | S4 | `unsupported_certainty`, **blocking** | A hedged finding stays hedged. A differential and a confirmation are different clinical documents, and only one of them can be acted on |
| F22 | Markdown, bullets or headings inside a section that will be printed | S4 | `format_breach`, **blocking** | The export is the artefact a referrer reads; markup in it is a defect with a visible face. Refused rather than stripped, because stripping is this application writing the report |
| F23 | A name, MRN or accession invented into the prose | S4 | `invented_identifier`, **blocking** | The submission schema has no identifier field, so there is nothing to invent *from*; a patient who does not exist in the record must not reach the report |

**F10's measurement half, and F19–F23, are the failures the Alpha copilot can now detect
from text alone** — nine deterministic checks in
`apps/radiology_copilot/src/futurekind_radiology/quality.py`, run at draft, again on every
keystroke that changes a checkable claim, and a third time before a signature.
F10's other half (a plausible finding nobody dictated) and F12 remain outside what text can
prove: the images are the only oracle, and `quality.scope` states that on the screen and in
the export rather than leaving it implied.

---

## 4. Automation bias is a design requirement

The failure that will decide whether this product is allowed to stay is not a parsing
bug. It is a radiologist who signs an AI draft in four seconds. Nothing below is
optional, because every alternative puts a human in the position of approving text they
did not read while the audit trail says they did.

1. **Section-by-section acceptance, not a single accept.** The AI pane proposes into
   fields; the report composer stays editable during and after drafting. This is already
   how the USG studio works and it is the reason that studio is the right first host.
2. **The model's original text stays diffable.** `metadata.review.amendments` is written
   per section at S6, so the Approval Screen can show what changed. A reviewer who sees
   they changed nothing on 40 consecutive reports will notice; a dashboard makes the
   department notice first.
3. **No shortcut that drafts and signs.** No keyboard path, no bulk action, no "accept
   all" that reaches `signed`. The copilot's review body has no field an automated caller
   could satisfy with a boolean.
4. **Measurements and numbers are the human's, by rule.** Where a modality requires a
   size or a count (CT nodes, tumour diameters, cardiac indices), the UI requires typing
   it rather than accepting it. This is the one place the product deliberately does less
   work than it could. **Now enforced below the UI as well:** `unsupported_measurement`
   refuses a number that appears in neither the submission nor a supplied prior, so a
   model-authored measurement blocks the signature instead of needing a field to be typed
   into — with the stated limit that digits are compared, so `two lesions` is not caught
   while `2 lesions` is.

**Status of these six in the Alpha copilot.** 1 is met in the screen (six editable
sections, draft lands in fields, nothing accepts the whole report). 3 is met in code: there
is no path from a draft to a signature in one call, and `POST /review` demands a name and a
submission. 4 is met, as above. 6 is met and printed. 2 is **partly** met: the amendment list
is recorded per section, but the screen does not yet show the dictation beside the findings it
became — the text is in `metadata.dictated_findings` and in the JSON export, waiting for a
diff. 5 cannot be met until anyone reports on this hardware: the rewrite rate needs a
department, and there is no measurement of it here.
5. **Latency must not become the argument for trust.** If drafts take eight seconds and
   manual reports take twelve minutes, the organisation will quietly reward accepting. So
   the quality metric published to the department is the rewrite rate, not drafts per
   hour (§S11).
6. **The AI is named on the artefact.** Provenance is not a hidden field: model, alias,
   prompt version and degraded state are rendered in the export (`rendering.py`), so a
   printed report says which parts had machine help.

---

## 5. API requirements

Existing endpoints do most of this. The point of the table is to separate what must be
built from what must merely be wired, because "add another microservice" is not the
default answer here.

| Need | Endpoint | Status | Notes |
| --- | --- | --- | --- |
| Draft a report | `POST /draft` (copilot) → `POST /chat` (Gateway) | **Exists** | Sprint 7, widened Sprint 9: the answer carries the nine quality checks and the computed confidence. Skill `radiology-report` |
| Re-check an edited draft | `POST /check` (copilot) | **Exists** | Sprint 9. The same nine checks over text the clinician is still typing — no Gateway call, no model in the loop, nothing stored |
| Sign | `POST /review` | **Exists** | Copilot-side only; ERP-side signature is the ERP's. Sprint 9: the body must carry the submission the draft came from, and a blocking finding refuses the signature |
| Export | `POST /export` | **Exists** | json / text / markdown; refuses unsigned |
| The working screen | `GET /` (copilot) | **Exists** | Sprint 9. One static HTML document served by the copilot: no external resource, no CDN, no browser storage |
| Health | `GET /health` | **Exists** | Closed 2026-10-08 (was register row 3): the probe endpoints publish verdicts only, and the catalogue source path is gone from the response |
| Deliver | ERP `POST /api/internal/reporting-studio/finalize` | **Exists** | Contract already matches the copilot document; no new ERP endpoint |
| Worklist | ERP `GET /api/internal/reporting-studio/worklist`, `GET /api/radiology/worklist` | **Exists** | |
| Priors | ERP `GET /api/patient-reports/patient/:patientId` | **Exists** | |
| Viewer | `{OHIF_BASE_URL}/viewer?StudyInstanceUIDs={uid}` | **Exists** | `networkDefaults.ts:93-94` |
| PACS filing | Orthanc `POST /tools/create-dicom` | **Exists** | `pacsArchive.ts` |
| Triage ordering | FutureKind `POST /triage` | **New** | Batch, ≤50 studies, returns priority + reason; must degrade to acquisition order (S3) |
| Per-item drafting | FutureKind `POST /draft-item` (ultrasound organ drafts) | **New** | Streams; low latency budget; the shape the USG studio already expects |
| Report read | `GET /reports/{report_id}` | **New** | Nothing today can answer questions about a stored report |
| Report search / list | `GET /reports` with filters | **New** | Needed for Audit Timeline and quality review; PHI-bearing so it needs the auth decision below |
| Critical notifications | `POST /critical-notifications`, `POST /critical-notifications/{id}/acknowledge` | **New** | Only stateful resource in the plan; gated on ADR-0005 |
| Model catalog | Gateway `GET /models` | **Exists, must change** | Unauthenticated today and enumerates provider + model pairs — register row 1, P8/P10 |

### The authentication decision that blocks all of the new ones

Every new endpoint above sits behind an identity FutureKind does not have yet. The
Gateway has one caller concept (`AuthenticatedCaller`) and the copilot authenticates to
it with a single shared API key. Three candidate answers, and the difference between
them is not technical:

1. **Machine credential per installation, human identity stays in the ERP.** FutureKind
   trusts the host's session and receives the clinician's name as a claimed attribute.
   Cheapest, and it makes P3 (a *named* human) only as strong as the host's login —
   acceptable once F13 is fixed, which is why the roadmap pairs them.
2. **FutureKind issues its own per-clinician tokens.** Strongest audit, but it means the
   platform owns an identity store for a hospital that already runs one, and two identity
   systems for one department is how people end up signing as each other.
3. **The ERP's HMAC-signed events as the authentication** (`outbox.ts:171-177` already
   signs bodies). No new secret management, and the signature is verifiable per event.
   This is the option the existing code makes easy and nobody has chosen yet.

Recommendation: **option 3 for the delivery path, option 1 for interactive drafting**,
with the clinician identity verified against the ERP session on each `/draft`. That keeps
FutureKind from owning an identity store while making every clinical act attributable to
a person rather than a deployment. It also means the answer is an ADR, not a ticket —
DOMAIN_MODEL Q1 and Q2 ("what identifies a patient", "is a Hospital an identifier") have
to be settled before any of these endpoints can be spec'd honestly, and they are still
open.
