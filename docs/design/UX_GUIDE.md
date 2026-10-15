# FutureKind UX Guide

**Owns:** how applications are composed into screens and how they speak — the screen inventory
across the family, role and mode behaviour, cross-application handoff, the wording of every
state a clinician can see, and the template a new screen's specification must follow.
**Does not own:** the tokens, the keyboard and the eleven patterns (`DESIGN_SYSTEM.md`), the
radiology screens themselves (`../product/UI_UX.md`), which applications exist
(`../product/PRODUCT_BIBLE.md`), what is safe (`../safety/CLINICAL_SAFETY.md`).
**Status:** one application has running screens; the rest of the inventory is design.

---

## 1. Three documents, one line each

| Document | Answers | Stops at |
| --- | --- | --- |
| `DESIGN_SYSTEM.md` | What does it look like, what keys work, what pattern is this | Any specific screen |
| **this document** | Which screens exist, in what order, doing what to whom, in what words | Any visual token or keystroke |
| `../product/UI_UX.md` | The radiology workspace, screen by screen | Anything another department owns |

A new department's screens are written in `UI_UX.md`'s shape (§8 here) in its own document, and
references this one for anything that is not specialty-specific. Nothing in this family gets a
fourth kind of UX document per department.

---

## 2. Screen inventory

Five of these exist in code today — the radiology workspace page with its study column, its draft
pane, its interim approval screen, its print-and-export handoff, and the QA session reading in
`scripts/validation/dashboard.py`. Everything else in the inventory is design.
"Frame" means it lives inside the host's workspace; "page" means the application owns the whole
window until it does not.

| Application | Screen | What it owns | Frame/page | Patterns (`DESIGN_SYSTEM.md` §6) | State |
| --- | --- | --- | --- | --- | --- |
| Radiology | Study queue | What is waiting, and in what order | page → ERP frame | — | **Built** (`UI_UX.md` §2) |
| Radiology | Reporting workspace | The three regions, the document, the sign | page | 1, 2, 3, 4, 5, 6, 7, 8, 9, 10 | **Built** (`UI_UX.md` §1, §4) |
| Radiology | Draft pane | Per-section proposal, diff, accept | pane | 1, 2 | **Built** as the copilot's own pane |
| Radiology | Comparison viewer | Two studies, one claim about change | pane | 3, 4 | Design (`UI_UX.md` §5) |
| Radiology | Approval screen | The named act, and what it attests | pane | 7, 9 | **Interim version running inside the copilot** (`../product/README.md:19`) |
| Radiology | Audit timeline | Who wrote, edited, accepted which sentence | page | 9 | Design (`UI_UX.md` §7) |
| Radiology | Department view and search | Throughput, backlog, a found report | page | — | Design (`UI_UX.md` §8) |
| Radiology | Settings | Name, modes, keys, defaults | page | — | Design (`UI_UX.md` §9) |
| Pathology | Specimen worklist / Case composer / Sign-out | The queue, the five-part document, the act | frames | 1–10 | Design (`../product/CLINICAL_SUITE.md` §3) |
| Physician | Round list / Note composer / Problem list / Summary builder | One ward, one patient, one document each | frames | 1, 2, 3, 7 | Design (`CLINICAL_SUITE.md` §4) |
| Emergency | Triage board / Pathway record / Instruction handout | The clock, the pathway, the words a patient leaves with | frames | 1, 5, 6, 11 | Design (`CLINICAL_SUITE.md` §6) |
| Critical Care | Bulletin / Record / Family briefing | The interval, the procedure record, the letter | frames | 1, 3, 5 | Design |
| Theatre | Pre-op / Note / Post-op | Assessment, dictation-into-structure, instructions | frames | 1, 2, 3 | Design (`CLINICAL_SUITE.md` §5) |
| Discharge | Summary builder / Referral letter | The composite document, the addressed letter | frames | 1, 3, 9 | Design |
| Coding | Suggestion review | Code proposals beside the signed text they came from | frame | 3, 7 | Design (`CLINICAL_SUITE.md` §6) |
| Tumour Board | Board sheet | One plan several clinicians are bound by | page | 7, 9 | Design, **cannot ship pre-ADR-0005** |
| Patient-Facing | Leaflet preview and approval | The exact words a patient will read | pane | 7, 11 | Design (`CLINICAL_SUITE.md` §7) |
| Timeline (with audit view) | One patient, ordered | Completeness, sources, staleness | frame | 9 | Design, **blocked on ADR-0007** |
| Command Center | Indicator board | Definitions before numbers | page | none — it drafts nothing | Design |
| Clinical QA | Session reading / Trend | What the reviewer did, over time | page | 4, 9 | **Prototype exists** (`scripts/validation/dashboard.py`) |

Rule of the inventory: **a screen that drafts something is a copilot screen**, whatever its name,
and inherits the eleven patterns. Consoles and surfaces implement none of them on purpose.

---

## 3. Roles, modes, and what a role is not

| Reader | What they need first | Mode that serves it | Non-negotiable |
| --- | --- | --- | --- |
| Reporting clinician (radiologist, pathologist) | The document and the source, in that order | Reading-room dark, wide | The source region never collapses to make room for the draft |
| Resident / trainee | The same, plus *why* a check fired | Same | A trainee's screen is not a simplified one. Explanatory text is available, never hidden by rank |
| Technologist / radiographer | Acquisition completeness, protocol named | Bright tablet, 44 px targets | They never see a patient's clinical question beyond what the study needs (`../product/UI_UX.md` §12) |
| Ward doctor | What changed overnight | Compact list | The plan is theirs; nothing pre-fills it |
| Surgeon | The note they dictated, structured | Dictation-first | An implant list with no source line is a defect |
| Medical typist / scribe operator | Speed and keys | Keyboard-only | Their name may never be the signer (`../integration/INTEGRATION_CARE_ERP_PACS.md:252`) |
| Coder | The signed document and the proposed code side by side | Two-pane | Never the claim itself (`../product/PRODUCT_BIBLE.md` §6.4) |
| Quality lead / administrator | Counts with definitions | Console | A metric whose events are not named is not printed (`CLINICAL_SUITE.md` §8) |

**A role in this family is a view, not a permission.** Permissions belong to the ERP
(`requireStaffPermission` already exists there, `../integration/AI_ENTRY_POINTS_CARE_ERP.md:74`);
a FutureKind application that grows its own access model is a second authority and will diverge
from the first. Modes (`DESIGN_SYSTEM.md` §3) are presentation and are the clinician's choice,
stored per user in the host, never in browser storage.

---

## 4. Handoff between applications

One patient crosses several applications in a day. Three rules keep the family from becoming
seven places where a record disagrees with itself:

1. **One writer per document, and the lock is the ERP's.** The ultrasound draft store already
   does read-modify-write under a row lock because a lost-update bug taught it
   (`../integration/INTEGRATION_CARE_ERP_PACS.md:19-25`). No copilot may open another department's
   document for editing — it may *read* it, and it must say which version it read.
2. **A handoff is a version, not a copy.** The ERP carries `sequenceNumber`/`totalVersions` and an
   `X-Report-Version` header (`:254`, `:310`); an application that writes a fresh document instead
   of a new version creates the duplicate-delivery incident `RADIOLOGY_WORKFLOW.md` calls F14.
3. **Cross-application context is read-only text with a source line.** When a discharge summary
   quotes an operative note, the quote carries which note and which version — the same discipline
   that makes a radiology draft traceable to its dictation, applied to a second department.

---

## 5. How every failure is worded

The built screen is the evidence: one envelope, one guidance entry per code, and a manual path
that stays live. The rules below are the family's, and they came out of driving the running
product through six failure modes rather than out of preference (`../product/ROADMAP.md` §4b).

**Structure of a failure sentence — three parts, in this order:**

1. **What happened**, in the words a clinician would use: *"Model did not finish the impression."*
2. **What it means for the document**: *"This draft was refused."*
3. **What to do next**, with the manual path first: *"Type it instead, or re-draft."*

That shape is the one already specified for the draft pane (`../product/UI_UX.md` §4, *Failure
presentation*), and it applies to every screen, console and surface in the family.

| Rule | Why it exists |
| --- | --- |
| **Never show a raw upstream body, an exception string, or a parse error.** Name the status, say nothing was filed, say what to try | A traceback is where submitted text can appear; and *"Unexpected token 'I'…"* is a browser's problem, not a clinician's |
| **A 422 must name the fields** it refused, because the message already promises it does | Found last night: the envelope carried `details.problems` and the screen had thrown them away |
| **A refusal must name the check**, in the same words the check list uses | A refusal that cannot be traced to a rule reads as the machine deciding for the human |
| **Nothing may be refused silently.** If an action did not happen, the screen says so where the action was started | A status line three regions away is not a failure message |
| **A retry is offered only when retrying is possible.** A page-load-only control is described as such | The network message once promised a Retry button that existed only at load |
| **A surface with a partial read says "incomplete", and names what is missing** | For Timeline and consoles this is the primary safety rule: silent absence is the harm |
| **One honest line when the model is down**, and the screen looks otherwise identical | `DESIGN_SYSTEM.md` §2, constraint five |
| **Clipboard success is claimed only on success** | It printed "copied" after a refused write, found by running it |

Wording register: the machine is never the subject of a clinical act. *"The draft proposes"*,
*"this section is the referrer's words"*, *"the check could not find this number in what you
dictated"* — and never *"the AI thinks"*, never a first person that could be read as the
clinician's own voice on a printed page.

---

## 6. States every screen must render

| State | Copilot screen | Surface or console |
| --- | --- | --- |
| Empty | Nothing is pre-filled with clinical text — a worked example on a live form is a defect (`ROADMAP.md` §4b) | Empty means *no events*, and says over what period |
| In flight | Elapsed seconds counting; nothing else disabled; Cancel keeps the words | A stale read counts as in flight: show its age |
| Refused | The reason, the check, the manual path | A cohort too small to report a rate prints nothing (`ROADMAP.md` §4b's rate guard) |
| Partial | A draft with a missing section is not offered | Completeness is a visible number, not a footnote |
| Degraded | Never silent substitution; the line says a fallback answered | Same rule: a lesser model may not answer quietly |
| End of session | What was produced, what was refused, what is still open | The reading a person is asked for in a meeting — `scripts/validation/dashboard.py` already prints five of these |

---

## 7. Interruption and recovery

The application is stateless and the browser holds the only copy of an unsent draft
(`../ARCHITECTURE.md:268-271`), so the family's recovery behaviour is a set of decisions rather
than a mechanism:

| Event | What happens | Why it is the answer |
| --- | --- | --- |
| Refresh or close mid-draft | The page refuses to leave with unsaved words; if it is left anyway, the draft is gone | Persisting clinical text on a shared cart would mean browser storage, which `../security/THREAT_MODEL.md` §3 forbids by test |
| Gateway dies mid-session | The failure names the code, keeps the typed text, keeps the manual path | F24/F6 |
| Slow model | The clock counts to the ceiling and the Cancel is live the whole time | A slow model that shows nothing is indistinguishable from a dead one |
| Clipboard refused | The truth is said, and the download path is offered | `DESIGN_SYSTEM.md` §6.8 |
| Study abandoned | Recorded as abandoned, not as a signed document with empty edits | The validation instrument counts abandonment separately on purpose |
| End of day | Session reading; nothing is auto-filed | A copilot does not decide when a day ends |

---

## 8. The template a new screen specification must fill

Every screen in the family is specified in the table shape `../product/UI_UX.md` uses, with these
eleven rows and no others. The list is a rule because a screen described in prose cannot be
reviewed, and an over-specified screen is a screen nobody builds.

Purpose · User · Layout · Input shown (including what is read-only, greyed and *whose words* it
is) · Actions · States · Failure presentation · Latency target and what is shown while waiting ·
Audit attached · Accessibility notes (roles, contrast, target size, keys) · **Must not have** —
the last row is mandatory, because a screen's danger is usually the thing that would be
convenient.

---

## 9. Conformance questions

1. Does every screen of the application have a row in §2, and does its *Must not have* say
   something a reviewer would object to?
2. Does each failure path reach the three-part sentence shape, or is there a place where a code is
   rendered as prose?
3. What does the screen show when the model is unavailable, and is that one line and one line only?
4. Which documents does it write into, at which version, and under whose lock?
5. For surfaces: how does the user learn the read is incomplete?
6. For consoles: is every printed number traceable to a counted event and a definition?
7. Whose name signs here, and can a typist, a resident or the machine be the one on the document?

*FutureKind · Genesis Night 3 · 2026-10-09. The wording rules in §5 are each the record of a
defect found in the running screen; the inventory in §2 is the only part of this document that
describes unbuilt work, which is why it carries a state column.*
