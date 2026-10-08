# FutureKind Failure Modes

**How this project dies, ranked, with the earliest sign available in this repository.**
Genesis Night 4, 2026-10-09.

| | |
| --- | --- |
| **Owns** | Failure analysis, success analysis, and the kill criteria. |
| **Does not own** | Threats from a malicious actor ([`security/THREAT_MODEL.md`](security/THREAT_MODEL.md)), clinical gates ([`safety/CLINICAL_SAFETY.md`](safety/CLINICAL_SAFETY.md)), the never-list ([`INVARIANTS.md`](INVARIANTS.md)). |
| **Numbering** | `FM1…` for failure modes. `F1…F30` already means "workflow break" in `clinical/HOSPITAL_WORKFLOW.md` §7, and one prefix for two things is the defect this file is meant to prevent, not propagate. |
| **Method** | Ranked by (probability × irreversibility), not by how frightening each row reads. Every warning sign must be checkable by a person who is not the author. |
| **Drift check** | Each `FM` row's "Already visible" line is dated and points at a measurement or a file, so the ranking can be re-tested rather than re-asserted; the kill criteria in §3 are the strongest form of the check, because each names the condition under which the file itself should be closed. What has no instrument: the rankings. They are judgement, labelled as judgement. |

---

## 1. Ranked failure modes

### FM1 — Correct and unused

The product works, the checks are sound, and nobody uses it, because it saves ninety
seconds and costs three clicks and a reading of a warning.

- **Mechanism.** Drafting speed is not the buyer's pain; the pain is queue, interruption and
  rework. A tool that improves only the typing step is measured against a step the
  clinician does not experience as the bottleneck.
- **Earliest sign.** Adoption well below the volume the department actually reports; or
  time-in-screen *rises*; or the dashboard's edit-rate falls toward zero, which means drafts
  are accepted unread — the rubber stamp, and worse than non-use. No threshold is proposed
  here on purpose: a number invented by engineering to detect a clinical failure is the
  failure FM2, and the pass thresholds in `GOLDEN_DATASET.yaml:56` are still labelled a
  proposal for the clinical owner for the same reason.
- **Already visible.** Not one clinician number exists, and the platform says so in its own
  latency row: a real `qwen3:14b` on the hospital's machine "has never been timed here, and
  that number is the single most important unknown" (`product/RADIOLOGY_WORKFLOW.md:234`).
  The dashboard deliberately asks the human for the two verdicts it cannot infer.
- **Cheapest monitor.** One afternoon, twenty cases, `run-cases.py session`. It has never
  been run against a real model or a real radiologist.

### FM2 — The empty clinical seat

An engineer's guess becomes a clinical decision by default, because no one else is present
to make it.

- **Mechanism.** Risk levels, thresholds, style authority and case ratification are all
  authored by engineering today. Nothing blocks a well-meaning correct change to a clinical
  parameter.
- **Earliest sign.** `ratified: pending` still at 100 of 100 in twelve months (measured now
  — `GOLDEN_DATASET.yaml`, all 100). Second sign: a `clinical_risk` value changed in a
  commit whose message mentions no clinician.
- **Already visible.** `GOLDEN_DATASET.yaml:56-60` labels the pass thresholds "proposal, for
  the clinical owner to set", and gate G5 in `CLINICAL_SAFETY.md` is marked Not done.
- **Cheapest monitor.** A one-line rule in `GOVERNANCE.md` — the four decisions engineering
  may not take alone — plus a commit-message convention.

### FM3 — A false refusal, publicly

One correct report is blocked, in front of a department, and the tool is routed around
forever.

- **Mechanism.** A check's severity is a hypothesis about the world; the world is the
  corpus, and the corpus was authored by an engineer. `dropped_observation` blocked 87 of
  100 *correct* expected answers before it was reclassified.
- **Earliest sign.** Any promotion of an `advisory` check to `block` without a measured cost
  line. The residual is already known: one faithful golden still refused (`E-03`, arithmetic
  on two dictated volumes).
- **Already visible.** Two fixes repaired checks introduced six commits earlier, same day
  (`invented_history` severity split, `invented_identifier` narrowing). That is the system
  working — the danger is stopping the measurement and keeping the block.
- **Cheapest monitor.** Every blocking check carries its false-positive rate against the
  ratified corpus, or it is advisory. This rule exists in prose; it needs the audit script
  to enforce it.

### FM4 — A missed hallucination, attributed to the platform

A wrong draft is signed. The investigation reaches the check list, and the check list's
measured detection is 3 of 306 synthetic probes.

- **Mechanism.** The nine checks are grounding and format instruments, not truth
  instruments. They catch a dropped observation or an invented measurement; they do not
  catch a plausible sentence that was never in the dictation and is not contradicted by the
  absence checks.
- **Earliest sign.** Someone quoting the old "87%" again; a check shipped with no paired
  baseline; a probe set that grows without the false-positive set growing with it.
- **Already visible.** 269 of the 303 missed probes raise nothing at all, and `audit-checks.py`
  is explicit that every number there is a property of the checks and a synthetic corpus.
- **Cheapest monitor.** The two numbers published side by side, always: newly-blocked probes
  and newly-blocked correct reports. One of them alone is marketing.

### FM5 — The evidentiary gap becomes a legal one

A coroner, inspector or plaintiff asks a question the platform answers in principle and
cannot answer in data.

- **Mechanism.** `skill_audit` lines are emitted to a log host and not retained. There is no
  `GET /reports/{id}`, no Hospital, no per-person identity, and `ADR-0003` does not exist.
- **Earliest sign.** A hospital's infosec or legal review asks for a retention figure and
  the answer is a design document. Second sign: a deployment is planned with the sentence
  "retention comes in Beta".
- **Already visible.** `CONSTITUTION.md` §7 row 4; `CLINICAL_SAFETY.md` §5's
  attestation-versus-verification table; the six medicolegal questions in §8, none of which
  is answerable from stored data today.
- **Cheapest monitor.** One test that a two-year-old audit line can be produced. It cannot
  be written yet, and *that* is the monitor: the absence of the test.

### FM6 — One person

The constitution, the roadmap, the clinical judgement, the merge rights and the support
queue are held by one human. Not a weakness of character — a single point of failure with
no redundancy and no documentation of its own reasoning.

- **Earliest sign.** An ADR that stays unwritten while being cited dozens of times (measured
  now: 131 references to five). Night 3 deferred its own implementation wave to a future
  decision by the same person.
- **Already visible.** `DOMAIN_MODEL.md` carries six owner questions, four answered in
  design and two still open, all addressed to one reader.
- **Cheapest monitor.** Any decision recorded twice — once as a rule, once as a reason — is
  a decision a stranger can re-read. `PHILOSOPHY.md` exists for that reason.

### FM7 — Shared credential, real PHI

One API key for a hospital, present in git history, and the platform's "who asked" promise
made on top of it.

- **Mechanism.** The Gateway authenticates a *deployment*, not a *person*, so no clinical
  act has an author at the protocol level. The screen says so plainly in its own header.
- **Earliest sign.** The key copied to a third laptop; a developer asking to reuse it for a
  demo; `ADR-0004` still unwritten when the second department goes live.
- **Already visible.** The history of this public repository contains a LAN address and the
  default master key (`ef89e4b`); the tip is clean, the history is not, and rotation is the
  operator's uncompleted action.
- **Cheapest monitor.** A CI check that fails on any `sk-` shaped literal in tracked files —
  which is cheap, blunt, and the only class of secret leak that has already happened here.

### FM8 — Death by description

The documents grow faster than the instruments, and the repository's honesty outruns its
evidence.

- **Mechanism.** Prose is cheap to add and expensive to keep true; every new document is a
  new way to be wrong. Night 3 added ten documents and one commit repairing three defects
  those documents created.
- **Earliest sign.** Document count rising while the number of *failing* checks stays flat;
  two files describing one mechanism; a README count that no command produces.
- **Already visible.** `CONCEPTUAL_DEBT.md` §5: 75 python files, 37 markdown, one of three
  test suites unwired while six documents count its tests.
- **Cheapest monitor.** The counter-rule every new document must satisfy: *name the check
  that fails when I drift.* If none, it must be a pointer.

### FM9 — The ungoverned neighbour

A hospital runs a chatbot next to FutureKind, and the quality of FutureKind's refusals is
judged by the other tool's recklessness — or the other way round.

- **Earliest sign.** A request to "just allow free chat on the radiology screen"; an
  Open WebUI instance pointed at a clinical skill rather than `platform-chat`.
- **Already visible.** `models.yaml:41-52` makes `platform-chat` the one non-clinical skill
  an OpenAI-format interface may use, which is the correct containment; the ERP carries
  eighteen AI paths that the platform does not govern (`APPLICATION_MAP.md` §3.1).
- **Cheapest monitor.** A named refusal with a reason the operator can show a clinician.

### FM10 — Deskilling and automation drift

Five years of accepted drafts produce a generation of reporters who no longer check the
measurement, because nothing ever told them it was wrong.

- **Earliest sign.** Edit distance toward zero while volume rises; a department that stops
  asking what a block means.
- **Already visible.** Not observable — there is no longitudinal data, and this is the
  failure mode the platform is structurally blind to. The mitigation is architectural:
  measurements are the human's, the watermark states AI assistance, and confidence is never
  taken from the model.
- **Cheapest monitor.** Publish per-clinician edit rate back to that clinician, not to a
  league table. The first is feedback; the second is gaming.

### FM11 — The licence becomes the argument

A fork ships to a hospital with different refusals under the same name, and the difference
is invisible to the buyer.

- **Earliest sign.** An issue from someone running a modified catalogue; a vendor citing
  FutureKind while the never-list is unenforceable in their build.
- **Already visible.** No trademark policy, no CLA, no foundation, zero external
  contributors, and a `CONTRIBUTING.md` whose Community section describes a practice rather
  than a record — which is fine as intent and misleading as evidence.
- **Cheapest monitor.** A named licence-plus-checklist artefact — "a conformant deployment
  answers these seven questions" — which is the only enforceable form of an open-source
  promise without trademark litigation.

### FM12 — The model gets good and the moat moves

Local models become adequate everywhere, so local-first stops being a differentiator, and
the platform is judged only on its drafting.

- **Earliest sign.** A competitor shipping on-prem with a better evaluation story.
- **Already visible.** None, and that is the point: this is the *least* dangerous row,
  because stage 4 (evidence) does not depend on model scarcity. If it arrives early, the
  strategy was already correct.
- **Cheapest monitor.** Keep the model layer replaceable — `ADR-0002` did that; the alias
  contract keeps it true.

---

## 2. Success analysis

The mirror question: if this works, what will have been observable first, and in what order?

| Signal | Why it is the leading one | State tonight |
| --- | --- | --- |
| **A clinician ratifies a golden case they did not write.** | Segregation of duties arrives in the evaluation, and every gate in `CLINICAL_SAFETY.md` §6 acquires a real input. | 0 of 100 |
| **Edit distance stays high while adoption stays high.** | Humans are reading. This single pair distinguishes FM1 from FM10, and both from success. | Never measured |
| **A second site installs it without the author in the room.** | The documentation is a working interface, not a description of one. | One deployment, one author |
| **A stranger's pull request deletes code and passes the gate.** | The smallest-system rule is held by people with no incentive to hold it. | No external contributors |
| **A department refuses a feature for a stated clinical reason.** | Ownership of the never-list has moved to the clinic. | Not attempted |
| **An incident produces a check *and* a measurement of that check's cost.** | The safety engine keeps running after launch. It already does this in the small: the tenth check was measured and rejected. | Working |
| **A regulator accepts the audit record without a custom export.** | Stage 4 becomes real. This is the one that turns the platform into an institution. | Impossible today |

> **Verdict.** Three of the seven are unachievable by engineering alone, and two are
> unachievable by this repository alone. So the honest reading of "success" for 2027 is not
> a feature set: it is **the ratification column filled by a clinician, and one number
> measured against a human.**

---

## 3. Kill criteria

A project that cannot name its own death condition is not engineering a strategy, it is
expressing a preference. These are proposals for the owner to accept, amend or reject — and
they are written now, while they cost nothing.

1. **If, after two years, no clinician has ratified a case**, the evaluation is an
   engineer's mirror and the safety argument is a document. Stop authorising new
   applications; fix the corpus or stop claiming it.
2. **If adoption exceeds 50% and edit distance approaches zero**, the product has become an
   automation the platform was explicitly designed to refuse. Turn the drafting off and
   keep the checks.
3. **If a hospital asks for liability transfer and we can only offer evidence**, do not
   sell it. A promise we cannot hold is not a gap to close with language.
4. **If the maintenance load of the documents exceeds the maintenance load of the code**,
   delete documents. The register in `CONCEPTUAL_DEBT.md` exists to make that decision
   mechanical rather than emotional.
5. **If a single person remains the only clinical, architectural and governance authority
   after 2029**, the platform is a personal practice with a repository, and the founding
   claim — an institution a hospital can audit — is false regardless of the code quality.

---

**FutureKind Principle**

> Do not ask what could go wrong. Ask what would be the first small, checkable sign — and
> put that sign where someone who is not you will look at it.
