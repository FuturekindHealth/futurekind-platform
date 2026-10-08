# FutureKind Radiology Copilot

The first clinical application built on FutureKind. One skill, `radiology-report`,
worked through the whole platform:

```
clinician submits                 copilot                  Gateway            LiteLLM          model
clinical indication        →   POST /draft          →   skill → alias    →   alias →     →   weights
previous reports                 (structured report      policy check        deployment
modality                          + quality + confidence)
findings                         POST /check            — no model call —
                                 POST /review
                                 (named sign-off)
                                 POST /export
                                 (the document)
```

`GET /` serves the screen a radiologist actually works in — the four POSTs above are
what its buttons call.

The copilot names no model, no provider, no endpoint and no policy field. It asks
the Gateway what it is *doing* — drafting a radiology report — and the platform
decides everything below that
([ADR-0002](../../docs/adr/ADR-0002-Gateway-vs-LiteLLM.md),
[Routing](../../core/gateway/README-ROUTING.md)).

## What a draft contains

Twelve parts. Six are the report a clinician signs, two are the checks over it, four
are the record of how it was made and under what governance. Each line has one owner,
which is what makes a draft reviewable rather than merely plausible:

| Part | Who writes it | Contents |
| --- | --- | --- |
| `clinical_indication` | **the clinician**, verbatim from the submission | Why the study was done — never restated by the model |
| `technique` | **the department** when supplied, otherwise the model's declaration | Acquisition parameters, or `"Technique not provided."` |
| `findings` | the model, from the dictation | What was seen, in report prose |
| `impression` | the model | The clinical conclusion — the section that carries the risk |
| `recommendations` | the model | What to do now, or `"None."` |
| `follow_up` | the model | When to look again and with what — kept apart from recommendations, because an interval inside a paragraph of referrals is an interval nobody books |
| `quality` | **the copilot**, from nine deterministic checks over the text | `status` (`clear` / `advisory` / `blocking`), the `findings` — each naming its section, quoting the phrase it objected to, and carrying `block` or `advisory` — plus `checks_run` and a `scope` line |
| `confidence` | **the copilot**, computed | `level`: `supported` / `review-carefully` / `not-safe-to-sign`, the `reasons`, and a `basis` that states the limit on its face: no check here reads the images |
| `metadata` | the copilot | Study, modality, the dictation beside the findings it became, `technique_from`, `profile`, `compared_with`, report id, drafted-at, prompt version, generator, review record |
| `model_provenance` | the Gateway, relayed | Request id, model, provider, `selected_by`, attempts, `degraded`, finish reason, tokens, latency |
| `skill` | the copilot | `radiology-report` and the capability it resolved to |
| `policy` | the Gateway, relayed | Clinical risk, approval required, audit required, downgrade allowed |

The model is asked for five keys, not six. An answer that also returns a
`clinical_indication` of its own has it dropped from the document and named in
`metadata.extra_sections` — losing text is the failure to avoid, not the extra key.
Neither `quality` nor `confidence` is offered to the model at all: a system that
asked a model to grade its own clinical safety would be asking the least reliable
party in the room.

```json
{
  "clinical_indication": "58-year-old, sudden severe headache with vomiting, declining consciousness",
  "technique": "Technique not provided.",
  "findings": "A large hyperdense collection in the left basal ganglia … 4.5 cm … 9 mm midline shift …",
  "impression": "Large left basal ganglia haemorrhage with intraventricular extension …",
  "recommendations": "Immediate neurosurgical review. Blood pressure control …",
  "follow_up": "Repeat imaging after any interval change in consciousness …",
  "quality": {"status": "clear", "findings": [], "checks_run": ["dropped_observation", "…all nine, by name…"], "checked_at": "…", "scope": "…none of them has seen the images."},
  "confidence": {"level": "supported", "label": "Grounded in what was submitted", "reasons": ["…"], "basis": "…not a probability that the diagnosis is correct: no check here reads the images."},
  "metadata": {"report_id": "fk-…", "dictated_findings": "…", "technique_from": "model", "compared_with": [], "profile": null, "prompt_version": "radiology-report-draft/0.3.0", "review": {"state": "pending_review"}},
  "model_provenance": {"model": "ollama/qwen3:14b", "provider": "litellm", "degraded": false, "…": "…"},
  "skill": {"name": "radiology-report", "capability": "reasoning"},
  "policy": {"clinical_risk": "high", "approval_required": false, "audit_required": true, "allow_downgrade": false}
}
```

Abbreviated text, real shape — this is the serialisation the tests assert on. A CT
head drafted this way carries `profile: null`, because Alpha has one study profile and
it is for MRI brain; the same draft of an MRI brain names the profile it was checked
under, so a reviewer can tell which nine rules ran.

The printout shows the report and not the dictation — that lives in the JSON, next
to the findings made from it, so a reviewer can compare the two.

## Human review

`POST /review` is where a named clinician takes ownership of the document (P3). It
also carries the `submission` the draft was made from, **and a signature without one is
refused** — the checks compare the text with what was submitted, and after an edit there
is no other text to compare it with.

* `signed` — the nine checks re-run over the amended text first. If any finding is
  still `block`, the sign-off is refused (`422`) with
  `{"blocking": [{"check", "section"}], "sections": […], "submission": …}` in `details`:
  check names and section names only, never the clinical text. Optionally with
  `amendments`, one per section; the sections a human rewrote are listed in
  `metadata.review.amendments`, and a finding in one of them is downgraded to
  `advisory` — the image, not the dictation, is their source, and this application does
  not overrule the person who owns the report. `model_provenance` is left exactly as the
  model reported it, so the record says both what the AI drafted and what the clinician
  approved.
* `returned_for_correction` — requires a comment saying what is wrong, because a
  bare rejection gives the next draft nothing to fix. It creates no attestation, so it
  needs no submission and is not gated on a blocking finding: a radiologist can always
  fix the words or send it back. What they cannot do is sign something this application
  can show is unsupported by what they submitted.

Amending never locks anything: a signed report can be reviewed again and exported
again, in any format. `POST /export` refuses (`409`) only until a clinician has
signed — the department's workflow puts review before export, and an application
that exported past that would be running a different workflow.

Three export formats: `json` for the system that stores it, `text` for print,
`markdown` for the review screen. All three carry the same six sections in the same
order, the sign-off state on the first line, the quality findings and the computed
confidence, and the provenance block at the end. A printed report therefore shows the
checks that were run on it — which is the only part of this design a reader who never
opens the API can verify.

## The nine checks, and what each one can and cannot say

Every check is a comparison of the draft's text with the text the clinician submitted
(indication, modality, study, dictation, technique, previous reports). No check calls a
model, no check has a threshold, and no check has seen the images — the same draft
produces the same findings in 2026 and in 2031, which is the whole reason the engine
exists rather than a prompt that asks the model to be careful.

| Check | What it looks for | Severity |
| --- | --- | --- |
| `dropped_observation` | A dictated clause that never reaches the findings section | `block` |
| `unsupported_measurement` | A number in the draft that is in neither the submission nor a supplied prior. Numbers are compared as whole tokens, so a dictated `19 mm` does not ground a drafted `9 mm`, and a digit inside `T2` grounds nothing | `block` in report prose, `advisory` in plan language ("repeat in 6 weeks") |
| `invented_history` | "unchanged", "stable since", "resolved" — with no previous report supplied to compare against | `block` |
| `unsupported_certainty` | An absolute in the **impression** ("no evidence of", "normal") while the submitted text hedges (possible, subtle, uncertain) — a differential and a confirmation are different documents | `block` |
| `format_breach` | Markdown, bullets or headings inside a section that will be printed | `block` |
| `invented_identifier` | A name, MRN, UHID or accession number that was not supplied | `block` |
| `unsupported_absence` | A negative this exam cannot answer — `"no pulmonary embolism"` on a brain study. The subject is searched in the submitted text, so a referrer who did raise it gets an answer without being called an invention | `advisory` |
| `structure_coverage` | A structure the profile lists that neither the dictation nor the draft mentions | `advisory` — a profile can never block for something nobody described |
| `self_reported_confidence` | The model answering with its own confidence key | `advisory`, and the number is not shown to the reviewer |

`block` refuses a signature until the words change. `advisory` is shown and the report
proceeds. A finding in a section the clinician has just rewritten is downgraded to
`advisory` either way: the person looking at the pixels owns that section, and an
application that overruled them would be asserting knowledge it does not have.

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
| A sign-off with no `submission` | `422 review_invalid` | Nothing to check the signed text against, so no attestation is recorded |
| A sign-off while a `block` finding stands | `422 review_invalid`, naming the checks and sections | A clinician can always correct the words or return the draft; what they cannot do is have the record say they attested to text this application can show is unsupported |
| More than five previous reports, oversized previous reports, or a prior with no date | `422 invalid_request` | Priors are the only legitimate source of a comparison, and an unbounded block of old report text is both a prompt-overflow and a second copy of a patient history |
| A submission key the contract does not define (`patient_name`, `mrn`) | `422 invalid_request` | `extra="forbid"`: this application has no field that can hold an identifier, which is stronger than a rule about not filling one |
| A model answer that returns its own `confidence` | `advisory`, and the value is not shown | A model's certainty does not track its correctness; showing it would train the reviewer to trust the wrong number |
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
python -m pytest   # 225 tests: 219 deterministic, 6 over real sockets
```

Use the interpreter from a virtualenv with `fastapi`, `uvicorn`, `pydantic`,
`httpx` and `PyYAML` installed — the same one the Gateway is installed in, so the
two suites exercise one shared transport.

To work in it rather than test it, start both processes (LiteLLM and the model
behind it must already be reachable, or every draft refuses with a visible reason):

```bash
python -m futurekind_gateway          # the Gateway, on 8100
python -m futurekind_radiology        # the copilot and its screen, on 8200
```

Then open **http://127.0.0.1:8200/** — that is the whole clinical surface in Alpha:
the submission on the left, the six editable sections in the middle, the quality
findings, confidence and provenance on the right. The screen is one static HTML file
shipped inside the package: no CDN, no framework, no font fetched from anywhere, no
localStorage and no session, so nothing a patient said is written to a browser or to a
second machine. It calls the same four endpoints a hospital integration would call, and
every keystroke that changes a checkable claim re-runs the checks through `POST /check`.

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

* **One study profile.** MRI brain, matched on the label the department typed. An MRI
  knee runs the same nine checks with no structure list and no out-of-scope negatives —
  a weaker pass, and the document says so in `metadata.profile` rather than pretending
  the two were checked equally.
* **The checks read text, never pixels.** They can show a statement is unsupported by
  what the clinician submitted; they cannot show a statement is true, and they cannot
  catch a finding that was dictated wrongly in the first place. `quality.scope` prints
  that limit on the screen and in the export.
* **A count in words is a count missed.** `2 lesions` is caught; `two lesions` is not.
  Widening the window to catch `2 white matter lesions` would also block
  `3 months later, no lesions`, and a check that blocks a correct sentence is a check
  that gets switched off — so the limit is stated in `tests/test_quality.py` and here
  instead of being papered over. The same trade leaves one more residue: numbers are
  matched as whole tokens, which kills the `9 mm` against a dictated `19 mm` near miss,
  but a bare age or date in the submitted text is still a number — a submitted
  "45-year-old" grounds a drafted 45 mm. Both are tested by name.
* **The golden dataset is unratified.** All 100 cases in `GOLDEN_DATASET.yaml` carry
  `ratified: pending`. A golden test therefore proves the pipeline holds a shape and
  refuses the `must_not_say` list; it does not prove a clinician blessed the wording.
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
