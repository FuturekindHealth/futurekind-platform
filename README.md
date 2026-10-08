# FutureKind

**Status: Alpha.** Local-first AI for hospital workflows. Not for patient data yet —
see [What Alpha is not](#what-alpha-is-not).

FutureKind is the layer between a hospital's clinical applications and the models
that answer them. An application says *what work it is doing* — "draft this
radiology report" — and the platform decides which model answers, under which
policy, and records what it did. The application never names a model, a provider
or an endpoint.

That inversion is the whole product. A clinician choosing a model picker is a
hospital accumulating decisions it cannot audit; a clinician choosing a *task* is
the same hospital with one place to look.

- **Local-first.** Inference runs on the hospital's own hardware. No cloud path is
  enabled by default, and none is selectable by a caller.
- **Human in control.** AI drafts. A named clinician signs. The platform can refuse
  a draft; it cannot approve one.
- **Auditable by construction.** One boundary, one request id, one audit line per
  governed call — small enough that a hospital could actually read it.

License: [Apache-2.0](LICENSE) · Security: [SECURITY.md](SECURITY.md) ·
Governance: [docs/CONSTITUTION.md](docs/CONSTITUTION.md)

---

## Architecture

```
   CARE ERP        Radiology        Pathology        Patient portal      (any application)
                     Copilot

                     every arrow below is the only arrow


                          +---------------------------+
                          |     FutureKind Gateway    |   core/gateway
                          |  the single AI boundary   |
                          +---------------------------+
        skill ──►  Skill  ──►  Capability  ──►  Policy  ──►  Alias  ──►  Model
        (what       (the         (routing       (risk,      (the one    (LiteLLM's
        the app      class of     class)         approval,    name both    decision,
        names)       work))                     audit,       sides        never named
                                                 limits)      agree)      by a caller

                          +---------------------------+
                          |          LiteLLM          |   configs/litellm
                          |  alias → model + endpoint |
                          +---------------------------+
                          |   Ollama on the hospital's own host   |
```

Five namespaces, each with one owner, are the design. `Skill`, `Capability`,
`Policy`, `Alias` and `Model` mean exactly one thing each, and a request may carry
only the first. The rules that bind them — and the tests that enforce them — are in
[docs/architecture/gateway-routing.md](docs/architecture/gateway-routing.md),
[docs/architecture/gateway-policy.md](docs/architecture/gateway-policy.md) and
[docs/adr/ADR-0002-Gateway-vs-LiteLLM.md](docs/adr/ADR-0002-Gateway-vs-LiteLLM.md).
The word list itself is [docs/DOMAIN_MODEL.md](docs/DOMAIN_MODEL.md).

Two doors, one rule book:

| Door | For | `model` means |
| --- | --- | --- |
| `POST /chat`, `GET /models` | applications written against FutureKind | n/a — a caller sends a `skill` |
| `POST /v1/chat/completions`, `GET /v1/models` | any OpenAI-format interface (Open WebUI today) | a **skill**, never a model id |

`GET /v1/models` returns intent and no infrastructure; `GET /models` returns the
routing table but only to a caller that already holds a key, as do `/metrics`,
`/chat` and both `/v1` operations. `GET /health` and `GET /health/ready` are the only
endpoints that answer an unauthenticated **caller**, and they report "is it well"
without naming a provider, a model or a path — a container runtime has to be able to
ask. The contract surface (`/docs`, `/redoc`, `/openapi.json`) is still open too; that
is SPEC-10-04, deliberately left for ADR-0004 rather than changed mid-release.

---

## What is here

| Path | What it is | State |
| --- | --- | --- |
| `core/gateway/` | The Gateway: FastAPI service, catalogue, policy, routing, LiteLLM transport, OpenAI-compatible door, logging, metrics | **Built**, 492 tests |
| `apps/radiology_copilot/` | The first clinical application on it: draft → review → sign → export for imaging studies | **Built**, 160 tests |
| `core/gateway/models.yaml` | The live catalogue: 6 authorised skills, their policy, and the aliases that serve them | Config, reviewed one skill at a time |
| `configs/` | Platform manifest and LiteLLM's alias list | Config |
| `compose.yaml` | One installation: postgres, redis, qdrant, litellm, gateway, open webui, behind profiles | Written and parsed; **never booted here** |
| `docs/` | Constitution, ADRs, domain model, specification, architecture, product design, threat model | The bulk of this repository, deliberately |
| `scripts/doctor/check-ai.sh` | Verifies the AI path is the path the architecture claims, including that LiteLLM is *not* reachable from the host | Runs on a deployed host |

Six skills are authorised. **121** are designed and reviewed on paper in
[docs/product/SKILL_LIBRARY.yaml](docs/product/SKILL_LIBRARY.yaml) — a design
catalogue that no process reads. The gap is clinical review capacity, not code, and
that is the point of the roadmap.

---

## Getting started

Python 3.12, and 16 GB of RAM if you intend to run a model locally.

```bash
git clone https://github.com/FuturekindHealth/futurekind-platform.git
cd futurekind-platform
cp .env.example .env        # then replace every <generated: …> value; see the file header
```

[**README-FIRST-DEPLOY.md**](README-FIRST-DEPLOY.md) is the deployment path, in the
order an operator can verify each step. It assumes Docker; if you have no container
runtime, the two Python packages run directly:

```bash
# The Gateway, with its own suite (492 tests, including real-socket end-to-end ones)
cd core/gateway
python -m venv .venv && .venv/bin/pip install -e ".[dev]" && .venv/bin/pytest

# The copilot. Its tests import the Gateway, so install both into one environment.
cd ../../apps/radiology_copilot
python -m venv .venv && .venv/bin/pip install -e ../../core/gateway -e ".[dev]" && .venv/bin/pytest
```

The Gateway needs an Ollama host (or any OpenAI-compatible backend LiteLLM can
address) before it can answer anything. Without one it still starts, still serves
`/health`, and answers `502` on a completion — honestly, rather than pretending.

---

## Development

```bash
cd core/gateway
python -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/pytest                    # the suite includes real-socket end-to-end tests
.venv/bin/ruff check src tests
```

`apps/radiology_copilot/` works the same way, except that its tests import the
Gateway, so both packages belong in one environment. Both are linted with ruff and
tested with pytest; CI (`.github/workflows/ci.yml`) runs both suites, both lints, and
the configuration and repository-hygiene checks.

One gap in that gate, stated rather than implied: the Gateway ships `py.typed` and is
fully annotated, the copilot is annotated but ships no marker, and **no static type
checker is configured for either package** — ruff here checks style, imports and
common bug patterns, not types.

Three conventions that are not style preferences:

- **No prompt or completion text in a log, ever.** Field names are denied at the
  logging boundary (`observability/logging.py`), not left to reviewer diligence.
- **A caller may not relax the policy applied to it.** `allow_downgrade` in a request
  body is a `422`, because otherwise every rule is a suggestion.
- **A skill is authorised one at a time**, in `models.yaml`, with its alias added in
  the same change. The Gateway refuses to start when the two files disagree.

Read [CONTRIBUTING.md](CONTRIBUTING.md) and then
[docs/CONSTITUTION.md](docs/CONSTITUTION.md). The constitution is not decoration: it
holds a register of this project's own violations, with file and line for each, and
several were closed by the last release pass rather than by this paragraph.

---

## Roadmap

[docs/product/ROADMAP.md](docs/product/ROADMAP.md) is the plan;
[docs/product/PRODUCT_SPECIFICATION.md](docs/product/PRODUCT_SPECIFICATION.md) is the
product. In short:

| Gate | Before it, this must be true |
| --- | --- |
| **Alpha** (now) | One boundary, policy enforced, audit emitted, the first application works end to end in tests |
| **Beta** | Audit *retained* (ADR-0003), approvals that cannot be granted today (ADR-0005), individual clinician authentication (ADR-0004), the golden set ratified by a clinician |
| **v1** | A hospital runs it unattended, and a second one can install it from the documents without a vendor in the room |

---

## Contributing

Issues and pull requests are welcome, and clinical review is the scarcest resource
here — a skill that never reaches `models.yaml` because nobody signed off on it is a
better outcome than one that reached it anyway. Start with
[CONTRIBUTING.md](CONTRIBUTING.md), the constitution, and
[docs/DOMAIN_MODEL.md](docs/DOMAIN_MODEL.md), which explains why `Skill`, `Agent`,
`Capability` and `Model` are four words rather than four spellings of one.

This repository's `main` branch is the released line; `develop` is where work lands.

---

## What Alpha is not

Stated plainly, because a hospital will judge this platform by whether it told the
truth at this stage:

- **Audit is emitted, not retained.** `skill_audit` lines go to stdout with no prompt
  or completion text in them. Nothing stores them. Ask "what did the system do on
  14 March" and today the answer is "if the log rotation kept it".
- **The platform cannot grant an approval.** A skill declaring `approval_required` is
  refused rather than waved through — the refusal is the honest behaviour until
  ADR-0005.
- **Nothing streams.** `stream: true` returns `501`. Streaming needs its cancellation
  and audit semantics specified first (SPEC-15-03).
- **One skill has a caller.** `radiology-report` runs in the copilot; the others are
  catalogue entries awaiting an application.
- **The golden set is unratified.** 100 studies, authored by an engineer, `ratified:
  pending` on every one of them. It is a starting artefact, not an evaluation.
- **Latency is measured on one machine.** The best number obtained so far is
  **3.9 tokens/s** on the development host — which is why the roadmap puts timing on
  the hospital's own hardware *before* building the interaction that depends on it.
- **The container path is built, not booted.** CI builds `core/gateway/Dockerfile`
  and interpolates `compose.yaml` on every push, so the packaging claims are
  checked. What no machine here has done is run the stack: there is no Docker
  daemon on any development host, so the healthcheck chain, the mount paths and
  the startup order are unexecuted. The Gateway itself is proved over real
  sockets in `test_end_to_end.py`.
- **No PHI has been processed by any of it,** and until audit retention and per-user
  authentication exist, that is the correct state for a deployment to be in.

---

## Licence

Apache-2.0. See [LICENSE](LICENSE) and [docs/product/README.md](docs/product/README.md).

FutureKind is clinical decision *support*. It does not diagnose, and no output from
it is a clinical decision.
