"""The reporting screen, tested as a second reader of the contracts it renders.

There is no DOM harness in this repository and no browser in the test suite, so these
tests do not pretend to click anything. What they can do is prove the two things that
actually break when somebody edits this file: that a rule the application owns is
*applied* by the screen rather than re-invented in JavaScript, and that the promises the
file makes about patient text on its head — nothing stored, nothing fetched from outside,
no clinical text interpolated into markup — are still true.

A source contract is only worth having if it can fail, so every presence check here is
paired with an absence check on the broken version of the same line.
"""

from __future__ import annotations

import re
from pathlib import Path

from futurekind_radiology import errors
from futurekind_radiology.report import editable_section_keys

SCREEN = (
    Path(__file__).resolve().parents[1] / "src" / "futurekind_radiology" / "static" / "index.html"
).read_text(encoding="utf-8")

#: The code, not the prose. The header comment names `localStorage` in order to forbid it,
#: so a storage test that reads the whole file passes for the wrong reason.
SCRIPT = re.search(r"<script>(.*?)</script>", SCREEN, re.S).group(1)

#: Every refusal class the application can raise, read off the module rather than typed
#: out here, so a new error class with no guidance on the screen is a test failure.
ERROR_CODES = sorted(
    {
        klass.code
        for name in dir(errors)
        if isinstance((klass := getattr(errors, name, None)), type)
        and issubclass(klass, errors.RadiologyError)
        and klass is not errors.RadiologyError
    }
)


# -- the ownership rule itself ---------------------------------------------------------------------


def test_the_four_prose_sections_are_always_editable() -> None:
    assert editable_section_keys("department") == (
        "findings",
        "impression",
        "recommendations",
        "follow_up",
    )


def test_a_technique_line_the_model_wrote_is_editable() -> None:
    """The defect this fixes: the screen locked technique unconditionally while
    `copilot._assemble` lets the model own the sentence when the department supplied no
    parameters. A locked box holding the machine's guess locks the radiologist out of
    their own report."""
    assert "technique" in editable_section_keys("model")


def test_a_technique_line_the_department_supplied_stays_locked() -> None:
    assert "technique" not in editable_section_keys("department")


def test_the_referrers_question_is_never_editable_in_the_draft() -> None:
    for owner in ("department", "model", "anything else"):
        assert "clinical_indication" not in editable_section_keys(owner)


# -- the screen applies that rule, it does not have its own ---------------------------------------


def test_the_screen_locks_technique_by_ownership_not_by_name() -> None:
    assert 'report.metadata.technique_from === "model"' in SCREEN
    # The broken version, and the reason the line above is a contract rather than a
    # decoration: a hardcoded `false` beside the section names is exactly what was here.
    assert '["technique", "Technique", false]' not in SCREEN


def test_the_screen_says_why_a_box_is_locked() -> None:
    """A locked field with no reason reads as a dead field, and the radiologist stops
    believing the panel."""
    for note in ("clinical_indication", "technique_department", "technique_model"):
        assert f"{note}:" in SCREEN, note
    assert "LOCK_NOTES" in SCREEN


# -- the promises about patient text -------------------------------------------------------------


def test_nothing_clinical_is_written_to_browser_storage() -> None:
    """The header comment claims the draft lives in this tab and nowhere else. A shared
    department workstation keeps the last patient on it otherwise."""
    for forbidden in (
        "localStorage",
        "sessionStorage",
        "indexedDB",
        "document.cookie",
        "caches.open",
        "serviceWorker",
    ):
        assert forbidden not in SCRIPT, forbidden


def test_no_clinical_text_is_interpolated_into_markup() -> None:
    """`innerHTML` with a template literal is how dictated text becomes HTML. Every place
    this file writes markup it writes a static string; anything carrying words uses
    `textContent` or a created node."""
    for statement in re.findall(r"\.innerHTML\s*=\s*([^;]+);", SCRIPT):
        assert "${" not in statement, statement
    assert "escapeHtml" not in SCREEN  # nothing escapes what is never interpolated


def test_the_page_loads_nothing_from_another_machine() -> None:
    """A CDN font or script tells somebody else that a radiologist is at work."""
    for pattern in (
        r'src\s*=\s*"https?://',
        r'href\s*=\s*"https?://',
        r"<link\b",
        r"@import",
        r'fetch\(\s*"https?://',
    ):
        assert not re.search(pattern, SCREEN), pattern


# -- every way the AI can fail has a next action --------------------------------------------------


def _guide_block() -> str:
    match = re.search(r"const GUIDE = \{(.*?)\n      \};", SCREEN, re.S)
    assert match, "the failure guidance block is gone from the screen"
    return match.group(1)


def test_every_refusal_the_application_can_raise_is_explained_on_screen() -> None:
    guide = _guide_block()
    for code in ERROR_CODES:
        assert re.search(rf"^\s+{code}:", guide, re.M), f"{code} has no guidance"


def test_the_guidance_check_can_actually_fail() -> None:
    """A presence test that matches everything proves nothing, so this one asserts the
    absence of a code the application does not have."""
    assert not re.search(r"^\s+not_a_real_code:", _guide_block(), re.M)


def test_a_credential_refusal_and_a_lost_connection_are_not_the_same_message() -> None:
    assert "policy_not_enforced" in _guide_block()
    assert "gateway_request_failed" in _guide_block()
    assert "network" in _guide_block()


# -- the workflow the department runs ------------------------------------------------------------


def test_the_four_workflow_endpoints_are_the_only_upstream_calls() -> None:
    """`/health` is the fifth, to say whether the service can draft at all. Anything else
    would mean the screen reaching past the workflow it renders."""
    paths = set(re.findall(r'post\(\s*"(/[a-z]+)"', SCRIPT)) | set(
        re.findall(r'fetch\(\s*"(/[a-z]+)"', SCRIPT)
    )
    assert paths == {"/draft", "/check", "/review", "/export", "/health"}


def test_the_screen_starts_without_anybody_else_s_clinical_text() -> None:
    """Prefilled indication and dictation were the demo's own hazard: a study can be
    reported under the sample words and only the signer notices. Placeholders describe
    the shape instead."""
    for field in ("indication", "findings", "technique"):
        block = re.search(rf'<textarea id="{field}"[^>]*>', SCREEN)
        assert block, field
        assert 'value="' not in block.group(0), field
        assert "placeholder=" in block.group(0), field


def test_a_finding_that_names_a_section_jumps_to_the_words_that_caused_it() -> None:
    assert "setSelectionRange" in SCREEN
    assert "scrollIntoView" in SCREEN


def test_a_non_json_answer_is_named_rather_than_dumped_on_the_screen() -> None:
    """A proxy error page or a crashed worker answers without JSON. The screen used to show
    the browser's own parse error, which a radiologist cannot act on, and the fallback for an
    unrecognisable body used to print all of it."""
    assert "function notJson(" in SCRIPT
    assert "without the JSON this screen expects" in SCRIPT
    assert "return JSON.stringify(body, null, 2);" not in SCRIPT  # the uncapped version
    assert "raw.length > 600" in SCRIPT


def test_a_failed_clipboard_write_does_not_claim_to_have_copied() -> None:
    assert "if (await copyToClipboard(result.content)) status(" in SCRIPT


def test_the_textareas_are_measured_after_they_are_in_the_document() -> None:
    """Height of a detached element is zero: the first version of the autosize collapsed
    every section of a drafted report to a 16-pixel slit."""
    assert "isConnected" in SCRIPT
    grow_calls = SCRIPT.index("function grow")
    assert 'for (const box of host.querySelectorAll("textarea")) grow(box);' in SCRIPT
    assert grow_calls < SCRIPT.index("function renderSections")


def test_printing_opens_the_audit_block_it_hides_on_screen() -> None:
    assert "beforeprint" in SCREEN
    assert "@media print" in SCREEN
