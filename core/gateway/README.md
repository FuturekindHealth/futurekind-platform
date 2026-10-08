# FutureKind Gateway

The Gateway is the single entry point for every AI request inside FutureKind.

An application names the work it is doing — a **skill** such as
`radiology-report` — and receives a completion. It never names a model, a
provider or an endpoint, and it is never told which one to prefer.

Ownership is fixed by [ADR-0002](../../docs/adr/ADR-0002-Gateway-vs-LiteLLM.md),
described end to end in
[docs/architecture/gateway-routing.md](../../docs/architecture/gateway-routing.md)
and written down, key by key, in
[docs/architecture/gateway-policy.md](../../docs/architecture/gateway-policy.md).

## Gateway owns

- **Skills** — the application's stated intent, and the only selector a request may carry
- **Policy** — declarative, per skill, in `models.yaml`: clinical risk level, approval
  and audit requirements, whether a lesser class may answer, and the request limits
  that skill runs under. A high or critical risk skill that leaves these unstated is
  refused at startup rather than defaulted
- **Authorization** — who may call, and which application a request came from
- **Audit** — one `skill_audit` record per audited skill, naming the risk, the alias
  asked for, and the model that answered; whether or not the request succeeded
- **Clinical context** — the patient-care framing a request carries into the platform
- **Observability** — structured logs, Prometheus metrics at `GET /metrics`, health
  and readiness. Distributed tracing is **not** implemented: no OpenTelemetry SDK is
  wired and no collector is deployed, so nothing here should be read as claiming
  spans (`docs/CONSTITUTION.md §7` row 4; `ROADMAP.md` 8.5)

A request may not carry policy: `allow_downgrade` in a body is rejected, because a
caller that can relax the rules applied to it has no rules.

The Gateway never logs prompt or completion text. See
`observability/logging.py`.

## LiteLLM owns

- Model aliases
- Provider routing and model routing
- Retries and provider failover
- Cost tracking and per-application budgets — **not enabled in this build**:
  `disable_spend_logs: true` in `configs/litellm/config.yaml` keeps LiteLLM's spend
  tables empty, and there are no virtual keys to attach a budget to (ADR-0004).
  This is stated here rather than in a footnote because the absence is invisible
  from the routing, which works

**The Gateway must never become a second LiteLLM.** A missing feature in
LiteLLM is an argument for an ADR, not for a parallel implementation here.

Applications must never communicate directly with LiteLLM or any LLM provider.
The Gateway owns every AI interaction — and within that ownership, it owns the
*why* and the *who*, while LiteLLM owns the *what ran*.

## What is wired today

`LiteLLMProvider` is the Gateway's only transport, and every row in
`models.yaml` routes through it. A request is addressed to LiteLLM **by alias**
(`fk-default`), never by a weights id; LiteLLM decides what that alias means
today. Before serving, the Gateway compares every alias in its catalogue with
`configs/litellm/config.yaml` and **refuses to start** if a name is missing —
the two files have to say the same thing, and neither is trusted on assertion.

Two doors, one rule book:

| Door | Dialect | `model` means |
| --- | --- | --- |
| `POST /chat` | FutureKind | not accepted; use `skill` |
| `POST /v1/chat/completions` | OpenAI | a **skill** name, from `GET /v1/models` |

Both call `GatewayService.handle`, so route resolution, policy enforcement and
the audit record happen in one order for both. The `/v1` door exists so an
interface such as Open WebUI can be pointed at the platform's own address
instead of at LiteLLM. `stream: true` is refused with `501` there until
streaming has a specification (SPEC-15-03).

## Running it

```bash
# From a checkout: the catalogue and the LiteLLM file are discovered by walking up.
futurekind-gateway                     # or: python -m futurekind_gateway

# What it needs to answer anything:
#   FK_GATEWAY_API_KEYS          application credentials (required in practice)
#   FK_GATEWAY_LITELLM_BASE_URL  e.g. http://fk-litellm:4000 (no default is guessed)
#   FK_GATEWAY_LITELLM_API_KEY   LiteLLM's master key — a different secret
#   FK_GATEWAY_LITELLM_CONFIG    path to configs/litellm/config.yaml
```

`compose.yaml` starts it under the `ai` profile with those four values, mounts
`models.yaml` and `configs/litellm/config.yaml` read-only (a clinical routing
change is an operator edit and a restart, not an image rebuild), and publishes
8100 while LiteLLM keeps no host port at all. `sh
scripts/doctor/check-ai.sh` then proves the path end to end, including that
LiteLLM is *not* reachable from the host.
