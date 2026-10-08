# Sprint 8 — AI governance migration: CARE ERP entry points and the first move

**Objective:** take one AI feature the clinic already runs and put it completely behind
FutureKind, without new clinical functionality, without workflow or UI change, and with the
ERP's own behaviour reused. Success test: *users cannot tell; administrators can.*

Scope of the code change: the CARE ERP repository and one configuration file in this
repository. Nothing else.

The ERP checkout is called `care-erp` everywhere in this repository. That is a documentation
name, not a path: a checkout directory encodes which machine the clinic's data lives on, and
this file is public.

## 0. Evidence marking

Every citation below is marked:

- **[V]** — I read the file at that line myself during this sprint.
- **[A]** — found by a delegated sweep of the ERP and *not* re-read by me. Treat as a strong
  lead, not a finding, until verified. (`PROTECTED_FILES.md` and `AGENTS.md` of that repo were
  read before touching anything; the ERP's markdown design docs were not used as evidence for
  any claim about behaviour.)

---

## 1. Architecture — what moved

### Before

```
Radiologist → ERP UI (UsgAiPanel) → POST /api/usg-ai/studies/:id/suggest
   → generateUsgSuggestions(usgGatewayProvider, …)
   → usgGatewayProvider.generate()
   → generateAiForTask("usg_ai_assistant", prompt, [], {maxTokens:1200})   [V]
   → resolveTaskRoute() / ai_provider_settings / ai_model_routes          [V]
   → provider chosen: ollama | openai | gemini | deepseek | qwen | …      [V]
   → POST {OLLAMA}/api/chat  (no auth header)                             [V]
```

The application knew, and chose, the model. No request id. No policy. Nothing that would
survive an audit question.

### After

```
Radiologist → ERP UI (unchanged) → POST /api/usg-ai/studies/:id/suggest (unchanged)
   → generateUsgSuggestions(futurekindGatewayProvider, …)
   → POST {Gateway}/chat   {"skill":"usg-advisory-suggestions","messages":[{role,content}]}
   → Gateway: skill → capability `fast` → alias `fk-fast` → policy → audit → LiteLLM → model
   → answer + {request_id, model, provider, selected_by, attempts, degraded, policy, usage}
   → same extractJson() + same coerceSuggestions() → same chips, same safety funnel
```

The application names an intent and nothing else. Governance is decided by configuration the
clinic reviews (`core/gateway/models.yaml`), and every answer is traceable to a request id.

**Unchanged by construction, not by promise:** the prompt text (imported, not copied), the JSON
contract, the defensive parsing, the PCPNDT fetal-sex refusal in `usgAiAssistant`, the
accept-only write-guard, the response shape, the feature flag, and the honest
"AI model gateway unavailable" state.

---

## 2. Every AI entry point found in the CARE ERP

All paths are under `/api`. The deepest shared Ollama call is
`lib/ai-providers/src/index.ts:833` `fetch(\`${base}/api/chat\`)` **[V]**; seven builtin
providers are declared at `lib/ai-providers/src/index.ts:373-439` **[V]**.

### 2.1 HTTP entry points

| # | Entry point | Deepest model call | Guard | Vision? | Size of the seam |
| --- | --- | --- | --- | --- | --- |
| 1 | `POST /usg-ai/studies/:id/suggest` — `routes/usgAi.ts:50` **[V]** | was `lib/ai/usgGatewayProvider.ts:118` **[V]** → now the Gateway | `requireStaffAuth` + `requireStaffPermission("/radiology")` + feature flag **[V]** | No — `images: []` **[V]** | **one injected provider object** |
| 2 | `POST /usg-ai/accept` — `usgAi.ts:63` **[V]** | none (deterministic merge) | same + write-guard **[V]** | No | n/a |
| 3 | `POST /radiology-ollama/{findings,impression,improve,grammar,impression-from-findings,format-care-style,draft,differential}` — 8 actions **[A]** | `handleAction`→`ollamaGenerate` (`radiologyOllama.ts:171`)→`createAiProvider("ollama")` **[V]** | mount + in-router `canUseAi` **[A]**, `localOnly` **[V]** | No — `images: []` **[V]** | `ollamaGenerate(` = 2 sites **[V]** |
| 4 | `POST /radiology-ollama/multi-review` — `radiologyOllama.ts:820` **[V]** | `executeInteractiveAiCall` + `ollamaGenerate` **[A]** | **`requireStaffAuth` only — no `canUseAi`, and `providers[]` comes from the request body [V]** | No `[]` **[A]** | fan-out |
| 5 | `POST /radiology-ollama/{test,verify,pipeline-self-test}` **[A]** | `ollamaDraftVerify.ts:186`, `aiPipelineSelfTest.ts:768` **[A]** | `canUseAi` **[A]** | self-test yes **[A]** | ops |
| 6 | `POST /ai/patient-message`, `/ai/radiology-impression`, `/ai/clinical-note`, `/ai/billing-insights`, `/ai/radiology-findings`, `/ai/teaching-*`, `/ai/transcribe/polish` — `routes/ai.ts` **[A]** | `generateAiForTask` (`lib/ai-providers/src/index.ts:1620` **[V]**) | `ai.ts:29` + per-route perms **[A]**; note `/ai/radiology-impression` has `requireStaffAuth` only **[A]** | No — `images=[]` **[A]** | `generateAiForTask(` = **20 non-test call sites** **[V]** |
| 7 | `POST /ai/transcribe` (Gemini) — `ai.ts:302` **[A]** | `geminiTranscribe`, key in the **query string** (`lib/integrations-gemini-ai/src/helpers.ts:27`) **[V]** | `ai.ts:29` **[A]** | audio | 1 |
| 8 | `POST /ai/transcribe/local` — `ai.ts:250` **[A]** | raw `fetch` to an admin-configured STT endpoint **[A]** | `ai.ts:29` **[A]** | audio | bespoke |
| 9 | `POST /ai-comparison/run` — `routes/aiComparison.ts:33` **[A]** | `generateAiResponse(providerName,…)` **[A]** | `requireStaffAuth` + `canUse` **[A]** | **Yes** — images from body **[A]** | provider named by the client **[A]** |
| 10 | `POST /ai-prompt-library/test` **[A]** | `generateAiResponse` with `[]` **[A]** | `requireStaffAuth` **[A]** | No | 1 |
| 11 | `POST /ai-reporting/{query,draft,polish,image-review,compare,rag-*}` — 8 routes **[A]** | `generateAiResponse`, `executeInteractiveAiCall`, `embeddings.ts:54` **[A]** | `ai_reporting.use` `canUse` **[A]** | `/query` + `/image-review` yes; `/draft`,`/polish`,`/compare` no **[A]** | large |
| 12 | `POST /radiology/studies/:id/ai-enhance` — `radiology.ts:2349` **[A]** | `aiReportEnhancer.ts:37` `generateAiForTask("report_enhancement")` **[A]** | `/radiology` **[A]** | No `[]` **[A]** | **0 front-end callers — dead route [V]** |
| 13 | `POST /radiology/voice-report-composer/{compose,test,benchmark}` **[A]** | **raw `fetch(${endpoint}/api/generate)` at `lib/voiceReportComposer/composer.ts:183` [V]** — bypasses the provider package entirely | `requireStaffAuth` only **[A]** | No | `ollamaGenerateJson(` 2 sites **[A]** |
| 14 | `POST /radiology/report-composer/{jobs,test,test/compare,vision-trial}` **[A]** | **raw `fetch /api/chat` at `lib/reportComposer/providers/ollamaComposerAdapter.ts:59` [V]** | mount + `canUse` **[A]** | **Yes** — `userMessage.images` **[A]** | `compose(` 3 sites **[A]** |
| 15 | `POST /ai/generate` (night batch) — `aiClinical.ts:77` **[A]** | enqueues; real inference in `radiologyJobHandlers.ts:270`→`gatewayInferenceProvider.ts:97` **[A]** | `requireStaffAuth`+`/radiology`+enablement **[A]** | **Yes** **[A]** | cron |
| 16 | `POST /fetal-usg/:id/generate-draft`, `/echo-cardiology/…-draft` **[A]** | `generateAiForTask("fetal_usg_draft"|"echo_draft")` **[A]** | `/radiology` **[A]** | No `[]` **[A]** | 1 each |
| 17 | OCR: `/expenses/scan-bill`, `/purchase-invoices/scan`, `/accounting/bank-statement/parse`, `/form-f/upload-id` **[A]** | `localDocumentOcr.ts:285`, `idCardOcrOllama.ts:207` **[A]** | module permission **[A]** | **Yes** **[A]** | shared resolver |
| 18 | `GET /ai-gw/v1/knowledge-base/search` — `aiCallerKnowledgeBase.ts:19` **[A]** | none on the read path **[A]** | `requireAiCallerAuth("knowledge_base:search")` **[V]** | No | 1 |

### 2.2 Not reachable by HTTP **[A]** unless marked

- Cron `*/15` night batch enqueue → `schedulerService.runNightBatch`; weekly reprocessing and
  learning aggregation; **the overnight queue drain is where real inference happens**
  (`cron.ts:275 fireOvernightAiTick`, started by `startRadiologyJobConsumer()`).
- `bootstrapLocalAi.ts:20` registers a resolver; it does not call a model **[A]**.
- CLI: `scripts/verify-ollama-ai-draft.mjs` **[V]**, `production-acceptance-ocr-ai.mjs`,
  `benchmark-ocr-ai.mjs`, `verify-deployment.mjs` (probes `/api/tags`) **[A]**.
- No browser→model calls anywhere. `11434` appears in UI text only **[A]**.

### 2.3 Two things found that are not migrations but findings

1. **`/api/ai` is mounted twice** — `routes/index.ts:777` (`requireStaffAuth` +
   `requireStaffPermission("/radiology")` → `aiClinicalRouter`) and `:1070`
   (`requireStaffAuth` only → `aiRouter`) **[V]**. Express falls through the first when the
   second's path is not in the first router, so the effective guard on a route is decided by
   which router owns it. Any migration under `/api/ai` must be checked against both mounts.
2. **A hardcoded LAN endpoint and model are committed as source defaults**:
   `lib/ai-providers/src/canonicalLocalAi.ts:12-14` = an internal `http://<lan-ollama-host>:11434`,
   `qwen3-vl:8b`, `nomic-embed-text` **[V]**. Their header says these are "the clinic's current
   production defaults". `x-care-signature` HMAC exists only for **outbound** events
   (`services/integration/outbox.ts:175` **[V]**); a reusable *inbound* verifier pattern exists
   in `lib/whatsappShareToken.ts:78-86` **[A]**. `routes/aiCallerCredentials.ts:76` returns a
   freshly generated key once at enrolment and stores only a hash **[V]** — correct, not a leak.

## 3. The smallest one, and why

Selection criteria, in order: (1) actually reachable from a clinician's screen, (2) text-only —
the Gateway has no vision capability, (3) the number of lines the migration must touch,
(4) existing tests to prove sameness, (5) an instant rollback that is not a redeploy.

| Candidate | In use? | Text-only | Seam | Tests | Rollback |
| --- | --- | --- | --- | --- | --- |
| **1 — `/usg-ai/suggest`** | wired to `UsgAiPanel.tsx`, rendered by `pages/UsgCompanionWorkspace.tsx` **[V]** | Yes `[]` **[V]** | **one provider object, injected as a function argument** **[V]** | 30 passing **[V]** | `ff_radiology_usg_ai_assistant` → 404 **[V]** |
| 12 — `/radiology/.../ai-enhance` | **no front-end caller at all** **[V]** | Yes | inline in a 2,349-line route file | unknown | none |
| 3 — `/radiology-ollama/draft` | yes, heavily (6 UI files) **[V]** | Yes | `ollamaGenerate` inside a 1,164-line route, with endpoint probing, primary/fallback failover, clinic timeout/audit settings and two verify endpoints that keep their own direct calls **[V]** | few | none |
| 6 — `/ai/patient-message` | 1 UI file **[V]** | Yes | `generateAiForTask` inline in the handler | unknown | none |
| 4 — `/radiology-ollama/multi-review` | unknown | Yes | shares `ollamaGenerate` | none | none |

**Chosen: candidate 1.** It is the only entry point in the ERP where a provider is *already a
parameter* (`generateUsgSuggestions(provider, …)` — `lib/usgAiService.ts:55-60` **[V]**), so the
migration is a substitution rather than a surgery: the service, the safety funnel, the route,
the response shape and the screen are untouched. It also has the only rollback lever that does
not involve a NAS redeploy.

**Honest caveat on "already used clinically".** The flag's `defaultValue: false`
(`lib/radiologyFeatureFlagRegistry.ts:176` **[V]**) and no committed migration or seed enables
it; `usgProductionReadiness.ts:41` records P8a as `code_complete` **[V]**. So it is built and
wired, and its production enablement lives in the `feature_flags` table — which is the clinic's
data, not this repository's. **If the panel is switched off at CARE today, the migrated feature
is one you can switch on rather than one you were already using**, and the strongest genuinely
in-use candidate is `/radiology-ollama/draft` (candidate 3) — which is 3–4× the work for the
reasons in the table, and is the correct next migration.

## 4. Implementation

**This repository (configuration only, no code):**

- `core/gateway/models.yaml` — new skill `usg-advisory-suggestions`: capability `fast`,
  `clinical_risk: moderate`, `audit_required: true`, `allow_downgrade: false`,
  `max_completion_tokens: 1200` (the ERP's own `maxTokens`, carried over so answer length does
  not change), `request_timeout_seconds: 120`. Alias `fk-fast` already existed in
  `configs/litellm/config.yaml`; **no LiteLLM change was needed**, and the startup alias check
  passed at boot (`aliases_checked: 3, drift: 0`).
- `core/gateway/tests/test_catalog.py` — the shipped-skill allowlist gains the new name, plus a
  new test pinning its governance so a future edit cannot relax `allow_downgrade` silently.
- `docs/product/SKILL_LIBRARY.yaml` — the skill gains a catalogue entry (121 now), with the
  migration recorded.

**CARE ERP (`artifacts/api-server/src`):**

| File | Change |
| --- | --- |
| `lib/ai/futurekindGatewayProvider.ts` | **new, 296 lines.** Implements the existing `UsgAiProvider` interface. `POST /chat` with `Bearer`; reuses `buildUsgPrompt`/`extractJson`/`coerceSuggestions`; fails closed on unset config, bad URL, refusal, truncation, degraded answer or skill mismatch; logs provenance without content |
| `lib/ai/usgAssistantPrompt.ts` | **new, 88 lines.** `buildUsgPrompt`, `extractJson`, `coerceSuggestions` moved verbatim from the deleted file |
| `lib/ai/usgGatewayProvider.ts` | **deleted, 126 lines.** This is the direct model access being removed — `generateAiForTask(USG_AI_TASK_KEY, …)` and the DB-driven provider/model choice for this feature |
| `lib/ai/usgGatewayProvider.test.ts` | **deleted** (13 tests). Its 6 pure-helper tests moved to `usgAssistantPrompt.test.ts`; its 7 provider tests were replaced by 22 stronger ones |
| `lib/ai/usgAssistantPrompt.test.ts` | **new, 6 tests** — the helpers, unchanged assertions |
| `lib/ai/futurekindGatewayProvider.test.ts` | **new, 22 tests** |
| `routes/usgAi.ts` | **2 lines:** the import and the provider argument; the stale comment replaced |
| `routes/usgAi.test.ts` | **1 mock path** |

Net in the ERP: **−139 lines** (deleted 126 + 13-test file, added two modules and two test
files, 3 lines changed in the route).

**Deliberate choices worth objecting to:**

- `available()` reads configuration instead of probing the network or the database. The old one
  did two DB reads per request. An unreachable Gateway is reported by the request, which is the
  same place the old provider reported it (it returned `[]` and logged) **[V]**.
- The ERP does **not** store provenance in a table. It logs
  `futurekind_ai_provenance` with the request id, model, provider, attempts, degraded flag and
  timings — enough for an administrator, no care text. Persisting it against the study is the
  one gap this sprint leaves open, and it is a schema decision in a system running on a NAS.
- No feature flag was added for the Gateway path. The ERP's own
  `ff_radiology_usg_ai_assistant` already gates the feature; a second switch would have been a
  way to keep two code paths alive for no clinical reason.
- `validateOllamaUrl` is reused in local/LAN mode (`allowLocal = true`) because the Gateway URL
  is operator configuration, not user input. Cloud-metadata IPs stay blocked, and an
  `AI_EGRESS_ALLOWLIST` still overrides — both are tested.

## 5. Verification and tests

| Suite | Before | After |
| --- | --- | --- |
| `usgGatewayProvider.test.ts` | 13 | deleted |
| `usgAssistantPrompt.test.ts` | — | 6 pass |
| `futurekindGatewayProvider.test.ts` | — | 22 pass |
| `routes/usgAi.test.ts` | 6 | 6 pass |
| `lib/usgAiService.test.ts` | 11 | 11 pass |
| **Total** | **30 pass** (measured before any edit) | **45 pass, 0 fail** |

`pnpm exec vitest run` cannot be used on this machine — it triggers a pnpm install that fails
on ignored build scripts (esbuild/sharp/tesseract), so the suites were run with
`./node_modules/.bin/vitest run <files>` directly. **`tsc -p tsconfig.json --noEmit` for
`api-server` is clean.**

What the 22 new tests prove, in the order that matters:

1. The request body's keys are exactly `skill`, `messages`, `stream` — and it explicitly asserts
   the absence of `model`, `provider`, `api_base`, `endpoint`, `base_url`. **This is the rule
   the whole platform rests on, now enforced by a test in the customer's repository.**
2. The prompt the Gateway receives is `buildUsgPrompt(context)` — byte-equal, and a separate
   test asserts the PCPNDT fetal-sex sentence survives the trip.
3. Unset config, refusal (`404 unknown_skill`), transport failure, non-JSON body, truncated
   (`finish_reason: length`), degraded, and skill-mismatch all yield zero suggestions and never
   throw.
4. The provenance log line contains `requestId`/`model`/`studyId` and **must not** contain the
   chip text, the prompt, or the API key; a refusal log must contain the code and request id and
   **must not** contain the upstream message (which can quote patient data).

**End-to-end, with a real model:** the running Gateway (`http://localhost:8100`, catalogue
reporting six skills, `alias_contract_verified … drift: 0`) was called through the migrated ERP
provider from Node on Windows. It returned **6 chips** with provenance
`{requestId, model: "ollama/gemma3:12b", provider: "litellm", selectedBy: "skill", attempts: 1,
degraded: false}` and the Gateway wrote its `chat_completed` line:
`skill=usg-advisory-suggestions, capability=fast, clinical_risk=moderate, alias=fk-fast,
prompt_tokens=283, completion_tokens=384, latency_ms=98570`.

**Limitation, stated plainly:** `LiteLLM` was not installed on this machine, so the hop between
the Gateway and Ollama was served by a scratch stand-in that performs only alias→deployment
routing and forwards to the real local Ollama (`gemma3:12b`). Model answers, tokens and timings
are real; LiteLLM's own retry/wallet behaviour is not in the loop. The ERP's production model
for this task is whatever the clinic routed (canonical default `qwen3-vl:8b`
`[V]`), not `gemma3:12b`, so **"same output" is proven for the prompt, the schema and the
parsing — not for the model's wording, which is now a configuration choice rather than an
application one.**

## 6. Performance measurements

| Path | p50 | Note |
| --- | --- | --- |
| Ollama `/api/chat` direct, real prompt, `num_predict 1200` | **~129 s** first call (cold model) | same box, same model |
| Stand-in alias routing → Ollama | ~99 s | routing time ≈ model time |
| **Gateway → stand-in → Ollama** | **~99 s**, Gateway self-report 98.6 s | **governance ≈ 0.2 s** (98.9 − 98.6 + request parsing) |
| **ERP provider → Gateway** | **~102 s**, 6 chips | ERP client adds ~2–3 s in this sample |
| Tiny completion (17 prompt / 2 completion tokens) | stand-in 1.34 s, Gateway 0.93 s, Gateway-reported 0.70–0.75 s | **in-boundary overhead ~0.19–0.23 s** |

Throughput measured: 384 completion tokens in 98.6 s ≈ **3.9 tokens/s** on this workstation.

**The finding that outranks everything else here: the governance cost is noise, and the model is
the product's problem.** At 3.9 tok/s, a chip answer of ~380 tokens takes ~100 s. The workflow
design target was 3 s per chip and the `fast` capability was chosen on that assumption; `fast`
on this hardware is not fast. This is exactly the kill criterion written in
`docs/product/ROADMAP.md` §2 ("if 8.0 shows p95 over ~3 s for a `fast` chip, chips are the wrong
interaction"), and it triggers. It is a measurement on *this* machine with a 12B model, not on
that clinic's inference host, so the action is: **re-run this harness on the hospital's box
before turning the feature on there**, and if it is the same, cut the chip token budget
(`max_completion_tokens` is now configuration, which is the point of the migration) or route
`fast` at a smaller model — without touching the ERP again.

## 7. Rollback plan

Three levels, cheapest first. Nothing requires a code edit.

1. **Turn the feature off** — `ff_radiology_usg_ai_assistant` → the router answers `404` for
   every request (`usgAi.ts:29-32` **[V]**), the panel hides itself, reporting continues
   manually. Existing behaviour, not a new mechanism.
2. **Turn the Gateway off** — unset `FUTUREKIND_GATEWAY_URL` or the key on `care-api`.
   `available()` returns false, `generate()` returns nothing, and the panel shows the ERP's own
   sentence: *"AI model gateway unavailable — manual reporting unaffected"*
   (`usgAiService.ts:82-89` **[V]**). Deterministic, no error, no half-chips.
3. **Revert the code** — the change is 3 lines in `routes/usgAi.ts` plus two new modules and one
   deleted file. `git checkout -- artifacts/api-server/src/routes/usgAi.ts` and
   `git checkout -- artifacts/api-server/src/lib/ai/` restores the previous state exactly; the
   new files are untracked and are removed by hand. On the NAS, the deploy path is
   `deploy-synology.sh` from `origin/main`, so nothing reaches the clinic until it is merged and
   deployed deliberately.

Rollback is *not* a runtime flag inside the provider. A switch that kept the direct Ollama call
alive "just in case" would have made the migration incomplete by design.

## 8. Deployment checklist for the clinic

1. Gateway reachable from `care-api`; alias `fk-fast` present in the LiteLLM config (it is).
2. Set `FUTUREKIND_GATEWAY_URL=http://<gateway-host>:8100` and
   `FUTUREKIND_GATEWAY_API_KEY=<key>` on the API container. If the site uses
   `AI_EGRESS_ALLOWLIST`, add the Gateway's `host:port` or requests will be refused by design.
3. Restart, then `GET http://<gateway>:8100/health` and confirm `usg-advisory-suggestions` is
   listed and `alias_contract_verified` shows zero drift.
4. Run the harness on the clinic's own machine and record p50/p95 **before** enabling the flag.
5. Enable `ff_radiology_usg_ai_assistant`; generate chips on one real study; grep `care-api`
   logs for `futurekind_ai_provenance` and match the `requestId` to a Gateway `chat_completed`
   line. Those two are the whole acceptance test.

## 9. What is still ungoverned, ranked

Migrating one feature leaves the rest exactly as they were. In order of concern:

1. **`/radiology-ollama/multi-review`** (`radiologyOllama.ts:820` **[V]**) — any authenticated
   staff member, no `canUseAi`, and `providers[]` accepted from the request body **[V]**. It
   fans clinical history and findings out to Gemini and others. This is not a missing
   migration; it is a permission bug with PHI attached, and it should be fixed before anything
   else on this list.
2. `/ai/radiology-impression` reachable under `requireStaffAuth` without a `/radiology`
   permission **[A]**, and the double `/ai` mount (**[V]**) that makes which guard applies a
   matter of router ordering.
3. **Three paths that bypass `@workspace/ai-providers` entirely** — verified:
   `lib/voiceReportComposer/composer.ts:183` (`/api/generate`) **[V]**,
   `lib/reportComposer/providers/ollamaComposerAdapter.ts:59` (`/api/chat`) **[V]**,
   `lib/ai/embeddings.ts:54` (`/api/embeddings`) **[A]**. A migration that only rewires the
   provider package will silently miss all three **[V]**.
4. `/radiology-ollama/draft` and its 7 sibling actions — the most-used AI feature at the site,
   the correct **next** migration, and the one that needs a decision about endpoint failover
   (which belongs to LiteLLM under `ADR-0002`, but is currently hand-rolled in the route with a
   5-minute endpoint cache **[V]**).
5. The Gemini integration's key in the URL query string **[V]** — move it to a header; it will
   otherwise appear in proxy and server logs.
6. The vision paths (report-composer, overnight shadow inference, OCR) cannot be migrated at all
   until a `vision` capability exists. That is roadmap decision **D-D**, and it is now backed by
   a measured reason rather than a preference.

## 10. Two findings from the ERP side, dated 2026-10-08

- **The ERP tree was not clean when this migration was made.** Uncommitted changes that this
  work did not author were present in `care-erp` alongside it: `routes/radiology.ts` (+187),
  `src/index.ts`, `lib/pacs/orthancPurge.ts`, `lib/pacsWorklistDetailFields.ts`,
  `routes/internal-radiology.ts`, `components/EmbeddedWadoViewer.tsx`,
  `lib/db/src/schema/radiologyWorklist.ts`. This migration's own edits are confined to
  `routes/usgAi.ts`, `routes/usgAi.test.ts` and `lib/ai/*`, and **nothing on the ERP side has
  been committed**. Consequence for anyone deploying this repository: the
  `usg-advisory-suggestions` skill has a routing entry and no caller. Do not read its presence
  in the routing table as the clinic being migrated — diff the ERP working tree first.
- **`POST /radiology/studies/:id/ai-enhance` has no caller in the front-end** (0 matches for
  `ai-enhance` under `artifacts/diagnostic-erp/src`) **[V]**. Either it is invoked from
  somewhere I did not look or it is dead weight on a route that reaches a model. Worth knowing
  before anyone counts it as a feature.
