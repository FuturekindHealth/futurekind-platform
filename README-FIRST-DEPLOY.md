# FutureKind — First Deployment

Three profiles, in this order. Each one is a step an operator can verify before
the next, because a platform that deploys in one gulp reports nothing when it fails.

## 1. Prepare

```bash
cp .env.example .env
```

Change these four before anything starts. They are placeholders in the example
file, and `configs/litellm/config.yaml` and `compose.yaml` both read them:

| Variable | Why it matters |
| --- | --- |
| `POSTGRES_PASSWORD` | holds the EHR and LiteLLM's own state |
| `LITELLM_MASTER_KEY` | the credential the Gateway presents upstream |
| `FK_GATEWAY_API_KEYS` | the credential every application and the interface presents to the Gateway |
| `OPENWEBUI_SECRET_KEY` | signs interface sessions |

`FK_RUNTIME` is where runtime data lives. It must not be inside the repository
(`docs/ARCHITECTURE.md:202-214`).

```bash
mkdir -p "$FK_RUNTIME"/{postgres,redis,qdrant,openwebui}
```

## 2. Infrastructure

```bash
docker compose --profile core up -d
docker ps
```

Three containers, all healthy: `fk-postgres`, `fk-redis`, `fk-qdrant`.

## 3. The AI path

```bash
docker compose --profile core --profile ai up -d --build
```

`--build` the first time: `fk-gateway` is built from `core/gateway/Dockerfile`.
Five containers now — the three above plus `fk-litellm` and `fk-gateway`.

The Gateway starts only after LiteLLM is healthy, and it starts or it does not: if
an alias in `core/gateway/models.yaml` is missing from
`configs/litellm/config.yaml`, the container exits and names both files
(`docs/SPECIFICATION.md` SPEC-07-03). That refusal is the deployment telling you
about a two-file mistake before a clinician finds out.

Verify from the host:

```bash
curl -s http://localhost:8100/health/ready
curl -s -H "Authorization: Bearer $FK_GATEWAY_API_KEYS" http://localhost:8100/v1/models
sh scripts/doctor/check-ai.sh
```

The doctor script checks four things, and the fourth is the one people skip: it
asserts that `localhost:4000` is **closed** to the host. LiteLLM publishes no port
here on purpose — all AI traffic passes through the Gateway
(`docs/ARCHITECTURE.md:106`), and a second address is a second entry point.

To see LiteLLM for yourself, go through the network it lives on:

```bash
docker compose exec litellm wget -qO- http://localhost:4000/health/liveliness
```

## 4. The interface

```bash
docker compose --profile core --profile ai --profile interface up -d
```

Open WebUI is configured with `OPENAI_API_BASE_URL=http://fk-gateway:8100/v1`. It
lists the platform's **skills** in its model picker and talks to nothing else. One
limitation to know before a clinician discovers it: the Gateway does not stream yet,
so set the interface to non-streaming responses (SPEC-15-03 owns that work).

## Changing a routing table

`core/gateway/models.yaml` is mounted read-only, so an edit and

```bash
docker compose --profile ai up -d --no-build gateway
```

apply a new skill, policy or alias without rebuilding an image. Add the matching
`model_name` to `configs/litellm/config.yaml` in the same change, or the Gateway
will refuse to start.

## What this deployment does not include

Monitoring, the vector knowledge services and Langfuse tracing.
`configs/futurekind.yaml` names each of those `planned`, which is the honest word:
compose starts no collector, no Grafana and no trace store, so the Gateway's
`GET /metrics` is an endpoint nothing scrapes yet. The applications that use this
platform — CARE ERP, the Radiology Copilot — are separate; `apps/radiology_copilot/`
is documented and tested but is not a service in this compose tree.
