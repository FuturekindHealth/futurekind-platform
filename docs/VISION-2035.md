# FutureKind Vision 2035

**Owns:** how a hospital works differently in 2035 because FutureKind exists — the workflow, not the
technology; what disappears, what becomes easier, what becomes safer, and what deliberately does
not change.
**Does not own:** the plan (`product/ROADMAP.md`), the family (`product/PRODUCT_BIBLE.md`), the
numbers (`business/COMMERCIAL_ROADMAP.md`), the rules (`CONSTITUTION.md`).
**Status:** a description of a state, written so that each claim can be checked in 2035 by someone
who was not here.

---

## 1. What this document refuses to be

No model names. No capability roadmap. No market size. Nine years of technology prediction would be
nine years of guesses, and the platform's founding decision was that the model is not the point:
the unit of clinical AI is a **skill** with a risk level, a policy and a human at the end
(`product/README.md:69-75`). This document describes a hospital, not a stack.

Every "today" here is cited; every "2035" is an intention whose mechanism is named.

---

## 2. The change, in one sentence

**In 2026 a hospital's AI problem is that nobody can say who wrote what; by 2035 the question has
gone strange, because every clinical document answers it itself.**

The reading is still done by a person. The decision is still made by a person. What stopped being
true is that *writing it down and proving afterwards who wrote it* costs the hours and the anxiety
it costs today (`product/README.md:64-66`).

---

## 3. What disappears

| Gone | What replaced it, today | Why it goes |
| --- | --- | --- |
| The transcription job | A clinician dictates and reviews | Drafting from speech is the one thing this class of model is genuinely good at (`product/PRODUCT_SPECIFICATION.md:259-260`) |
| Fourteen studio-specific AI paths | One boundary with a declared skill per act | Eighteen entry points and one governed path today (`integration/AI_ENTRY_POINTS_CARE_ERP.md:72-92`) is a temporary state; the platform's argument is not that AI is banned, it is that AI is *attributable* |
| "Which model did we use?" as a meeting topic | A policy per risk class, decided once by the operator | P7 and P16 already forbid the caller's choice; 2035 is simply the point where nobody remembers why it was controversial |
| The reconstruction after an incident | A query | Today provenance exists on the document and retention does not (`ARCHITECTURE.md:307`). Once ADR-0003 lands, the consultant-hours activity disappears first |
| The report that arrives after the patient has left | A measured p95 that people argue about with numbers | The latency target is aspirational and unmeasured (`product/PRODUCT_SPECIFICATION.md:243`) — the discipline of having a number is the change, not the number |
| The blank follow-up field | An interval that became a task someone owns | `DOMAIN_MODEL.md` now defines Recommendation, FollowUp and Task separately, which is what makes "nobody booked it" visible as a state rather than a memory |
| The department's structure list, living in one consultant's head | Profiles in the product | `profiles.py` already encodes "an MRI brain must account for these fourteen things". Institutional memory written down is the least glamorous and most durable artefact this family produces |
| The typist's name on a clinician's signature | An authenticated signer | Beta gate G1 is a hospital-side login, and it is the row in `SPECIFICATION.md:898-909` that most changes daily practice |

---

## 4. What becomes easier

- **Being the third reader.** A busy department head reviewing a colleague's report today must
  reconstruct why it says what it says. In 2035 the review opens with the dictation, the draft, the
  amendments and the checks, all attached. Peer review stops being an act of trust and becomes an
  act of reading.
- **Teaching.** A trainee sees, per section, what the department expects a study to describe — the
  profile on screen, not in a handbook. The same artefact that gates quality is the syllabus.
- **Referring.** The referring clinician reads a summary written by the person who saw the images,
  in words the patient can act on, and the letter carries the version it came from.
- **Adapting.** A new modality, a new grading system or a new country's identifier format is a
  profile, a prompt version and a policy row — not a fork. `architecture/APPLICATION_MAP.md` §2
  is the claim that this stays cheap; §6 is the warning that porting the checks is not automatic.
- **Recovering from an outage.** Today a dead model leaves a manual path and one honest line. In
  2035 that is unremarkable because it never stopped working that way: the product's resilience
  story is that nothing depends on the AI being available to do the thinking.

---

## 5. What becomes safer — and what becomes newly dangerous

**Safer, by mechanism:** certainty that cannot rise silently between draft and signature
(`unsupported_certainty`); measurements that must appear in what was dictated
(`unsupported_measurement`); a comparison that must name its prior or be refused
(`DOMAIN_MODEL.md`, Comparison); a section the human rewrote changing what the machine may
object to (`ARCHITECTURE.md:280-283`); and a signature that the system of record can refuse to
accept from a bot (`integration/INTEGRATION_CARE_ERP_PACS.md:252`).

**Newly dangerous, and this is the part a vision document normally omits:**

| Risk | Why it grows with adoption | The counter that must already exist |
| --- | --- | --- |
| **Deskilling** | A trainee who never writes a findings paragraph may never learn its structure | Profiles are shown as expectations, not answers; a training mode that withholds the draft until the trainee has typed their own — a design decision for the department, not a feature |
| **Automation drift** | A check that fires on 30 % of correct drafts gets ignored, and then the other 70 % are ignored too | Table 4's discipline as a standing measurement, not a one-off: severity is decided by measured cost (`product/ROADMAP.md` §4b) |
| **Metric gaming** | Once substantive-rewrite rate is a number people are appraised on, it becomes a number people manage | `product/UI_UX.md:235` already refuses reports-per-hour scoreboards and any AI-vs-human accuracy league table. That refusal is the 2035 safeguard |
| **Shared credentials at scale** | One login per department is convenient and quietly destroys every attribution claim | G1 is not a box-tick; it is the precondition of the sentence the product exists to say |
| **The ungoverned neighbour** | A better consumer model appears outside the hospital, on a phone | The answer is not a ban. It is that the governed path can prove who wrote what and the other one never will |

---

## 6. What does not change, by decision

1. **A human signs.** P3, P11. If 2035's technology makes that seem slow, the constitution is the
   place to argue, not the product.
2. **The reading is done by a person, and the AI drafts from what they dictate — not from the
   pixels.** `product/SKILL_LIBRARY.yaml:14-16` makes this the reason 121 skills need no vision
   capability. A future imaging model is a different product with a different safety case, not a
   setting.
3. **No hospital's data is anyone else's.** No federated learning, no cross-site benchmark, no
   vendor dashboard (`CONSTITUTION.md:344-348`). In 2035 this will look commercially
   self-defeating to somebody, and it will still be the reason a hospital trusts the installation.
4. **Nothing the AI produces is a decision, and no output is a diagnosis.** `README.md:236-237`.
5. **The platform stays one boundary.** A second way to reach a model is the failure this whole
   project exists to prevent, whether it arrives as an SDK convenience or a procurement shortcut.

If any of the five changes, it changes through a written amendment by the owner
(`CONSTITUTION.md:482-489`) — not through a feature that makes it easier in practice.

---

## 7. A Tuesday in the department, 2035

An imagined day, deliberately, with its numbers labelled as targets rather than results.

**07:50.** The queue is already ordered, and the ordering rule is visible on each row. Nobody has
typed a header. Twelve studies from overnight, two of them flagged by the acquisition check as
protocol-incomplete; the technologist's fix list is the same list.

**08:05.** The first brain MRI: the clinician dictates, the draft arrives in the middle of the
screen with the dictation still on the left, and one advisory says the mesial temporal structures
were not accounted for. They account for them, or say why they should not be. Two minutes.

**10:30.** A referral letter for a patient going to a district hospital is drafted from the signed
report and the problem list. The referring consultant changes one sentence and signs it. The letter
the patient carries is versioned, and the district hospital can see which report it came from.

**14:00.** The QA lead opens the weekly reading: substantive amendments per 100 reports, blocking
findings that turned out to be wrong, three cases where a follow-up interval was written and never
booked. She does not have to ask anyone to reconstruct anything.

**17:40.** Nobody types a report at home. That is the whole point, and it is the only number in this
section that will be easy to check in 2035.

---

## 8. What has to be true before 2035 is reachable

| By | What | Why it is the load-bearing one |
| --- | --- | --- |
| 2027 | The four decisions: approvals, retention, a Hospital identifier, citation | `SPECIFICATION.md:898-909` lists these as waiting on a decision rather than an action — the platform is not the constraint |
| 2027 | A measured baseline: dictation-complete to signed, from the ERP's own timestamps | Without it, "finishes reporting earlier" is a sentence about a product nobody timed |
| 2028 | Ratified cases per department — at minimum pathology, discharge and one ward document | All 100 golden cases today are imaging; thirteen applications have no evaluation |
| 2028 | Individual authentication in both studios | The sentence the product exists to be able to say |
| 2029 | Every authorised skill's `clinical_risk` confirmed by a named clinician, and every enforceable never-row enforced in code | Stage 3 multiplies the number of places an engineer's reasonable guess becomes hospital policy. The guesses are good tonight; they are not authorised (`CLINICAL_SAFETY.md` §2, `GOVERNANCE.md` G1) |
| 2030 | A second hospital that installed it from the documents, without a vendor in the room | `README.md:180` already names this as the definition of v1 |
| 2032 | A deployment can answer the seven conformance questions from stored evidence inside a day | This is the year the platform is either an institution with an audit trail or a drafting tool with a philosophy — the two branches are described in `BLUEPRINT.md` §1 |
| 2035 | The profiles and prompts of four departments, reviewed annually by clinicians | This is the actual accumulated asset — not code, and not a model |

**And the failure mode worth naming.** The likeliest 2035 is not a dystopia; it is a radiology
pilot that never left one department, running well, while eighteen other paths quietly became
twenty. A platform that stays useful to one service is a good tool and a failed thesis. The
difference between those two futures is decided by the three items in §8 dated 2027–2028, which are
conversations and a measurement, not engineering.

---

## 9. How to tell, in 2035, whether any of this happened

Three questions, each answerable without reference to the repository:

1. **Time.** Is a study's dictation-complete-to-signed interval shorter than the 2026 baseline, on
   the hospital's own timestamps, for the same case mix?
2. **Trust.** Would the reporting clinician's own family be reported in this department, on this
   system, with this audit trail — and can they name what the machine wrote?
3. **Proof.** For any sentence in any signed report, can the department produce who drafted it, who
   edited it, who signed it and what policy governed it — in under a day, two years later?

If the third answer is no, the first two do not matter. That is the order the roadmap has to keep.

*FutureKind · Genesis Night 3 · 2026-10-09. §7 is explicitly imagination. Everything cited as
"today" in this document was read from the repository or the integration record.*
