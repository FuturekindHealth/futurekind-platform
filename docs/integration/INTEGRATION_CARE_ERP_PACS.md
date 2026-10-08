# CARE ERP ↔ PACS ↔ FutureKind — integration design

**Deliverable 7 of Genesis Night.** Written against the ERP source in
`care-erp/artifacts/api-server/src` and the Orthanc/OHIF deployment in
`care-pacs`, not against either project's documentation. `care-erp` is a documentation name
for the CARE ERP checkout, not a path or a host — see
[AI_ENTRY_POINTS_CARE_ERP.md](AI_ENTRY_POINTS_CARE_ERP.md). Every claim below has a file and
line. Where the ERP already solves a problem, this document says *use it* and names the
thing to delete from FutureKind's own plan.

---

## 0. The four findings that change the design

Discovered by reading the source. Each one removes work from FutureKind and adds a
constraint.

**I1 — The ERP already has a structured draft store with an observation ledger, and it is
concurrency-safe without FutureKind.** `radiology_report_drafts.structured_json` is written
as a single read-modify-write under `SELECT … FOR UPDATE`
(`lib/persistCareStructuredFormatState.ts:1-45`), because **six per-key writers previously
lost updates against that column** — the header comment documents the bug: two overlapping
requests both composed against a stale snapshot and "the second write silently discarded
every key the first had added". The envelope carries format state, an **observation ledger**,
viewer measurements, applied patterns and the linked study.

> Consequence: FutureKind must not keep its own draft store as a second source of truth.
> It sends a **patch** to the ERP's existing envelope. A lost update in a clinical draft is
> a dropped finding, and the ERP has already paid for that lesson.

**I2 — The ERP's shadow-inference draft contract is richer than FutureKind's report.**
`ShadowStructuredDraft` (`lib/ai/shadowInference.ts:12-18`) is:

```ts
findings: Array<{ key; text; laterality?: "left"|"right"|"bilateral"|"none"; negated?: boolean; evidence: EvidenceAnchor[] }>
measurements: Array<{ id: string; value: number; unit: string }>
impression: string[]
studyContext: { studyInstanceUid; modality?; imageCount }
```

and its provenance (`InferenceProvenance`, `:24-38`) carries `modelVersion`, `modelDigest`,
`provider`, `degraded`, and a `resourceFailureCode` enum
(`GPU_OUT_OF_MEMORY | CONTEXT_BUDGET_EXCEEDED | PROVIDER_TIMEOUT | PROVIDER_HTTP_ERROR`) so
a job that failed for capacity reasons is not recorded as an empty result.

> Consequence: `RadiologyReport`'s five prose strings are the weaker document model. This is
> `docs/DOMAIN_MODEL.md` R5's **Observation**, already implemented, with laterality, negation
> and evidence anchors. FutureKind adopts it (Sprint 9) rather than inventing a third shape.
> `negated` and `laterality` are exactly the two fields that catch the failures the golden
> set probes (R-5 "states an absence the study cannot exclude", and the wrong-side lesion).

**I3 — The ERP refuses an AI caller any clinical write, and that refusal is correct.**
The AI-caller token class (`aic_…`) is scoped to `knowledge_base:search` and
`knowledge_base:read` (`middleware/requireAiCallerAuth.ts:53-54`). There is no radiology
scope for an AI caller. The reporting-studio class authenticates with
`REPORTING_STUDIO_API_KEY` in `x-api-key` (`routes/internal-reporting-studio.ts:77-91`).

> Consequence: FutureKind integrates **as the studio** — a human-driven client holding the
> studio credential — and never as an `aic_` caller. An AI path that could write a report is
> a P11 violation with a nice API.

**I4 — Two gates exist on the delivery path that FutureKind cannot see or bypass.**
`POST /finalize` returns `409` when the Match Center identity is unresolved ("Resolve GREEN
or APPROVED in the ERP before finalizing", `:812-818`) and `409` when an **obstetric
ultrasound has no complete PCPNDT Form F** (`:820-831`). The same PCPNDT gate is
fail-closed in the PACS return policy (`lib/usgPacsReturnPolicy.ts:110-120`:
`pcpndt_missing` blocks the archive even when nothing else does).

> Consequence: a draft can be perfect and still be undeliverable for legal reasons in the
> host. The UI must render those two `409`s as *waiting on the hospital*, never as an AI or
> platform failure. PCPNDT is a real statutory constraint on the exact product this
> repository builds first (ultrasound at CARE Diagnostics), and FutureKind has no mention of
> it anywhere else — see the roadmap.

---

## 1. Topology and trust boundaries

```
   Browser (clinician) ──► USG / MRI studio (Next.js, :3000/:3090) ──► CARE ERP api-server
        │  session: studio login (today: shared PIN)                        │  x-api-key:
        │                                                                  │  REPORTING_STUDIO_API_KEY
        │  launch                                                            │
        ▼                                                                  ▼
   OHIF (nginx /dicom-web) ───────► Orthanc :8042 ◄── create-dicom ── ERP pacsArchive
                                                                            ▲
   Studio server ── POST /draft ──► FutureKind Copilot :8200                │ PDF + finalize
                                        │  Bearer FK_GATEWAY_API_KEY        │
                                        ▼                                   │
                                 FutureKind Gateway :8100 ──────────────────┘
                                        │ alias fk-reasoning
                                        ▼
                                    LiteLLM :4000 ──► Ollama (qwen3:14b) [local]
                                                  └─► (optional cloud provider, operator-declared)
```

Four boundaries, and only two of them are FutureKind's:

| Boundary | Credential today | Integrity |
| --- | --- | --- |
| Browser → studio | shared PIN (USG), **none** (MRI studio) | **Weak — blocking for Beta** |
| Studio → ERP | `x-api-key` constant-time, 503 when unset (`requireStudioKey`) | Good pattern, shared secret |
| Copilot → Gateway | `Bearer` API key; log carries an 8-hex digest only (`deps.py:67-73`) | Good |
| Gateway → LiteLLM → provider | LiteLLM master key held by the Gateway config, never in a request | Good, but see threat model §5 |
| ERP → external partner callbacks | HMAC-SHA256 signed body (`services/integration/outbox.ts:171-177`) | **The mechanism FutureKind should use** |

## 2. Sequence — the happy path, with the artefacts named

```
Reception          ERP                 Studio            Copilot          Gateway        Orthanc
   │  order ────────►│                                                                      │
   │                │ radiology_studies: accession ACC-20261008-US-021, patientId P-00010   │
   │                │◄─ GET /internal/reporting-studio/worklist ──│                          │
   │                │    (also GET /billing-status)               │                          │
   │                │                                             │                          │
   │   scan ────────►│──── DICOM store (modality → Orthanc) ──────────────────────────────►│
   │                │                                             │                          │
   │                │        clinician dictates organ-by-organ ───│                          │
   │                │                              POST /draft ───│                          │
   │                │                                             │── POST /chat ──────────►│
   │                │                                             │◄─ content+policy+prov ──│
   │                │        chips rendered, accepted per organ ──│                          │
   │                │◄─ PATCH structured_json (FOR UPDATE) ───────│   (draft saved in ERP)   │
   │                │                                             │                          │
   │                │◄─ POST /finalize {accession, reportText, radiologistName, RegNumber, finalizedAt, pdfUrl}
   │                │   409 if identity unresolved / PCPNDT Form F missing                  │
   │                │── patient_reports: reportNumber, status → REPORT_FINAL → DELIVERED     │
   │                │── archiveReportToPacs → POST /tools/create-dicom (Encapsulated PDF) ─►│
   │                │── integration_outbox INSERT (report.finalized)                         │
   │                │   worker: POST + x-care-signature → partner → 200 → status=sent        │
```

## 3. REST APIs

### 3.1 FutureKind → ERP (all exist today)

| Call | Method | Auth | Notes |
| --- | --- | --- | --- |
| `/api/internal/reporting-studio/ping` | GET | `x-api-key` | Liveliness + `erpVersion()` (`:93-95`) |
| `/api/internal/reporting-studio/worklist` | GET | `x-api-key` | The queue source (`:263`) |
| `/api/internal/reporting-studio/audit` | GET | `x-api-key` | (`:577`) — an audit surface already exists host-side |
| `/api/internal/reporting-studio/billing-status` | GET | `x-api-key` | Per-accession billing map (`:676`) |
| `/api/internal/reporting-studio/finalize` | POST | `x-api-key` | The delivery contract (`:736`) |
| `/api/patient-reports/patient/:patientId` | GET | ERP session | Priors and history |

**`finalize` request, exactly as the ERP reads it** (`:738-752`):

```json
{
  "accessionNumber": "ACC-20261008-US-021",
  "worklistId": 4471,
  "reportText": { "technique": "…", "findings": "…", "impression": "…", "recommendation": "…" },
  "radiologistName": "Dr …",
  "radiologistRegNumber": "…",
  "finalizedAt": "2026-10-08T09:41:02Z",
  "pdfUrl": "https://…/report.pdf"
}
```

**Responses:** `200 {ok:true, reportId}` · `200 {ok:true, idempotent:true}` (already
`REPORT_FINAL`/`DELIVERED`, `FINAL_STATUSES` `:74`; the `pdfUrl` is still merged into
`dicomMetadata.reportingStudioPdfUrl`) · `400` no accession and no worklistId · `404`
worklist entry not found · `409` identity unresolved · `409` PCPNDT Form F incomplete ·
`503` key not configured · `401` unauthorized.

> ⚠ **Real contract mismatch, must be fixed before the first delivery.** The ERP field is
> `reportText.recommendation` (singular, `:744`). FutureKind's document key is
> `recommendations` (plural, `report.py::SECTION_KEYS`). A silent `undefined` here loses the
> follow-up paragraph — the section most likely to carry "repeat in 6 weeks" — and the ERP
> would still return `ok: true`. Fix: an explicit mapping at the boundary **and** an ERP-side
> test that a missing `recommendation` fails. Do not rely on a rename matching by hope.

### 3.2 ERP → FutureKind (must be built)

| Call | Method | Purpose |
| --- | --- | --- |
| `/draft` | POST | Already exists in the copilot — called by the studio, not by the ERP |
| `/triage` | POST | **New.** ≤50 accessions, returns priority + reason. Must degrade to acquisition order |
| `/reports/{report_id}` | GET | **New.** The document + provenance + review history |
| `/events` (receiver) | POST | **New.** Accepts the ERP's signed outbox events so FutureKind learns about withdrawals, amendments and supersessions it did not cause |

The receiver is the piece most integrations skip. Without it, a report withdrawn in the ERP
stays "signed" in the copilot forever, and the copilot's answer becomes confidently wrong.
Verification is §4.

## 4. Authentication — the decision, with a recommendation

Three candidate models for how FutureKind proves who is acting. The ERP already contains the
answer to most of the hard parts.

| Option | Mechanism | Cost | Risk |
| --- | --- | --- | --- |
| **A. Studio credential + relayed identity** | FutureKind holds `REPORTING_STUDIO_API_KEY`, sends the clinician's name/registration in the body exactly as the USG studio does today | Zero new code — the ERP already defends this path: `boundRelayedPersonName` caps length and collapses whitespace so a name "cannot smuggle content into a signature block", `resolveRelayedInstant` refuses a future-dated signature, and the server's receipt time is always stored alongside (`internal-reporting-studio.ts:833-846`) | The identity is **relayed, not authenticated**. Acceptable only while the studio login is a shared PIN. On P3 this is the weakest link in the whole design |
| **B. HMAC-signed machine channel** | The ERP's outbox pattern: `x-care-event-id`, `x-care-event-type`, `x-care-timestamp`, `x-care-signature: sha256=HMAC(secret, body+timestamp)` (`outbox.ts:171-177`), with `idempotencyKey` and `correlationId` in the body | FutureKind must implement a verifier, a timestamp window and a dedupe table | Strong for machine-to-machine, says nothing about which human |
| **C. Per-clinician tokens issued by FutureKind** | Real identity inside the platform | An identity store duplicating the hospital's; two login systems for one department | The classic way a platform becomes a second source of truth |

**Recommendation: A for interactive drafting, B for events, and A is only lawful once the
studio login is individual.** The relay-bounding in the ERP is a mitigation, not an
authentication: the honest sentence to write in the hospital's own governance document is
*"the name on a FutureKind-assisted report is the name the studio session claims."* That
becomes false — and provably true — the day the USG studio has per-clinician logins, which is
Beta's blocking gate (`ROADMAP.md` R1), not a FutureKind feature.

Three requirements copied from the ERP because they are correct:

1. **Fail closed when a secret is absent.** `requireStudioKey` answers `503` when the env var
   is unset rather than allowing the request (`:79-82`). The Gateway must refuse to start with
   no `FK_GATEWAY_API_KEY`, and must refuse a weak one: `checkSecretStrength` +
   `logWeakKeyOnce("INTERNAL_API_KEY")` (`internalApiKeyAuth.ts:15-22`) is the pattern to copy
   into the Gateway's settings.
2. **Constant-time compare, always** (`safeEqual`, `:4-11`) — uniform across all internal
   bearer guards, including the Gateway's.
3. **Never log the credential.** The Gateway already logs an 8-hex digest
   (`deps.py:67-73`); the copilot's `settings.redacted()` keeps the key out of its own config
   echo. The LiteLLM master key stays in the Gateway's environment and never in a request,
   a log line, a metric label or an error body.

## 5. Callbacks, events and the outbox contract

The ERP's outbox is a transactional outbox with claim-based locking and exponential backoff:

| Property | Value | Evidence |
| --- | --- | --- |
| Envelope | `eventId, eventType, eventVersion, idempotencyKey, correlationId, sourceOrg, destinationOrg, occurredAt, data` | `outbox.ts:159-169` |
| Headers | `x-care-event-id`, `x-care-event-type`, `x-care-timestamp`, `x-care-signature` | `:171-177` |
| Backoff | `30_000 * 2^(attempt-1)`, capped at 1 h | `backoffMs`, `:94-97` |
| State | `pending → sent`, or `pending` with `nextAttemptAt`, or **`dead`** when `attemptNo >= maxAttempts` | `:196-210` |
| Attempt ledger | `recordAttempt(row.id, attemptNo, "success"|"failure", status, text, reason, durationMs)` | `:180-215` |
| Concurrency | row claim via `lockedAt`/`lockedBy` | `:150-210` |
| Failure taxonomy | `delivery_not_configured`, `http_<status>` recorded per attempt | `:150-210` |

**What FutureKind's `/events` receiver must do**, in this order:

1. Verify `x-care-signature` over the exact received bytes with the shared secret, and reject
   a `x-care-timestamp` more than 5 minutes from now (the ERP signs `body + timestamp`, so the
   window is what stops replay).
2. Dedupe on `idempotencyKey` into a small table before doing any work, and answer `200` for a
   duplicate — the ERP marks a duplicate delivery `sent`, not retried, so a `409` here would
   turn a healthy re-delivery into a dead letter.
3. Apply by `eventType`; unknown types are **accepted and ignored with a warning**, not failed.
   A new ERP event type must never break a hospital's reporting.
4. Record `correlationId` on every state change so a report's timeline (§Audit screen) can show
   the event that caused it.

## 6. Draft lifecycle and version history

The ERP owns this. FutureKind mirrors it and must not build a parallel chain.

| FutureKind `metadata.review.state` | ERP status | Owned by |
| --- | --- | --- |
| `pending_review` | `radiology_report_drafts` row, `structured_json` patch | ERP draft store (I1) |
| `signed` | `patient_reports` created; worklist `REPORT_FINAL`; signature columns + role guard `radiologyD1FinalWriter.ts:76` (refuses `typist\|ai\|system\|bot`) | ERP |
| `delivered` | worklist `DELIVERED`, outbox `sent` | ERP |
| `amended` | `sequenceNumber` / `totalVersions`, `resolvedSuperseded`, `X-Report-Version: n/total` (`patient-reports.ts:439`), amendment writer `radiologyD1AmendmentWriter.ts` | ERP |
| `withdrawn` | `withdraw-signature` (`patient-reports.ts:2869`) | ERP |
| `superseded` | series description `Radiology Report PDF v2/3 SUPERSEDED` (`pacsArchive.ts:205-210`) | ERP + Orthanc |

Rules that follow:

- A withdrawal must reach the copilot through §5, or the copilot will keep answering that a
  report is signed.
- The copilot's own `report_id` is the join key and is stored in the ERP envelope's metadata;
  the ERP's `reportNumber` is the clinical identifier. Two identifiers, one documented mapping.
- **Never delete.** An amended report is a new version, and the PACS series label makes
  supersession visible in the archive (`usgPacsReturnPolicy.ts:131-140`: a *new* report series,
  Orthanc mints the Series/SOP UIDs, "we never reuse or overwrite a source-image series").

## 7. Error handling and retry strategy

| Failure | Detect | Retryable | Who retries | User sees | Timeout budget |
| --- | --- | --- | --- | --- | --- |
| Gateway down | copilot → `503` (`GatewayRequestError`) | Yes, once | Studio | *"AI unavailable — dictate directly"*; composer still works | 120 s client |
| Model refuses / prose instead of JSON | `502 ModelOutputError` | Once, then stop | Copilot refuses to offer a draft | Reason in the draft pane | skill ceiling |
| Truncated (`finish_reason=length`) | `ReportTruncatedError` | Only with a raised token budget, by config | Nobody silently | "Model did not finish — refused" | — |
| Degraded substitution | policy `allow_downgrade:false` → `DegradedAnswerError` | No | Human re-drafts or types | Named as degraded | — |
| `finalize` `409` identity unresolved | ERP | No — blocked on the hospital | Staff, in the ERP | *"Waiting on patient identity verification"* | — |
| `finalize` `409` PCPNDT | ERP | No — statutory | Staff, in the ERP | *"Form F required before this study can be finalised"* | — |
| `finalize` `404` | worklist row gone | No | Human | Names the accession it looked for | — |
| `finalize` network failure | transport | **Yes, idempotent** | Studio, with backoff | "Delivery pending", never "signed" | 10 s |
| Outbox `dead` | ERP attempt ledger | Manual replay | Integration officer | Report is signed but not forwarded; visible in the queue strip | — |
| Orthanc `create-dicom` non-2xx | `pacsArchive.ts:236-241` throws with the status | Yes | ERP | Report delivered; *"not filed to PACS"* tick absent | 30 s |
| Clock skew | future-dated `finalizedAt` refused by `resolveRelayedInstant` | No | — | NTP is a deployment requirement | — |

**Global retry rule:** one automatic retry per operation, with idempotency, then stop and show
the reason. A silent retry loop against a model is how a department ends up with four
different impressions for one study and no record of why.

## 8. Offline behaviour

| Out | What must still work | What is degraded | What must not be lost |
| --- | --- | --- | --- |
| **FutureKind Gateway / model** | The studio's own composer, dictation, autosave, print, ERP sync, PACS return — all host-side and independent | Drafting, triage ordering | Typed text. Autosave continues against the ERP |
| **ERP** | Nothing clinical is lost: the studio's autosave is against the ERP, so an ERP outage stops reporting for reasons that predate FutureKind | Everything, as today | Local composer state until the session dies; the copilot keeps drafts it already made |
| **Orthanc** | Reporting, signing, delivery | PACS filing | The archive is retried; the report is not reverted |
| **Hospital internet** | Local Ollama, LiteLLM, Gateway, ERP, Orthanc, OHIF — the whole product, because `local_first: true`, `internet_required: false` (`configs/futurekind.yaml`) | Optional cloud provider (declined by default); share links that resolve publicly | Nothing |

This table is the strongest argument in the repository for local-first: the only component
whose loss stops the department is the hospital's own database, and that was true before this
platform existed.

## 9. Field mapping

| Clinical concept | ERP | PACS | FutureKind |
| --- | --- | --- | --- |
| Patient | `patients.patientId` (UHID `P-00010`); **no MRN column** | `PatientID` tag | **absent by design** (workflow D3) |
| Order | `radiology_studies.accessionNumber` `ACC-YYYYMMDD-MOD-NNN` | `AccessionNumber` | `study` label only, in metadata |
| Study | `radiology_studies.studyInstanceUid` | `StudyInstanceUID` | carried as a document reference, never sent to the model |
| Report sections | `reportText.{technique,findings,impression,recommendation}` | PDF body | `SECTION_KEYS` — **see the singular/plural defect in §3.1** |
| Signature | `signedByName`, `signedAt`, `verifiedByName`, `verifiedAt` (`patientReports.ts:38-46`) | PDF signatory block | `metadata.review.{clinician,reviewed_at}` |
| Version | `sequenceNumber`, `totalVersions`, `resolvedSuperseded` | series description | **not stored** — read from the ERP |
| Provenance | not in the ERP today | not in DICOM | `model_provenance` + `skill` + `policy` on the document |
| Structured findings | `structured_json` observation ledger | DICOM SR (parallel path exists) | **to adopt (I2)** |

Provenance is the column the ERP does not have. Its natural home is the same
`structured_json` envelope, written as a patch under the row lock — one write path, one
concurrency story, and no new column.

## 10. PACS specifics

- **Viewer launch** is `{OHIF_BASE_URL}/viewer?StudyInstanceUIDs={uid}`
  (`usg-reports/src/lib/networkDefaults.ts:93-94`; base is that installation's `OHIF_BASE_URL`, which this document does not name), images
  over nginx `/dicom-web` → `orthanc:8042` (`care-pacs/ohif/enterprise/default.conf:43-45`).
  FutureKind never proxies DICOM; it hands over a URL the ERP already builds.
- **Archive** is Encapsulated PDF, `SOPClassUID 1.2.840.10008.5.1.4.1.1.104.1`, `Modality: OT`,
  posted to `/tools/create-dicom` with `Tags` + base64 `Content` (`pacsArchive.ts:210-240`).
  A *new* report series is minted; source image series are never touched.
- **Two artefacts exist and both are correct:** DICOM SR and Encapsulated PDF, with an
  extraction hierarchy that prefers `dicom_sr_scoord → dicom_sr_num → ge_private_tag →
  encapsulated_pdf → ocr → manual` (`usgExtractionHierarchy.ts:24-32`). FutureKind produces a
  report document, not a second SR writer. If structured findings (I2) are ever wanted in the
  archive, the SR path already exists and should be extended, not duplicated.
- **The archive endpoint is anonymous.** `orthanc/config/orthanc.json` in `care-pacs` sets
  `AuthenticationEnabled: false` (`:7`), `RemoteAccessAllowed: true` (`:6`),
  `DicomWeb.EnableCors: true` with `Access-Control-Allow-Origin: *` (`:19-22`),
  `DicomAlwaysAllowStore: true` and `DicomCheckCalledAet: false` (`:23-24`), and port `8042`
  is published to the host (`docker-compose.yml:56`). `getOrthancConfig` optionally sends
  Basic credentials from env (`pacsArchive.ts:17-23`) which therefore authenticate nothing.
  Anyone reachable on the ward network can read every study, write new ones, and issue
  browser cross-origin requests to it. This is threat-model §5, and it is the host's
  configuration to change — FutureKind cannot fix it from inside the platform.

## 11. What must be built, in order

Small list, because most of it already exists.

1. **Fix the `recommendation`/`recommendations` mapping** at the boundary, with a test that
   fails if the follow-up paragraph is silently dropped. (Half a day, prevents the worst
   silent defect in this document.)
2. **Route one live studio draft path through the Gateway** — `usg-reports`
   `lib/usg/aiDraft.ts:89-94` currently reads `OLLAMA_URL`/`OLLAMA_MODEL` from the application's
   environment and calls Ollama directly. Replace with a copilot call. Removes one ungoverned
   path, changes no clinical workflow, keeps per-item chips.
3. **`POST /events` receiver** with signature verification, dedupe and `correlationId`.
4. **Structured findings (I2) in the copilot document**, matching `ShadowStructuredDraft`, and a
   patch writer into the ERP's `structured_json` under the existing row lock.
5. **`/triage`**, with the documented fallback to acquisition order.
6. **`GET /reports/{id}`** and list/search — needed by the Audit Timeline and the metrics view.
7. Nothing else. No new ERP endpoint, no new archive path, no new draft store, no new identity
   system.

## 12. Open questions for the owner

1. **Who owns `finalizedAt`?** The ERP bounds a relayed timestamp rather than trusting it.
   FutureKind should send nothing and let the ERP stamp the signature — which means
   `radiologistName`/`finalizedAt` should eventually disappear from the studio payload
   entirely once per-clinician login exists. Do you want that now or after R1?
2. **Do you accept the PCPNDT gate as a product surface?** The `409` is statutory and
   correct. The alternative — hiding it — would be FutureKind deciding that a legal
   requirement is an implementation detail.
3. **Where does provenance live in the ERP?** A `structured_json` patch needs no migration. A
   real column would be cleaner to query and is a schema change in a system you run in
   production. Recommendation: patch now, column when the first audit query proves slow.
4. **Is the MRI studio's image-grounded draft (I2's author) in or out of scope?** It is a
   working `qwen3-vl:8b` pipeline with its own grounding rules and ops fail-safes. Bringing it
   inside the Gateway requires a `vision` capability and an async job model — the only place
   in this sprint where "not yet built" is a real answer rather than a decision not taken.
