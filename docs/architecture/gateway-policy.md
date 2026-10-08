# Gateway Policy

**Status:** Current design, as of Sprint 2
**Date:** 2026-10-07
**Governing decisions:** [ADR-0001 Local-First AI](../adr/ADR-0001-Local-First-AI.md), [ADR-0002 Gateway vs LiteLLM](../adr/ADR-0002-Gateway-vs-LiteLLM.md)
**Component:** `core/gateway/` — `policy.py`, `catalog.py`, `routing.py`, `service.py`
**Read with:** [gateway-routing.md](gateway-routing.md), which says who decides what; this file says how a decision is written down and enforced.

ADR-0002 rule 3 is normative about location:

> Skill→capability mapping, whether a lower class may answer a given skill, and
> the clinical context attached to a request are Gateway policy. They belong in
> `models.yaml`, not in application code and not in LiteLLM configuration.

This document is what that rule looks like in practice: the vocabulary an
operator may write, the rules the loader enforces, what each decision does at
request time, and what is deliberately *not* policy.

---

## What policy is, and what it is not

Policy is the set of decisions about a clinical request that the platform makes
on behalf of the clinician, and that a clinician's hospital should be able to
read without reading Python. Before Sprint 2, two of them were Python:

| Decision | Where it lived | Where it lives now |
| --- | --- | --- |
| Request size limits | `api/routes_chat.enforce_limits` | `models.yaml`, per skill |
| Whether a lesser model may answer | unconditional in `routing.build_chain` | `allow_downgrade`, per skill |
| Clinical risk of an intent | nowhere | `clinical_risk`, per skill |
| Whether the answer needs sign-off | nowhere | `approval_required`, per skill |
| Whether the request is audited | always, for everything | `audit_required`, per skill |

Policy is **not** model selection, provider selection, retries, failover
ordering or cost. Those are LiteLLM's, and a policy field that reaches for one
of them would be the Gateway becoming a second LiteLLM — the specific failure
mode ADR-0002 exists to prevent.

---

## The vocabulary

A skill's stanza in `core/gateway/models.yaml` carries its policy next to its
intent. Flat keys, one block per skill, no nesting:

```yaml
skills:
  radiology-report:
    capability: reasoning        # required: which class serves this intent
    clinical_risk: high          # required: the operator's assessment, not a default
    audit_required: true         # optional, default true
    allow_downgrade: false       # optional, default true; forced false at high/critical
    approval_required: false     # optional, default false; forced true at critical
    max_completion_tokens: 1024  # optional: tightens the platform ceiling, never raises it
    request_timeout_seconds: 90  # optional: shortens the platform timeout, never lengthens it
    max_messages: 20             # optional
    max_content_chars: 8000      # optional
    description: Draft or review a radiology impression.
    enabled: true
```

This is the shipped `radiology-report` stanza with the rest of the vocabulary
added, so one block shows every key. `approval_required`, `max_content_chars`
and `enabled` are shown for completeness only: no skill in `models.yaml` needs
them today, because the defaults already say what this deployment means.

`POLICY_KEYS` in `policy.py` is the authoritative list, and
`test_every_policy_key_is_a_field_and_a_documented_key` fails if the list and
the `SkillPolicy` fields ever disagree. Limit keys are named exactly as their
`FK_GATEWAY_*` environment counterparts, so one vocabulary covers both places a
limit can be set.

### Clinical risk levels

`unspecified` → `low` → `moderate` → `high` → `critical`, in that order.

`unspecified` is not a risk assessment and may not be written in configuration.
It is what a request gets when it names no skill, and it is reported back as
`"clinical_risk": "unspecified"` so that "nobody assessed this" stays visible in
the response and in the audit record instead of quietly inheriting something
reassuring.

---

## Validation rules

Enforced when the catalogue loads, not when a patient is waiting. A violation
refuses the start, because the alternative is discovering an unaudited high-risk
skill during an audit request two years later.

| # | Rule | Why it is a startup failure |
| --- | --- | --- |
| 1 | Every skill must declare `clinical_risk` | An unassessed clinical skill is the exact failure this layer exists to prevent. |
| 2 | `clinical_risk` must be one of the four declarable levels | A typo reads as "no risk declared". |
| 3 | `high` or `critical` ⇒ `audit_required: true` | A high-risk skill nobody can reconstruct is not auditable, only lucky. |
| 4 | `high` or `critical` ⇒ `allow_downgrade: false` | "Quietly use a smaller model" looks like reliability and is a change to the answer's provenance. |
| 5 | `critical` ⇒ `approval_required: true` | A critical action without sign-off is an unreviewed clinical decision. |
| 6 | Flags must be booleans; limits positive integers; timeout in `(0, 3600]` | `audit_required: "no"` or `max_messages: 0` silently inverts or disables a rule. |
| 7 | No key outside `POLICY_KEYS` on a skill | `alow_downgrade` would otherwise load as "the operator asked for nothing". |
| 8 | A skill may not declare `alias`, `model`, `provider`, `api_base` or `endpoint` | A skill naming infrastructure is ADR-0002's fused namespace coming back. |

Rules 3–5 are checked against the **composed** policy — the declaration folded
over the floor — not against each written key. That distinction is the point: a
skill that declares `clinical_risk: high` and forgets `allow_downgrade` is still
a silently downgradable high-risk skill.

---

## What each decision does at request time

Order of operations on `POST /chat`, and it matters: authentication → streaming
guard → routing → policy → provider.

Routing comes before the limits because the limits now live on the skill being
routed to. The consequence is deliberate: a request that is both oversized *and*
unroutable is answered `404 unknown_skill`, not `422`, because the routing
failure is the more actionable of the two.

| Field | Effect | Enforcement point |
| --- | --- | --- |
| `clinical_risk` | Reported to the caller, written into the audit line | `schemas.SkillPolicySchema`, `service._audit` |
| `approval_required` | `403 approval_required`, before any provider is named | `policy.check_approval` |
| `audit_required` | One `skill_audit` line per request, answered or refused | `service._audit` |
| `allow_downgrade` | The route's candidate chain becomes the primary entry alone | `routing.build_chain` |
| `max_messages`, `max_content_chars`, `max_completion_tokens` | `422 invalid_request` naming the limit, the skill and the risk | `policy.check_request` |
| `request_timeout_seconds` | Shortens the `asyncio.wait_for` around one provider attempt | `service.complete` |

### Two rules that constrain every policy

**A policy may tighten a platform limit, never raise it.** `limits_for()` takes
the `min()` of the skill's ceiling and `FK_GATEWAY_MAX_*`. This is one function
rather than three call-site `min()`s so it cannot be forgotten. A skill that
genuinely needs a wider ceiling than the platform default has to widen the
platform — a decision with a name and a deploy behind it, not a YAML edit inside
one skill.

**A request that names no skill gets `DEFAULT_POLICY`, and `DEFAULT_POLICY` is
inert.** It audits, allows downgrade, adds no limits and leaves the timeout
alone, so introducing this layer changed nothing for existing callers.
`test_the_default_policy_is_the_inert_one` is the guard: if a default flips, every
skill-less request changes behaviour without anyone editing anything.

---

## The alias, and why it is not policy

`ADR-0002` step 3 replaces `provider:` + `model:` with a single
`alias:` per routing row, and adds a startup check that the alias exists in
LiteLLM's model list. The field now exists on the row — `ModelEntry.alias`,
declared in `models.yaml` as `fk-default` / `fk-fast` / `fk-reasoning`, matching
`configs/litellm/config.yaml` — and is threaded to `Route.alias` so the audit
line can state both the alias asked for and the model that answered, which is
what ADR-0002's consequences section requires.

It is deliberately **not** a skill policy field. An alias names a routing
target; a skill names an intent. Putting an alias on a skill would let one
intent pin a model, which is the fusion ADR-0002 removed, and rule 8 above
refuses it at load time.

The alias appears in no response body and in no request body: `GET /models`
reports `model` and `provider` for provenance but not the alias, per the naming
table in [gateway-routing.md](gateway-routing.md#naming-rules). It is a log
field. What is *not* yet done is the startup existence check, because the
Gateway cannot read LiteLLM's model list without integrating with LiteLLM — see
debt below.

---

## Reading a policy from outside

`GET /models` skill cards carry the four governance fields and nothing else:

```json
{
  "name": "radiology-report",
  "capability": "reasoning",
  "description": "Draft or review a radiology impression.",
  "enabled": true,
  "clinical_risk": "high",
  "approval_required": false,
  "audit_required": true,
  "allow_downgrade": false
}
```

`POST /chat` repeats the same object as `policy` on the completion, so an
application can render "needs your sign-off" without asking a second endpoint.

Numeric limits and the timeout are not published. Reporting them teaches a
caller to size a request to the ceiling, and a timeout is a statement about
infrastructure rather than about the clinical decision.

---

## An audit line, for shape

```json
{"event":"skill_audit","request_id":"c1a2…","skill":"radiology-report",
 "capability":"reasoning","clinical_risk":"high","approval_required":false,
 "alias":"fk-reasoning","answered":false,"provider":null,"model":null,
 "downgrades_allowed":false}
```

Written whether the request succeeded or not, and containing no prompt or
completion text — the same rule the rest of the logging follows
(`observability/logging.py`).

---

## Remaining debt in this layer

- **Approval is a refusal, not a workflow.** There is no approvals service, so
  nothing a caller can send proves a clinician signed off. The Gateway refuses
  `403` rather than accepting an unverifiable claim and calling it enforcement.
  A deployment that needs `approval_required` skills needs the approvals
  boundary designed first; that is a Sprint 3 question, and the answer must not
  be a self-attested boolean on the request.
- **`audit_required: false` means no attestation line, not no logging.** The
  operational lines (`chat_completed`, `request_completed`) still happen. A
  clinical system probably wants audit on everywhere; the field exists so the
  choice is written down rather than assumed.
- **The alias existence check now exists.** A wrong `alias:` string used to load
  happily and fail upstream; the Gateway now reads
  `configs/litellm/config.yaml` at startup and refuses to serve if a name it will
  send is not a `model_name` there (`litellm_config.py`, SPEC-07-03 in
  `docs/SPECIFICATION.md`). What remains of ADR-0002's stated cost is the
  `model:` column itself — inventory the check keeps honest until step 3 deletes
  it.
- **The chain still orders concrete candidates.** `allow_downgrade` narrows it,
  but the Gateway is still choosing *which* lesser entry to try — the overlap
  with LiteLLM's retries that ADR-0002 records as debt. Step 4 should leave this
  field and delete the ordering.
- **`capability` is still a public selector**, so a request can arrive with no
  declared risk. ADR-0002 lists its removal as scheduled; it is a contract change
  and is kept out of this layer's change on purpose.

---

**FutureKind Principle**

> A rule that needs a pull request to change is not configuration. A clinical
> platform should be able to answer "what did you allow, for whom, and who said
> so?" from one file and one log line.
