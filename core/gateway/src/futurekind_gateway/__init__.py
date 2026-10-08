"""FutureKind Gateway.

The single entry point for every AI request in the FutureKind platform.

Applications name a *skill* — what the clinician is doing (``radiology-report``,
``clinical-chat``, ``summarize-document``, ``pathology-review``).  The Gateway
loads that skill's policy from ``models.yaml``, resolves it to a capability and
then to a model, and invokes the provider through the
:class:`~futurekind_gateway.providers.base.Provider` abstraction.

Applications never choose infrastructure and never choose policy.  Both are the
operator's, written in ``core/gateway/models.yaml`` and enforced here.  See
``docs/ARCHITECTURE.md``, ``core/gateway/README-ROUTING.md``,
``docs/architecture/gateway-routing.md`` and
``docs/architecture/gateway-policy.md``.

This package is the Gateway skeleton: configuration, model catalogue, policy
layer, routing, the provider contract, the HTTP surface and observability.  No
concrete providers are implemented yet, so ``POST /chat`` resolves its route,
enforces the skill's policy, and then returns ``501 provider_not_implemented``
naming the provider that still needs an implementation.
"""

__version__ = "0.1.0"

__all__ = ["__version__"]
