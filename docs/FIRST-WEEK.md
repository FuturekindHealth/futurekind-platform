# Your First Week

**What an engineer must understand in seven days to preserve the soul of FutureKind.**
Genesis Night 4, 2026-10-09. Written for a stranger arriving in 2032.

| | |
| --- | --- |
| **Owns** | The onboarding path, the invariant understandings, the traps, the first pull request. |
| **Does not own** | Rules, names, architecture, sequence — each has exactly one owner, listed in [`README.md`](README.md). |
| **Premise** | In 2032 the code will be different. The models will be unrecognisable, half the files below will have been rewritten, and the radiology prompt may be a memory. What must not have changed is in §2. |

---

## 1. The five days

Ninety minutes of reading and one written answer per day. The written answer is the point:
understanding that cannot be stated is not on record, and this repository's whole argument
is that things not on record did not happen.

### Day 1 — Why anything exists here at all

Read [`CONSTITUTION.md`](CONSTITUTION.md) §1–§2 and [`PHILOSOPHY.md`](PHILOSOPHY.md) §2.

The constitution is the rules. `PHILOSOPHY.md` is the test for telling a rule from a habit:
*does removing this change who is responsible, or only how it is done?* Nine assumptions
pass that test and the entire technology stack fails it.

**Write down:** one thing in this repository you believe is defended as a principle but is
actually an accident of 2026. (There are known ones — three capability classes named after
three models on one GPU; a `model:` key that its own file's comment schedules for deletion.
Finding a new one is the exercise.)

### Day 2 — The language, and how a decision is recorded

Read [`DOMAIN_MODEL.md`](DOMAIN_MODEL.md) §1 and the rename rulings, then
[`adr/ADR-0002-Gateway-vs-LiteLLM.md`](adr/ADR-0002-Gateway-vs-LiteLLM.md) in full. It is
the best-written argument in the repository and it is also the one with unfinished business.

**Write down:** the difference between a Skill, a Capability, an Alias and a Model, in your
own four sentences, with one example of each and the file that owns each. If any of the four
sentences contains the word "tier", "mode" or "class", read `DOMAIN_MODEL.md` again — that
is the vocabulary leak talking.

### Day 3 — Trace one request, and one refusal

Start at `core/gateway/models.yaml` and follow a `radiology-report` request through
`catalog.py` → `policy.py` → `routing.py` → `providers/litellm.py`, then the copilot's four
operations in `apps/radiology_copilot/src/futurekind_radiology/copilot.py`. Then find the
code that **refuses**: a skill marked `critical` cannot be authorised today, and a policy
that forbids downgrade gets a chain of one.

**Write down:** which line would fail first if a hospital asked to choose the model itself,
and what you would have to delete to satisfy them. (The answer should be a guard test, not a
refactor. If your answer is a refactor, you have found N1 eroding.)

### Day 4 — The measurement culture, which is the actual product

Read [`safety/CLINICAL_SAFETY.md`](safety/CLINICAL_SAFETY.md) §5–§6, then
[`CONCEPTUAL_DEBT.md`](CONCEPTUAL_DEBT.md) §2, then skim the headers of
`scripts/validation/audit-checks.py` and `run-cases.py`. Note the third thing: the ten
quality checks and the nine that ship.

The habit to internalise is here, and it is rare enough to be the culture: a check that
blocked 87 of 100 correct reports was **downgraded**, not celebrated; a detection figure
that "claimed 87% and meant nothing" was re-measured; a tenth check was built, measured and
**rejected**; the dashboard refuses to infer a clinician's verdict from text because that
would be grading its own homework.

**Write down:** one claim in this repository that has no instrument named beside it. If you
cannot find one, look in the documents you were not sent.

### Day 5 — Try to break it, and read what refuses you

In a branch: add a `model` field to the request schema. Then add the word `TODO` to a
document. Then change a prompt's version in code without changing it in
`PROMPT_LIBRARY.md`. Then cite `somefile.py:99999`. Run the gates
([`../.github/workflows/ci.yml`](../.github/workflows/ci.yml)) and read every failure.

**Write down:** which of the four attacks the gates caught, and which they did not. The ones
that got through are the reason §4 exists. (Known gap: a citation whose line drifted but is
still non-blank passes — the checker verifies existence, not agreement. That is D13, and
knowing it on day five is worth more than a clean dashboard.)

---

## 2. The seven things that must survive any rewrite

This is the soul, stated as propositions a 2032 engineer should be able to defend without
having read 2026's meeting notes. If a future change breaks one of these, it is not a
refactor.

1. **A named human is last.** No code path produces a clinical final state without a human
   transition behind it. If the machine could sign, it will eventually be blamed when it did
   — and the fix will be to make it sign properly, which is the wrong direction.
2. **The caller asks for a skill, never for a model.** Permission and intent belong to the
   application; what runs belongs to the platform. This is what makes hardware changes a
   config edit instead of a clinical API break.
3. **Every safety claim carries the measurement that produced it, and the measurement names
   its stub.** "98% accurate" is a sentence; "3 of 306 synthetic probes newly blocked,
   against 1 of 100 correct reports newly refused, on an unratified corpus authored by an
   engineer" is an instrument. The second is less marketable and is the only one worth
   keeping.
4. **One word per thing, one authority per fact.** Documents point; they do not copy. A
   number that moves lives in exactly one file, or nowhere.
5. **The never-list is a feature with a cost column.** A refusal without its price reads as
   an oversight and gets deleted by the next helpful person. Argue for a refusal with the
   thing it costs the clinician, or do not call it a refusal.
6. **The hospital owns its evidence, and nothing leaves the building.** Not as ideology: as
   the only arrangement a hospital can audit, and therefore defend.
7. **Deleting is a contribution.** The two best commits in this repository's history removed
   36 placeholder files and one duplicate compose tree. Complexity is not neutral — it is
   the interest rate on every future change.

---

## 3. The reading path, with its honest cost

The document set is larger than a week. This is the path; everything else is reference.

| Order | File | Why it is on the path |
| --- | --- | --- |
| 1 | [`README.md`](README.md) (root) | One screen of what the thing is. |
| 2 | [`CONSTITUTION.md`](CONSTITUTION.md) §1–2, §6–7 | Mission, the principles, how they change, and where the platform is dishonest about itself. Read §7 first if you have ten minutes: it is the fastest honest map of the gaps. |
| 3 | [`PHILOSOPHY.md`](PHILOSOPHY.md) | The reasons, and the fundamental/accidental test. |
| 4 | [`DOMAIN_MODEL.md`](DOMAIN_MODEL.md) §1 + terminology map | The nouns. Skip the object entries until you need one. |
| 5 | [`adr/ADR-0002`](adr/ADR-0002-Gateway-vs-LiteLLM.md) | How a decision is written here, and what "not yet authorised" means. |
| 6 | [`ARCHITECTURE.md`](ARCHITECTURE.md) — the as-built section only | Then read its own honesty table, and understand that the aspirational boxes above it are a wish, not a diagram. |
| 7 | [`product/RADIOLOGY_WORKFLOW.md`](product/RADIOLOGY_WORKFLOW.md) | The only place the platform meets a real workflow, step by step, with what AI may and may not do at each. |
| 8 | [`safety/CLINICAL_SAFETY.md`](safety/CLINICAL_SAFETY.md) §5–6 | Attestation versus verification, and the five gates. |
| 9 | [`CONCEPTUAL_DEBT.md`](CONCEPTUAL_DEBT.md) | What is rotten and why the rot is structural. This is the document that tells you how to *not* repeat the last four years. |
| 10 | [`INVARIANTS.md`](INVARIANTS.md) §1 | The refusals, each with the pressure that will ask for it. Read it before your first customer meeting, not after. |
| 11 | [`FIRST-WEEK.md`](FIRST-WEEK.md) §4 | Your first pull request. |

Optional and good: [`BLUEPRINT.md`](BLUEPRINT.md) for the ten-year argument,
[`FAILURE-MODES.md`](FAILURE-MODES.md) for the risk register, [`GOVERNANCE.md`](GOVERNANCE.md)
if you are the clinical seat, [`VISION-2035.md`](VISION-2035.md) for the far view.

Reference only: the product family documents. They are design work for applications that do
not exist, and reading them before the eleven files above will give you the impression that
FutureKind is a fourteen-application platform. It is one application and a gate.

---

## 4. Your first pull request

Do this before you build anything, in this order of preference:

1. **Delete something with a reason.** A duplicated sentence, an unread config key, a
   restated number, a document with no owner. The gate is the argument; if the tests do not
   move, the deletion was worth exactly the review time it cost, which is a legitimate
   finding to write in the description.
2. **Add a missing instrument, not a claim.** A validator for an enum that lives in a
   comment, a CI job for the suite that has never run, a comparison between two lists that
   are hand-copied today (`CONCEPTUAL_DEBT.md` S4 is the easiest one in the repository).
3. **Write the failing test for a boundary you believe in.** The highest-value tests here are
   the ones that prove a guard is not vacuous. `apps/radiology_copilot/tests/test_screen.py`
   pairs every absence-check with a positive control — copy that shape.
4. Then, and only then, a feature.

Two rules about the craft:

- **Never let "green" be the evidence.** `scripts/validation/test-dashboard.py` once reported
  a pass while executing nothing, and twenty-eight of the repository's tests were counted in
  six documents that CI never runs. A gate that cannot fail is worse than no gate, because it
  buys confidence.
- **Line-neutral edits in the heavily cited files.** `DOMAIN_MODEL.md`, `SPECIFICATION.md` and
  `ARCHITECTURE.md` are cited by line number from many places. Adding a line silently shifts
  every inbound citation past it, and the checker only verifies that the target line exists
  and is non-blank. Insert at the end, or replace line-for-line.

---

## 5. Four traps, each of which has caught someone here

| Trap | What it looks like | What is true |
| --- | --- | --- |
| **The catalogue is not the capability.** | `SKILL_LIBRARY.yaml` has 121 skills with statuses. | Six are authorised. The other 115 are decisions about work nobody has approved — read them as a backlog in a formal shape. |
| **The chain is not walking.** | `routing.py` expands fallback chains transitively, cycle-safe, capped. | No configuration populates a fallback, so every chain is one long and `degraded` has never been true in a shipped deployment. The *policy* it enforces is real; the *machinery* is debt (`ADR-0002` says so). |
| **The ADR number is not the ADR.** | Five ADRs are cited 131 times as blockers and gates. | Only two exist. The references are promises, and `GOVERNANCE.md` §3 is the fix. |
| **The manifest is not the deployment.** | `configs/futurekind.yaml` lists tracing, search, crawler, vector and monitoring. | No process reads that file; it says so in its own header. `compose.yaml` is the deployment. |

---

## 6. Five questions to ask about the deployment you inherited

If any answer is "I'd have to ask someone", that is the work.

1. **Who signed the last AI-assisted report, and can you prove it from stored data?**
2. **Which model answered last Tuesday, and can a clinician see that without asking?**
3. **What would you produce, tomorrow, for a regulator who asked for everything the AI did to
   one named patient?** Not "what does the log say" — what is *retained*.
4. **Which refusals in the documents are enforced in code, and which are prose?** Count them;
   the ratio is the safety story's real strength.
5. **Who is the Clinical Authority for the specialty you are about to change, and did they
   agree?** If nobody exists, the honest state of your change is *blocked*, not *assumed*
   (`GOVERNANCE.md` G1).

---

## 7. How to disagree with this file

Open an issue and quote the sentence. If you disagree with §2, the bar is a working argument
that a hospital is *safer* having broken that rule, with the incident you have in mind. If
you disagree with §1, send a better week. If you disagree with §3, add a pointer, not a
tenth parallel document.

If you are right, the correct change is smaller than the argument that proved it.

---

**FutureKind Principle**

> You are not here to add intelligence. You are here to keep a hospital able to say, years
> later and in its own words, exactly what its machine did — and to refuse, on purpose and
> with a reason, everything that would make that sentence harder.
