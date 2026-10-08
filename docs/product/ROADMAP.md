# FutureKind Product Roadmap — Alpha → Beta → v1 → Enterprise → Cloud

**Deliverable 9 of Genesis Night.** Sequenced by what unlocks what, not by what is most
interesting. Effort is in engineer-days (an engineer who has this repository open), and every
number is labelled **estimate** because the only measured timings in this project are against
stubs. Business value is stated against the two named sites.

---

## 0. The three decisions that gate everything else

Roadmap items do not block on infrastructure. Four decisions do, and they cost a
conversation, not a sprint.

| Decision | What it decides | Blocks | Who |
| --- | --- | --- | --- |
| **D-A. ADR-0005 — approvals as a platform concept** | Whether the Gateway can hold a human sign-off, or whether every application keeps enforcing its own | Beta's policy gate, 9 skills marked `beta` in `SKILL_LIBRARY.yaml`, and the critical-notification resource | Platform owner, with the clinical owner |
| **D-B. Individual clinician authentication in the host studios** | Whether "a named human signed this" (P3) is true | **Beta, absolutely.** Threat model F-A | **Hospital** (studio code) |
| **D-C. Audit retention — where the record lives and for how long** | Whether the platform can honestly claim audit | Beta; every medicolegal promise; `DOMAIN_MODEL.md` Q3 | Platform owner + hospital information governance |
| **D-D. Vision and asynchronous jobs** | Whether FutureKind becomes the boundary for the ERP's image-grounded MRI drafting, or concedes it | Whether P16 (one AI boundary) is achievable at this site at all | Product owner, with the neurophysics/radiology lead |

D-D is the one nobody has noticed yet. `care-erp` already runs an overnight
image-grounded draft pipeline on `qwen3-vl:8b` with its own grounding rules, ops controls and
fail-safes (`lib/ai/gatewayInferenceProvider.ts`, `lib/ai/shadowInference.ts`,
`overnightVisionConfig.ts`). The Gateway has no `vision` capability and no job model, so the
hospital's most advanced AI work can only ever live outside the governed boundary. Saying
"no vision" as a product principle is defensible; saying "no vision" while the customer runs
vision and leaving it un-governed is not a decision, it is drift.

---

## 1. Where we are

**Alpha, built and verified:** Gateway with skill/capability/policy/alias/model namespaces,
alias contract checked at startup, OpenAI-compatible interface, fail-closed parsing, provenance
and policy on every answer, golden fixtures and an end-to-end test through three real uvicorn
processes; CI on every push running both suites (492 Gateway + 225 copilot tests), ruff, the
citation check and an image build. The radiology copilot now runs one complete clinical
workflow — MRI brain — end to end in a browser a radiologist can use: submit, draft, edit,
nine deterministic grounding checks, a sign-off that refuses an unsupported draft, export.
Public-facing hygiene is done: LICENSE, README, SECURITY.md, issue templates, and no live
infrastructure identifier in the tracked tree.
100 golden studies designed (unratified). 121 skills designed (6 authorised).
**Not built:** audit retention, approvals, individual identity, a real-model latency number.

The honest summary: **the platform layer is finished, the clinical layer is usable and proven
once, and nothing has been measured on the hardware this will actually run on.**

---

## 2. Sprint 8 — make one live path governed (the smallest real clinical value)

> **EXECUTED 2026-10-08, IN THE ERP WORKING TREE — NOT YET COMMITTED.** Full record:
> [`docs/integration/AI_ENTRY_POINTS_CARE_ERP.md`](../integration/AI_ENTRY_POINTS_CARE_ERP.md).
> The ERP's ultrasound advisory chips were migrated behind the Gateway as a new skill
> (`usg-advisory-suggestions`); re-measured 2026-10-08, **45 tests pass across the four
> files that carry the change** (`routes/usgAi.test.ts`,
> `lib/ai/futurekindGatewayProvider.test.ts`, `lib/ai/usgAssistantPrompt.test.ts`,
> `lib/usgAiService.test.ts`), and
> the direct model access for that feature is deleted. The wider `lib/ai` directory is
> not claimed green — 9 of its 50 test files were failing in that working tree when this
> was measured, for reasons that predate and do not belong to this migration.
> **The kill criterion in 8.0 triggered:** measured throughput on this
> workstation was **3.9 tokens/s** (`gemma3:12b`), so a ~380-token chip answer takes ~100 s —
> governance itself cost ~0.2 s, the model costs everything. The chip budget must be re-measured
> on the clinic's own box before `ff_radiology_usg_ai_assistant` is switched on there.

> **Also executed in this repository on 2026-10-08** was the release-readiness half that the
> roadmap had not itemised: the Apache-2.0 licence, `README.md`, `SECURITY.md`, the contributing
> guides and issue templates, CI running both suites and building the image, the inventory
> endpoints authenticated (8.4), and every live infrastructure identifier removed from the
> tracked tree (tip `4ef5dd3` on `develop`). **The published history was not rewritten**, so
> what was tracked before that commit is still reachable there — rotating a deployed credential
> is the operator's task, and no `filter-branch` does it for them.

> *"The next implementation sprint MUST be the smallest possible sprint that delivers real
> clinical value."* This is that sprint.

**Why this one.** The USG studio at CARE Diagnostics is live, has a worklist, a structured
composer, per-organ AI chips, PDF printing, share links, an audit table and a PACS return with
a PCPNDT gate. Its AI path is the only part that is wrong: it calls Ollama directly and picks
the model from an environment variable (`lib/usg/aiDraft.ts:89-94`), which is exactly what
`ADR-0002` rule 1 forbids and what Constitution P16 exists to prevent. No new workflow, no new
screen, no new clinical behaviour — replace the transport under a feature clinicians already
use, and it becomes auditable, policy-governed and model-swappable.

| Task | Effort | Dependency | Value |
| --- | --- | --- | --- |
| **8.0 Time `fk-reasoning` on the hospital's machine.** One script, 20 real dictations, p50/p95/max wall time and token counts. **Do this first; it can invalidate everything below** | 0.5 d estimate | Access to the machine | Decides whether 8 s is achievable or whether the product needs a different model class |
| 8.1 Add a `us-organ-chips` skill stanza (capability `fast`) + alias, and a copilot path that returns per-organ chip JSON instead of five prose sections | 2–3 d | 8.0 | One governed clinical path instead of one ungoverned one |
| 8.2 Point `aiDraft.ts` at the copilot/Gateway; delete its `OLLAMA_URL`/`OLLAMA_MODEL` handling | 1–2 d | 8.1 | Removes a direct-to-model path. **Net code deletion in the studio** |
| 8.3 Fix the `recommendation` ↔ `recommendations` mapping at `finalize` with a test that fails when the follow-up paragraph is dropped (integration §3.1) | 0.5 d | — | Prevents the worst silent defect in the design |
| ~~8.4 Authenticate `/models`, `/metrics`, `/health`, or strip their detail (threat model F-D)~~ | ~~0.5–1 d~~ | — | **Done 2026-10-08.** Closes constitution register rows 1–3. `/models` and `/metrics` require a credential; the two probe endpoints keep their key-free reach and publish verdicts only |
| 8.5 Reword the audit/tracing claims in `ARCHITECTURE.md`, `core/gateway/README.md` and `configs/futurekind.yaml` to match what exists until D-C lands | 0.5 d | — | Register row 4's honest half: stop advertising a capability that is not there |
| 8.6 Add 10 injection cases and 10 "limitation not supplied" cases to the golden set, with the 100% safety gate written down | 1 d | — | The first evaluation that tests a *threat*, not only a diagnosis |

**Total: 6–8 engineer-days.** Definition of done: a sonographer at CARE Diagnostics accepts an
organ chip exactly as today, and the chip's `request_id` can be traced to alias, model, prompt
version and policy — which today cannot be said of any AI output at that hospital.

**Kill criterion for 8.1–8.2:** if 8.0 shows p95 over ~3 s for a `fast` chip, chips are the
wrong interaction (a clinician will not wait per organ). Then ship the whole-report draft for
CT/MRI first and keep the USG chips ungoverned but *explicitly deferred*, rather than shipping
a laggy chip UI and teaching the department to switch the AI off.

## 3. Sprint 9 — the first clinical product

> **EXECUTED 2026-10-08** on `feature/radiology-copilot-alpha`. The brief was explicitly *not*
> a platform, documentation or architecture sprint: build the first usable FutureKind product,
> and let everything revolve around a radiologist reading one study. Gateway, LiteLLM, policy,
> routing, provider interfaces, compose, ADRs and the constitution were frozen unless an
> actual bug blocked implementation — none did, so none of them changed.
>
> This section was written before that brief existed and planned a different sprint ("one
> document model, not three"). The sprint that ran did not follow it, so the plan is recorded
> below under *what the original plan deferred* rather than quietly rewritten.

**What shipped.** MRI brain, the whole way through:

* `submission.py` — previous reports as input (≤5, ≤2 000 characters each, ≤6 000 total), with
  the whole submission defining the grounding text every check compares against.
* `report.py` — a sixth signed section (`follow_up`), plus `quality` and `confidence` inside the
  document, and `metadata.profile` / `metadata.compared_with`.
* `quality.py` — nine deterministic checks over the draft's own text: dropped observation,
  unsupported measurement, invented history, unsupported certainty, unsupported absence, format
  breach, invented identifier, self-reported confidence, structure coverage. No model grades the
  model, no thresholds, no nondeterminism.
* `profiles.py` — the MRI brain study profile: 14 structures with synonyms, and the negatives a
  brain study cannot support.
* `copilot.py` — the sign-off gate. Checks re-run on the text being signed; a `block` finding
  refuses the signature; a section the clinician rewrote is downgraded to `advisory`; the
  refusal carries check names and section names and no clinical text.
* `prompt.py` `0.3.0` — the number rule, the comparison rule, the hedge rule, follow-up kept
  apart from recommendations. The same prompt, versioned up; no second prompt was created.
* `api.py` + `static/index.html` — `POST /check` and the working screen. One static file, no
  external resource, no browser storage.
* `rendering.py` — quality and confidence in all three export formats, so a printed report
  shows what was checked.
* Tests: 225 in the copilot (45 of them on the quality engine), including negative,
  malformed-input and safety cases, and the six golden MRI brain cases.

**The claim this earns:** open the copilot, paste findings, get a structured report, review it,
approve it, export it — with no infrastructure, architecture or release work in the way.

### What the original plan deferred

The ERP already has the better shape (integration I1/I2). Adopt it; do not invent.

| Task | Effort | Notes |
| --- | --- | --- |
| 9.1 Structured findings in `RadiologyReport`: `key`, `text`, `laterality`, `negated`, `evidence[]`, typed `measurements` | 3–4 d | Mirrors `ShadowStructuredDraft` exactly |
| 9.2 Write the report into the ERP's `radiology_report_drafts.structured_json` as a **patch under the existing row lock** | 2 d | `persistCareStructuredFormatState.ts` — the lost-update bug is already documented there; do not build a second draft store |
| 9.3 Draft-pane UI: chips bound to observations, per-item accept, diff preserved | 3–5 d | Extends what `UsgAiDraftPanel.tsx` already does |
| 9.4 `GET /reports/{report_id}` and list/search | 2–3 d | Needed by the Audit Timeline and the metrics view |
| 9.5 Substantive-vs-cosmetic amendment classification | 1–2 d | The metric the product must earn (§5 of the workflow) |

**Total: 11–16 d estimate.** Value: laterality and negation become checkable fields, which
closes the threat model's only "not detectable" row, and one fewer place a report exists.

## 4. Sprint 10 — measure it against reality

| Task | Effort | Why it is a sprint and not a chore |
| --- | --- | --- |
| 10.1 Take 100 **reported** studies from the USG/MRI studios, keep the signed report as the expected answer, replace the authored goldens | 3–5 d with clinical time | `GOLDEN_DATASET.yaml` says `ratified: pending` on all 100 and names this exact method as the cheapest fix |
| 10.2 Run the six-step scoring against real `qwen3:14b`; publish per-category pass rates | 2 d | First honest answer to "is the draft good" |
| 10.3 Baseline the workflow: dictation-complete → signed, from ERP timestamps | 1 d | Without it, "saves time" is a claim about a product nobody has timed |
| 10.4 Decide the model class per capability from the measurements, not from the paper size | 1 d + owner | Feeds D-D and any cloud question |

**Total: 7–9 d plus a radiologist's afternoons.** This is the highest-value sprint in the
document: everything after Beta is gated on evidence that does not exist yet.

**Carried into this sprint from §3:** the document-model half that Sprint 9 did not reach —
structured findings with typed `laterality` / `negated` / `measurements`, the write into the
ERP's existing draft row under its lock, and `GET /reports`. Laterality and negation as *fields*
would replace two of the copilot's nine regex checks with something that cannot be fooled by
prose, so the deferred plan is now also the quality engine's next step.

## 5. Alpha → Beta gate

Beta is a **claim change**, not a feature set: in Alpha the copilot says "a human reviewed
this document"; in Beta the *platform* can say "this skill required an approval and this named
human granted it". To make that sentence true:

| Gate | Item | Effort | Depends on |
| --- | --- | --- | --- |
| **G1** | Individual clinician authentication in both studios (per-user login, role, session) | Hospital-side, **days-to-weeks** | D-B |
| **G2** | ADR-0005 approvals + the approvals primitive; migrate copilot-side review into it | 5–8 d | D-A, G1 |
| **G3** | Audit storage + retention period agreed (`core/audit`, Q3 answered) | 5–10 d | D-C |
| **G4** | Orthanc authenticated, CORS restricted, port not published (threat model F-C) | Hospital config, **hours** | — |
| **G5** | Golden set ratified (Sprint 10) and the emergency/medicolegal safety gate passing | see Sprint 10 | — |
| **G6** | Study Queue + `/triage` with documented degradation to acquisition order | 4–6 d | 8.0 latency |
| **G7** | Approval Screen and Audit Timeline as specified (`UI_UX.md` §6, §7) | 5–8 d | G1–G3. **Half met:** the copilot ships a working review-and-sign screen with the nine checks, the computed confidence and the blocking gate (`static/index.html`, `POST /check`). What remains is the ERP-integrated screen, the Audit Timeline, and a signer bound to a session rather than a typed name |
| **G8** | `/events` receiver (HMAC verify + idempotency + correlation) so withdrawals reach us | 2–3 d | integration §5 |
| **G9** | 10–15 skills authorised in `models.yaml`, each reviewed one at a time | 1 d per skill + clinical review | clinical owner time — the true bottleneck |

**Beta total: ~30–45 engineer-days plus hospital-side identity work and clinician review time.**
The identity work is the long pole and it is not ours; it is also the one that, if skipped,
makes everything else in this roadmap a decoration.

## 6. Beta → v1

v1 means a department can run this without an engineer in the room, and a second department
can ask for it.

| Work | Effort | Business value |
| --- | --- | --- |
| Pathology block: prompt 2 authorised, 10–15 golden cases from reported specimens | 5–8 d | The second product line, in the same hospital, with an existing skill (`pathology-review` is already authorised) |
| Emergency: `ed-triage-note` + one pathway skill, with the disposition-*question* rule enforced by a test | 6–10 d | The ED is where a late report costs the most, and where the "no disposition decision" rule must be proven |
| Discharge/referral/coding skills (`discharge-summary`, `referral-letter`, `icd10-coding-suggestion`) | 5–8 d | Largest recovered clinician-hours, lowest clinical risk, fastest way to get a non-radiology department to want the platform |
| Skill authorisation tooling: a checked, reviewable way to move a catalogue entry into `models.yaml` with its alias, and a CI assertion that the two agree | 3–5 d | Turns "121 designed skills" into a queue instead of a backlog |
| Search + metrics view (rewrite rate, refusal rate, p50/p95 latency) | 4–6 d | The only thing that lets a department trust the tool over time |
| Role model per department (radiologist vs technician vs coder), if `caller` scopes were added | 4–6 d | Procurement asks for it |
| PCPNDT surface: render the two `409`s as *waiting on the hospital*, and record Form F state in the queue | 2 d | **Statutory.** Ultrasound at this site without it is not deployable |
| Dark mode + tablet pass (`UI_UX.md` §10, §11) | 3–5 d | Adoption, in the room where the work happens |

**v1 total: ~35–55 d estimate.**

## 7. v1 → Enterprise

Enterprise at two hospitals is not "multi-tenant SaaS". It is N installations that a central
team can configure, and the domain model is explicit that `Tenant` must stay at zero
occurrences.

| Capability | Effort | Notes |
| --- | --- | --- |
| Per-hospital policy variants (same skill, different risk/approval/retention) | 6–10 d | Finally answers `DOMAIN_MODEL.md` Q1 honestly. Needs the Hospital identifier to exist as data, which it does not yet |
| Config distribution and drift detection across installs | 5–8 d | One change must not be applied by hand to N `models.yaml` files |
| Retention export to the hospital's own SIEM; evidence bundles for a medicolegal request | 4–6 d | The Audit Timeline is a screen; this is the artefact a lawyer wants |
| Capacity planning: concurrency ceilings, queueing, model warm-up budgets | 5–8 d | The ERP already models this for vision (`resourceFailureCode`, GPU OOM, context budget) — copy that, it is better than a guess |
| Signed artefact integrity (detached signature on the exported PDF, verifiable) | 4–5 d | Ties to the ERP's `signedArtifactGuard` |
| Uptime and upgrade story: versioned skills, migration of a stored document's schema | 5–10 d | `RadiologyReport` will need a schema version before it has users, not after |

## 8. Enterprise → FutureKind Cloud

Deliberately last, deliberately narrow, and the smallest section in this document on purpose.

**What cloud may mean here:** managed *skills and evaluation* — a hosted catalogue of reviewed
prompts, golden sets and scoring runs that an installation pulls down; model updates; a
support plane that sees metrics and never sees content.

**What it must never mean:** a place patient text goes for processing, or a shared database
across hospitals. That is P14 and P10, and it is the specific way a local-first healthcare
platform loses the right to call itself local-first. Any cloud path that receives care text is
an ADR, a written agreement with each hospital, and provenance that names the provider on the
report.

**Effort: not estimable yet.** The dependency is legal and commercial, not technical.

## 9. Risks, in the order that would end the product

| # | Risk | Likelihood | Impact | Mitigation | Early warning |
| --- | --- | --- | --- | --- | --- |
| R1 | A real `qwen3:14b` on the hospital's hardware is too slow for a drafting loop | **Unknown — never measured** | Product-level | **Sprint 8.0, first task** | A p95 over 20 s for one report, or over 3 s for a chip |
| R2 | Clinicians accept drafts without reading them | **High, and it looks like success** | Patient harm, then the product is switched off by management | §4 of the workflow (typing numbers, per-section accept, no draft-and-sign shortcut); publish rewrite rate, not throughput | Impression rewrite rate near zero while volume rises |
| R3 | Attribution stays false because identity is a shared PIN | High until G1 | Regulatory and legal; the platform's core claim is untrue | Beta gate G1, owned by the hospital | Any audit question that cannot be answered per person |
| R4 | Audit is claimed but not retained | Certain today | The word "auditable" becomes a liability | G3 + reword claims now (8.5) | An incident where the answer cannot be produced |
| R5 | A hallucinated finding reaches a signed report | Some non-zero probability per report — **and we cannot yet quantify it because the goldens are unratified** | One is enough to end the deployment | Safety gates, typed measurements, refusal on truncation, golden reruns on every model change | The first substantive rewrite that was accepted at draft time |
| R6 | Skill library outruns review capacity | High (121 designed, 6 authorised) | Either config drift or a stalled roadmap | One-skill-per-review authorisation, `status`/`blocked_by` fields already in place | Skills copied into `models.yaml` without clinical sign-off |
| R7 | P16 keeps eroding because host apps find direct model calls easier | High — already four paths | The governance boundary becomes decorative | Migrate one per sprint (§2 is the template); make the Gateway path *less* code than a direct call | A fifth direct call appearing during Beta |
| R8 | Procurement stalls on "who owns the data" | Medium | Commercial | The answers already exist: no cloud by default, no cross-hospital path, hospital owns the DB, provenance in the report | A question the answer to which requires an ADR |
| R9 | Scope creep into a reporting studio or an image reader | Medium, and it is *our* failure mode | Two systems of record; the platform dies of maintenance | §3.2 of the product spec is a written boundary; keep deleting | Any PR that adds a composer, a queue database, or pixel access |

## 10. What this roadmap deletes

Prefer deleting complexity, so the list is part of the plan.

- **`OLLAMA_URL`/`OLLAMA_MODEL` in the USG studio** — replaced by a skill and an alias (8.2).
  Application-level model selection is not a feature; it is the violation.
- **A FutureKind-side draft store** — the ERP's `structured_json` under a row lock already
  exists and already had the lost-update bug fixed. Keep the copilot's in-memory document only.
- **`configs/futurekind.yaml`'s monitoring claims** (`prometheus`, `grafana`,
  `opentelemetry`, `tracing: Langfuse`) until something is deployed. A manifest that advertises
  a capability the system lacks is how a review document becomes fiction (8.5).
- **The placeholder clinical layer — deleted 2026-10-08.** `genesis/` and `agents/` held
  **34 files, 14 of them zero bytes**, the rest 1–10 bytes of scaffolding stubs:
  `agents/radiology/prompt.md` contained the word `prompt`, `agent.yaml` contained `yaml`,
  `style-guide.md` and `genesis.md` contained `ai`, and six example files held two-to-eight
  characters of keyboard noise. Five were literally named `New Text Document.txt`; there was
  also an `er.txt`, a `4h.txt` and an `e.txt`. The brief was **delete the tree, or write it**,
  and writing it is clinical work this sprint was not allowed to invent, so it is deleted.
  What remains is the actual task, unchanged: author the doctrine, starting with the house
  style, and give `agents/<specialty>/agent.yaml` the schema R4 asks for. An empty
  `genesis/report_style.md` next to a constitution that cites it was worse than its absence,
  because it made a style authority look like it existed.
- **The duplicate idea** `plain-language-report` vs `patient-explainer` in
  `SKILL_LIBRARY.yaml` — one capability seen from two screens; merge when either is authorised.
- **Any `tier` field** on a model — `ADR-0002:155` refused it for having no data behind it, and
  it was right.

## 11. One-page sequence

```
Sprint 8  measure latency → govern the USG chip path → fix the mapping → close the 3 leaks
          EXECUTED. The chip path is governed in the ERP working tree (uncommitted); the three
          inventory leaks are closed; the release-readiness pass landed in this repository.
          The latency number is 3.9 tok/s on a workstation and is still not a hospital number.
Sprint 9  THE FIRST CLINICAL PRODUCT — MRI brain in a browser: submit → draft → nine
          grounding checks → named sign-off that refuses an unsupported draft → export.
          EXECUTED 2026-10-08 on feature/radiology-copilot-alpha.
Sprint 9' one document model (adopt the ERP's), report read/search — DEFERRED, not forgotten
Sprint 10 ratify the goldens, run them for real, baseline the workflow, then 9'
─────────────────────────────── ALPHA ENDS HERE ───────────────────────────────
Beta gate G1 identity · G2 approvals (ADR-0005) · G3 retention · G4 Orthanc · G5 evidence
          G6 triage · G7 approval+audit screens (half met by the copilot's own screen) ·
          G8 events · G9 10-15 skills
──────────────────────────────── Beta ────────────────────────────────────────
v1        pathology · emergency · documentation/coding · authorisation tooling · PCPNDT surface
Enterprise N installations, per-hospital policy, SIEM export, capacity ceilings
Cloud     managed skills and evaluation only. Never a place patient text goes.
```

**If only one thing in this roadmap is done:** Sprint 8.0 and 8.1-8.3. It costs about a week,
it converts a live ungoverned AI path into a governed one, and it produces the first real
number about whether any of the rest of this document is possible. **That sentence is now a
warning as much as a recommendation:** the product sprint happened, the screen works, and the
number is still missing. A radiologist using this on real studies at real speed is the next
unknown, and it is the one that decides whether any of it is usable.
