# FutureKind Architecture
Release line: Genesis. Which boxes are built is at the end, under "What this document is".

---

# Vision

FutureKind is an open, local-first AI platform for healthcare.

It provides the infrastructure required for hospitals to deploy trustworthy AI while keeping clinicians in control and patient data under hospital ownership.

FutureKind is not an application.

It is the platform upon which healthcare applications are built.

---

# Design Principles

1. Local First
2. Human in Control
3. Open Standards
4. Security by Default
5. Modular Architecture
6. Observability Everywhere
7. Vendor Independence

---

# Platform Layers

                    Applications

------------------------------------------------------------

CARE ERP

Radiology

Pathology

Patient Portal

WhatsApp

Voice

------------------------------------------------------------

FutureKind Core

Authentication

Gateway

Audit

Configuration

Notifications

Permissions

SDK

Secrets

------------------------------------------------------------

FutureKind Services

LiteLLM

Open WebUI

Qdrant

Redis

PostgreSQL

Langfuse

SearXNG

Crawl4AI

------------------------------------------------------------

Infrastructure

Docker

Synology

Cloudflare

AI Servers

---

# Rules

Applications never communicate directly with AI models.

All AI traffic passes through FutureKind Gateway.

Applications never communicate directly with Ollama.

Applications never communicate directly with databases.

FutureKind Core owns:

Authentication

Authorization

Audit

Configuration

Logging

Metrics

Tracing

Notifications

Health

---

# AI Gateway

Every request follows:

Application

↓

Gateway

↓

LiteLLM

↓

Model Router

↓

LLM

↓

Gateway

↓

Application

---

# Configuration

One configuration source.

.env

No duplicated settings.

---

# Logging

Every service produces structured logs.

---

# Metrics

Every service exposes metrics.

---

# Health

Every service exposes health endpoints.

---

# Security

No secrets inside compose.

No passwords inside repositories.

---

# Runtime

Git stores:

Code

Configuration

Documentation

Scripts

Runtime data is stored outside Git.

---

# Deployment

FutureKind supports:

Docker Compose

Kubernetes (future)

Nomad (future)

Cloud (future)

without changing platform architecture.

---

# Mission

Human Wisdom.

AI Precision.

Open Healthcare.

---

# The clinical product, as built

Everything above is the platform. This is the part a radiologist touches, described the way it
is actually assembled — seven modules, one document, four operations, no state.

```
 browser (static/index.html)  ── one origin, served by the same process
        │  POST /draft · /check · /review · /export      GET /health
        ▼
 api.py            request bodies as contracts, one error envelope, nothing cached
   ├── submission.py   what the clinician supplied. No patient identifier field, by rule
   ├── copilot.py      the four operations. Stateless: the document travels through the caller
   │      ├── prompt.py       the system turn, versioned so a report names its prompt
   │      ├── gateway.py      skill-only request; the app never names a model
   │      ├── report.py       the document: six sections + quality + confidence + provenance
   │      │                   and the ownership rule that decides what may be typed in
   │      ├── profiles.py     which study gets which structure checklist
   │      └── quality.py      nine deterministic checks over text, and the confidence computed
   │                          from them
   └── rendering.py    the same document as text, markdown or json — one order, one heading set
```

Four decisions give the shape its meaning:

- **The application is stateless on purpose.** Each operation takes the document and returns a
  new one, so a hospital can run several instances and the record stays where the domain model
  says a Report belongs. It also means the browser holds the only copy of a draft, which is why
  the screen refuses to leave with unsaved words instead of persisting them.
- **Governance is checked before the medicine is read.** Policy, risk level, skill identity and
  downgrade come first; a perfect JSON answer under the wrong policy is refused. Truncation is
  checked before parsing, because a half-written impression is the one artefact that reads as
  complete.
- **Ownership is stated per section, not per screen.** The referrer's question and the
  department's technique line enter from the submission; when nobody supplied a technique the
  model owns that sentence, and the screen unlocks it. Findings, impression, recommendations and
  follow-up are drafted by the model and owned by whoever signs.
- **The checks compare words to words and say so.** They can show a statement is unsupported by
  what was submitted; they cannot show it is true, and none of them has seen the images. That
  limitation travels inside the document (`quality.scope`, `confidence.basis`) rather than in a
  README nobody re-reads at four in the afternoon.

What sits outside this box and is not built: individual authentication of the signer (ADR-0004),
the platform approvals primitive (ADR-0005), audit retention, the ERP's Approval Screen, and any
measure of what a real model costs in seconds and tokens. The roadmap's Beta gates are those
items, not new modules here.

---

# What this document is

A target architecture, written before most of it existed. Read it with the inventory
below, because a diagram of a platform is not a description of a deployment, and this
repository has been reviewed against both readings. It sits at the end of the file on
purpose: an earlier release pass inserted it here at the top and silently invalidated
every `ARCHITECTURE.md:<line>` citation in the documents that point into this one —
which is exactly the class of defect `docs/DOMAIN_MODEL.md` says a citation is meant
to prevent. `scripts/doctor/check-citations.py` now catches that.

| Box in this document | Status on 2026-10-08 |
| --- | --- |
| FutureKind Gateway (`core/gateway/`) | **Built and tested** — 492 tests: catalogue, policy, routing, LiteLLM transport, OpenAI-compatible door, logs and metrics |
| Radiology Copilot (`apps/radiology_copilot/`) | **Built and tested** — 255 tests: draft, grounding checks, review, sign, export, and the reporting screen's own contracts; 6 over real sockets. In no compose file yet |
| LiteLLM, PostgreSQL, Redis, Qdrant, Open WebUI | **Defined in `compose.yaml`**, which is the only compose tree; not started on any host from this repository, because no container daemon was available during development, so the deployment path is validated by parsing and by `docker compose config` in CI rather than by booting |
| Audit | **Emitted, not retained.** `skill_audit` log lines exist; no storage is configured. Register row 4, and the reason Beta has a gate |
| Authentication, Authorization, Permissions, Notifications, Secrets, SDK, CLI | **Not built.** `core/{auth,audit,cli,config,notifications,sdk}` held no files and are removed from the working tree; the Gateway's only credential is a shared API key (ADR-0004 pending) |
| Langfuse, SearXNG, Crawl4AI, Prometheus, Grafana, OpenTelemetry | **Not deployed and not configured.** `configs/futurekind.yaml` marks each `planned`; nothing reads those keys yet |

Version numbers are not declared here either: each package carries its own in its
`__init__.py`, which is the number `[tool.hatch.version]` builds, `GET /health`
reports and the served OpenAPI document publishes. The git tag is the platform
version. A copy of a number in a prose document is a second place to be wrong.

The rules in this document still bind the code that exists: one AI boundary, no model
or provider selection from a caller, no prompt text in a log. A box that is absent is
unbuilt, not permitted.

---

# The layer above this one

The **Applications** box near the top of this file is the 2026 target list, and it is kept here
because it is where the boundary rule was drawn: applications never speak to a model. It is not the
product plan, and it must not be read as one — that would give this document an owner it does not
have.

The application family is owned by [`product/PRODUCT_BIBLE.md`](product/PRODUCT_BIBLE.md): fourteen
applications in three kinds, each tested against four rules, with the merges and the refusals
recorded. What each one calls, reads, writes and hands off is
[`architecture/APPLICATION_MAP.md`](architecture/APPLICATION_MAP.md), whose first section is the
contract this file's boundary makes possible — `SPEC-12-04`: a credential and a skill name, no
platform change, never a LiteLLM key.

Three invariants from this document bind every application above it, and none of them is
negotiable by convenience: the application names a skill and never a model; the signed document
lives in the hospital's system of record and not in the application; and the platform's silence
about prompt content is a property of the whole stack, not of the Gateway alone. An application that
would need a fifth layer, a new request field or a second AI boundary is not a new product — it is
an amendment proposal, and `docs/SPECIFICATION.md` §17 is where such proposals are recorded.