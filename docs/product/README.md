# FutureKind product layer

Genesis Night output — what the platform is *for*, written against the two sites that will
run it: **CARE Diagnostics** and **Hope Neurotrauma & Multispeciality Hospital**.

Nothing in this folder changes the architecture. `Gateway → LiteLLM → providers` is accepted
as built; everything here is above it.

## Reading order

| # | Document | What it is | Status |
| --- | --- | --- | --- |
| 1 | [`RADIOLOGY_WORKFLOW.md`](RADIOLOGY_WORKFLOW.md) | Patient arrival → signed report in HIS/ERP/PACS. Steps S0–S11 with the shipped path drawn from the code, five modalities, 30 failures each stating whether code can detect it, the automation-bias requirements, the API surface | **S4–S6 built** for MRI brain — dictation → draft → nine checks → named sign-off → export, plus the keyboard, print and clipboard handoff and the client's handling of six ways the AI can fail. S0–S3, S5's viewer and S7–S11 remain design |
| 2 | [`PRODUCT_SPECIFICATION.md`](PRODUCT_SPECIFICATION.md) | Features, modules, clinical and commercial value, boundaries, release shapes, success metrics | M1 built in Alpha; the rest design |
| 3 | [`SKILL_LIBRARY.yaml`](SKILL_LIBRARY.yaml) | 121 clinical skills, machine-checkable: risk, approval, audit, capability, status, blocker, examples | Design catalogue; **6** skills are authorised in code |
| 4 | [`SKILL_EXAMPLES.md`](SKILL_EXAMPLES.md) | Twelve skills at wire level — the six highest-risk and six non-obvious output shapes | Design; all 12 currently return `unknown_skill` |
| 5 | [`PROMPT_LIBRARY.md`](PROMPT_LIBRARY.md) | Six specialties, versioned prompts, constraints, output schemas, failure modes, evaluation | **1 running** (radiology `0.3.1`), 5 designs |
| 6 | [`GOLDEN_DATASET.yaml`](GOLDEN_DATASET.yaml) | 100 representative studies, six-step scoring, pass thresholds, hallucination probes | Authored by an engineer; **`ratified: pending` on all 100** |
| 7 | [`UI_UX.md`](UI_UX.md) | Eleven screens plus dark and tablet modes, PHI discipline, build order | Design; §6's Approval Screen has an interim version running inside the copilot |
| 8 | [`ROADMAP.md`](ROADMAP.md) | Sprint 8–10, Beta gate G1–G9, v1, Enterprise, Cloud; risks with early warnings; what gets deleted; **§12 the family waves** | Plan |
| 9 | [`PRODUCT_BIBLE.md`](PRODUCT_BIBLE.md) | The family above the platform: fourteen applications in three kinds, the four tests every application must pass, what was merged and what was refused | Design; one application of the fourteen is built |
| 10 | [`CLINICAL_SUITE.md`](CLINICAL_SUITE.md) | Each application's design — document shape, sections a machine may write, checks, boundaries, priorities — with Radiology 2.0 ranked | Design; the radiology half is partly built |
| — | [`../design/DESIGN_SYSTEM.md`](../design/DESIGN_SYSTEM.md), [`../design/UX_GUIDE.md`](../design/UX_GUIDE.md) | The shared language: tokens, keyboard, eleven patterns; then the screen inventory and the wording of every state | Tokens and keystrokes read out of the built screen |
| — | [`../architecture/APPLICATION_MAP.md`](../architecture/APPLICATION_MAP.md) | Which application calls what, reads and writes what, and where its record lives; the three authorised skills nothing calls | Design; one row is built |
| — | [`../clinical/HOSPITAL_WORKFLOW.md`](../clinical/HOSPITAL_WORKFLOW.md) | The whole hospital mapped, with the consolidated never-list and the answer to who owns the workflow | Mapped; most nodes are `assumed`, not documented |
| — | [`../safety/CLINICAL_SAFETY.md`](../safety/CLINICAL_SAFETY.md) | What each risk level forces a product to do, what may be claimed about a document, the five entry gates, the contraindications | Framework complete; **no application has passed the gates** |
| — | [`../business/COMMERCIAL_ROADMAP.md`](../business/COMMERCIAL_ROADMAP.md), [`../VISION-2035.md`](../VISION-2035.md) | Which motions suit which applications and what to sell first; how a hospital works differently in 2035 | Estimates, labelled as such |
| — | [`../README.md`](../README.md) | **The ownership index of the whole document set.** Read this before adding a document anywhere | Current |
| — | [`../integration/INTEGRATION_CARE_ERP_PACS.md`](../integration/INTEGRATION_CARE_ERP_PACS.md) | Sequences, REST contracts, auth, callbacks, lifecycle, version history, errors, retry, offline | Design against the ERP's actual source |
| — | [`../integration/AI_ENTRY_POINTS_CARE_ERP.md`](../integration/AI_ENTRY_POINTS_CARE_ERP.md) | Every AI entry point in the CARE ERP, the one migrated in Sprint 8, its tests, rollback and measured latency | **Executed in the ERP working tree — not yet committed or merged.** The Gateway side (`usg-advisory-suggestions` in `models.yaml`) is here; the calling side is not, so no clinician can reach that skill from the ERP until the ERP change lands. Read §10 of that document before treating this migration as shipped |
| — | [`../security/THREAT_MODEL.md`](../security/THREAT_MODEL.md) | Prompt injection, PHI leakage, malicious reports, hallucination, audit bypass, privilege escalation, residency, recovery | Assessment with five ranked findings |

## Executive summary, in the numbers that matter

| | |
| --- | --- |
| Skills designed | **121** — `status` split, counted from the file: 110 alpha · 9 beta · 2 blocked |
| Skills authorised in `core/gateway/models.yaml` | **6** — five designed here, one migrated from the CARE ERP in Sprint 8 |
| Skills that cannot be authorised as designed | **2** — `guideline-citation` needs retrieval and citation (ADR-0006), `cohort-extraction` needs Hospital and Patient context (ADR-0007). Neither needs a new model capability; none of the 121 needs vision |
| Clinical risk distribution | 37 critical · 49 high · 31 moderate · 4 low |
| Requiring human approval | **116 of 121** |
| Golden evaluation studies | **100** (15 normal · 20 emergency · 40 common · 15 rare · 10 medicolegal) |
| …ratified by a clinician | **0** |
| Prompts running in code | **1** — `radiology-report-draft/0.3.1` |
| Deterministic safety checks on a draft | **9**, run three times (draft, every edit, before signature). Six of them can refuse the sign-off; none of them asks the model |
| Tests in the repository | **775** — 492 Gateway and 255 copilot (both in CI), 28 on the validation dashboard (`scripts/validation/`, not in CI) |
| Real-model latency measurements | **0.** The only timing taken is 27–30 ms against a stub |
| Ungoverned direct-to-model paths at the customer | **at least 4**, of which one uses a vision model and one selects its model from an environment variable |

**What that means.** The platform is not the constraint. Four decisions — approvals
(ADR-0005), a citation capability (ADR-0006), individual authentication of the signer, and
audit retention — stand between Alpha and Beta, and three of them are conversations. The
third and fourth are the ones that make the product's central claim true or false, and both
are cheap relative to what they unlock.

**The product, in one line.** FutureKind drafts; a named clinician decides. Every sentence in
a report can be traced to the model, alias, prompt version and request that produced it, and
to the human who accepted or rewrote it — and nothing the AI produces is a decision.

**The next sprint worth doing** adds no new capability either, and it is the same one the
roadmap has named since Genesis Night: time a real model on the hospital's own hardware. Two
things have changed since that sentence was written — Sprint 8 governed the ultrasound chip
path (in the ERP's working tree, not yet merged), and Sprint 9 shipped a product a radiologist
can actually open and use. So the measurement is no longer only about tokens per second. It is
twenty consecutive MRI brains through the copilot on the clinic's machine, with a radiologist
recording how often they reached for the keyboard: rewrite rate, blocking findings per study,
and wall time. That single afternoon produces the first evidence for every claim in this
folder, and it is the cheapest item in the roadmap.

## Product vision

Healthcare does not have an AI problem; it has a **documentation and attribution** problem.
The reading is done by a person, the decision is made by a person, and the hours go into
writing down what the person saw and proving afterwards who wrote it. A chat window in a
hospital coat does not solve that: it produces text with no owner, no trace and no gate.

FutureKind's bet is that the useful unit in clinical AI is not the model and not the prompt —
it is the **skill**: a named clinical intent, with a declared risk level, a mandatory audit
requirement, a capability class, an alias that routes it, and a policy block that travels with
every answer. Twelve of those skills, in twelve documents, in one platform, is what turns
"we added AI to the radiology department" into "the hospital has a governed boundary where its
AI work happens."

Three commitments make the shape coherent, and each is falsifiable in the code:

1. **The hospital owns the data as a physical fact.** Local-first is not an encryption
   posture; it is that the model, the router, the store and the archive are in the building,
   and `internet_required: false`. Cloud is optional, declared by the operator, named in the
   report's provenance, and never chosen by a caller.
2. **A clinical final state has a human behind it.** No AI path can sign, deliver, notify or
   release. Where the platform cannot yet enforce that as a first-class Approval, it says so —
   the Gateway *refuses* a skill that declares `approval_required` rather than pretending.
3. **Traceable or labelled.** Every answer carries which model gave it, how many attempts,
   whether it was degraded, and which prompt version shaped it. A lesser model may not answer
   silently, which is why the golden set exists: "lesser" has to be measurable or the promise
   is decoration.

The ambition in the brief — the healthcare AI operating system for hospitals — is right, and
the route to it is not a bigger platform. It is **skill after skill after skill**, each
reviewed, each authorised one at a time, each scored against cases a clinician ratified, on
the hardware the hospital already owns. A platform earns that position by being the only place
a hospital's AI work can happen safely, and that is an accumulation of 120 small reviewed
decisions, not a architecture rewrite.

## Who has to review what

| Reviewer | Must read | To decide |
| --- | --- | --- |
| **Clinical owner (radiologist)** | `GOLDEN_DATASET.yaml` header + 20 cases of their choosing; `RADIOLOGY_WORKFLOW.md` §S4–S6, §4 | Whether the expected answers are right, and whether the automation-bias rules are acceptable in practice |
| **Clinical owner** | `SKILL_EXAMPLES.md` §A (the six critical) | Whether the six highest-risk skills are safe to design at all |
| **Hospital administrator** | `../security/THREAT_MODEL.md` §10 findings F-A and F-C | Individual logins; authenticating Orthanc. Both are hours-to-days and both are the hospital's |
| **Platform owner** | `ROADMAP.md` §0 (D-A…D-D) | Approvals, identity, retention, vision |
| **Everyone** | `SKILL_LIBRARY.yaml` header | That 121 intents is a review problem, not a build problem |

## Standing contradictions, recorded rather than smoothed over

The full list is in the Genesis Night report; the four that matter most:

1. **Human approval is mandatory and the platform cannot grant it — so critical skills are
   unreachable in both directions.** Declaring `approval_required: false` on a `critical`
   skill fails catalogue load; declaring `true` fails every request with `403`. **37 of the
   121 designed skills are `critical`.** Resolved honestly in Alpha by enforcing sign-off twice
   (copilot + ERP) and naming ADR-0005 as the single decision that opens that class.
2. **P16's single AI boundary is contradicted by the customer's own systems** — four live
   direct-to-model paths, including an image-grounded MRI drafting pipeline the Gateway cannot
   host because it has no vision capability and no job model.
3. **The ERP's clinical document model is still better than FutureKind's.** `ShadowStructuredDraft`
   has laterality, negation and evidence anchors as *fields*; `RadiologyReport` has six prose
   strings and nine checks that compare them with the submitted text. The checks are a
   second-best answer, not the same answer: a regex over prose misses `two lesions`, and prose
   cannot say *which* lesion a measurement belonged to. Adopt the ERP's shape (roadmap §3,
   deferred into Sprint 10) rather than growing the prose to compensate.
4. **Audit is advertised in three places and retained in none.** Until `core/audit` writes and
   a retention period exists, the honest wording is "emits".

---

*FutureKind · Genesis Night · 2026-10-08. These documents are engineering work; the code that
has landed out of them is M1, the radiology copilot. Nothing in this folder has been reviewed by
a clinician, and nothing here is a clinical instruction.*
