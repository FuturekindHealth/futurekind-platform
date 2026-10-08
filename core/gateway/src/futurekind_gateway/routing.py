"""Capability routing: turning what an application asks for into what runs.

Applications request a **skill** (``radiology-report``) or, at the technical
layer, a **capability** (``reasoning``).  The router resolves that to a
catalogue entry, attaches the skill's :class:`~futurekind_gateway.policy.SkillPolicy`,
and produces the ordered chain of candidates the service layer may walk.

Routing rules, in one place on purpose:

* ``skill`` is the application-level selector and wins over ``capability``.
* If both are supplied they must agree, otherwise the request is refused rather
  than silently routed somewhere else.
* Neither supplied routes to the configured default capability, under
  ``DEFAULT_POLICY`` — which is why naming a skill is the safer call.
* **No selector may name a model, provider or endpoint** (``ADR-0002``). The
  model id a route resolves to is internal and is never accepted as input.
* Disabled entries are never routed to, and never appear in a fallback chain.
* A policy that forbids downgrade gets a chain of one: the lesser classes stay
  in the catalogue but out of this request's route.
* Fallback chains are expanded transitively, deduplicated, cycle-safe and capped.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

from .catalog import ModelCatalog, ModelEntry
from .errors import RoutingError
from .policy import DEFAULT_POLICY, SkillPolicy

#: Guards against pathological fallback graphs even though cycles are rejected.
MAX_CHAIN_LENGTH = 16


@dataclass(frozen=True)
class Route:
    """A resolved request: what was asked for, the rules it runs under, and what can serve it."""

    capability: str
    entry: ModelEntry
    chain: tuple[ModelEntry, ...]
    selected_by: str
    default_capability: str = ""
    skill: str | None = None
    policy: SkillPolicy = DEFAULT_POLICY

    @property
    def provider(self) -> str:
        return self.entry.provider

    @property
    def model(self) -> str:
        """Internal. Reported outward for provenance; never accepted as input."""
        return self.entry.model

    @property
    def target(self) -> str:
        """The name this Gateway sends to its provider for this route.

        The alias, when the row has one (``ModelEntry.target``). ``model`` stays
        the thing the alias resolves to behind LiteLLM, which is why both appear
        in the audit line: one is what was asked for, the other is what ran.
        """
        return self.entry.target

    @property
    def alias(self) -> str | None:
        """Internal. The LiteLLM-facing name of the resolved target; audit only."""
        return self.entry.alias

    @property
    def candidates(self) -> tuple[ModelEntry, ...]:
        return self.chain

    @property
    def has_fallbacks(self) -> bool:
        return len(self.chain) > 1

    def candidate_capabilities(self) -> tuple[str, ...]:
        return tuple(entry.capability for entry in self.chain)

    def to_public_dict(self) -> dict[str, object]:
        # No policy fields here on purpose: `routes()` describes capabilities, and a
        # capability has no risk level of its own — only the skills that name it do.
        return {
            "capability": self.capability,
            "skill": self.skill,
            "selected_by": self.selected_by,
            "provider": self.provider,
            "model": self.model,
            "chain": [entry.capability for entry in self.chain],
        }


class ModelRouter:
    """Resolve skill/capability requests into ordered :class:`Route` objects."""

    def __init__(self, catalog: ModelCatalog, *, default_capability: str = "default") -> None:
        self._catalog = catalog
        self._default_capability = default_capability

    @property
    def catalog(self) -> ModelCatalog:
        return self._catalog

    @property
    def default_capability(self) -> str:
        return self._default_capability

    def resolve(
        self,
        *,
        skill: str | None = None,
        capability: str | None = None,
    ) -> Route:
        """Return the route for a request, or raise a routing/domain error.

        A skill is the application's word for what it needs; a capability is the
        Gateway's technical class for serving it.  A skill wins when both are
        given, because it is the nearer statement of intent — and if the two
        disagree the request is refused, since a routing decision made on a
        coincidence of precedence is not a decision anyone can defend later.

        The route carries the skill's policy with it, so every layer downstream
        reads the same decision instead of re-deriving it.  A request that names
        no skill gets ``DEFAULT_POLICY``, which is why an application that wants
        its own rules applied has to name the skill those rules are written for.
        """
        requested_skill = self._catalog.require_skill(skill) if skill else None

        if requested_skill is not None:
            if not requested_skill.enabled:
                raise RoutingError(
                    f"Skill '{requested_skill.name}' is disabled in the model catalogue",
                    details={"skill": requested_skill.name},
                )
            entry = self._catalog.require(requested_skill.capability)
            selected_by = "skill"
            if capability and capability != entry.capability:
                raise RoutingError(
                    f"Skill '{requested_skill.name}' is served by capability "
                    f"'{entry.capability}', not the requested '{capability}'",
                    details={
                        "skill": requested_skill.name,
                        "requested_capability": capability,
                        "actual_capability": entry.capability,
                    },
                )
        elif capability:
            entry = self._catalog.require(capability)
            selected_by = "capability"
        else:
            entry = self._catalog.require(self._default_capability)
            selected_by = "default"

        if not entry.enabled:
            raise RoutingError(
                f"Capability '{entry.capability}' is disabled in the model catalogue",
                details={"capability": entry.capability},
            )

        policy = requested_skill.policy if requested_skill is not None else DEFAULT_POLICY
        chain = self.build_chain(entry, allow_downgrade=policy.allow_downgrade)
        return Route(
            capability=entry.capability,
            entry=entry,
            chain=chain,
            selected_by=selected_by,
            default_capability=self._default_capability,
            skill=requested_skill.name if requested_skill else None,
            policy=policy,
        )

    def build_chain(
        self, entry: ModelEntry, *, allow_downgrade: bool = True
    ) -> tuple[ModelEntry, ...]:
        """Expand an entry and its fallbacks into an ordered, enabled-only chain.

        ``allow_downgrade`` is the skill's policy, not the caller's: when it is
        false the chain is the primary entry alone, so a lesser class cannot
        answer a request that was routed to a ``high`` or ``critical`` risk
        skill.  The candidates stay in the catalogue — this narrows one route, it
        does not take a model out of service.
        """
        if not allow_downgrade:
            return (entry,) if entry.enabled else ()

        chain: list[ModelEntry] = []
        seen: set[str] = set()
        pending: list[ModelEntry] = [entry]

        while pending:
            current = pending.pop(0)
            if current.capability in seen:
                continue
            if not current.enabled:
                continue
            chain.append(current)
            seen.add(current.capability)
            if len(chain) >= MAX_CHAIN_LENGTH:
                break
            for fallback in current.fallbacks:
                # The catalogue rejects dangling names at load, so `require` cannot fail here.
                pending.append(self._catalog.require(fallback))

        if not chain:
            raise RoutingError(
                f"No enabled model can serve capability '{entry.capability}'",
                details={
                    "capability": entry.capability,
                    "fallbacks": list(entry.fallbacks),
                },
            )
        return tuple(chain)

    def routes(self) -> Iterator[Route]:
        """Every enabled capability's route, in catalogue order."""
        for entry in self._catalog.enabled_entries():
            yield Route(
                capability=entry.capability,
                entry=entry,
                chain=self.build_chain(entry),
                selected_by="catalogue",
                default_capability=self._default_capability,
            )

    def describe(self) -> list[dict[str, object]]:
        """Machine-readable routing table, used by ``GET /models``."""
        return [route.to_public_dict() for route in self.routes()]

    def missing_providers(self, registered: tuple[str, ...]) -> list[str]:
        """Providers the catalogue needs that no implementation answers to."""
        available = set(registered)
        return [
            provider
            for provider in self._catalog.providers_in_use()
            if provider not in available
        ]


__all__ = [
    "MAX_CHAIN_LENGTH",
    "ModelRouter",
    "Route",
]
