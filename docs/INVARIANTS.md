# FutureKind Invariants

**Two registers: what we will not build, and what must not be lost.**
Genesis Night 4, 2026-10-09.

| | |
| --- | --- |
| **Owns** | The refusal register (`N`) and the protection register (`M`), each with the pressure that will erode it. |
| **Does not own** | The principles behind them ([`CONSTITUTION.md`](CONSTITUTION.md)), the clinical never-rows ([`clinical/HOSPITAL_WORKFLOW.md`](clinical/HOSPITAL_WORKFLOW.md) §5), the gates ([`safety/CLINICAL_SAFETY.md`](safety/CLINICAL_SAFETY.md) §6). |
| **Difference** | The workflow's never-list is about *steps in care*. This file is about *things a competing product will ask us to build*. A refusal with no named pressure behind it is a sentence; with the pressure named, it is a design. |
| **Rule** | A new `N` row requires an ADR. A refusal is a decision, and an undocumented decision erodes at the first deadline. |

---

## 1. Things we will never build

| # | Never | The pressure that will ask for it | What is offered instead | Anchored in |
| --- | --- | --- | --- | --- |
| **N1** | A model, provider or endpoint selector in any application-facing request. | "Just for benchmarking." "Just for incident forensics." "The radiologist wants to choose." Every one is reasonable and every one makes a model id part of a public API. | An operator-authenticated inventory surface (`GET /models`), which already exists and already keeps the choice out of the clinical path. | `ADR-0002` rule 1, P8 |
| **N2** | A second place that accepts a completion request. | The pragmatic one: an app that "just calls Ollama for a thumbnail". It is always one small exception, and it is always how the audit trail gets a hole. | A skill and a credential. `SPEC-12-04` makes a new application cost nothing but those. | P16; constitution tripwire 2 |
| **N3** | Any agent that *completes* a clinical act — signing, booking, ordering, billing, discharge. | The demo that sells: an end-to-end workflow with no human pause. Buyers will ask for it in 2029 and the ask will sound like progress. | Drafts plus a named human transition. `P11` is untradeable, so the answer is a shorter workflow, not an autonomous one. | P11, P2 |
| **N4** | A general chat box inside a clinical workspace. | It is cheap, users like it, and it appears in every prototype. It also has no owner, no version and no signature — so whatever it produced cannot enter a record. | Skill-shaped surfaces with a document at the end. | `design/DESIGN_SYSTEM.md` |
| **N5** | AI peer review of AI output, presented as review. | Scale arguments. "A second model catches what the first missed." It catches *some* things and it is not peer review, because no one is accountable for either. | A human reviewer who sees the provenance, and a check list whose cost is measured. | `product/RADIOLOGY_WORKFLOW.md` S11 |
| **N6** | Any safety number taken from the model about itself. | It is free, it looks rigorous, and every vendor does it. A confidence value is a stylistic claim by the thing being graded. | Attestation of what the system *did*, and verification only by a human or a deterministic check. | P13, `CLINICAL_SAFETY.md` §5 |
| **N7** | Pre-ticked safety checklist items. | The usability argument: save the surgeon four taps. The four taps are the entire evidentiary value of the checklist. | Pre-*filled* fields a human must affirm, never an affirmative state. | `product/CLINICAL_SUITE.md` (Theatre) |
| **N8** | A notification raised by a model. | Critical-value safety feels like the obvious win, and it is the fastest way to teach a department to ignore the alert channel. | Flags that a human confirms, and a notification the human sends. | `RADIOLOGY_WORKFLOW.md` S10 |
| **N9** | Hospital-wide semantic search over the record. | Everyone asks for "ChatGPT over our EHR" in the first meeting. It is a consent, minimisation and audit problem wearing a search box. | Per-application retrieval with an explicit, cited corpus — which is a `Knowledge` object the platform has not built and does not advertise. | `PRODUCT_BIBLE.md` (Knowledge Assistant refusal) |
| **N10** | Any cross-hospital data path, including federated training. | The research motion asks politely, then repeatedly, and the academic pitch is "just gradients". | Nothing without a constitutional amendment. Today there is not even a `Hospital` identifier to scope it by. | P14; §7 row 8 |
| **N11** | A pixel-level diagnostic claim. | Pathology and radiology buyers both test images first, and the capability set has no `vision` class at all. | Drafting from what the reporting clinician dictated, stated as the product principle rather than a limitation. | `SKILL_LIBRARY.yaml` finding; ADR-0002 open items |
| **N12** | A patient-facing diagnostic conversation. | "Patients will ask anyway" is true and is not a specification. | A plain-language explanation of a report a clinician signed, on explicit patient request, watermarked. | `RADIOLOGY_WORKFLOW.md` S9 |
| **N13** | Bring-your-own-key, or a model marketplace inside an application. | It looks like flexibility and is actually the removal of governance — plus the fastest route to leaking the LiteLLM master key into a client. | A credential per application and an alias per capability. | `ADR-0002`, `SPEC-12-04` |
| **N14** | Any automatic optimisation of a clinical parameter — prompt, threshold, routing, severity. | "We'll let the data decide" is seductive after a good measurement sprint, and it turns a metric into a target. | Measure, publish, and let a named human change it. The dashboard's stated authority ceiling is the template: it cannot nudge a draft, a prompt or a policy. | Night-2 rule, `PHILOSOPHY.md` §3.3 |
| **N15** | A second prompt for one job. | A per-profile prompt is the natural way to add a variant, and forks the safety text silently. | Version the one prompt: patch for wording, minor for a clause, major plus an ADR for a relaxed prohibition. | `PROMPT_LIBRARY.md` version rules |
| **N16** | Per-clinician scoreboards. | Management will ask, the data is already in the dashboard, and the metric looks like quality. It measures who trusts the tool least — or most. | Feedback to the individual about their own edits; aggregate to the department. | `FAILURE-MODES.md` FM10 |

**The pattern in the pressure column.** Not one of these would be asked for maliciously.
Each arrives attached to a real user need, a real demo and a real deadline. That is why they
are a register and not a paragraph: a refusal needs to be written down *with the argument
that will be used against it*, or it loses.

---

## 2. Things we must protect

| # | What | Why it is fragile | The mechanism that protects it | First sign it is being lost |
| --- | --- | --- | --- | --- |
| **M1** | **One word per thing.** `DOMAIN_MODEL.md` and its status marks. | Vocabulary rot is invisible in review; every new doc adds a plausible synonym. | The terminology map plus the rename rulings R1–R11. | A new document uses a banned synonym to describe a shipped field (see `CONCEPTUAL_DEBT.md` D10). |
| **M2** | **One AI boundary.** | The exception is always small and always justified. | Guard tests; the constitution's second tripwire; `SPEC-12-06`. | Any component other than the Gateway accepting a completion request. |
| **M3** | **The alias contract and its boot-time check.** | It is one function that nobody notices until it is deleted for convenience. | `litellm_config.py` verification; `SPEC-07-03`. | A routing path that works when the check is skipped in a test. |
| **M4** | **Measurement before claim.** | Producing the number is slow; asserting it is fast, and asserting wins under deadline. | `scripts/validation/`, paired detection, severity-by-cost. | A safety sentence in a document with no instrument named beside it. |
| **M5** | **Statelessness — the EHR is the record.** | It reads as a missing feature, and the fastest way to "fix" it is to add a database, which silently transfers liability. | Four operations; the document travels through the caller; retention is a gated decision, `ADR-0003`. | A copilot that stores a patient artefact before retention exists. |
| **M6** | **The prompt's version rules.** | A one-word edit to a safety clause looks trivial and is a clinical change. | `PROMPT_VERSION`, the length ceiling, the duplicate-rule test. | A version bump in one file and not the other — the fork its own test comment names. |
| **M7** | **The golden-case *format*.** | The corpus is unratified and tempting to discard; the format is the expensive part and outlives every case. | `GOLDEN_DATASET.yaml` conventions, six-step scoring, `must_not_say`. | Cases edited to make a check pass. |
| **M8** | **The refusal list, with its costs.** | An uncosted refusal reads as an oversight and gets "fixed" by someone helpful. | This file; `HOSPITAL_WORKFLOW.md` §5; `CLINICAL_SAFETY.md` §9. | A refusal removed or softened with no ADR and no named incident. |
| **M9** | **The audit *line* format, even with no storage.** | Without retention the log looks worthless, so it is tempting to stop emitting or to log prompt text to make it useful. | `skill_audit` lines; the rule that prompt and completion text never enter a log. | A field added to an audit line that contains clinical text. |
| **M10** | **A safety property readable by a person who is not paid.** | The commercial pressure to make the check list, thresholds or prompt proprietary is exactly the pressure that turns open source into a shell. | Apache-2.0; `PHILOSOPHY.md` §3.4; the free/paid split in `business/COMMERCIAL_ROADMAP.md`. | A paid tier that changes a threshold rather than adding a service. |
| **M11** | **History hygiene, on a public repository.** | The tip is clean; the history is not, and a rotation that never happens means the leak is live. | The redaction pass, `.env.example` defaults, and an operator rotation that is still outstanding. | A new secret-bearing object in the tree, or a "temporary" key used in a demo. |
| **M12** | **The reasoning, not only the decision.** | One person holds the arguments; when they leave, the rules become arbitrary and the first arbitrary rule gets deleted. | This document set: `CONSTITUTION.md` for rules, `PHILOSOPHY.md` for reasons, ADRs for decisions. | A rule enforced with no ADR beneath it — the constitution's third tripwire. |
| **M13** | **Deletion as a valid contribution.** | Incentives reward features. A PR that removes 400 lines and passes the gate reads like nothing happened. | `ROADMAP.md` §10, the placeholder-layer deletion, this file's sibling register. | Two consecutive releases that add nothing and remove nothing. |

---

## 3. Where these registers end and the constitution begins

`CONSTITUTION.md` §6 already carries a "what must not grow, ever" list: a second AI
boundary, model or provider selection in a request, a silent substitution of a lesser
model, any cross-hospital data path without amendment, and a clinical final state with no
human transition. Those five are *rules*. This file's N-register is the same territory plus
the eleven refusals that have not yet become constitutional questions because nobody has
asked for them loudly enough — which is exactly when a register is cheapest to write.

Where an `N` row and a principle disagree, the principle wins. Where a *new* refusal is
needed, the path is an ADR first and a row second, so the register cannot quietly become a
list of preferences.

---

**FutureKind Principle**

> The features are replaceable and will be. What defines the product is the list of things
> it said no to, the reasons it gave, and the record it can still produce years later.
