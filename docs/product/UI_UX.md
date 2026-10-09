# FutureKind Clinician Workspace — UI/UX specification

**Deliverable 6 of Genesis Night.** Eleven screens plus two modes, specified for the two
places this will actually be used: a radiology reading room at Hope Neurotrauma, and an
ultrasound room at CARE Diagnostics with a tablet on a cart and a corridor outside.

**Ownership, since the document set grew around it.** This file owns **the radiology screens**.
The shared language every department's screens must obey is
[`../design/DESIGN_SYSTEM.md`](../design/DESIGN_SYSTEM.md) — tokens, the keyboard, the eleven
patterns — and the cross-application screen inventory and state wording is
[`../design/UX_GUIDE.md`](../design/UX_GUIDE.md). Where this file states a rule that is really a
family rule, the design system is its authority; where the design system states a pattern, this
file is where radiology's version of it is specified. Neither file restates the other.

## 0. Six constraints that decide every layout below

These come from the site, not from taste.

1. **It is hosted inside what already exists.** The USG studio is Next.js + Tailwind +
   shadcn/ui + Radix, already has a PACS queue component (`UsgPacsQueue.tsx`), a lock screen
   (`LockScreen.tsx`) and dark-mode-aware settings (`SettingsView.tsx`). M3 adds panes to
   those, not a fourth web app. A separate "FutureKind portal" would create a second place
   where a report is incomplete.
2. **The screen is visible to other people.** An ultrasound room has a curtain, a attendant
   and sometimes a second patient. Queue rows, headers and toast messages are PHI surfaces
   and are specified as such in §12.
3. **Sunlight and a lap.** The tablet is used on a radiographer's lap, in a lit room, often
   one-handed. Contrast, target size and thumb reach are functional requirements.
4. **The clinician is in a hurry and reads nothing.** Every safety affordance must work when
   the user is skimming. Any design that relies on the user reading a paragraph will be
   bypassed — which is why §6 puts the attestation in the button label rather than in a
   modal.
5. **It must work when the AI is down.** F6 in the workflow catalogue. No screen may become
   unusable because a model did not answer, and no screen may look different when the AI is
   unavailable except for one honest line.
6. **Nothing here is a chatbot.** §13. There is no free-text assistant in a clinical
   workspace. Open WebUI remains the general surface for non-clinical work; a chat box next
   to a patient's report would defeat every governance property this platform has.

Type, colour and density follow the host's existing Tailwind/shadcn tokens. Dark mode is a
real theme (§10), not an inverted filter.

---

## 1. Radiology Workspace — the frame

| | |
| --- | --- |
| Purpose | The single screen a reporting clinician lives in: queue left, study and report centre, AI pane right |
| User | Radiologist, sonographer-clinician |
| Layout | Three columns, 22% / 48% / 30% on a desktop; collapses to tabbed panes on a tablet (§11). Persistent header: clinician name, session, department, AI status chip |
| Data | Worklist, current study, current report document, provenance |
| Actions | Select study → open report; start draft; open viewer; sign; export; withdraw/amend |
| States | No study selected · draft in flight · draft refused (with reason) · draft unsigned · signed · delivered · filed to PACS · undelivered |
| Latency | First paint < 1 s from worklist data alone; no screen may wait on the model |
| Audit | Session open/close, study opened, pane actions |
| Must not have | A model selector. A provider name in the header. A temperature slider. Anything that lets the user choose "a better model" |

The AI status chip is the only always-visible AI element: `local qwen3 · ready` /
`unavailable` / `degraded — not permitted for this skill`. It reports the *deployment*, not
a knob, and it is the one place a clinician is allowed to see which model is answering
(P8 transparency: reported, never selectable).

## 2. Study Queue

| | |
| --- | --- |
| Purpose | Decide what to report next, and see what is owed |
| User | Radiologist (own list); department lead (everyone's) |
| Layout | Ordered rows: accession, modality, study, patient initial + age/sex, priority badge, triage reason, waiting time, referrer location. Sticky summary strip: `12 undelivered · 1 critical unacknowledged · 3 re-drafted` |
| Data | ERP worklist (`internal-reporting-studio.ts:263`, `radiology.ts:335`) + FutureKind `/triage` ordering |
| Actions | Sort/filter by modality, referrer, priority, waiting; open; bulk *open* (never bulk sign) |
| States | AI ordering on · **AI ordering off (fallback to acquisition order, shown in the header, never silent)** · triage failed · empty |
| Failure presentation | Triage failure ⇒ header reads *"ordering without AI"*, rows keep acquisition order. A failed AI path must never stop a radiologist reporting |
| Latency | Renders < 1 s; triage for 50 studies < 2 s |
| Audit | Which studies were opened and when (the raw material for the rewrite-rate metric) |
| PHI | See §12 — initials and age, never full name, never on the corridor view |

**Priority is carried three ways:** colour, an icon shape, and the words in the badge. A
sunlit screen and a colour-blind reader are both real at this site. Priority 1 is inpatient
deterioration, not the loudest referral text (workflow B1).

## 3. Patient View

| | |
| --- | --- |
| Purpose | Everything this patient has, in one place: identity, orders, studies, reports, priors |
| User | Reporting clinician; referring clinician; trained staff on request |
| Layout | Identity header (UHID `P-000NN`, name, age/sex, ward or OPD, allergies banner), then tabs: Studies · Reports · Problems · Medicines · Timeline |
| Data | ERP `patients`, `radiology_studies`, `patient-reports`, `GET /api/patient-reports/patient/:patientId` (`patient-reports.ts:1396`) |
| Actions | Open study in viewer; compare two reports; request a plain-language explanation (a **different skill**, `patient-explainer`); copy a citation-safe reference into the current report |
| States | Reports at four states visible distinctly: `draft` · `pending_verification` · `verified` · `delivered` — plus superseded revisions greyed with the current one explicit |
| Failure presentation | A prior that will not load is named as missing. Never a silent gap where a comparison should be |
| Latency | Identity < 500 ms; report list < 1 s |
| Audit | Every patient record opened is logged (who, which UHID, when) — this is the access trail a privacy review asks for, and it is the reason the view exists as a screen rather than as a query |
| Must not have | An AI field that answers "summarise this patient" without a named skill. Cross-hospital lookup (P14) |

## 4. AI Draft pane

| | |
| --- | --- |
| Purpose | Propose report text into fields, without ever owning them |
| User | Reporting clinician |
| Layout | Right column, five blocks matching the five model-authored sections (technique, findings, impression, recommendations, follow-up). Each block has: proposed text, *accept into field* / *discard*, and a per-block diff against what the field already held. Below: `redraft with a note` (the only steer a human may give) |
| Input shown | Modality, study, the recorded clinical indication (read-only, greyed, labelled *"referrer's words"*), technique if supplied, dictated observations verbatim |
| Actions | Draft · redraft with note · accept per section · discard all · dictate manually |
| States | Idle · in flight (elapsed seconds counting; nothing disabled) · refused-with-reason · partial (never: a draft with a missing section is not offered) · truncated · degraded |
| Failure presentation | Each reason in plain words, and always the manual path stays live: *"Model did not finish the impression — this draft was refused. Type it instead, or re-draft."* |
| Latency | 8 s first draft target, 20 s p95, 90 s ceiling. **The elapsed number is shown**, so a slow model is visible rather than mysterious |
| Audit | `request_id`, prompt version, model, attempts, degraded — attached to the draft, not to a log the user cannot see |
| Must not have | A single "Accept all and sign". A whole-pane replacement of the composer. Streaming text into the signed field before the clinician accepts it |

**Who owns each section's words, and what that means on screen.** Decided per section rather
than by a blanket rule, because the dangerous setting is a locked box holding a sentence the
machine wrote. `report.py::editable_section_keys` is the one authority and the screen renders
from it, so the rule cannot drift from the rendering; each locked box states whose words it
holds and where to change them.

| Section | Written by | Locked on screen | Why, and what would change it |
| --- | --- | --- | --- |
| Clinical indication | The referrer, copied from the submission | **Always** | It is the question the study answers. A model that paraphrases it has changed the clinical question — the Sprint 7 live defect. To change it, edit the box in the Study column and redraft |
| Technique | The department when it supplies parameters; the model only to say they were not given | **Only when the department wrote it** | The department's own line must not be retyped into something untrue. When nobody supplied a protocol the sentence is the model's guess, and the radiologist at the console is the only person who knows whether the study had one — so it is editable, and the note says so |
| Findings | The model, from the dictation | Never | The comparison against the dictation is the whole review. `dropped_observation` and `unsupported_measurement` are the machine's half; the images are the reviewer's |
| Impression | The model | Never | The highest-value section and the highest-risk one. `unsupported_certainty` refuses a hedge that became a certainty, and a rewrite here is the case where a blocking finding falls to advisory — because the image, not the dictation, becomes the source |
| Recommendations | The model | Never | Advice about what to do now is a clinical act, not a formatting one. Fully editable, fully checked |
| Follow-up | The model | Never | Kept apart from recommendations because an interval buried in a paragraph of referrals is an interval nobody books. Whether this section should be AI-generated at all is the sharpest question the afternoon can answer: it is the one section whose entire content is a decision rather than an observation |

Nothing auto-updates after a signature: the document is amended and re-exported,
`metadata.review.amendments` names what a human took over, and `model_provenance` keeps saying the
draft was machine-authored. A silent auto-update of a signed report would be a different report.

Rows of the table above the Alpha now meets on its own screen: elapsed seconds counting with a
Cancel (*States*, *Latency*), failure presentation in plain words with the manual path left live
(*Failure presentation*), and audit attached to the draft rather than to a log (*Audit*).
Per-block accept/discard and the per-block diff remain the ERP pane's work.

Per-item mode (ultrasound, mammography, cardiac — workflow D2): the pane proposes **chips**
keyed to organs, exactly as `UsgAiDraftPanel.tsx:122-141` already does. A chip is accepted or
rejected individually; the report body is never written by the AI. This is the pattern that
made D2 the default, and it is the only place in the product where "the AI never writes the
report" is literally visible.

## 5. Comparison Viewer

| | |
| --- | --- |
| Purpose | Check the draft against the pixels, and against the prior |
| User | Reporting radiologist |
| Layout | 60:40 images:report, side-by-side prior on a second monitor or a split on tablet. Report pane is the live document, not a copy |
| Data | OHIF via `{OHIF_BASE_URL}/viewer?StudyInstanceUIDs={uid}` (`networkDefaults.ts:93-94`; the base is the installation's own value, not a name this document carries); images over `/dicom-web` → Orthanc `:8042`; prior report text from the ERP |
| Actions | Launch viewer; load prior; request an AI comparison (`prior-study-comparison`) **between the current dictation and the prior report text**; request a differential check |
| States | Viewer loaded · viewer unreachable (with the URL it tried) · prior not found · prior found but different study/protocol |
| AI action limits | `prior-study-comparison` never reads prior pixels. Its answer is text-to-text and says so on its face |
| Latency | Viewer first paint < 3 s LAN; prior text < 1 s |
| Audit | Viewer launch, prior loaded, comparison requested |
| The step this screen exists to protect | The radiologist looking at the images. Everything in the layout must support that and nothing may compete with it |

## 6. Approval Screen

| | |
| --- | --- |
| Purpose | The one screen where a machine output becomes a clinical document |
| User | One individually authenticated clinician |
| Layout | Six sections' final text; **diff against the model's original per section**; the nine quality findings and the computed confidence, each naming its section; provenance summary (model, alias, prompt version, attempts, degraded); the AI-involvement line rendered on the preview; name and registration pre-filled from the session; one button |
| Actions | Sign · sign with comment · return for edit · re-draft |
| Button label | *"I, Dr <name>, accept these sections as my clinical opinion"* — the attestation is in the control, not in a modal someone clicks through |
| Hard rules | No keyboard shortcut reaches sign without focus in the pane. No bulk sign. No signing action that also drafts. If any section is unaccepted, the button reads *what is missing*, not *Sign*. Numbers in a report (sizes, counts, scores) are typed, never accepted (§4 of the workflow) — and since Sprint 9 the server enforces the same rule independently: an unsupported measurement is `blocking`, and `POST /review` refuses it whether or not the screen remembered to disable anything |
| States | Ready · blocked (missing sections / no individual identity in session) · signed · signed-and-amended · withdrawn |
| Failure presentation | If the ERP will not accept the signature (role is `typist|ai|system|bot`, `radiologyD1FinalWriter.ts:76`), the screen names the reason. It must not look like a successful sign that failed downstream |
| Latency | < 2 s. Sign-off that feels expensive gets batched |
| Audit | Copilot `metadata.review` (who, when, which sections rewritten) **and** the ERP's own signature columns. Both, keyed by the same `report_id` |
| Identity requirement | **Blocking for Beta.** Today the USG studio's signer name is a clinic-level *setting* and one shared PIN authenticates the room (`auth.ts:10-27`, `schema.prisma:91-93`). A signature must come from a login, not a configuration row |

**Built, in interim form (Sprint 9, worked over in Genesis Night 2).** The Alpha copilot
serves its own working screen at `GET /` —
`apps/radiology_copilot/src/futurekind_radiology/static/index.html`. Three columns: the
submission and its previous reports, the six report sections with the signer's name, and the
quality findings with the computed confidence and the provenance. It debounces into
`POST /check` while the clinician types, and a blocking finding disables the sign button and
refuses it server-side as well.

What the interaction work added, each item because it cost the person at the console
attention they should be spending on the images: `Ctrl/⌘+Enter` drafts, then signs; `Alt+R`
re-checks without waiting for the debounce; `Ctrl/⌘+Shift+C` copies the signed report for the
RIS; `Ctrl+P` prints it; `Alt+N` starts the next study; `Alt+D` and `Alt+M` give the reading
room its dark and wide modes. Tab order skips what cannot be typed in. Textareas grow to
their content, because 700 characters of findings in a 92-pixel box is a scroll bar fought
once per study. A quality finding that names a section is a button, and clicking it focuses
that section and selects the quoted words instead of leaving the reviewer to hunt for them.
Boxes are locked by **who owns the words** (`report.py::editable_section_keys`) and every
locked box says so and says where to change it — the technique line is locked when the
department supplied it and editable when the model wrote it, which is the case that used to
be locked both ways. The inputs start empty, with placeholders instead of a worked example:
prefilled indication and dictation is a form on which a real study can be reported under
somebody else's words.

One divergence from §6 above, stated rather than slipped: signing does have a shortcut. The
rule's purpose is that a signature must never be an accidental keystroke or a bulk act, and
that holds — `Ctrl/⌘+Enter` signs only a draft that exists, is not blocked, and has a name
typed; with no name it moves focus to the name box and signs nothing. The literal "no
shortcut reaches sign" is a preference for the ERP pane and is listed as an open question for
the afternoon, not settled by this screen.

What it is **not**, and must not be mistaken for: the ERP-integrated Approval Screen; an
individually authenticated identity (the name is typed, which is exactly the F-A defect
above); the per-section diff against the model's original text; a saved-draft or
across-refresh recovery — the draft lives in that tab and nowhere else, so the page refuses
to leave with unsaved words instead of writing the last patient onto a shared workstation.
It exists so the workflow can be used and measured today, and it is deliberately throwaway
once the studio has the real pane.

## 7. Audit Timeline

| | |
| --- | --- |
| Purpose | One report's whole life, in order, attributable |
| User | Reporting clinician (own reports), department lead, information-governance officer |
| Layout | Vertical timeline: ordered · acquired · drafted (n attempts, each with reason if refused) · edited per section · signed · delivered · filed to PACS · viewed by · amended · superseded · critical notification raised/acknowledged |
| Data | Copilot document + Gateway `request_id` lines + ERP outbox attempts and status transitions |
| Actions | Open any row's detail; export the timeline as text for a medicolegal request; jump to the version's PACS series label |
| States | Complete · **partial where retention is partial** — the platform emits audit today but does not yet retain it (`Q3` in `DOMAIN_MODEL.md`, register row 4), and the screen must say which segments are reconstructed rather than recorded |
| Must show | Which model answered, which alias was asked for, degraded flag, prompt version. Which a reviewer can check against `configs/litellm/config.yaml` |
| Must not show | Prompt or completion text (never logged, by design), API keys, the caller credential (an 8-hex digest only, `deps.py:67-73`) |
| Latency | Not latency-critical; correctness is |

## 8. Search, and the department view

| | |
| --- | --- |
| Purpose | Find work: by accession, UHID, referrer, phrase in a report, date band, modality, or "everything this model drafted that I signed" |
| User | Clinician, department lead, quality officer, coding desk |
| Layout | One search bar with typed filters; results table; and a **Metrics tab** that is a separate surface, not a dashboard widget |
| Data | Needs `GET /reports` with filters (**new endpoint**) + the ERP's `patient-reports` search |
| Search classes | Identifier search (accession, UHID) · full-text over report sections · provenance search (model/alias/prompt version/request id) · review search (unsigned > N hours, amendments containing the impression, undelivered, unacknowledged criticals) |
| The metrics view | Four numbers, deliberately chosen: drafts refused per 100; **impression rewrite rate**; substantive rewrite rate (diagnosis changed, not wording); median draft latency p50/p95. Deliberately absent: reports per hour, and any AI-vs-human accuracy scoreboard that is not the rewrite rate. The product must not reward the behaviour it is afraid of |
| States | Indexed · not-yet-stored (search across reports the platform never persisted is unavailable and says so) |
| PHI | Identifier search only for non-clinical roles; full-text search is a clinical role's capability, and every search is itself audited |

## 9. Settings

| | |
| --- | --- |
| Purpose | Deployment configuration, and the honest statement of what is not configured |
| User | Installation administrator (not the clinician) |
| Layout | Four groups: Connection (Gateway URL, credential present/absent — never the value) · Department (technique templates, signature block per clinician *once individual identity exists*, local reporting conventions) · Skills enabled in this installation (read-only mirror of `models.yaml`, with the alias each resolves to) · Diagnostics (self-test: Gateway reachable, alias contract satisfied, model answering, clock skew, ERP reachable, Orthanc reachable) |
| Hard rules | **No model selection, no provider selection, no temperature.** Those live in `models.yaml` and `configs/litellm/config.yaml` and are changed by a reviewed edit that the Gateway's startup check verifies (SPEC-07-03). A settings screen that let an operator pick a model would un-make ADR-0002 |
| States | Configured · degraded (self-test shows which leg failed, with the same fail-closed language the draft pane uses) |
| Audit | Every settings write, with actor and before/after — configuration is a clinical change here |
| Reuse | `SettingsView.tsx` in the USG studio already has an integrations-test pattern (`pingOllama`, `aiDraft.ts:107-116`); the FutureKind self-test is the same shape pointed at the Gateway |

## 10. Dark mode

| | |
| --- | --- |
| Purpose | A reading room is dim. Light emitted at a radiologist during a 200-study day is an ergonomics problem and, for image review, an accuracy problem |
| Requirements | A real theme with its own tokens (not `invert`); image panes stay neutral-grey so windowing is not judged against a black surround; text contrast ≥ 7:1 for report body (the existing shadcn tokens already carry `dark:` variants — `LockScreen.tsx`, `UsgPacsQueue.tsx`, `SettingsView.tsx`) |
| Semantic colour | Priority and risk colours must be re-verified in dark mode, not simply brightened. This is why §2 carries priority three ways |
| Status | Persists per user, follows the OS in tablet mode, and is never remembered per room (a shared cart must not fight the previous user) |
| Print/export | Always light. A printed signed report must not depend on a screen theme |

## 11. Tablet mode

| | |
| --- | --- |
| Purpose | Ultrasound reporting at the machine, on a cart, sometimes one-handed |
| Layout | Pane-based, one pane at a time, with the queue as a pull-down; targets ≥ 44 px; primary actions in the bottom third; the AI chip row is thumb-height because it is used hundreds of times per list |
| Input | On-screen typing of dictated observations is expected at this site, so section fields are large and per-organ chips beat prose. A physical keyboard attaches and must reflow the three-column desktop layout without losing state |
| Behaviour | Draft while typing continues. Draft failures never disable a field. Offline tolerance: drafting requires the Gateway, dictation does not (§6 of the integration doc) |
| Session | A cart is shared. Lock on blur after 60 s, and the lock screen must not display the patient, the accession or the draft preview (`LockScreen.tsx` already exists — its content is the review item) |
| Battery/network | Wi-Fi to a NAS-hosted app on a hospital LAN drops. A lost session must never lose typed dictation: local persist of the composer draft, re-attach on return |

## 12. Shared-screen and PHI discipline

Rules that bind every screen above.

- **Corridor-safe queue.** Default row content is initials, age band, modality, priority,
  waiting time. Full name and study detail appear only inside a selected study, on a device
  in the reporting room. There is a `display` mode for a wall screen that shows counts and
  priorities and no patient data at all.
- **No PHI in URLs.** Identifiers in a path or query end up in a browser history, a proxy log
  and a screenshot in a WhatsApp group. `report_id` and `request_id` are opaque. The export
  filename already excludes study text (`copilot.py::export`) — that discipline extends to
  every share link.
- **No PHI in toasts, badges or empty-state copy.** An error that names the patient becomes a
  leak the moment someone photographs the screen.
- **Validation errors carry structure, not values.** Already true in the copilot
  (`gateway.py::_problem_list` strips pydantic `input`/`ctx`); UIs must render that and not
  the raw error.
- **Screenshots are a support surface with the same rules.** Any "report a problem" control
  captures app state, not page pixels, so it cannot accidentally carry a name.
- **Audit of viewing** (§3) is what makes access misuse visible; it exists because a shared
  cart and a shared PIN make "who looked" otherwise unanswerable.

## 13. What is deliberately not in this product

1. **A chat box.** No free-text assistant beside a clinical report. The clinical surface
   calls named skills with typed inputs; general chat stays in Open WebUI, pointed at the
   Gateway's OpenAI-compatible interface with `platform-chat` (`clinical_risk: low`) — a
   different surface for a different kind of work, with its own audit.
2. **A model picker, a provider picker, a temperature field.** §9.
3. **A "trust this draft" toggle.** Approval is not a preference.
4. **A second composer.** There is one report body. The AI pane proposes into it; it does
   not maintain a parallel document someone must reconcile.
5. **An image-analysis overlay.** No boxes on pixels, no automated measurements (§3.2 of the
   product spec). If the vision decision (`ROADMAP.md` D4) goes the other way, this list is
   revisited as a decision with an ADR — not as a feature.
6. **A dark pattern that makes refusing easy and reading hard.** Every screen must make the
   *slower* safe action cheaper than the fast unsafe one. Where it cannot, the workflow
   (§4) puts the control in code, not in the design.

## 14. Build order for the screens

Only one screen has to exist for the product to be worth deploying, and it is not the
workspace.

| Order | Screen | Why this order |
| --- | --- | --- |
| 1 | **AI Draft pane, in chip form, inside the existing USG studio** | The studio already has the composer, the queue, the audit and the PACS return. One pane, routed through the Gateway, converts a live direct-to-model path into a governed one. Smallest change, real clinical value |
| 2 | Approval Screen | Without it, the product cannot honestly say a human signed it — and P11 is the requirement, not a nice-to-have. **Interim half shipped in Sprint 9:** the copilot's own screen does the review, the blocking gate and the attestation name; the ERP-integrated pane with a session-bound signer is what remains |
| 3 | Study Queue (with triage) | Triage is the second-most-visible AI value and the easiest to demonstrate to a department |
| 4 | Audit Timeline | Needed the first time someone asks "which model wrote this", which will be in week one |
| 5 | Comparison Viewer integration | Mostly host-side wiring of an existing OHIF launch |
| 6 | Patient View, Search, Settings | Valuable, and not what makes the deployment safe |
| 7 | Dark + tablet polish | Real requirements, but the app already ships with `dark:` variants and a tablet layout in the host |
