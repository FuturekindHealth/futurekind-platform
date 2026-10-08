# FutureKind Conceptual Debt

**What this repository repeats, contradicts, and cannot check.** Genesis Night 4, 2026-10-09.

| | |
| --- | --- |
| **Owns** | Debt of *ideas*: duplicated concepts, duplicated vocabulary, duplicated authorities, hidden coupling, placeholders standing in for decisions. Ranked, with the evidence that made each row real. |
| **Does not own** | Implementation sequence ([`product/ROADMAP.md`](product/ROADMAP.md)), principle violations ([`CONSTITUTION.md`](CONSTITUTION.md) §7), naming rulings ([`DOMAIN_MODEL.md`](DOMAIN_MODEL.md)). |
| **Difference from §7** | The constitution's register lists *violations of rules*. This lists *structures that make the next violation easy to write*. A row here is not a failure; it is a loaded gun. |
| **Method** | Every row was measured tonight against the tree. `path:NN` citations are ones the author ran, not inherited. |
| **Drift check** | This is the file's own instrument: each row names the command that measured it, so the register can be re-run rather than re-believed. It goes stale in the opposite direction from the others — a *closed* row must be deleted, not left as history, or the register becomes a list of things once true. |

Nine kinds, one test each. A row earns a place only if the test is answered with a
command or a file.

| Kind | The test |
| --- | --- |
| **Restated number** | Can the number move without any gate failing? |
| **Two authorities** | Is there a second copy of the same contract that nothing compares? |
| **Placeholder authority** | Does a live sentence depend on a document that does not exist? |
| **Unfalsifiable citation** | Can a contributor on a clone check the evidence? |
| **Vocabulary leak** | Does a banned synonym appear in the shipped interface? |
| **Dead mechanism** | Can the current configuration ever execute this path? |
| **Hidden coupling** | Does a change in one component silently land on another? |
| **Prose-as-config** | Is there a file that reads like configuration and is read by nobody? |
| **Description surplus** | Does the documentation out-number the enforcement it describes? |

---

## 1. The register

Severity is not "how bad the code is". It is **who is misled, and in which direction.**
`Misleads-a-clinical-decision` > `Misleads-an-architecture-decision` > `Wastes-a-reader's-time`.

| # | Finding | Kind | Evidence, measured | Severity |
| --- | --- | --- | --- | --- |
| **D1** | **Five ADRs are cited as authority and do not exist.** ADR-0003 (retention), 0004 (identity), 0005 (approval), 0006 (multi-site), 0007 (identifier) are referenced **131 times** across tracked markdown (0005 alone 55); `git ls-files docs/adr` returns two files. | Placeholder authority | Measured with `grep -o` over every tracked `.md` | **Highest.** Whole gates — Beta, the clinical apps, the research motion — are *scheduled behind an argument that has not been written.* A reader cannot tell a deferred decision from an omitted one. |
| **D2** | **Counts are restated in prose and were already wrong.** `ARCHITECTURE.md:304-305` 492/255, `product/README.md:46` 775, `CHANGELOG.md:193` 775 **and** 407 citations, `SPECIFICATION.md:929` said 482, `DOMAIN_MODEL.md:1207` said 380. The checker prints its own total on every run and nothing recomputes the prose figure, which is how `CHANGELOG.md:193`'s "407" became a historical artefact within one sprint — including this row, which deliberately quotes no current count. | Restated number | Two of five test-count sites were stale before tonight's fix (corrected in `52bf45f`); the citation figure is a fresh measurement | Misleads-an-architecture-decision. Six documents can be wrong from one `pytest` run, and one of them is the release record. |
| **D3** | **`configs/futurekind.yaml` is 85 lines of configuration that no code reads** and says so at `:3-8`. It advertises `search: SearXNG`, `crawler: Crawl4AI`, `tracing: planned`, `vector: Qdrant`; `compose.yaml` starts postgres, redis, litellm, gateway, openwebui, qdrant and one network. | Prose-as-config | `grep -rn futurekind.yaml` outside `docs/` → one comment in `core/gateway/pyproject.toml:13`. CI only parses it for YAML validity | Wastes-a-reader's-time, rising: a filename ending in `.yaml` under `configs/` is read as truth by everyone who arrives. |
| **D4** | **The Gateway's fallback machinery has no fallback data.** `routing.py:175-215` expands chains transitively, cycle-safe and capped; `service.py:176` walks them and `:58` defines `OUTCOME_FALLBACK`. **No `fallbacks:` key exists in any YAML in the repository** (measured), so every chain is length one, `degraded` (`service.py:448`) is always false, and the fallback outcome is unreachable in shipped configuration. | Dead mechanism | `grep -rn fallbacks --include='*.yaml' .` → no output | Misleads-an-architecture-decision. `ADR-0002:126` already admits the overlap with LiteLLM retries as debt; the sharper fact is that the code path guarding the "silent substitution" promise (P13) has never once run with more than one candidate. |
| **D5** | **The application re-implements the boundary instead of referencing it.** `apps/radiology_copilot/src/futurekind_radiology/gateway.py:32-49` re-declares thirteen fields of the Gateway's response with `extra="ignore"` (`:35`), and loosens two types: `policy: dict[str, Any]` (`:43`) vs `SkillPolicySchema`, `usage: dict[str, int]` (`:48`) vs `TokenUsageSchema`. `copilot.py:69` re-types the four policy field names as a literal tuple. | Hidden coupling | Read directly | **Misleads-a-clinical-decision.** A Gateway field rename makes the copilot read `None`/absent silently rather than fail — the exact "the check passed because it stopped looking" shape. The app compensates with a runtime presence test (`copilot.py:98`), which is a good guard for four names and no guard for thirteen. |
| **D6** | **One document shape lives in five lists.** `report.py:30` `SECTION_KEYS` — whose own comment says "This tuple is the authority" — `:48` `MODEL_SECTION_KEYS`, `:53` `REVIEWER_EDITABLE_SECTIONS`, then `scripts/validation/run-cases.py:59` `EDITABLE` typed by hand, and `dashboard.py:128` `SECTIONS = HARNESS.EDITABLE`. No test compares any of them. The correct pattern already exists one directory over: `tests/test_screen.py:20` imports `editable_section_keys` from the app instead of restating it. | Two authorities | `grep -rn EDITABLE` shows one definition and no comparison | Misleads-a-measurement: the instrument that grades the product is measuring *its own copy* of the section contract. A renamed section would be scored against the old name. |
| **D7** | **The prompt has two homes.** `prompt.py` holds the running text; `product/PROMPT_LIBRARY.md` §1 carries a copy, and its guard is a pinned string in `tests/test_prompt.py:146`, whose comment at `:144` states the risk plainly: "a bump here without a bump there is a fork". Six prompts are documented; one has ever executed. | Two authorities | Read directly | Misleads-a-clinical-decision. A clinician's right to read what the system was told is served by the markdown copy — and a markdown copy can be wrong. |
| **D8** | **121 designed skills sit in a file that reads like a catalogue.** `SKILL_LIBRARY.yaml:1` declares 121 ids (measured: 110 `alpha`, 9 `beta`, 2 `blocked`); `models.yaml` authorises 6. Promotion is a hand copy (`SKILL_LIBRARY.yaml:37-41` says so) and no code reads the file at all — its only machine reference is an issue-template link. | Description surplus | `grep -c "^- id:"` = 121; `grep -rn SKILL_LIBRARY --include='*.py'` = 0 | Wastes-a-reader's-time now, misleads-a-roadmap-commitment later: nothing distinguishes "designed" from "available" to a machine, so a promise can be quoted from either side. |
| **D9** | **Tracked documents rest on evidence a clone cannot see.** `.gitignore` excludes `docs/AUDIT-*.md` and `docs/REVIEW-*.md`; both exist locally and are untracked, and `ADR-0002:9,41`, `DOMAIN_MODEL.md` (R11, several evidence rows) and `gateway-routing.md` cite them. | Unfalsifiable citation | `git status --porcelain --ignored docs` shows both as ignored | Misleads-an-architecture-decision. ADR-0002's opening says everything it relies on is restated in the ADR — true for its own argument, not for the vocabulary entries that quote the papers directly. |
| **D10** | **Banned synonyms live in the shipped interface.** `DOMAIN_MODEL.md:364` bans "review" as a system noun ("Keep **sign-off** as the verb and **Approval** as the noun"); the code's sign-off record is `ReviewRecord` (`report.py:249`, `:260 reviewed_at`) and `models.yaml:58` says "Draft or review a radiology impression". `:307` bans "tier" as a Capability synonym; tracked prose uses it for hardware class (`business/COMMERCIAL_ROADMAP.md:184`, `product/PRODUCT_SPECIFICATION.md:168`), for a roadmap wave (`product/ROADMAP.md:478`), and once as the banned thing itself ("a lower-risk capability tier", `product/RADIOLOGY_WORKFLOW.md:339`). | Vocabulary leak | Read directly | Misleads-an-architecture-decision, and the most instructive row here: the naming authority won the argument in 2026 and lost it in the code it then praised. |
| **D11** | **Three version namespaces, and two claims about one.** `gateway/__init__.py:24` `0.1.0`, `radiology/__init__.py:16` `0.2.0`, one tag `v0.1.0-alpha1`, prompt `radiology-report-draft/0.3.1`. `configs/futurekind.yaml:3-8` and `ARCHITECTURE.md:313` say "the git tag is the platform version"; `apps/radiology_copilot/pyproject.toml:11-12` says the opposite on purpose — "Application version is independent of the platform version". Both sentences are defensible; neither number matches the tag, and no file states the platform version anywhere. | Two authorities | `grep __version__`, `git tag` | Wastes-a-reader's-time until a deployment record is quoted from the wrong namespace — then misleads-a-clinical-decision, because "which build produced this report" is an audit question. |
| **D12** | **The golden dataset's schema lives in a comment and drifts from its data.** `GOLDEN_DATASET.yaml:20` declares `modality: CT \| CTA \| CTP \| MRI \| US \| XR \| MG \| Fluoro`; measured counts are CT 36, US 20, XR 17, MRI 17, CTA 5, MG 3, **HRCT 1**, **CTP 1**, Fluoro 0. | Two authorities | `grep -o "modality: [A-Z]*" \| sort \| uniq -c` | Misleads-an-evaluation: per-modality claims are grouped by a field with no validator, so `HRCT` is silently its own class and `Fluoro` is a phantom one. |
| **D13** | **The drift guard checks existence, not agreement.** `scripts/doctor/check-citations.py` verifies a cited line exists and is non-blank. Live example: `DOMAIN_MODEL.md:140` quoted "`alias: fk-reasoning` (`models.yaml:124`)" — the alias is at `models.yaml:162`, and `:124` is a comment. A shifted-but-non-blank line passes; comma-joined citations (`file.yaml:1,2,3`) are not checked at all. And its denominator is the *working tree* — `check-citations.py:67` walks `root.rglob("*")`, not the tracked set — so the two gitignored working papers are scanned when present and missing on a clone, which makes the reported total a property of the machine rather than of the repository. | Dead mechanism (in the guard itself) | Verified by reading both lines | Misleads-an-architecture-decision. This is the mechanism that let D2 and D10 survive: the repo has a citation gate and citation drift anyway, which teaches the wrong lesson about gates. |
| **D14** | **`ARCHITECTURE.md` holds two truths 150 lines apart.** `:52-66` draws eight Core boxes and a Services layer; `:302-309` states plainly that one component exists. Both are in the same file, in the same voice. | Description surplus | `ls core` → `gateway` | Wastes-a-reader's-time, and it is the *shape* of the problem the whole register is about: the aspirational view and the as-built view are both prose, so neither can fail. |
| **D15** | **An undeclared cross-boundary import.** `apps/radiology_copilot/tests/test_end_to_end.py:47-50` does `sys.path.insert(0, GATEWAY_ROOT/src)` and imports `futurekind_gateway.main`; `apps/radiology_copilot/pyproject.toml` declares no such dependency. The comment at `:44-46` justifies it honestly (the test starts the Gateway as `compose` would). | Hidden coupling | Read directly | Wastes-a-reader's-time in CI, misleads-a-dependency-audit later: the only place the platform's own SDK-less boundary is crossed is the test that claims to prove it. |
| **D16** | **Three HTTP clients and two hand-written DOM surfaces.** `httpx` (`gateway.py`), raw `urllib` (`run-cases.py:79-100`), `ThreadingHTTPServer` (`dashboard.py:55`); `static/index.html` (1,273 lines) and `dashboard.html` (425). | Two authorities | `wc -l` | Mostly *not* debt — see §3. The one that is: the screen's markup is guarded by regex over the file (`tests/test_screen.py`), so a UI refactor is protected by string matching rather than by behaviour. |

---

## 2. Three structures explain sixteen rows

Listing rows is not insight. Three mechanisms generated most of them, and each has a
counter-rule that would have prevented several rows at once.

### 2.1 Restatement without generation

Every fact that moves and is *copied* rather than *derived* will be wrong by the next
sprint. The repository has measured proof: two stale test counts, one stale citation
count, one drifted `path:line` quoting a comment, a modality convention that lost a
value, and a "zero occurrences" proof that became false by the ordinary act of writing
more architecture.

> **Counter-rule.** *A fact that moves has one home. Documents point; they do not copy.*
> Concretely: no count in prose unless dated, generated, or both. A number that is neither
> dated nor produced by a command is deleted, not corrected.

Applied to the register this closes D2, D11, D12, and half of D13 — and it is the rule the
`check-citations` gate cannot enforce, which is why it must be a review question instead.

### 2.2 A claim with no instrument is a promise, not a property

The strongest discipline in this repository — severity by measured cost, paired detection,
an oracle that re-derives counts independently — exists almost entirely on the *radiology*
side. Nothing equivalent guards the documents themselves, so D1, D8, D9 and D14 grew in
prose while the code stayed honest. The imbalance is the finding: **the platform's south
border (toward the model) is engineering-grade; its north border (toward the hospital and
toward its own documentation) is written in sentences that cannot fail.**

> **Counter-rule.** *Every new document names the check that fails when it drifts.* If no
> check can be named, the document is allowed only as a pointer to one that has a check.

### 2.3 Placeholders as authority

Naming an unwritten ADR, an unbuilt service directory, or a designed-but-unauthorised skill
is how a plan gets quoted as a capability. The constitution already caught one instance of
this pattern and deleted the artefacts rather than the sentence (`§7` row 10, the `agents/`
and `genesis/` trees). D1, D8, D14 and D9 are the same failure with better handwriting.

> **Counter-rule.** *A reference may point to a decision that exists, or to an explicit
> "not written" list — never to a number.* An index of intended-but-unwritten ADRs, each
> with the decision it must make, converts 131 dangling references into one honest backlog.

---

## 3. Not debt

Four things that look like debt and must be defended when someone tries to tidy them away.

- **Two HTTP clients.** `run-cases.py` deliberately does not import the product
  (`:299-303`: the oracle re-derives counts "so agreement between the two is evidence
  rather than tautology"). A shared client would silently merge the instrument and the
  measured. Keep both.
- **The stateless copilot.** Four operations, no database, the document travelling through
  the caller, the EHR as the record. This looks like a missing feature ("no `GET
  /reports`") and is the design: retention is a separate, gated decision (`ADR-0003`), not
  a default.
- **The 115 unauthorised skills.** They are the product backlog, and they are honest about
  their own status at `SKILL_LIBRARY.yaml:1-11`. The debt is that the status is prose, not
  a field a machine can count — which is D8's fix, not a deletion.
- **Eleven design patterns for one built screen.** Premature *standardisation* would be
  worse than a second implementation, because it would freeze a shape that has only been
  exercised once. See §4.

---

## 4. The simplicity review: what to delete, and what it breaks

Ordered by (rows closed) ÷ (risk of deleting). Each is a verdict, not a suggestion; the
owner's job is to refuse any of them out loud.

| # | Delete or replace | Closes | Breaks | Cost |
| --- | --- | --- | --- | --- |
| **S1** | Numbers in prose → one dated line in `CHANGELOG.md`, everything else points at it. | D2, D11 | Nothing runs on a count. | Minutes, repeated forever. |
| **S2** | The `model:` key in `models.yaml:142-166` once ADR-0002 step 3 is authorised — its own comment already schedules it (`:33-34`). | D4's worst half | `GET /models` provenance output and one test asserting inventory. | Small, bounded, already agreed in principle. |
| **S3** | The Gateway's chain *walking* (`routing.py:175-215`, `service.py:176`), keeping skill-level degradation policy (may/may-not-downgrade) and deleting multi-candidate expansion. | D4 | Cycle/cap tests written for a graph no config can express. Deleting them is correct — a test for an unreachable branch is a lie with a green tick. | Half a day. Needs the ADR-0002 step-4 amendment first. |
| **S4** | `run-cases.py:59 EDITABLE` → import the app's tuple. One line, and the instrument stops grading its own copy. | D6 | Nothing: the values are identical today (verified by reading both). | Minutes. |
| **S5** | `PROMPT_LIBRARY.md` §1's *copied prompt body* → the version string, the clause inventory, and a pointer to `prompt.py` as the only text. | D7 | Nothing executable. The doc must keep the *reasoning* for each clause — that is the part no code has. | One careful edit. |
| **S6** | `configs/futurekind.yaml` → delete the component advertisement, keep `name`, `license`, `repository`; move RAM figures to the deploy README. Or reclassify the file by moving it to `docs/`. | D3 | CI's YAML-parse step (a one-line change) and several prose citations. | Low, and it is the cheapest way to stop describing intent as configuration. |
| **S7** | `ARCHITECTURE.md`'s aspirational box list → one as-built diagram plus an explicit "planned layers" table marked as such. | D14 | Inbound `ARCHITECTURE.md:NN` citations — which is the *good* kind of breakage: the checker fails loudly instead of a reader failing quietly. | A day, plus citation repair. |
| **S8** | The second routing document: `core/gateway/README-ROUTING.md` folds into `docs/architecture/gateway-routing.md`. | D9-adjacent | Four named citations. | Low. Two documents for one mechanism is the defect `docs/README.md` already names. |
| **S9** | A validator over `GOLDEN_DATASET.yaml`'s declared enums (modality, category), run in CI. | D12 | Nothing — and it catches the next silent value instead of today's two. | Small, and it is the only *addition* on this list. Added because a rule with no instrument is a wish (§2.2). |
| **S10** | An unwritten-ADRs index in `docs/adr/`, one line each for 0003–0007 stating the decision owed and who owes it. | D1 | Nothing. Converts 131 dangling citations into one honest register. | An hour, and the highest value-per-line item here. |

**What the list refuses to do.** It does not delete the fourteen application designs, the
115 skills, the eleven patterns or the statelessness. Those are the parts of Night 3 that
cost thinking rather than typing, and the register's own rule (§2.2) says a document earns
its keep by naming its drift check — several of them already do (`DESIGN_SYSTEM.md` §10's
conformance questions, `CLINICAL_SAFETY.md` §6's gates). Where they don't yet, the fix is a
check, not a deletion.

---

## 5. The ratio worth watching

Tracked files tonight: **75 `.py`, 37 `.md`, 141 total**; 17 python files in the Gateway's
test directory, 14 in the copilot's, one in `scripts/validation/` that CI has never run
(`ci.yml` invokes `pytest` only at `:46` and `:81`). So: the documentation surface is half
the size of the code surface, and one of the three test suites is unwired while six
documents count its tests.

That is not an indictment of writing. It is the tripwire the constitution should have and
does not: **a repository where the number of claims exceeds the number of instruments
drifts quietly, and the drift looks like progress.** The two cheapest instruments to add,
in order: a CI job for the dashboard suite, and a `--collect-only` count produced by the
build instead of typed by a human.

---

**FutureKind Principle**

> Debt of code is paid in refactors. Debt of ideas is paid in misreadings — and the
> interest is charged in other people's time. Delete the second kind first.
