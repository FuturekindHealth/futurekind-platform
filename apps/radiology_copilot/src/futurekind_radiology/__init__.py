"""FutureKind Radiology Copilot — the first clinical workflow on the platform.

One skill, ``radiology-report``, worked end to end: a clinician submits an
indication, a modality and their findings; the Gateway drafts a structured
report; a named radiologist reviews it; the signed document exports.

This package is an **Application** in the sense of ``docs/ARCHITECTURE.md`` — it
sits above FutureKind Core and reaches no model except through the Gateway. It
holds no clinical state: every operation is a pure transform of the document it
is handed, because ``docs/DOMAIN_MODEL.md`` places a Report's storage in the EHR
and explicitly outside FutureKind.
"""

__version__ = "0.1.0"

#: The only skill this application uses, and the reason it exists.
SKILL_NAME = "radiology-report"
