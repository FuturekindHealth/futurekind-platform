"""Gateway domain errors.

Every failure the Gateway can surface carries a stable machine-readable
``code``, an HTTP status, and an operator-facing ``message``.  The FastAPI layer
renders these into one consistent envelope so callers can branch on ``code``
rather than parsing prose.

Provider-side failures have their own hierarchy in
:mod:`futurekind_gateway.providers.base`; the service layer translates them
into the domain errors defined here.
"""

from __future__ import annotations

from typing import Any


class GatewayError(Exception):
    """Base class for every error the Gateway reports deliberately."""

    code: str = "gateway_error"
    status_code: int = 500
    #: Whether retrying an identical request is plausibly useful.
    retryable: bool = False

    def __init__(
        self,
        message: str | None = None,
        *,
        code: str | None = None,
        status_code: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.message = message or self.__doc__ or "Gateway error"
        self.code = code or type(self).code
        self.status_code = status_code or type(self).status_code
        self.details: dict[str, Any] = dict(details or {})
        super().__init__(self.message)

    def to_body(self, request_id: str | None = None) -> dict[str, Any]:
        """Render the JSON error envelope returned to callers."""
        error: dict[str, Any] = {
            "code": self.code,
            "message": self.message,
            "retryable": self.retryable,
        }
        if self.details:
            error["details"] = self.details
        if request_id:
            error["request_id"] = request_id
        return {"error": error}


class ConfigurationError(GatewayError):
    """The Gateway cannot serve as configured."""

    code = "configuration_error"
    status_code = 503


class CatalogError(GatewayError):
    """The model catalogue is missing, unreadable or invalid."""

    code = "catalog_error"
    status_code = 503
    retryable = False


class AuthenticationError(GatewayError):
    """The caller presented no credential, or an unknown one."""

    code = "unauthenticated"
    status_code = 401


class AuthenticationNotConfiguredError(GatewayError):
    """Authentication is required but no API keys are configured.

    Failing closed is the only safe behaviour for a clinical gateway: an
    unauthenticated AI endpoint must never be started by accident.
    """

    code = "authentication_not_configured"
    status_code = 503


class ApprovalRequiredError(GatewayError):
    """The skill's policy requires sign-off the Gateway has no way to verify.

    Raised only by a policy an operator declared in ``models.yaml``, and never
    bypassed by a caller-supplied claim: an approvals service has to confirm a
    signature, so until one exists the Gateway refuses instead of granting. The
    request is audited on the way out.
    """

    code = "approval_required"
    status_code = 403

    def __init__(self, skill: str, *, clinical_risk: str) -> None:
        super().__init__(
            f"Skill '{skill}' requires clinical approval, which this Gateway cannot verify yet",
            details={
                "skill": skill,
                "clinical_risk": clinical_risk,
                "required": "approval",
                "hint": (
                    "record the approval in an approvals service and have it call the Gateway, "
                    "or set approval_required: false for this skill if its risk level allows it"
                ),
            },
        )
        self.skill = skill
        self.clinical_risk = clinical_risk


class ValidationError(GatewayError):
    """The request was well-formed JSON but semantically unusable."""

    code = "invalid_request"
    status_code = 422


class UnknownSkillError(GatewayError):
    """No catalogue entry exists for the requested skill."""

    code = "unknown_skill"
    status_code = 404

    def __init__(self, skill: str, *, known: tuple[str, ...] = ()) -> None:
        super().__init__(
            f"Skill '{skill}' is not declared in the model catalogue",
            details={"skill": skill, "known_skills": list(known)},
        )
        self.skill = skill


class UnknownCapabilityError(GatewayError):
    """No catalogue entry exists for the requested capability."""

    code = "unknown_capability"
    status_code = 404

    def __init__(self, capability: str, *, known: tuple[str, ...] = ()) -> None:
        super().__init__(
            f"Capability '{capability}' is not in the model catalogue",
            details={"capability": capability, "known_capabilities": list(known)},
        )
        self.capability = capability


class RoutingError(GatewayError):
    """The request cannot be mapped to any usable route."""

    code = "routing_failed"
    status_code = 400


class ProviderNotImplementedError(GatewayError):
    """The route resolved, but its provider has no implementation in this build."""

    code = "provider_not_implemented"
    status_code = 501

    def __init__(self, provider: str, *, registered: tuple[str, ...] = ()) -> None:
        super().__init__(
            f"Provider '{provider}' has no implementation registered with this Gateway",
            details={
                "provider": provider,
                "registered_providers": list(registered),
                "hint": "Implement the Provider contract and register it with ProviderRegistry",
            },
        )
        self.provider = provider


class FeatureNotImplementedError(GatewayError):
    """A declared part of the contract this build does not perform yet."""

    code = "feature_not_implemented"
    status_code = 501


class ProviderFailedError(GatewayError):
    """Every candidate provider for this route failed."""

    code = "provider_unavailable"
    status_code = 502
    retryable = True


class UpstreamTimeoutError(GatewayError):
    """The provider did not answer within the configured timeout."""

    code = "provider_timeout"
    status_code = 504
    retryable = True


__all__ = [
    "ApprovalRequiredError",
    "AuthenticationError",
    "AuthenticationNotConfiguredError",
    "CatalogError",
    "ConfigurationError",
    "FeatureNotImplementedError",
    "GatewayError",
    "ProviderFailedError",
    "ProviderNotImplementedError",
    "RoutingError",
    "UnknownCapabilityError",
    "UnknownSkillError",
    "UpstreamTimeoutError",
    "ValidationError",
]
