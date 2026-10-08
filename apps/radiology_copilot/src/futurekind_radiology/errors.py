"""Every way this application can refuse to produce a report.

The envelope is the Gateway's (``docs/SPECIFICATION.md:263``): ``{error: {code,
message, retryable, request_id, details}}``. One shape across the platform means
a screen written against it does not have to learn a second one, and a clinician
sees the same field names wherever a request failed.

Two rules hold here that the Gateway also holds:

* **A refusal states why, and never quotes the patient.** ``details`` carries
  structure — key names, counts, byte lengths — never model output or dictated
  text, because an application log picked up by an operator must not become the
  place clinical data went.
* **Refusals fail closed.** An unusable model answer is an error, not a report
  with an empty ``impression``. A blank section in a radiology document is worse
  than no document.
"""

from __future__ import annotations

from typing import Any

__all__ = [
    "DegradedAnswerError",
    "GatewayRequestError",
    "ModelOutputError",
    "PolicyNotEnforcedError",
    "RadiologyError",
    "ReportTruncatedError",
    "ReviewError",
    "SkillMismatchError",
    "UnsignedExportError",
]


class RadiologyError(Exception):
    """Base class for a refusal this application can explain."""

    code = "radiology_error"
    status_code = 500
    retryable = False

    def __init__(
        self,
        message: str,
        *,
        details: dict[str, Any] | None = None,
        request_id: str | None = None,
        retryable: bool | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}
        self.request_id = request_id
        if retryable is not None:
            self.retryable = retryable

    def to_body(self) -> dict[str, Any]:
        """The JSON error envelope, in the Gateway's field names."""
        return {
            "error": {
                "code": self.code,
                "message": self.message,
                "retryable": self.retryable,
                "request_id": self.request_id,
                "details": self.details,
            }
        }


class GatewayRequestError(RadiologyError):
    """The Gateway answered with an error, so no draft exists.

    The upstream ``code`` and ``request_id`` are carried through: they are what an
    operator needs to find the Gateway log line for the same request.
    """

    code = "gateway_request_failed"
    status_code = 502

    def __init__(
        self,
        message: str,
        *,
        upstream_code: str | None = None,
        status_code: int | None = None,
        retryable: bool | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(message, retryable=retryable, **kwargs)
        self.status_code = status_code or self.status_code
        if upstream_code:
            self.details.setdefault("upstream_code", upstream_code)


class ModelOutputError(RadiologyError):
    """The answer arrived but is not a report.

    Raised for prose instead of JSON, unparseable JSON, a missing section or a
    section that is not text. Each carries the structural reason only.
    """

    code = "model_output_unusable"
    status_code = 502
    retryable = True


class ReportTruncatedError(RadiologyError):
    """Generation ran out of tokens mid-report.

    A truncated report is the dangerous case rather than the annoying one: the
    section most likely to be cut is the last one, and a half-written impression
    reads like a complete one. The draft is withheld and the clinician is told the
    report was not finished.
    """

    code = "report_truncated"
    status_code = 502
    retryable = True


class PolicyNotEnforcedError(RadiologyError):
    """The skill's policy is not the one this document was written against.

    ``radiology-report`` is only safe to draft under a policy that audits the
    request and forbids a lesser model answering it. If an operator relaxes
    either, drafting must stop — silently continuing is how a high-risk skill
    becomes a low-risk one without anyone deciding that.
    """

    code = "policy_not_enforced"
    status_code = 503


class SkillMismatchError(RadiologyError):
    """The completion did not come from ``radiology-report``."""

    code = "skill_mismatch"
    status_code = 503


class DegradedAnswerError(RadiologyError):
    """A lesser model answered a high-risk skill.

    The policy says ``allow_downgrade: false``, so this should be unreachable. It
    is checked rather than assumed: Constitution P13 makes a silent substitution
    the failure this platform exists to prevent, and the application is the last
    place that can still refuse it.
    """

    code = "degraded_answer"
    status_code = 503


class UnsignedExportError(RadiologyError):
    """Export was asked for a report no clinician has signed off."""

    code = "report_unsigned"
    status_code = 409


class ReviewError(RadiologyError):
    """The sign-off action is not one this report can accept."""

    code = "review_invalid"
    status_code = 422
