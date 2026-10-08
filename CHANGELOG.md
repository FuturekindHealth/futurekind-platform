# Changelog

All notable changes to FutureKind Platform will be documented in this file.

The format is based on Keep a Changelog.

---

## [Unreleased]

Release-readiness pass, 2026-10-08. No feature, no architecture change: every entry
below closes a blocker raised by the engineering review before the first public push.

### Changed

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

### Removed

- The placeholder clinical layer: 34 files under `genesis/` and `agents/` (14 of them
  zero bytes, the rest keyboard noise, five named `New Text Document.txt`). The
  clinical doctrine they were meant to hold is scheduled work, not an empty file.
- `core/gateway/openapi.yaml`, a hand-written four-path stub that contradicted the
  served `/openapi.json`.
- `services/.gitignore` (a copy of the root file) and the empty directories that
  advertised unbuilt components.

### Added

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

### Verified

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
