# Continuous Improvement Framework

Parts 6, 7, 9 and 13 of the sprint: the two loops that turn work into change, the longitudinal
questions that say whether any of it is improving, and the regression gates that decide whether a
change is allowed to ship.

The rule over all of it, from [`../INVARIANTS.md`](../INVARIANTS.md) N14 — "any automatic
optimisation of a clinical parameter: prompt, threshold, routing, severity" — and
[`../CONSTITUTION.md`](../CONSTITUTION.md) P13 (`docs/CONSTITUTION.md:316`, clinical truth is
traceable or labelled): **the loop proposes; a person decides.** In code, `loops.apply()` raises
`AutoApplyError` — the only function in the package that always fails — and that refusal is
mutation-proved ([`HANDBOOK.md`](HANDBOOK.md) §6).

---

## 1. Loop one: human edits to prompt change

The brief's seven steps, each against the symbol that performs it:

| Step | Symbol | What it does | State |
| --- | --- | --- | --- |
| Human edits captured | `edits.compare_documents`, `store.SessionRecord.edit` | Section-level diffs, hashes not text by default | C — needs a session |
| Edits classified | `loops.classify_edit_events` | Splits substantive from style-only, with the `is_substantive` reasons kept so the decision can be re-read | C |
| Patterns aggregated | same, keyed `(section, suggested error class)` | Aggregation is per section, because a prompt clause is per section | C |
| Ranked by harm | `loops.rank_harm`, `loops.mean_harm` | **Mean, not total.** A repeated cosmetic nuisance must not outrank two unsafe recommendations | M |
| Prompt improvements proposed | `loops.prompt_proposals` | One `ImprovementProposal` per pattern at `min_count`, naming the section instruction to review | C |
| Revalidated | `proposal.validation` | "re-run the frozen corpus: substantive-edit rate for this section must fall while blocking findings do not rise, on the same case mix" | C |
| Applied | — | **Refused.** `apply()` raises; the change happens in a commit a person writes | by design |

No step needs a spreadsheet. The brief's "no manual spreadsheets" is satisfied by the store, not by
a dashboard: everything above runs on a JSONL file outside the tree.

Two properties worth defending:

- A proposal carries `cases`, so the ranking can be re-derived from the underlying events rather
  than trusted.
- A proposal's severity language is a *hint for a human label*, and the code says so in its own
  `notes`. An automatic error label on a human edit is the beginning of a loop that applies itself.

## 2. Loop two: overrides to deterministic rule

| Step | Symbol | Note |
| --- | --- | --- |
| Override captured | `loops.override_events(audit_rows)` | Takes the paired golden audit rows: engine findings, faithful-or-probe flag, and what happened |
| Classified | same | Emits `false_positive` and `missed_pattern` events with a mapped class |
| Ranked | `loops.check_proposals` | Same mean-harm ordering as loop one |
| Rule proposed | `check_proposals(...)` | "adjust the rule's **scope**, not its severity: severity is set by measured cost" |
| Validated both ways | `proposal.validation` | Paired re-run over all 100 cases: newly blocked probes on one side, newly blocked **correct reports** on the other, both reported — one of them alone is a marketing number |
| Deployed | — | Refused here. A check ships as a commit to `quality.py`, with its measurement attached, which is gate G2 in [`../safety/CLINICAL_SAFETY.md`](../safety/CLINICAL_SAFETY.md) §6 |

This loop is the one that works today: `python -m evidence loop-state` reports `check_loop.available:
true`, measured over "9 checks, 100 faithful drafts, 310 probes", and names its own known cost in
the same output — "detection is 3 of 306 measurable probes, and one faithful report still blocks
(`E-03`)". The prompt loop reports `available: false`, because no clinician session has ever been
recorded.

**The asymmetry is the design.** A loop that can run on synthetic data keeps running; a loop that
needs a clinician says it is stopped rather than producing a plausible-looking number from nobody.

## 3. The improvement queue, ordered by harm rather than by volume

The ordering key is `(-harm_weight, -count, identifier)` in `loops._rank_key`, where the weight is
`mean_harm` — the harm *per event*, not the total. Volume enters only after severity is equal, so 40
style events rank below 2 unsafe recommendations.

`test_harm_weighting_orders_danger_above_volume` asserts both halves of that on the same data: the
totals *and* the means are true, and only one of them decides the queue. The rule is not a style
choice. [`../FAILURE-MODES.md`](../FAILURE-MODES.md) FM10 is the failure where a measurement becomes
a target, and a queue ordered by total events is exactly a target that rewards the noisy nuisance and
never reaches the dangerous rare case.

## 4. Regression: no improvement ships on its own claim

Part 13. `regression.compare(paired_rows, endpoints)` runs every gate over the *same* paired cases
and returns one exit code. Four gates, four endpoints, one rule per gate
([`METRICS.md`](METRICS.md) §3), plus two that make the verdict mean something:

1. **An inconclusive gate blocks.** Fewer than two paired observations yields
   `verdict="inconclusive: fewer than two paired observations"` with `passed=False`, and
   `RegressionReport.passed` additionally requires `comparable_pairs > 0`. Two locks, each
   mutation-proved.
2. **Every gate prints its own power.** A pass on twenty cases usually means "this study could not
   have detected anything", and the row says so.

Workflow and productivity get a **relative** tolerance (`TOLERANCE`, 10% of the baseline) because an
absolute one is meaningless: one second is nothing on a nine-minute report and everything on a
nine-second one. Safety and quality get none, because "worse but within 10%" is not a sentence anyone
wants to read in a release note.

## 5. Longitudinal: the four questions, and what confounds each

`longitudinal.four_questions()` returns the four claims a decade of use would want, each with its
metric, unit, required strata, confounders, and — as data — `measurable_today` and `why_not`. All
four are `false` today, with reasons that are not about the code:

| Question | Metric | Why it cannot be answered yet |
| --- | --- | --- |
| Is the product improving? | faithful-draft refusals, unannounced degradations, review seconds | no model has run and no clinician has been timed; the corpus is synthetic |
| Are the prompts improving? | substantive-edit rate per section against a *frozen* corpus | one prompt version has ever been executed, so there is no second point |
| Are the users improving? | edit rate by reporter, first 40 against next 40 | no per-person credential exists, so a reporter cannot be named (ADR-0004) |
| Are hallucinations decreasing? | clinically consequential labels per 100 cases, by detected class | labels need a clinician and a ratified case; audit volume is the only trendable term |

Three instruments guard the moment those become answerable:

- **`period_key` refuses a timezone-naive timestamp.** A series that mixes zones is a series with a
  bug in its x-axis.
- **`mann_kendall` refuses fewer than four points** and reports monotone tendency only, never a
  slope. A slope through three monthly points invites exactly the reading it cannot support.
- **`case_mix_drift` compares strata between periods with a chi-square-style statistic** from a
  printed table of critical values, because the most common false improvement in this product class
  is a change in which cases arrived. There is no decomposition, no ARIMA and no hierarchical model
  in this module: each would let a handful of points look like a finding.

And one rule above all: **a trend across a corpus change is not a result.** The corpus version
belongs in the series key — `scripts/validation/evidence/longitudinal.py:12` states it in the module
that would otherwise draw the line, and `reporting.AUDIENCES["research_team"]` states it again as the
note the research view travels with.

## 6. What would make this framework lie

- A proposal applied without a named person. `apply()` raises, so this requires deleting code — which
  is the point of the guard.
- A validation run whose corpus moved underneath it. The frozen-corpus rule in §5.
- A ranking by total events instead of mean harm (§3).
- An inconclusive gate reported as a pass (§4).
- A trend drawn from three points because the chart looked empty (§5).
- Editing a prompt to fix a measured failure without recording the version. The version is a
  clinical claim, and [`../GOVERNANCE.md`](../GOVERNANCE.md) owns the bump.

## 7. Drift check

The check that fails when this file drifts is `python -m evidence loop-state` — §2's quoted strings
are that command's own output, so a reworded refusal shows up as a diff against the printed JSON —
plus `test_apply_is_refused`, `test_harm_weighting_orders_danger_above_volume`,
`test_the_four_questions_name_what_they_cannot_answer` and the two regression fail-closed tests. The
quoted numbers in §5's table are `TrendQuestion.why_not` strings read from the code.
