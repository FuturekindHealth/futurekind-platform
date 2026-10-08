<!--
The one rule this repository is built around: a change is judged against what the
platform already claims. Read docs/CONSTITUTION.md §7 before touching the boundary.
-->

## What changed, and which claim it answers

Link the issue, the register row (`CONSTITUTION.md §7`), the specification clause
(`SPEC-…`), or the threat-model finding (`F1…F5`). A change that answers nothing is
a feature, and this is not where features land.

## Does it move the boundary?

- [ ] No — nothing under `core/gateway/` or `apps/radiology_copilot/` changed
- [ ] Yes — and `docs/ARCHITECTURE.md`, `docs/adr/ADR-0002-…` and
      `docs/architecture/gateway-routing.md` say the same thing as the code now

## Gates

- [ ] `ruff check src tests` and `pytest` pass in `core/gateway/`
- [ ] The same in `apps/radiology_copilot/` (its tests import the Gateway — that
      import must be real, not skipped)
- [ ] A **new** endpoint either requires a credential or states, in its docstring and
      in `docs/SPECIFICATION.md` §6.5, why a caller without one may read it
- [ ] No prompt or completion text in any log line, error body or metric label — and a
      test that would fail if one appeared
- [ ] No real host address, hostname, credential or customer identifier in any file
      (CI checks the terms; a reviewer checks the shape)
- [ ] Clinical claims carry evidence: a file and line, a measurement, or the word
      *Design* in front of them

## If a document was wrong before this change

Say so in the description rather than editing it silently. This repository keeps a
register of its own violations precisely so that a correction is visible; the value is
in the record, not in the appearance.
