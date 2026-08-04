# FutureKind Architecture
Version: 0.1.0 Genesis

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