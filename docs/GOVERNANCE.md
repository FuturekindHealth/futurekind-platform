# FutureKind Governance

**Who decides, who may not, and what the project owes the world outside its author.**
Genesis Night 4, 2026-10-09.

| | |
| --- | --- |
| **Owns** | Decision rights, the clinical veto, the amendment machinery, the open-source strategy, the path to a foundation. |
| **Does not own** | The principles being governed ([`CONSTITUTION.md`](CONSTITUTION.md)), the pricing and motions ([`business/COMMERCIAL_ROADMAP.md`](business/COMMERCIAL_ROADMAP.md)), the refusals ([`INVARIANTS.md`](INVARIANTS.md)). |
| **Measured starting point** | `CONTRIBUTING.md` exists; there is no `CODE_OF_CONDUCT.md`, no CLA, no trademark policy, and **no file in this repository contains the word "foundation"** (checked across all tracked markdown). Governance is not weak here — it is unowned. |

---

## 1. The seat problem, stated plainly

Every decision in this repository is currently taken by one person, who is simultaneously
platform owner, architect, product manager, security reviewer and — by default — the
clinical authority. That is the correct structure for stage 1 and the principal risk for
stages 3 and 4 (`FAILURE-MODES.md` FM2, FM6).

The problem is not the person. It is that **an empty seat is never left vacant: the nearest
discipline fills it.** With no clinician present, an engineer's estimate of clinical risk is
what `models.yaml` contains, and it is recorded as though a clinician had chosen it. The
repository is honest about this — `GOLDEN_DATASET.yaml:56` labels its pass thresholds "for
the clinical owner to set" — but honesty about an empty seat does not fill it.

So governance here has one job: **name the decisions that must wait, and make the waiting
visible.**

---

## 2. Four seats

| Seat | Holds | May decide | May not decide |
| --- | --- | --- | --- |
| **Platform Owner** (one person today) | The constitution, ADRs, the merge, the trademark if one exists. | Amendments by ADR; scope; whether a skill is authorised; whether to accept a hospital. | A clinical risk level, a pass threshold, a case ratification, or the meaning of a clinical word. |
| **Clinical Authority** (named per specialty; **vacant today**) | The medicine. | `clinical_risk` per skill, the never-rows that bind care, golden-case ratification, the document shape and house style, pass thresholds, and any prompt change that touches a prohibition. | Implementation, storage choice, deployment topology. |
| **Hospital Operator** (per site) | The building's trust. | The credential per application, which skills that site enables, the retention period within law, who may see `/models`, incident contact. | The platform's rules; the prompt; the catalogue's policy defaults. |
| **Contributor** | Code, documents, proposed skills. | Anything that does not move a clinical boundary. | A new public request field (`SPEC-12-06`), a new refusal, a severity change. |

> **Rule G1 — the clinical veto.** A change touching any of the four items in the Clinical
> Authority's "may decide" column cannot be merged on engineering reasoning alone. If no
> Clinical Authority exists for that specialty, the change is *blocked*, not *assumed*. This
> is the only genuinely new mechanism in this file, and the cheapest: a named line in the
> PR template, not a committee.

> **Rule G2 — segregation of duties.** Whoever authors an evaluation case may not ratify it.
> Tonight this is satisfied by nobody having ratified any: all 100 cases are
> `authored_by: engineering` and `ratified: pending`. The rule prevents the moment when the
> first case is signed by its own author because it was expedient.

> **Rule G3 — an unowned decision is announced as unowned.** Any document may record a
> decision as *owed* (with the seat named), and may not record it as *made* without the
> seat's owner. The five named-but-unwritten ADRs are the current test of this rule, and
> §5 fixes the mechanism rather than blaming the symptom.

---

## 3. The amendment path, and what it must not become

`CONSTITUTION.md` §6 already requires: owner only, via a written ADR, stating which
principle conflicted with which real requirement, what was tried under the existing
principle first, and what protection replaces the relaxed one — with P2, P4, P11 and P13
never tradeable. That is a good rule and needs no amendment.

What it lacks is a **queue**. Today an amendment request exists only as a prose reference.
The addition is procedural:

1. One file per decision owed: `ADR-0003` retention, `ADR-0004` identity, `ADR-0005`
   approval, `ADR-0006` multi-site, `ADR-0007` the Hospital identifier. **Status: named, not
   written**, each carrying the question, the seat that answers it, and the gate it blocks.
2. A reference in any document may cite an ADR only if the ADR exists **or** the citation
   resolves to that named-not-written index. After that, `grep` for the ADR id finds the
   decision, not a mystery.
3. Superseding is allowed and normal; silently contradicting is a defect. An ADR that stops
   being true gets a successor and a `Superseded by` line, not an edit.

> **Rule G4 — no dangling authority.** This closes 131 references at the cost of five stub
> files, and it is the highest value-per-line item in Night 4's deletion list
> (`CONCEPTUAL_DEBT.md` S10).

---

## 4. Open-source strategy

### 4.1 What the licence actually buys

Apache-2.0 with a patent grant, and no copyleft. The consequence, stated once:
**anyone may take the code and withhold their changes**, including changes to a safety
check. FutureKind's answer is not a licence change — the permissive licence is the
distribution strategy — it is the choice of what to put where.

### 4.2 Always free, and never proprietary

Not "free as in beer". These must remain readable by a person who is not a customer,
because a clinician's safety depends on them:

- The **prompt text** and its version rules. A patient's record was drafted by words someone
  must be able to read.
- The **quality check list**, its severities, and the measured cost of each. A proprietary
  safety check is a contradiction.
- The **golden-case format** and any published corpus. Reproducibility is the whole
  evidentiary claim.
- The **vocabulary** (`DOMAIN_MODEL.md`), the **never-list**, and the **audit record's
  shape**. Interoperability of *evidence* is a public good; a hospital that switches vendors
  must keep its own history legible.
- The **Gateway's policy semantics** — the file format of `models.yaml`, not its contents.

Paid layers are allowed to be closed or hosted, and are services rather than withheld
safety: retention infrastructure at scale, evaluation as an annual service, deployment
certification, integration build support, and the operational contract. The distinction is
one sentence long and it is the test to apply to every future pricing proposal:

> **A paid tier may add a service. It may never move a threshold, soften a refusal, or hide
> a check.**

### 4.3 The conformance problem, and the only cheap answer

Apache-2.0 permits a fork that keeps the name and drops the refusals. Without trademark
enforcement — which a single maintainer cannot fund — the only enforceable instrument is
technical and it is small:

> A **conformance checklist** published in the repository: seven questions a deployment must
> answer from its own data (which skill was requested, which alias, which model answered,
> who was authenticated, what was blocked and why, who signed, and can all seven be produced
> two years later). A deployment that answers them from stored evidence may say it is
> FutureKind-conformant. One that cannot, cannot — and the test is public, so a buyer can run
> it.

That converts a licence argument into an evaluation, which is the platform's native
strength (`BLUEPRINT.md` §6, verdict 8).

### 4.4 Contributor ladder, kept deliberately small

`CONTRIBUTING.md` has principles and a checklist; it has no path from stranger to trust. The
minimum credible version: **Contributor** (proposals, docs, fixes) → **Member** (a merged
change of any kind, then review rights on non-clinical code) → **Maintainer** (owns a
component, not a person-count). Skill proposals already have an issue template; what is
missing is the sentence saying who accepts one and against which gate. Nothing here needs a
CLA: a Developer Certificate of Origin on commits is the standard, lighter, and matches
Apache-2.0's patent grant.

### 4.5 A foundation: when, and for what

No entity is mentioned anywhere in this repository today. The honest proposal:

| Trigger | Why that trigger | Form |
| --- | --- | --- |
| First external maintainer with review rights | Ownership of the merge becomes a question someone else must answer. | A legal entity holding the trademark and the domain; a two-person board with a clinical seat. |
| First hospital that is not the author's | Retention, incident contact and a liability answer need an addressee. | Same entity; no change of licence. |
| First paid deployment | A vendor cannot also be the neutral auditor of its own safety claims. | Split: foundation holds the specification, conformance checklist and corpus; a services company sells deployment. The split *is* the assurance product. |

**Anti-goals.** No open-core that withholds safety. No foundation before the first external
maintainer, because a legal entity with one member and no community is paperwork, not
governance. No CLA, no contributor licence assignment — it transfers rights the contributor
should keep and scares exactly the people this project needs.

---

## 5. Multi-site governance: what must exist before hospital #2

Not a roadmap — a precondition list, because each item is a governance question that a
second site converts into an incident.

1. **A `Hospital` identifier** (`ADR-0007`). Without it, "cross-hospital data path" (P14) is
   unenforceable: there is no subject to scope the prohibition to.
2. **A per-application, per-site credential** (`ADR-0004`). One shared key across two
   hospitals means one hospital can read the other's spend and inventory.
3. **A retention period, named, per site** (`ADR-0003`) — with the answer to "who can see it,
   and who can destroy it".
4. **A named Clinical Authority per specialty** (G1), not one for the whole platform: risk
   tolerance differs between departments and the catalogue must be able to say so.
5. **An incident path**: `SECURITY.md` describes reporting; nothing yet describes a *clinical*
   incident, its triage, or who tells the affected patient. That is `CLINICAL_SAFETY.md` §7's
   job, and it needs an owner outside engineering.

---

## 6. Tripwires

The constitution's three (§6) plus two from this sprint. All five are greps or CI jobs, so
governance does not depend on anyone remembering to read a document.

| # | Tripwire | What it means when it fires |
| --- | --- | --- |
| T1 | A `model:` or `provider:` key appears in any request schema. | N1 has already been conceded in a corner of the codebase. |
| T2 | Anything other than `core/gateway` accepts a completion request. | The single AI boundary (P16) is gone, and with it the audit claim. |
| T3 | A principle has no ADR beneath it while a feature does. | The constitution has become commentary. |
| T4 | **A new document names no check that fails when it drifts.** | It is a restatement, and restatements rot (`CONCEPTUAL_DEBT.md` §2.1). |
| T5 | **A number appears in prose that is neither generated nor dated.** | It is already wrong somewhere (`FAILURE-MODES.md` FM8). |

---

## 7. The governance calendar, which is one line

Quarterly, against this file only: are the four seats filled; did any G1-class change merge
without a clinician; are the five named ADRs still unwritten; what did the register in
`CONSTITUTION.md` §7 and `CONCEPTUAL_DEBT.md` gain or lose. Thirty minutes, and the whole
mechanism.

---

**FutureKind Principle**

> Governance is not who approves a pull request. It is the guarantee that a clinical
> decision cannot be made by accident, by the only discipline in the room, on a Tuesday,
> because nobody was waiting for it.
