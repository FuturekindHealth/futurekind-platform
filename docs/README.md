# FutureKind documentation

The repository is mostly documents, deliberately. This index is the **ownership map**: it says what
each document is responsible for, and where it must stop. It exists because the constitution's P18
([`CONSTITUTION.md`](CONSTITUTION.md)) says a concept has one name, one owner and one definition —
and an unowned second owner is how two documents start disagreeing about the same object.

**If you are going to change something, read the row that owns it before you write a new section
somewhere else.**

---

## 1. The governing layer

| Document | Owns | Stops at |
| --- | --- | --- |
| [`CONSTITUTION.md`](CONSTITUTION.md) | Why FutureKind exists, the nineteen principles, what may never be traded, and the register of known non-conformance | Anything operational: it is not a specification, a design, a roadmap or a list of preferences |
| [`SPECIFICATION.md`](SPECIFICATION.md) | Normative platform requirements, with statuses (`[BUILT]`, `[PARTIAL]`, `[PLANNED]`, `[BLOCKED]`) and the "what must still wait" table | Implementation detail; no class, table or schema |
| [`DOMAIN_MODEL.md`](DOMAIN_MODEL.md) | **The naming authority.** One canonical word per idea, the four contexts, the recommended renames, and the unresolved questions for the owner | Behaviour and layout. A PR introducing a domain term with no row here is incomplete |
| [`adr/`](adr/) | Decision records: local-first (ADR-0001), Gateway versus LiteLLM ownership (ADR-0002) | Anything that is not a decision with a date |

## 2. The architecture layer

| Document | Owns | Stops at |
| --- | --- | --- |
| [`ARCHITECTURE.md`](ARCHITECTURE.md) | The target stack, and the clinical product **as built** — the seven modules, the four operations, the decisions that give the shape its meaning | Version numbers, and any claim about a box that does not exist |
| [`architecture/gateway-routing.md`](architecture/gateway-routing.md) | How a request reaches a model: the chain, attempts, degradation, timeouts | What a request may contain (that is the specification) |
| [`architecture/gateway-policy.md`](architecture/gateway-policy.md) | The policy layer: risk ladder, validation rules, approval and audit requirements | Which model answers. Never |
| [`architecture/APPLICATION_MAP.md`](architecture/APPLICATION_MAP.md) | Which applications exist, what each calls, what each reads and writes, where its record lives, and what configuration a new one needs — including §3.1, the ERP's eighteen ungoverned AI paths mapped to the application, refusal or deletion that takes each one | The words, the product choice, the screens, the sequence |

## 3. The product layer

| Document | Owns | Stops at |
| --- | --- | --- |
| [`product/README.md`](product/README.md) | The folder index, the numbers that matter, the product vision, and who has to review what | Architecture. Nothing in that folder changes it |
| [`product/PRODUCT_BIBLE.md`](product/PRODUCT_BIBLE.md) | The family: which applications exist, their kind, users, value, dependencies, shared components and risk; what was merged or refused | Individual skills, screens and order of build |
| [`product/CLINICAL_SUITE.md`](product/CLINICAL_SUITE.md) | Each application's design: document shape, sections a machine may write, checks, boundaries, priorities | Which applications exist; screens; safety gates |
| [`product/PRODUCT_SPECIFICATION.md`](product/PRODUCT_SPECIFICATION.md) | The radiology product's features, boundaries, commercial value, release shapes and success metrics | Workflow steps (that is the workflow document) |
| [`product/RADIOLOGY_WORKFLOW.md`](product/RADIOLOGY_WORKFLOW.md) | Radiology's twelve steps S0–S11, modality variations, the F1–F30 failure catalogue, automation-bias requirements, API needs | Other departments — [`clinical/HOSPITAL_WORKFLOW.md`](clinical/HOSPITAL_WORKFLOW.md) owns the rest of the journey |
| [`product/UI_UX.md`](product/UI_UX.md) | The radiology workspace, screen by screen, and the PHI discipline of surfaces | Tokens, keystrokes and cross-application patterns: those are [`design/DESIGN_SYSTEM.md`](design/DESIGN_SYSTEM.md) |
| [`product/SKILL_LIBRARY.yaml`](product/SKILL_LIBRARY.yaml) | The 121 designed skills, machine-checkable: risk, approval, audit, capability, status, blocker | Runtime. The only skill file the platform loads is `core/gateway/models.yaml` |
| [`product/SKILL_EXAMPLES.md`](product/SKILL_EXAMPLES.md) | Twelve skills at wire level, including the six highest-risk | Every skill. Twelve is the reviewed set |
| [`product/PROMPT_LIBRARY.md`](product/PROMPT_LIBRARY.md) | The running prompt verbatim, its version, its measured size, and the constraints it enforces | A second prompt for the same act — extend, do not fork |
| [`product/GOLDEN_DATASET.yaml`](product/GOLDEN_DATASET.yaml) | The evaluation corpus: 100 studies, six-step scoring, thresholds, hallucination probes — all imaging, and `ratified: pending` on every one | Any clinical text in the repository. It lives outside the tree |
| [`product/ROADMAP.md`](product/ROADMAP.md) | The sequence: sprints, the Alpha→Beta gates, v1, Enterprise, Cloud, risks with early warnings, what gets deleted, and §12's family waves | What exists (the map) and what it is worth (the business layer) |

## 4. The design layer

| Document | Owns | Stops at |
| --- | --- | --- |
| [`design/DESIGN_SYSTEM.md`](design/DESIGN_SYSTEM.md) | The shared language: tokens, the keyboard, the eleven patterns, review and approval as one pattern, accessibility and conformance | Any specific screen |
| [`design/UX_GUIDE.md`](design/UX_GUIDE.md) | The screen inventory, role and mode behaviour, cross-application handoff, the wording of every state, and the template a new screen spec must fill | Visual tokens and keystrokes |

## 5. The clinical-operations layer

| Document | Owns | Stops at |
| --- | --- | --- |
| [`clinical/HOSPITAL_WORKFLOW.md`](clinical/HOSPITAL_WORKFLOW.md) | The whole hospital: every node, what AI may help with there, the consolidated never-list, and who owns the workflow (answer: the EHR) | Radiology's internal steps, which stay in `product/RADIOLOGY_WORKFLOW.md` |
| [`safety/CLINICAL_SAFETY.md`](safety/CLINICAL_SAFETY.md) | Clinical harm: what each risk level forces a product to do, what the product may claim about a document, automation-bias obligations, the five entry gates, the contraindications and the safety register | Attackers, which are the threat model's |

## 6. The security and integration layer

| Document | Owns | Stops at |
| --- | --- | --- |
| [`security/THREAT_MODEL.md`](security/THREAT_MODEL.md) | Attackers and accidents: injection, PHI leakage, forged reports, hallucination as a threat, audit bypass, privilege escalation, residency, recovery, and the ranked findings | What a clinician should see on a screen |
| [`../SECURITY.md`](../SECURITY.md) | How to report a vulnerability, and the disclosure window | The threat model itself |
| [`integration/INTEGRATION_CARE_ERP_PACS.md`](integration/INTEGRATION_CARE_ERP_PACS.md) | The ERP and PACS contracts: sequences, auth, callbacks, lifecycle, versions, errors, retry, offline | Anything the ERP does not actually do — cited from its source where claimed |
| [`integration/AI_ENTRY_POINTS_CARE_ERP.md`](integration/AI_ENTRY_POINTS_CARE_ERP.md) | Every AI entry point in the ERP, its guard, its model call, and the one path migrated through the Gateway | The clinical design of what those paths should say |

## 7. The commercial and vision layer

| Document | Owns | Stops at |
| --- | --- | --- |
| [`business/COMMERCIAL_ROADMAP.md`](business/COMMERCIAL_ROADMAP.md) | Which motions suit which applications, what to sell first, cost to serve, the commercial refusals, and the decisions only the owner can make | The unit economics, which live in `product/PRODUCT_SPECIFICATION.md` §5 |
| [`VISION-2035.md`](VISION-2035.md) | How a hospital works differently in 2035 — workflow, not technology — and the three questions that decide whether it happened | Any plan, date or number that belongs to the roadmap |

---

## 8. Reading order, by who you are

| You are | Read, in this order |
| --- | --- |
| Evaluating the platform | `CONSTITUTION.md` → `ARCHITECTURE.md` (the as-built half) → `architecture/APPLICATION_MAP.md` → `SPECIFICATION.md` §16–§17 |
| Building the next application | `architecture/APPLICATION_MAP.md` §2 and §6 → `product/CLINICAL_SUITE.md` §1 → `design/DESIGN_SYSTEM.md` → `design/UX_GUIDE.md` §8 → `safety/CLINICAL_SAFETY.md` §6 |
| A clinician deciding whether to trust it | `README.md`'s intended-use sentence → `safety/CLINICAL_SAFETY.md` §3, §5 and §9 → `product/RADIOLOGY_WORKFLOW.md` §4 → `product/GOLDEN_DATASET.yaml` header |
| Running the hospital's side of it | `clinical/HOSPITAL_WORKFLOW.md` → `business/COMMERCIAL_ROADMAP.md` §5 and §7 → `product/ROADMAP.md` §12 |
| Reviewing a pull request | `DOMAIN_MODEL.md` (does this introduce a word?) → the document that owns the area → `scripts/doctor/check-citations.py` |

## 9. Three rules that keep this set honest

1. **A citation that has drifted is a defect in the citing document.** `path:line` pairs are checked
   by `scripts/doctor/check-citations.py` on every push; section-number pointers are not, so a
   numbered claim must carry a line.
2. **A count in a document is a promise.** Test totals, skill counts and version numbers are the
   first things a release pass invalidates; prefer the rule to the number, as
   `DOMAIN_MODEL.md` §1 now does.
3. **A second document for one thing is a defect.** Extend the artefact that owns the subject. This
   index is the record of who owns what, and a new document needs a row here on the day it is
   added.
