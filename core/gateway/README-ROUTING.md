# Routing

Applications never choose infrastructure.

An application states **what it is doing**. Everything below that statement is
the platform's decision, and the platform is free to change it.

## The five names, and who may speak them

| Name | Spoken by | Example | Decides |
| --- | --- | --- | --- |
| **Skill** | the application | `radiology-report` | what clinical work is being done |
| **Policy** | the operator, in `models.yaml` | `clinical_risk: high` | how carefully that work is treated |
| **Capability** | the Gateway | `reasoning` | what class of processing serves it |
| **Alias** | the Gateway, addressed to LiteLLM | `fk-reasoning` | which entry to ask LiteLLM for |
| **Model** | LiteLLM only | `qwen3:14b` | which weights actually run |

**Provider** is a sixth word, and it belongs to the Gateway alone: it names the
transport a request is handed to, which today is `litellm` for every row in the
catalogue. It is not the backend family — `ollama/…` sits inside the model string
because choosing a backend is LiteLLM's decision, and a second copy of that
decision here would be two answers to one question.

A request may carry a skill, and may still carry a capability as a legacy
refinement. It may **not** carry a model, a provider, an endpoint or a policy
field: a body that names one is rejected with `422 invalid_request`.

Skills declared in the catalogue today, with the risk level each one carries:

| Skill | Capability | Clinical risk | Downgrade allowed | Audited |
| --- | --- | --- | --- | --- |
| `platform-chat` | `default` | low | yes | yes |
| `radiology-report` | `reasoning` | high | no | yes |
| `pathology-review` | `reasoning` | high | no | yes |
| `clinical-chat` | `default` | moderate | yes | yes |
| `summarize-document` | `fast` | low | yes | no |

`platform-chat` is the one non-clinical skill, and the one an OpenAI-format
interface can be pointed at today.

Naming a skill is not only how an application says what it needs — it is how it
gets the policy written for that need. A request that names only a capability
runs under the default policy and reports its risk level as `unspecified`.

Capabilities today are `default`, `fast` and `reasoning`. They conflate a
service class with a task type; the split into `chat`, `vision`, `embedding` and
an explicit tier axis is tracked as remaining work, not as something this file
claims is finished.

## Why the boundary is drawn there

Accepting a model name in a request would put infrastructure into the public API
of every clinical application. Changing hardware would then be a breaking change
for those applications — the opposite of what this platform is for.

Keeping model selection in LiteLLM instead means the Gateway stays small enough
for a hospital to audit, and one table names the weights rather than two.

> Changing hardware never requires application changes.
