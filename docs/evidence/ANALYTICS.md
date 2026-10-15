# Hospital Analytics Guide

Parts 10 and 12: what each reader sees, and how the same instruments behave at one centre, ten and
a hundred. Implemented in
[`../../scripts/validation/evidence/reporting.py`](../../scripts/validation/evidence/reporting.py).

---

## 1. Seven readers, seven questions, one dataset

`reporting.AUDIENCES` is the whole definition, quoted from the code rather than retyped:

| Audience | The question it is answered for | Must never see |
| --- | --- | --- |
| `radiologist` | Is this draft worth my time, and did I catch anything? | other reporters, per-case labels by colleague |
| `department_head` | Where is the reporting load, and is turnaround moving? | `case_ref`, typed characters by reporter |
| `medical_director` | Can I sign off that this is safe to use here? | `case_ref` — "the only view that answers a regulator; it is aggregate or nothing" |
| `quality_committee` | What reached a patient, and what did we miss? | `case_ref`, typed characters |
| `research_team` | Is this a finding or is this noise? | raw text, quasi-identifiers below k |
| `engineering` | What broke, how often, and what is the next fix worth doing? | raw text |
| `administration` | What did this cost, and what did we get? | `case_ref`, error classes, labels |

Two of the `must_not_see` rows are the ones people argue about, and the code already picked a side:

- The **radiologist** gets their own per-case labels and nothing about a colleague. The note attached
  to that view is `docs/FAILURE-MODES.md` FM10: individual feedback, not a league table.
- **Administration** gets cost and nothing clinical. A per-case error count in a budget paper is how
  a clinician ends up named in one.

## 2. What a "view" is, and what it is not

`view()` is a **filter, not a permission system**, and it says so in the note it stamps on every
result: *aggregate only; a view is a filter, not a permission system*. There is no authentication in
this repository to put behind it (ADR-0004 is still pending), so:

- The filter is there to make the least-privilege choice the default, and to make an over-broad
  request visible in review — not to defend a hostile session.
- Anyone who needs enforcement gets it from the Gateway's policy layer, which owns permission
  ([`../CONSTITUTION.md`](../CONSTITUTION.md) P16). An analytics tool that invents its own authorisation
  would be a second, weaker copy of the thing that already exists — the pattern
  [`../CONCEPTUAL_DEBT.md`](../CONCEPTUAL_DEBT.md) records as duplicated authority.

An unknown audience raises `KeyError` naming the seven; there is no default view, because a default
that shows everything is the discovery most analytics systems make after an incident.

## 3. Aggregation, and the two tables

- `table_1()` produces baseline characteristics over `modality`, `category`, `difficulty`, `site` and
  `role`, plus the distribution of `time_to_final_seconds`. A column nobody recorded is reported as
  *"not recorded — a data-collection gap, not a zero"*, which is the difference between an honest
  table and one that quietly invents a denominator.
- `results_table(records, success_field, denominator_field)` gives stratified rates with Wilson
  intervals and suppresses any stratum below `K_MIN`.
- `store.distribution()` reports n, mean, median, p25, p75, min, max. There is no standard deviation
  in the aggregate views, because a mean and an SD over a dozen reports of mixed difficulty is the
  summary most likely to be quoted as a claim.

## 4. The k-anonymity floor

`K_MIN = 5`, and it applies twice:

1. In `results_table`, where a stratum with fewer than five cases is suppressed rather than printed.
2. In `anonymise_check`, which counts `cells_below_k` across the quasi-identifier combination
   (`site`, `modality`, `study`, `category`, `difficulty`, `role`, `month`) before any export is
   written.

The second one matters more than it looks. A cell of one is not a privacy incident about patients —
it is one about the *reporter*. "MRI brain, rare, difficulty 5, consultant, October" can name a
single person's work in a department of eight. That is why the combination is checked as a whole and
why a thin cell produces `"refused: fix the offenders before writing any export"`.

## 5. Multi-site, and the principle that limits it

`centre_summary()` groups by `site`, reports each site's own rates with its own intervals, prints the
heterogeneity as a *spread of rates* and never a pooled effect, and says the reason in its own
`caution`: a between-site gap is case mix until a stratified analysis says otherwise.

What it may compare is limited by [`../CONSTITUTION.md`](../CONSTITUTION.md) P14
(`docs/CONSTITUTION.md:335`), and the limit is tighter than this sprint's brief assumed:

> Each installation is sovereign. No cross-hospital inference, no shared model of a patient, no
> platform-wide analytics that a hospital cannot see or refuse.

P14 names federated learning, **cross-site benchmarks** and vendor-side dashboards as forbidden
"until this principle is deliberately amended, not quietly eroded by a metrics field". So:

| Scale | Permitted today | Not permitted |
| --- | --- | --- |
| One installation | Its own rates over time, against its own baseline | Anything about "hospitals": one site is one case mix, and its average is not a product characteristic |
| Several sites **inside one hospital** | Stratified comparison of prompts, workflows, turnaround and label rates, case mix beside every one; the patient data stays where it was | Pooling for a single headline number |
| Several **hospitals** | Nothing at platform level. Each installation produces its own analysis, in its own store, and can see and refuse it | A cross-hospital benchmark, a shared model of a patient, or a vendor-side comparison — each of which needs an amendment decided under [`../GOVERNANCE.md`](../GOVERNANCE.md), not a field added to a metrics table |

Part 12 of the brief asked for a 1 / 10 / 100 hospital ladder. The honest ladder is the one above:
the instruments support the first two rungs, and the third is a governance question with an
instruments-shaped hole in it. **The unit of analysis at any scale is the centre, not the case** —
one clinician's hundred reports are not a hundred independent observations, and every per-case
p-value in this package must be read with that beside it.

**Patient data never moves between installations** (P14), and `centre_summary` says it in its own
`rule` field. The store's `site` field is a name for a place, not a pointer to its patients, and
`GroundTruthCase.source` records what a centre contributed to a case without carrying anything from
it.

## 6. Dashboards, and the ceiling they already have

The existing validation dashboard
([`../../scripts/validation/dashboard.py`](../../scripts/validation/dashboard.py)) keeps its stated
authority ceiling, which [`../INVARIANTS.md`](../INVARIANTS.md) N14 quotes as the platform's template:
it cannot nudge a draft, a prompt or a policy. This guide does not raise it.

What the evidence system adds is not a new dashboard but the layer underneath one: the store, the
audience definitions and the suppression rules. Whether a hospital wants a screen at all is a
department decision, and the one thing that should never appear on it is a per-reporter leaderboard —
`radiologist.must_not_see` is written so that the honest answer to "can we show this per person?" is
already in the code.

## 7. What each reader may conclude

| Reader | May conclude | May not conclude |
| --- | --- | --- |
| Radiologist | Where their own editing is concentrated | That a colleague is slower |
| Department head | Turnaround is moving, or is not | That a specific report was late because of a person |
| Medical director | Whether this installation can be signed off as safe to use | Anything about a patient |
| Quality committee | What reached a patient and what was missed | That a falling label rate is an improving product — audit volume is the confounder ([`IMPROVEMENT.md`](IMPROVEMENT.md) §5) |
| Research team | Whether a difference is distinguishable from noise | Anything about care, from an unratified corpus ([`GROUND_TRUTH.md`](GROUND_TRUTH.md) §4) |
| Engineering | What to fix next, in harm order | That a merged change is safe because the gate passed at n = 3 |
| Administration | What it cost | That cost is the point |

## 8. Drift check

The check that fails when this file drifts is the reporting block in `test_evidence.py`:
`test_seven_audiences_each_have_a_question_and_a_boundary` (seven, each with a question and a
`must_not_see`), `test_a_view_is_a_filter_not_a_permission`, `test_thin_cells_are_flagged_before_export`,
`test_centre_summary_refuses_to_pool_patients` and `test_csv_export_refuses_the_repository`. §1's
question strings and §4's `K_MIN` are read from `reporting.AUDIENCES` and the module constant, so a
reworded question makes that table wrong while the tests keep passing — which is why they are quoted
rather than paraphrased.
