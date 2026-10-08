# FutureKind Blueprint

**What FutureKind should become, and what has to be true for that to be said honestly.**
Genesis Night 4, 2026-10-09. A synthesis, not a specification.

| | |
| --- | --- |
| **Owns** | The whole picture: the ten-year answer, every boundary judged, the ecosystem verdict, the competitive position, the reading order of the document set. |
| **Does not own** | Rules ([`CONSTITUTION.md`](CONSTITUTION.md)), names ([`DOMAIN_MODEL.md`](DOMAIN_MODEL.md)), arrangement ([`ARCHITECTURE.md`](ARCHITECTURE.md)), sequence ([`product/ROADMAP.md`](product/ROADMAP.md)), reasons ([`PHILOSOPHY.md`](PHILOSOPHY.md)). |
| **Status** | Derivative and subordinate. Every claim here cites the file that owns it. Where this document adds a claim, it is labelled a *verdict* — the owner's to refuse. |

---

## 0. The eighteen outputs, and why there are not eighteen files

The brief named eighteen documents. `docs/README.md` rule 3, which this repository wrote
and this sprint is bound by, says **a second document for one thing is a defect.** Nine of
the eighteen already have an owner. So they are extended where they belong, and only the
unowned material gets a file. The deviation is recorded here so reversing it is the
owner's call, not a discovery.

| Named output | Where it lives | New or extended |
| --- | --- | --- |
| Blueprint | this file | **New** |
| Philosophy | [`PHILOSOPHY.md`](PHILOSOPHY.md) | **New** |
| Canonical Model | [`DOMAIN_MODEL.md`](DOMAIN_MODEL.md) + §3 of this file | Extended |
| Design Language | [`design/DESIGN_SYSTEM.md`](design/DESIGN_SYSTEM.md) | Extended Night 3 |
| System Map | [`ARCHITECTURE.md`](ARCHITECTURE.md), [`architecture/APPLICATION_MAP.md`](architecture/APPLICATION_MAP.md) | Exists |
| Clinical Model | [`clinical/HOSPITAL_WORKFLOW.md`](clinical/HOSPITAL_WORKFLOW.md), [`DOMAIN_MODEL.md`](DOMAIN_MODEL.md) | Exists |
| Product Ecosystem | §4 below, [`product/PRODUCT_BIBLE.md`](product/PRODUCT_BIBLE.md) | This file + Bible |
| Technical Debt Review | [`CONCEPTUAL_DEBT.md`](CONCEPTUAL_DEBT.md) | **New** |
| Commercial Strategy | [`business/COMMERCIAL_ROADMAP.md`](business/COMMERCIAL_ROADMAP.md) | Extended Night 3 |
| Governance Model | [`GOVERNANCE.md`](GOVERNANCE.md) | **New** |
| Clinical Safety Principles | [`safety/CLINICAL_SAFETY.md`](safety/CLINICAL_SAFETY.md) + §5 | Extended Night 3 |
| Open-Source Strategy | [`GOVERNANCE.md`](GOVERNANCE.md) §4 | **New** |
| 2035 Vision | [`VISION-2035.md`](VISION-2035.md) | Extended Night 3 |
| Founder Notes | §7 below | This file |
| Lessons Learned | §8 below | This file |
| Things We Will Never Build | [`INVARIANTS.md`](INVARIANTS.md) register N | **New** |
| Things We Must Protect | [`INVARIANTS.md`](INVARIANTS.md) register M | **New** |
| The 2032 engineer's first week | [`FIRST-WEEK.md`](FIRST-WEEK.md) | **New** |

Seven new files, each owning something no existing file owns. No document count is stated
here, because a count in prose is the exact defect this sprint registers
([`CONCEPTUAL_DEBT.md`](CONCEPTUAL_DEBT.md) S1).

---

## 1. The answer

**FutureKind should become the layer of a hospital that lets it *prove* what its AI did —
not a better way to generate text.**

Read that as an evolution in four stages, each with the test that says it happened:

| Stage | What FutureKind is | The test it is real | State |
| --- | --- | --- | --- |
| 1 — **Gate** | One boundary a model request cannot avoid: permission, policy, provenance, privacy. | A caller cannot name a model, and the Gateway refuses to boot on an unknown alias. | **Done.** Guarded by tests. |
| 2 — **Instrument** | A product a clinician uses, whose every safety claim carries a measurement. | A radiologist's time-to-sign and edit rate are measured by *her*, not inferred by the tool. | **Built, unmeasured.** No model has run here; no clinician has been timed. |
| 3 — **Suite** | Many small applications on one language and one policy file. | A second specialty ships without touching the platform (SPEC-12-04). | **Designed.** Fourteen applications, one implementation. |
| 4 — **Evidence** | The artefact a hospital produces for a regulator, a coroner and a patient: what was asked, what answered, what was drafted, who changed it, who signed. | Any of the six medicolegal questions in `CLINICAL_SAFETY.md` §8 answered from stored data in under a minute. | **Not started, and this is the whole game.** Audit is emitted, not retained; there is no Hospital object; identity is one shared key. |

**Verdict 1.** Stages 1–3 are the industry's ordinary ambition, and FutureKind is already
near the top of it. Stage 4 is where the platform is *behind its own argument*: it has
written more about accountability than it can currently demonstrate. The ten-year plan is
therefore not a feature plan. It is the migration of one border — the northern one — from
prose into the same class of artefact as the southern.

**Verdict 2.** The word "platform" in `description: Local-first AI Platform for Healthcare`
is aspirational. What exists is one application and a gate. That is not an insult; it is
the correct size for stage 2, and saying so is what keeps stage 4 honest.

---

## 2. Boundaries judged

Five verdicts on every boundary the platform draws. The evidence column is what a
contributor could check on a clone.

### 2.1 Drawn well, and enforced — do not touch

| Boundary | Why it holds |
| --- | --- |
| **Application → Gateway** | One selector: a skill. `SPEC-12-06` makes a new public request field need an ADR, and the guard tests refuse a request that names a model. This is the platform's most valuable constraint and the hardest to keep under pressure from a customer wanting a model picker. |
| **Gateway → LiteLLM** | Two files that must agree, checked at boot (`litellm_config.py`), refusing to start rather than discovering a misroute on a live clinical request. This is what `ADR-0002` Option A bought, and it is the reference pattern for the rest of this table. |
| **Skill → Capability → Alias → Model** | Three namespaces with one travel order, stated at `models.yaml:4-8`, and the resolution code refuses to skip a hop. |
| **Document → section** | Locking follows who owns the words (`report.py:56`), and the clinical indication is not writable by the model or the reviewer. A UI rule that encodes a clinical one. |
| **Copilot → EHR** | Stateless: four operations, the document travels through the caller, and the record stays outside the AI. `HOSPITAL_WORKFLOW.md` §6 answers Q5 the same way. |

### 2.2 Leaking — close with a mechanism

| Boundary | The leak | Fix, in one line |
| --- | --- | --- |
| Gateway → application response | `gateway.py:32-49` re-declares thirteen fields with `extra="ignore"`, so a rename makes a field vanish instead of failing. | `extra="forbid"` on the client, or publish a schema both sides import. |
| Policy vocabulary | `copilot.py:69` hard-codes four policy field names that the Gateway owns. | The response carries the schema version; the app refuses an unknown version. |
| Application → its system of record | Documented for radiology only; pathology's record "is not documented in this repository". | One integration contract per specialty, written before the app is authorised. |
| Never-list → code | Nineteen workflow nodes say what AI may never do; `CLINICAL_SAFETY.md` G3 demands a refusal path plus a test, and only radiology has one. | Every never-row gets a named guard or is marked unenforced. |

### 2.3 Overlapping — merge or mark one as authority

`routing.py`'s chain walking against LiteLLM's retries; `PROMPT_LIBRARY.md` §1 against
`prompt.py`; `SKILL_LIBRARY.yaml`'s 121 designs against `models.yaml`'s 6 authorisations;
`ARCHITECTURE.md`'s aspirational boxes against its own as-built table; `README-ROUTING.md`
against `gateway-routing.md`. All five are registered as D4, D7, D8, D14 and S8 in
[`CONCEPTUAL_DEBT.md`](CONCEPTUAL_DEBT.md), and all five are the same shape: **two
documents of equal voice about one thing, with nothing to decide between them.**

### 2.4 Should disappear

The second routing document. The component advertisement in `configs/futurekind.yaml`.
The `model:` key once step 3 is authorised — its deletion is already scheduled at
`models.yaml:33-34`. The multi-candidate chain walker. The fourth meaning of "tier". The
practice of counting tests in prose. Each with what it breaks is in the debt file's §4,
which is where deletions belong, not here.

### 2.5 Should become stronger

Ranked by what a hospital would actually be unable to answer without them.

1. **Retention.** "Audit emitted, not retained" is `CONSTITUTION.md` §7 row 4, and it is
   the platform's widest gap: not one of the six medicolegal questions is answerable two
   years from now. `ADR-0003` does not exist. **Verdict 3:** nothing above stage 2 should
   be authorised for a second hospital before this closes, because the promise the
   platform makes is an evidentiary one.
2. **Identity.** One shared API key per deployment, so "who asked" has no answer and
   `approval_required` cannot be honoured — declaring it currently yields 403. `ADR-0005`
   does not exist. It is cited 55 times.
3. **Sovereignty's unit.** There is no `Hospital` object, so a cross-hospital data path
   (P14) is unrepresentable rather than forbidden, and multi-site (ADR-0006) has nothing
   to enumerate. A missing noun is a missing rule.
4. **Ratification.** 100 of 100 golden cases are `ratified: pending`, authored by
   engineering. The evaluation instrument is complete and its inputs are not signed. Every
   gate in `CLINICAL_SAFETY.md` §6 leans on this one unfilled column.
5. **The never-list.** See §2.2. Fourteen applications will inherit it as prose unless it
   becomes code while there is only one.

---

## 3. The canonical model, judged from above

`DOMAIN_MODEL.md` is the naming authority and Night 4 found it in the state its own rules
predict: right about the platform, wrong about the present tense. Three verdicts.

**Verdict 4 — the model is complete enough to build on; the problem is enforcement, not
coverage.** Fourteen objects, statuses marked [CODE]/[DOC]/[ABSENT], eleven renames, six
owner questions with four now answered in design. Nothing conceptual is missing for stages
1–3. What is missing is the three objects stage 4 needs: **Hospital**, **Actor** (the named
human, distinct from the credential), and **Record** (what survives, for how long, in whose
custody). Each is blocked on an unwritten ADR rather than on an unwritten schema, which is
why they are absent from the map and not from the model.

**Verdict 5 — ownership of truth needs one more column, and it is the column that would
have prevented most of the debt register.** For each concept: which file defines it, which
may restate it, and what fails when they disagree. Today the answer to the third question
is "nothing fails". The suggestion is not a new table in the domain model but a rule about
restatement — see `PHILOSOPHY.md` §2 and the counter-rules in the debt file's §2.

**Verdict 6 — the vocabulary's failure mode is present-tense measurement.** The naming
authority proved its case by counting words in another document, and those counts went
stale while everyone was busy being correct about something else. A proof that is a
measurement must be re-run or deleted; this one was repaired in `52bf45f` and the class of
error is now named rather than fixed one instance at a time.

---

## 4. The ecosystem verdict: share four things, refuse eight

The brief asked what becomes common as FutureKind grows. The answer is short and
unpopular: **less than the instinct says.**

| Share centrally? | Layer | Why |
| --- | --- | --- |
| **Yes, already** | **Terminology** | `DOMAIN_MODEL.md`. One word per thing is the only asset that appreciates. |
| **Yes, already** | **Policy** | `models.yaml`. Risk, approval, audit and downgrade as data a clinician can read. |
| **Yes, already** | **Review pattern** | One sign-off shape for all fourteen apps (`DESIGN_SYSTEM.md` §7). A second approval UI is a second clinical risk model. |
| **Yes, already** | **Evidence format** | The golden case shape, the audit line shape, the provenance fields. The *format* is shared; the *content* is each department's. |
| Not yet | Identity | One hospital, one key. Build it when the second hospital arrives — but write ADR-0004 now, because the shape constrains the other four. |
| Not yet | Retention store | ADR-0003. This is the exception to the rule below: it is not premature, it is *owed*. |
| Not yet | Analytics | One deployment's numbers. `dashboard.py` is honest that it can nudge nothing. |
| **Refuse** | A shared UI framework | Eleven patterns documented, one exercised. A component library built for one screen is a private thing with extra ceremony. |
| **Refuse** | A model catalogue beyond aliases | `ADR-0002` decided this. Reopening it is a new ADR, not a refactor. |
| **Refuse** | Hospital-wide search | The Knowledge Assistant is a named refusal (`PRODUCT_BIBLE.md`). Search over an EHR is a consent and audit problem wearing a UI. |
| **Refuse** | A notification bus | The workflow says flags never raise the notification. A bus would make it possible, which is the reason not to build it. |
| **Refuse** | A document store | The EHR is the record. Owning the artefact would own the liability, and both. |

> **Verdict 7 — the two-user rule.** *A shared thing is built when its second user
> exists, except for vocabulary, policy, review and evidence format, which are shared by
> definition because they are not services.* Premature service-sharing is the most
> expensive form of the duplication this sprint is supposed to delete: it looks like
> architecture and behaves like a fifth dependency.

---

## 5. The clinical gradient, stated as one law

`CLINICAL_SAFETY.md` holds the ladder and `RADIOLOGY_WORKFLOW.md` holds it per step; Night
4's addition is the sentence that generates both:

> **FutureKind may act as early as it likes on anything that produces a draft, only at the
> last possible moment on anything that produces a decision, and never on anything that
> produces a consequence.**

Draft = text into a field a human owns. Decision = a state change in care. Consequence = a
patient, a schedule, a bill, a legal record. The platform's southern half (drafts) is a
product question; the middle (decisions) is a configuration question with a human named in
it; the northern edge (consequences) is a refusal — and the refusals are the part a
competitor cannot copy without changing what they sell.

Where AI must never speak, and where FutureKind should intentionally do nothing, is the
register in [`INVARIANTS.md`](INVARIANTS.md) §N, which is also where the *cost* of each
silence is written down — because an uncosted refusal reads as an oversight and gets
"fixed".

---

## 6. Competitive position: the category is not the one the name suggests

FutureKind does not compete with Epic. It competes with **the habit of pasting a clinical
question into a consumer chatbot**, and with the vendor who bundles an assistant into the
record and cannot be audited by the buyer.

| Group | Their real move | Learn | Refuse |
| --- | --- | --- | --- |
| **Epic / Cerner / Oracle Health** | Own the workflow and the data; AI arrives inside a record the hospital cannot open. | The discipline of the in-basket; the document as the unit; distribution through the workflow owner. | Being the last decider as a business model. |
| **OpenAI / Anthropic / Google** | Own capability; indifferent to documents; sell raw intelligence. | Evaluation rigour, and that model quality is not our moat — it is our input. | Anything that makes a model id a user-facing choice. |
| **Nabla / Abridge / Ambience / Suki** | Clinical documentation, sold through speed; the safety story is a vendor claim. | Document-first UX; drafting into a structure; the fact that speed is what clinicians buy. | Unverifiable accuracy claims. Their buyers cannot re-run their evaluation; ours can. |
| **Aidoc / Viz.ai** | Opportunistic detection pushed into a radiologist's queue; paid per finding. | Triage-worklist economics; the value of a negative result stated with a rate. | Push. FutureKind's drafting is on-request (`RADIOLOGY_WORKFLOW.md` S5) and its alerts are flagged, never raised. |
| **PathAI / Paige** | Computational pathology on pixels. | Nothing yet — the honest gap is that we have no `vision` capability and thirteen applications that assume dictation. | A pixel claim before the modality exists. |
| **Microsoft / Alibaba** | Platform gravity, bundling, a national-scale data question. | Distribution matters more than elegance, and open source is a distribution story. | Scale as a goal in itself. |

> **Verdict 8 — the moat is the buyer's ability to check.** Apache-2.0 means the code is
> not the moat; the vocabulary, the refusal list, the evaluation format and an auditable
> record are, because they are expensive to produce and impossible to fake in public. Every
> competitor's pitch requires the hospital to trust a claim. FutureKind's can require the
> hospital to test one. That is a real difference and the strategy should be built on it —
> with the equal-and-opposite weakness stated: **we cannot sell liability transfer**, and a
> large part of the market buys exactly that.

---

## 7. Founder notes

Four nights, in the order the lessons actually arrived.

**The platform was built before it was measured, and the order shows.** The Gateway is
genuinely good: one boundary, an alias contract checked at boot, guard tests against its
own API's regression. Then it shipped a clinical product with no clinician in the loop and
an evaluation corpus nobody has signed. Both are reversible; neither is reversible if
people stop checking.

**The most valuable commit of the sprint deleted 36 files.** `agents/` and `genesis/` were
placeholders that made an unbuilt clinical layer look built. Deleting them was a product
decision, not a tidy-up. The same logic now applies to five named-but-unwritten ADRs, and
the fix is the same: an honest register instead of a dangling citation.

**The documentation is ahead of the enforcement by design, and that is a bet, not a
slip.** Night 3 wrote fourteen applications and Night 4 wrote a philosophy. If a second
hospital arrives and the retention and identity gaps are still prose, the documents will
read as marketing — which is the one outcome this repository's own honesty rules cannot
survive.

**What is genuinely rare here, and worth defending against future cleverness:** a suite of
checks whose severity was *reduced* after measurement (`dropped_observation`, blocking 87
of 100 correct reports), a hallucination figure that was re-measured because the first
version "claimed 87% and meant nothing", a tenth check that was designed, measured and
*rejected*, and a validation dashboard that refuses to infer the clinician's verdict from
text because that would be grading its own homework. Any of those could have been left as a
stronger-sounding claim. They were not.

---

## 8. Lessons learned, phrased so they bind

1. **A gate that cannot fail is worse than no gate.** `scripts/validation/test-dashboard.py`
   reported green while executing nothing, and 28 tests were counted in six documents that
   CI never runs. Verification must include the failing case; the file now exits 1 when it
   collects nothing.
2. **Every number in prose is a future lie with a shelf life.** Six sites restated test
   counts; two were already wrong. A fact that moves has one home and everything else
   points at it.
3. **Naming a decision is not making it.** 131 references to five unwritten ADRs, 115
   skills that are decisions about unauthorised work, one config file that advertises six
   components and is read by no process.
4. **A second document for one thing is the defect that causes the others.** Two routing
   READMEs, two prompt authorities, two catalogues, two architecture views in one file.
5. **Refusals are the most valuable artefacts, and they need the most evidence** — a
   refusal without a cost column gets deleted by the next helpful engineer.
6. **Correctness is not the same as being believed.** The platform is right about more than
   it can currently prove; the fix is instruments, not sentences.
7. **The clinical seat was empty for four nights.** Every risk level, threshold and
   unratified case is an engineer's guess standing in for a clinician's decision. Writing
   governance down (`GOVERNANCE.md`) is how the guess stops being a decision.

---

**FutureKind Principle**

> The work is not to make the machine cleverer. It is to make the hospital able to say, in
> writing and under inspection, exactly what the machine did — and to keep that sentence
> true when the machine is replaced, which it will be.
