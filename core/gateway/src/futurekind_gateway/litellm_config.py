"""The other side of the alias contract, read once at startup.

``ADR-0002`` gives LiteLLM the alias namespace: the Gateway sends ``fk-default``,
LiteLLM decides what runs. That promise is only real if the name the Gateway
sends exists in the list LiteLLM will accept. Until this module the Gateway held
aliases it had never checked, so a typo in either file would surface as a
``502`` in front of a clinician.

This reads ``configs/litellm/config.yaml`` — read-only, and never sent anywhere
— and answers one deployment question about the rows that route to LiteLLM:
does every alias they name exist on the other side?

Two deliberate asymmetries in how the answer is used:

* **A missing alias is fatal.** The pairing is the contract. If LiteLLM has no
  such name, every request on that capability fails, and a Gateway that starts
  anyway is a Gateway that will fail loudly at the worst possible moment. This
  is the one startup refusal in the process, next to the deliberate non-fatal
  rule in :mod:`futurekind_gateway.app` — a YAML typo degrades, a broken
  two-sided contract does not.
* **A drifted model string is a warning.** The catalogue's ``model`` is a
  statement about what the alias resolves to, for provenance and audit. When
  LiteLLM's copy disagrees, the audit line could describe the wrong weights —
  which is a reporting fault, not a routing one, since LiteLLM answers by alias
  regardless. Refusing to start over a comment in a routing table would trade a
  real outage for a paperwork mismatch.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .catalog import ModelCatalog, ModelEntry
from .errors import ConfigurationError

#: The provider name whose targets are addressed by alias and checked here.
LITELLM_PROVIDER_NAME = "litellm"


@dataclass(frozen=True)
class LiteLLMConfig:
    """The model list LiteLLM was configured with, as the Gateway sees it.

    ``targets`` maps a ``model_name`` to every ``litellm_params.model`` declared
    under it. The value is a tuple rather than a string because LiteLLM permits
    the same name to carry several deployments for load balancing; a catalogue
    row naming any one of them is not drift.
    """

    source: str
    targets: Mapping[str, tuple[str, ...]]

    def aliases(self) -> tuple[str, ...]:
        return tuple(self.targets)

    def has_alias(self, alias: str) -> bool:
        return alias in self.targets

    def targets_for(self, alias: str) -> tuple[str, ...]:
        return self.targets.get(alias, ())

    @classmethod
    def load(cls, path: Path | str) -> LiteLLMConfig:
        """Parse LiteLLM's configuration file.

        Anything unreadable, un-YAML, or missing a ``model_list`` is refused with
        :class:`ConfigurationError`: this file is the second half of the alias
        contract, so "I could not read it" must never be reported as "it matched".
        """
        location = Path(path)
        try:
            document = yaml.safe_load(location.read_text(encoding="utf-8"))
        except OSError as exc:
            raise ConfigurationError(
                f"Cannot read the LiteLLM configuration at {location}: {exc.strerror or exc}",
                details={"path": str(location)},
            ) from exc
        except yaml.YAMLError as exc:
            problem = getattr(exc, "problem", None) or str(exc)
            raise ConfigurationError(
                f"The LiteLLM configuration at {location} is not valid YAML: {problem}",
                details={"path": str(location)},
            ) from exc

        if not isinstance(document, Mapping):
            raise ConfigurationError(
                f"The LiteLLM configuration at {location} must be a YAML mapping",
                details={"path": str(location), "found": type(document).__name__},
            )

        model_list = document.get("model_list")
        if not isinstance(model_list, list) or not model_list:
            raise ConfigurationError(
                f"The LiteLLM configuration at {location} declares no model_list entries",
                details={"path": str(location)},
            )

        targets: dict[str, list[str]] = {}
        for index, item in enumerate(model_list):
            if not isinstance(item, Mapping):
                raise ConfigurationError(
                    f"model_list entry {index + 1} in {location} is not a mapping",
                    details={"path": str(location), "entry": index + 1},
                )
            name = item.get("model_name")
            if not isinstance(name, str) or not name.strip():
                raise ConfigurationError(
                    f"model_list entry {index + 1} in {location} has no model_name",
                    details={"path": str(location), "entry": index + 1},
                )
            params = item.get("litellm_params")
            target = params.get("model") if isinstance(params, Mapping) else None
            if not isinstance(target, str) or not target.strip():
                # A name without a target is a deployment LiteLLM cannot serve;
                # treating it as a match would be the same false green light.
                raise ConfigurationError(
                    f"model_name '{name.strip()}' in {location} has no litellm_params.model",
                    details={"path": str(location), "model_name": name.strip()},
                )
            targets.setdefault(name.strip(), []).append(target.strip())

        return cls(
            source=str(location),
            targets={name: tuple(values) for name, values in targets.items()},
        )


@dataclass(frozen=True)
class AliasReport:
    """What the startup comparison found, separated into the two consequences."""

    checked: int
    config_source: str
    drift: tuple[dict[str, Any], ...] = ()

    @property
    def has_drift(self) -> bool:
        return bool(self.drift)


def litellm_rows(catalog: ModelCatalog) -> tuple[ModelEntry, ...]:
    """Enabled catalogue rows this Gateway will send to LiteLLM."""
    return tuple(
        entry
        for entry in catalog.enabled_entries()
        if entry.provider == LITELLM_PROVIDER_NAME
    )


def verify_aliases(catalog: ModelCatalog, config: LiteLLMConfig) -> AliasReport:
    """Compare the aliases the Gateway will send with the names LiteLLM accepts.

    Raises :class:`ConfigurationError` naming every alias at fault. A row that
    routes to LiteLLM with no alias at all is reported the same way: without a
    name there is nothing for LiteLLM to route on, and sending the weights id
    instead would quietly put model selection back in the Gateway's hands.
    """
    rows = litellm_rows(catalog)
    missing: list[dict[str, Any]] = []
    drift: list[dict[str, Any]] = []

    for entry in rows:
        if entry.alias is None:
            missing.append(
                {
                    "capability": entry.capability,
                    "alias": None,
                    "reason": "routes to LiteLLM without declaring an alias",
                }
            )
            continue
        if not config.has_alias(entry.alias):
            missing.append(
                {
                    "capability": entry.capability,
                    "alias": entry.alias,
                    "reason": "no model_name of that name in the LiteLLM configuration",
                }
            )
            continue
        if entry.model and entry.model not in config.targets_for(entry.alias):
            drift.append(
                {
                    "capability": entry.capability,
                    "alias": entry.alias,
                    "catalogue_model": entry.model,
                    "litellm_models": list(config.targets_for(entry.alias)),
                }
            )

    if missing:
        raise ConfigurationError(
            "The model catalogue routes to LiteLLM with aliases that LiteLLM does "
            f"not recognise: {', '.join(sorted(str(item['alias']) for item in missing))}",
            details={
                "missing": missing,
                "litellm_config": config.source,
                "litellm_aliases": list(config.aliases()),
                "catalogue": catalog.source,
                "hint": (
                    "add a model_name for the alias to configs/litellm/config.yaml, or "
                    "correct the alias in the model catalogue — both files must say the "
                    "same thing before either can be deployed"
                ),
            },
        )

    return AliasReport(
        checked=len(rows),
        config_source=config.source,
        drift=tuple(drift),
    )


__all__ = [
    "LITELLM_PROVIDER_NAME",
    "AliasReport",
    "LiteLLMConfig",
    "litellm_rows",
    "verify_aliases",
]
