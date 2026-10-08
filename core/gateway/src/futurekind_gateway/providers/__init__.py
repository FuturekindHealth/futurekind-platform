"""Provider registry — the seam between routing and real backends.

Routing decides *which* provider a capability needs.  The registry decides
whether this Gateway build can actually serve it, and lazily owns one instance
per provider so connections are created on first use, not at import time.

The registry starts empty by design: ``create_app`` imports no provider, so a
test assembles exactly the backends it means to exercise and cannot accidentally
depend on a real one. The deployed process wires LiteLLM in
:func:`futurekind_gateway.main.build_production_app`. A catalogue row that names
a provider nothing answers to is still reported with a precise
``ProviderNotImplementedError`` instead of a vague failure deep in a request —
which is the difference between a missing setting and a missing feature.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterator

from ..errors import ConfigurationError, ProviderNotImplementedError
from .base import Provider

logger = logging.getLogger("futurekind.gateway.providers")

#: Anything that builds a Provider when called with no arguments.
ProviderFactory = Callable[[], Provider]


class ProviderRegistry:
    """Name -> lazily constructed provider."""

    def __init__(self) -> None:
        self._factories: dict[str, ProviderFactory] = {}
        self._instances: dict[str, Provider] = {}

    def register(
        self,
        name: str,
        factory: ProviderFactory,
        *,
        replace: bool = False,
    ) -> None:
        """Bind a provider name to a zero-argument callable.

        Registering a :class:`Provider` subclass works directly, since the class
        itself is the factory.
        """
        if not isinstance(name, str) or not name.strip():
            raise ConfigurationError(
                "Provider registration requires a non-empty name",
                details={"name": repr(name)},
            )
        normalized = name.strip()
        if not callable(factory):
            raise ConfigurationError(
                f"Provider '{normalized}' must be registered with a callable factory",
                details={"provider": normalized, "factory": type(factory).__name__},
            )
        if normalized in self._factories and not replace:
            raise ConfigurationError(
                f"Provider '{normalized}' is already registered",
                details={"provider": normalized},
            )
        self._factories[normalized] = factory
        # Any cached instance belongs to the factory being replaced.
        self._instances.pop(normalized, None)

    def unregister(self, name: str) -> None:
        """Forget a provider. Closing its instance is the caller's job via :meth:`close`."""
        self._factories.pop(name, None)
        self._instances.pop(name, None)

    def is_registered(self, name: str) -> bool:
        return name in self._factories

    def names(self) -> tuple[str, ...]:
        """Registered provider names, sorted for stable reporting."""
        return tuple(sorted(self._factories))

    def __len__(self) -> int:
        return len(self._factories)

    def __contains__(self, name: object) -> bool:
        return isinstance(name, str) and name in self._factories

    def __iter__(self) -> Iterator[str]:
        return iter(self.names())

    def get(self, name: str) -> Provider:
        """Return the provider instance for ``name``, building it on first use.

        Raises :class:`ProviderNotImplementedError` when nothing answers to that
        provider name — the expected state for every route in this skeleton.
        """
        factory = self._factories.get(name)
        if factory is None:
            raise ProviderNotImplementedError(name, registered=self.names())

        cached = self._instances.get(name)
        if cached is not None:
            return cached

        try:
            instance = factory()
        except Exception as exc:  # noqa: BLE001 - factory failure is a configuration fault
            raise ConfigurationError(
                f"Provider '{name}' failed to initialize: {exc}",
                details={"provider": name},
            ) from exc

        if not isinstance(instance, Provider):
            raise ConfigurationError(
                f"Provider '{name}' did not return a Provider instance",
                details={
                    "provider": name,
                    "returned": type(instance).__name__,
                },
            )
        declared = getattr(instance, "name", "")
        if declared and declared != name:
            raise ConfigurationError(
                f"Provider registered as '{name}' declares the name '{declared}'",
                details={"registered_as": name, "declares": declared},
            )

        self._instances[name] = instance
        return instance

    async def close(self, name: str) -> None:
        """Close one built provider, if it exists."""
        instance = self._instances.pop(name, None)
        if instance is None:
            return
        await instance.close()

    async def close_all(self) -> None:
        """Close every built provider, reporting the first failure after trying all."""
        built = dict(self._instances)
        self._instances.clear()
        errors: list[str] = []
        for name, instance in built.items():
            try:
                await instance.close()
            except Exception as exc:  # noqa: BLE001 - shutdown must always continue
                logger.warning("provider_close_failed", extra={"provider": name, "error": str(exc)})
                errors.append(f"{name}: {exc}")
        if errors:
            logger.warning("provider shutdown reported failures", extra={"failures": errors})


__all__ = ["ProviderFactory", "ProviderRegistry"]
