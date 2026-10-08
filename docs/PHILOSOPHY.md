# FutureKind Philosophy

**Why the rules are the rules.** Genesis Night 4, 2026-10-09.

| | |
| --- | --- |
| **This file owns** | The reasons. Which assumptions are load-bearing, which are accidents of the current stack, and what FutureKind would still believe with no code at all. |
| **This file does not own** | The rules. [`CONSTITUTION.md`](CONSTITUTION.md) owns those, and binds this document. |
| **Precedence** | Where this file and the constitution disagree, **the constitution is right and this file is the defect.** An explanation may not soften a rule it is explaining. |
| **Read next** | [`BLUEPRINT.md`](BLUEPRINT.md) for the synthesis, [`FIRST-WEEK.md`](FIRST-WEEK.md) for the onboarding path. |

The constitution states nineteen principles. A principle with no stated reason survives
one inconvenient quarter. This file supplies the reasons so the principles survive ten
years — and marks which reasons are durable, so that when one turns out to be wrong, the
amendment has something specific to contradict.

---

## 1. The disappearance test

Ask: *if every line of code in this repository disappeared tonight, what would still be
true about FutureKind, and what would have to be rediscovered?*

Five things survive, and they are the actual assets:

1. **A vocabulary.** `DOMAIN_MODEL.md` names what a Study, an Observation, an Impression
   and a Skill are, with evidence for each name. Two engineers who share it build one
   system; two who don't build two that must later be reconciled at the cost of both.
2. **A refusal list.** The things FutureKind will not do — no model selection from a
   caller, no machine as last decider, no AI speech into a consent conversation — are
   design work. They are harder to produce than features, because they require knowing
   the clinical situation behind each one.
3. **An evaluation method, and a corpus.** The shape of a golden case (`GOLDEN_DATASET.yaml`:
   the study, the dictation, the six-step scoring, the `must_not_say` assertions) is a
   reusable instrument. Its 100 cases are worth less than its format, because they are
   `ratified: pending` — all 100, measured from the file — and an unratified case proves
   nothing about care. The *format* is what a hospital cannot easily reinvent.
4. **An argument about accountability.** Who signs, who may see, what must be retained,
   and why a shared credential is not an identity. That argument is the reason the
   Gateway is shaped the way it is.
5. **A record of what was tried and rejected.** The register in `CONSTITUTION.md` §7, the
   reversals in git history, the tenth quality check that was measured and dropped.

What would have to be rediscovered: every `.py` file, the catalogue, compose, the screen,
the prompt text. Not one of those five survivors is code.

**The conclusion this file draws:** FutureKind's durable value is linguistic, clinical and
evidential — not programmatic. So the platform should be organised as if code were
consumable and language were not. `CB5` ("model capability decays fast; clinical language
does not") is the same claim stated as a rule; this is it stated as an asset list, and the
asset list is what a ten-year plan should protect.

---

## 2. Fundamental against accidental

Every assumption in this repository gets one test:

> **Would removing this change who is responsible, or only how something is done?**
> Responsibility → fundamental. Mechanism → accidental.

That is the whole test, and it is deliberately not "is it old", "is it hard" or "is it in
an ADR".

### Fundamental — removal changes a responsibility

| Assumption | Why it survives a rewrite |
| --- | --- |
| A named human accepts the consequence of every clinical act the platform touches. | Not a safety preference. Accountability in medicine is legally and clinically indivisible, so any system that inserts a machine into the accountability chain breaks the model rather than bending it. `P11`, `CONTRIBUTING.md`'s "never replaces clinical judgment". |
| The document, not the conversation, is the unit of clinical work. | A hospital's binding artefacts are versioned documents that outlive their author and are read by people who never met them. This is why a chat box is wrong in a clinical workspace — not because chat is unfriendly, but because a chat turn has no owner, no version and no signature. |
| Context is the scarce clinical resource. | Models are becoming abundant; a clinician's attention is not, and is the only hospital resource an AI product spends. Every feature buys its seconds back from someone's focus. The product's real currency is attention, so its real measure is what it *did not* ask a person to look at. |
| Sovereignty is a property of auditability, not of ideology. | "Local-first" (`ADR-0001`) is not a privacy mood. A hospital cannot audit a decision made by a system it does not run, and an unauditable clinical decision cannot be defended. Local execution is the mechanism; **being able to answer for what happened** is the requirement. |
| A rule a caller can relax is not a rule. | `CB7`. Enforceability must live in the component the risky actor does not control. Every instance of the opposite — a per-request model picker, a caller-supplied severity, a fallback the app may decline — failed somewhere else first. |
| Terminology is an interface. | Decisions are stored in language. A repository with two words for one thing contains two decisions about it, and nobody remembers which one is live. Naming errors are not cosmetic; they compound at the rate of new contributors. |
| Safety claims carry their measurement, or they carry nothing. | The unpaired hallucination figure "claimed 87% and meant nothing" (`audit-checks.py:22-25`). A number without a named instrument is marketing, and marketing inside a clinical repository is a safety defect. |

### Accidental — removal changes only the mechanism

FastAPI, Pydantic, uvicorn, httpx, Python itself. The four copilot endpoints and their
names. Ports 8100/8200. `compose.yaml`. The `fk-*` alias namespace. Three capability
classes called `default`/`fast`/`reasoning` — a fact about three models on one GPU, not a
fact about medicine; the fundamental need is *a named degradation class the policy can
bind to*. `models.yaml` as a file — fundamental need: policy is data, not code. The
OpenAI-compatible surface — an accident of ecosystem gravity; the fundamental part is that
applications must not need our SDK. The shared API key — accidental *and already
known-bad* (`ADR-0004` does not exist). The six radiology section keys — accidental per
specialty; the ordering-with-one-authority is not. LiteLLM itself — the routing need is
fundamental, this product is not.

### Why the split is worth making

Three of the repository's open wounds are accidents defended as if they were principles:

- `core/gateway/models.yaml` still carries `model:` (`:142-166`), and its own comment says
  step 3 of `ADR-0002` deletes it (`:33-34`). A model id is a mechanism.
- Six documents restate test counts. `ARCHITECTURE.md:304-305` says 492 and 255;
  `SPECIFICATION.md:929` still says 482; `product/README.md:46` says 775. A test count is a
  mechanism's shadow, and it moves without asking.
- The Gateway walks fallback chains (`routing.py:175-215`, `service.py:176`) that no data
  populates: no `fallbacks:` key exists in any YAML in this repository (measured). Chain
  length is one, `degraded` is always false, and `OUTCOME_FALLBACK` (`service.py:58`) is
  unreachable in shipped configuration. The *retry* is LiteLLM's mechanism; the
  *degradation policy* is the Gateway's rule. The code currently implements the first and
  cannot exercise the second.

**Rule this file proposes, for the owner to ratify as an amendment:** *a fundamental
assumption may be enforced in code; an accidental one may only be encoded where it is
cheapest to replace.* A corollary with teeth: when a reviewer says "the architecture
forbids this", the answer must name which row of the table above the objection sits in.

---

## 3. Five philosophies

### 3.1 Clinical

**Claim:** the product's job is to make a document more correct in less of a clinician's
time, and to leave the clinician's judgement untouched. Not to write more text.

- Drafting is help; deciding is not. The line is not "AI suggests, human confirms" —
  confirmation fatigue makes that hollow. The line is *which act the machine is
  participating in*: reordering a queue is help, pre-ticking a surgical checklist destroys
  the only value the checklist has, and measuring a structure is work the human chose to
  do.
- **A refusal is a clinical feature.** `CLINICAL_SAFETY.md` and
  `HOSPITAL_WORKFLOW.md` spend more words refusing than promising, and that is the correct
  ratio for a tool that enters a legal record.
- The clinician must stay the author. The screen drafts *into a field, never over it*
  (`design/DESIGN_SYSTEM.md`), and confidence is never taken from the model
  (`P13`, `product/PROMPT_LIBRARY.md`), because a number a model gives about itself is
  not evidence.
- **What would falsify this:** measured evidence that review-with-AI is *slower and worse*
  than writing. Today neither is measured — no model has run here and no radiologist has
  been timed, which `ROADMAP.md` §10 states plainly.

### 3.2 Engineering

**Claim:** the system must be small enough for a hospital to audit, and every rule must
be a mechanism rather than a sentence.

- Explicit over clever. `CONTRIBUTING.md`: "Prefer explicit behaviour over hidden magic."
- Deletion is a contribution. Two files for one thing, a key nothing reads, a branch no
  config populates — each is a place where the truth can be wrong.
- **Code is cheap to write and expensive to keep.** The expensive form of debt here is not
  ugly code, it is duplicated *ideas*; see [`CONCEPTUAL_DEBT.md`](CONCEPTUAL_DEBT.md).
- Every claim needs an instrument with its name in the file. `scripts/validation/` exists
  before the feature does.
- What would falsify this: a component whose audit by an outside hospital engineer takes
  longer than a day. The Gateway is currently auditable in an afternoon; keep it that way.

### 3.3 Safety

**Claim:** safety here means *not being trusted too much*, which is a different problem
from *not being tricked*, and the industry has mostly been solving the second.

- Automation bias is the primary hazard, not adversarial input. A prompt injection needs a
  malicious author; a rubber-stamped draft needs only a busy radiologist at 19:40.
- A check's severity is set by its measured cost, not by how frightening its name is.
  `dropped_observation` blocked 87 of 100 correct reports because the audit corpus had a
  particular shape, not because the product misbehaved — and the fix was a reclassification
  with numbers, not a rewording.
- **Silence is a design act, and it must carry a cost column.** Where the platform
  deliberately does nothing — no AI during acquisition, no notification raised by a model,
  no measurement taken on the machine's say-so — that inaction is stated with what it costs
  the user, or it reads later as an oversight and gets "fixed".
- What would falsify this: one incident where a block refused a correct report and the
  department routed around the tool permanently. That failure mode is cheaper to prevent
  than to recover, and it is measured today (1 of 100 faithful reports still refused,
  residual `E-03`).

### 3.4 Open source

**Claim:** the code is not the moat, so giving it away costs little and buys the only
thing that cannot be bought — outside scrutiny of a clinical system.

- Apache-2.0, and the obligations that come with it: a stranger must be able to build,
  test, and disagree.
- **What must stay readable by a person who is not paid:** the prompt, the check list and
  the thresholds, the audit record's format, the vocabulary. A safety property whose
  definition is a trade secret is not a safety property — it is a promise.
- The uncomfortable half: a licence cannot protect a hospital from a bad fork, and this
  repository currently has no external contributors while it does have community
  documents. Open source is a maintenance claim, and claims must be paid in maintenance.
- What would falsify this: users who want a hosted service more than they want the source.
  That is a real market outcome and it is not a betrayal — it is the reason the platform
  boundary must stay honest either way.

### 3.5 Commercial

**Claim:** sell assurance, not access to intelligence.

- What is abundant: models, drafting, and eventually every competitor's first draft.
  What is scarce: a defensible record of what was asked, what answered, what was produced,
  who edited it and who signed it — plus someone who can re-run the evaluation and be
  believed.
- So the paid layer is *retention, evaluation at scale, deployment certification, and
  support that answers in a hospital's language*. The free layer is everything a clinician
  must read to be safe.
- The limit of the position, stated rather than hidden: hospitals often buy liability
  transfer, and FutureKind refuses to carry clinical liability. That is a genuine
  competitive weakness, not a misunderstanding of the market. See
  [`business/COMMERCIAL_ROADMAP.md`](business/COMMERCIAL_ROADMAP.md).
- What would falsify this: nobody pays for assurance while paying for convenience. Then
  the strategy is wrong, the philosophy is not.

---

## 4. The non-negotiables, stated so they can be broken

`CONSTITUTION.md` §2 says P2, P4, P11 and P13 may never be traded for convenience,
latency, cost or release date. Restated as falsifiable claims — because a rule that cannot
be contradicted cannot be checked:

| Never traded | The claim | What would force an amendment |
| --- | --- | --- |
| **P2** human final decision | No code path may produce a clinical final state without a human transition behind it. | Nothing. If this is wrong, the product is wrong. An amendment would have to argue that a hospital prefers an unaccountable artefact. |
| **P4** privacy / local-first | Patient data and the prompt travel only as far as the hospital's own boundary. | A regulator requiring a national processing register the hospital cannot host. That changes the deployment, not the duty. |
| **P11** auditability | What happened can be reconstructed for as long as the record is legally required. | Nothing — only a failure to fund it. Retention is a cost line, which is exactly how it gets lost. |
| **P13** no silent substitution | The model that answered is the class that was promised, or the request visibly fails. | A clinical requirement that only a different model can meet. Then the answer is a *new skill*, not a hidden swap. |

These four are not values in the decorative sense. Each is a promise someone outside the
project will rely on: a patient, a coroner, an inspector, a clinician defending a decision
in 2040. The reason they are untradeable is that the promisor cannot renegotiate them on
our schedule.

---

## 5. Four assumptions this philosophy is load-bearing on

Self-critique, in the brief's own terms — argue against everything above.

1. **That hospitals want this boundary.** Local-first, auditable, human-signs is a
   procurement position that wins in some markets and loses in most. If the market decides
   it wants a vendor who is also the decider, the platform survives only in
   sovereignty-sensitive buyers. *Check:* does the first non-owner hospital install it
   without the author present?
2. **That the document stays the unit of work.** Imaging reports are structured and
   versioned today. If record-keeping shifts to continuous agent-written notes, "a document
   with one owner and a signature" may be the wrong object. *Check:* is the golden case
   shape still intelligible to a clinician in 2032?
3. **That attention is the scarce resource.** If review is the bottleneck and drafting is
   not, optimizing time-to-sign is optimizing the wrong number, and the correct target
   becomes triage of what to read. *Check:* the dashboard's own edit-rate numbers, once a
   human has produced them.
4. **That refusal is a feature people will pay to keep.** Refusals are cheap to state and
   expensive to hold when a competitor says yes. *Check:* the first time a customer asks
   for a model picker and the answer stays no while the revenue does not disappear.

If assumption 1 fails, the strategy changes. If 2, 3 or 4 fails, the *products* change and
the philosophy holds, because none of the four fundamental rows in §2 depends on them.
That asymmetry is the point of writing it down.

---

## 6. One paragraph to hand to a stranger

FutureKind is what a hospital needs in order to ask a model something and still know,
afterwards, who asked, what answered, what was drafted, who changed it and who signed it.
Everything else — the Gateway, the catalogue, the checks, the golden cases — exists to keep
that sentence true at three in the evening, in a language the inspector reads, without a
single byte leaving the building.

---

**FutureKind Principle**

> Code is consumable. Language, refusal and evidence are not. Spend the sprint protecting
> the second kind, and the first kind will be cheap to replace.
