# FutureKind Product Specification

**Radiology Copilot, first product. CARE Diagnostics and Hope Neurotrauma &
Multispeciality Hospital, first customers. Local-first, hospital-owned, clinician-signed.**

This is a product document. It says what the thing does, who uses it, what it is worth and
what it deliberately is not. The architecture it sits on is accepted and unchanged
(`docs/ARCHITECTURE.md`, `ADR-0002`); the workflow is specified in
`docs/product/RADIOLOGY_WORKFLOW.md`.

---

## 1. The one-paragraph version

A radiologist at CARE Diagnostics finishes a scan, dictates or types what they saw, and
within seconds has a sectioned draft on screen that says exactly what they said, in report
language, with an impression and a follow-up. They correct it, sign it, and it is in the
ERP and the PACS. Nothing they typed left the building. Every word of the draft can be
traced to the model, the alias, the prompt version and the request id that produced it, and
the report says which sections a human rewrote. The AI never signed anything, never
decided anything, and is never the reason a report is late.

**The sentence a hospital can repeat:** *FutureKind drafts; a named clinician decides.*

## 2. The problem, in the department's terms

There is a backlog of reported studies and a shortage of reporting time. The bottleneck is
not image acquisition, not the PACS and not the ERP — it is the minutes between "I have
seen this" and "it is written down and signed". Three forces act on those minutes:

- **Volume.** A screening or OPD ultrasound list runs all day; a CT head from the ED cannot
  wait; the same radiologist does both.
- **Documentation load.** The report is also a legal document, a billing artefact and the
  input to a coding system. Typing it correctly three times (report, ERP, PACS) is the
  hidden cost.
- **Risk.** A dropped observation, an invented measurement or a restated clinical question is
  how an assist becomes a liability. This is the reason generic chat clients in a hospital
  are not a product — they cannot say what they were told, what they added, or who signed it.

The existing answer at this site is a set of direct-to-model paths that no governance layer
sees: the ERP's own AI providers package (local Ollama `qwen3-vl:8b` by default, with cloud
Qwen/DeepSeek/OpenAI behind opt-in flags — `lib/ai/gatewayInferenceProvider.ts:5-9`), the
USG studio's per-organ skeleton draft (`usg-reports/src/lib/usg/aiDraft.ts:89-94`, where the
**model name comes from an application environment variable** — `OLLAMA_MODEL`), and the USG
studio's vision OCR of biometry (`lib/usg/ollamaOcr.ts`). None of them passes a policy
boundary, and two of them choose a model in application code, which is the exact thing
`ADR-0002` rule 1 forbids a caller from doing. That is not a missing feature; it is the
missing product. `CONSTITUTION.md` P16 calls it drift; this spec calls it the entry point.

## 3. What FutureKind ships as product

Four modules. One of them is the platform the Gateway already is, and is listed so nobody
builds a fifth.

| Module | What it is | Ships |
| --- | --- | --- |
| **M1 Radiology Copilot** | Draft → check → review → sign → export, for imaging studies, with nine deterministic grounding checks gating the signature. The application in `apps/radiology_copilot/` | **Alpha, built** |
| **M2 Skill Runtime** | The Gateway's five namespaces: Skill → Capability → Policy → Alias → Model. Everything above M1 calls it; nothing above M1 names a model | Exists, six skills authorised |
| **M3 Clinician Workspace** | The screens: queue, draft, comparison, approval, audit, search. Hosted *in* the existing studios rather than as a fifth web app | Design (`UI_UX.md`) |
| **M4 Evaluation** | 100 golden studies, six-step scoring, drift metrics. The thing that decides whether a model change is allowed | Design, unratified (`GOLDEN_DATASET.yaml`) |

Cross-cutting and not optional: **Integration** (ERP + PACS,
`docs/integration/INTEGRATION_CARE_ERP_PACS.md` and the entry-point survey in
`docs/integration/AI_ENTRY_POINTS_CARE_ERP.md`) and
**Governance** (policy block on every answer, provenance in every document, audit that
retains nothing it should not). **Skill Library** and **Prompt Library** are configuration
assets that belong to M2 and M1 respectively.

### 3.1 Features, and the value each one buys

| Feature | Clinical value | Commercial value |
| --- | --- | --- |
| Structured draft from dictation (six sections, five authored by the model) | Turns a 12-minute typing task into a 2-minute checking task | Reporting throughput without more radiologist hours |
| Nine deterministic checks against the clinician's own submission, plus a computed confidence grade | A fabricated measurement, an invented history or a hedged sign settled into a diagnosis is visible before a name goes on it — and no check is the model grading itself | The claim a hospital can put in front of a regulator: here is what was tested, and here is what was not |
| Section-by-section accept, never a whole-report accept | The reviewer's attention is where the safety is | The audit trail is per section, which is what a regulator or a claim asks for |
| Named-clinician sign-off with the section diff | "Who wrote this sentence" has an answer | The difference between a defensible record and an indefensible one |
| Model provenance printed on the report | A reader knows machine help was involved and what class of model gave it | Lets the hospital buy a better model later without re-explaining its own history |
| Fail-closed parsing (no partial drafts, no truncated impressions) | A missing section is visible; a half-sentence is refused | Prevents the incident that stops procurement |
| Policy block on every answer | Risk level, audit requirement and downgrade permission travel with the text | Enables different rules per department without different code |
| Undisclosed substitution is impossible (`allow_downgrade: false`, P13) | A lesser model cannot answer a high-risk skill quietly | The hospital can contract on a model class and verify it |
| Local-first deployment | Patient narrative is processed on the hospital's own machine | No per-token bill, no data-processing agreement per vendor |
| ERP delivery + PACS archive on signature | The report exists in exactly one place of record | No double entry, no reconciliation staff time |
| Search and audit timeline | A department can find its own work a year later | Required for accreditation and for medicolegal requests |

### 3.2 What FutureKind is not, stated in the specification

Every one of these is a place where a reasonable engineer would have added capability and
the product would have gotten worse.

- **Not a reporting studio.** The ERP and the two studios already have worklists, composers,
  print, share links and audit. M1 hands them a document (workflow D1).
- **Not an image reader — and this is a contested boundary, not a settled one.** No vision.
  The AI drafts from what the clinician dictated, never from the pixels. That is a product
  decision with a clinical reason: a system that reads pixels has an opinion about a study
  the radiologist has not formed yet, and it is wrong in a way that is hard to see. It is
  also a boundary the *customer has already crossed twice, without FutureKind*:
  `care-erp` runs an overnight image-grounded MRI draft on `qwen3-vl:8b`
  (`lib/ai/gatewayInferenceProvider.ts:1-13`, with its own grounding rules, safe-mode
  "LIMITED REVIEW" labelling, ops controls and fail-safes), and `usg-reports` runs vision OCR
  of on-screen biometry (`lib/usg/ollamaOcr.ts:2-3`). `SKILL_LIBRARY.yaml` is correct that
  none of the 121 designed skills needs vision — but the platform's lack of a `vision`
  capability is now the reason the hospital's most advanced AI work can only happen outside
  the governed boundary. That is a roadmap decision (`ROADMAP.md` §0, decision **D-D**), not a
  philosophy.
- **Not a different document model than the ERP's.** The ERP's shadow-inference draft already
  carries structured findings with `laterality`, `negated` and `evidence[]` anchors, typed
  `measurements`, and inference provenance (`modelVersion`, `modelDigest`, `degraded`,
  `resourceFailureCode`) — `lib/ai/shadowInference.ts:11-38`. FutureKind's `RadiologyReport`
  is five prose strings. **The ERP's shape is better and it is the one
  `docs/DOMAIN_MODEL.md` R5 describes as an `Observation`.** M1 should adopt it rather than
  invent a third.
- **Not a clinical decision.** No disposition, no dose, no staging decision, no "fit for
  anaesthesia". The prompts forbid it, the schemas carry `not_stated`, and the workflow
  routes every decision to a named human.
- **Not a second identity system.** It authenticates to the ERP's session or a signed
  machine credential; it does not run a user database for a department that has one
  (workflow §5, and the reason `Tenant` has zero occurrences in the domain model and
  should keep none).
- **Not a data path between hospitals.** P14: nothing crosses an installation without an
  explicit amendment. A second site is a second deployment, not a tenant.
- **Not an archive.** The PACS is the archive. M1 produces one PDF for the ERP's existing
  Encapsulated PDF writer and stops.

## 4. The five workflows this product is judged on

Not five modalities — five moments that matter at the two named sites. Each is one or more
skills in `SKILL_LIBRARY.yaml`, scored by cases in `GOLDEN_DATASET.yaml`.

1. **Acute head CT from the ED** (Hope, neurosurgery-led). The report decides a thrombolysis
   or a surgical conversation. `ct-head-acute-stroke`, `ct-head-trauma`, `ct-perfusion-stroke`.
   Latency budget 20 s, policy ceiling 90 s, `reasoning`. **This is the flagship
   demonstration, because the department that owns this hospital is the one that will
   accept or reject it.**
2. **OPD ultrasound at CARE Diagnostics.** High volume, structured, already has per-item AI
   chips and a working ERP/PACS path. `us-abdomen`, `us-kidney-urinary`, `us-thyroid`.
   Latency budget 3 s per item. **This is the first deployment, because the workflow
   already exists and only its AI path is wrong.**
3. **Screening mammography with density notice** (once a breast service exists). `mg-screening`,
   `mg-density-notice`, `breast-lesion-recall-decision` — the one two-reader workflow, and the
   one where the patient-facing letter is a clinical artefact in its own right.
4. **Paediatric and neonatal** at a multispeciality hospital. `neuro-glasgow-coma-scale`,
   `ed-paediatric-fever-pathway`, `neonatal-delivery-transition-note`, and the safeguarding
   cases already in the golden set. Highest consequence of a wrong number; the reason the
   arithmetic-refusal rule exists.
5. **Discharge, referral and coding** — the documentation load that does not need a scanner.
   `discharge-summary`, `referral-letter`, `icd10-coding-suggestion`,
   `medication-reconciliation`. Lowest clinical risk per document, largest recovered
   clinician-hours, and the fastest way to make a non-radiology department ask for the
   platform.

## 5. Commercial value, as unit economics rather than a claim

No revenue number is asserted here, because the three inputs that decide it are the owner's,
not the platform's. The model is deliberately simple.

**Cost per reported study** ≈ `(amortised hardware + electricity + support time) / studies reported`
with **no per-token cost** in the local default configuration. `configs/futurekind.yaml`
declares `local_first: true`, `internet_required: false`, minimum 16 GB RAM / recommended
32 GB — a machine in the range of the Synology the clinic already operates. A cloud
provider is optional per P8-style configuration, and when used it is an operator decision
recorded in provenance, never a caller's.

**The three numbers only the owner can supply**, and the product's economics are entirely
determined by them:

| Input | Why it decides everything | Where it comes from |
| --- | --- | --- |
| Studies reported per month, by modality | Sets the hardware tier and the payback period | ERP `radiology_studies` counts — a query, not a guess |
| Average reporting minutes per study today | The saving is minutes × studies × loaded cost of a radiologist | Time one list honestly, or read the studio's audit timestamps |
| Current cost of a report reaching a patient late | The cost is clinical, not administrative: a delayed decision, a duplicated study, a referred patient who came back | Clinical and operations judgement |

**Value realised in four places**, in the order a hospital will actually notice:

1. **Reporting time returned.** Drafting is the typing; reviewing is the thinking. The
   product replaces the first with the second. Measured as *minutes per study*, not as
   "AI accuracy".
2. **Double entry removed.** One signature writes the ERP record, the PDF and the PACS
   series. Today that is manual or duplicated across studio-specific code.
3. **Defensibility bought.** Provenance, per-section amendments and a retained audit trail
   are things a hospital pays consultants to reconstruct after an incident. Having them
   before is cheaper, and it is the difference between "the AI said" and "dr X signed
   section 3 after editing sections 2 and 4".
4. **A platform instead of four pilots.** Each new direct-to-model path in the hospital is a
   new unmanaged data path, a new cost line and a new thing to audit. One boundary with 121
   configured skills is procurement, not development. This is the actual product
   proposition: **FutureKind is where the hospital's AI experiments stop being
   experiments.**

**Pricing shape (for the owner to decide, not this document).** Local-first with no per-call
cost argues against per-study billing, which would require the platform to trust the
hospital's own count. A deployment fee plus a support-and-model-update subscription aligns
incentives correctly: the hospital owns its data and its hardware, and what it buys is the
skill library, the evaluation work and the guarantee that a model change is measured rather
than swallowed. Per-seat pricing would charge the department for using the product, which is
the opposite of the point.

## 6. How it fits the hospital's existing workflow

The product is inserted at one point and touches nothing else.

```
Reception / ERP order  ──►  Modality / PACS acquisition  ──►  Reporting clinician
        (unchanged)              (unchanged; MWL unchanged)          │
                                                                     │  dictation
                                                                     ▼
                                              FutureKind Copilot  ── draft + provenance
                                                                     │
                                              clinician edits, signs │  (ERP refuses ai|system|typist|bot)
                                                                     ▼
                                     ERP patient_reports ──► PACS Encapsulated PDF ──► referring clinician
                                       (system of record)         (archive)             (unchanged)
```

What stays exactly as it is: ordering, patient identity, acquisition, the modality worklist,
the viewer, billing, and the referring clinician's route to a result. What FutureKind
replaces: the typing, and the four ungoverned model calls. What FutureKind adds that does
not exist today: the ability to say, for any sentence in any report, which model wrote it,
under which policy, and which human accepted it.

## 7. Release shapes

| | Alpha | Beta | v1 | Enterprise | FutureKind Cloud |
| --- | --- | --- | --- | --- | --- |
| Users | One department, one site | Both sites' radiology | Radiology + pathology + ED | Multi-site, own their installs | Optional managed skills |
| Skills live | 1–3 | 10–15 | 40–60 | all ratified in library | per-contract |
| Clinical gate | Copilot-side signature | Copilot + Gateway approvals (ADR-0005) | Policy-enforced per department | Contractual per site | Same as v1 |
| Identity | Deployment credential + ERP session claim | **Individual clinician authentication (blocking)** | Role model per department | Hospital-scoped policy variants | per-tenant |
| Audit | Emitted, not retained | Retained, searchable | Retained with retention policy | Export to the hospital's own SIEM | Customer-controlled |
| Models | Local `qwen3:14b` via Ollama | Local, with measured comparison | Local default + optional cloud under policy | Policy per risk class | Same |
| Kills the product if | real-model latency > 90 s routinely | a hallucinated finding reaches a signed report | drafts are accepted unedited | an installation leaks outside its site | — |

Full detail, effort, dependencies and risks: `docs/product/ROADMAP.md`.

## 8. Success metrics

| Metric | Target | Measured how | Status |
| --- | --- | --- | --- |
| Time from dictation complete → signed | Falls vs baseline | ERP timestamps, `finalize` → signature | **Baseline not yet taken** |
| Impression rewrite rate | Reported, not targeted | `metadata.review.amendments` sections vs model output | Computable today |
| **Substantive** rewrite rate (diagnosis changed, not phrasing) | The only quality metric that matters | Needs a classification rule for amendment type | Not built |
| Draft availability | ≥99% of attempts produce either a draft or a visible reason | Copilot error codes | Built |
| Hallucinated findings reaching a signature | 0 | Golden-set safety score + random audit of signed reports | Golden set unratified |
| Median draft latency on the hospital's own hardware | < 8 s p50, < 20 s p95 | `latency_ms` per `chat_completed` | **Unknown. Stub-only measurements exist** |
| Reports delivered to ERP and filed to PACS on first attempt | ≥99% | ERP outbox `pending/sent/dead` | Exists in ERP |
| Clinician willingness to keep using it | qualitative | one question, weekly, in the workspace | Not asked yet |

## 9. Why this is the right product now

- For every skill in the current library, the platform layer is finished enough that the
  blocker is a *decision*, not missing infrastructure: ADR-0005 (approvals), ADR-0006
  (citation), individual authentication, clinical ratification of the golden set. Four
  decisions, no rebuilds. The two exceptions are the ones the customer created: a `vision`
  capability and an asynchronous job model, both of which exist at the hospital today
  outside this platform (§3.2).
- The hospital already runs three of the four workflow pieces (worklist, composer, archive)
  and got the fourth wrong only in its AI path. Fixing one path is a smaller change than a
  new system, and this site has proven it can operate the change — it already operates the
  studios, Orthanc, OHIF and the ERP.
- Documentation burden, not image interpretation, is where an LLM is genuinely useful in a
  hospital, and this design uses it only there.
- The alternative — more per-department direct model calls — is already happening in four
  places. The product decision is whether the hospital's AI gets one boundary with policy
  and provenance, or four without.
