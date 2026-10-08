# Skill examples — twelve skills at wire level

Companion to `docs/product/SKILL_LIBRARY.yaml`. The catalogue gives 121 clinical
intents in compact form; expanding 121 verbatim wire exchanges would be ~3,000 lines of
near-identical JSON. Twelve are expanded here instead: the six highest-risk, and the six
whose **output shape** is not the obvious one. A reviewer who reads this file and the
catalogue header has read everything that constrains a skill.

## What every example has in common

Three things are true of all twelve and are stated once rather than twelve times.

**1. Only four of these skills exist in the platform today.** Live skills are
`platform-chat`, `radiology-report`, `pathology-review`, `clinical-chat`,
`summarize-document` (`core/gateway/models.yaml`). Every other skill named in this
repository is a *design* until its stanza is copied into `models.yaml` by hand, together
with its alias in `configs/litellm/config.yaml` — and the Gateway's startup check
refuses a half-made change (SPEC-07-03). So most responses below are annotated
**"after authorisation"**. Asking for an unauthorised skill today returns:

```json
{ "error": { "code": "unknown_skill", "message": "Skill 'ed-chest-pain-pathway' is not declared in the model catalogue",
  "retryable": false, "request_id": "fk-7c1d…", "details": { "skill": "ed-chest-pain-pathway",
  "known_skills": ["clinical-chat", "pathology-review", "platform-chat", "radiology-report", "summarize-document"] } } }
```

That is the correct behaviour and it is why the library can hold 121 entries safely: an
unreviewed skill cannot be reached.

**2. A body that names a model or a provider is rejected `422`.** Not ignored — rejected
(ADR-0002 rule 1, Constitution P8). The caller selects a *skill*; the platform selects
the model and then reports what it chose.

**3. The `policy` block is on every response, and `approval_required: true` currently
means refusal, not workflow.** The Gateway has no approvals service, so a skill that
declares it gets `403 approval_required` (`policy.py:305-320`,
`docs/architecture/gateway-policy.md:213`). Every clinical skill in `models.yaml` is
therefore declared `approval_required: false` and the sign-off is enforced by the
application — see D4 in `docs/product/RADIOLOGY_WORKFLOW.md`. Where an example shows
approval, it shows the *application's* review step, which is not a platform **Approval**
and must not be described as one.

Response envelopes carry `request_id`, `skill`, `capability`, `model`, `provider`,
`selected_by`, `policy`, `attempts`, `degraded`, `content`, `finish_reason`,
`usage`, `latency_ms` (SPEC-06-09, SPEC-06-10). Examples below are abridged to the
fields that matter for the point being made; `usage` is `{prompt_tokens,
completion_tokens}` and nothing else, because the Gateway does not report a total it did
not compute.

---

## A. The six highest-risk

### A1. `ct-head-acute-stroke` — after authorisation

Why here: the report this skill drafts can trigger thrombolysis, and the failure mode is
a confident number the images do not contain.

```json
POST /chat
{
  "skill": "ct-head-acute-stroke",
  "messages": [
    { "role": "system", "content": "You are drafting an acute stroke CT impression from the reporting radiologist's dictation. Report only what the dictation states. Never give a thrombolysis decision. If the dictation does not state a measurement, write 'not stated' rather than estimating. Answer with one JSON object and nothing outside it." },
    { "role": "user", "content": "Indication: 67M, 3 h left MCA syndrome, NIHSS 14, last known well 02:40, no anticoagulants.\nStudy: CT head non-contrast, thin sections.\nFindings: No haemorrhage. Loss of insular ribbon right, obscured left lentiform nucleus. ASPECTS 7 on the reading the reporter performed. No midline shift. Hyperdense MCA sign not sought.\nTechnique: supplied by department." }
  ]
}
```

```json
200
{
  "request_id": "fk-2f9a…",
  "skill": "ct-head-acute-stroke",
  "capability": "reasoning",
  "model": "ollama/qwen3:14b",
  "provider": "ollama",
  "selected_by": "skill_policy",
  "policy": { "clinical_risk": "critical", "approval_required": false, "audit_required": true, "allow_downgrade": false },
  "attempts": 1,
  "degraded": false,
  "content": "{\"findings\":\"No intracranial haemorrhage. Right insular ribbon loss and obscuration of the left lentiform nucleus, consistent with early ischaemic change. ASPECTS 7 as read by the reporting radiologist. No midline shift. Hyperdense MCA sign: not stated.\",\"impression\":\"Acute right MCA territory ischaemic change without haemorrhage, ASPECTS 7. Within the reported 3-hour window on the stated clinical timeline.\",\"recommendations\":\"Thrombolysis eligibility is a clinical decision for the stroke team on the stated timeline and NIHSS; the imaging does not exclude treatment. Hyperdense vessel sign not assessed — consider CTA if the team requires vessel imaging. Not for reporting until signed by the radiologist.\"}",
  "finish_reason": "stop",
  "usage": { "prompt_tokens": 512, "completion_tokens": 198 },
  "latency_ms": 9840
}
```

What the application does with it: sections go into the composer as proposals. The ASPECTS
value is *the radiologist's read*, carried verbatim from the dictation — if the dictation
had not stated it, the draft would say `not stated`, and the UI requires the number to be
typed rather than accepted (§4.4 of the workflow).

The failure this shape prevents: `not stated` for the hyperdense sign instead of a
plausible "no hyperdense MCA sign". Absence of evidence written as evidence of absence is
the single most dangerous sentence this product can generate.

### A2. `ct-chest-pulmonary-embolism` — after authorisation

Why here: a negative that depends on a technical condition the caller may not have
supplied.

```json
POST /chat
{
  "skill": "ct-chest-pulmonary-embolism",
  "messages": [
    { "role": "system", "content": "Draft a CTPA impression from the radiologist's dictation. A study the dictation describes as technically inadequate cannot be reported as negative for embolism — say what the limitation is instead. Never give an anticoagulation plan. One JSON object only." },
    { "role": "user", "content": "Indication: 34F, pleuritic pain, tachycardic 112, D-dimer 2400, hypoxic 91% on air.\nStudy: CTPA.\nFindings: Segmental filling defect right lower lobe pulmonary artery. Main and left pulmonary arteries clear. LV:RV ratio approximately 1.2. No pericardial effusion. Small right pleural effusion. Bolus timing adequate." }
  ]
}
```

```json
200
{
  "skill": "ct-chest-pulmonary-embolism",
  "capability": "reasoning",
  "degraded": false,
  "policy": { "clinical_risk": "critical", "approval_required": false, "audit_required": true, "allow_downgrade": false },
  "content": "{\"findings\":\"Segmental filling defect in the right lower lobe pulmonary artery, in an optimally timed bolus. No filling defect in the main or left pulmonary arteries. RV:LV ratio approximately 1.2, indicating right heart strain. Small right pleural effusion. No pericardial effusion.\",\"impression\":\"Acute pulmonary embolism, segmental, right lower lobe, with imaging evidence of right ventricular strain. Submassive physiology on imaging alone — clinical risk stratification is not an imaging call.\",\"recommendations\":\"Escalate now: the combination of hypoxia, tachycardia and RV strain requires a senior decision on disposition and reperfusion assessment. Anticoagulation and thrombolysis decisions are the treating team's, not this report's.\"}",
  "finish_reason": "stop",
  "latency_ms": 11230
}
```

Note what the draft refuses: it reports strain and names the escalation, and stops short
of treatment. Also note that if `Bolus timing adequate` had been absent, the correct
output is a limitation statement, not "no filling defect identified" — that variant is a
golden case, `C-11` in `GOLDEN_DATASET.yaml`.

### A3. `ed-chest-pain-pathway` — after authorisation

Why here: not a radiology skill at all. It shows that the same governance applies to a
clinical pathway, and it exercises the arithmetic guard.

```json
POST /chat
{
  "skill": "ed-chest-pain-pathway",
  "messages": [
    { "role": "system", "content": "Assist with an emergency-department chest pain impression from the data given. Compute nothing that was not supplied. Do not discharge and do not name a drug dose. One JSON object only." },
    { "role": "user", "content": "52M, epigastric discomfort 40 min, sweating, HTN, smoker.\nECG: sinus rhythm 88, no ST change, T inversion V5-V6 new against a 2024 tracing.\nTroponin: 14 ng/L at 0 h, 61 ng/L at 3 h (99th percentile 14).\nHEART score 7.\nBP 158/92, sats 97%, no failure signs." }
  ]
}
```

```json
200
{
  "skill": "ed-chest-pain-pathway",
  "capability": "reasoning",
  "policy": { "clinical_risk": "critical", "approval_required": false, "audit_required": true, "allow_downgrade": false },
  "content": "{\"impression\":\"Rising troponin (14 to 61 ng/L, above the 99th percentile) with new lateral T-wave inversion and a HEART score of 7 — high-risk acute coronary syndrome, NSTEMI pattern.\",\"reasoning\":\"Two independent abnormalities (biochemical rise, ECG change) plus a high clinical score. The single troponin value at 0 h would not have been sufficient; the delta is the finding, and both numbers were supplied.\",\"escalation\":\"Admit, urgent cardiology review, invasive strategy per the receiving team. Do not discharge from the ED on this impression.\",\"missing\":[\"Weight and renal function — relevant to antithrombotic choice, not stated in the data given\"]}",
  "finish_reason": "stop",
  "latency_ms": 8100
}
```

The `missing` key is the point. The skill names what it was not given rather than
silently reasoning without it. A pathway skill that never admits an absent input is a
liability, not an assist.

### A4. `medication-reconciliation` — after authorisation

Why here: the output is a **discrepancy table**, not prose, and prose is what a model
will produce unless the schema forbids it.

```json
POST /chat
{
  "skill": "medication-reconciliation",
  "messages": [
    { "role": "system", "content": "Compare home, prescribed and administered medicines. Output one JSON object with a `discrepancies` array. Each item: drug, kind (omission | dose | duplication | route | timing | unknown-home-dose), evidence quoted from the lists given, and clinical risk. Where the lists are insufficient to classify, kind is `insufficient-data` and you say what is missing. Do not decide whether to restart anything." },
    { "role": "user", "content": "Home list (GP): warfarin 5 mg nocte (AF, CHA2DS2-VASc 4), amlodipine 10 mg, atorvastatin 20 mg, salbutamol PRN.\nInpatient chart days 1-4: enoxaparin 40 mg od from day 2, amlodipine 10 mg, atorvastatin 20 mg.\nAdministration record: warfarin not given since day 1. INR today 1.2 (therapeutic range 2-3).\nQuestion: discharge day 5 planned." }
  ]
}
```

```json
200
{
  "skill": "medication-reconciliation",
  "capability": "reasoning",
  "policy": { "clinical_risk": "critical", "approval_required": false, "audit_required": true, "allow_downgrade": false },
  "content": "{\"discrepancies\":[{\"drug\":\"warfarin\",\"kind\":\"omission\",\"evidence\":\"Home 5 mg nocte; charted enoxaparin from day 2 instead; no warfarin administration since day 1; INR 1.2 (subtherapeutic)\",\"clinical_risk\":\"Thromboembolism in AF with CHA2DS2-VASc 4 and a subtherapeutic INR. Bridging was started and the oral anticoagulant was not resumed.\",\"decision_required\":\"Restart, bridge, or document an intentional hold — clinician, before discharge\"},{\"drug\":\"enoxaparin\",\"kind\":\"unknown-home-dose\",\"evidence\":\"Prophylactic dose on the chart; not on the home list; no thrombosis or surgical indication stated in the data given\",\"clinical_risk\":\"Cannot be assessed without the indication\",\"decision_required\":\"State the indication or stop\"},{\"drug\":\"salbutamol\",\"kind\":\"omission\",\"evidence\":\"On home list, absent from the chart and the administration record\",\"clinical_risk\":\"Low if truly PRN, higher if the patient is dependant — inhaler technique and use not documented\",\"decision_required\":\"Confirm PRN status\"}],\"matched\":[\"amlodipine 10 mg\",\"atorvastatin 20 mg\"],\"insufficient_data\":[\"No respiratory or surgical history supplied, so the enoxaparin indication cannot be classified\"]}",
  "finish_reason": "stop",
  "latency_ms": 12600
}
```

The failure this shape prevents: a paragraph that mentions warfarin in passing. A table
row forces a `decision_required` line, which is what a discharge checklist consumes.

### A5. `pre-anaesthetic-assessment` — after authorisation

Why here: the skill produces a *grade*, which looks like a decision, and the design must
make it not one.

```json
POST /chat
{
  "skill": "pre-anaesthetic-assessment",
  "messages": [
    { "role": "system", "content": "Draft a pre-anaesthetic assessment. You may state an ASA grade from the comorbidity given. You must not state fitness for anaesthesia, must not choose a technique, and must end with the questions an anaesthetist must answer. One JSON object." },
    { "role": "user", "content": "62M, elective inguinal hernia repair.\nPMH: type 2 diabetes on metformin, ischaemic heart disease (PCI 2022), EF 45% on 2025 echo, mild COPD.\nAirway: Mallampati 4, neck extension limited, mouth opening 3 cm, previous anaesthesia uneventful (2022, LMA).\nDrugs: metformin, aspirin 75, atorvastatin, bisoprolol.\nAllergies: none documented.\nBloods: Hb 131, Na 138, K 4.1, creatinine 112, eGFR 58." }
  ]
}
```

```json
200
{
  "skill": "pre-anaesthetic-assessment",
  "capability": "reasoning",
  "policy": { "clinical_risk": "critical", "approval_required": false, "audit_required": true, "allow_downgrade": false },
  "content": "{\"asa_grade\":\"ASA III (severe systemic disease with daily activity limitation not implied by the data given — the EF 45% and IHD place this at III on the stated history).\",\"airway\":\"Mallampati 4 with limited neck extension and 3 cm mouth opening: anticipated difficult mask ventilation possible, intubation previously uneventful with LMA in 2022. Prior plan should be retrieved.\",\"cardiovascular\":\"EF 45%, IHD with PCI 2022, on bisoprolol. Most recent echo 2025 — confirm currency against local rule for the stated EF.\",\"medication_actions\":\"Metformin with eGFR 58: day-of-surgery holding and renal plan are decisions for the anaesthetist and surgeon. Aspirin 75: continuation or cessation is a surgical-bleeding-risk decision. Bisoprolol: continue.\",\"questions_for_the_anaesthetist\":[\"Airway equipment and operator for a Mallampati 4 with limited extension — which plan, and who is present?\",\"Is a 2025 echocardiogram adequate for this operation under local practice, or is a current one required?\",\"Perioperative glycaemic plan at eGFR 58, including metformin hold and monitoring frequency.\",\"Antiplatelet decision for hernia repair on aspirin.\",\"Postoperative level: ward or higher dependency, given EF 45% plus COPD.\"],\"not_stated\":[\"Functional capacity in METs\",\"smoking status and current COPD severity\",\"obstructive sleep apnoea screening\",\"whether the surgical team expects a day-case discharge\",\"date of the most recent echocardiogram relative to the operation\"]}",
  "finish_reason": "stop",
  "latency_ms": 10400
}
```

`not_stated` is the requirement here, not a courtesy. A pre-anaesthetic note that reads as
complete is the document most likely to be filed with its omissions unchased, so the draft
lists what it was not given.

The failure this shape prevents: an unqualified "fit for general anaesthesia". Fitness is
a human act; the grade is data entry, and the difference is what P11 exists for.

### A6. `laboratory-critical-value-review` — **blocked** (ADR-0005)

Why here: it is one of only two skills in the catalogue marked `blocked_by`, and what it
shows is that the blocker is a *decision*, not a missing model.

```json
POST /chat
{
  "skill": "laboratory-critical-value-review",
  "messages": [
    { "role": "system", "content": "Identify a critical laboratory value and draft the notification that must follow. Do not assign the notification to a person; name the role that must receive it and leave the recipient field for the platform record." },
    { "role": "user", "content": "Platelets 18 x10^9/L, ward 4, 71F day 2 post-hip arthroplasty, on enoxaparin since day 1, no bleeding documented, FBC 24 h ago 96. Location: inpatient ward." }
  ]
}
```

What happens today, once the stanza is authorised but before ADR-0005 exists:

```json
403
{
  "error": {
    "code": "approval_required",
    "message": "Skill 'laboratory-critical-value-review' requires clinical approval, which this Gateway cannot verify yet",
    "retryable": false,
    "request_id": "fk-b40e…",
    "details": {
      "skill": "laboratory-critical-value-review",
      "clinical_risk": "critical",
      "required": "approval",
      "hint": "record the approval in an approvals service and have it call the Gateway, or set approval_required: false for this skill if its risk level allows it"
    }
  }
}
```

Quoted from `core/gateway/src/futurekind_gateway/errors.py:87-110`, because the wording is
the design: it names what is missing rather than pretending to grant it.

**And note the deadlock this skill is in, which is the strongest argument in the repository
for ADR-0005.** A `critical` skill cannot be authorised at all today:

| Declaration | What happens | Evidence |
| --- | --- | --- |
| `clinical_risk: critical`, `approval_required: false` | **Startup fails.** The catalogue refuses to load | `policy.py:242-252` — "a critical skill may not run without sign-off" |
| `clinical_risk: critical`, `approval_required: true` | **Every request fails** with `403 approval_required` | `policy.py:305-320` |
| `clinical_risk: high`, `approval_required: false` | Loads and answers — which is how `radiology-report` ships | `models.yaml:54-66`; the escalation rules only force `audit_required` and `allow_downgrade` (`policy.py:225-241`) |

So the platform's own governance makes critical skills unreachable, in the *safe* direction,
and 37 of the 121 designed skills are `critical`. `laboratory-critical-value-review` is marked
`blocked_by: ADR-0005` in the catalogue for exactly this reason: the escape hatch the `hint`
offers ("set approval_required: false if its risk level allows it") is closed by configuration
for the skills that need it most. That is fail-closed working as intended, and it is also why
"the blockers are decisions, not infrastructure" is the honest summary of this file.

The design answer is not to flip the declaration to `false`. A critical-value
notification is a **timed clinical act** — the hospital's rule is that someone must be
reached within a window, and the record must show which named human raised it and which
named human acknowledged it. That is ADR-0005 (SPECIFICATION §17), and until it is
written the Gateway is right to refuse rather than let an application pretend.

What a correct response would eventually contain, so the ADR has something to be written
against:

```json
{ "content": "{\"critical\":true,\"value\":\"platelets 18 x10^9/L\",\"direction\":\"falling (96 → 18 in 24 h)\",\"action_window\":\"notify the responsible ward clinician within 30 minutes of this result being flagged\",\"draft_notification\":\"Ward 4, 71F day 2 post hip arthroplasty: platelets fallen 96 → 18 in 24 hours. Critical. Withhold further enoxaparin pending review — the decision is the clinician's. Haematology input advised; HIT is a stated possibility given the timing after heparin exposure.\",\"recipient_role\":\"ward responsible clinician, with haematology on the same notification\",\"not_stated\":[\"who has been notified\",\"whether the sample was haemolysed or clotted — repeat is implied by the fall\",\"bleeding status at the time of the result\"]}" }
```

`not_stated` carries "who has been notified" deliberately: the platform must not be able
to answer a question whose answer is a medicolegal fact it does not yet store.

---

## B. The six non-obvious output shapes

### B1. `radiology-worklist-triage` — a batch, and the only skill whose input is many patients

Why here: every other skill answers about one case. This one answers about fifty, and the
governance problem is what it must *not* put in the answer.

```json
POST /chat
{
  "skill": "radiology-worklist-triage",
  "messages": [
    { "role": "system", "content": "Order the studies below for reporting priority and give one short reason per study. Return only accession, priority and reason. Do not restate patient names, dates of birth or clinical narratives in the answer — the reason must not repeat the referral text. If a study cannot be prioritised from the data given, priority is 'undetermined'." },
    { "role": "user", "content": "50 studies. [accession, modality, ordered-by location, referral question, red-flag terms present]\nACC-20261008-CT-011 | CT head | ED | 'sudden headache, worst ever' | yes\nACC-20261008-CT-012 | CT head | ward 4 | 'day 3 post-craniotomy, new confusion' | yes\nACC-20261008-US-007 | US abdomen | OPD | 'RUQ pain, LFT deranged, bili 84' | yes\n… 47 more" }
  ]
}
```

```json
200
{
  "skill": "radiology-worklist-triage",
  "capability": "fast",
  "policy": { "clinical_risk": "high", "approval_required": false, "audit_required": true, "allow_downgrade": false },
  "content": "{\"ordering\":[{\"accession\":\"ACC-20261008-CT-012\",\"priority\":1,\"reason\":\"inpatient, new neurological change after craniotomy\"},{\"accession\":\"ACC-20261008-CT-011\",\"priority\":2,\"reason\":\"ED, history consistent with thunderclap onset\"},{\"accession\":\"ACC-20261008-US-007\",\"priority\":3,\"reason\":\"jaundice pattern with pain — obstruction not excluded\"},{\"accession\":\"ACC-20261008-CT-019\",\"priority\":\"undetermined\",\"reason\":\"referral question is a follow-up interval with no stated change\"}],\"count\":50,\"ordering_basis\":\"stated clinical acuity only\"}",
  "latency_ms": 2100
}
```

Constraints this shape imposes, and why they are the design:

- Priority 1 is **inpatient deterioration**, not the sickest-sounding outpatient. An ED
  referral text is written to be alarming; a ward patient who has just changed is the one
  whose plan is stalled by the wait.
- `undetermined` is a real value. A triage skill that always ranks produces a queue nobody
  defends.
- The reason field never quotes the referral. The ordering is displayed on a shared
  screen in a corridor (§`UI_UX.md` §2), so an answer that restates clinical narrative
  leaks into a hallway.

### B2. `neuro-glasgow-coma-scale` — arithmetic that must refuse

Why here: it is the clearest demonstration that a skill can be *correct* and still be
unsafe if it is allowed to complete a number.

```json
POST /chat
{
  "skill": "neuro-glasgow-coma-scale",
  "messages": [
    { "role": "system", "content": "Compute a GCS total only if all three components are given as numbers. If any component is absent or descriptive, return `complete: false` and state which component is missing. Never infer a component from a narrative description." },
    { "role": "user", "content": "GCS recorded as E4, V 'confused words', M6." }
  ]
}
```

```json
200
{ "content": "{\"complete\":false,\"given\":{\"eye\":\"E4 (spontaneous)\",\"verbal\":\"described as 'confused words' — not a numeric score\",\"motor\":\"M6 (obeys commands)\"},\"cannot_compute\":\"verbal component is not numeric\",\"if_confirmed_as_V4\":{\"total\":14,\"basis\":\"E4 + V4 + M6\"},\"rule\":\"the confirmation must come from the assessing clinician, not from this conversion\"}" }
```

And the parallel case that must *not* happen, which is why the constraint is written as
refusal rather than guidance: with `V "drowsy, few words"` the model must not return 13.
A GCS total that moved the patient's category on a TBI pathway is a documented clinical
act, and this is exactly where a helpful conversion becomes a fabricated observation.

### B3. `mg-density-notice` — the output goes to a patient, and the law dictates its content

Why here: the register changes. Findings text is not the deliverable; a letter is.

```json
POST /chat
{
  "skill": "mg-density-notice",
  "messages": [
    { "role": "system", "content": "Write a patient-facing density notice. Plain language, no risk percentages, no reassurance that is not evidence-supported, must state what the screening result was and what the density means for future screening, must state who to contact. Do not diagnose." },
    { "role": "user", "content": "Screening mammogram, 48F, result normal, breast density category C (heterogeneously dense). Programme: national screening. Recall interval unchanged." }
  ]
}
```

```json
200
{
  "skill": "mg-density-notice",
  "capability": "default",
  "policy": { "clinical_risk": "moderate", "approval_required": false, "audit_required": true, "allow_downgrade": false },
  "content": "{\"letter\":\"Dear Madam,\\n\\nYour screening mammogram has been reported as normal.\\n\\nYour breast tissue is described as heterogeneously dense. This means the mammogram shows a lot of normal fibrous and glandular tissue rather than fatty tissue. It is common and it is not a diagnosis.\\n\\nWhy we tell you: dense tissue can make it harder for a mammogram to show an abnormality. It is a bit like reading a page with the writing in pale ink. Because of this, a normal mammogram in dense breasts is slightly less certain than a normal mammogram in fatty breasts.\\n\\nWhat happens next: your next screening appointment is at the usual interval. No extra test has been recommended from this result.\\n\\nWhat to do between appointments: if you notice a lump, skin change, nipple discharge or a change you can feel that was not there before, contact your family doctor or the screening unit. Do not wait for the next invitation.\\n\\nThe screening team can be contacted on the number printed at the top of this letter.\",\"approved_for_send_by\":\"named clinician required before release\",\"not_included\":[\"a sensitivity figure\",\"a lifetime risk estimate\",\"any comparison to other patients\"]}"
}
```

Two design notes. The `approved_for_send_by` field exists because a letter that reaches a
patient is a clinical act, and this is the one skill where the application's own gate is
visibly insufficient — the release must be an ERP decision, not a copilot one. And
`not_included` names the numbers the model was tempted by, because a notice containing a
sensitivity percentage becomes a document the department has to defend.

### B4. `icd10-coding-suggestion` — codes, confidence, and the boundary it must not cross

Why here: the output is a code list, and a code is the artefact that becomes an
insurance claim.

```json
POST /chat
{
  "skill": "icd10-coding-suggestion",
  "messages": [
    { "role": "system", "content": "Suggest ICD-10 codes from the record supplied. For each, give the evidence phrase from the record and a confidence. Where the record does not specify a required character (laterality, acuity, encounter type), say which detail is missing rather than choosing a code. Never output a code you had to invent a detail to reach." },
    { "role": "user", "content": "Discharge summary extract: 'Type 2 diabetes mellitus with diabetic ketoacidosis, treated in HDU. Chronic kidney disease stage 3a. Hypertension. Right foot: neuropathic ulcer, skin only, no bone involvement, healing at discharge.' Episodes: this admission only." }
  ]
}
```

```json
200
{
  "skill": "icd10-coding-suggestion",
  "capability": "default",
  "policy": { "clinical_risk": "moderate", "approval_required": false, "audit_required": true, "allow_downgrade": false },
  "content": "{\"suggestions\":[{\"code\":\"E11.1\",\"label\":\"Type 2 diabetes mellitus with ketoacidosis\",\"evidence\":\"'Type 2 diabetes mellitus with diabetic ketoacidosis'\",\"confidence\":\"high\"},{\"code\":\"N18.3\",\"label\":\"Chronic kidney disease, stage 3\",\"evidence\":\"'Chronic kidney disease stage 3a'\",\"confidence\":\"high\",\"note\":\"3a versus unspecified 3 depends on the local code set edition — confirm\"},{\"code\":\"I10\",\"label\":\"Essential (primary) hypertension\",\"evidence\":\"'Hypertension'\",\"confidence\":\"medium\",\"note\":\"'Essential' is an assumption; the record does not state a cause\"},{\"code\":\"E11.6\",\"label\":\"Type 2 diabetes with neurological complications\",\"status\":\"withheld\",\"reason\":\"the record states ketoacidosis, not coma or stupor — DKA does not imply a neurological complication code\"},{\"code\":\"L97.-\",\"label\":\"Non-pressure chronic ulcer of lower limb\",\"evidence\":\"'neuropathic ulcer, skin only, right'\",\"confidence\":\"medium\",\"missing\":[\"site within the foot (heel / midfoot / other) required for the 6th character in most local extensions\",\"whether the ulcer is specified as limited to breakdown of skin (depth character)\"]}]}",
  "finish_reason": "stop"
}
```

The `E11.6` row is the shape's point. It sits in the same array with
`status: "withheld"` and a reason, because a coder needs to see that the code was
*considered and rejected* — otherwise the absence is indistinguishable from an oversight,
and the rework request is exactly "why isn't the DKA complication coded". Note also that
`confidence: "medium"` on `I10` is the honest one: the local code set forces a choice
between "essential" hypertension and unspecified, and the record did not make it.

### B5. `tumour-staging-note` — a stage group that must not be assembled from gaps

Why here: the output is the number that decides treatment, and the correct behaviour is
frequently to decline to produce it.

```json
POST /chat
{
  "skill": "tumour-staging-note",
  "messages": [
    { "role": "system", "content": "Assemble a TNM staging note from the components supplied. Use 'c' or 'p' prefixes as the evidence type given. If any element required for a stage group is missing, output the elements you have and set stage_group to null with the missing elements named. Do not assume node-negativity from an unexamined specimen." },
    { "role": "user", "content": "Colectomy specimen, moderately differentiated adenocarcinoma, tumour 4.1 cm through muscularis propria into pericolic fat, no penetration of visceral peritoneum. 2 of 18 nodes involved, no extranodal deposit. Circumferential margin clear by 2 mm. Lymphovascular invasion present. No distant deposits on CT chest/abdomen/pelvis. Mismatch repair proficient. No preoperative therapy." }
  ]
}
```

```json
200
{
  "skill": "tumour-staging-note",
  "capability": "reasoning",
  "policy": { "clinical_risk": "critical", "approval_required": false, "audit_required": true, "allow_downgrade": false },
  "content": "{\"prefix\":\"p (resected specimen, no neoadjuvant therapy stated)\",\"T\":\"pT3 (tumour extends through muscularis propria into pericolic fat; visceral peritoneum not involved)\",\"N\":\"pN1a (2 of 18 regional nodes; 1-3 nodes is N1a; no extranodal deposit stated)\",\"M\":\"cM0 (no distant deposits on stated cross-sectional imaging)\",\"stage_group\":\"IIIB\",\"stage_group_basis\":\"pT3 pN1a cM0, colon, AJCC 8th edition grouping\",\"margin\":\"R0 — circumferential margin clear by 2 mm; the 1 mm threshold for a threatened CRM means this is clear but close\",\"lymphovascular_invasion\":\"present — a risk modifier for adjuvant decision, not a stage element\",\"mismatch_repair\":\"proficient (dMMR/MSI status noted for prognostic use, not for staging)\",\"adequacy\":\"18 nodes examined; fewer than 12 would make pN unreliable — this specimen is adequately sampled\",\"missing_or_stated_as_absent\":[\"tumour budding not reported\",\"perineural invasion not reported — absence is not stated, so it is unknown rather than negative\"],\"for_the_multidisciplinary_team\":[\"Adjuvant eligibility is a team decision on fit, timing and the stated risk modifiers\",\"the 2 mm CRM is the number the team will ask about first\"]}"
}
```

The last two keys are the design. `unknown rather than negative` is written out because
"perineural invasion: no" in a staging note is a claim nobody examined, and a team reading
a generated note cannot tell the difference from a measured one.

And note the element the model had to get right: **2 of 18 nodes is `pN1a`, not `pN1b`**
(N1a = 1–3 regional nodes, N1b = 4–6, in the edition this note uses). The stage group
`IIIB` is correct either way, which is precisely the trap — a wrong element hides inside a
right summary. This is why a staging skill is `critical`, and why the human check is an
element-by-element check rather than a read of the group letter.

**This case is currently untested.** `GOLDEN_DATASET.yaml`'s 100 studies are imaging
reports only; there is no pathology or staging case in it, so the `pN1a`/`pN1b`
substitution has no evaluation behind it. Adding a staging block to the golden set is
listed as work in `ROADMAP.md`, and the broader gap — 121 designed skills against 100
golden cases for one modality family — is contradiction #11 in the sprint report.

### B6. `guideline-citation` — blocked, and the refusal is the output shape

Why here: it is the only skill in the catalogue whose correct answer is "I cannot do
this", and it demonstrates the difference between a model that sounds authoritative and
a platform that is allowed to be.

```json
POST /chat
{
  "skill": "guideline-citation",
  "messages": [
    { "role": "system", "content": "You may cite only sources present in the context supplied to you. If no source text is supplied, say so and stop. Never output a citation from memory." },
    { "role": "user", "content": "What is the recommended follow-up interval for a 7 mm solid incidental pulmonary nodule in a low-risk patient?" }
  ]
}
```

Today: the catalogue declares it `status: blocked` with
`blocked_by: ADR-0006 and SPEC-08-06 — no retrieval or citation capability exists;
services/knowledge and Qdrant are present in compose but nothing reads them`. There is no
retrieval path in the Gateway and no `embedding` capability, so nothing can be placed in
the context that would make a citation honest. The response below is therefore what the
skill must return *even if* it were authorised today — a refusal with a labelled fallback,
not an interval from memory.

The correct response, which is the whole design requirement:

```json
200
{
  "skill": "guideline-citation",
  "capability": "default",
  "degraded": false,
  "content": "{\"citation_available\":false,\"reason\":\"No guideline text was supplied to this request and the platform has no retrieval path. A follow-up interval from model memory is not a citation.\",\"what_can_be_answered\":\"The Fleischner-style framework for a 7 mm solid nodule in a low-risk patient is commonly a follow-up CT at around 6-12 months, then consideration of a later interval scan — but this is recalled general knowledge, not a verified reference, and must not be entered into a patient's record as a guideline.\",\"what_a_clinician_should_do\":\"Check the local or national guideline the department follows and record the interval from that document.\",\"do_not_use_for\":\"any note, medicolegal summary, or protocol where the source is expected to be named\"}"
}
```

The `what_can_be_answered` paragraph is labelled in the response itself, so a downstream
screen cannot render it without the label. This is Constitution P13 (traceable or
labelled) applied at the output shape rather than in a policy document, and it is the
pattern every future retrieval-backed skill inherits: the answer must carry the status of
its own evidence.

---

## What these twelve say in aggregate

1. **The shape is the safety mechanism.** Nine of the twelve carry a field in which the
   answer declares its own gaps (`not_stated`, `missing`, `insufficient_data`,
   `cannot_compute`, `not_included`, `withheld`, `citation_available: false`) — counted,
   not asserted. The other two (A1, A2) do it inside the section prose with the words
   "not stated", which is weaker: a field can be validated by a screen, a phrase cannot.
   Any skill added to this file without one of the two needs a reason.
2. **Latency is a per-skill promise, not a platform one.** The examples above are written
   at 2.1 s (triage, `fast`) to 12.6 s (reconciliation, `reasoning`); the workflow's 8 s
   target for a report draft is a per-skill budget with a per-skill ceiling. **These
   numbers are designed targets, not measurements** — only `radiology-report` has ever run
   here, and only against a stub.
3. **Eleven of the twelve run on capabilities that exist** (`default`, `fast`,
   `reasoning`). The twelfth, `guideline-citation`, is blocked *because* a capability does
   not exist — retrieval. So the honest summary of this file is: two blockers are
   decisions (ADR-0005 approvals, ADR-0006 citation), one is a capability (embedding and
   retrieval), and one is a hospital-side identity change (individual authentication of
   the signer).
4. **Every one of the twelve is rejected today** with `404 unknown_skill`, because none of
   them is in the six authorised stanzas in `core/gateway/models.yaml`. The catalogue's
   size is not the risk; the clinical review capacity to authorise skills one at a time is.
