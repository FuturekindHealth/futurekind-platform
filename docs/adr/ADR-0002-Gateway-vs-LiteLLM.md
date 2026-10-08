# ADR-0002: Gateway vs LiteLLM Ownership

**Status:** Accepted

**Date:** 2026-10-07

**Deciders:** FutureKind platform owner

**Relates to:** ADR-0001 (Local-First AI), `docs/ARCHITECTURE.md`, `docs/architecture/gateway-routing.md`. It also answers a 2026-10-07 layering review kept as an internal working paper; every claim it made that survives is restated in this document, so nothing here depends on a file the repository does not publish.

---

## Context

FutureKind places an AI Gateway above LiteLLM. `docs/ARCHITECTURE.md` specifies the request chain as:

```
Application → Gateway → LiteLLM → Model Router → LLM
```

`configs/futurekind.yaml` names `ai.gateway: LiteLLM`. `core/gateway/README.md` lists the Gateway's responsibilities as Authentication, Authorization, Model Routing, Prompt Logging, OpenTelemetry Tracing, Metrics, Audit Trail, Rate Limiting, Cost Tracking and Fallback Models.

Those documents disagree about one thing: **where model routing lives.** The architecture diagram places it below the Gateway, inside LiteLLM. The Gateway README claims it as a Gateway responsibility.

The Gateway skeleton implemented against the second reading. `core/gateway/models.yaml` (added in `c1db9c2`, FK-0200) names a provider and a raw Ollama model id for every entry:

```yaml
reasoning:
  provider: ollama
  model: qwen3:14b
```

and `configs/litellm/config.yaml` independently registers the same models under different names:

```yaml
- model_name: fk-reasoning
  litellm_params:
    model: ollama/qwen3:14b
```

Three tables now describe one routing reality: the Gateway catalogue, the LiteLLM model list, and the `fk-*` alias namespace. The engineering audit recorded this as finding 3, and the architecture review recorded the consequences as findings 1, 4 and 5.

---

## Problem

The Gateway is at risk of becoming a second LiteLLM.

Model routing is not a single decision. It is at least six: which weights answer, which endpoint serves them, what happens on failure, which credentials are used, what the request cost, and how spend is limited per caller. LiteLLM already implements all six. Every one the Gateway reimplements is a second place where the answer can disagree with the first.

The concrete symptoms already present:

- **A duplicated model table.** Adding a model means editing `models.yaml` *and* `configs/litellm/config.yaml`, with different key names in each. Nothing fails if they drift; the Gateway simply routes to something the operator did not intend.
- **A skipped layer.** `provider: ollama` means the Gateway would call Ollama directly, bypassing the hop the architecture diagram makes mandatory — and bypassing LiteLLM's virtual keys, budgets, rate limits and spend logs, which are audit findings S4 and S5.
- **Provider topology that cannot be expressed.** `ProviderRegistry` is keyed by a single string, so primary/secondary endpoint failover — the shape `.env.example` used to advertise with an `OLLAMA_SECONDARY` that no code read, removed 2026-10-08 — and "one model reachable through two backends" are unrepresentable.
- **Infrastructure names in the application contract.** The delivered request schema accepted a `model` field. That makes every model id part of the public API, so changing hardware becomes a breaking change for clinical applications — the direct opposite of `README-ROUTING.md`: "Changing hardware never requires application changes."

This ADR decides ownership. It does not decide implementation order.

---

## Options Considered

Two readings of the existing documents are coherent. A third was rejected outright.

### Option A — The Gateway owns intent; LiteLLM owns models

**Decision.** The Gateway routes *skill* and *capability* to a **model alias**. LiteLLM owns the alias-to-model-and-endpoint mapping, provider selection, retries, failover and cost accounting.

The Gateway's catalogue stops naming Ollama model ids. `reasoning` resolves to the alias `fk-reasoning` and nothing more; LiteLLM decides that it currently means `qwen3:14b` on the host in the operator's `.env`, and decides again on the next restart. The address is never in this ADR, a catalogue or a document, because it is the deployment's fact to hold.

| Concern | Owner |
| --- | --- |
| Skills, clinical context, authorization, audit | Gateway |
| Model aliases, provider routing, model routing, retries, failover, cost | LiteLLM |

**Cost:** two files must agree about alias names, so a startup check is needed: every alias the catalogue references must exist in the LiteLLM model list, or the Gateway refuses to start rather than discovering it on a live clinical request.

### Option B — The Gateway is the sole model router

**Decision.** The Gateway chooses provider, endpoint, model, retry and failover. LiteLLM is demoted to a protocol adapter, or removed.

**What it buys:** the architecture diagram would need editing, `core/gateway/README.md` would be literally correct, and one table would own everything.

**What it costs:** the Gateway must implement, test and operate virtual keys, per-application budgets, rate limiting, spend tracking, provider health, retry policy and credential rotation — for every backend it will ever support. That is the platform's single largest non-clinical build effort, reimplemented in the one component that must stay small enough for a hospital to audit. It also re-opens ADR-0001's vendor-independence argument, because the router code hard-codes backend behaviour.

### Option C — Both, opportunistically (rejected)

Route some capabilities through LiteLLM and others directly to a backend, per row. Rejected: it preserves both tables forever, and every future bug report must start by asking which path a given request took. The repository already has one instance of a duplicated model table; a deliberate policy of two is not a design, it is the current accident formalised.

---

## Decision

**Option A is adopted.**

The FutureKind Gateway owns **skills, policy, authorization, audit and clinical context**. LiteLLM owns **model aliases, provider routing, model routing, retries, provider failover and cost tracking**.

**The Gateway must never become a second LiteLLM.** Where a capability gap in LiteLLM is found, the response is an issue against the platform boundary or a new ADR — not a parallel implementation inside the Gateway.

Three rules follow, and are normative:

1. **Model identifiers are internal.** No application-facing request field may name a model, a provider or an endpoint. A model id may appear in a *response*, because a clinician must be able to see which model produced a report line — the right to know what answered is not the right to choose what answers. That distinction is recorded here deliberately.
2. **Applications express intent.** A *skill* (`radiology-report`, `clinical-chat`, `summarize-document`, `pathology-review`) is what an application asks for. A *capability* (`chat`, `reasoning`, `vision`, `embedding`) is the technical class the Gateway maps it to. A *provider* is where the Gateway's request goes next, which under this ADR is LiteLLM.
3. **Routing decisions the Gateway does make are auditable and owned.** Skill→capability mapping, whether a lower class may answer a given skill, and the clinical context attached to a request are Gateway policy. They belong in `models.yaml`, not in application code and not in LiteLLM configuration.

---

## Consequences

### Positive

- One model table. `configs/litellm/config.yaml` becomes the only place weights are named; audit finding 3 closes by deletion rather than by reconciliation.
- The architecture diagram in `docs/ARCHITECTURE.md` is true as written, so `README-ROUTING.md`'s "changing hardware never requires application changes" holds for real: a new GPU node is a LiteLLM config edit.
- Per-application virtual keys, budgets, rate limits and spend logs come from LiteLLM instead of being rebuilt — which is what audit findings S4 and S5 actually need in a clinical deployment.
- Provider failover becomes expressible, because the Gateway no longer needs to know how many providers exist.
- The Gateway stays small enough that a hospital can audit it, which was ADR-0001's premise.
- Model routing decisions are made by the component that can see every backend's health, latency and cost. The Gateway cannot see those without duplicating LiteLLM's state.

### Negative

- Two configuration files are now coupled by name, and nothing external enforces that coupling. **A startup alias check is mandatory, not optional** (task 4 of the migration below), or a typo silently routes to the wrong model.
- LiteLLM becomes a hard dependency on the request path, not an optional one. `configs/futurekind.yaml` already calls it the gateway; this ADR removes the reading in which it could be skipped. Local-first is unaffected — LiteLLM runs in the same compose project.
- Some features become harder to reach. Streaming, per-token cancellation and true load-aware routing depend on upstream support in LiteLLM. If a real clinical requirement cannot be met there, this ADR must be amended — the answer is not to quietly build a second router.
- Model provenance in responses is now LiteLLM-supplied, so the Gateway reports what it was told rather than what it chose. The audit record must say which alias was requested *and* which model answered.
- Work already done is partly redundant: the fallback-chain machinery in `routing.py` and `service.py` overlaps LiteLLM's retries. It is retained for now because removing it changes behaviour, and it is the correct home for *skill-level* degradation policy. This is recorded as debt, not as a feature.

---

## Migration Strategy

Four steps, each independently shippable. This ADR authorises steps 1 and 2 only.

**Step 1 — Remove infrastructure leakage. (Done with this ADR.)**
Delete the `model` field from the public request schema and the catalogue's model-id selector path. Applications specify a skill. Tests that asserted model pinning are updated to assert the new architecture, since the behaviour they described is the behaviour this ADR removes. Model ids remain in the catalogue as internal data, pending step 4.

**Step 2 — Introduce the three concepts as explicit boundaries. (Done with this ADR.)**
Add `Skill` to the catalogue and to resolution; retain `capability` as the technical layer; document `Provider` as the execution backend. Add guard tests so the boundary cannot silently re-fuse: a request naming a model must be rejected, and a skill must resolve without any provider being registered. No provider is implemented.

**Step 3 — Alias the catalogue to LiteLLM. (Not yet authorised.)**
Replace `model: qwen3:14b` with `alias: fk-reasoning` in `models.yaml`. Add the startup check that every referenced alias exists in the LiteLLM model list, failing start with the alias name and the file that named it. This is the step that makes Option A real, and it is the step that finally closes audit finding 3.

**Step 4 — Move provider mechanics to LiteLLM and shrink the Gateway. (Not yet authorised.)**
Implement one provider — LiteLLM — against the existing `Provider` contract. Delete the Gateway's per-model fallback chain in favour of LiteLLM's retries, keeping only skill-level degradation policy in the Gateway. Point `compose.yaml` at the Gateway and remove direct model-backend exposure from the application path. Revisit audit findings S4, S5, S6 and S12 here, because virtual keys and spend logs are LiteLLM features the Gateway merely has to require.

Deliberately *not* in this migration: an `ollama` provider, an OpenAI provider, provider health checks in the Gateway, a per-provider credential store, and any second model table. Each of those is the shape Option B would take, and each is refused by this decision.

---

## Open Items

Deferred with reasons, so they are not mistaken for completion:

- **`capability` remains on the public request.** This ADR removes model selection; capability is technical rather than infrastructural, and removing it was not authorised. Under this ADR it should become an internal refinement, so one application-facing selector exists. Scheduled for Sprint 2.
- **No `tier` axis yet.** `default`/`fast`/`reasoning` conflate service class with task type (architecture review finding 3). Splitting them needs a capability set (`chat`, `vision`, `embedding`) that cannot be populated until step 3 makes non-chat aliases meaningful. Adding a `tier` field today would be an abstraction with no data behind it.
- **Skill is not a metrics label yet.** Per-skill counters are the natural next step for capacity and audit work, but adding a label before any application calls a skill produces an empty axis.
- **`ProviderRegistry` stays keyed by a bare string.** Under Option A there is exactly one provider on the request path, so a provider-target abstraction has no second occupant to justify it yet. It becomes necessary the moment a non-LiteLLM backend is legitimately required.

---

**FutureKind Principle**

> The Gateway decides *what was asked for* and *who was allowed to ask*. LiteLLM decides *what ran*. A hospital must be able to understand that sentence by reading two files.
