"""FutureKind Radiology Copilot — the first clinical workflow on the platform.

One skill, ``radiology-report``, worked end to end for one study type — MRI brain:
the study and its clinical indication arrive, any previous reports come with them,
the Gateway drafts, nine deterministic quality checks compare the draft with what
was submitted, a named radiologist edits and approves it section by section, and
only the signed document exports.

This package is an **Application** in the sense of ``docs/ARCHITECTURE.md`` — it
sits above FutureKind Core and reaches no model except through the Gateway. It
holds no clinical state: every operation is a pure transform of the document it
is handed, because ``docs/DOMAIN_MODEL.md`` places a Report's storage in the EHR
and explicitly outside FutureKind.
"""

__version__ = "0.2.0"

#: The only skill this application uses, and the reason it exists.
SKILL_NAME = "radiology-report"
