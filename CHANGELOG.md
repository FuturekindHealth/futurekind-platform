# Changelog

All notable changes to FutureKind Platform will be documented in this file.

The format is based on Keep a Changelog.

---

## [Unreleased]

Neither pass below is tagged; `develop` carries both.

### Sprint 9 — the first clinical product (2026-10-08)

Not a platform sprint. The Gateway, LiteLLM, policy, routing, the provider interfaces,
compose, the ADRs and the constitution were frozen for this work and none of them changed:
no bug in them blocked the product. Everything here is above the boundary, in
`apps/radiology_copilot/`, and it is the first thing in this repository a clinician can use.

#### Added

- **`quality.py` — nine deterministic checks** over a draft, each a comparison of the draft's
  text with the text the clinician submitted: `dropped_observation`,
  `unsupported_measurement`, `invented_history`, `unsupported_certainty`,
  `unsupported_absence`, `format_breach`, `invented_identifier`,
  `self_reported_confidence`, `structure_coverage`. No model grades the model, no thresholds,
  no learned score — the same dictation and the same draft always give the same verdict, which
  is the only kind of rule a department can audit afterwards. The module's own docstring
  states the limit it cannot escape: every check compares words to words, and none of them
  has seen the images.
- **`profiles.py` — the MRI brain study profile**: fourteen structures with the synonyms that
  count as mentioning them, and the negatives a brain study cannot support. One profile,
  because five more would be a guess about five departments. A profile can only ever raise an
  advisory finding, never block a report for a structure nobody described.
- **`RadiologyReport.follow_up` and `RadiologyReport.confidence`** in the document itself.
  Follow-up is kept apart from recommendations because they are different acts — what to do
  now, and when to look again — and an interval buried in a paragraph of referrals is an
  interval nobody books. Confidence is computed from the checks, the provenance and the
  completeness of the input, and a model that returns its own `confidence` key has it named
  and withheld.
- **Previous reports as input** (`submission.py`): up to five, each under 2 000 characters,
  under 6 000 in total, each needing its date. A comparison in the draft is only legitimate
  against one of these, and the absence of them is stated to the model rather than left
  silent.
- **`static/index.html`, served at `GET /`** — the screen a radiologist works in: the
  submission and its priors on the left, the six editable sections in the middle, the quality
  findings, confidence and provenance on the right. One static file inside the package: no
  CDN, no framework, no font fetched from anywhere, no localStorage and no session, and it
  calls the same four endpoints an integration would.
- **`POST /check`** — the same nine checks over the text as it stands, with no Gateway call
  and nothing stored, so the findings move while the clinician types.
- `tests/test_quality.py` (45 tests): every check proved caught *and* the innocent version of
  the same sentence proved not caught; three MRI brain golden fixtures derived from the
  golden set's own dictations; malformed-input cases (six priors, oversized priors, a prior
  with no date, a `patient_name` field); determinism; the plan-versus-assertive severity
  split; and one draft that raises all nine checks in the documented order.

#### Changed

- **Sign-off is now a gate, not a formality.** `POST /review` requires the submission the
  draft was made from, re-runs the nine checks over the amended text, and refuses a signature
  while any finding is `block` (`422`, carrying check names and section names only — never the
  clinical text). A section the clinician rewrote has its findings downgraded to advisory:
  the image, not the dictation, is their source, and this application does not overrule the
  person who owns the report. Nothing is locked — a corrected sentence clears the block, a
  returned draft needs no submission, and a signed report can still be amended and re-exported.
- **Prompt `radiology-report-draft/0.3.0`.** The same running prompt, versioned up rather than
  forked: every number must appear in the observations or a supplied prior; no comparison
  unless the prior is in the request; a hedged finding stays hedged; follow-up apart from
  recommendations; `"None."` in a section with nothing to say. `docs/product/PROMPT_LIBRARY.md`
  §1 carries the new text verbatim, with the enforcement of each clause mapped to the check or
  the parse error that backs it.
- **A measurement is compared as a whole number, not as a substring.** `"9" in "19 mm"` is
  true, so a draft that shrank a dictated 19 mm midline shift to 9 mm passed
  `unsupported_measurement` — the near miss, right digit and wrong number, which is exactly
  the error the golden set's `must_not_say` column weighs most. Numbers are tokenised on both
  sides now, and a digit inside a sequence name (`T2`) grounds nothing. The residue the rule
  leaves is written down rather than smoothed over: a bare age or date in the submitted text
  still grounds a drafted size, and the test that says so explains why tightening it further
  would refuse correct reports.
- The quality pass and the confidence grade render in **all three export formats**, so a
  printed report states what was checked on it — the only part of this design a reader who
  never opens the API can verify.
- The product documents now say what is built instead of what was designed:
  `RADIOLOGY_WORKFLOW.md` §S4–S6 and its failure catalogue (F19–F23 are the failures code can
  now catch), `UI_UX.md` §6 with the interim screen recorded as interim, `ROADMAP.md` §3 with
  the plan that was not followed kept visible rather than overwritten, and
  `docs/product/README.md`'s summary numbers.

#### Verified

Measured on this tree, counted from `--junit-xml` rather than from a summary line:
**717 tests — 492 Gateway, 225 copilot (45 of them on the quality engine, 6 over real
sockets) — zero failures, zero errors, zero skips.** ruff clean on both packages; 213
in-tree `path:line` citations resolve; 50 relative documentation links resolve; no CRLF in
any `.sh` or `.py`; no zero-byte tracked file; no infrastructure identifier in any tracked
or staged file.

The workflow was then walked in a browser against a running Gateway and a stub LiteLLM —
two real processes, real sockets, nothing mocked in the application:

* Draft: `200`, six editable sections, `quality` with one advisory `structure_coverage`
  finding, `confidence` = `review-carefully`, Approve **enabled** (an advisory does not
  stop a signature), provenance naming `ollama/qwen3:14b`, prompt `0.3.0`, profile
  "MRI brain", `Compared with: no priors`.
* One invented sentence typed into Findings — *"A 27 mm right frontal lesion is present,
  unchanged from the MRI of 4 months ago"*: `unsupported_measurement` and
  `invented_history` both **block**, `not-safe-to-sign`, the Approve control disabled, the
  banner changed, and Return-for-correction left enabled.
* `POST /review` on the same document: `422` with
  `{"blocking": [{"check": "unsupported_measurement", "section": "findings"},
  {"check": "invented_history", "section": null}], "sections": ["findings"]}` — and the
  response body contains neither `27` nor the words "frontal lesion".
* The words corrected: the block cleared, the report signed, and the text export carried
  the signed banner, FOLLOW-UP, the quality findings and the confidence grade.
* With a previous report supplied, the same comparison sentence passed and provenance
  printed `Compared with: 2026-06-02 — MRI MRI BRAIN WITH CONTRAST`.

**Not measured here:** any real model on any hospital hardware. The answering side of that
last run was a stub, and it is the only honest reason the draft came back in 5 ms.

#### What this sprint did not solve

No real-model latency number — the only timing in this repository is still 27–30 ms against a
stub. No ERP integration, no PACS modification, no clinician authentication (the signer's name
is typed, which is the F-A defect and it is unchanged), no audit retention, no streaming. The
golden dataset is still `ratified: pending` on all 100 cases. The checks read text, so a
plausible finding nobody dictated is still invisible, and `quality.scope` says so on the screen
rather than leaving it to a README.

### Sprint 8 — release readiness (2026-10-08)

No feature, no architecture change: every entry below closes a blocker raised by the
engineering review before the first public push.

#### Changed

- **Security — the inventory is no longer public.** `GET /models` and
  `GET /models/{capability}` now require the credential `POST /chat` has always
  required; `GET /metrics` likewise, because its label values name providers and
  model ids. `GET /health` and `GET /health/ready` stay reachable without a key — a
  container runtime cannot hold one — and publish verdicts only: no catalogue path,
  no provider names, no upstream error text. Closes constitution register rows 1–3.
- **Security — `.env.example` ships no credential and no host.** Placeholder secrets
  become `<generated: openssl rand -hex 32>` with the command stated; the real LAN
  addresses of the reference clinic are gone, and the unread `OLLAMA_SECONDARY` with
  them.
- **Deployment — one compose tree.** `compose/compose.core.yaml` and its
  empty-alias LiteLLM config are deleted; `compose.yaml` is the only file describing
  an installation.
- **Version — one declaration per artefact.** The root `VERSION` file is deleted, the
  platform manifest holds a release-line name and no number, and
  `[tool.hatch.version]` reads each package's `__init__.py`, which is the number the
  wheel, `GET /health` and the served OpenAPI document all report.
- **Claims matched to the system.** OpenTelemetry tracing, Prometheus, Grafana,
  Langfuse and cost/budget tracking are marked planned or absent in
  `core/gateway/README.md`, `configs/futurekind.yaml` and `docs/ARCHITECTURE.md`,
  which now opens with a table of which boxes are built.
- `docs/adr/adr/ADR-0001-Local-First-AI.md` flattened to `docs/adr/`, repairing the
  two architecture links that pointed through the doubled segment.
- Skill counts corrected to the six authorised stanzas; the 121-skill design
  catalogue remains design.

#### Removed

- The placeholder clinical layer: 34 files under `genesis/` and `agents/` (14 of them
  zero bytes, the rest keyboard noise, five named `New Text Document.txt`). The
  clinical doctrine they were meant to hold is scheduled work, not an empty file.
- `core/gateway/openapi.yaml`, a hand-written four-path stub that contradicted the
  served `/openapi.json`.
- `services/.gitignore` (a copy of the root file) and the empty directories that
  advertised unbuilt components.

#### Added

- `LICENSE` (Apache-2.0, matching what both `pyproject.toml` files declared),
  `README.md` and `SECURITY.md` — the front door and the disclosure channel, both of
  which were previously empty.
- CI (`.github/workflows/ci.yml`): both Python suites, both lints, YAML and compose
  validation, the alias-contract check between the two catalogue files, relative-link
  validation, and a repository-hygiene gate for the identifiers and placeholder files
  this pass removed.
- Issue templates for bugs and skill proposals, a pull-request template, and an
  issue-form config that routes security reports to private disclosure.
- `py.typed` is unchanged; no static type checker is configured for either package,
  and the README says so rather than leaving it implied.

#### Verified

492 Gateway tests and 160 copilot tests, zero failures and zero skips; ruff clean on
both packages; 54 relative documentation links resolve; no zero-byte or
placeholder-path tracked file; no private address, hostname or credential-shaped
string in any shipped file. `compose.yaml` and `core/gateway/Dockerfile` remain
**parse-verified only** — no container daemon was available on any machine used for
this work, so the compose path has still never been booted.

## [0.1.0-genesis] - 2026-08-03

### Added
- Initial repository
- Project vision
- Version file
