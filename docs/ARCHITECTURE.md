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
| Radiology Copilot (`apps/radiology_copilot/`) | **Built and tested** — 229 tests: draft, grounding checks, review, sign, export; 6 over real sockets. In no compose file yet |
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