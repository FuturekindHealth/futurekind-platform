# Security policy

FutureKind puts an AI boundary inside a hospital. That is a security product before
it is a convenience one, so this file is written to be read by the person who has
to decide whether to deploy it.

**Alpha status.** See [What Alpha is not](README.md#what-alpha-is-not). Two absences
matter most: audit records are emitted and **not retained**, and authentication is a
**shared API key**, not a per-clinician identity. Do not put patient data on a system
that cannot answer "who was allowed to do what, and what did it do".

---

## Supported versions

| Branch / tag | Supported | What that means |
| --- | --- | --- |
| `main` (release tags `v*`) | **Yes** | Fixed for the current release line |
| `develop` | Best effort | Fixes land here first; expect them to move fast |
| Anything older than the previous minor release | No | Upgrade. Several Alpha-era gaps are only closed by moving forward |

Security fixes are released as patch versions. There is no private distribution
channel yet: a fix is published, so a report's window is the time between the fix
landing and the tag being cut — which is why coordinated disclosure below is real
coordination and not a courtesy.

---

## Reporting a vulnerability

**Do not open a public issue for a security problem.** Not for an unauthenticated
endpoint, not for a way to reach a model without policy, not for anything that could
touch a report or a patient.

Report through **GitHub's private vulnerability reporting** — the *Report a
vulnerability* form on the Security tab of
[`FuturekindHealth/futurekind-platform`](https://github.com/FuturekindHealth/futurekind-platform),
which opens a private thread with the maintainers instead of a public issue. If that
is unavailable to you, describe the problem to the repository owner only as far as it
can be triaged — no reproduction steps in a public place — and ask for a private
channel before continuing.

Include:

1. What you ran or sent, in a form someone else could repeat.
2. What the system did that it should not have.
3. The impact you think it has on a deployed hospital, in your words — the maintainers
   will assess it, but a clinical reader's framing changes priorities here.

You will get an acknowledgement within **5 working days**. If the report is accepted,
a fix target and a disclosure date are agreed with you before anything is published;
the usual window is **90 days** from acknowledgement, shortened if the issue is
exploitable against a live deployment we know about, extended on request if you need
more time to ship a fix on your side.

Do not test against a hospital deployment you do not operate. Testing the code in this
repository, or your own instance of it, is in scope and welcome — and a report that
comes with a failing test is the fastest kind of report to close.

If you believe a finding affects CARE ERP or the imaging viewer rather than this
platform, say so in the report; those are separate codebases and may need a separate
channel, and the distinction matters more than the routing.

---

## Disclosure policy

- **Embargo.** A fix ships before the write-up. During the embargo we share the
  technical detail with the reporter only.
- **Publication.** The advisory goes out with the release that fixes it: what was
  affected, which versions, how to detect it, what to do. No credit is required and
  attribution by name happens only with your agreement.
- **This repository stays honest afterwards.** Findings that were ours — a leak the
  code actually had — are recorded in [docs/CONSTITUTION.md](docs/CONSTITUTION.md) §7
  and [docs/security/THREAT_MODEL.md](docs/security/THREAT_MODEL.md) as closed rows
  with the change that closed them. A constitution that only lists intentions is
  decoration, so a report that proves a violation makes the repository worse-looking
  and better-founded at the same time. That is the intended trade.
- **Internal working papers are not published.** Dated audit and review documents
  sometimes inventory weaknesses that are still open in a *live* hospital system we do
  not operate. Those documents are kept out of this repository until the findings are
  closed (`.gitignore` explains it); an advisory describes the problem once the fix
  exists, and never before.

---

## PHI policy

Protected health information does not enter FutureKind's persistence, logs or metrics,
and the platform does not accept that as a promise anyone has to remember to keep.

- **Prompts and completions are never logged.** No log call, no exception message, no
  metric label. The denylist is enforced at the logging boundary
  (`core/gateway/src/futurekind_gateway/observability/logging.py`, `FORBIDDEN_FIELDS`),
  so a developer adding `patient_name=` to a log line is refused by code rather than by
  a reviewer who had a long week.
- **An audit line names decisions, not content.** `skill_audit` records the skill, its
  clinical risk, the alias asked for, the model that answered, the policy that ran and
  the request id. It does not contain clinical text.
- **Errors carry no patient text.** A validation failure reports the rule it broke and
  the field's location; never the rejected value.
- **No identifiers are invented here.** There is no MRN format, no patient id column and
  no PHI table. The Gateway is stateless with respect to clinical content, and the
  copilot holds a draft only in memory: the system of record stays the hospital's.
- **Credentials are not identity.** Today a caller presents a shared API key, so an
  audit line can say *which application* and not *which clinician*. Per-user identity is
  ADR-0004, and until it exists no audit record here can identify a person.
- **Nothing leaves the machine by default.** Local-first is not a preference but a
  configuration: inference goes to the operator's own backend, no cloud provider is
  enabled, and a caller cannot select one. Cross-border or cross-hospital data flow
  needs an explicit constitutional amendment (P14) and, for a real hospital, a written
  agreement before a technical change.

A deployment is still the hospital's controller of its data. This platform is a
processor inside their network, and a report that says otherwise is a finding worth
reporting above.

---

## Security principles

1. **One boundary, and it is small enough to audit.** The Gateway owns permission and
   provenance; LiteLLM owns which weights run. If a hospital cannot read the boundary
   in an afternoon, the boundary is wrong.
2. **Fail closed.** Authentication required with no keys configured answers `503` and
   serves nobody. A catalogue that disagrees with LiteLLM's alias list stops the
   process at startup rather than in front of a clinician. An unknown skill, an
   unimplementable route and a policy the platform cannot enforce are all refusals.
3. **A caller may not relax the rules applied to it.** Policy is configuration the
   operator owns. `allow_downgrade`, `audit_required` and request limits in a request
   body are rejected, not ignored.
4. **Intent, not infrastructure.** An application names a task and never a model, a
   provider or an endpoint. The response reports what answered for provenance; the
   request cannot ask for it. This removes a class of attack — model selection as a
   way around policy — rather than mitigating it.
5. **Least exposure by default.** LiteLLM publishes no host port: it is reachable from
   the platform network and through the Gateway, and `check-ai.sh` asserts the
   negative — that a direct call from the host *fails*. An inventory endpoint is
   authenticated, because a routing table is a map of the deployment.
6. **The identifier in a log is a digest.** A caller is recorded as eight hex
   characters of a SHA-256 over the key: enough to correlate, not enough to reuse.
   Comparisons are constant-time, and "unknown key" and "wrong key" read identically.
7. **Secrets are generated, never typed into an example.** `.env.example` ships shapes
   and an `openssl rand -hex 32` instruction. A placeholder in the shape of a real key
   becomes a published credential the moment someone deploys without reading.
8. **Security claims are tested or withdrawn.** Every principle above has a test that
   fails if the behaviour regresses: the unauthenticated inventory read, the refusal to
   start on alias drift, the rejection of a policy field in a body, the absence of
   prompt text in a log line. Where a claim has no test and no code — audit *retention*
   being the largest one — the documents say it is absent instead of implying it is
   present.

---

## Scope notes

Not a vulnerability, by design:

- A refusal to answer because a skill needs an approval the platform cannot grant.
- A `501` for `stream: true`, or for a provider with no implementation registered.
- The Gateway declining to hold clinical state, so drafts live in the application.
- A deployment that puts no cloud provider in `configs/litellm/config.yaml`.

A vulnerability, and worth reporting:

- Any response, log line or metric label containing prompt or completion text.
- An endpoint returning provider, model or path detail to an unauthenticated caller.
- A way to make the Gateway send a prompt it was not authorised to send.
- A policy field a caller could set, or a downgrade a caller could trigger.
- A skill that answers without an audit line when its policy says `audit_required`.

```text
Last reviewed: 2026-10-08
```
