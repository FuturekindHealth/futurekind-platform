# FutureKind Commercial Roadmap

**Owns:** which applications suit which way of selling, in what order a hospital buys them, what
each is worth and what it costs to serve, and the commercial things this family must not do.
**Does not own:** the unit economics (`../product/PRODUCT_SPECIFICATION.md` §5, which this applies
rather than repeats), the release shapes Alpha→Cloud (`:220-230`), the engineering sequence
(`../product/ROADMAP.md`), the family and its dependencies (`../product/PRODUCT_BIBLE.md`), what is
safe (`../safety/CLINICAL_SAFETY.md`).
**Status:** estimates, not measurements. §4 says which single input would change each one.

---

## 1. Six constraints that decide the shape, before any market talk

These are not preferences. Four are constitutional and one is arithmetic.

| Constraint | Source | Commercial consequence |
| --- | --- | --- |
| Local-first is the default posture, not an option | P7, `../CONSTITUTION.md:214-216`, `:47-48` | The customer owns the hardware. There is no hosted inference to resell |
| Federated learning, cross-site benchmarks and vendor-side dashboards are forbidden until the constitution is amended | `../CONSTITUTION.md:344-348` | **Multi-tenant SaaS analytics is not a product line; it is a constitutional amendment.** Nothing may be built or sold that presumes it |
| One AI boundary, no model selection by a caller | P16 | The sale is governance, not model choice. A customer cannot "pick GPT" through us |
| No cross-hospital data path; one installation per hospital | P14, and `../DOMAIN_MODEL.md:1267-1269` — *keep `Tenant` at zero occurrences* | Enterprise means **N installations with a contract**, not one database with N rows |
| No per-token cost in the local default configuration | `../product/PRODUCT_SPECIFICATION.md:156-161` | Usage-based billing would require trusting the hospital's own count, which the specification already rejects (`:189-195`) |

And the arithmetic: the platform is **Apache-2.0** (`LICENSE`, `README.md:234`). The code is not the
moat, and a roadmap that pretends otherwise is a plan to lose. What is scarce here is the reviewed
accumulation around the code — 121 skills with declared risk and approval, an evaluation corpus,
prompt versions, and the measured behaviour of both (`../product/ROADMAP.md` §4b) — plus the ability
to support a hospital at 4pm when the model is slow.

**The product proposition, in the specification's own words:** *FutureKind is where the hospital's
AI experiments stop being experiments* (`../product/PRODUCT_SPECIFICATION.md:186-187`). Eighteen
entry points and one governed path is not a greenfield; it is a consolidation sale.

---

## 2. The six motions

| Motion | What it actually is here | Who signs | What must be true first | Honest difficulty |
| --- | --- | --- | --- | --- |
| **On-premise, single department** | Today's shape: one installation, one radiology or ultrasound service | Department head with the hospital's IT | A real-model latency number, and the §4.2 afternoon. Both are one machine and one afternoon | **Low.** Two sites already operate the studios, Orthanc, OHIF and the ERP |
| **On-premise, whole hospital** | The same installation, more copilots | Medical director + IT | ADR-0005 and G1 identity, because more than one department means more than one signer | **Medium** — and the ADRs, not the screens, are the gate |
| **Enterprise, multi-site** | N installations, per-site policy variants, one skill library, contractual support | Group CIO/CTO | ADR-0007 (a Hospital identifier) — register row 8 of `../CONSTITUTION.md:544` says it is a *gap* today; SIEM export; capacity ceilings | **High.** This is the motion that needs a decision, not a feature |
| **Government / public hospitals** | Procurement into settings where patient data may not leave, and often cannot be hosted by a foreign vendor | Procurement + a state health authority | An audit trail that survives a records request (ADR-0003), a published intended-use statement (`README.md:236-237`), and a support SLA a department can call | **High, and the best fit for local-first.** The constitutional constraint is the differentiator here, not a limitation |
| **Academic / teaching** | A hospital that also researches: cohorts, de-identification, curriculum | Dean + ethics committee | `de-identification-review` `SKILL_LIBRARY.yaml:1579` and `cohort-extraction` `:1566` are both unusable until ADR-0007; research use needs a consent and retention policy the platform does not model | **High, and it is the motion that will ask first.** The answer today is "the governance is real, the research surface is not built" |
| **International** | Installations in other countries' hospitals | Local partner or the hospital itself | Language profiles per department (the golden set already names non-English and code-mixed dictation as an open gap — `GOLDEN_DATASET.yaml:1784`), local identifier formats, local regulation. **Per-country policy, never a fork** | **Medium-high.** The architecture supports it; the content does not exist |
| **"SaaS" / FutureKind Cloud** | Not hosted inference. Managed **skills and evaluation** — version, prompt, golden run — for hospitals that run their own box | Same as on-premise | The skill library under version control, and the evaluation harness as a service (`scripts/validation/`) | **Medium.** `../product/PRODUCT_SPECIFICATION.md:224-230` already caps it: *never a place patient text goes* |

---

## 3. Which application suits which motion

A copilot that produces a signed clinical document sells to a department head. A console sells to
an administrator. A surface sells to nobody until an identifier exists. That is the whole logic of
this table.

| Application | Single dept | Whole hospital | Enterprise | Government | Academic | International | Cloud/managed |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Radiology Copilot | **●** | ● | ● | ● | ● | ● | ○ skills |
| Pathology Copilot | ● | ● | ● | ○ | ● | ○ | ● |
| Physician / Emergency / Critical Care | ○ | ● | ● | ● | ● | ● | ● |
| Theatre Copilot | ○ | ● | ● | ● | ○ | ○ | ● |
| Discharge Copilot | ● | ● | ● | **●** | ● | **●** | ● |
| Coding Assistant | ● | ● | ● | ● | ○ | ● | **●** |
| Tumour Board | ○ | ● | ● | ○ | ● | ○ | ○ *(ADR-0005)* |
| Patient-Facing Text | ● | ● | ● | ● | ● | **●** | ● |
| Timeline (with audit view) | ○ | ○ | ● *(ADR-0007)* | ● | ● | ○ | ○ |
| Command Center | ○ | ● | **●** | **●** | ● | ● | ● |
| Clinical QA | ● | ● | ● | **●** | ● | ● | ● |

● = suits; ○ = possible but not the buyer's first reason. Note the two rows where **government** is
the strongest fit — Discharge and Command Center — because those are where an administrator's
obligations (throughput, records, accreditation evidence) and the local-first constraint coincide.

---

## 4. Value, difficulty, market and clinical impact — scored, and labelled as estimates

Scale 1–5, where 5 is best on value/market/impact and worst on difficulty. **Every score is a
judgement with one named input that would change it**; none of it is a measurement, because the
measurements this family needs have not been taken (`../safety/CLINICAL_SAFETY.md` register S2).

| Application | Value | Difficulty | Market size | Clinical impact | The input that changes the score |
| --- | --- | --- | --- | --- | --- |
| Radiology Copilot | 4 | 2 | 4 | 4 | Minutes per study saved, measured — the number the afternoon produces |
| Discharge Copilot | **5** | 2 | 5 | 3 | Whether the ERP's discharge record exists at all (`../architecture/APPLICATION_MAP.md` §7) |
| Coding Assistant | 4 | 3 | 4 | 2 | Payer mix, and whether a hospital's denials are actually recoverable |
| Clinical QA | 3 | 2 | 5 | 3 | Whether NABH evidence collection is today manual — if it is, this is the first paid product |
| Command Center | 3 | 4 | 4 | 2 | ADR-0007, and whether bed/TAT events are in the ERP |
| Pathology Copilot | 4 | 3 | 3 | 4 | Twenty ratified pathology reports. Its skill is already authorised and unused (`core/gateway/models.yaml:68`) |
| Emergency Copilot | 4 | 3 | 4 | **5** | A measured p95. Time-critical value and time-critical risk move together |
| Physician Copilot | 3 | 4 | 5 | 3 | Ward data, and whether residents are the buyer or the blocked party |
| Theatre Copilot | 3 | 4 | 3 | 4 | Whether the ERP holds implants and specimens as records |
| Critical Care Copilot | 3 | 4 | 2 | 5 | ICU flowsheet access; a smaller market, the highest consequence per document |
| Tumour Board | 4 | 3 | 2 | 4 | ADR-0005. Before it, this is a document with no defensible signature |
| Patient-Facing Text | 2 | 2 | 4 | 3 | Literacy assessment, and the PCPNDT and consent rules per country |
| Timeline | 4 | 5 | 3 | 4 | ADR-0007 only. It is the most wanted surface and the least buildable |

**Read the table by its bottom line, not its top:** the three highest value-per-difficulty rows are
Discharge, Clinical QA and Radiology — and two of them sell to an administrator rather than a
clinician. The clinical-impact column peaks at Emergency and Critical Care, which are the two with
the least measured evidence behind them. **That gap between what pays first and what helps most is
the central commercial fact of this family**, and it is the reason `../product/ROADMAP.md` §12
insists the safety gates run before revenue.

---

## 5. What to sell first, and what it costs to serve

Three things sell in this order, and none of them is a model:

1. **A governed boundary.** The customer already has eighteen AI entry points and one governed path
   (`../integration/AI_ENTRY_POINTS_CARE_ERP.md:72-92`). The first contract is consolidation:
   credentials, policy, provenance and one audit story, sold as risk reduction to whoever answers
   for a data request.
2. **Recovered clinician hours.** Named in `../product/PRODUCT_SPECIFICATION.md:172-187` as four
   places value appears; the sale needs one of them measured, which is a query against
   `radiology_studies` and a timed list, not a pilot.
3. **Defensibility, when it is real.** Provenance and per-section amendments exist today; retention
   does not. **This must be sold in the right order** — an installation that buys the audit story
   before ADR-0003 buys a promise. `../safety/CLINICAL_SAFETY.md` §8 is the sentence to put in front
   of a customer, not behind one.

Cost to serve, in the shape the specification prefers (`:189-195`): **a deployment fee plus a
support-and-model-update subscription.** What the subscription actually is: the skill library under
version, the golden reruns on every model change, prompt versioning, and a human who can say why
draft latency doubled. Per-seat pricing is rejected for the stated reason — it charges the
department for using the product. Per-study pricing is rejected because local-first means we cannot
count.

---

## 6. Non-revenue value that decides whether any of it is adopted

| Value | Who cares | Why it beats a feature list |
| --- | --- | --- |
| Reduced dependence on a locum or an outsourced reporting line | Department head | It is staffing, and staffing is a number in a budget |
| One reporting surface instead of four studio-specific hacks | IT | The maintenance argument alone funds an installation |
| A trainee who learns the department's structure because the screen shows it | Teaching hospital | And it is the same artefact as a profile, so it costs nothing extra |
| Records that answer a request without reconstruction | Administrator, medicolegal | Today that work is done by a consultant at an hourly rate |
| The hospital keeps its own data as a physical fact | Every Indian public-hospital procurement | Local-first is a compliance position, not a philosophy |

---

## 7. What this family must not do commercially

1. **No accuracy claims.** Not "95 % correct", not a leaderboard against human reports. The honest
   sentence is the intended-use one already published (`README.md:236-237`), and SPEC-09-03
   (`../SPECIFICATION.md:507-516`) makes an unearned capability claim a defect.
2. **No cloud analytics, no cross-site benchmarks, no vendor dashboard** — the constitutional
   prohibition, restated commercially because it is where a sales conversation will drift
   (`../CONSTITUTION.md:344-348`).
3. **No multi-tenant anything.** `Tenant` has zero occurrences and should keep none
   (`../DOMAIN_MODEL.md:1267-1269`). Enterprise is N installations.
4. **No billing model that requires counting at our end** (`../product/PRODUCT_SPECIFICATION.md:189-195`).
5. **No selling the golden set, the case files or any clinical text.** The evaluation corpus lives
   outside the repository by rule, and the phrase tables and case files have never held real human
   edits — they must not become a dataset to be licensed.
6. **No "AI reads the images" positioning.** Not one of the 121 skills needs vision, by design
   (`../product/SKILL_LIBRARY.yaml:14-16`). A pixel claim would be both false and the fastest way to
   lose a hospital that has read the safety guide.
7. **No sale of an application whose §6 safety gates are unmet.** A pilot whose failure is absorbed
   by the department that volunteered it is a bad contract, not a foot in the door.

---

## 8. Risks to the commercial model, in the order they would end it

| # | Risk | Early warning | Mitigation that is actually available |
| --- | --- | --- | --- |
| C1 | Real-model latency makes drafting slower than typing | p95 over 20 s for a report on the hospital's own hardware | The measurement itself, before any second department is promised anything |
| C2 | One hallucinated finding in a signed report | The first substantive rewrite accepted at draft time | Refusal gates, measured severities, and the honest claim in §5 of the safety guide |
| C3 | An installation's audit story collapses under a records request | The first legal ask, which will come before ADR-0003 | Sell retention as a gap, or do not sell defensibility yet |
| C4 | A competitor forks Apache-2.0 code and undercuts on price | Someone quoting the repository back at us | The moat is the accumulation: reviewed skills, ratified cases, measured severities, support |
| C5 | One person is both the clinical and the platform owner | `../SPECIFICATION.md:918-920` already names it: "one person's silence a dependency" | The §9 decisions below, made in writing with dates |
| C6 | Procurement in government settings demands certifications the platform does not hold | A tender document with a clause we cannot answer | Publish the intended-use statement, the security posture and the known gaps — `SECURITY.md` and the safety guide are the answer, not a slide |

---

## 9. Decisions for the owner, in commercial order

| # | Decision | Why nobody else can make it |
| --- | --- | --- |
| 1 | The three numbers: studies/month by modality, average reporting minutes today, cost of a late report | They set hardware tier and payback, and they live in the hospital's database |
| 2 | Whether defensibility is sold before retention exists | It is a promise about a gap |
| 3 | Which of the two hospitals is the reference site, and therefore which department's golden cases get ratified first | It chooses the second and third products for everyone |
| 4 | Whether a coding product may be sold to a payer-facing function at all | §6.4 of the Bible; a liability judgement |
| 5 | Whether Enterprise means "we support N installations" or "one hospital with a group contract" | It decides whether ADR-0007 is urgent or next-year |
| 6 | Price and licence posture for a public repository: what is free, what is paid, what is a service | Apache-2.0 has already answered part of it |

*FutureKind · Genesis Night 3 · 2026-10-09. Every score in §4 is an estimate with its swing factor
named, and no number in this document is a measurement of anything.*
