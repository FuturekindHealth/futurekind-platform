# The FutureKind Constitution

**Status:** Proposed — supreme; accept it or amend it, but do not silently violate it
**Date:** 2026-10-07
**Authority:** This document sits **above every ADR**. An ADR that conflicts with it is
wrong, whatever it decided and whoever accepted it.
**Subordinates:** ADR-0001, ADR-0002, `docs/ARCHITECTURE.md`, `docs/DOMAIN_MODEL.md`,
`docs/architecture/*`, all code.
**Not:** a specification, a design, a roadmap, or a list of preferences. It states what
FutureKind may not become.

---

## 1. Mission

**To put trustworthy AI in the hands of clinicians without taking responsibility away
from them, and without taking the patient's data away from the hospital.**

*Why this wording.* `ARCHITECTURE.md:234-240` states the mission as a slogan —
"Human Wisdom. AI Precision. Open Healthcare." A slogan cannot be violated, and a
mission that cannot be violated cannot guide a decision. This version has three
nouns you can test code against: *trustworthy*, *clinician responsibility*,
*hospital data custody*. When a feature trades one of them for convenience, the
document tells you which one lost.

*What follows from it.* Any component that makes a clinical decision without a named
human, or that moves patient data outside the hospital's control, or that produces an
answer with no traceable basis, is out of mission — not "out of scope".

*ADRs that depend on it.* ADR-0001 (local-first) exists entirely to keep the second
clause true (`ADR-0001:54`). ADR-0002 exists to keep the first clause enforceable by
making the Gateway the single place permission and provenance are decided.

---

## 2. Vision

**Every hospital runs its own FutureKind, and no hospital needs permission from a
vendor to use it.**

*Why.* `ARCHITECTURE.md:8` calls the platform "open, local-first"; ADR-0001 `:11`
targets "hospitals of all sizes, including those with limited connectivity". The
vision is not "cheap self-hosting". It is that clinical AI is not a service a
hospital subscribes to, because a subscribed-to clinical system cannot promise a
patient where their words went.

*What follows from it.* Local-first is not a deployment preference, it is the
default posture — cloud models are an optional extension (ADR-0001 `:19`), and every
extension must be able to fail without taking a clinical workflow down with it. It
also means a hospital's upgrade path may never be gated on someone else's release
schedule.

*ADRs that depend on it.* ADR-0001. Also: this vision is the reason
`ARCHITECTURE.md:12-14`'s "FutureKind is not an application" matters — a platform
that must be forkable by a hospital cannot also be the product's UI.

---

## 3. Core beliefs

The beliefs are the load-bearing layer between mission and principle. They are
assertions about the world that, if false, make the principles unreasonable. State
them so that when one turns out false, the consequence is a debate rather than a
surprise.

**CB1 — A clinical answer is a statement about a person, not a string.**
Therefore provenance, basis and authorship are not metadata; they are part of the
answer.

**CB2 — Responsibility in medicine is indivisible and always names a human.**
An AI cannot be a defendant, a signatory, or the person woken up at 3am.

**CB3 — A system cannot be trusted by a hospital if the hospital cannot read it.**
This is why ADR-0002 chose to keep the Gateway small rather than capable
(`ADR-0002:85`, `:117`).

**CB4 — Data that leaves a hospital's control cannot be protected by policy alone.**
Encryption at rest, DPAs and good intentions all fail at the same place: someone
else's logs.

**CB5 — Model capability decays fast; clinical language does not.**
Whatever is named after a model will be renamed every eighteen months. Whatever is
named after clinical intent survives. This is the single strongest argument for the
Skill/Capability/Alias/Model separation ADR-0002 imposed.

**CB6 — An unrecorded decision will eventually be argued to have never been made.**
Auditability is not observation; observation is for operators, audit is for people who
were not in the room.

**CB7 — A rule a caller can relax is not a rule.**
The smallest belief with the most code consequences: it is why `allow_downgrade` is
configuration and why a request carrying it gets `422`.

---

## 4. Principles

Each principle states the rule, why it exists, which engineering decisions follow,
and which ADR depends on it. Where no ADR exists, that is written as a gap — a
principle with no decision beneath it is a wish.

### P1 — Clinical primacy

> FutureKind serves the clinical task. The clinical task never serves FutureKind.

**Why.** `CONTRIBUTING.md:39-41` already commits the platform to "assists
clinicians… never replaces clinical judgment". A platform that requires clinicians to
adapt to its vocabulary, latency or failure modes has inverted that.
**Engineering decisions that follow.** Degradation must be visible rather than
convenient — which is why a refused downgrade answers the caller instead of quietly
using a smaller model. Any integration that would make an application wait on a
platform-side migration is the platform's problem, not the clinic's (the reason
`capability` is being retired as a public selector instead of the catalogue being
forced to match it).
**ADRs that depend on it.** ADR-0002 rule 2 (`:104`), which makes intent — not
infrastructure — the public contract. **No ADR states this principle outright;
gap → recommended ADR-0006.**

### P2 — Patient safety before capability

> A feature that cannot be made safe is not shipped. A feature that is safe but
> slow to ship is fine.

**Why.** `CONTRIBUTING.md:11` lists "Patient safety" as the first thing a
contribution must improve. The failure mode this guards against is specific and
common: a plausible, well-formed, wrong sentence reaching a patient because the
platform was eager.
**Engineering decisions that follow.** Clinical risk must be declared, never
defaulted — the loader refuses a skill with no `clinical_risk` (`models.yaml`
requires it of every skill). High and critical risk skills may not be downgradable,
enforced at load rather than at request time. Approval-required skills **refuse**
rather than proceed on an unverifiable claim.
**ADRs that depend on it.** None. The risk ladder is a policy mechanism with no
decision record behind it. **Gap → recommended ADR-0006.**

### P3 — A named human owns every clinical statement

> Every clinical statement is traceable to a human who is accountable for it. AI
> drafts; humans decide.

**Why.** CB2. If responsibility cannot be located, nothing in this platform can be
defended in a medicolegal review — and `genesis/medicolegal.md`, the file meant to
own that reasoning, was empty and is deleted. The reasoning has no home until a
clinical owner writes it.
**Engineering decisions that follow.** An AI output may never be *final* without a
human action; therefore Approval is a first-class object with a real lifecycle, not
a boolean on a request (see P9). Provenance fields (`model`, `provider`,
`skill`, `clinical_risk`) are reported on completions so accountability has
something to attach to. **Sign-off** stays the clinical verb and **Approval** the
system record, per `docs/DOMAIN_MODEL.md`.
**ADRs that depend on it.** ADR-0002 (`:97`) gives the Gateway the audit and
clinical-context duty, which is the *recording* half. The *human-decision* half has
no ADR. **Gap → recommended ADR-0005.**

### P4 — Data ownership stays with the hospital

> Patient data is the hospital's. FutureKind holds it, processes it, and never
> claims it.

**Why.** ADR-0001 `:54` is the platform's founding promise, and CB4 says the promise
is only worth what the data paths enforce.
**Engineering decisions that follow.** No telemetry that carries clinical content;
prompt and completion text are never written to the Gateway's own logs
(`observability/logging.py:31`, `FORBIDDEN_FIELDS`). Runtime data lives outside Git
and outside the image (`ARCHITECTURE.md:202-214`, `FK_RUNTIME` in `.env.example`).
A vendor key is never embedded in a distributed artifact — `ARCHITECTURE.md:196-198`
already bans secrets in compose and repositories.
**ADRs that depend on it.** ADR-0001 in full. **The privacy *mechanism* — log-field
discipline — has no ADR. Gap → recommended ADR-0004.**

### P5 — Human oversight is a designed affordance, not a posture

> Where a human must supervise, the interface must make supervision possible:
> show the basis, show the difference from the prior state, and make override cheap.

**Why.** "Human in Control" (`ARCHITECTURE.md:21`) is currently a belief with no
mechanism. A human tapping "approve" on output they cannot interrogate is not
oversight; it is a delay with a signature.
**Engineering decisions that follow.** Output must be decomposable into
individually acceptable parts (**Observations**), not paragraphs (P13). Policy must
be surfaced to the application — `approval_required` on every completion exists so a
UI can say "this still needs you". Risk levels must be honest, including the
admittedly uncomfortable `unspecified` for a request that named no skill.
**ADRs that depend on it.** None. **Gap → recommended ADR-0005 and ADR-0006
together.**

### P6 — Patient safety by default, not by configuration

> The safe setting is the default setting. Weakening protection must be an explicit,
> logged, operator-owned act.

**Why.** This is already the code's best habit: authentication fails closed — if
auth is required and no keys are configured, `/chat` answers `503` rather than
serving an open AI endpoint (`api/deps.py`). Defaults decide what happens when
someone is in a hurry, which is most of the time.
**Engineering decisions that follow.** Keep the fail-closed pattern everywhere a new
surface appears. Note the one place the platform currently contradicts itself:
`require_auth` may be set false (`config.py:100,120`, honoured at `deps.py:88`),
which is legitimate for development and illegitimate for a hospital. Under this
principle the off-switch must be visibly non-prod — the constitution does not
require deleting it, it requires that a hospital installation cannot end up on it by
accident.
**ADRs that depend on it.** ADR-0002's authorization consequence. Not stated as a
decision anywhere. **Gap → recommended ADR-0007.**

### P7 — Vendor independence

> No single vendor may become a requirement for core clinical work.

**Why.** `ARCHITECTURE.md:26` lists it as a design principle, and ADR-0001 rejected
cloud-first partly for this reason (`:48`). It is also the reason ADR-0002 exists at
all: if model choice lived in the Gateway, every backend change would be a FutureKind
change.
**Engineering decisions that follow.** Applications speak **Skills**, never models
(ADR-0002 rule 1, `:103`). Model identity is reachable only through an **Alias**, so
a hospital moving from Ollama to anything else is a config edit, not a code change.
LiteLLM is one Provider among a contract's worth — `ProviderRegistry` stays keyed by
a bare string precisely so adding a second does not force a new abstraction
(`ADR-0002:157`).
**Tension to name honestly.** ADR-0002 `:123` accepts that "LiteLLM becomes a hard
dependency on the request path". Under P7 that is survivable only because LiteLLM is
self-hosted in the same compose project; the moment it is a SaaS endpoint, P7 and P4
are both broken. **ADRs that depend on it.** ADR-0001, ADR-0002.

### P8 — Transparency of provenance

> The system must be able to say, for any output, which skill was asked, which
> policy applied, which alias was requested, which model answered, and whether a
> lesser class answered in place of the one routed to.

**Why.** CB1 and CB3. A hospital that cannot read the platform cannot audit it, and
a clinician who cannot see what produced a sentence cannot responsibly sign it.
**Engineering decisions that follow.** Response schemas report `skill`,
`capability`, `model`, `provider`, `selected_by`, `degraded`, `attempts` and the
`policy` object. `degraded` exists specifically so a substitution is not invisible.
Model ids are reported but never accepted — the right to know is not the right to
choose (ADR-0002 `:103`).
**Where the platform currently fails this principle.** The **Alias** — the thing
actually *requested* — is logged but returned nowhere, and an operator's
provenance view depends on unauthenticated log access (see P10). **ADRs that depend
on it.** ADR-0002.

### P9 — Auditability is a record, not a log

> The audit trail must outlive the process that wrote it, be retrievable by someone
> who was not in the room, and state what was *decided*, not only what happened.

**Why.** CB6. And because the platform already claimed it: `ARCHITECTURE.md:56` puts
**Audit** in FutureKind Core, `:118` lists it as Core-owned, and `core/gateway/README.md:26`
advertised an audit record and OpenTelemetry tracing. `configs/litellm/config.yaml:22`
sets `disable_spend_logs: true`. All three subdirectories under `monitoring/` were empty,
and no tracing code exists anywhere in the Gateway.
The advertisements were withdrawn on 2026-10-08 — the README names what runs, the
manifest says `planned`, and the architecture document opens with which boxes are
built. **What was withdrawn was the claim, not the gap:** audit is still emitted and
still not retained, which is why this principle is `[ABSENT]` rather than repaired.
**Engineering decisions that follow.** A record needs retention, ownership and a
query path — so `skill_audit` must be persisted somewhere a hospital controls, with
a stated retention period. Emitting JSON to stdout is a *transport*, and a
constitution should refuse to call transport a record. Where storage remains
unimplemented, the honest engineering act is to **not advertise it**: the README
claim already exceeds the code.
**ADRs that depend on it.** None. This is the largest unbacked principle in the
platform. **Gap → recommended ADR-0003.**

### P10 — Privacy by data path, not by policy

> Assume the log pipeline, not the attacker. Names of fields are the control, and
> no code path may put clinical text into a telemetry surface.

**Why.** CB4. The realistic leak in a clinical AI system is a well-meaning engineer
adding `content=str(request)` to a debug line. Hence a *denylist of field names*
rather than a style guide (`observability/logging.py:31`), and a validation-failure
envelope that reports the violated rule instead of the rejected value
(`tests/test_api_chat.py:260` uses an MRN-shaped secret precisely to prove it).
**Engineering decisions that follow.** Keep the field blacklist. Extend it to every
new outward surface, including metrics labels and `/health` details — and today
`/health` reports `"{n} models from {catalog.source}"`, i.e. an absolute server
filesystem path, to any caller. Path disclosure is not patient data, but it is the
same category of mistake and P10 forbids the category.
**ADRs that depend on it.** None. **Gap → recommended ADR-0004.**

### P11 — AI limits are stated as prohibitions

> AI may draft, summarise, translate, compare and question. AI may not be the final
> author of a clinical decision, may not sign, may not order, may not dispense, and
> may not be the only thing standing between a question and a patient.

**Why.** `CONTRIBUTING.md:41`'s "never replaces clinical judgment" is currently a
promise with no enforcement surface. Prohibitions are enforceable; values are not.
**Engineering decisions that follow.** Approval exists as an object so a signature
has somewhere to live (P3). Any *order/set of* action surface must not exist
(see P16's ban on tool access to a model, and ADR-0002's refusal to let the Gateway
touch provider credentials). Nothing in the platform may classify an AI output as
final: a final state must be reachable only by a human transition.
**ADRs that depend on it.** None. **Gap → recommended ADR-0005.**

### P12 — Workflow belongs to clinicians, not to the platform

> FutureKind participates in clinical workflows. It does not own, redefine, or
> require them.

**Why.** `CONTRIBUTING.md:12` and ADR-0001 `:48` both say "clinical workflow" as if
the term were defined; `docs/DOMAIN_MODEL.md` records it as [ABSENT] as a structure.
Meanwhile the host EHR — CARE ERP (`ARCHITECTURE.md:36`) — already owns real
workflows. Two owners of one workflow diverge, and the patient pays.
**Engineering decisions that follow.** A **Skill** is the platform's whole exposure of
a workflow step: one intent in, one answer out, no state imposed on the clinic. The
Gateway stays stateless about conversations (P18) for exactly this reason. Before any
workflow engine is built here, Q5 in `docs/DOMAIN_MODEL.md` — FutureKind or the EHR? —
must be answered, because that question is a boundary, not a feature.
**ADRs that depend on it.** ADR-0002 `:97` (Gateway owns clinical context, LiteLLM
owns nothing clinical). No ADR decides workflow ownership. **Gap → recommended
ADR-0005.**

### P13 — Clinical truth is traceable or labelled

> Every clinical statement inside FutureKind must either point at its basis — an
> observation, a document, a prior report, a measurement — or be explicitly marked
> as inference. An unlabelled inference presented as fact is the platform's primary
> harm mode.

**Why.** CB1. The distinctive failure of LLMs is not wrongness but *unmarked*
wrongness: the sentence and its basis are indistinguishable in the output.
**Engineering decisions that follow.** **Observations** are first-class, so a report
decomposes into acceptable parts and a claim can be refused without refusing the
document. **Knowledge** must be citable or it is not admissible (P15). A model that
cannot be grounded should say so; the platform's own precedent is the honesty
pattern of `clinical_risk: "unspecified"` — name the absence instead of defaulting it
away. `genesis/quality_check.md` and `genesis/reasoning.md` were to hold this rule for
each specialty; both were empty and are deleted, so the rule exists here in P12 alone
until clinical authoring gives it per-specialty text.
**ADRs that depend on it.** None. **Gap → recommended ADR-0006.**

### P14 — Hospital philosophy: one hospital, one authority

> Each installation is sovereign. No cross-hospital inference, no shared model of a
> patient, no platform-wide analytics that a hospital cannot see or refuse.

**Why.** ADR-0001 `:11` promises deployability to hospitals of any connectivity, and
`ARCHITECTURE.md:10` gives them data ownership. Sovereignty is what makes N
installations safe instead of merely duplicated.
**Engineering decisions that follow.** Do not import "tenant" thinking:
`docs/DOMAIN_MODEL.md` records `Tenant`, `facility` and `site` as absent, and
`configs/futurekind.yaml:14` `organization: FutureKind Health` names the *vendor* — a
trap for anyone reading tenancy into that key. Federated learning, cross-site
benchmarks and vendor-side dashboards are all forbidden until this principle is
deliberately amended, not quietly eroded by a metrics field.
**ADRs that depend on it.** ADR-0001. Note the corollary nobody has written down: a
**Hospital** needs an identifier. Today it has none anywhere in the repository, so
sovereignty is currently a convention between deployments rather than a property of
the system. **Gap → recommended ADR-0007.**

### P15 — Knowledge is content, not infrastructure

> Knowledge is curated, versioned, attributable clinical material. A vector database
> is not knowledge, and retrieval without provenance is not evidence.

**Why.** The platform currently names only products: `vector: Qdrant`,
`search: SearXNG`, `crawler: Crawl4AI` (`configs/futurekind.yaml:40-46`) and an empty
`services/knowledge/`. Naming the storage and calling it knowledge is how an
unverified web crawl ends up inside a radiology impression.
**Engineering decisions that follow.** Every ingested item needs origin, version and
an adoption decision by a clinical owner; a citation must survive from the retrieved
chunk to the generated sentence. Crawled material is *candidate* knowledge and must
not be admissible until adopted.
**ADRs that depend on it.** None. ADR-0002's boundary helps by keeping retrieval
decisions away from model routing. **Gap → recommended ADR-0006.**

### P16 — The Gateway is the single AI boundary; and it is thin

> All AI traffic passes the Gateway, and the Gateway owns exactly four things:
> permission, policy, provenance, privacy. It owns no model choice, no credential,
> no retry, no spend.

**Why.** `ARCHITECTURE.md:104-110` states the boundary, and ADR-0002 exists because
the boundary and the *thickness* were being confused: a gateway that also routes
models drifts, and two tables disagree forever (`ADR-0002:53-56`).
**Engineering decisions that follow.** No application may reach a model or a
backend directly, and — read widely, this includes **Tools**: an agent's tool call
that reaches a model outside the Gateway breaks P3's traceability as surely as a
browser would. Provider credentials never appear in the Gateway. A tool is
registered, bounded and audited, or it does not exist.
**ADRs that depend on it.** ADR-0002 (`:97`, `:99`).
**Live exception, admitted.** ADR-0002 `:126` retains the Gateway's candidate-chain
machinery, which "overlaps LiteLLM's retries". Since Sprint 2, `allow_downgrade`
decides *whether* a chain may be walked, but the Gateway still orders *which* lesser
entry runs. Under P16 that residue is out of compliance, recorded as debt rather than
fixed — which the constitution permits briefly and P16 forbids permanently.

### P17 — Skills are intent; Agents are personas; neither may choose infrastructure

> A **Skill** is the only unit of clinical intent the platform routes on. An
> **Agent** is a clinical persona that owns prompts, style, templates and a set of
> Skills. An Agent never appears in a Gateway request, and a Skill never names a
> model, alias or provider.

**Why.** `docs/DOMAIN_MODEL.md` records the collision: Sprint 1 made Skill the
enforced unit of intent, while `agents/` grew folder-per-specialty structures that
wanted the same job. They were empty enough that nothing broke, which is exactly when
such boundaries are lost. The tree is deleted as of 2026-10-08; the collision it
represented is still resolved by the rule below, not by the deletion.
**Engineering decisions that follow.** Namespaces stay separate and are guarded by
tests: `Skill`, `Capability`, `Policy`, `Alias`, `Model`, `Agent` each mean one thing
with different permissions. The loader refuses infrastructure keys on a skill.
when the clinical layer is authored, `agents/<specialty>/agent.yaml` must get a schema
that cannot express routing (`name`, `specialty`, `skills`, `templates`, `style`) and
nothing else.
**ADRs that depend on it.** ADR-0002 rules 1-2 (`:103-104`).

### P18 — Language is a first-class artifact

> A concept has one name, one owner and one definition, or it does not enter the
> codebase.

**Why.** CB5 plus the observed cost: the repository's own chain is written two ways
(`ARCHITECTURE.md:138-154` versus `docs/architecture/gateway-routing.md:18`), one word
used to mean both FutureKind's service and LiteLLM (`configs/futurekind.yaml:40` now
reads `gateway: FutureKind Gateway` and `:42` `routing: LiteLLM`, which is the
separation this principle asked for), and a
`Model Router` exists twice with different jobs.
**Engineering decisions that follow.** `docs/DOMAIN_MODEL.md` is the naming
authority; a PR introducing a new domain term without a row there is incomplete
(Sprint 3's M0 asks for exactly that checklist line). Code identifiers follow the
document, not the reverse.

### P19 — The platform must be deletable in its parts

> Every component may be replaced without a clinical application changing a line.

**Why.** `ARCHITECTURE.md:230` promises deployment changes "without changing platform
architecture"; CB5 generalises it. This is the falsifiable form of ADR-0002's
migration plan.
**Engineering decisions that follow.** Intent-level public API only. Configuration
separates the durable (skills, policy) from the volatile (aliases, endpoints,
credentials). No public surface is named after a product — which is why
`ai.gateway: LiteLLM` is a language bug and not merely a typo.
**ADRs that depend on it.** ADR-0002 (its whole negative-consequences section).

---

## 5. The clinical objects under constitutional rule

These are not principles; they are the four-plus nouns the principles attach to,
recorded here so that the clinical team and the platform team cannot each mean
something different. Language authority stays with `docs/DOMAIN_MODEL.md`; this
section states what each must *serve*.

**Observation.** The smallest individually checkable clinical statement about a
patient. Rule: nothing may be accepted as a whole that a clinician cannot accept
part by part (P5, P13). Status: [ABSENT] — the word appears in no code, no
configuration and no clinical file; only in `docs/DOMAIN_MODEL.md` and here.

**Report.** The clinical deliverable. It contains Observations, concludes with an
Impression, and is signed by a human. Rule: a Report may reach a final state only
through a human transition (P11). Status: [ABSENT] as an entity; exists today as a
suffix on two skill names, with `models.yaml` calling the radiology one an
"impression" and the pathology one a "report" — same artefact, two nouns, one file.

**Approval.** The recorded act of a named human accepting a clinical statement.
Rule: it is a record with an author, never a request field (P3, P11, CB7). Status:
enforceable as a refusal only (`403 approval_required`); `gateway-policy.md` says so
plainly — "Approval is a refusal, not a workflow".

**Knowledge.** Adopted, versioned, citable clinical material. Rule: no citation, no
admissibility (P13, P15). Status: [ABSENT]; named only by three product keys in
`configs/futurekind.yaml` and an empty directory.

**Skill.** The public unit of clinical intent, and the only thing an application may
ask for. Rule: it carries policy and never infrastructure (P17, P19). Status: [CODE],
enforced and guarded by tests.

**Agent.** A clinical persona owning prompts, style, templates and a set of Skills.
Rule: it never enters the Gateway; if it must, that is a constitutional amendment,
not a parameter (P17). Status: [ABSENT] — the sixteen placeholder files under
`agents/` were deleted on 2026-10-08, so the concept has no artefact at all.

---

## 6. Future evolution

**How this document changes.** Only the platform owner may amend it, and only via a
written ADR that states which principle was in conflict with what real requirement,
what was tried under the existing principle first, and what protection replaces the
one being relaxed. "It was inconvenient" is not an input. Two clauses are stronger
still: **P2, P4, P11 and P13 may never be traded for convenience, latency, cost or
release date.** They are the difference between this platform and a chatbot in a
hospital coat.

**Where authority sits.**

```
Constitution  (why; immutable; falsifiable)
   ↓ binds
ADRs          (what was decided; may be superseded by a later ADR)
   ↓ constrain
ARCHITECTURE  (how it is arranged)      DOMAIN MODEL (what things are called)
   ↓                                     ↓ describes and constrains
code, configuration, logs
```

The Domain Model is not below the ADRs: it binds them on naming, because a decision
taken in a language with two words for one thing is a decision nobody can re-read in
two years. That is an unusual arrangement and it should be stated rather than
assumed.

**What may grow.** More Providers under one contract; more Skills; new capabilities
once a modality axis exists (ADR-0002 `:155` refuses a `tier` field with no data
behind it — correct, and an example of the constitution working); clinical doctrine,
for which `genesis/` was the intended home and which now starts from nothing; more
services.

**What must not grow, ever.** A second AI boundary (P16). Model or provider
selection in a request (P8, ADR-0002 rule 1). A silent substitution of a lesser model
(P13). Any cross-hospital data path without an explicit amendment (P14). A clinical
final state with no human transition behind it (P11).

**How to tell the platform is drifting, early.** Three cheap tripwires, all
checkable by grep: if a `model:` or `provider:` key appears in any request schema; if
anything other than `core/gateway` accepts a completion request; if a principle in
this file has no ADR underneath it while a feature has. As of this writing, the
second of those is nearly satisfied by `configs/futurekind.yaml:44` naming Open WebUI
`interface` in the Services layer.

---

## 7. Known non-conformance at adoption

A constitution that describes only intentions is decoration. These are violations
found against the code as it was written, listed with the evidence so that they
become work rather than embarrassment. A row is marked closed only with the change
that closed it, and stays in the register as the record that the constitution
caught it. Full matrix in the Sprint 4 review; this is the standing register.

| # | Principle broken | Evidence | State |
| --- | --- | --- | --- |
| 1 | P10 Privacy, P8 Transparency | `GET /models` is unauthenticated (`AuthenticatedCaller` appears only on `/chat`, `routes_chat.py:90`) and returns every internal `provider` + `model` pair | **Closed 2026-10-08** — `/models` and `/models/{capability}` take the same `AuthenticatedCaller` as `/chat`; `test_openapi.py` and `test_api_models.py` refuse the unauthenticated read |
| 2 | P10 | `/metrics` is unauthenticated and `fk_gateway_catalog_models` carries `{capability, provider, model}` labels (`metrics.py:79`) — enumerating the model inventory | **Closed 2026-10-08** — `/metrics` requires a credential; a Prometheus scrape sends a bearer token, so the gate is a deployment setting, not a code change. Nothing in this repository ships a scraper, so nothing was broken by closing it |
| 3 | P10 | `/health` returns `"{n} models from {catalog.source}"` — an absolute server path, unauthenticated | **Closed 2026-10-08** — the probe endpoints keep their key-free reach (a container runtime cannot hold a credential) and lost their inventory: no catalogue path, no provider names, no upstream error text. `catalog_source` is gone from the response model; the reason a catalogue failed to load is logged on the host instead |
| 4 | P9 Auditability | `core/audit/` empty; `disable_spend_logs: true` (`configs/litellm/config.yaml:22`); `monitoring/*` empty; while `ARCHITECTURE.md:56,118` and `core/gateway/README.md:26` advertise audit and tracing | Claim exceeds system. The advertisement is being removed, not reworded around a capability that does not exist; the storage work stays scheduled in the ROADMAP |
| 5 | P16 thinness | ADR-0002 `:126` retains Gateway chain ordering that overlaps LiteLLM retries | Admitted debt |
| 6 | P18 Language | `ARCHITECTURE.md:150-154` (Model Router / LLM) vs `gateway-routing.md:18` (Provider / Model) | Partly resolved 2026-10-07: `configs/futurekind.yaml` no longer calls LiteLLM "gateway" (`:40` Gateway, `:42` routing), and the chain the architecture drew is now the chain that runs — Gateway → LiteLLM → backend |
| 7 | P4 / ARCHITECTURE `:168-172` | ".env one configuration source, no duplicated settings" vs `models.yaml`, `configs/futurekind.yaml`, two compose files with different data roots (`compose.yaml` `${FK_RUNTIME}/…` vs the now-deleted `compose/compose.core.yaml`, whose postgres volume sat at `../data/postgres`), four version declarations | Narrowed 2026-10-08, not closed: the second compose tree is deleted, and the four version declarations are now one per artefact (`[tool.hatch.version]` reads the package `__init__.py`; `VERSION` is gone; the manifest holds only the release-line name). What remains is the actual rule — `.env` holds deployment settings, `models.yaml` holds routing, `configs/futurekind.yaml` holds a codename. Three files, three kinds: "one source" is still false as written, and SPEC-11-01 now holds by there being nothing to duplicate rather than by generation |
| 8 | P14 Sovereignty | No Hospital identifier exists anywhere; ADR-0001 `:54`'s subject is unrepresentable | Gap |
| 9 | P3 / P5 / P11 / P13 | Four principles with no ADR beneath them | Gap |
| 10 | P17 | `agents/` and `genesis/` intend a clinical layer that does not exist; commit `dfec7f0` "AI Genesis-A constitution." claims an authority this file now holds | Artefacts removed 2026-10-08: both trees were deleted rather than left as an advertisement. The authority collision is settled by this file being the only constitution in the repository; the clinical layer itself remains unbuilt and scheduled |

Nothing in this register requires new capability to fix, which is what made leaving
it broken a choice rather than a constraint. Items 1-3 closed on 2026-10-08: an
authentication dependency and a label review, exactly as priced here. Item 4's
honest half is a wording change until storage exists — the wording is being changed,
and the storage stays scheduled rather than promised.

---

**FutureKind Principle**

> We build the smallest system a hospital can audit, that answers for what it did,
> and that never lets a machine be the last one to decide. Every other document in
> this repository is an argument about how, and must survive being read against this
> one.
