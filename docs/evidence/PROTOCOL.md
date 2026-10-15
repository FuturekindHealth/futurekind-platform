# Evaluation Protocol

The study design, written before the data exists, which is the only moment at which it can
genuinely control anything. Parts 1, 8 and 9 of the sprint; the numbers in §4 are computed by
`python -m evidence` instruments and were measured 2026-10-09.

**This protocol is not run yet, and nothing in it reports a result.** Its purpose is that when the
one afternoon in [`../product/ROADMAP.md`](../product/ROADMAP.md) §4.2 happens, the questions, the
endpoints, the sizes and the analysis are already fixed — so that the answer cannot be chosen after
the data is seen ([`../FAILURE-MODES.md`](../FAILURE-MODES.md) FM8).

---

## 1. The questions, in the order they can actually be answered

| # | Question | Primary endpoint | Whose decision is it |
| --- | --- | --- | --- |
| Q1 | Does a draft change what the radiologist types? | `human_typed_chars` per report | Product |
| Q2 | Does it change the report's clinical content? | clinically consequential labels per 100 cases (`E02`, `E07`, `E08`) | Clinical |
| Q3 | Does it change the time to a signed report? | `time_to_final_seconds`, median | Department |
| Q4 | Does it cost anything that was not there before? | false blocks (`E16`), unannounced degradations (`E20`), interruptions (`E18`) | Safety |
| Q5 | Do people keep using it? | continuation after one week, and the direct satisfaction question | The clinicians |

Q1 through Q4 are measurable with what exists once a session is recorded. Q5 needs neither a model
nor a statistic, only a decision repeated by a person who could have stopped.

## 2. Who participates, and what each contributes

Part 1 of the sprint asked which roles the framework must support. The study uses the same list, and
each role answers a different question — which is why `role` is on the record and why an unattributed
session is class `E22`.

| Role | Contributes | Can it ratify a case? |
| --- | --- | --- |
| Consultant radiologist | The signed report, the labels, the ratification | Yes |
| Senior registrar | Reviews under supervision; the editing behaviour of someone who has not yet settled a style | No |
| Resident / medical student | Where a draft misleads a less certain reader — the automation-bias population | No |
| Pathologist | The same instruments on a different document type; nothing transfers without its own benchmark ([`BENCHMARK.md`](BENCHMARK.md) §3) | For pathology cases only |
| Referring physician / medical director | Whether the report answered the clinical question asked | Yes, as `clinical_authority` |
| Technologist | Whether the AI path interrupted the work at the console | No |

The current record shape supports `role` and `actor_label` but not identity
([`FRAMEWORK.md`](FRAMEWORK.md) §7.4), so **resident-against-consultant comparisons are
state-2 in this study**: designable, not attributable.

## 3. The unit, the pairing, and the one thing that must not be dropped

The unit of analysis is **the case**, not the report section and not the keystroke. Every comparison
is paired on the same case, which is what makes `mcnemar` and `wilcoxon_signed_rank` the right tests
instead of two-sample tests on unequal case mix.

The study sheet must carry one column the instruments do not yet produce: **the human draft written
before the AI draft was seen.** Without it, Q1 cannot distinguish "the radiologist typed less" from
"the radiologist read more", and the difference is the entire product claim.

## 4. Sizes, computed before anyone asks for a pilot

`python -m evidence` prints these; they are the reason this section exists.

| Design | Value | Command |
| --- | --- | --- |
| Minimum detectable standardised paired effect at n = 20 | **0.6265** | `stats.mde_paired(20)` |
| … at n = 50 | 0.3962 | same |
| … at n = 100 | 0.2802 | same |
| … at n = 400 | 0.1401 — four times the cases for one quarter of the effect | same |
| Cases needed to see a 15-point change in a paired binary outcome, at 25% discordance | **1,396** | `stats.sample_size_for_mcnemar(0.25, 0.15)` |

Read the two rows together, because they are the decision the owner has to make:

- A twenty-case pilot can show a **large** change and nothing else. It is the right instrument for
  "does the workflow survive contact with a radiologist" and the wrong instrument for "is quality
  better". Its own regression gate prints this number beside every verdict, by design.
- A study that could detect a 15-point improvement in a refusal or acceptance rate is a **fourteen
  hundred case, multi-week, multi-centre** effort. That is not a pilot; it is the Evidence stage, and
  it is priced in [`EVIDENCE_ROADMAP.md`](EVIDENCE_ROADMAP.md) §3.
- A "no difference found" from twenty cases is not evidence of safety. It is the most expensive
  sentence in clinical software, and `mde_paired` exists to stop anyone writing it.

## 5. The first study, at the size that is actually available

Twenty cases, one consultant, one afternoon — the protocol already in
[`../product/ROADMAP.md`](../product/ROADMAP.md) §4.2, now with its endpoints fixed:

1. Sample by the department's own mix, not by convenience: the corpus's difficulty spread is
   7 / 25 / 29 / 25 / 14 across 1–5, so twenty cases drawn at random from it are mostly middling.
2. Register before running: `stats.Preregistration` requires question, primary endpoint, comparison,
   unit of analysis, n, alpha, power, analysis, and a `signed_by`. An unsigned registration is
   refused (`violations()` names it as a draft) and the experiment refuses to analyse.
3. Record the session in a store **outside the repository**; text stays out unless the
   `--allow-text` decision is taken deliberately ([`FRAMEWORK.md`](FRAMEWORK.md) §4).
4. Collect the human-draft-first column. Twenty of those make Q1 answerable for the first time.
5. Label what the reviewer changed with taxonomy codes. Two reviewers on the same ten cases, so
   `inter_reader` in the taxonomy stops being empty on all 26 classes — measured 2026-10-09, and
   it is the only number in this directory that a second clinician must supply before it can exist.
6. Analyse as registered. Any endpoint added afterwards is reported as hypothesis-generating, with
   Holm adjustment, by `experiment.Experiment.analyse()` — it appends that warning itself.

## 6. What this protocol will not do

- **No baseline-vs-best-ever comparison.** Paired against the same cases, or not at all.
- **No composite outcome.** Six axes stay six ([`METRICS.md`](METRICS.md) §5).
- **No claim about another department** from radiology data: all 100 cases are imaging, so thirteen
  applications start at zero ([`BENCHMARK.md`](BENCHMARK.md) §3).
- **No patient data between centres**, ever ([`ANALYTICS.md`](ANALYTICS.md) §5, P14).
- **No conclusion from an inconclusive gate.** The regression gate fails closed at n < 2, and the
  refusal is mutation-proved.

## 7. Drift check

The check that fails when this file drifts is `python -m evidence selftest` plus
`test_the_detectable_effect_is_pinned_to_an_absolute_number` and
`test_sample_size_for_a_realistic_discordance_is_painfully_large` in `test_evidence.py`: §4's four
values are those tests' known answers, computed rather than remembered. If `mde_paired` or
`sample_size_for_mcnemar` changes, the tests fail first and this table becomes the thing that has to
be re-run.
