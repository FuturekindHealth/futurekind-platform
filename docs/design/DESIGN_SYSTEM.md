# FutureKind Design System

**Owns:** the shared interaction model and visual language every application above the platform
uses — tokens, the keyboard, navigation, and the eleven patterns that make a FutureKind
application feel like one product.
**Does not own:** the radiology screens (`../product/UI_UX.md`), per-application screen inventories
and flows (`UX_GUIDE.md`), the words (`../DOMAIN_MODEL.md`), what is safe (`../safety/CLINICAL_SAFETY.md`),
error *codes* (they belong to the API; their rendering is §6.5 here).
**Status:** the built radiology screen is the reference implementation; every token and shortcut
below was read out of it, and every rule it cannot yet satisfy is marked **gap** rather than
claimed.

---

## 1. Two rendering targets, one language

`../product/UI_UX.md` §0.1 says the workspace is hosted inside what already exists — the USG
studio is Next.js + Tailwind + shadcn/ui + Radix — while the copilot's own screen is a single
HTML file with **no external resources and no framework**
(`apps/radiology_copilot/src/futurekind_radiology/static/index.html`, asserted by
`apps/radiology_copilot/tests/test_screen.py`). Both are correct and they will not share a
component library. The language is therefore split deliberately:

| Portable across every application | Not portable, and must not be standardised |
| --- | --- |
| Token *names* and their meanings (§3) | A build system for tokens, or a shared CSS file |
| The keyboard map (§4) and the focus rules (§8) | A component package imported into the ERP |
| The eleven patterns (§6) as behaviour | Markup, class names, or a visual theme shipped as an artefact |
| Refusal and failure wording rules (§6.5) | The department's own vocabulary |

**Rule 1.** An application implements the language in its host's idiom. A FutureKind screen that
fights the host's frame creates a second place where a report is incomplete — which
`../product/UI_UX.md` §0.1 already rejects for a stronger reason than taste.

---

## 2. The six constraints, promoted from radiology to the family

Each is quoted from `../product/UI_UX.md` §0 with the family consequence added. Nothing here
repeals any of them.

| Constraint | Family consequence |
| --- | --- |
| Hosted inside what already exists | Every copilot is a *pane* in its department's workspace, or its own page only where no workspace exists yet (the radiology case, today) |
| The screen is visible to other people | PHI surfaces are a design-system category, not a radiology section: queue rows, headers, toasts, printouts, and the shared screen all obey `../product/UI_UX.md` §12 wherever they occur |
| Sunlight and a lap | Minimum target size and contrast are numeric requirements (§3, §8), and they bind the tablet as much as the reading room |
| The clinician is in a hurry and reads nothing | **Safety text lives in controls, not prose.** The sign-off button carries the attestation; a refusal names the check in its own first line; nothing depends on the user reading a paragraph |
| It must work when the AI is down | Every application has a manual path that is *always* live, and the only visible difference when the model is gone is one honest line |
| Nothing here is a chatbot | No free-text assistant beside a patient's record, in any department. `clinical-chat` stays out of clinical workspaces (§6.11) |

---

## 3. Tokens

The names are the contract. Values are the radiology screen's, read from
`static/index.html:39-66`; a host that already has a palette maps its own values onto the same
names rather than inventing new names.

| Token | Light | Dark | Means — and what it must never mean |
| --- | --- | --- | --- |
| `--ink` | `#16202b` | `#dde6ee` | Text with an owner. Never a status |
| `--muted` | `#56667a` | `#93a5b8` | Text that is context, not instruction. Never a disabled control |
| `--line` | `#d3dbe3` | `#2c3a48` | Structure |
| `--bg` / `--card` / `--field` | `#f4f6f8` / `#ffffff` / `#ffffff` | `#0f151b` / `#161e26` / `#10171e` | Page, panel, and the box a human types in. `--field` exists because a typed-in box and a read-only box must not be the same colour |
| `--hover` | `#eef2f6` | `#1e2933` | Reachable |
| `--block` | `#b4232c` | `#ef6a72` | **A check refuses this document.** Not "error", not "delete", not a red queue row |
| `--advisory` | `#8a5d00` | `#d9a441` | **A check noticed something.** Not a warning about the user |
| `--clear` | `#1d6b3f` | `#57b87e` | **A check passed.** Not "success" in general, and never on a button that has not been pressed |
| `--focus` | `#12507e` | `#6ab2e8` | Where the keyboard is |

**Rule 2 — the word always travels with the colour.** `--block`, `--advisory` and `--clear` are
three states a clinician must distinguish without trusting hue, so the severity word is rendered
next to the coloured rule (`static/index.html:868`). Colour-only status is a defect. **Gap:** the
built screen has five `aria-*`/`role` attributes in more than a thousand lines; the pattern is
right and the semantics are thin. §8 makes that a per-application conformance item, not a
claim.

**Rule 3 — dark mode is a theme, not an inversion** (`../product/UI_UX.md` §10). The reading-room
theme is chosen because a bright page next to a dark viewer is the thing that hurts; the built
screen reads `prefers-color-scheme`, keeps an explicit override (`index.html:1164`) and pairs it
with a wide mode (`Alt+M`).

---

## 4. The keyboard

Read from `static/index.html:1192-1222`. This map is family-wide: an application that needs a key
the host already owns wins by not binding it, and says so in its own screen inventory.

| Keys | Action | Family rule |
| --- | --- | --- |
| `Ctrl/⌘ + Enter` | Draft, then sign when a draft is on screen | The two most-used acts share one hand. Never bound to a destructive act |
| `Alt + R` | Re-check after an edit | Live re-check is the pattern that stops a refusal feeling arbitrary |
| `Ctrl/⌘ + Shift + C` | Copy the signed report for the RIS | Copy is opt-in and named; nothing is on the clipboard by accident (§6.8) |
| `Alt + N` | Next study | The queue advance is a keystroke, not a scroll |
| `Alt + D` / `Alt + M` | Reading-room dark / wide mode | Modes are one keystroke because the room changes at the console, not at a settings page |
| `Esc` | Dismiss a failure | And only that. `Esc` never cancels a draft, never closes a document |
| `Tab` | Order that skips what cannot be typed in | Locked boxes are skipped; a locked box still names whose words it holds |
| `Ctrl/⌘ + P` | Print | The print rendering opens the audit block the screen hides (§6.9) |

**Rule 4.** A shortcut is documentation-free: the label of the button it triggers says what it
does. Adding a keystroke that duplicates a label is how the map becomes folklore.

---

## 5. Navigation and the frame

Three regions, in this order, on every copilot: **the source on the left** (what the human said or
what the record holds), **the document in the middle** (what will be signed), **the assistant on
the right** (what the machine proposes, per section). The order is the argument: the source is
where correctness is checked, so it stays adjacent to the document, and the assistant is the
furthest thing from the signature.

- No copilot replaces its host's frame, queue or navigation.
- A queue is a PHI surface (§2) and its rows are specified per field, not per screen.
- One screen, one document. Multi-study review (`../product/CLINICAL_SUITE.md` §2) is the same frame with
  the source region holding two studies, not a new layout.
- Every surface has an empty state that names why it is empty. "No prior study available" is a
  product statement; a blank panel is an accusation.

---

## 6. The eleven patterns

Each is a rule, its evidence, and its consequence for the next application.

**6.1 Draft into a field, never over it.** A proposal is accepted per section by an explicit act,
and the diff against what the field held is shown. `../product/UI_UX.md` §4. Consequence: a
copilot that offers one "accept all and sign" has removed the act it exists to record.

**6.2 A locked box says whose words it holds.** Locked fields carry a note naming the owner and
where to change them (`static/index.html:779-780`); locking follows text ownership, decided in
one place the screen reads rather than in the screen
(`apps/radiology_copilot/src/futurekind_radiology/report.py::editable_section_keys`).
Consequence: no department may lock a section because it felt machine-authored — the dangerous
setting is a locked box holding a sentence the machine wrote.

**6.3 A check that names the text is a control, not a caption.** Each check row focuses the
section and selects the quoted words (`static/index.html:818-830`). Consequence: a check with no
anchor is noise; when porting checks to a new department, if a rule cannot name the words it
objects to, it should be advisory or it should not ship.

**6.4 Confidence is computed and shown as a band.** `supported` / `review-carefully` /
`not-safe-to-sign`, derived from the checks, never taken from the model
(`../product/UI_UX.md` §0.4's "reads nothing" applies here: a band is legible in a skim). A model
that reports its own confidence is *refused* by `self_reported_confidence`
(`apps/radiology_copilot/src/futurekind_radiology/quality.py:226-236`).

**6.5 Failure in plain words, with the manual path live.** One error envelope, one guidance entry
per code, the request id, and the sentence that says what to do next. `../design/UX_GUIDE.md` §5
owns the wording; the rule here is structural: **a failure that names no next action is a bug**,
and a failure that shows a raw upstream body is a leak.

**6.6 Latency is shown, not smoothed.** Elapsed seconds counting while a draft is in flight, with
a Cancel that keeps the dictation (`../product/UI_UX.md` §4, *Latency*). Consequence: no spinner
without a number, anywhere in the family.

**6.7 Sign-off is a verb inside a control.** The attestation lives in the button label, not in a
modal the skimming clinician dismisses (`../product/UI_UX.md` §0.4, §6). Consequence: no
confirmation dialog as a safety mechanism — a dialog that is always accepted is not a gate.

**6.8 Handoff, and what leaves the screen.** Print, clipboard, and the write into the system of
record — `patient_reports` in the ERP and the encapsulated PDF into PACS
(`../integration/INTEGRATION_CARE_ERP_PACS.md:127`).
Clipboard success is claimed only when the write succeeded (`index.html`'s `copyToClipboard`
returns a boolean); the export carries the provenance block. **Two gaps, both named elsewhere and
therefore not fixed by this document:** a signed report can print without a watermark
(`../security/THREAT_MODEL.md` §3), and anything copied travels outside every control the platform
has.

**6.9 Audit visible where it is used.** On screen, provenance collapses to the one line that gets
read; in print and in export, the audit block opens. A record nobody can see is not an audit trail
(`../product/UI_UX.md` §7).

**6.10 Nothing clinical is written to browser storage.** No `localStorage`, `sessionStorage`,
`indexedDB`, cookies, caches or service workers — asserted by a test rather than by a comment
(`apps/radiology_copilot/tests/test_screen.py`; `../security/THREAT_MODEL.md` §3). The cost is
stated to the user: a refresh loses the draft, so the page refuses to leave with unsaved words.
Consequence: **draft recovery across a refresh is a feature this family refuses by policy**, and
any application that wants it must first change that policy in the open, not by shipping a cache.

**6.11 No chat box in a clinical workspace.** §2's constraint, stated as a rule for the thirteen
applications that have not been built yet, because the temptation arrives with `clinical-chat`,
which is already authorised and unused (`core/gateway/models.yaml:80`).

---

## 7. Review and approval are one pattern everywhere

The review flow is: source visible → proposal per section → checks re-run on every edit →
blocking findings refuse the signature → the human's own words replace the machine's → the record
names which sections a human took over. The approval flow is that plus one thing the platform
cannot yet do: **verify** that the named human approved it. Until ADR-0005, an application
attests and the ERP's own refusal of a machine signer is the enforcement
(`../integration/INTEGRATION_CARE_ERP_PACS.md:252`), and the product says so rather than implying
otherwise (`../safety/CLINICAL_SAFETY.md` §5).

No department gets a different review flow. Where a department's document differs, it changes
sections, profiles and checks — not the pattern. This is the single most important constraint in
this document, because the cheap alternative (a per-specialty approval UX) is exactly how a
hospital ends up with four kinds of signature and one audit story nobody can reconstruct.

---

## 8. Accessibility, interruption and density

| Requirement | The rule | How it is checked |
| --- | --- | --- |
| Contrast | Body text and every status colour meet it in both themes; `--advisory` and `--block` were chosen against `--card`, not against each other | A measured claim, per theme, in the application's own test file |
| Target size | 44 px minimum in tablet mode; the reading room may go smaller because a mouse is present | Layout assertion |
| Focus | Visible, never removed, and the tab order skips what cannot be typed in | `test_screen.py`-style assertion on the built screen |
| Screen readers | Roles and labels on every control that changes the document; severity carried by text as well as colour | **Gap** — five `aria-*`/`role` attributes in the built screen. Each new application adds the semantics rather than copying the deficit |
| Reduced motion | The elapsed clock updates; nothing animates to persuade | A rule with no exception, because motion in a clinical screen is a persuasion technique |
| Interruption | A draft in flight can be cancelled; a page with unsaved words refuses to leave; a failure is dismissible without losing text | The three states are tested in the radiology screen today |
| Density | Two modes (reading-room, wide) plus print. Never a third "compact" that hides the source | §5's order is a density rule |

---

## 9. What is deliberately not standardised

- **No component library, no token build step, no design-tool artefact.** Two rendering targets
  and one small team; a shared package would be the third thing to version and the first thing to
  drift. The names and the behaviour are the standard.
- **No per-department review UX** (§7).
- **No department-specific colour meanings.** A queue row is never `--block`; only a check is.
- **No new status colours for new applications.** Fourteen applications and four semantic colours
  is the design; if a screen needs a fifth, the pattern it renders is wrong.
- **No icons as the only carrier of meaning.** An icon may repeat a word; it may not replace one.
- **No dark mode invented per screen.** One theme, one override, one system signal.

---

## 10. Conformance

A new application is *in the language* when it can answer these seven questions with a citation:

1. Which tokens does it use, and are the four semantic ones bound to their meanings?
2. Which shortcuts does it bind, and does each one's label already say what it does?
3. Where is the source, and is it adjacent to the document?
4. Which of the eleven patterns does it implement, and which does it *not* need — with a reason?
5. What happens when the model is down, and is the manual path visibly live?
6. What does it write to browser storage: nothing, and what test proves that?
7. What does its printout carry that its screen hides?

The built screen answers all seven in `apps/radiology_copilot/tests/test_screen.py` (19 tests),
and that file is the template for the next thirteen. **A design system nobody can test is a
mood board.**

*FutureKind · Genesis Night 3 · 2026-10-09. Every value and keystroke here was read from the
running screen; the three items marked **gap** are the ones it does not yet meet.*
