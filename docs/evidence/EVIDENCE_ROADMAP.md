# FutureKind Evidence Roadmap

Part 12 of the sprint and the last file in this directory: the order in which the evidence actually
gets built, what each step costs, and which decision it unlocks. This does not replace
[`../product/ROADMAP.md`](../product/ROADMAP.md) — that owns the product sequence. This owns the
question *what must be true before FutureKind may say it helps*, and every step below is priced in
human hours rather than sprints, because that is the only currency these steps use.

---

## 1. The one dependency every step shares

The instruments exist; the inputs do not. So the first constraint is not engineering:

| Missing input | Blocks | Who can supply it | Cost |
| --- | --- | --- | --- |
| Ratified cases | Every claim about care — gate G1 (`docs/safety/CLINICAL_SAFETY.md:136`) | A consultant with twenty files and an hour | one afternoon, no code |
| A model that answers on the clinic's machine | Every latency, refusal and draft-quality number | The owner: the deployment that has LiteLLM and a provider key | one machine, one key |
| A session producer | The store has no writer (`../FRAMEWORK.md` §7.1) | Engineering, after the afternoon exists to shape it | one small, tested bridge |
| Per-person identity | Attribution, inter-reviewer agreement, anything about *who* | ADR-0004, which is still pending | a deployment decision, not a feature |

Two of these are the owner's to unlock and cannot be written into code by anyone here.

## 2. The steps, in order

| # | Step | Cost | What it unlocks | What proves it happened |
| --- | --- | --- | --- | --- |
| E1 | Ratify twenty MRI brain cases that already exist | One consultant-hour | Moves radiology from rung 1 to rung 2 in [`BENCHMARK.md`](BENCHMARK.md) §4 | `evidence groundtruth` prints `ratified_and_valid: 20` |
| E2 | Run the twenty-case session on the clinic's own machine, with the human-draft-first column | One afternoon, one clinician | The first state-M numbers about *work*: review seconds, typed characters, substantive edits | A store outside the tree, and `evidence tables` over it |
| E3 | Bridge `run-cases.py session` rows to `SessionRecord`, with timestamps captured at the harness | Half a day, with tests | Turns the instruments from designed into used | A test that a session row converts without inventing a stamp |
| E4 | Retention, or a deliberate decision not to have it (ADR-0003) | A governance decision | Whether any of this survives the browser tab. Until it lands, `E23 unretained` is the honest class for every claim about defensibility | A signed line in an ADR, in either direction |
| E5 | One pre-registered A/B — prompt version, or alias — sized at what the instruments can detect | One experiment, run twice | Whether the loop in [`IMPROVEMENT.md`](IMPROVEMENT.md) §1 closes on real data | `Preregistration.signed_by` set, `analysed: true`, one endpoint marked primary |
| E6 | The paired regression gate on every release | Zero marginal cost once E3 exists | "Nothing got worse" becomes a checkable claim instead of a feeling | The gate row in a release note, with its MDE printed beside it |
| E7 | Ratify twenty cases in a second department | Another consultant-hour, elsewhere | A second benchmark rung-2, and the first evidence that the platform is not one department wearing a costume | The same command, a different specialty |
| E8 | Longitudinal reporting that a department reads | One period boundary, then patience | The four questions in [`IMPROVEMENT.md`](IMPROVEMENT.md) §5, from state C to state M | `evidence figure` with at least four periods and `case_mix_drift` attached |

E1 and E2 are the same afternoon. That is the whole finding of this roadmap: **the distance between
 tonight's instruments and the first real number is one consultant, one machine and one hour of
 someone else's calendar.** Nothing in steps E1–E2 requires a line of code.

## 3. Sized properly, when the pilot is not enough

E2 answers "does the workflow survive contact with a radiologist". It cannot answer "is quality
better", and the arithmetic is in the instruments rather than in an argument:
`mde_paired(20) = 0.6265` and a 15-point change in a paired binary outcome at 25% discordance needs
**1,396 cases** (`stats.sample_size_for_mcnemar(0.25, 0.15)`).

So the multi-case study is a separate decision with three inputs nobody has yet:

1. Several clinicians, so reporter effects are not confounded with the intervention.
2. The same corpus frozen across arms ([`IMPROVEMENT.md`](IMPROVEMENT.md) §5).
3. An analysis unit that is the centre, not the case, once more than one site contributes
   ([`ANALYTICS.md`](ANALYTICS.md) §5, and P14 at `docs/CONSTITUTION.md:335` on cross-hospital work).

At 1,396 paired cases, a single department reaches this in months, not weeks. That is worth knowing
before promising a paper rather than after.

## 4. What is deliberately *not* scheduled

- **More instruments.** Fifteen modules with no producer is already ahead of the data. E3 is the
  only code in this list, and it is deferred until the afternoon shapes it.
- **A cross-hospital benchmark.** P14 forbids it until amended deliberately
  ([`BENCHMARK.md`](BENCHMARK.md) §6).
- **Confidence, trust or usefulness as engineered proxies.** Each would be a state-N number wearing
  state-M clothes ([`METRICS.md`](METRICS.md) §2, §6).
- **A tenth quality check to close the E02 gap.** Measured and refused in
  `docs/product/ROADMAP.md` §4.1; the human remains the check.
- **A dashboard for the evidence.** The existing validation dashboard keeps its authority ceiling
  ([`ANALYTICS.md`](ANALYTICS.md) §6). A screen is the last thing this needs, not the first.

## 5. The sequence, if only one step happens

If nothing else in this file is ever done, **do E1 and E2.** Twenty ratified cases and one afternoon on
the clinic's machine turn the entire directory from "designed" into "measured", and every number in
[`FRAMEWORK.md`](FRAMEWORK.md) §1 that is currently state C moves with them. Everything else — the
A/B, the longitudinal series, the second department, the paper — is downstream of that single
afternoon, which is why [`../FIRST-WEEK.md`](../FIRST-WEEK.md) tells a new engineer that the most
valuable thing they can do in their first month is arrange it.

## 6. Drift check

The check that fails when this file drifts is `python -m evidence groundtruth` for E1's target number
and `python -m evidence baseline` for the corpus figures; the two statistics in §3 are the pinned
outputs of `stats.mde_paired` and `stats.sample_size_for_mcnemar`, asserted by
`test_the_detectable_effect_is_pinned_to_an_absolute_number` and
`test_sample_size_for_a_realistic_discordance_is_painfully_large`. The "no producer" claim in §1 is
re-checkable with `grep -rln --include=*.py "from evidence" apps core scripts`, which today returns
one file: the package's own tests.
