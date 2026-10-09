# FutureKind Product Bible

**Owns:** the product family — which applications exist above the platform, who uses each one,
what each produces, what each depends on, which are merged or refused, and the tests every
application must pass to be allowed to exist.
**Does not own:** individual skills (`SKILL_LIBRARY.yaml`), screens (`UI_UX.md`, `../design/UX_GUIDE.md`),
sequence (`ROADMAP.md`), words (`../DOMAIN_MODEL.md`), platform requirements (`../SPECIFICATION.md`),
commercial motions (`../business/COMMERCIAL_ROADMAP.md`).
**Status:** design. One application of the fourteen is built.
**Review required from:** the clinical owner — §8 lists the six decisions this document cannot
make alone, and `../DOMAIN_MODEL.md` Q6 says the risk level of every skill in the library is
still an engineer's guess.

---

## 1. The sentence, and the four tests

FutureKind is the platform; **the product is the set of applications that use it**. Every
application in this family must pass four tests, and each test is already written down
somewhere else — this document only applies them together:

1. **It asks for a skill and never for a model.** `SPEC-12-04` (`../SPECIFICATION.md:668-669`):
   a new application obtains a credential and names a skill; it *shall not* require a platform
   change and *shall not* hold a LiteLLM key. Fourteen applications is therefore a
   configuration and authoring problem, not a build problem — which is the same finding the
   skill library made about its own 121 entries (`SKILL_LIBRARY.yaml:17-20`).
2. **Its output has a human's name on it before it reaches a patient.** P3 and P11
   (`../CONSTITUTION.md:138-139`, `:285-287`): the AI may not sign, order, dispense or be the
   final author. In practice this means every application writes into a system of record that
   refuses an `ai|system|typist|bot` signer — the guard already exists in the ERP
   (`../integration/INTEGRATION_CARE_ERP_PACS.md:252`).
3. **It reuses the canonical objects instead of inventing its own.** P18
   (`../CONSTITUTION.md:413-414`): one name, one owner, one definition, or it does not enter the
   codebase. §5 lists which objects each application reads and writes; §6.2 names the merges this
   family decision made.
4. **It can be measured before it is trusted.** An application whose skills have no ratified
   golden cases cannot be authorised. This is not a paperwork rule: all 100 cases in
   `GOLDEN_DATASET.yaml` are imaging studies — counted from the file's own `modality:` field, 36
   CT, 20 US, 17 XR, 17 MRI, 5 CTA, 3 MG, 1 HRCT, 1 CTP — and **not one is a pathology report, a
   discharge summary or a ward note**. Thirteen of the fourteen applications in this family
   currently have no evaluation at all.

Test 4 is the most important sentence in this document. The constraint on the product family is
not models, screens or architecture; it is **three unbuilt platform primitives and one missing
evidence base**.

---

## 2. Three kinds of application, not twenty nouns

The brief named twenty products. Fourteen survive as applications; four were merged; two were
refused. The taxonomy is deliberately small because each kind has a different risk profile,
a different owner and a different release gate:

| Kind | What it does | What it produces | Risk driver |
| --- | --- | --- | --- |
| **Copilot** | Presents one Agent, drafts a document from a clinician's own words, gates it, exports it | A **Report** | A wrong sentence reaching a patient |
| **Surface** | Reads canonical objects and arranges them for a question. Drafts nothing | A view, a list, a comparison | Showing an incomplete record as if it were complete |
| **Console** | Reads the *institution's* record — throughput, quality, utilisation | A number, a cohort, an indicator | Governing by a metric nobody defined |

A Copilot is the only kind that can produce a clinical document, so it is the only kind that
needs a review-and-sign gate, a quality engine and a refusal path. A Surface and a Console must
never be given a draft box: an application that shows text in a box a clinician can accept
*is* a copilot whatever its name says. That single rule is what keeps this family from
turning into twenty chat windows.

---

## 3. The family

Skills are cited by `id` from `SKILL_LIBRARY.yaml`; the file owns their risk, approval, audit,
capability and status, and this document does not restate them.

### 3.1 Copilots

| # | Application | Primary user | The document it produces | Skills it needs (`SKILL_LIBRARY.yaml`) | Dependencies beyond the platform | Built? |
| --- | --- | --- | ---|---|---|---|
| 1 | **Radiology Copilot** | Reporting radiologist | Imaging report, five sections | `radiology-report` `SKILL_LIBRARY.yaml:105` plus the modality stanzas in sections 2–7 | Individual signer (Beta gate G1), audit retention | **Alpha, built** — `apps/radiology_copilot/` |
| 2 | **Pathology Copilot** | Reporting pathologist | Gross + microscopy + diagnosis + IHC panel | `pathology-review` `:970`, `cytopathology-report` `:982`, `haematology-bone-marrow-report` `:994`, `cervical-screening-report` `:1006` | A case set (test 4); a specimen-level Patient Context (ADR-0007) | Design |
| 3 | **Physician Copilot** | Ward doctor, resident | Daily note, problem list, medication review, summary | `ward-round-daily-note` `:786`, `problem-list-reconciliation` `:798`, `medication-reconciliation` `:810`, `clinical-summary` `:774` | A case set; ward data the ERP does not expose yet (§7.3) | Design |
| 4 | **Emergency Copilot** | ED physician, triage nurse | Triage note, pathway record, discharge instruction | `ed-triage-note` `:725`, `ed-chest-pain-pathway` `:737`, `ed-paediatric-fever-pathway` `:749`, `ed-discharge-instructions` `:761` | Time-critical decision support waits for ADR-0005 — `neuro-stroke-thrombolysis-check` `:687` is already marked `beta` for exactly that reason | Design |
| 5 | **Critical Care Copilot** | ICU consultant, registrar | ICU bulletin, family briefing, sedation and transfusion records | `intensive-care-bulletin` `:823`, `neuro-critical-care-family-briefing` `:1119`, `procedural-sedation-record` `:1094`, `transfusion-reaction-record` `:1081` | ADR-0005 (the transfusion record is `beta` for it); a case set | Design |
| 6 | **Theatre (OT) Copilot** | Surgeon, anaesthetist, theatre coordinator | Pre-anaesthetic assessment, operative note, post-op instruction, handover | `pre-anaesthetic-assessment` `:847`, `operative-note-draft` `:835`, `post-operative-instruction` `:859`, `stroke-rehabilitation-handover` `:1107` | A case set; **implants and consent are fields the ERP has no documented surface for** (§7.3) | Design |
| 7 | **Discharge Copilot** | Discharging clinician, medical records officer | Discharge summary, referral letter, follow-up plan | `discharge-summary` `:1343`, `referral-letter` `:1355`, `follow-up`-bearing stanzas in section 17 | A case set; the patient's medication list at discharge (`medication-reconciliation` `:810`, `critical`) | Design — the cheapest second product, see `ROADMAP.md` §12 |
| 8 | **Coding Assistant** | Coder, billing office, medical records | ICD-10 and procedure suggestions, authorisation and appeal letters | `icd10-coding-suggestion` `:1406`, `procedure-coding-suggestion` `:1418`, `prior-authorisation-letter` `:1430`, `claim-appeal-draft` `:1442` | Nothing new — but §6.4 explains why this one needs a rule no other application needs | Design |
| 9 | **Tumour Board Copilot** | MDT chair and members | One board summary, staging note, plan, survivorship or palliative plan | `tumour-board-summary` `:1218`, `tumour-staging-note` `:1231`, `oncology-treatment-plan` `:1243`, `survivorship-care-plan` `:1256`, `palliative-care-plan` `:1268` | **Cannot ship before ADR-0005**: a board decision binds several clinicians to one plan, and the library says so (`:1226`) | Design |

### 3.2 Surfaces

| # | Application | Reader | What it shows | Depends on | Built? |
| --- | --- | --- | --- | --- | --- |
| 10 | **Clinical Timeline** | Clinician at the bedside; referrer | One patient's care as ordered events: orders, studies, reports, approvals, drugs, follow-ups | ADR-0007 (Patient Context), `../DOMAIN_MODEL.md` Q2 — a timeline is exactly the artefact that must not be built on a guessed identifier | Design |
| 11 | **Audit Timeline** | Signer, quality lead, and an external authority | Who wrote, edited, accepted or refused which sentence of which report, and under which model and prompt | ADR-0003 retention — the platform emits `skill_audit` and stores nothing (`../ARCHITECTURE.md:307`) | Design. **A view of #10, not a second surface** (§6.2) |
| 12 | **Patient-Facing Text** | Clinician approves; patient reads | Plain-language summaries, pre-procedure and fasting instructions, appointment briefs | A human gate and a legibility rule; `patient-explainer` `:1467` and `plain-language-report` `:1479` merge into one skill (§6.2) | Design |

### 3.3 Consoles

| # | Application | Reader | What it answers | Depends on | Built? |
| --- | --- | --- | --- | --- | --- |
| 13 | **Hospital Command Center** | CEO, medical director, admin, infection control, bed manager | Turnaround time, backlog, utilisation, AI usage, cohort and indicator queries | ADR-0007 (a cohort cannot be assembled without a Hospital identifier — `cohort-extraction` `:1566` is `blocked` on it), plus a definition of every metric it prints | Design |
| 14 | **Clinical QA and Peer Review** | Quality team, NABH lead, department head | Whether reports were reviewed, what was amended, whether critical values were actioned, indicator trends | Audit retention; the amendment classification the roadmap already names as unbuilt (`PRODUCT_SPECIFICATION.md:240`) | **Prototype exists**: `scripts/validation/dashboard.py` is QA instrumentation for one department, and §6.5 treats it as the pattern |

### 3.4 Refused, and why

| Proposal | Refusal | Evidence |
| --- | --- | --- |
| **Medical Scribe** as an AI application | There is no speech path in the platform, and adding one is a platform change this brief forbids. The three capabilities are text-only (`core/gateway/models.yaml:142-166`) and a content-part array is refused with `422` rather than dropped silently. | The transcription the hospital runs today is outside the Gateway (`/ai/transcribe`, `AI_ENTRY_POINTS_CARE_ERP.md:80`) and stays there. What *is* a skill is the clean-up step, and `/ai/transcribe/polish` (`:79`) is one of the ungoverned paths this family has to absorb. A scribe application therefore = an ERP microphone + the Gateway's `radiology-report` skill on text. Nothing to build here except the boundary. |
| **Clinical Search** as an AI application | Search over the EHR is an ERP capability, not a model call, and the retrieval capability it would need does not exist (`guideline-citation` `:1528` is `blocked` on ADR-0006). | Building a second index of clinical text would create a second copy of patient data with different retention — the one thing P14 and the PHI rules forbid in a new shape. |
| **Medical Knowledge Assistant** | Cannot ship, and **no application in this family may present recalled text as guideline-derived** until citation exists. | `SPEC-08-06`; `SKILL_EXAMPLES.md:488`, `:504-518` — un-sourced recall must be labelled `citation_available: false`. This is a safety rule (§4), not a feature flag. |
| **Multidisciplinary Board** as separate from **Tumour Board** | One application, one name: #9. | P18. Two names for one act is the defect `SKILL_LIBRARY.yaml:31-33` already warns about for patient-facing text. |

---

## 4. Clinical risk across the family

The library's own distribution, counted from `SKILL_LIBRARY.yaml`: **37 critical, 49 high, 31
moderate, 4 low, and 116 of 121 skills require a named human approval**. Risk is not spread
evenly across the fourteen applications, and the family consequence is:

| Class | Applications | What follows for the design |
| --- | --- | --- |
| **Document with a decision inside** | #1, #2, #4, #5, #6, #9 | Must ship the full gate: deterministic checks, a refusal that cannot be overridden by the AI path, per-section amendment capture, and provenance on the saved document. The radiology copilot is the only implementation of this pattern so far, which makes it the family's reference, not its first chapter. |
| **Document that leaves the building** | #7, #8, #12 | The harm is not a wrong sentence inside the hospital, it is a wrong sentence a patient or a payer acts on. #8 additionally needs a rule no other application has: **a coding suggestion may not be the reason a service was billed** — billing must remain able to say no. `PRODUCT_SPECIFICATION.md:138-140` already treats the patient-facing letter as a clinical artefact in its own right. |
| **View of a record** | #10, #11 | The failure mode is a *silent absence*. A timeline that shows five of seven events is worse than no timeline. Requires: completeness stated on the surface, source named, and staleness visible. |
| **Number that governs** | #13, #14 | The failure mode is a metric with no definition. Every indicator in these two must be traceable to a counted event and a written definition, or it is deleted — the rule the validation dashboard already lives by (`ROADMAP.md` §4b: an impossible duration is labelled, not averaged away). |

Two cross-cutting rules:

- **Automation bias is a design requirement, not a training note.** `RADIOLOGY_WORKFLOW.md`
  states the requirement for the built product; §2 of `../design/DESIGN_SYSTEM.md` makes it a
  family rule: the source text stays visible next to the draft, the draft never overwrites a
  field silently, and the machine's confidence is computed from checks the clinician can see
  rather than asserted by the model.
- **Refusal is a product feature.** Every copilot must be able to say *no* — to a draft it
  cannot ground, and to a signature the checks block. `ROADMAP.md` §4b records what it costs:
  a check that refuses ordinary comparison prose four times in eleven sentences is a check
  that teaches clinicians to distrust correct refusals.

---

## 5. Shared components

The family exists only because this list is shared. Each item names the one document that owns
it, so nothing here is a second definition.

| Component | What it is | Owner document | Status |
| --- | --- | --- | --- |
| **The drafting loop** | submit → draft → deterministic checks → review → sign → export, as four stateless operations | `../ARCHITECTURE.md:244-288` | Built for radiology |
| **The Agent** | One specialty's persona: prompt, section structure, study profiles, the skill list it may name | `../DOMAIN_MODEL.md:565-595` (concept, `[ABSENT]`); realised as the four files an application already has — see §6.1 | Adopted by decision |
| **Grounding checks** | Text-vs-text checks with two severities, and a confidence computed from them | `quality.py`, documented in `../ARCHITECTURE.md:261-262` | Built, nine checks; **radiology-specific**: the phrase and structure lists must be per-Agent before a second copilot uses them |
| **Section ownership rule** | Which boxes a human may type in, decided by who wrote the text | `report.py::editable_section_keys`, `UI_UX.md` §4 | Built for radiology |
| **Refusal and failure language** | One error envelope, one guidance table, plain words, manual path always live | `../design/UX_GUIDE.md` §5 | Pattern proven in radiology |
| **Provenance block** | model, alias, prompt version, attempts, degraded, request id — attached to the document | `SPEC-06-10` (`../SPECIFICATION.md:330-331`) | Built |
| **Export and handoff** | text / markdown / json / print / clipboard into the system of record | `../design/DESIGN_SYSTEM.md` §7 | Built |
| **Review instrument** | A session that measures the clinician rather than scoring the model, and a reading of the finished afternoon | `scripts/validation/dashboard.py`, `ROADMAP.md` §4b | Built for radiology |
| **Design language** | Colour, type, density, shortcuts, icons, focus, modes | `../design/DESIGN_SYSTEM.md` | Design |
| **Canonical objects** | Study, Report, Observation, Impression, Approval, Sign-off, Task, Notification… | `../DOMAIN_MODEL.md` — the naming authority | §6.3 |

Two entries are the reason applications can be authored cheaply; one entry is the reason that
cheapness is dangerous: **the grounding checks are currently radiology-specific**. Porting
`radiology-report`'s checks to pathology without porting the phrase and structure lists would
produce an engine that refuses nothing, silently. Any new copilot therefore begins with its own
check audit, the way `ROADMAP.md` §4b did for radiology — measure per check, then decide the
severity.

---

## 6. Family decisions that delete complexity

### 6.1 An Agent is not a layer, and gets no directory

`agents/` and `genesis/` held sixteen placeholder files and were deleted on 2026-10-08
(`../DOMAIN_MODEL.md:583-588`); register row 10 of `../CONSTITUTION.md:546` records the authority
collision. R4 asked the question the deletion did not answer: *did a clinician choose a Skill or
did an Agent choose it?*

**Adopted answer: an Agent is the name for the specialty-authoring files inside one
application** — the system turn (`prompt.py`), the study structures (`profiles.py`), the document
shape and ownership rule (`report.py`), and the list of skills the application may name. The
radiology copilot already ships exactly those four files; the concept gets no new directory, no
new service and no new request field, and P17's stop line holds: **an Agent never appears in a
Gateway request** (`../CONSTITUTION.md:391-396`). The clinical answer to "who chose it" is: the
clinician chose the application, the application named the skill, and the record says which.

This also settles the *status* of the Clinical Documentation context in
`../DOMAIN_MODEL.md:84`: it stops being `[ABSENT]` when the first application is described in
these words, which is tonight, in design.

### 6.2 Merges

| Merged | Into | Why |
| --- | --- | --- |
| Audit Timeline | Clinical Timeline, as a second reader view | Same events, same store, different audience and retention rules. Two surfaces would be two places to be wrong about completeness. |
| Multidisciplinary Board | Tumour Board Copilot | One act, one name (P18). |
| Patient Summary | Discharge Copilot's output, shown on the Patient-Facing Text surface | A summary is a document, not an application. The brief's "Patient Summary" is `clinical-summary` (`:774`) and `discharge-summary` (`:1343`) rendered for a second reader. |
| Referral Intelligence | Discharge Copilot + Command Center | The letter is a document; the routing question is a cohort question. Splitting it into an application would hide the fact that neither half can ship before ADR-0007. |
| `patient-explainer` + `plain-language-report` | One skill, one voice | The library already flagged these as one capability seen from two screens (`SKILL_LIBRARY.yaml:33-35`). |

### 6.3 Objects reused, never redefined

Every application reads and writes the canonical objects named in `../DOMAIN_MODEL.md` §3; the
additions the family needs are proposed there (§ Clinical Documentation), not here, because that
file is the naming authority. The one rule this document adds is about *ownership of state*:

> **A copilot is stateless like the radiology one.** The document travels through the caller; the
> system of record is the ERP; FutureKind holds no second copy of a clinical document. A Surface
> or a Console reads the ERP too. An application that keeps its own clinical database is a second
> system of record, and `../DOMAIN_MODEL.md:487-489` already says where a Report belongs.

### 6.4 The coding rule, stated once

Coding is the only application whose output can change what a patient is charged or an insurer
pays. It therefore gets one constraint no other application needs: **the suggestion is derived
from the signed document, and the claim is derived from the suggestion by a human coder — never
from the model directly.** `SPECIFICATION.md:140-144` places billing outside the platform's
scope; this is the application-side consequence.

### 6.5 The QA console inherits the instrument, not a new one

`scripts/validation/dashboard.py` already measures review time, edits, words not typed, what the
reviewer did after each confidence badge, and the checks that fired on correct drafts. That is a
Clinical QA console for one department. #14 is that tool with a second reader (the quality
lead), not a second implementation — so its roadmap item is *expose the same rows over a
period*, and its risk item is *a metric with no definition*.

---

## 7. What the family needs from the platform — and what it must not ask for

### 7.1 Four decisions, unchanged and already named

| Need | Blocks | Where it is already recorded |
| --- | --- | --- |
| **Approval as a platform primitive (ADR-0005)** | 9 `beta` skills, every critical copilot's honest claim, Tumour Board entirely | `SPECIFICATION.md:901`; the nine `beta` stanzas and their `blocked_by` lines, e.g. `SKILL_LIBRARY.yaml:138` and `:1226`; `docs/product/README.md:111-115` |
| **Audit retention (ADR-0003)** | Audit Timeline, Medicolegal summary, every Beta claim about defensibility | `SPECIFICATION.md:900`; `../ARCHITECTURE.md:307` |
| **Hospital and Patient Context (ADR-0007, Q1, Q2)** | Timeline, Command Center, cohort work, anything referencing a patient | `SPECIFICATION.md:902`; `SKILL_LIBRARY.yaml:1574` |
| **Retrieval and citation (ADR-0006, SPEC-08-05)** | Knowledge Assistant, `guideline-citation`, any "per guideline" sentence | `SPECIFICATION.md:903`; `SKILL_LIBRARY.yaml:1536` |

Until each lands, the affected applications run with the application-side substitute and say so:
sign-off enforced by the copilot and the ERP together (the Sprint 7 model), provenance stored on
the document rather than in a queryable audit store, and no guideline claim at all. **A
substitute must be named in the product, not hidden in it** — that is the difference between a
provisional design and a false claim (SPEC-09-03, `SPECIFICATION.md:507-516`).

### 7.2 Nothing the family may ask for

No new capability, no new request field, no second AI boundary, no retry or failover logic in
the Gateway, no cross-hospital data, no `tier` axis: P16 and P14
(`../CONSTITUTION.md:372-374`, `:344-348`), `SPEC-12-05` (`../SPECIFICATION.md:671-673`) and
`SPEC-15-02`. Fourteen applications do not need one of these — a fact worth keeping in mind when
an application's first impulse is to ask.

### 7.3 The honest gap in the evidence base

This document can name the ERP's radiology tables from the integration record —
`radiology_report_drafts.structured_json`, `patient_reports` with `signedByName`/`verifiedByName`
and version `sequenceNumber`, `radiology_studies`, `integration_outbox`, `feature_flags`
(`../integration/INTEGRATION_CARE_ERP_PACS.md:19-25`, `:127-129`, `:254`, `:305-311`) — and it can
say what is **not** documented anywhere in this repository: registration and order tables,
pharmacy, wards, ICU, theatre as a clinical object, discharge, beds, NABH indicators, infection
control and turnaround time. Applications #3 to #8 and #13 therefore rest on assumption, not
evidence. **Before any of them is estimated, the ERP surface has to be walked and recorded the
way radiology's was** (`AI_ENTRY_POINTS_CARE_ERP.md` is the template). That is a day of work and
it is the cheapest de-risking item in this family.

---

## 8. Decisions this document cannot make alone

| # | Decision | Why it is the owner's, not the engineer's |
| --- | --- | --- |
| 1 | Confirm or correct the risk class of every skill the family adopts | `../DOMAIN_MODEL.md` Q6: an engineer assigned those values and they are live configuration |
| 2 | Which application is second | `ROADMAP.md` §12 gives the criteria and the recommendation; the choice sets what the hospital is asked to review |
| 3 | Whether an application may sign into the ERP with a per-user identity before G1 exists | Beta gate G1 is hospital-side; every copilot inherits the answer |
| 4 | The identifier that means "this patient" inside FutureKind | Q2. A wrong identifier format outlives every convenience (`../DOMAIN_MODEL.md:439-441`) |
| 5 | Whether the ward, theatre and ICU data the family assumes exists is actually in the ERP | §7.3 — unverified, and it changes three estimates |
| 6 | Whether a coding suggestion may ever be auto-applied | §6.4. This is a liability decision |

---

## 9. What this document is

Design, written against the two named sites and the code that exists. It claims no measurement
about any unbuilt application, and it deliberately owns no skill, no screen and no sequence —
so that when an application is built, the argument about what it *means* has already been
settled once, in this file and its three owners.

## 9. What is shared, and what is not (Genesis Night 4)

This file owns the family; the argument for the split below is in
[`../BLUEPRINT.md`](../BLUEPRINT.md) §4. What belongs here is the rule an application author
can apply without re-reading it.

> **The two-user rule.** A shared thing is built when its second user exists — except for
> vocabulary, policy, the review pattern and the evidence format, which are shared by
> definition because none of them is a service.

| Layer | Status for a fourteenth application |
| --- | --- |
| Terminology (`../DOMAIN_MODEL.md`) | **Shared now.** One word per thing is the only asset that appreciates. |
| Policy (`core/gateway/models.yaml`) | **Shared now.** Risk, approval, audit and downgrade as data a clinician can read. |
| Review and sign-off pattern (`../design/DESIGN_SYSTEM.md` §7) | **Shared now.** A second approval UI is a second clinical risk model. |
| Evidence format (golden case shape, audit line shape, provenance fields) | **Shared now.** The format is common; the content belongs to each department. |
| Identity, retention, analytics | **Not yet.** Each is gated behind an unwritten ADR, and building one early invents its shape for everyone. Retention is the exception: it is not premature, it is owed. |
| A shared UI framework, a model catalogue beyond aliases, hospital-wide search, a notification bus, a document store | **Refused.** Not deferred — refused, with the reason in `../INVARIANTS.md` §1. |

The failure this rule prevents is the pleasant one: a team builds a platform layer because
two documents describe similar screens, and the layer has one user, no evidence, and a
dependency graph that now needs the second application to arrive *correctly*. Fourteen
applications were designed in one night; one exists. Until a second is real, the shared
things are the four above, and every other "common service" is a private thing with extra
ceremony.

*FutureKind · Genesis Night 3 · 2026-10-09. Nothing here has been reviewed by a clinician other
than the platform owner. §9 added Genesis Night 4 · 2026-10-09.*
