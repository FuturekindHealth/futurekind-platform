"""Declarative policy: the Gateway's business rules, read from configuration.

``ADR-0002`` rule 3 is normative about where these decisions live:

    Skill->capability mapping, whether a lower class may answer a given skill,
    and the clinical context attached to a request are Gateway policy. They
    belong in ``models.yaml``, not in application code and not in LiteLLM
    configuration.

Before this module, two of those rules were Python: the request limits in
``api/routes_chat.enforce_limits`` and the unconditional fallback chain in
``routing.build_chain``. Both now come from configuration, so changing them is
an operator edit rather than a code review.

One policy attaches to each skill. A request that names no skill gets
:data:`DEFAULT_POLICY`, which is deliberately inert: it keeps today's behaviour
so that introducing policy is not itself a behaviour change.

The configuration vocabulary is a skill's own stanza in ``models.yaml``. Only
``clinical_risk`` is required of a skill; every other line below may be omitted,
and the shipped file uses a subset of it::

    radiology-report:
      capability: reasoning
      clinical_risk: high          # required, and the operator's decision
      approval_required: false
      audit_required: true
      allow_downgrade: false       # forced for high and critical risk
      max_messages: 20             # may tighten, never raise, the platform ceiling
      max_content_chars: 8000
      max_completion_tokens: 1024
      request_timeout_seconds: 60

The model **alias** is not part of policy. It belongs to the routing row
(``catalog.ModelEntry.alias``), because a skill that named a model target would
re-fuse intent and infrastructure — see ``docs/architecture/gateway-policy.md``.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, fields
from typing import Any

from .config import GatewaySettings
from .errors import ApprovalRequiredError, CatalogError, ValidationError

#: Clinical risk levels, in escalation order.
#:
#: ``unspecified`` is not a risk assessment. It is what a request carries when
#: no skill was named, so that "nobody assessed this" stays visible in the audit
#: record instead of defaulting into ``low``. A declared skill may not use it.
CLINICAL_RISK_LEVELS = ("unspecified", "low", "moderate", "high", "critical")

#: Levels a skill may declare in configuration.
DECLARABLE_RISK_LEVELS = CLINICAL_RISK_LEVELS[1:]

#: Levels that carry a clinical consequence, and therefore the coupled rules below.
ESCALATED_RISK_LEVELS = ("high", "critical")

#: Every policy key a configuration block may carry. Unknown keys are typos to reject.
POLICY_KEYS = frozenset(
    {
        "clinical_risk",
        "approval_required",
        "audit_required",
        "allow_downgrade",
        "max_messages",
        "max_content_chars",
        "max_completion_tokens",
        "request_timeout_seconds",
    }
)

#: Keys whose value must be a real boolean, not YAML's idea of one.
_BOOLEAN_KEYS = ("approval_required", "audit_required", "allow_downgrade")

#: Keys whose value must be a positive integer. Names mirror ``GatewaySettings`` so
#: one vocabulary covers environment and configuration.
_INTEGER_KEYS = ("max_messages", "max_content_chars", "max_completion_tokens")

#: A policy timeout above this is an operator typo, not a clinical decision.
MAX_POLICY_TIMEOUT_SECONDS = 3_600.0


@dataclass(frozen=True)
class SkillPolicy:
    """The governance rules attached to one skill, fully resolved.

    Values are decisions, not capabilities: nothing here can be widened by a
    caller, only enforced. ``None`` on a limit field means "the skill adds no
    ceiling", which leaves the platform's own limit in force.

    Limits are kept here rather than in a separate object because a single skill
    declares both, and splitting them would let the two drift apart.
    """

    clinical_risk: str = "unspecified"
    approval_required: bool = False
    audit_required: bool = True
    allow_downgrade: bool = True
    max_messages: int | None = None
    max_content_chars: int | None = None
    max_completion_tokens: int | None = None
    request_timeout_seconds: float | None = None

    def to_dict(self) -> dict[str, Any]:
        """Every field, including the unset limits. Folded under a skill's declarations."""
        return {field.name: getattr(self, field.name) for field in fields(self)}

    def to_public_dict(self) -> dict[str, Any]:
        """What ``/chat`` reports about this decision.

        Governance only. The numeric limits are deployment tuning — reporting them
        would invite a caller to size a request to the ceiling, and reporting a
        timeout would report infrastructure speed.
        """
        return {
            "clinical_risk": self.clinical_risk,
            "approval_required": self.approval_required,
            "audit_required": self.audit_required,
            "allow_downgrade": self.allow_downgrade,
        }

    @property
    def escalated(self) -> bool:
        """True when the risk level brings the coupled rules with it."""
        return self.clinical_risk in ESCALATED_RISK_LEVELS


#: The floor a skill's declarations are folded over, and the whole policy for a
#: request that names no skill. It is a decision made once, here, rather than a
#: rule repeated at each call site.
DEFAULT_POLICY = SkillPolicy()


def _check_risk(owner: str, value: Any) -> str:
    if not isinstance(value, str) or value.strip().lower() not in DECLARABLE_RISK_LEVELS:
        raise CatalogError(
            f"Skill '{owner}' declares clinical_risk {value!r}; use one of "
            f"{', '.join(DECLARABLE_RISK_LEVELS)}",
            details={
                "owner": owner,
                "field": "clinical_risk",
                "allowed": list(DECLARABLE_RISK_LEVELS),
            },
        )
    return value.strip().lower()


def _check_boolean(owner: str, key: str, value: Any) -> bool:
    if not isinstance(value, bool):
        raise CatalogError(
            f"Skill '{owner}' field '{key}' must be true or false",
            details={"owner": owner, "field": key, "found": type(value).__name__},
        )
    return value


def _check_positive_int(owner: str, key: str, value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise CatalogError(
            f"Skill '{owner}' field '{key}' must be a positive whole number",
            details={"owner": owner, "field": key, "found": repr(value)[:80]},
        )
    return value


def _check_timeout(owner: str, value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CatalogError(
            f"Skill '{owner}' field 'request_timeout_seconds' must be a number of seconds",
            details={"owner": owner, "field": "request_timeout_seconds"},
        )
    seconds = float(value)
    if not 0.0 < seconds <= MAX_POLICY_TIMEOUT_SECONDS:
        raise CatalogError(
            f"Skill '{owner}' requests a timeout of {seconds:g}s, which must be "
            f"between 0 and {MAX_POLICY_TIMEOUT_SECONDS:g}s",
            details={"owner": owner, "field": "request_timeout_seconds"},
        )
    return seconds


def declared_policy(owner: str, values: Mapping[str, Any]) -> dict[str, Any]:
    """Validate the policy keys one configuration block declares.

    Returns only those keys, so the caller can fold them over
    :data:`DEFAULT_POLICY`. The distinction between "the operator chose this" and
    "the floor supplied this" is what makes an omitted limit mean "no ceiling
    from this skill" rather than "the skill set it to the default".
    """
    unknown = sorted(set(values) - POLICY_KEYS)
    if unknown:
        raise CatalogError(
            f"Skill '{owner}' has unsupported policy field(s): {', '.join(unknown)}",
            details={"owner": owner, "unsupported": unknown, "supported": sorted(POLICY_KEYS)},
        )

    declared: dict[str, Any] = {}
    for key, value in values.items():
        if key == "clinical_risk":
            declared[key] = _check_risk(owner, value)
        elif key in _BOOLEAN_KEYS:
            declared[key] = _check_boolean(owner, key, value)
        elif key in _INTEGER_KEYS:
            declared[key] = _check_positive_int(owner, key, value)
        elif key == "request_timeout_seconds":
            declared[key] = _check_timeout(owner, value)
    return declared


def _reject_unsafe_combination(owner: str, policy: SkillPolicy) -> None:
    """Refuse a configuration that states a clinical contradiction.

    These are startup failures rather than runtime warnings for the same reason
    a dangling fallback name is: an operator must not be able to deploy a
    high-risk skill that is unaudited, silently downgradable, or unsigned, and
    discover it from an audit request two years later.
    """
    if not policy.escalated:
        return
    if not policy.audit_required:
        raise CatalogError(
            f"Skill '{owner}' is '{policy.clinical_risk}' risk but declares audit_required: false",
            details={
                "owner": owner,
                "field": "audit_required",
                "clinical_risk": policy.clinical_risk,
            },
        )
    if policy.allow_downgrade:
        raise CatalogError(
            f"Skill '{owner}' is '{policy.clinical_risk}' risk but still allows a "
            "downgrade to a lesser class; declare allow_downgrade: false",
            details={
                "owner": owner,
                "field": "allow_downgrade",
                "clinical_risk": policy.clinical_risk,
            },
        )
    if policy.clinical_risk == "critical" and not policy.approval_required:
        raise CatalogError(
            f"Skill '{owner}' is 'critical' risk but declares approval_required: false; "
            "a critical skill may not run without sign-off",
            details={
                "owner": owner,
                "field": "approval_required",
                "clinical_risk": policy.clinical_risk,
            },
        )


def resolve_policy(owner: str, declared: Mapping[str, Any]) -> SkillPolicy:
    """Fold one block's declared keys over the fail-closed floor and validate.

    The safety rules run on the composed policy, not on each declaration, because
    they are about the decision as deployed: a skill that declares
    ``clinical_risk: high`` and forgets ``allow_downgrade`` is still a
    silently-downgradable high-risk skill.
    """
    merged = DEFAULT_POLICY.to_dict()
    merged.update(declared)
    policy = SkillPolicy(**merged)
    _reject_unsafe_combination(owner, policy)
    return policy


@dataclass(frozen=True)
class RequestLimits:
    """One request's effective ceilings, already clamped by the platform."""

    max_messages: int
    max_content_chars: int
    max_completion_tokens: int
    request_timeout_seconds: float


def limits_for(policy: SkillPolicy, settings: GatewaySettings) -> RequestLimits:
    """Combine a policy's ceilings with the operator's, keeping whichever is lower.

    This is the whole of the rule "a skill policy may tighten a platform limit,
    never raise it", which is why it is one function: a rule stated per call
    site is a rule one call site will eventually forget.
    """

    def lower_int(value: int | None, ceiling: int) -> int:
        return ceiling if value is None else min(value, ceiling)

    def lower_seconds(value: float | None, ceiling: float) -> float:
        return ceiling if value is None else min(value, ceiling)

    return RequestLimits(
        max_messages=lower_int(policy.max_messages, settings.max_messages),
        max_content_chars=lower_int(policy.max_content_chars, settings.max_content_chars),
        max_completion_tokens=lower_int(
            policy.max_completion_tokens, settings.max_completion_tokens
        ),
        request_timeout_seconds=lower_seconds(
            policy.request_timeout_seconds, settings.request_timeout_seconds
        ),
    )


def check_approval(policy: SkillPolicy, *, skill: str | None) -> None:
    """Refuse a request whose approval the Gateway cannot verify.

    There is no approvals service yet, so nothing a caller can send proves a
    clinician signed this off. The only honest readings of
    ``approval_required: true`` are therefore to grant it — which would make the
    rule decorative — or refuse. Refusing is fail-closed and visibly says what
    is missing, so a deployment that needs the feature asks for it rather than
    discovering the gate in front of a patient.
    """
    if not policy.approval_required:
        return
    raise ApprovalRequiredError(
        skill or "an unattributed request",
        clinical_risk=policy.clinical_risk,
    )


def _subject(skill: str | None) -> str:
    """Name what a limit applies to, for a caller who never sees an internal id."""
    return f"skill '{skill}'" if skill else "this request"


def check_request(
    policy: SkillPolicy,
    *,
    skill: str | None,
    message_count: int,
    longest_message_chars: int,
    requested_max_tokens: int | None,
    settings: GatewaySettings,
) -> None:
    """Enforce the policy before a model is called.

    Raises :class:`ValidationError` naming the rule, so the operator's fix is
    either to shorten the request or to change the configuration.  The timeout is
    not checked here: nothing about a request body can exceed it, so
    :func:`limits_for` supplies it to the service layer instead.
    """
    check_approval(policy, skill=skill)
    limits = limits_for(policy, settings)
    subject = _subject(skill)

    if message_count > limits.max_messages:
        raise ValidationError(
            f"{subject} accepts at most {limits.max_messages} messages per request",
            details={
                "limit": "max_messages",
                "received": message_count,
                "allowed": limits.max_messages,
                "skill": skill,
                "clinical_risk": policy.clinical_risk,
            },
        )
    if longest_message_chars > limits.max_content_chars:
        raise ValidationError(
            f"A message exceeds the {limits.max_content_chars} character limit for {subject}",
            details={
                "limit": "max_content_chars",
                "longest_message_chars": longest_message_chars,
                "allowed": limits.max_content_chars,
                "skill": skill,
                "clinical_risk": policy.clinical_risk,
            },
        )
    if requested_max_tokens is not None and requested_max_tokens > limits.max_completion_tokens:
        raise ValidationError(
            f"max_tokens exceeds the {limits.max_completion_tokens} token ceiling for {subject}",
            details={
                "limit": "max_completion_tokens",
                "requested": requested_max_tokens,
                "allowed": limits.max_completion_tokens,
                "skill": skill,
                "clinical_risk": policy.clinical_risk,
            },
        )


__all__ = [
    "CLINICAL_RISK_LEVELS",
    "DEFAULT_POLICY",
    "DECLARABLE_RISK_LEVELS",
    "ESCALATED_RISK_LEVELS",
    "MAX_POLICY_TIMEOUT_SECONDS",
    "POLICY_KEYS",
    "RequestLimits",
    "SkillPolicy",
    "check_approval",
    "check_request",
    "declared_policy",
    "limits_for",
    "resolve_policy",
]
