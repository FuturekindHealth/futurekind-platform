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

## 8. The synthesis and governance layer

Genesis Night 4 was a thinking sprint: no code, and no new authority except where none
existed. Each row below owns something no earlier document did — and the mapping of the
sprint's eighteen named outputs onto these files is stated once, in
[`BLUEPRINT.md`](BLUEPRINT.md) §0, so no second copy exists to disagree with.

| Document | Owns | Stops at |
| --- | --- | --- |
| [`BLUEPRINT.md`](BLUEPRINT.md) | The ten-year answer, every boundary judged, the ecosystem verdict, the competitive position, the output mapping, founder notes and lessons | Rules, names, arrangement, sequence — all of which already have owners above |
| [`PHILOSOPHY.md`](PHILOSOPHY.md) | The *reasons* for the principles, the fundamental-versus-accidental test, the five philosophies, and the assumptions that could falsify them | The principles themselves. Where the two disagree, the constitution is right and this file is the defect |
| [`CONCEPTUAL_DEBT.md`](CONCEPTUAL_DEBT.md) | Debt of ideas: duplicated concepts, vocabulary, authorities and hidden coupling, ranked with the command that measured each, and the deletion list | Principle violations (`CONSTITUTION.md` §7), implementation sequence (`product/ROADMAP.md`) |
| [`FAILURE-MODES.md`](FAILURE-MODES.md) | Ranked ways this project fails, each with an earliest checkable warning sign; the success signals; the kill criteria | Threats from an attacker (`security/THREAT_MODEL.md`), clinical gates (`safety/CLINICAL_SAFETY.md`) |
| [`INVARIANTS.md`](INVARIANTS.md) | The refusal register (`N`) with the pressure behind each refusal, and the protection register (`M`) with the first sign of loss | The clinical never-rows (`clinical/HOSPITAL_WORKFLOW.md` §5) and the principles underneath both |
| [`GOVERNANCE.md`](GOVERNANCE.md) | Decision rights, the four seats, the clinical veto, the amendment queue, the open-source strategy and the foundation triggers | The principles being governed, and the pricing arithmetic |
| [`FIRST-WEEK.md`](FIRST-WEEK.md) | The onboarding path, the seven things that must survive any rewrite, the traps, and the first pull request | Anything that is a rule, a name or a specification |

## 9. Reading order, by who you are

| You are | Read, in this order |
| --- | --- |
| Evaluating the platform | `CONSTITUTION.md` → `ARCHITECTURE.md` (the as-built half) → `architecture/APPLICATION_MAP.md` → `SPECIFICATION.md` §16–§17 |
| Building the next application | `architecture/APPLICATION_MAP.md` §2 and §6 → `product/CLINICAL_SUITE.md` §1 → `design/DESIGN_SYSTEM.md` → `design/UX_GUIDE.md` §8 → `safety/CLINICAL_SAFETY.md` §6 |
| A clinician deciding whether to trust it | `README.md`'s intended-use sentence → `safety/CLINICAL_SAFETY.md` §3, §5 and §9 → `product/RADIOLOGY_WORKFLOW.md` §4 → `product/GOLDEN_DATASET.yaml` header |
| Running the hospital's side of it | `clinical/HOSPITAL_WORKFLOW.md` → `business/COMMERCIAL_ROADMAP.md` §5 and §7 → `product/ROADMAP.md` §12 |
| Joining the project, with a week | [`FIRST-WEEK.md`](FIRST-WEEK.md) — five days, one written answer each, then the seven things that must survive any rewrite |
| Deciding whether to trust it with a patient | [`CONSTITUTION.md`](CONSTITUTION.md) §7, then [`FAILURE-MODES.md`](FAILURE-MODES.md) §1, then [`INVARIANTS.md`](INVARIANTS.md) §1 |
| Reviewing a pull request | `DOMAIN_MODEL.md` (does this introduce a word?) → the document that owns the area → `scripts/doctor/check-citations.py` |

## 10. Four rules that keep this set honest

1. **A citation that has drifted is a defect in the citing document.** `path:line` pairs are checked
   by `scripts/doctor/check-citations.py` on every push; section-number pointers are not, so a
   numbered claim must carry a line. The checker verifies that a cited line *exists and is
   non-blank* — it cannot verify agreement, which is why a drifted-but-non-blank line has passed
   before (`CONCEPTUAL_DEBT.md` D13).
2. **A fact that moves has one home; documents point, they do not copy.** Test totals, skill
   counts, citation counts and version numbers are the first things a release pass invalidates.
   A number in prose is allowed only if it is dated or produced by a command — otherwise it is
   deleted, not corrected.
3. **A second document for one thing is a defect.** Extend the artefact that owns the subject. This
   index is the record of who owns what, and a new document needs a row here on the day it is
   added.
4. **A new document names the check that fails when it drifts.** A guard test, a validator, a
   conformance question, or an explicit "nothing — this is prose". A document that cannot answer
   is a restatement, and restatements rot quietly while looking like progress.

## 11. The evidence layer

Genesis Night 5 built instruments, not arguments: [`evidence/`](evidence/) is the layer that answers
"does this help clinicians?" with a number, and its code is
[`../scripts/validation/evidence/`](../scripts/validation/evidence/) — the only place in this
repository where a measurement is defined. Mapping the sprint's twelve named outputs onto these
files is stated once, in [`evidence/FRAMEWORK.md`](evidence/FRAMEWORK.md) §0, so no second copy
exists to disagree with (rule 3).

| Document | Owns | Stops at |
| --- | --- | --- |
| [`evidence/FRAMEWORK.md`](evidence/FRAMEWORK.md) | What counts as evidence here, the record shape, the three states a number may be in, and what this framework is still missing | Any number. It points at commands |
| [`evidence/HANDBOOK.md`](evidence/HANDBOOK.md) | How to run the instruments, what each verb refuses, and how to prove a refusal still refuses | What a result means clinically |
| [`evidence/PROTOCOL.md`](evidence/PROTOCOL.md) | The study: participants, endpoints, sizes computed before the run, and the one afternoon's procedure | A result. None exists |
| [`evidence/ERROR_TAXONOMY.md`](evidence/ERROR_TAXONOMY.md) | The 26 error classes, generated from the code that defines them | The definitions themselves, which live in `evidence/taxonomy.py` |
| [`evidence/METRICS.md`](evidence/METRICS.md) | Every metric's formula, denominator, gaming route and disposition — including the ones deleted | The six axes' refusal to become one |
| [`evidence/GROUND_TRUTH.md`](evidence/GROUND_TRUTH.md) | What a case must carry to be an expected answer, and who may say so | The cases. A clinical authority supplies those |
| [`evidence/BENCHMARK.md`](evidence/BENCHMARK.md) | What a department's benchmark consists of, and the rungs that promote one | Cross-hospital comparison, which P14 restricts |
| [`evidence/RESEARCH.md`](evidence/RESEARCH.md) | Tables, statistics, figures, export, and the anonymisation gate in front of them | Interpretation |
| [`evidence/EXPERIMENTATION.md`](evidence/EXPERIMENTATION.md) | A/B design: allocation, order, registration, analysis, multiplicity | Any experiment run, because none has been |
| [`evidence/IMPROVEMENT.md`](evidence/IMPROVEMENT.md) | Both feedback loops, the regression gates, and the four longitudinal questions | Applying a change — `apply()` raises |
| [`evidence/ANALYTICS.md`](evidence/ANALYTICS.md) | Seven readers, what each must never see, k-anonymity, and multi-site limits | Permission, which the Gateway owns |
| [`evidence/EVIDENCE_ROADMAP.md`](evidence/EVIDENCE_ROADMAP.md) | The order the evidence gets built, priced in human hours | The product sequence, which `product/ROADMAP.md` owns |
| [`evidence/BASELINE.md`](evidence/BASELINE.md) | The one real measurement available before a model runs, generated by `python -m evidence baseline --markdown` | Hand-editing. The file is the command's output |

You are measuring something: `evidence/HANDBOOK.md` §1 first, then whichever of the three above owns
your question — a metric, a study, or a reader's view.
