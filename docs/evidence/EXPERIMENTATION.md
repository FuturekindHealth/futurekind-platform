# Experimentation Guide

Part 8: A/B testing of prompts, models and quality rules, measured statistically. In
[`../../scripts/validation/evidence/experiment.py`](../../scripts/validation/evidence/experiment.py),
with the statistics in `evidence/stats.py`.

Everything here is **state C** — designed, tested against synthetic input, waiting for a real run.
No experiment has ever been executed by this project, because the two things an experiment needs are
a model that answers and a clinician who reviews, and neither has been available on this machine.

---

## 1. What may be tested, and what may not

| Variable | Testable this way | Constraint |
| --- | --- | --- |
| Prompt version | Yes | A prompt is clinical prose: the version bump rule and the authority to change it are owned by [`../GOVERNANCE.md`](../GOVERNANCE.md), not by the experimenter |
| Model alias | Yes | Only as an alias. ADR-0002 rule 1 keeps a model name out of any application-facing request, so the arm label is the alias and `Provenance.model` records what actually answered |
| Quality rule, scope or severity | Yes for **scope**; not as an experiment for severity | Severity comes from measured false-positive cost ([`../safety/CLINICAL_SAFETY.md`](../safety/CLINICAL_SAFETY.md) §6 gate G2), and a change to a threshold is a governance decision, not an arm |
| Which department's cases | No | That is a benchmark question, not an experiment ([`BENCHMARK.md`](BENCHMARK.md) §4) |
| Patient assignment | Never | The unit is the case, and cases are already made; nothing is randomised about a patient's care |

## 2. Allocation

`allocate(case_refs, arms, seed)` is deterministic and balanced: cases are hashed under a published
seed and each goes to the least-filled arm among the hash-ordered candidates.

Two properties were chosen on purpose:

- **Reproducible by a stranger.** Re-running with the same case list gives the same allocation, so a
  published study can be checked by someone who does not have the data.
- **Not tunable.** Balance is enforced *after* the hash, so nobody can search for a seed that gives a
  favourable case mix. The seed is published and the resulting mix is reported afterwards by
  `arm_summary`, which prints case mix beside the outcome — the two numbers a reader needs together.

`ARMS` is two. A third arm needs a different order-balancing rule and a different multiplicity
treatment; neither exists, and the module says so at
`scripts/validation/evidence/experiment.py:39` rather than pretending to scale.

## 3. Order, in a crossover

`crossover_order(case_refs, seed)` puts every case in both arms with the arm order alternating. This
matters more in this product than in most: reading a draft you wrote yourself is not the same task as
reading one a model wrote, so an unbalanced order makes "arm B looked better" and "arm B was usually
read second" the same sentence.

The offset that decides which order comes first is derived from the seed **once**, then order
alternates by case index. Per-case hashing looks more random and is not balanced: with 20 cases it
produced 9/11, which is exactly the imbalance a reader would later attribute to the intervention.
`test_crossover_balances_arm_order` is what stops that regression coming back.

## 4. Registration, and the refusal that makes it real

`stats.Preregistration` holds question, primary endpoint, comparison, unit of analysis, `n_planned`,
alpha, power, analysis, secondaries, exclusions and `signed_by`. `violations()` returns:

- `no owner: an unsigned pre-registration is a draft, and drafts get changed`
- `n_planned must be a number the study can actually reach`
- `a primary endpoint must be named before, not after`
- `alpha must be one of the tabled values, chosen in advance` (0.01, 0.05, 0.10)

`Experiment.analyse()` calls it first and returns `{"analysed": False, "problems": [...]}` when the
registration is incomplete. **That refusal is the feature.** An experiment with no pre-registered
primary endpoint can always be made to show something afterwards, and a measurement programme whose
outputs are always positive has stopped measuring
([`../FAILURE-MODES.md`](../FAILURE-MODES.md) FM8).

## 5. Analysis, chosen by the shape of the data

| Endpoint type | Test | Why this one |
| --- | --- | --- |
| Binary paired (accepted / blocked / labelled) | exact McNemar, `stats.mcnemar(b, c)` | Computed from the binomial "as-or-less-probable" tail, not a chi-square approximation. With 15 and 2 discordant pairs the exact p is 0.00235; an approximation would be a claim about arithmetic nobody checked |
| Continuous paired, n ≥ 10 | Wilcoxon signed rank, with the bootstrap percentile interval replacing its normal-approximation interval | The rank test keeps a single 40-minute report from dominating a mean; the interval comes from the resampled deltas because that is the quantity anyone would plot |
| Continuous paired, n < 10 | bootstrap only, and `wilcoxon_signed_rank` **refuses** | The approximation's own floor is 10, and it says so in its `caution` rather than producing a p-value that looks fine |
| Any rate | Wilson score interval | Wald gives an interval touching zero for 1 success in 10 cases — which is how a small pilot reports "no harm found" |

## 6. Multiplicity

Endpoints analysed beyond the registration get `multiplicity_warning`: the list of them, the Holm
step-down adjusted p-values, and the note "hypothesis-generating, and must be labelled that way in any
write-up". `holm` is monotone in its adjusted values, and a test enforces that, because an adjustment
procedure that can make a smaller p larger is not a procedure.

Nothing here Bonferroni-corrects a whole dashboard. The honest position is the one the registration
takes: **one primary endpoint**, and everything else is allowed to be interesting but not to be a
result.

## 7. Size, before the arm is built

`stats.mde_paired(n)` and `stats.sample_size_for_mcnemar(discordance, difference)` exist so nobody
discovers the size problem after the run. Measured 2026-10-09: a 20-case pilot detects a standardised
paired effect of 0.6265; a 15-point change in a paired binary outcome at 25% discordance needs 1,396
cases. `regression.compare` prints the MDE on every gate row for the same reason — a green light from
an underpowered gate is the expensive kind of false positive.

## 8. What a result means here

A significant difference between two prompt versions on a synthetic corpus is a result **about the
instruments**. It becomes a result about care only when the cases are ratified and a clinician was in
the loop ([`GROUND_TRUTH.md`](GROUND_TRUTH.md) §1), and the regression gate has run against it
([`IMPROVEMENT.md`](IMPROVEMENT.md) §4). Both halves are mechanical; neither is optional.

## 9. Drift check

The check that fails when this file drifts is the experiment block in `test_evidence.py`:
`test_allocation_is_deterministic_and_balanced`, `test_crossover_balances_arm_order`,
`test_unregistered_experiment_refuses_analysis` and `test_registered_binary_endpoint_analyses`. The
four quoted `violations()` strings are copied from `stats.Preregistration`, and the two size numbers
in §7 are the pinned outputs of `mde_paired(20)` and
`sample_size_for_mcnemar(0.25, 0.15)` — `test_the_detectable_effect_is_pinned_to_an_absolute_number`
and `test_sample_size_for_a_realistic_discordance_is_painfully_large` fail if either moves.
