# FutureKind Radiology Copilot

The first clinical application built on FutureKind. One skill, `radiology-report`,
worked through the whole platform:

```
clinician submits                 copilot                  Gateway            LiteLLM          model
clinical indication        →   POST /draft          →   skill → alias    →   alias →     →   weights
modality                       (structured report)      policy check        deployment
findings                         POST /review           audit, provenance
                                 (named sign-off)
                                 POST /export
                                 (the document)
```

The copilot names no model, no provider, no endpoint and no policy field. It asks
the Gateway what it is *doing* — drafting a radiology report — and the platform
decides everything below that
([ADR-0002](../../docs/adr/ADR-0002-Gateway-vs-LiteLLM.md),
[Routing](../../core/gateway/README-ROUTING.md)).

## What a draft contains

Nine parts, and the last three are not decoration. Each line of the report has one
owner, which is what makes a draft reviewable rather than merely plausible:

| Part | Who writes it | Contents |
| --- | --- | --- |
| `clinical_indication` | **the clinician**, verbatim from the submission | Why the study was done — never restated by the model |
| `technique` | **the department** when supplied, otherwise the model's declaration | Acquisition parameters, or `"Technique not provided."` |
| `findings` | the model, from the dictation | What was seen, in report prose |
| `impression` | the model | The clinical conclusion — the section that carries the risk |
| `recommendations` | the model | What follows, or `"None."` |
| `metadata` | the copilot | Study, modality, the dictation beside the findings it became, `technique_from`, report id, drafted-at, prompt version, generator, review record |
| `model_provenance` | the Gateway, relayed | Request id, model, provider, `selected_by`, attempts, `degraded`, finish reason, tokens, latency |
| `skill` | the copilot | `radiology-report` and the capability it resolved to |
| `policy` | the Gateway, relayed | Clinical risk, approval required, audit required, downgrade allowed |

The model is asked for four keys, not five. An answer that also returns a
`clinical_indication` of its own has it dropped from the document and named in
`metadata.extra_sections` — losing text is the failure to avoid, not the extra key.

```json
{
  "clinical_indication": "62-year-old with sudden right hemiparesis, onset 3 hours",
  "technique": "Technique not provided.",
  "findings": "No intracranial haemorrhage, oedema, mass effect or midline shift. ...",
  "impression": "No acute intracranial haemorrhage or mass effect on this non-contrast study. ...",
  "recommendations": "Clinical correlation. Consider CT angiography with perfusion ...",
  "metadata": {"report_id": "fk-…", "dictated_findings": "…", "technique_from": "model", "review": {"state": "pending_review"}},
  "model_provenance": {"model": "ollama/qwen3:14b", "provider": "litellm", "degraded": false, "…": "…"},
  "skill": {"name": "radiology-report", "capability": "reasoning"},
  "policy": {"clinical_risk": "high", "approval_required": false, "audit_required": true, "allow_downgrade": false}
}
```

The printout shows the report and not the dictation — that lives in the JSON, next
to the findings made from it, so a reviewer can compare the two.

## Human review

`POST /review` is where a named clinician takes ownership of the document (P3).

* `signed` — optionally with `amendments`, one per section. The sections a human
  rewrote are listed in `metadata.review.amendments`; `model_provenance` is left
  exactly as the model reported it, so the record says both what the AI drafted and
  what the clinician approved.
* `returned_for_correction` — requires a comment saying what is wrong, because a
  bare rejection gives the next draft nothing to fix.

Amending never locks anything: a signed report can be reviewed again and exported
again, in any format. `POST /export` refuses (`409`) only until a clinician has
signed — the department's workflow puts review before export, and an application
that exported past that would be running a different workflow.

Three export formats: `json` for the system that stores it, `text` for print,
`markdown` for the review screen. All three carry the same five sections in the same
order, the sign-off state on the first line, and the provenance block at the end.

## What it refuses

| Situation | Behaviour | Why |
| --- | --- | --- |
| The model answers in prose | `502 model_output_unusable`, no report object | Sections must be reviewable one at a time |
| A section is missing or empty | `502`, naming the section | A blank section reads as a normal study |
| Generation ran out of tokens | `502 report_truncated` | A half-written impression looks like a whole one |
| `degraded: true` on the completion | `503 degraded_answer` | The skill forbids a lesser model answering (P13) |
| `audit_required: false` or `allow_downgrade: true` | `503 policy_not_enforced` | The draft was written under a policy that does not exist |
| `approval_required: true` | `503 policy_not_enforced` | This Alpha's sign-off lives in the document, not in a platform Approval, and does not pretend otherwise |
| Export before sign-off | `409 report_unsigned` | Review comes before export |
| Any request body naming a model or provider | `422 invalid_request` | ADR-0002, enforced on both sides of the boundary |

Governance is checked **before** the answer is parsed, so a broken policy is never
dressed up as a usable report. A refusal names the Gateway `request_id` it came
from, quotes no clinical text, and never echoes a rejected body.

This application writes no log line containing a dictation or a report, and stores
no clinical state: the document travels through the caller, because a Report's
record belongs to the EHR
([DOMAIN_MODEL](../../docs/DOMAIN_MODEL.md): "stored in the EHR (CARE ERP), not in
FutureKind").

## Running it

Needs the Gateway from the same repository. On a machine with Python:

```bash
cd apps/radiology_copilot
python -m pytest          # 160 tests: 154 deterministic, 6 over real sockets
python -m futurekind_radiology
```

Use the interpreter from a virtualenv with `fastapi`, `uvicorn`, `pydantic`,
`httpx` and `PyYAML` installed — the same one the Gateway is installed in, so the
two suites exercise one shared transport.

Environment (all optional except where noted):

| Variable | Default | Meaning |
| --- | --- | --- |
| `FK_RADIOLOGY_GATEWAY_BASE_URL` | `http://127.0.0.1:8100` | Where the Gateway lives |
| `FK_RADIOLOGY_GATEWAY_API_KEY` | unset | Sent to the Gateway as `Authorization: Bearer`. Required once the Gateway has keys configured |
| `FK_RADIOLOGY_REQUEST_TIMEOUT_SECONDS` | `120` | Longer than the skill's own 90 s policy timeout, so this app is never the thing that cut off a legitimate draft |
| `FK_RADIOLOGY_HOST` / `FK_RADIOLOGY_PORT` | `127.0.0.1` / `8200` | Where the copilot listens |

`GET /health` reports the Gateway it is pointed at, and only whether a credential
is configured — never the credential.

## Not built here, on purpose

* **No CARE ERP integration.** Structured JSON out; the handoff is designed, not
  implemented (see *Future ERP integration points* in the sprint report).
* **No approvals service.** The review record lives in the document. When the
  approvals ADR is written, `copilot.py::_REQUIRED_POLICY` is the line that changes.
* **No audit storage.** `audit_required: true` makes the Gateway write the record;
  the copilot reads it back and refuses to draft without it.
* **No clinician authentication.** The review body carries a name the department
  already trusts. Binding that name to a session is ADR-0004's job, so this service
  belongs behind the hospital's own authentication, not in front of it.
* **No house style.** `genesis/report_style.md` and `agents/radiology/style-guide.md`
  were empty placeholders and are deleted from this repository, so the prompt states the minimum that makes a draft
  checkable and carries no institutional voice. That is the clinical owner's work,
  not a prompt-engineering task.
* **No patient identifier.** `DOMAIN_MODEL` Q2 forbids inventing an MRN format in an
  application; the EHR supplies it at handoff.
