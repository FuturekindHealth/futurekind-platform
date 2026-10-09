# FutureKind Platform Specification

**Version:** 0.1
**Status:** Canonical draft — binds implementation, does not bind ADRs
**Date:** 2026-10-07
**Integrates:** [CONSTITUTION.md](CONSTITUTION.md), [DOMAIN_MODEL.md](DOMAIN_MODEL.md),
[ARCHITECTURE.md](ARCHITECTURE.md), [ADR-0001](adr/ADR-0001-Local-First-AI.md),
[ADR-0002](adr/ADR-0002-Gateway-vs-LiteLLM.md)
**Is not:** an ADR (it records no choice among alternatives), a README, or an
implementation plan.
**Citation form for future ADRs:** `SPEC-<§>-<nn>` — e.g. `SPEC-10-03`. An ADR that
changes a requirement must cite the requirement it changes.

---

## 0. Reading this specification

### 0.1 Where it sits

```
CONSTITUTION.md      why, and what may never be traded        — may not be violated
   ↓
ADRs                 which choice was made, and why           — bind this spec where decided
   ↓
THIS SPECIFICATION   what the platform is, normatively        — binds implementations
   ↓
ARCHITECTURE.md      how it is arranged (descriptive)
DOMAIN_MODEL.md      what every thing is called (binding on naming)
   ↓
code, configuration, logs
```

Two consequences, stated because they will otherwise be argued about:

- Where this document says **SHALL** and no ADR has decided the point, the requirement
  is marked `[PROVISIONAL]`: it binds implementation, but it needs ratification in the
  ADR recommended beside it. A specification may not settle a decision silently that
  the platform has only ever argued in a design note.
- Where this document and `ARCHITECTURE.md` disagree, `ARCHITECTURE.md` is stale,
  except on naming, where `DOMAIN_MODEL.md` wins.

### 0.2 Notation

| Word | Meaning |
| --- | --- |
| **SHALL** | Conforming implementations must satisfy it. A violation is a defect. |
| **SHOULD** | Conforming implementations may depart with a written reason. |
| **MAY** | Permitted, neither required nor discouraged. |
| `[BUILT]` | Implemented and tested today, in `core/gateway/`. |
| `[PARTIAL]` | Implemented, but does not yet do what the requirement describes. |
| `[PLANNED]` | No code exists; the requirement is a contract for future work. |
| `[BLOCKED]` | Cannot proceed until a named decision is made. Owner named in §17. |
| `[PROVISIONAL]` | Normative here, awaiting the ADR listed beside it. |

Statuses are not decoration. They are the reason this specification can be trusted
over a document that describes the platform as it is intended to be.

---

## 1. Platform purpose

**SPEC-01-01.** FutureKind SHALL provide AI assistance to clinicians inside a
hospital's own infrastructure, while leaving clinical responsibility with a named
human and patient-data custody with the hospital.
*Ratified by:* Constitution §1; ADR-0001 `:54`. `[PLANNED]` — custody is asserted but
not enforceable today (SPEC-10-06, SPEC-11-05).

**SPEC-01-02 [PROVISIONAL].** FutureKind SHALL be useful when the internet is
unavailable. Cloud inference SHALL be an optional extension whose absence degrades
quality, never availability.
*Rationale:* Constitution P7; ADR-0001 rejected cloud-first (`:48`).
*Current state:* no code depends on the internet, so this holds by accident; it
becomes a requirement the first time an extension is added. `[PARTIAL]`

**SPEC-01-03.** The platform SHALL NOT be an application.
*Source:* `ARCHITECTURE.md:12-14`. An application is a *consumer* of this platform
(SPEC-04-02), and no component here may present itself as the clinician's workflow
surface.

**SPEC-01-04.** Every requirement in this specification SHALL be traceable to a
principle in `CONSTITUTION.md` or to an ADR. A requirement with neither is a wish and
must be deleted or promoted to an ADR.

---

## 2. System boundaries

### 2.1 The one AI boundary

```
            clinical staff and patients
                        │
   Applications (CARE ERP, Radiology, Pathology, Portal, WhatsApp, Voice)
                        │  ← the only public interface of this platform
        ══════════ TRUST BOUNDARY ══════════
                        │  POST /chat  { skill, messages, … }
                    Gateway          permission · policy · provenance · privacy
                        │  alias
                      LiteLLM        model choice · retries · failover · cost
                        │
                  Providers          transport
                        │
                      Models         compute
                        │
            GPU node, hospital-owned
```

**SPEC-02-01.** All AI traffic SHALL pass through the Gateway.
*Source:* `ARCHITECTURE.md:106`; Constitution P16.
**Current conformance: YES, as of Sprint 6 (2026-10-07).** `compose.yaml` declares a
`gateway` service with a published port (`:127` `8100:8100`), mounts its catalogue
and LiteLLM's alias file read-only, and depends on a healthy LiteLLM; LiteLLM's host
publish was removed in the same change (`:77` is now `expose:` only), so an
application that wants a model has one address (`:8100`) and no second one.
`scripts/doctor/check-ai.sh` asserts both
halves, including that `localhost:4000` does **not** answer from the host.
`[BUILT]` for the manifest. One caveat stays honest: the manifest has never been
executed — no Docker daemon exists in this development environment — so what is
proved is the file's shape and the Gateway's behaviour over real sockets
(`core/gateway/tests/test_end_to_end.py`), not a `docker compose up`.

**SPEC-02-02.** An application SHALL NOT hold a credential to any model backend.
Provider credentials SHALL exist only in LiteLLM's configuration and the host's
environment, never in the Gateway, an application, or this repository.
*Source:* ADR-0002 (`:146` refuses per-provider credentials in the Gateway);
Constitution P4, P11. `[BUILT]` — the Gateway holds LiteLLM's master key as its own
upstream credential and never exposes it (`config.public_dict` reports presence, not
value), and with no published LiteLLM port there is no address an application could
put that key in.

**SPEC-02-03.** A component below the trust boundary SHALL NOT learn a skill name, a
clinical risk level, or a patient identifier.
*Source:* `gateway-routing.md` (LiteLLM "Forbidden"); Constitution P14. `[BUILT]` —
`ChatRequest` carries the resolved alias, messages, sampling and extras only, and
`tests/test_end_to_end.py` reads the alias off the far side of a real socket.

**SPEC-02-04.** The platform SHALL NOT be the origin of truth for clinical data. The
EHR is; FutureKind reads and drafts. `[PLANNED]` — depends on `SPEC-12-04`.

### 2.2 Out of scope, by definition

Scheduling, billing, ordering, dispensing, documentation storage, and the
clinician-facing interface SHALL NOT be provided by this platform. A feature request
that requires them is a request for an application, not a component here.

---

## 3. Core concepts

Names, owners and permissions are defined by `DOMAIN_MODEL.md`; this section states
only what each concept is *allowed to do*, which is the specification's contribution.

| Concept | May be named in a request | May appear in a response | May be chosen by an operator | Enforcement |
| --- | --- | --- | --- | --- |
| **Skill** | SHALL | SHALL | SHALL (`models.yaml:39-102`) | `catalog.Skill.from_raw` `[BUILT]` |
| **Capability** | MAY, legacy only — scheduled for removal | SHALL | SHALL | `ModelEntry` key `[BUILT]` |
| **Policy** | SHALL NOT | SHALL (governance fields only) | SHALL | `POLICY_KEYS` + startup validation `[BUILT]` |
| **Alias** | SHALL NOT | SHALL NOT — log field only | SHALL | `ModelEntry.alias` uniqueness `[BUILT]`; existence check `[PLANNED]` |
| **Provider** | SHALL NOT | SHALL (provenance) | SHALL NOT — Services own it | `ProviderRegistry` `[PARTIAL]` |
| **Model** | SHALL NOT | SHALL (provenance) | SHALL NOT — LiteLLM chooses | ADR-0002 rule 1 `[BUILT]` |
| **Agent** | SHALL NOT | SHALL NOT | SHALL (clinical owner) | no code yet `[PLANNED]` |
| **Hospital** | SHALL NOT | SHALL NOT | SHALL | no identifier exists `[BLOCKED]` (SPEC-10-06) |

**SPEC-03-01.** A concept SHALL have exactly one name, one owner and one definition
across code, configuration and documentation, or it SHALL NOT enter the codebase.
*Source:* Constitution P18; `DOMAIN_MODEL.md`.

**SPEC-03-02.** A request body SHALL NOT be able to widen any protection applied to
it. `extra="forbid"` on `ChatRequestSchema` and the rejection of policy fields are the
mechanism; a new field SHALL be refused by the same rule, not by convention. `[BUILT]`
— guarded by `test_no_policy_field_is_accepted_from_a_caller`.

**SPEC-03-03.** Vocabulary SHALL NOT name infrastructure. A public concept named after
a product, a vendor or a model generation SHALL be renamed. `configs/futurekind.yaml`
`ai.gateway: LiteLLM` was the live case and is now closed (Sprint 6: `:40`
`gateway: FutureKind Gateway`, `:42` `routing: LiteLLM`, per `DOMAIN_MODEL.md` R1 and
`CONSTITUTION.md §7` row 6). `ai.interface: Open WebUI` (`:44`) remains: a product
name sitting in a role slot, in the one file that declares roles — and the role is
misclassified as well (SPEC-04-03 puts a clinician's window in the Services layer).
`[PARTIAL]`

---

## 4. Platform layers

Per `ARCHITECTURE.md:30-98`, with each layer's knowledge limited deliberately.

| Layer | Contents | May know | SHALL NOT know |
| --- | --- | --- | --- |
| **Applications** | CARE ERP, Radiology, Pathology, Patient Portal, WhatsApp, Voice | skill names, conversation content, its own credential | models, aliases, providers, policy internals |
| **FutureKind Core** | Gateway, Authentication, Audit, Configuration, Notifications, Permissions, SDK, Secrets | intent, policy, caller identity, the record | provider credentials, model selection, spend |
| **FutureKind Services** | LiteLLM, Qdrant, Redis, PostgreSQL, Langfuse, SearXNG, Crawl4AI, Open WebUI | models, aliases, endpoints, cost | skills, clinical context, departments |
| **Infrastructure** | Docker, Synology, Cloudflare, AI Servers | hardware | clinical meaning |

**SPEC-04-01.** Knowledge SHALL flow downward only as intent, and upward only as
result plus provenance. Any component that needs a concept belonging to the layer
below it is mis-assigned.

**SPEC-04-02.** Applications SHALL be independently deployable and may be replaced
without a platform change (`ARCHITECTURE.md:14`; Constitution P19).

**SPEC-04-03.** A user-facing interface SHALL be an Application, not a Service.
`Open WebUI` is listed in the Services layer (`ARCHITECTURE.md:74`) and as
`ai.interface` (`configs/futurekind.yaml:44`) while being the thing a clinician
looks at; if it can start a chat, it is above the trust boundary and SHALL obey
SPEC-02-01. Since Sprint 6 the deployed one does: `compose.yaml` gives the interface
`OPENAI_API_BASE_URL=http://fk-gateway:8100/v1` and no LiteLLM address at all, so the
only way it can reach a model is through the boundary. `[PROVISIONAL]` on the layer
name — ADR-0007 should place it; `[BUILT]` on the traffic rule.

**SPEC-04-04.** A layer SHALL NOT be added to accommodate a single component. Four
layers is the specification; five requires an ADR.

---

## 5. Runtime architecture

### 5.1 Processes and ports

| Process | Port | Started by | Required for |
| --- | --- | --- | --- |
| Gateway | 8100 (`compose.yaml`, published) | `compose.yaml`, profile `ai` | all AI traffic |
| LiteLLM | 4000 (`expose:` only, no host publish) | `compose.yaml`, profile `ai` | inference |
| Open WebUI | 3000 → 8080 | `compose.yaml`, profile `interface` | the interface door |
| PostgreSQL | internal | profile `core` | EHR/LiteLLM state |
| Redis | internal | profile `core` | cache/queue |
| Qdrant | 6333 (`compose.yaml:178`) | profile `core` | knowledge (unused today) |
| Prometheus / Grafana / OTel collector | — | nothing; `monitoring/*` are empty dirs | observation |

**SPEC-05-01.** The Gateway SHALL be a declared service in the canonical deployment
file, and readiness SHALL gate traffic on it. `[BUILT]` in the manifest since Sprint
6: `compose.yaml` declares it, `core/gateway/Dockerfile` healthchecks
`/health/ready` rather than `/health`, and `litellm` is a healthy dependency rather
than a peer. Built and interpolated by CI on every push; never executed against a running
stack, because no Docker daemon exists in this development environment.

**SPEC-05-02.** A request SHALL pass these stages in this order, and no stage after
the first failure shall execute:

1. authenticate the caller — `401`, or `503` when auth is required and unconfigured
   (`deps.py:88`)
2. reject undeclared fields and shapes — `422` (schema validation)
3. resolve skill → policy → capability → catalogue row — `404`/`400`
4. enforce the skill's policy — `403` approval, `422` limits
5. invoke the Provider for the resolved target — `501`/`502`/`503`/`504`
6. record provenance and audit, then answer

*Source:* Constitution P1, P2, P6, P16; implementation `GatewayService.handle` and
nothing else. `[BUILT]` — the committed Gateway suite covers this path, and both doors (`POST /chat`
and `POST /v1/chat/completions`) reach stage 3 through the same function, so a
stage cannot be reordered for one transport without failing the other's tests.

**SPEC-05-03.** The Gateway SHALL be stateless between requests. Conversation history
is the application's. `[BUILT]` *Decision:* Constitution P12 keeps workflow state out
of the platform; a server-side conversation store would require amending P12, not
merely adding a table.

**SPEC-05-04.** Every outbound call SHALL have a deadline. The platform default is
120s (`config.py:102`); a skill MAY shorten it (`request_timeout_seconds`), and SHALL
NOT lengthen it (`policy.limits_for`, `[BUILT]`).

**SPEC-05-05.** A failure SHALL be reported with the same envelope whatever its
origin — `{"error": {code, message, retryable, request_id, details}}` — and an
unhandled exception SHALL NOT expose its body (`app.py` exception handlers). `[BUILT]`

### 5.2 The catalogue as runtime configuration

**SPEC-05-06.** Routing and policy SHALL load from one file at startup and be
immutable thereafter for the process lifetime. `[BUILT]` — `ModelCatalog.load` →
`GatewaySettings.catalog_path`.

**SPEC-05-07.** Startup SHALL be non-fatal on an invalid catalogue: the process
serves `/health` and `/health/ready` and explains the exact field at fault, and every
request surface answers `503 catalog_error`. `[BUILT]` — verified live: an unsafe
policy yields a `503` whose message names the skill and the field.

---

## 6. Gateway responsibilities

The Gateway owns exactly four things (Constitution P16). Each is a contract, not a
disposition.

### 6.1 Permission

**SPEC-06-01.** Every endpoint that can cause AI work or return internal
infrastructure SHALL require a caller credential.
*Current conformance: YES.* `AuthenticatedCaller` guards `POST /chat`, both `/v1`
operations, `GET /models`, `GET /models/{capability}` and `GET /metrics`. The two
endpoints left open — `GET /health` and `GET /health/ready` — are the ones a
container runtime or load balancer has to reach without a key, so they answer with
verdicts and carry no inventory (SPEC-06-14). Constitution register rows 1 and 2
are closed. `[BUILT]`

**SPEC-06-02.** Authentication SHALL fail closed. Required auth with no configured
keys answers `503 authentication_not_configured`; there is no configuration in which
a mis-deployed Gateway serves AI anonymously. `[BUILT]`

**SPEC-06-03.** Credentials SHALL be compared without leaking their value into logs,
responses or timing differences, and a caller SHALL be identified outward only by a
digest label. `[BUILT]` — `caller_label`, `X-FK-Api-Key`/bearer.

**SPEC-06-04.** A credential SHALL be scoped to one Hospital and one Application.
`[BLOCKED]` — no Hospital or Application entity exists (`DOMAIN_MODEL.md` Hospital,
Caller); ADR-0007.

### 6.2 Policy

**SPEC-06-05.** Every skill SHALL declare `clinical_risk`; the loader SHALL refuse a
skill that does not. Risk levels: `low | moderate | high | critical`, with
`unspecified` reserved for requests that named no skill and inadmissible in
configuration. `[BUILT]`

**SPEC-06-06.** Unsafe combinations SHALL be refused at load, not at request time:
`high`/`critical` require `audit_required: true` and `allow_downgrade: false`;
`critical` requires `approval_required: true`. `[BUILT]`

**SPEC-06-07.** A skill limit SHALL only tighten a platform limit. `[BUILT]`

**SPEC-06-08.** `approval_required` SHALL refuse the request (`403`) until a
verifiable approval exists. A caller-supplied claim of approval SHALL NOT satisfy it.
`[BUILT]` as refusal; `[BLOCKED]` as feature → ADR-0005.

**SPEC-06-09.** Policy SHALL be visible to the application on every completion
(`policy.clinical_risk`, `approval_required`, `audit_required`, `allow_downgrade`)
and SHALL NOT expose numeric limits or timeouts. `[BUILT]`

### 6.3 Provenance

**SPEC-06-10.** Every completion SHALL report `skill`, `capability`, `model`,
`provider`, `selected_by`, `degraded`, `attempts` and `request_id`. `[BUILT]`

**SPEC-06-11.** A substitution of a lesser model SHALL be reported as
`degraded: true` and SHALL NOT be silent (Constitution P13). `[BUILT]` — note that no
shipped catalogue row declares a fallback, so the mechanism is currently exercised
only in tests.

**SPEC-06-12.** The Gateway SHALL NOT retry a provider failure by choosing a
different model, except by walking the chain its own policy permits. Retries as
retry-with-backoff belong to LiteLLM. `[PARTIAL]` — ADR-0002 `:126` records the
overlap as debt; removal is ADR-0002 step 4.

### 6.4 Privacy

**SPEC-06-13.** Prompt and completion text SHALL NOT appear in Gateway logs,
telemetry, error bodies or metrics labels. Field names are the control
(`FORBIDDEN_FIELDS`, `logging.py:31`), and a validation error SHALL report the rule
and its location, never the rejected value. `[BUILT]`

**SPEC-06-14.** Introspection surfaces SHALL NOT enumerate internal identifiers to
an unauthenticated caller. Two surfaces read this way, and both now hold the line:
`GET /models` requires a credential, and `GET /metrics` — whose
`fk_gateway_catalog_models{capability, provider, model}` labels are the routing
table in another format — requires one too, with Prometheus' own bearer-token scrape
config as the deployment side. The probe endpoints answer without a key and therefore
report only health verdicts: no catalogue path, no provider names, no upstream error
text. `[BUILT]`

### 6.5 The public API

| Endpoint | Purpose | Auth | What an unauthenticated reader sees |
| --- | --- | --- | --- |
| `POST /chat` | one completion by skill | yes | 401 |
| `POST /v1/chat/completions` | the same, in OpenAI's dialect (`model` = skill) | yes | 401 |
| `GET /v1/models` | the skills an interface may select | yes | 401 |
| `GET /models` | skills + policy, and the routing table | yes | 401 |
| `GET /models/{capability}` | one resolved chain | yes | 401 |
| `GET /health` | component verdicts | **no** — a probe holds no key | status, service, version, timestamp, `healthy` per component |
| `GET /health/ready` | traffic gate | **no** | ready/not-ready and the reason in words |
| `GET /metrics` | Prometheus exposition | yes | 401 |
| `GET /docs`, `/redoc`, `/openapi.json` | contract | **no** | the whole surface — see SPEC-10-04, still open |

The two `/v1` rows were authenticated from their first commit: a door built for an
interface to be pointed at is not a place to inherit an older door's defect.
`GET /v1/models` returns no provider, alias or model id; `GET /models` returns the
routing table but only to a caller that already holds a key.

`GET /health` used to report `"{n} models from {catalog.source}"` — an absolute
server path, free to anyone who could reach the port. It now reports `loaded`, and
the path a failed catalogue load names goes to the log, which is on the host.

**SPEC-06-15.** The served OpenAPI document SHALL be the contract. `[BUILT]` —
`core/gateway/openapi.yaml` (4 paths, summaries only, no `responses`, no
`securitySchemes`) is deleted, and `/openapi.json` is the only contract in the
repository. `test_openapi.py` is what makes the served document more than a
convenience: every advertised path must exist, every operation must declare responses
and a description, and the credential-bearing operations must document their
`security`. A hand-written copy could only ever be re-checked by eye, which is how it
stayed wrong for six sprints.

---

## 7. LiteLLM responsibilities

**SPEC-07-01.** LiteLLM SHALL own model aliases, model selection, provider selection,
retries, provider failover and cost tracking. The Gateway SHALL NOT reimplement any
of them. *Source:* ADR-0002 (`:97`); Constitution P7, P16.

**SPEC-07-02.** The Gateway SHALL address LiteLLM by **Alias**, and an alias SHALL be
the only model-facing string the Gateway holds once step 3 lands. Since Sprint 6 the
Gateway *sends* the alias and nothing else (`ModelEntry.target`,
`tests/test_end_to_end.py` reads it off the far side of a socket); the catalogue
still *carries* `provider` and `model` per row (`core/gateway/models.yaml:104-127`)
as declared inventory for provenance and for the drift comparison below.
`[PARTIAL]` — the sending half is built, the deletion is step 3.

**SPEC-07-03.** Startup SHALL fail when a referenced alias does not exist at
LiteLLM. ADR-0002 `:122` calls this "mandatory, not optional". `[BUILT]` since
Sprint 6: `litellm_config.py` reads `configs/litellm/config.yaml`, and
`app.verify_alias_contract` raises `ConfigurationError` naming every alias at fault
before the process serves anything — the one fatal startup refusal in a process that
is otherwise deliberately non-fatal. A row that routes to LiteLLM with no alias at
all is refused on the same path, because sending the weights id instead would put
model selection back in the Gateway. A *drifted* `model:` string is a warning
(`alias_model_drift`), not a refusal: it changes what the audit line claims, not
where the request goes.

**SPEC-07-04.** Alias names SHALL live in exactly one place per side and SHALL be
checked against each other, not copied by hand into a third document. They are in
two files — `configs/litellm/config.yaml:3,8,13` and
`core/gateway/models.yaml:108,116,124` — and SPEC-07-03's check now enforces the
coupling at startup, with `tests/test_litellm_config.py::test_the_two_shipped_files_agree`
holding the repository to it.

**SPEC-07-05.** LiteLLM SHALL NOT be reachable from an application. `[BUILT]` since
Sprint 6: `compose.yaml` gives litellm `expose:` and no published port, the Gateway
publishes 8100, and `scripts/doctor/check-ai.sh` fails the deployment if
`localhost:4000` answers from the host at all.

**SPEC-07-06.** Spend logs SHALL NOT be disabled in a deployment that bills, budgets
or audits AI use. `configs/litellm/config.yaml:22` currently sets
`disable_spend_logs: true`, which contradicts `ARCHITECTURE.md`'s ownership of Audit
(`:118`) — the record that would answer "what did this cost, for whom" is switched
off. `[PROVISIONAL]` → ADR-0003.

**SPEC-07-07.** LiteLLM SHALL run in the same installation as its Gateway. A hosted
LiteLLM would violate Constitution P4 and P7 simultaneously.

---

## 8. Clinical object model

No class, table or schema is specified here: `DOMAIN_MODEL.md` records every one of
these objects as `[ABSENT]`, and inventing their persistence would be implementation
through a specification. What the specification does fix is the **contract each must
satisfy**, so the ADR that designs them cannot quietly weaken the principle.

**SPEC-08-01 (Observation).** A clinical statement SHALL be representable as
individually checkable parts, and a clinician SHALL be able to accept or reject one
part without rejecting its document. *Prerequisite:* none code-wise; requires the
clinical owner's definition of an observation. `[PLANNED]` → ADR-0006.

**SPEC-08-02 (Impression).** A document's conclusion SHALL be distinguishable from
the observations supporting it. Today `models.yaml:58` calls the artefact an
"impression" and `:48` calls its sibling a "report"; the naming SHALL be reconciled
(`DOMAIN_MODEL.md` R5) before either becomes an entity.

**SPEC-08-03 (Report).** A Report SHALL reach a final state only through a human
transition. No platform state SHALL be able to mark a report final. `[PLANNED]` →
ADR-0005.

**SPEC-08-04 (Approval).** An approval SHALL record who, when, of which version of
which statement, and SHALL be created by a person, not asserted by a caller. Until
such an object exists, `approval_required` SHALL refuse (SPEC-06-08). `[BLOCKED]` →
ADR-0005.

**SPEC-08-05 (Patient Context).** Every clinical artefact SHALL be attributable to
one Patient Context and one Hospital. Nothing in the platform can express this today:
no identifier exists, and the only MRN-shaped string in the repository is a test
fixture invented to prove PHI does not leak (`test_api_chat.py:254`). `[BLOCKED]` →
ADR-0007. Until it is unblocked, any AI surface that would need it SHALL NOT ship.

**SPEC-08-06 (Knowledge).** A clinical statement SHALL cite its basis or be labelled
as inference (Constitution P13). Crawled or searched material SHALL be candidate
knowledge and SHALL NOT be admissible until a clinical owner adopts it, with origin
and version retained. `[PLANNED]` → ADR-0006. Note the ordering constraint: no
retrieval surface should be built before SPEC-08-05, or citations will point at
patients the platform cannot identify.

**SPEC-08-07 (Workflow).** Workflow ownership SHALL be decided before any workflow
engine is built in this repository: FutureKind participates, or CARE ERP owns and
FutureKind is called. `DOMAIN_MODEL.md` Q5 records the question; the constitution's
answer in one direction is P12. `[BLOCKED]`

**SPEC-08-08 (Agent).** An Agent SHALL own prompts, style, templates and a set of
Skills, and SHALL NOT appear in a Gateway request. The sixteen placeholder files under
`agents/` were deleted on 2026-10-08, so nothing contradicts this yet; when an Agent is
authored, its schema SHALL NOT permit a routing field (`DOMAIN_MODEL.md` R4). `[PLANNED]`

**SPEC-08-09.** No clinical object SHALL be persisted by the Gateway. It records
decisions about requests; the EHR records the patient.

---

## 9. Audit model

**SPEC-09-01.** The platform SHALL emit one audit record per audited request,
whatever the outcome, carrying at least: request id, caller label, skill, capability,
clinical risk, alias requested, model that answered, provider, attempts, degraded,
outcome. `[BUILT]` — `service.py:316` `skill_audit`; verified live, including the
failure path (`answered: false`, alias present, no prompt text).

**SPEC-09-02.** An audit **record** SHALL be distinguished from an audit **transport**.
A JSON line on stdout is transport. A record has retention, ownership, integrity and a
retrieval path. **FutureKind has transport and no record.** `[BLOCKED]` → ADR-0003.

**SPEC-09-03.** A component SHALL NOT claim audit or tracing capability it does not
provide. `[BUILT]` as of 2026-10-08 — the wording change this rule needed is what
happened: `core/gateway/README.md:26` now names logs, metrics and health and states
that distributed tracing is not implemented; `configs/futurekind.yaml` marks
`prometheus`, `grafana`, `opentelemetry` and `tracing` `planned` instead of `true`;
`docs/ARCHITECTURE.md` opens with a table saying which boxes are built and which are
not; and `disable_spend_logs: true` is annotated with why cost tracking is absent
rather than left to read as a LiteLLM feature. `core/audit/` and `monitoring/` no
longer exist even as empty directories. The capability is still missing — the rule
is that the documents must say so, and now they do.

**SPEC-09-04.** Retention period, export format and per-Hospital access SHALL be
declared by ADR-0003. A hospital SHALL be able to take its own audit record with it
when it leaves (Constitution P14).

**SPEC-09-05.** Policy changes SHALL be attributable. Today `models.yaml` is edited in
place, so "what was the risk classification when this answer was given" is answerable
only from the log, never from the configuration (`gateway-policy.md` debt). The
specification requires the audit record to carry enough to answer it — and §13 makes
that versioning a first-class object.

**SPEC-09-06.** An audit record SHALL NOT contain clinical text (SPEC-06-13). Its
purpose is accountability, not documentation; the two stores SHALL NOT be merged.

---

## 10. Security model

**SPEC-10-01.** Authorization decisions SHALL live in the Gateway, so that a change
of application, model or provider cannot become a change of policy. `[BUILT]` for
`/chat`; `[BLOCKED]` for scope (SPEC-06-04).

**SPEC-10-02.** Every protection SHALL default to on. `require_auth` SHALL default
true (`config.py:100`); where it may be disabled for development, a deployment that
serves clinical work SHALL NOT be startable in that state, and the state SHALL be
reported by `/health` — which it already is (`routes_health.py:57`). `[PARTIAL]` —
the off-switch is currently indistinguishable between a laptop and a hospital.
`[PROVISIONAL]` → ADR-0007.

**SPEC-10-03.** Secrets SHALL NOT be committed, and SHALL NOT appear in compose files
(`ARCHITECTURE.md:196-198`). `[BUILT]` in letter (compose uses `${...}` references) and
in the example too, since 2026-10-08: `.env.example` carries no key at all, real or
shaped-like-one. Every secret slot is `<generated: openssl rand -hex 32>` with the
command written above it, because the earlier form — a placeholder in the exact shape
of a live master key — was the credential a deployment got by copying the example and
changing nothing. Hosts are the same story: `OLLAMA_PRIMARY` is given as a shape
(`http://<host-running-ollama>:11434`), not an address, and the unused
`OLLAMA_SECONDARY` is gone rather than documented as a capability.

**SPEC-10-04.** The OpenAPI document is a discovery surface. Serving `/docs` and
`/openapi.json` unauthenticated publishes the platform's full attack surface to
anything that can reach the port. SHALL be behind the same credential as the
endpoints it describes. `[PROVISIONAL]` → ADR-0004.

**SPEC-10-05.** PHI discipline SHALL be enforced by field-name denylist at the logging
boundary, not by reviewer diligence (SPEC-06-13). `[BUILT]`

**SPEC-10-06.** A Hospital SHALL have an identifier, and every credential SHALL be
scoped to it, so that custody claims become enforceable rather than architectural.
`[BLOCKED]` → ADR-0007. This is the requirement that makes ADR-0001's promise
testable; until it exists, "the hospital controls its data" is true by deployment
geometry, not by system design.

**SPEC-10-07.** Network exposure SHALL default to internal. A published port is an
exception requiring a reason; `4000:4000` on LiteLLM (SPEC-07-05) is currently that
exception without the reason recorded.

---

## 11. Deployment model

**SPEC-11-01.** One Installation SHALL be described by exactly one authoritative
manifest. `[BUILT]` since 2026-10-08: `compose/compose.core.yaml` defined postgres,
redis and qdrant a second time with a different data root (`../data/postgres`) and a
looser pin (`qdrant:latest`), and nothing referenced it; it is deleted, and
`compose.yaml` is the only compose file in the repository. The rule is now satisfied
by there being nothing to argue with, which is weaker than satisfying it by
generation — a second tree can still be added by accident, and CI is where that would
be caught.

**SPEC-11-02.** The canonical stack SHALL include the Gateway (SPEC-05-01). `[BUILT]`
since Sprint 6, with the same caveat as SPEC-02-01: the manifest is written and
parsed, never executed. `/health/ready` remains the traffic gate, and the container
healthcheck in `core/gateway/Dockerfile` asks that endpoint rather than `/health`, so
a Gateway reporting a problem is not restarted for reporting it.

**SPEC-11-03.** All runtime data SHALL live outside the image and outside Git, under
the `FK_RUNTIME` root (`FK_RUNTIME` in `.env.example`; `ARCHITECTURE.md:202-214`). `[BUILT]` for
infra services; the Gateway writes nothing to disk, which is compliant by absence.

**SPEC-11-04.** Deployment targets are `docker`, `synology`, `kubernetes` (planned),
`cloud` (planned) (`configs/futurekind.yaml:24-32`) and SHALL NOT change the platform
architecture (`ARCHITECTURE.md:230`). Note that `deployment/` is an empty directory
while `platform.deployment:` means install channel — `DOMAIN_MODEL.md` R8 renames the
key to `platform.targets:` so one word stops doing two jobs.

**SPEC-11-05.** Configuration SHALL have one source per kind of value, and each kind
SHALL name its source. `ARCHITECTURE.md:168-172`'s "one configuration source: `.env`,
no duplicated settings" is false as written — routing and policy live in
`models.yaml`, platform metadata in `configs/futurekind.yaml`, service config in
`FK_GATEWAY_*`, and the alias half of the contract lives in a file the Gateway now
reads but does not own (`configs/litellm/config.yaml`). As of Sprint 6
`.env.example` names all sixteen `FK_GATEWAY_*` variables the Gateway reads
(`config.py:144-175`: `MODELS_PATH`, `HOST`, `PORT`, `DEFAULT_CAPABILITY`,
`REQUIRE_AUTH`, `API_KEYS`, `REQUEST_TIMEOUT_SECONDS`, `MAX_MESSAGES`,
`MAX_CONTENT_CHARS`, `MAX_COMPLETION_TOKENS`, `LOG_LEVEL`, `JSON_LOGS`,
`SERVICE_NAME`, `LITELLM_BASE_URL`, `LITELLM_API_KEY`, `LITELLM_CONFIG`), with the
thirteen tuning keys documented rather than required.

| Kind | Authoritative source |
| --- | --- |
| Secrets, endpoints, host paths | `.env` |
| Skills, capabilities, policy, aliases | `core/gateway/models.yaml` |
| What each alias resolves to, and its params | `configs/litellm/config.yaml` — read by the Gateway at startup, never written by it |
| Platform metadata | `configs/futurekind.yaml` |
| Runtime tuning | `FK_GATEWAY_*`, listed in `.env.example` |

`[PROVISIONAL]` — the table itself needs the ADR that ratifies `.env`'s scope. Two
sources now share one name space (aliases in `models.yaml`, deployments in
`config.yaml`) and SPEC-07-03's startup check is what keeps them one contract;
"one source per kind" still has an exception, and it is now an enforced one rather
than a hoped-for one.

**SPEC-11-06.** A hospital SHALL be able to install, upgrade and remove an
Installation without a vendor action (Constitution P14). `[PARTIAL]` —
`README-FIRST-DEPLOY.md` is an install path in the order it must be run, with the
refusal cases named, and `README.md` and `SECURITY.md` are written. Still missing:
`scripts/install`, `scripts/upgrade` and `scripts/restore` hold no script. They are
deleted from the working tree — git never tracked an empty directory, so they were
a local shape rather than a shipped one — and the procedures themselves remain the
gap this requirement is `[PARTIAL]` for. Removal has no procedure written down, so
an Installation cannot yet be taken away by its owner.

---

## 12. Extension model

The platform's claim to be extensible means nothing unless the *procedure* is cheap
and the *boundaries* hold while it is followed. Four extension types, four recipes.

**SPEC-12-01: a new Skill.** Add a `models.yaml` skill stanza with a capability and a
declared `clinical_risk`. **No code change. No application change. No restart of
anything else.** `[BUILT]` — this is the cheapest path in the platform and it is the
specification's proof that the design works. `platform-chat` was added this way in
Sprint 6: catalogue stanza and a restart, nothing else.

**SPEC-12-02: a new Capability or Alias.** Add a `models:` row, and add the matching
`model_name` to `configs/litellm/config.yaml` in the same change. Fallbacks SHALL be
declared as a chain the policy may narrow, not as a retry mechanism (SPEC-12-05).
`[BUILT]` — including SPEC-07-03's startup check, so an alias added on one side
only is a container that refuses to start rather than a clinical request that fails
upstream.

**SPEC-12-03: a new Provider.** Implement the `Provider` contract and register a
factory. Adding one SHALL NOT require a new abstraction — `ProviderRegistry` stays
keyed by a bare string until a second legitimate backend exists
(ADR-0002 `:157`). `[BUILT]`, and **one implementation exists**: `LiteLLMProvider`,
registered by `main.build_production_app` and nothing else. A second entry in that
registry is the event ADR-0002 `:157` reserves the abstraction question for, and
until then the Gateway speaks to models through one door.

**SPEC-12-04: a new Application.** Obtain a credential, name a skill. SHALL NOT
require a platform change, and SHALL NOT be given a LiteLLM key (SPEC-02-02).

**SPEC-12-05: degradation SHALL NOT be an extension point.** A Skill's policy MAY
narrow a chain; no extension MAY add a retry, a failover ordering or a
cost-driven choice inside the Gateway (ADR-0002 `:99`; Constitution P16).

**SPEC-12-06.** An extension that needs a new public request field SHALL require an
ADR first. Fields are how a contract is remembered; `model` is the cautionary
example (`ARCHITECTURE.md` era, removed in ADR-0002 step 1).

---

## 13. Versioning strategy

**SPEC-13-01.** Exactly one place SHALL declare the platform version, and everything
else SHALL read it. `[BUILT]` as of 2026-10-08, resolved toward the second option the
earlier draft refused to choose: **each artefact declares its own version in its
package `__init__.py`, and `[tool.hatch.version]` reads it from there** — so the wheel,
`GET /health` and the served OpenAPI document cannot disagree, which is what test pairs
(`test_openapi.py`: `info.version == __version__`) assert. The three copies that used to
contradict it are gone: the root `VERSION` file is deleted, `configs/futurekind.yaml`
keeps only `codename: Genesis` (a release line, not a number — nothing reads the file),
and `ARCHITECTURE.md` names the release line instead of restating a version. The platform
version is the git tag. A comment is not the mechanism, and the comment that used to
claim the manifest was the source now says what actually happens.

**SPEC-13-02.** Five things have independent versions and SHALL NOT be conflated:

| Artifact | Versioned by | Change requires |
| --- | --- | --- |
| Platform | `__init__.py` / release | normal release process |
| Public API (request/response/error codes) | §14 compatibility rules | ADR + migration |
| Catalogue (`models.yaml`: skills, policy, aliases) | **not yet versioned** | see SPEC-13-03 |
| Clinical doctrine (`genesis/` and `agents/` — deleted 2026-10-08; no artefacts to version yet) | not yet versioned | clinical owner's release |
| Constitution | semantic, amendment-based | ADR explaining the trade |

**SPEC-13-03.** The catalogue SHALL carry a version or hash that the audit record
includes, so a policy change is attributable (SPEC-09-05). Without it, "the system
was configured that way at the time" cannot be evidenced. `[PLANNED]` → ADR-0003
naturally owns this alongside retention.

**SPEC-13-04.** Version numbers SHALL follow semantic versioning for the public API,
and a breaking change SHALL be a major. A new Skill, a new Capability, a new Alias or
a changed risk level SHALL NOT be a platform version change — the point of the
separation is that they are configuration.

**SPEC-13-05.** Codenames (`Genesis`) SHALL identify a release line, not a
document's authority. The current ambiguity — commit `dfec7f0` "AI Genesis-A
constitution." against an empty `genesis/` (now deleted) and a live `docs/CONSTITUTION.md` — SHALL
be resolved by the platform owner (`CONSTITUTION.md §7` row 10), not by convention.

---

## 14. Compatibility rules

**SPEC-14-01.** Names an application may use — skill names, `skill`, `capability`,
`messages`, `temperature`, `max_tokens`, `stop`, `stream`, `parameters`, and the
error codes below — are a **frozen public contract**. Removing or renaming one is a
major version and requires a migration with a deprecation window. The OpenAI dialect
added in Sprint 6 freezes the same words plus one reinterpretation: on
`/v1/chat/completions`, `model` means **skill**. That mapping is now part of the
contract, so renaming a skill is a breaking change for an interface that has it in a
picker, and no future version may let `model` mean a deployment on that door.

**SPEC-14-02.** The error codes are the API. They SHALL remain stable in meaning even
as messages change:

| Code | Status | Retryable | As reported today |
| --- | --- | --- | --- |
| `unauthenticated` | 401 | no | yes |
| `approval_required` | 403 | no | yes |
| `routing_failed` | 400 | no | yes |
| `unknown_skill`, `unknown_capability` | 404 | no | yes |
| `invalid_request` | 422 | no | yes |
| `configuration_error`, `catalog_error`, `authentication_not_configured`, `not_ready` | 503 | no | yes |
| `provider_not_implemented`, `feature_not_implemented` | 501 | no | yes |
| `provider_unavailable`, `provider_rate_limited` | 502 | **yes** | yes |
| `provider_timeout` | 504 | **yes** | yes |
| `provider_authentication_failed`, `provider_request_rejected`, `provider_protocol_error` | 502 | no | **`true` — defect** |
| `http_error`, `internal_error` | 404/500 | no | yes |

`[PARTIAL]` — twenty codes are reachable in service: the thirteen `GatewayError`
subclasses in `errors.py`; `http_error` and `internal_error` from the app-level
exception handlers (`app.py:396-416`); `not_ready` from the readiness route
(`routes_health.py:171`); and four produced by the service layer's translation of a
provider failure (`service.py:_translate`, plus `provider_protocol_error` when a
provider answers with something that is not text).

Two findings, measured rather than inferred:

- **`retryable` lies for three codes.** A LiteLLM credential rejection, a refusal,
  or a malformed answer all inherit `retryable = True` from `ProviderFailedError`,
  so the envelope invites an application to retry a request the platform already
  declined. The provider-side exception knows the difference — `retryable is False`
  on `ProviderAuthenticationError` and `ProviderRequestRejectedError` — and the
  information is dropped at translation. The fix is small and changes a public
  semantic, so it is a decision rather than a correction; see §17.
- **Seven of the twenty codes exist outside the error hierarchy.** `http_error` and
  `internal_error` from the handlers, `not_ready` from one route, and the four
  provider-translation codes from the service layer — none has a class, so none has
  a declaration a reader can find. `not_ready` is the worst of them: a code invented
  in a route body appears in no document and no test but its own.

A table that lists codes nobody has promised is the same defect as the hand-written
OpenAPI stub: the document is the contract only if the code consults it.

**SPEC-14-03.** Adding a request field SHALL be minor; adding a *required* field is
major. A field that names infrastructure SHALL NOT be added at any version
(ADR-0002 rule 1).

**SPEC-14-04.** The catalogue format is versioned with the Gateway: a key the loader
does not recognise SHALL be refused, not ignored (`catalog.py` strict loading). This
is deliberately backwards-incompatible in the safe direction — a typo in a clinical
routing table fails loudly.

**SPEC-14-05.** An alias SHALL be treated as a public name between two operators
(Gateway and LiteLLM) even though it is invisible to applications: renaming one
SHALL require changing `configs/litellm/config.yaml` and `core/gateway/models.yaml`
in one atomic change, with SPEC-07-03's check preventing partial application.
`[BUILT]` — the check is the mechanism now, and `test_the_two_shipped_files_agree`
holds the repository to it.

**SPEC-14-06.** Responses SHALL NOT break on unknown fields — consumers SHALL ignore
them — while requests SHALL NOT (SPEC-03-02). One direction of strictness, chosen so
that adding information is safe and accepting new instructions is not.

The OpenAI door is a named exception, and the exception is narrower than it looks:
unknown *request* fields on `/v1/chat/completions` are ignored rather than refused,
because OpenAI clients send a long tail the platform does not model and refusing them
would break every interface. Ignored means **not forwarded** — nothing reaches a
model except what `GatewayService` puts in the provider request
(`test_sampling_knobs_travel_and_unknown_ones_are_dropped` asserts `extra == {}`).
Strictness about what a backend may be told is the property; strictness about JSON
keys was only ever its expression.

**SPEC-14-07.** A principle SHALL NOT be deprecated for convenience. Constitution
P2, P4, P11, P13 have no compatibility path; a requirement that conflicts with them
is a defect in the requirement.

---

## 15. Future evolution

**SPEC-15-01.** The next structural change SHALL be ADR-0002 step 3, not a new
feature: aliases become the only model-facing string the Gateway holds, and
`model:` is deleted from the catalogue. SPEC-07-03's check landed in Sprint 6, which
is what turns that deletion from a redesign into a removal — the coupling is already
enforced, so the column has stopped carrying routing decisions.

**SPEC-15-02.** A **tier** axis (service class separated from task type) SHALL NOT be
invented before `vision` or `embedding` aliases exist to populate it
(ADR-0002 `:154`). The specification inherits that refusal deliberately: an
abstraction with no data behind it is the most expensive kind of debt.

**SPEC-15-03.** Streaming SHALL be specified before it is implemented, and its
specification SHALL state where cancellation, timeout and audit records land, since
`501 feature_not_implemented` currently reserves the name without the semantics
(SPEC-14-01).

**SPEC-15-04.** The clinical object model (§8) is expected to change shape as the
doctrine behind it is written — `genesis/` was deleted as a placeholder, so that
authoring starts from nothing. The **requirements** in §8 are not expected to change: they
say what a clinical object must satisfy, which is the specification's proper
constitency.

**SPEC-15-05.** This specification SHALL be amended by pull request with the
requirement ID, the reason, and the constitution principle it serves. A requirement
that cannot cite one SHALL be deleted rather than defended.

**SPEC-15-06.** When SPEC-02-01, 06-01, 07-03, 09-02 and 10-06 are satisfied, the
platform's security posture becomes *assertable* rather than architectural, and this
document may move from "Canonical draft" to "Version 1.0". Those five are the
specification's own definition of done. **Three are now met** — SPEC-02-01 (the
Gateway is the deployed entry point and LiteLLM has no host port), SPEC-07-03 (alias
coupling is enforced at startup) and SPEC-06-01 (every surface naming infrastructure
requires a credential, closed 2026-10-08). Two remain: SPEC-09-02 (audit records that
outlive the process) and SPEC-10-06 (a Hospital identifier). Both need capability, not
wording — which is what this section was written to discover.

---

## 16. What can now be implemented safely

Sprint 6 executed two of the five items this section listed on 2026-10-07: the
Gateway became the deployed entry point (SPEC-02-01, 05-01, 11-02), and one more
skill was added entirely in configuration (SPEC-12-01, platform-chat). What is
unblocked now, with every decision it needs already taken:

1. **~~Authenticate the introspection surfaces, and remove `model` from the catalogue
   metric.~~** SPEC-06-01, 06-14, 10-04; register rows 1–3 of `CONSTITUTION.md §7`.
   **Done 2026-10-08, by the second option the earlier draft did not take.** The
   surfaces were authenticated rather than stripped: `/models`,
   `/models/{capability}` and `/metrics` now require the credential `/chat` always
   did, and the probe endpoints were reduced to verdicts instead of losing their
   detail wholesale. The `fk_gateway_catalog_models{capability, provider, model}`
   label set survives *because* the scrape now needs a key — an operator's Prometheus
   is entitled to the routing table, an anonymous reader is not. Blast radius as
   predicted: three route signatures, one response model, and their tests.
   SPEC-10-04 (`/docs`, `/redoc`, `/openapi.json`) is the part of this item that is
   **not** done, and it is deliberately left for ADR-0004.
2. **Correct `retryable` for the three provider-translation codes** (§14). The
   provider exceptions already know the answer; the translation drops it. One
   decision is needed because the field is part of the frozen contract, not because
   the fix is unclear.
3. **Delete `model:` from the catalogue** (SPEC-07-02, 15-01). ADR-0002 step 3 was
   blocked on "the check needs LiteLLM integration"; the integration and the check
   both exist now, so what remains is authorisation, then a deletion.
4. **More skills, aliases and capability rows, in configuration only.** The path is
   proved end to end and the startup check now catches a half-made change, which is
   exactly what made adding an alias unsafe before.
5. **The clinical object *definitions*, not their persistence.** SPEC-08-01…08-08
   constrain what an object must satisfy; the clinical owner can satisfy those in
   in prose today, with no code, no ADR and no `genesis/` — the tree is deleted, so
   this is an empty page rather than a folder of empty files.
6. **Wording honesty in the remaining documents.** SPEC-09-03, 13-01, 14-07 and
   register rows 4, 6 and 7 of `CONSTITUTION.md §7`; `ARCHITECTURE.md:150-154`'s
   "Model Router / LLM" chain still names a hop the platform does not have, and the audit and
   tracing claims still do not.

The common shape has not changed since Sprint 5 wrote it, and Sprint 6 is evidence
for it rather than against it: **the remaining safe work is enforcement and honesty,
not capability.** Adding the one capability that mattered — a working request path —
required no new concept, no new abstraction, and no second implementation of
anything LiteLLM already owns.

---

## 17. What must still wait

| Waits for | Requirement | Blocking decision | Owner |
| --- | --- | --- | --- |
| Audit storage, retention, export | SPEC-09-02, 09-04, 13-03 | ADR-0003: how long, readable by whom, exported in what format | Platform owner + clinical owner |
| Anything approval-related beyond refusal | SPEC-08-04, 06-08 as a feature | ADR-0005: what an approval records, who may create one | Clinical owner |
| A clinical object that references a patient | SPEC-08-05, 10-06, 06-04 | ADR-0007: Hospital and Patient Context identifiers | Clinical owner (identifier format is a clinical decision) |
| Retrieval, citation, grounding | SPEC-08-06 | ADR-0006, and SPEC-08-05 first | Clinical owner + Services |
| Workflow engine | SPEC-08-07 | FutureKind or CARE ERP owns the workflow (`DOMAIN_MODEL.md` Q5) | Platform owner |
| Model ids leaving the catalogue | SPEC-07-02, 15-01 | ADR-0002 step 3 authorisation only — the integration and the startup check it was waiting on now exist | Platform owner |
| `retryable` telling the truth on three codes | SPEC-14-02 | A decision to change a frozen field's semantics for `provider_authentication_failed`, `provider_request_rejected`, `provider_protocol_error` | Platform owner |
| The deployed stack proven on a hospital machine | SPEC-02-01, 05-01, 11-02 | CI builds the image and validates the compose tree, but `docker compose up` has never been run here, so the booted stack and its healthcheck chain are unexecuted | Hospital IT |
| A second Provider, or the Gateway doing retries | SPEC-12-03, 06-12, 12-05 | Constitution P16 — refused until an ADR argues against it | No one; it is a boundary |
| Multi-hospital data paths, cross-site analytics | Constitution P14 | A constitutional amendment, not an ADR | Platform owner only |
| Streaming semantics | SPEC-15-03 | An ADR fixing cancellation/audit behaviour | Services |
| A `tier` axis, or any new abstraction with no data behind it | SPEC-15-02 | Refused by design | — |

Three honest observations about this table. First, of twelve waiting items **two are
deliberate refusals** (a second provider, a `tier` axis) and are not waiting for
anything; of the remaining ten, **nine await a decision and exactly one awaits an
action** — running the stack on hardware that belongs to a hospital. That is the most
useful thing a specification can tell a small team: the queue is short, and the
constraint is ambiguity rather than capacity. Second, **the platform owner appears on
nearly every row because the decisions are boundary decisions**, and one person owns
both the clinical and the platform side — efficient until it makes one person's
silence a dependency. Third, this table is the reason Sprint 6 was scoped the way it
was: it executed the one row that needed no decision from anyone (SPEC-02-01,
05-01, 07-03, 11-02, 12-01/02) and left every row that needs a clinical or
contractual judgement untouched.

---

**Conformance note.** This specification states what FutureKind is *required* to be.
Where it says `[BUILT]`, the claim is carried by the committed test suite — every test
in `core/gateway/tests/`, passing with `ruff check` clean as of Sprint 6
(2026-10-07). Of those, `test_end_to_end.py` is the part that makes the phrase mean
something: it starts the production Gateway and a stub LiteLLM on loopback ports and
asserts on bytes that crossed a real socket, so the request path is not proved only
inside one process. What the suite cannot prove is the booted stack: CI builds
`core/gateway/Dockerfile` and interpolates `compose.yaml` on every push, but no Docker
daemon exists here, so no container has ever started in this environment. Where this file
says `[PARTIAL]`, `[PLANNED]`, `[BLOCKED]` or `[PROVISIONAL]`, it is deliberately not
a claim about today.
