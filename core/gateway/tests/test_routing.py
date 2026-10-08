"""Unit tests for skill and capability routing."""

from __future__ import annotations

import inspect

import pytest

from futurekind_gateway.catalog import ModelCatalog
from futurekind_gateway.errors import (
    RoutingError,
    UnknownCapabilityError,
    UnknownSkillError,
)
from futurekind_gateway.policy import DEFAULT_POLICY
from futurekind_gateway.routing import MAX_CHAIN_LENGTH, ModelRouter, Route
from tests.conftest import make_catalog, make_policy_catalog


def router_for(document: dict | None = None, *, default: str = "default") -> ModelRouter:
    catalog = make_catalog(document) if document is not None else make_catalog()
    return ModelRouter(catalog, default_capability=default)


# -- selection ---------------------------------------------------------------------------------


def test_no_selector_routes_to_the_configured_default() -> None:
    router = router_for()
    route = router.resolve()

    assert route.capability == "default"
    assert route.model == "fake-large"
    assert route.selected_by == "default"


def test_default_capability_can_be_reconfigured_without_touching_the_catalogue() -> None:
    route = router_for(default="fast").resolve()

    assert route.capability == "fast"
    assert route.selected_by == "default"


def test_capability_selector_returns_that_capability() -> None:
    route = router_for().resolve(capability="reasoning")

    assert route.provider == "fake"
    assert route.model == "fake-thinker"
    assert route.selected_by == "capability"


def test_a_skill_resolves_to_the_capability_it_declares() -> None:
    route = router_for().resolve(skill="clinical-chat")

    assert route.capability == "default"
    assert route.skill == "clinical-chat"
    assert route.selected_by == "skill"


def test_a_skill_selects_by_intent_not_by_processing_class() -> None:
    """The application states intent; which capability class serves it is internal."""
    router = router_for()

    assert router.resolve(skill="clinical-chat").model == "fake-large"
    assert router.resolve(skill="summarize-document").model == "fake-small"


def test_an_agreeing_skill_and_capability_pair_is_accepted() -> None:
    route = router_for().resolve(skill="clinical-chat", capability="default")

    assert route.capability == "default"
    assert route.selected_by == "skill"


def test_a_conflicting_skill_and_capability_pair_is_refused() -> None:
    """Silently honouring one of two contradictory selectors is how misrouting hides."""
    with pytest.raises(RoutingError, match="not the requested 'reasoning'"):
        router_for().resolve(skill="summarize-document", capability="reasoning")


def test_a_disabled_skill_is_refused() -> None:
    with pytest.raises(RoutingError, match="Skill 'retired-skill' is disabled"):
        router_for().resolve(skill="retired-skill")


def test_an_unknown_skill_is_a_404_and_is_not_treated_as_a_capability() -> None:
    with pytest.raises(UnknownSkillError):
        router_for().resolve(skill="clinical-chat-typo")


def test_a_model_id_is_not_a_routable_selector() -> None:
    """The deleted model selector must not stay reachable through routing."""
    with pytest.raises(UnknownSkillError):
        router_for().resolve(skill="fake-small")


def test_routing_never_accepts_a_model_keyword_argument() -> None:
    """An ADR-0002 guard: re-adding model pinning would have to edit this test."""
    parameters = inspect.signature(router_for().resolve).parameters

    assert "model" not in parameters
    assert set(parameters) == {"skill", "capability"}


def test_unknown_capability_is_a_404_not_a_fallback_to_default() -> None:
    router = router_for()
    with pytest.raises(UnknownCapabilityError):
        router.resolve(capability="vision")


def test_disabled_capability_cannot_be_routed_to() -> None:
    with pytest.raises(RoutingError, match="disabled"):
        router_for().resolve(capability="retired")


def test_a_disabled_default_capability_is_refused() -> None:
    document = {
        "models": {
            "default": {"provider": "p", "model": "m", "enabled": False},
            "backup": {"provider": "p", "model": "b"},
        }
    }
    with pytest.raises(RoutingError, match="disabled"):
        router_for(document, default="default").resolve()


# -- fallback chains ---------------------------------------------------------------------------


def test_chain_orders_primary_first_then_fallbacks() -> None:
    route = router_for().resolve(capability="reasoning")

    assert route.candidate_capabilities() == ("reasoning", "fast", "default")
    assert route.has_fallbacks is True


def test_chain_is_transitive_and_deduplicated() -> None:
    document = {
        "models": {
            "top": {"provider": "p", "model": "t", "fallbacks": ["left", "right"]},
            "left": {"provider": "p", "model": "l", "fallbacks": ["shared"]},
            "right": {"provider": "p", "model": "r", "fallbacks": ["shared"]},
            "shared": {"provider": "p", "model": "s"},
        }
    }
    route = router_for(document, default="top").resolve()

    assert route.candidate_capabilities() == ("top", "left", "right", "shared")


def test_a_fallback_cycle_terminates_instead_of_looping() -> None:
    """Mutual fallbacks are legal at load time, so the chain must be cycle-safe."""
    document = {
        "models": {
            "a": {"provider": "p", "model": "a", "fallbacks": ["b"]},
            "b": {"provider": "p", "model": "b", "fallbacks": ["a"]},
        }
    }
    route = router_for(document, default="a").resolve()

    assert route.candidate_capabilities() == ("a", "b")


def test_disabled_entries_are_skipped_in_a_chain() -> None:
    document = {
        "models": {
            "primary": {"provider": "p", "model": "p", "fallbacks": ["gone", "usable"]},
            "gone": {"provider": "p", "model": "g", "enabled": False},
            "usable": {"provider": "p", "model": "u"},
        }
    }
    route = router_for(document, default="primary").resolve()

    assert route.candidate_capabilities() == ("primary", "usable")


def test_chain_length_is_capped_even_in_a_dense_graph() -> None:
    names = [f"m{index}" for index in range(MAX_CHAIN_LENGTH + 6)]
    raw = {}
    for position, name in enumerate(names):
        raw[name] = {
            "provider": "p",
            "model": name,
            "fallbacks": names[position + 1 : position + 3],
        }
    route = router_for({"models": raw}, default=names[0]).resolve()

    assert len(route.candidates) == MAX_CHAIN_LENGTH


def test_a_primary_entry_with_no_enabled_candidates_is_refused() -> None:
    document = {
        "models": {
            "only": {"provider": "p", "model": "o", "fallbacks": ["off"]},
            "off": {"provider": "p", "model": "x", "enabled": False},
        }
    }
    # The primary is enabled, so it is itself a candidate: the chain is non-empty.
    route = router_for(document, default="only").resolve()
    assert route.candidate_capabilities() == ("only",)


# -- policy on the route -----------------------------------------------------------------------


def test_a_route_carries_the_policy_of_the_skill_that_selected_it() -> None:
    """The policy travels with the route so no downstream layer re-derives it."""
    route = ModelRouter(make_policy_catalog(), default_capability="default").resolve(
        skill="radiology-report"
    )

    assert route.policy.clinical_risk == "high"
    assert route.policy.allow_downgrade is False


def test_a_request_that_names_no_skill_gets_the_default_policy() -> None:
    route = ModelRouter(make_policy_catalog(), default_capability="default").resolve()

    assert route.policy is DEFAULT_POLICY
    assert route.policy.clinical_risk == "unspecified"


def test_a_policy_that_forbids_downgrade_gets_a_chain_of_one() -> None:
    """`reasoning` falls back to `fast` in this catalogue; the policy must be able to stop it."""
    router = ModelRouter(make_policy_catalog(), default_capability="default")

    assert router.resolve(skill="radiology-report").candidate_capabilities() == ("reasoning",)
    assert router.resolve(skill="radiology-report").has_fallbacks is False
    # The same capability reached by name, with no policy to narrow it, still walks.
    assert router.resolve(capability="reasoning").candidate_capabilities() == (
        "reasoning",
        "fast",
        "default",
    )


def test_a_forbidden_downgrade_is_narrowed_at_the_chain_not_hidden_from_the_response() -> None:
    """The lesser models stay listed for operators; only this route cannot use them."""
    router = ModelRouter(make_policy_catalog(), default_capability="default")

    assert [route.capability for route in router.routes()] == ["default", "fast", "reasoning"]
    assert router.resolve(skill="radiology-report").chain[0].capability == "reasoning"


def test_a_route_reports_the_alias_it_was_routed_to() -> None:
    route = ModelRouter(make_policy_catalog(), default_capability="default").resolve(
        skill="radiology-report"
    )

    assert route.alias == "fk-reasoning"


def test_a_route_without_a_declared_alias_reports_none() -> None:
    """An alias no operator wrote must not be invented by the router."""
    catalog = make_catalog({"models": {"fast": {"provider": "p", "model": "m"}}})

    assert ModelRouter(catalog, default_capability="fast").resolve().alias is None
    # And where one is written, it is the row's own name, not the capability's.
    assert ModelRouter(make_policy_catalog(), default_capability="default").resolve(
        capability="fast"
    ).alias == "fk-fast"


def test_build_chain_defaults_to_allowing_downgrade() -> None:
    """`routes()` describes capabilities, which have no policy of their own."""
    catalog = make_policy_catalog()
    router = ModelRouter(catalog, default_capability="default")

    assert len(router.build_chain(catalog.require("reasoning"))) == 3


# -- reporting ---------------------------------------------------------------------------------


def test_routes_iterates_enabled_capabilities_only() -> None:
    router = router_for()

    assert [route.capability for route in router.routes()] == ["default", "fast", "reasoning"]


def test_describe_exposes_chains_for_operators() -> None:
    described = router_for().describe()

    reasoning = next(item for item in described if item["capability"] == "reasoning")
    assert reasoning["chain"] == ["reasoning", "fast", "default"]
    assert reasoning["provider"] == "fake"


def test_missing_providers_names_catalogue_providers_with_no_implementation() -> None:
    router = router_for()

    assert router.missing_providers(()) == ["fake"]
    assert router.missing_providers(("fake", "other")) == []


def test_route_reports_the_provider_and_model_it_resolved() -> None:
    catalog = make_catalog()
    entry = catalog.require("fast")
    route = Route(capability="fast", entry=entry, chain=(entry,), selected_by="capability")

    assert route.provider == "fake"
    assert route.model == "fake-small"
    assert route.to_public_dict()["chain"] == ["fast"]


def test_router_exposes_the_catalogue_it_was_built_from() -> None:
    router = router_for()

    assert isinstance(router.catalog, ModelCatalog)
    assert router.default_capability == "default"
