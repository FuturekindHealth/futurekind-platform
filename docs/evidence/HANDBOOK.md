# Validation Handbook

How to run the instruments in [`../scripts/validation/evidence/`](../../scripts/validation/evidence/),
in the order that makes the results mean something. Written for the person who has to reproduce a
number for a hospital, a regulator or a paper — not for whoever wrote the code.

Nothing here needs a model, a GPU, a container daemon or a network. One thing does: the study
verbs take `--store`, and a store only exists once sessions have been recorded, which has not
happened yet ([`FRAMEWORK.md`](FRAMEWORK.md) §7). The verbs that need no data — `baseline`,
`taxonomy`, `groundtruth`, `selftest`, `loop-state` — run today, and they are the ones that print
the honest starting position.

---

## 1. Setup, and the two commands that say whether the instruments are alive

Python 3.12 or newer. The package imports the standard library and, in `baseline` only, PyYAML to
read the corpus this repository already ships.

```bash
cd scripts/validation
PYTHONPATH=. python -m evidence selftest     # expected: "9 of 9 evidence self-tests pass"
PYTHONPATH=. python -m pytest -q test_evidence.py   # expected: 71 passed
```

`selftest` is the one to run on a machine you have never used before: it carries known answers for
the Wilson interval and McNemar, so it detects a wrong statistic rather than a wrong assumption.
It exits non-zero when anything fails, and CI runs it on every push
([`.github/workflows/ci.yml`](../../.github/workflows/ci.yml)).

If either command cannot start, the two things to check first are the working directory (the
package is imported as `evidence`, so `PYTHONPATH` must reach `scripts/validation`) and whether
`futurekind_radiology` is installed — `test_evidence.py` imports the product's real check names on
purpose, because a taxonomy that maps an error class onto a check the product no longer runs is a
taxonomy that lies.

## 2. The verbs, and what each one refuses

| Verb | Needs | Prints | Refuses |
| --- | --- | --- | --- |
| `baseline [--markdown]` | the shipped golden dataset | composition share, dictated and reference words, measurements per case, probe counts, difficulty spread, four limitations | nothing — but it will not let the limitations be separated from the numbers: they are emitted in the same output |
| `taxonomy [--markdown]` | nothing | the 26 classes, their detectors and fix targets, plus engine coverage | a class without an observable or a detector |
| `groundtruth` | the shipped golden dataset | `ratified_and_valid`, `usable_as_evidence_about_care`, provenance spread | to call any of the corpus evidence about care |
| `selftest` | nothing | the count of known-answer checks that passed | — |
| `loop-state` | nothing | what each improvement loop can do today, and the measured cost of the one that can | — |
| `view --audience NAME --store FILE` | a session store outside the tree | that audience's aggregate, and the fields it must not see | an unknown audience, rather than defaulting to everything |
| `check --store FILE` | a session store | the anonymisation verdict and the between-centre summary | to print a clear verdict while an offender exists |
| `tables --store FILE --success FIELD` | a session store | Table 1 and stratified rates with Wilson intervals | a cell thinner than `K_MIN` — it is suppressed, not rounded |
| `figure --store FILE --metric NAME [--period P] [--svg]` | a session store | a trend series, each point carrying `n` | to draw a line through fewer than two periods |
| `regress --paired FILE` | a paired run, as JSON | four gates, each with its minimum detectable effect | to read an inconclusive gate as a pass |

`--store` paths are checked against the repository: a store inside a git working tree is refused
by `store.append()` and `reporting.write_csv()`, because a draft becomes patient text the moment it
is about a patient and this tree is public. Choose somewhere outside it, e.g.
`~/fk-evidence/session.jsonl`.

## 3. The order that makes a result mean something

1. `selftest`, then `test_evidence.py`. If the instruments are not green, every later number is
   decoration.
2. `groundtruth`. This decides what kind of claim is available at all: with
   `usable_as_evidence_about_care: 0.0`, only instrument claims are on the table.
3. `baseline --markdown`, redirected into the generated artefact, so the corpus description in the
   documents and the one the command prints cannot diverge:
   ```bash
   PYTHONPATH=. python -m evidence baseline --markdown > ../../docs/evidence/BASELINE.md
   ```
4. `taxonomy --markdown`, the same argument, into [`ERROR_TAXONOMY.md`](ERROR_TAXONOMY.md).
5. `loop-state`, which says what the improvement loops can and cannot do before anyone proposes a
   prompt change.
6. Only then, the study verbs against a real store.

Steps 3 and 4 are the rule against restating a moving fact: the documents hold the command's
output, not a copy of it
([`README.md`](../README.md) §10 rule 2, and [`CONCEPTUAL_DEBT.md`](../CONCEPTUAL_DEBT.md) D2 for
what happens when a count is typed into prose).

## 4. Reading a number out of this system

Four rules, all of them enforced somewhere in the code rather than only here:

- **Find the denominator.** Every rate in `reporting` carries its `n`. A percentage without an `n`
  was produced by something that had one; look for it before repeating it.
- **Find the state.** [`FRAMEWORK.md`](FRAMEWORK.md) §3's three states — measured, computable but
  unrun, not computable. `time saved` is state 2 and must never be quoted in state 1's tense.
- **Find the provenance.** `store.real_rows()` drops stub-model rows before anything is aggregated.
  A figure built from stub provenance is a figure about the test double.
- **Find the axis.** Six axes, no composite ([`METRICS.md`](METRICS.md) §5). "The score went up" is
  not a sentence this system produces, and if a document says it, the document is the defect.

## 5. What to do when a refusal fires

| Refusal | Means | Do |
| --- | --- | --- |
| `refusing to write an evidence store inside the repository` | the path is in a git tree | move the store outside; do not add an exception |
| `a record carries section text but --allow-text was not given` | clinical text was about to be stored silently | decide deliberately, then pass the flag, and expect `text_stored: true` in every export audit |
| `an evidence store must live outside the tree` (on read) | the same rule protects reading | move the file |
| `unknown audience` | a view was asked for that has no owner | add the audience with its question and its boundary, in `reporting.AUDIENCES` — never a default |
| `six axes stay six axes` | something tried to compute a composite | stop; the composite is the thing this project refuses on purpose |
| `prompts, checks, severities and thresholds change by a commit a person writes` | code tried to apply an improvement | read the proposal, then change the prompt in a commit yourself |
| `not enough periods to draw a line` | a trend was requested from one point | report the point, not a trend |

A refusal that fires is the system working. The failure mode is a refusal that no test can see,
which is why §6 exists.

## 6. Proving a refusal still refuses

`docs/safety/CLINICAL_SAFETY.md` §6 gate G3 requires "a check that the test fails when the path is
removed". For the evidence instruments that check is committed:

```bash
python scripts/validation/check-refusals.py          # 14 of 14 refusals proved
python scripts/validation/check-refusals.py --list   # what it would break
```

It applies each guard's removal to the working tree one at a time, runs the test that is supposed
to notice, restores the file, and reports any mutation that survived. It refuses to start over
uncommitted changes in the files it touches, and it proves a known-green baseline test before
breaking anything — a mutation "caught" by a test that was already failing proves nothing.

Run on 2026-10-09: 14 of 14, and the tree restored byte-identical. Two of those runs found real
gaps rather than confirming existing ones: the detectable-effect test compared only ratios, so any
constant in the power table passed, and the fail-closed safety gate's operative branch was not the
one its test appeared to cover. Both now have a test that can see them.

**CI runs it on every push** (`.github/workflows/ci.yml`, job `validation`). That is the right
home for it: the runner's checkout is clean by construction, which is the condition the harness
refuses to start without, and the tree is disposable afterwards — the two things a laptop has to
arrange for itself. A proof that only runs when someone remembers it is the
[`CONCEPTUAL_DEBT.md`](../CONCEPTUAL_DEBT.md) D13 defect wearing a better outfit.

**Adding a refusal means adding its mutation.** A guard without a row in `check-refusals.py` is a
guard that will silently rot the first time someone "simplifies" it.

## 7. Every number in this directory is reproducible

| Quoted as | Command | Measured |
| --- | --- | --- |
| 26 classes, 9 with an engine detector, 34.6% coverage | `python -m evidence taxonomy` | 2026-10-09 |
| 0 of 100 cases usable as evidence about care | `python -m evidence groundtruth` | 2026-10-09 |
| composition share median 0.9446, 0.23 measurements per reference report | `python -m evidence baseline` | 2026-10-09 |
| 71 evidence tests, 28 dashboard tests | `python -m pytest -q test_evidence.py test-dashboard.py` | 2026-10-09 |
| 14 of 14 refusals proved | `python scripts/validation/check-refusals.py` | 2026-10-09 |

## 8. Drift check

The check that fails when this file drifts is §1's pair of commands plus §6's harness: the counts
in §7 are the printed output of those commands on the date named beside each, which is the only
form a moving number is allowed to take here
([`README.md`](../README.md) §10 rule 2). If a reader runs §1 and the numbers differ, §7 is stale
and this file has no other claim on them.
