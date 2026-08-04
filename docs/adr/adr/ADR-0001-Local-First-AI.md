# ADR-0001: Local-First AI

**Status:** Accepted

**Date:** 2026-08-03

## Context

Healthcare organizations process highly sensitive patient information. Many hospitals require systems that continue functioning during internet outages and wish to retain full control over clinical data.

FutureKind is intended to be deployable by hospitals of all sizes, including those with limited connectivity.

## Decision

FutureKind adopts a **Local-First AI** architecture.

All core AI capabilities should operate on locally deployed models whenever practical.

Cloud AI providers remain optional extensions rather than mandatory dependencies.

## Rationale

- Patient privacy
- Lower latency
- Offline capability
- Reduced operational cost
- Vendor independence
- Regulatory flexibility

## Consequences

### Positive

- Hospitals retain ownership of their data.
- AI continues working without internet access.
- Easier deployment in privacy-sensitive environments.

### Negative

- Local hardware requirements are higher.
- Large models may require GPU acceleration.

## Alternatives Considered

- Cloud-only AI
- Hybrid-first AI

Both were rejected because they make hospitals dependent on external infrastructure for core clinical workflows.

---

**FutureKind Principle**

> Patient data should remain under the hospital's control whenever reasonably possible.
