# FutureKind Clinical Safety Guide

**Owns:** the clinical-harm model for everything built above the platform — what each risk level
forces an application to do, what the product is allowed to claim about a document, the obligations
that counter automation bias, the gates an application passes before it touches a patient, and the
places this family refuses to deploy.
**Does not own:** attackers (`../security/THREAT_MODEL.md`), the words (`../DOMAIN_MODEL.md`), the
workflow (`../clinical/HOSPITAL_WORKFLOW.md`), the screens (`../design/DESIGN_SYSTEM.md`,
`../design/UX_GUIDE.md`), sequence (`../product/ROADMAP.md`).
**Status:** the framework is complete; **no application in the family has passed the §6 gates**,
because no clinician has yet used one on a patient.

---

## 1. The line between this and the threat model

The threat model asks who could make this system cause harm, and what stops them. This document
asks the quieter question: **what happens when the system is believed.**

The two must be answered about the same artefact, because the failure they describe is shared.
A forged report and a hallucinated one both reach a patient as a signed sentence; the difference
is intent, and a patient cannot see it. So where `../security/THREAT_MODEL.md` §4 covers a forged
document and §5 covers hallucination as a threat, this document covers the *design consequences*
of both: what a screen must show, what a check must refuse, and what nobody may claim about the
difference.

One sentence, for the reader who only gets one: **security is about not being tricked; safety is
about not being trusted too much.** Both are required for the same signature.

---

## 2. The risk ladder, and what each rung forces a product to do

The ladder and its startup rules belong to the platform (`../architecture/gateway-policy.md:74-102`):
`unspecified` is not declarable and is reported visibly; every skill must declare a risk;
`high` or `critical` forces audit and forbids downgrade; `critical` forces approval. What this
document adds is the **product-side obligation** for each rung, because the platform's rule is a
config constraint and a clinician cannot read configuration.

| Declared risk | Platform rule at load | What the application must therefore show or do |
| --- | --- | --- |
| **low** | audit optional | A result with no clinical consequence may be dismissed by the user. It may not be *filed* anywhere a patient record reads as clinical |
| **moderate** | audit optional, downgrade allowed | The user must be able to see what was proposed before it entered the document. Silent substitution is allowed by policy here and **not** by product: a lesser model answering quietly is the same defect whatever the ladder permits |
| **high** | `audit_required: true`, `allow_downgrade: false` (`../architecture/gateway-policy.md:96-97`) | Per-section provenance, a review act that can be refused, and a named human on the output. This is the rung the shipped radiology skill sits on (`core/gateway/models.yaml:62`) |
| **critical** | `audit_required: true`, `allow_downgrade: false`, `approval_required: true` — the last of those is rule 5, `../architecture/gateway-policy.md:98` | **Currently unreachable.** Declaring `approval_required` makes every request `403` until ADR-0005 exists, and *not* declaring it on a critical skill fails catalogue load (`docs/product/README.md:111-115`). So all 37 critical skills in the design library are, today, either not authorisable or authored down to `high` |

**That row is the most important safety finding in this document, and it is a fact about
configuration, not opinion.** Counted from `core/gateway/models.yaml`: the six authorised skills
carry `low`, `high`, `high`, `moderate`, `low` and `moderate`
(`:51`, `:62`, `:74`, `:87`, `:99`, `:127`). **Not one is `critical`.** Which means either no
critical work has been authorised, or critical work has been declared as high in order to run at
all. Both readings are true of the radiology skill: drafting an impression is `high` because the
sign-off is enforced in the application and in the ERP twice over — a defensible choice, and an
unratified one (`../DOMAIN_MODEL.md` Q6 says an engineer assigned those levels and the clinical
owner has not confirmed them).

Until ADR-0005 lands, the family's rule is: **a critical act is drafted, never completed, and the
product says which it did.** "We refused this signature" is a safety feature; "the platform
approved it" is a claim no one may make yet.

---

## 3. Intended use, and the foreseeable misuse that is not a user error

**Intended use.** FutureKind applications convert a clinician's own words, and the record they are
given, into a structured document; they check that conversion mechanically; they refuse a signature
when the conversion asserts something its inputs do not support; and they attach to the result
which model, alias, prompt version and policy produced it. They do not interpret images, do not
decide, and do not deliver.

The misuses below are foreseeable, which means they are design inputs rather than training
problems:

| Foreseeable misuse | Why it will happen | What the design does about it |
| --- | --- | --- |
| Skim-signing a draft because it looks finished | A well-formed report is its own argument. `../product/PRODUCT_SPECIFICATION.md:240` already names the only quality metric that matters as the **substantive** rewrite rate, and it is not built | The source stays adjacent to the document; the band says `review-carefully`, not a score; the refusal is a block, not a warning |
| Using a draft as a checklist while reading the images | That is what a list of structures looks like | `structure_coverage` reports what the *text* omitted, never what the *study* showed; the wording says so (`../ARCHITECTURE.md:280-283`) |
| A trainee accepting the machine's phrasing as the teaching | The screen cannot tell who is reading | Same screen for everyone; the explanation of a check is available, never hidden by rank (`../design/UX_GUIDE.md` §3) |
| Treating a console number as a compliance statement | A dashboard looks like a finding | No metric without a counted event and a written definition; accreditation claims remain the hospital's signed statement (`HOSPITAL_WORKFLOW.md` §3) |
| Asking a copilot "what should I do" | The box is on the screen | There is no box. `clinical-chat` is authorised and unused, and stays out of clinical workspaces (`../design/DESIGN_SYSTEM.md` §6.11) |
| Copying a draft into a message | It is one keystroke | Copy is opt-in and named, success is claimed only on success, and the exposure is accepted in the open (`../security/THREAT_MODEL.md` §3) |

---

## 4. Automation bias, as six obligations

`../product/RADIOLOGY_WORKFLOW.md` §4 states the requirement for the built product. Applied to the
family, it becomes six things every application must do, because a rule that lives in one
department's workflow document will not survive thirteen new screens.

1. **Evidence beside conclusion.** The words the draft came from are on screen, not one click away.
2. **The machine's confidence is computed, and shown as a band.** A number that looks like
   probability is a claim about the world the model never earned
   (`quality.py`'s `self_reported_confidence` refuses the model grading itself).
3. **A refusal names its rule and the text it objects to,** and a check that cannot name the words
   is advisory or is not shipped (`../design/DESIGN_SYSTEM.md` §6.3).
4. **Correcting the machine lowers the objection.** A finding in a section the human rewrote falls
   to advisory — the human, not the dictation, is now the source
   (`../ARCHITECTURE.md:280-283`).
5. **The manual path never depends on the AI.** No screen becomes unusable because a model did not
   answer; the only visible difference is one honest line.
6. **Refusals are measured, not assumed correct.** A blocking check that fires often on correct
   documents is a defect at the severity, not at the check
   (`../product/ROADMAP.md` §4b: table 4's "sole reason a correct draft cannot be signed").
   Unmeasured severity is how a product teaches a clinician that red means noise.

---

## 5. What the product may claim about a document

The distinction is between **attesting** and **verifying**, and it is the sentence most likely to be
overclaimed in a demo.

| Claim | Allowed today? | Because |
| --- | --- | --- |
| "This document was drafted by a model, and a named human signed it." | **Yes**, where the system of record refuses a machine signer (`../integration/INTEGRATION_CARE_ERP_PACS.md:252`) | The refusal is code in the ERP, not a promise here |
| "The platform verified that this named human approved it." | **No.** Beta gate G2/ADR-0005 | An application-held signature is an attestation. Saying otherwise would be SPEC-09-03's exact violation (`../SPECIFICATION.md:507-516`) |
| "Every sentence in this report can be traced to a model, a prompt version and a request." | **Yes** for the copilot's own draft; **partly** — provenance travels on the document, and it is retained only as long as the document is | `docs/product/README.md:107-126` records the audit gap |
| "Nothing in this report was written without the reviewer seeing it." | **No**, for anything that reached the clipboard or a printer | `../security/THREAT_MODEL.md` §3, and the missing watermark |
| "This check set would have caught that." | **No** — measured against authored golden cases, none of them ratified, and against a stub rather than a model | `../product/ROADMAP.md` §4.1: 3 of 306 hallucination probes |
| "The AI did not see the images." | **Yes**, and it should be said on screen | `../ARCHITECTURE.md:280-283` puts the scope inside the document rather than in a README |

The UI consequence is `../design/DESIGN_SYSTEM.md` §7's rule: **review and approval are one pattern
in every department**, and until ADR-0005 the pattern's output is an attestation that the interface
labels as such. A substitute must be named in the product, never implied by it.

---

## 6. The five gates before an application touches a patient

Every application in `../product/CLINICAL_SUITE.md` §10 passes these, in order. Each gate produces
an artefact, because a gate with no artefact is a conversation.

| Gate | Requirement | Artefact it must produce | The radiology precedent |
| --- | --- | --- | --- |
| **G1 Evidence** | Ratified cases for *that department*, with the signed report as the expected answer | A case file the clinical owner has marked ratified, and its pass rate | `GOLDEN_DATASET.yaml` — and its warning: **all 100 cases are imaging**, so thirteen applications start at zero |
| **G2 Measured checks** | Every check run over correct drafts first; each severity chosen from the measured false-positive rate and the sole-reason count | A table-4 run for that department | `scripts/validation/audit-checks.py` — and its result: four ordinary sentences refused wrongly, fixed before any new check was added |
| **G3 Boundaries in code** | §5's claims and `HOSPITAL_WORKFLOW.md` §5's never-list implemented, not documented — a refusal path, a test, and a check that the test fails when the path is removed | A test file that names the boundary and the control that proves it is not vacuous | `apps/radiology_copilot/tests/test_screen.py` (19 tests, each absence-check carrying a positive control) |
| **G4 Failure driven live** | The application run through every way the AI can fail, by hand, before a clinician meets it | A list of the failure modes actually exercised, and what each produced | `../product/ROADMAP.md` §4b: six failure modes, four defects found only by driving it |
| **G5 A named risk owner** | The clinical owner confirms the skill's `clinical_risk`, its approval requirement and its timeout ceiling | A signed line in `SKILL_LIBRARY.yaml` — the file whose own header says every risk value there is still an engineer's guess (`../DOMAIN_MODEL.md` Q6) | Not done. **This gate is the one the whole family is waiting on** |

An application that reaches a patient with any gate unmet is a pilot, and a pilot is not a product.
The distinction matters because a pilot's failure is absorbed by the person who volunteered it, and
a product's failure is absorbed by whoever came after.

---

## 7. Incidents

No new taxonomy. The classes are the workflow catalogue's — F1 to F30 in
`../product/RADIOLOGY_WORKFLOW.md` §3 — and a department adds to that list only when it has a real
incident to add, for the reason the catalogue exists: an invented failure class is a category nobody
will file under.

| Review rule | Why |
| --- | --- |
| Review the **document and the act**, not the model's score | "DO NOT SCORE THE MODEL — measure the radiologist" is the standing instruction, and a score pretending to know what a reviewer thought is the instrument grading itself |
| Count the refusal as well as the miss | A check that blocked a correct report is an incident with a victim: the clinician's trust |
| Ask who was interrupted | Most clinical errors are the moment the screen was left, not the sentence that was drafted |
| Keep the correction, not only the error | The substantive-amendment rate is the metric the product must earn (`../product/RADIOLOGY_WORKFLOW.md:381`); it needs a classification rule that does not exist yet |
| Publish the count back to the department | A quality reading nobody outside can see is a compliance log, and a compliance log gets ignored |

---

## 8. What a hospital must be able to prove afterwards

Six questions, in the order a lawyer asks them, with today's honest answer.

| Question | Can FutureKind answer it today? |
| --- | --- |
| Which model, alias, prompt version and request produced this sentence? | **Yes**, on the document — the copilot attaches it (`../ARCHITECTURE.md:256`) |
| Under which policy, and with what risk classification? | **Yes**, in the response envelope and the audit line, for as long as the log lives |
| What was proposed before the human changed it? | **Yes** in the copilot's own review record; **not in a searchable store** — retention is ADR-0003 and the platform emits without storing (`../ARCHITECTURE.md:307`) |
| Who reviewed, and when? | **Partly.** The name is typed, not authenticated: Beta gate G1. A clinician who signs with someone else's credential produces a document that proves nothing (`../product/RADIOLOGY_WORKFLOW.md` F13) |
| Who else saw it, or took it out of the building? | **No.** Clipboard and print are untracked, and the printout has no watermark (`../security/THREAT_MODEL.md` §3) |
| Can any of the above be produced two years from now? | **No.** That is the single most serious line in `../DOMAIN_MODEL.md` Q3 for a medicolegal system |

**The safety consequence is a deployment instruction, not a feature request:** until retention
exists, an installation that relies on FutureKind for defensibility is relying on a browser tab. A
hospital adopting this today must keep its own record — which it does, in the ERP — and must not be
sold the platform's audit as the thing that wins a case.

---

## 9. Contraindications — where this family does not deploy

| Do not | Because |
| --- | --- |
| Intraoperative frozen-section decision support | Latency is unmeasured (`../product/PRODUCT_SPECIFICATION.md:243`) and the act is time-critical; a slow answer here is a different clinical act |
| Anything that requires reading pixels | No `vision` capability exists, and the product principle is drafting from dictation, not from images (`../product/SKILL_LIBRARY.yaml:14-16`). The hospital's own vision pipelines stay outside, ungoverned, until the platform has a job model |
| Weight-based or paediatric dose arithmetic | Arithmetic refusal exists to *not answer*; a draft that cannot add reliably should say so, and a clinician should not be shown a near-miss |
| Autonomous notification or recall | A notification is a timed clinical act needing a named human and retention — both unbuilt (`../DOMAIN_MODEL.md`, Notification) |
| Cross-site analytics, federated learning, vendor dashboards | Forbidden by P14 until a constitutional amendment (`../CONSTITUTION.md:344-348`) |
| A second copy of any clinical record | Two owners of one workflow diverge, and the patient pays (P12, `../CONSTITUTION.md:306`) |
| Presenting recalled text as a guideline | No citation capability; label it `citation_available: false` or do not say it (`../product/SKILL_EXAMPLES.md:488`) |
| Coding output as the reason a claim was made | `../product/PRODUCT_BIBLE.md` §6.4 |

---

## 10. Safety register

| # | Item | Severity | Who closes it |
| --- | --- | --- | --- |
| S1 | No skill's risk level has been confirmed by a clinician, and every `critical` skill is unauthorisable today | High | Clinical owner (Q6) + ADR-0005 |
| S2 | Nothing measured against a real model or a real radiologist | High | The afternoon in `../product/ROADMAP.md` §4.2 |
| S3 | Golden cases exist for one department only, and are unratified in all 100 | High | Clinical owner, per department |
| S4 | Audit emitted, not retained | High | ADR-0003 |
| S5 | Signer is attested, not authenticated | High | Beta gate G1, hospital-side |
| S6 | Printout carries no watermark; clipboard leaves untracked | Medium | One attribute in the renderer, and a decision about where copied text may go |
| S7 | No fallback chain declared, so `degraded` can never be true — resilience is a single provider attempt | Medium | `configs/` and the operator's decision, not the Gateway's |
| S8 | The `assumed` rows in `HOSPITAL_WORKFLOW.md` §3 mean eight applications rest on records nobody has walked | Medium | A two-day ERP inventory pass |

**Closing note, because a safety document should end with its own limitation.** Every claim in this
guide is traceable to a rule in configuration, a line in code, or a measurement taken against a
stub. None of it is traceable to a patient. A framework this cautious is worth about one
afternoon of a radiologist using it, and that afternoon is the difference between a safety case and
a safety document.

## 11. The gradient, stated as one law (Genesis Night 4)

§2 is a ladder of *risk*. This is a ladder of *acts*, and it is the part a reviewer can
apply to a new application without asking permission:

> **FutureKind may act as early as it likes on anything that produces a draft, only at the
> last possible moment on anything that produces a decision, and never on anything that
> produces a consequence.**

A **draft** is text inside a field a human owns. A **decision** is a state change in care. A
**consequence** reaches a patient, a schedule, a bill or a legal record.

| Run | The act | Where the platform sits | Evidence in this repository |
| --- | --- | --- | --- |
| 1 | Suggest, never block | The lowest rung, and the only one allowed to run unasked | The USG advisory chips: suggestions a radiologist accepts or rejects, with the ERP's sex-disclosure funnel upstream of display (`core/gateway/models.yaml:104-140`) |
| 2 | Order a queue | Allowed, and only as a re-ordering that hides nothing | Triage in `product/RADIOLOGY_WORKFLOW.md` S3: reorder-only |
| 3 | Draft into a field | The product's centre of mass | Four operations; `design/DESIGN_SYSTEM.md` — draft into a field, never over it |
| 4 | Answer a question asked | On-request elaboration only | S5: comparison and explanation appear *on explicit request* |
| 5 | Refuse arithmetic | A deliberate silence with a cost (§11.1) | Measurements are transcribed by the human; `quality.py` blocks an invented number instead of computing one |
| — | **Complete** a clinical act | **Forbidden** | No code path signs. `copilot.py` has no sign operation that a model can reach; S6 is "none, by construction" |
| — | **Notify** anyone | **Forbidden** | S10: flags never raise the notification |
| — | **Judge** another AI's output | **Forbidden** | S11: peer review of AI-assisted work by another AI is not peer review |

The three forbidden rungs are not missing features. They are the difference between this
platform and an automation with a review screen attached, and each is registered with the
pressure that will ask for it in [`INVARIANTS.md`](../INVARIANTS.md) §1.

### 11.1 Where FutureKind intentionally does nothing, and what that costs

An uncosted silence reads as an oversight and gets "fixed" by the next helpful engineer.
So every intentional inaction carries its price, stated as the thing the clinician must do
by hand.

| The silence | Why | What it costs the clinician |
| --- | --- | --- |
| No AI during acquisition | A protocol change is a human decision at the scanner, and an overlay there trains people to accept machine advice under time pressure | They select the protocol, as they do today |
| No measurement computed or corrected by the model | A number the machine derived is a number nobody checked; the one place the product does less work than it could | They read the calipers and type the value |
| No self-reported confidence | A model's certainty is a stylistic claim by the thing being graded | They see flags and evidence, not a score, and decide |
| No notification raised | An alert is a clinical act with an owner and a time | They confirm the flag before anyone is paged |
| No checklist pre-ticking | The four taps are the checklist's entire evidentiary value | They tick, every time, on purpose |
| No unprompted patient-facing explanation | Explaining a diagnosis to a patient is a consultation, not a render | They choose when a plain-language version exists, and they write the indication |
| No AI review of AI output | Two machines agreeing is not two machines reviewing | A second human reads the difficult cases |

*FutureKind · Genesis Night 3 · 2026-10-09. §11 added Genesis Night 4 · 2026-10-09.*
