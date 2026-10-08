"""The model catalogue: skill -> policy -> capability -> alias -> model.

Per ``ADR-0002`` these are distinct namespaces, and only the outer ones are
names an application may use:

* **Skill** — application intent. ``radiology-report``, ``clinical-chat``,
  ``summarize-document``, ``pathology-review``. What a clinician pressed.
* **Policy** — the governance attached to that intent: clinical risk, approval,
  audit, whether a lesser class may answer. Declarative, validated at startup,
  owned by the Gateway. See :mod:`futurekind_gateway.policy`.
* **Capability** — technical class the Gateway maps a skill to. ``chat``,
  ``reasoning``, ``vision``, ``embedding``.
* **Alias** — the stable name of the routing target, agreed with LiteLLM.
  Internal: reported in no response, logged for audit, and the name the Gateway
  actually sends (``ModelEntry.target``).
* **Provider** — the transport the request is handed to. ``litellm`` for every
  row that obeys the platform rule; the backend family lives inside the model
  string, because choosing it is LiteLLM's job and not this catalogue's.
* **Model** — which weights run behind the alias, in LiteLLM's notation
  (``ollama/gpt-oss:20b``). **Internal.** No application-facing field may carry
  a model id; the catalogue holds them as declared inventory, cross-checked
  against ``configs/litellm/config.yaml`` at startup.

Expected document::

    models:
      default:
        alias: fk-default
        provider: litellm
        model: ollama/gpt-oss:20b
      fast:
        alias: fk-fast
        provider: litellm
        model: ollama/gemma3:12b
        fallbacks: [default]

    skills:
      radiology-report:
        capability: reasoning
        clinical_risk: high
        allow_downgrade: false

Loading is deliberately strict.  Unknown keys, self-referencing fallbacks,
skills naming a capability that does not exist, a skill with no declared risk
level, an unsafe risk/approval combination, duplicate YAML keys and dangling
fallback names all fail at startup with a message that names the field at
fault — because a silently ignored typo in a clinical routing table is far more
dangerous than a refused start.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .errors import CatalogError, UnknownCapabilityError, UnknownSkillError
from .policy import (
    DEFAULT_POLICY,
    POLICY_KEYS,
    SkillPolicy,
    declared_policy,
    resolve_policy,
)

#: The two stanzas a catalogue may contain. Anything else is a typo to reject.
_CATALOG_KEYS = frozenset({"models", "skills"})

#: Optional keys an entry may carry beyond ``provider`` and ``model``.
_ENTRY_KEYS = frozenset(
    {"provider", "model", "alias", "description", "fallbacks", "enabled"}
)

#: What a skill is, as opposed to how it is governed.
_SKILL_IDENTITY_KEYS = frozenset({"capability", "description", "enabled"})

#: A skill declares its intent and its policy — and no infrastructure at all.
_SKILL_KEYS = _SKILL_IDENTITY_KEYS | POLICY_KEYS

_REQUIRED_ENTRY_KEYS = ("provider", "model")


class _UniqueKeyLoader(yaml.SafeLoader):
    """``yaml.SafeLoader`` that rejects duplicate mapping keys.

    ``SafeLoader`` silently lets the last duplicate win, which in a routing
    table means a model entry can vanish without any error at all.
    """

    def construct_mapping(self, node: yaml.MappingNode, deep: bool = False) -> dict[Any, Any]:  # type: ignore[override]
        seen: set[Any] = set()
        for key_node, _ in node.value:
            key = self.construct_object(key_node, deep=deep)
            if key in seen:
                line = getattr(key_node.start_mark, "line", None)
                where = f" (line {line + 1})" if isinstance(line, int) else ""
                raise CatalogError(
                    f"Duplicate key '{key}' in model catalogue{where}",
                    details={"key": str(key)},
                )
            seen.add(key)
        return super().construct_mapping(node, deep=deep)


def _clean_string(value: Any, *, field_name: str, entry_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CatalogError(
            f"'{entry_name}' needs a non-empty string '{field_name}'",
            details={"entry": entry_name, "field": field_name},
        )
    return value.strip()


@dataclass(frozen=True)
class Skill:
    """An application intent, with its policy attached and no infrastructure.

    A skill is the only name a clinical application is meant to know.  It
    declares which capability serves it, and the policy that governs it: no
    model, no provider, no endpoint.  Renaming a model or moving a capability to
    another backend cannot break a skill, which is the property ``ADR-0002``
    exists to protect.

    ``policy`` is always present because there is no such thing as an
    ungoverned clinical skill.  Its risk level must be declared — the loader
    refuses a skill without one — and the rest inherits the validated floor:
    audited, downgradable, inside the platform's limits.
    """

    name: str
    capability: str
    policy: SkillPolicy = DEFAULT_POLICY
    description: str = ""
    enabled: bool = True

    def to_public_dict(self) -> dict[str, Any]:
        """Identity plus governance. Never the alias, the model or the numeric limits."""
        return {
            "name": self.name,
            "capability": self.capability,
            "description": self.description,
            "enabled": self.enabled,
            **self.policy.to_public_dict(),
        }

    @classmethod
    def from_raw(cls, name: str, raw: Any) -> Skill:
        """Build one skill from its parsed YAML block.

        The block is read by vocabulary rather than nested: ``capability``,
        ``description`` and ``enabled`` say what the skill is, the keys in
        ``policy.POLICY_KEYS`` say how it is governed, and anything else is
        refused.  Infrastructure is in that last category by definition — which
        is why a skill naming a model or a provider fails here instead of
        quietly becoming the thing ``ADR-0002`` removed.
        """
        if not isinstance(name, str) or not name.strip():
            raise CatalogError("Skill catalogue contains an empty skill name")
        if not isinstance(raw, Mapping):
            raise CatalogError(
                f"Skill '{name}' must be a mapping of fields",
                details={"skill": name},
            )

        cleaned = name.strip()
        unknown = sorted(set(raw) - _SKILL_KEYS)
        if unknown:
            raise CatalogError(
                f"Skill '{cleaned}' has unsupported field(s): {', '.join(unknown)}",
                details={
                    "skill": cleaned,
                    "unsupported": unknown,
                    "supported": sorted(_SKILL_KEYS),
                },
            )

        enabled_raw = raw.get("enabled", True)
        if not isinstance(enabled_raw, bool):
            raise CatalogError(
                f"Skill '{cleaned}' field 'enabled' must be true or false",
                details={"skill": cleaned},
            )

        # No default for the risk level, on purpose: an unassessed clinical skill
        # is the failure mode this layer exists to prevent.
        if "clinical_risk" not in raw:
            raise CatalogError(
                f"Skill '{cleaned}' must declare clinical_risk — one of low, moderate, "
                "high or critical. A clinical skill may not be deployed unassessed.",
                details={"skill": cleaned, "missing": "clinical_risk"},
            )

        declared = declared_policy(
            cleaned, {key: value for key, value in raw.items() if key in POLICY_KEYS}
        )
        return cls(
            name=cleaned,
            capability=_clean_string(
                raw.get("capability"), field_name="capability", entry_name=cleaned
            ),
            policy=resolve_policy(cleaned, declared),
            description=str(raw.get("description") or "").strip(),
            enabled=enabled_raw,
        )


@dataclass(frozen=True)
class ModelEntry:
    """One capability and the concrete model it currently resolves to.

    ``alias`` is the LiteLLM-facing name for this routing target — ``fk-default``
    in ``configs/litellm/config.yaml``.  It is internal: logged for audit, never
    returned, never accepted.  It is also what the Gateway now *sends* (see
    :attr:`target`), and :mod:`futurekind_gateway.litellm_config` proves at
    startup that the name exists on the other side, which is the check
    ``ADR-0002`` step 3 needs before the model ids can be deleted from this file.

    ``provider`` is the transport this Gateway invokes — ``litellm`` once the
    platform rule is enforced, never a model family.  ``model`` is what the
    alias resolves to *behind* LiteLLM, in LiteLLM's own notation
    (``ollama/gpt-oss:20b``).  It is inventory and provenance: reported to
    operators, compared against LiteLLM's configuration at startup, and never
    accepted from a caller.
    """

    capability: str
    provider: str
    model: str
    alias: str | None = None
    description: str = ""
    fallbacks: tuple[str, ...] = ()
    enabled: bool = True

    @property
    def target(self) -> str:
        """The name the Gateway addresses its provider with.

        The alias when there is one, because under ``ADR-0002`` the alias is the
        only identifier both sides agree on and LiteLLM decides what it means.
        Falling back to ``model`` keeps a pre-alias row usable during migration
        — and is precisely the path the startup check refuses to let a LiteLLM
        row take, so the fallback cannot survive an accident.
        """
        return self.alias or self.model

    def to_public_dict(self) -> dict[str, Any]:
        """Shape returned by ``GET /models`` — provider internals are included deliberately.

        The alias is not: ``docs/architecture/gateway-routing.md`` records it as
        the one identifier that may appear in neither direction.
        """
        return {
            "capability": self.capability,
            "provider": self.provider,
            "model": self.model,
            "description": self.description,
            "fallbacks": list(self.fallbacks),
            "enabled": self.enabled,
        }

    @classmethod
    def from_raw(cls, capability: str, raw: Any) -> ModelEntry:
        """Build one entry from its parsed YAML block, validating every field."""
        if not isinstance(capability, str) or not capability.strip():
            raise CatalogError(
                "Model catalogue contains an empty capability name",
            )
        if not isinstance(raw, Mapping):
            raise CatalogError(
                f"Model '{capability}' must be a mapping of fields",
                details={"capability": capability},
            )

        unknown = sorted(set(raw) - _ENTRY_KEYS)
        if unknown:
            raise CatalogError(
                f"Model '{capability}' has unsupported field(s): {', '.join(unknown)}",
                details={
                    "capability": capability,
                    "unsupported": unknown,
                    "supported": sorted(_ENTRY_KEYS),
                },
            )

        for key in _REQUIRED_ENTRY_KEYS:
            if key not in raw:
                raise CatalogError(
                    f"Model '{capability}' is missing required field '{key}'",
                    details={"capability": capability, "missing": key},
                )

        fallbacks_raw = raw.get("fallbacks") or ()
        if not isinstance(fallbacks_raw, (list, tuple)):
            raise CatalogError(
                f"Model '{capability}' field 'fallbacks' must be a list of capability names",
                details={"capability": capability},
            )
        fallbacks = tuple(
            _clean_string(item, field_name="fallback", entry_name=capability)
            for item in fallbacks_raw
        )
        if len(set(fallbacks)) != len(fallbacks):
            raise CatalogError(
                f"Model '{capability}' lists the same fallback more than once",
                details={"capability": capability, "fallbacks": list(fallbacks)},
            )

        enabled_raw = raw.get("enabled", True)
        if not isinstance(enabled_raw, bool):
            raise CatalogError(
                f"Model '{capability}' field 'enabled' must be true or false",
                details={"capability": capability},
            )

        alias_raw = raw.get("alias")
        alias = (
            None
            if alias_raw is None
            else _clean_string(alias_raw, field_name="alias", entry_name=capability)
        )

        return cls(
            capability=capability.strip(),
            provider=_clean_string(raw["provider"], field_name="provider", entry_name=capability),
            model=_clean_string(raw["model"], field_name="model", entry_name=capability),
            alias=alias,
            description=str(raw.get("description") or "").strip(),
            fallbacks=fallbacks,
            enabled=enabled_raw,
        )


@dataclass(frozen=True)
class ModelCatalog:
    """Validated, ordered view of every model the Gateway can route to."""

    entries: tuple[ModelEntry, ...]
    source: str = "<memory>"
    skills: tuple[Skill, ...] = ()

    def __post_init__(self) -> None:
        if not self.entries:
            raise CatalogError(
                "Model catalogue declares no models",
                details={"source": self.source},
            )
        by_capability: dict[str, ModelEntry] = {}
        for entry in self.entries:
            existing = by_capability.get(entry.capability)
            if existing is not None:
                raise CatalogError(
                    f"Model catalogue declares '{entry.capability}' twice",
                    details={"capability": entry.capability, "source": self.source},
                )
            by_capability[entry.capability] = entry

        # Two capabilities claiming one alias would be a silent misroute: LiteLLM
        # would answer both with whatever that name means, and neither row's
        # policy would describe what actually ran.
        by_alias: dict[str, str] = {}
        for entry in self.entries:
            if entry.alias is None:
                continue
            owner = by_alias.setdefault(entry.alias, entry.capability)
            if owner != entry.capability:
                raise CatalogError(
                    f"Model catalogue gives alias '{entry.alias}' to both '{owner}' "
                    f"and '{entry.capability}'",
                    details={"alias": entry.alias, "capabilities": [owner, entry.capability]},
                )

        # Dangling and self-referencing fallbacks are startup failures, not runtime surprises.
        for entry in self.entries:
            for fallback in entry.fallbacks:
                if fallback == entry.capability:
                    raise CatalogError(
                        f"Model '{entry.capability}' lists itself as a fallback",
                        details={"capability": entry.capability, "fallback": fallback},
                    )
                if fallback not in by_capability:
                    raise CatalogError(
                        f"Model '{entry.capability}' falls back to unknown capability '{fallback}'",
                        details={
                            "capability": entry.capability,
                            "fallback": fallback,
                            "known_capabilities": sorted(by_capability),
                        },
                    )

        # A skill must name a capability that exists, for the same reason a
        # fallback must: the alternative is discovering it on a live clinical request.
        by_skill: dict[str, Skill] = {}
        for skill in self.skills:
            if skill.name in by_skill:
                raise CatalogError(
                    f"Model catalogue declares skill '{skill.name}' twice",
                    details={"skill": skill.name, "source": self.source},
                )
            by_skill[skill.name] = skill
            if skill.capability not in by_capability:
                raise CatalogError(
                    f"Skill '{skill.name}' names capability '{skill.capability}', "
                    "which the catalogue does not declare",
                    details={
                        "skill": skill.name,
                        "capability": skill.capability,
                        "known_capabilities": sorted(by_capability),
                    },
                )

    @property
    def by_capability(self) -> Mapping[str, ModelEntry]:
        return {entry.capability: entry for entry in self.entries}

    @property
    def by_skill(self) -> Mapping[str, Skill]:
        return {skill.name: skill for skill in self.skills}

    @classmethod
    def load(cls, path: Path | str) -> ModelCatalog:
        """Read and validate ``models.yaml`` from disk."""
        location = Path(path)
        try:
            text = location.read_text(encoding="utf-8")
        except OSError as exc:
            raise CatalogError(
                f"Cannot read model catalogue at {location}: {exc.strerror or exc}",
                details={"path": str(location)},
            ) from exc

        try:
            document = yaml.load(text, Loader=_UniqueKeyLoader)
        except CatalogError:
            raise
        except yaml.YAMLError as exc:
            problem = getattr(exc, "problem", None) or str(exc)
            raise CatalogError(
                f"Model catalogue at {location} is not valid YAML: {problem}",
                details={"path": str(location)},
            ) from exc

        return cls.from_document(document, source=str(location))

    @classmethod
    def from_document(cls, document: Any, *, source: str = "<memory>") -> ModelCatalog:
        """Validate an already-parsed catalogue document."""
        if document is None:
            raise CatalogError(
                "Model catalogue is empty",
                details={"source": source},
            )
        if not isinstance(document, Mapping):
            raise CatalogError(
                "Model catalogue must be a YAML mapping",
                details={"source": source, "found": type(document).__name__},
            )

        unknown = sorted(set(document) - _CATALOG_KEYS)
        if unknown:
            raise CatalogError(
                f"Model catalogue has unsupported top-level key(s): {', '.join(unknown)}",
                details={
                    "source": source,
                    "unsupported": unknown,
                    "supported": sorted(_CATALOG_KEYS),
                },
            )

        raw_models = document.get("models")
        if not isinstance(raw_models, Mapping):
            raise CatalogError(
                "Model catalogue needs a 'models' mapping",
                details={"source": source, "found": type(raw_models).__name__},
            )

        raw_skills = document.get("skills")
        if raw_skills is not None and not isinstance(raw_skills, Mapping):
            raise CatalogError(
                "Model catalogue's 'skills' stanza must be a mapping",
                details={"source": source, "found": type(raw_skills).__name__},
            )

        entries = tuple(
            ModelEntry.from_raw(str(capability), raw) for capability, raw in raw_models.items()
        )
        skills = tuple(
            Skill.from_raw(str(name), raw) for name, raw in (raw_skills or {}).items()
        )
        return cls(entries=entries, source=source, skills=skills)

    def capability_names(self) -> tuple[str, ...]:
        return tuple(entry.capability for entry in self.entries)

    def enabled_entries(self) -> tuple[ModelEntry, ...]:
        return tuple(entry for entry in self.entries if entry.enabled)

    def providers_in_use(self) -> tuple[str, ...]:
        """Distinct provider names, in first-declared order."""
        seen: dict[str, None] = {}
        for entry in self.entries:
            seen.setdefault(entry.provider, None)
        return tuple(seen)

    def size(self) -> int:
        return len(self.entries)

    def require(self, capability: str) -> ModelEntry:
        """Return an entry by capability, or raise :class:`UnknownCapabilityError`."""
        entry = self.by_capability.get(capability)
        if entry is None:
            raise UnknownCapabilityError(capability, known=self.capability_names())
        return entry

    def skill_names(self) -> tuple[str, ...]:
        return tuple(skill.name for skill in self.skills)

    def enabled_skills(self) -> tuple[Skill, ...]:
        return tuple(skill for skill in self.skills if skill.enabled)

    def require_skill(self, name: str) -> Skill:
        """Return a skill by name, or raise :class:`UnknownSkillError`.

        A skill is the only selector an application may use under ``ADR-0002``,
        so this is deliberately the only outward name lookup the catalogue
        offers.  Model ids stay inside: ``catalog.resolve_selector`` existed
        only to let callers pin one, and it was deleted with that field.
        """
        skill = self.by_skill.get(name)
        if skill is None:
            raise UnknownSkillError(name, known=self.skill_names())
        return skill

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "count": self.size(),
            "capabilities": list(self.capability_names()),
            "skills": list(self.skill_names()),
            "providers": list(self.providers_in_use()),
        }


__all__ = [
    "CatalogError",
    "ModelCatalog",
    "ModelEntry",
    "Skill",
]
