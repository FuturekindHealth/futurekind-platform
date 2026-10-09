"""A/B testing for a clinical system, where the unit of comparison is a case.

Part 8. Three things make this harder than the web version, and the module is shaped around
them:

**The unit is the case, not the click.** Cases arrive in batches, by modality, to different
reporters, and a change that helps on normal CTs can harm on medicolegal MRIs. Assignment is
therefore by *case reference* and analysis reports every stratification the corpus can
support. A study that averages over 40 normal ultrasounds and 4 emergency CTAs is a study of
whatever the mixture was, not of the prompt.

**Carry-over is real.** The same radiologist reading the same case under two prompts is a
paired design, and the second reading is not independent of the first: they now know what the
tool tends to say. That makes the crossover the *right* design for measuring effort and the
*wrong* one for measuring detection of a rare error, where learning from arm A contaminates
arm B. Both are provided, and each states what it cannot show.

**Order is a variable.** Half the cases get A first, half get B first (Williams-style for two
arms), so a systematic difference between first and second reading cancels instead of hiding
inside the effect.

The platform's own constraint, restated because it is the one rule an experiment cannot
negotiate: an experiment changes what runs *behind an alias*, in operator-owned
configuration. No clinical request ever names an arm, a prompt or a model
(`docs/adr/ADR-0002-Gateway-vs-LiteLLM.md` rule 1, `docs/INVARIANTS.md` N1). A/B here is a
deployment decision with a measurement attached, not a caller-side switch.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any

from . import stats
from .stats import Preregistration

#: Two arms, order balanced across cases. For more than two arms use `williams_order`.
ARMS = ("A", "B")


def allocate(
    case_refs: Sequence[str], arms: Sequence[str] = ARMS, seed: str = "fk-experiment"
) -> dict[str, str]:
    """Deterministic, balanced, ungameable assignment.

    Hash-based rather than random so that re-running with the same case list reproduces the
    same allocation — which is what lets a published study be checked by a stranger. Balance
    is enforced by assigning each case to the least-filled arm among the hash-ordered
    candidates, so nobody can choose a `seed` to get a favourable case mix; the seed is
    published, and the mix is reported afterwards rather than tuned.
    """
    if len(arms) < 2:
        raise ValueError("an experiment needs at least two arms")
    counts = dict.fromkeys(arms, 0)
    assignment: dict[str, str] = {}
    for ref in sorted(
        case_refs, key=lambda item: hashlib.sha256(f"{seed}:{item}".encode()).hexdigest()
    ):
        chosen = min(
            arms,
            key=lambda arm: (
                counts[arm],
                hashlib.sha256(f"{seed}:{ref}:{arm}".encode()).hexdigest(),
            ),
        )
        assignment[ref] = chosen
        counts[chosen] += 1
    return assignment


def crossover_order(
    case_refs: Sequence[str], seed: str = "fk-crossover"
) -> list[tuple[str, tuple[str, ...]]]:
    """Each case in each arm, with the order of arms balanced across cases.

    Without the balancing, "arm B looked better" and "arm B was usually read second" are the
    same sentence, and there is no way to tell them apart after the fact.

    The offset that decides which order comes first is derived from the *seed*, once, and then
    order alternates by case index. Per-case hashing would look more random and would not be
    balanced: with 20 cases it produced 9/11, which is exactly the imbalance a reader would
    later attribute to the intervention.
    """
    orders = [tuple(ARMS), tuple(reversed(ARMS))]
    offset = int(hashlib.sha256(seed.encode()).hexdigest()[:8], 16) % 2
    return [(ref, orders[(index + offset) % 2]) for index, ref in enumerate(sorted(case_refs))]


@dataclass
class Experiment:
    identifier: str
    question: str
    arm_a_label: str
    arm_b_label: str
    unit: str
    endpoints: tuple[str, ...]
    prereg: Preregistration
    rows: list[dict] = field(default_factory=list)

    def _pairs(self, endpoint: str) -> list[tuple[float, float]]:
        pairs: list[tuple[float, float]] = []
        for row in self.rows:
            arms = row.get("arms", {})
            value_a = arms.get(self.arm_a_label, {}).get(endpoint)
            value_b = arms.get(self.arm_b_label, {}).get(endpoint)
            if isinstance(value_a, (int, float)) and isinstance(value_b, (int, float)):
                pairs.append((float(value_a), float(value_b)))
        return pairs

    def analyse(self, binary: Iterable[str], continuous: Iterable[str]) -> dict[str, Any]:
        """Refuse to analyse an unregistered study, then run the registered tests.

        The refusal is the feature. An experiment with no pre-registered primary endpoint can
        always be made to show something afterwards, and a measurement programme whose outputs
        are always positive has stopped measuring
        (`docs/FAILURE-MODES.md` FM8, `docs/CONSTITUTION.md` CB7).
        """
        problems = self.prereg.violations()
        if problems:
            return {
                "experiment": self.identifier,
                "analysed": False,
                "reason": "pre-registration incomplete",
                "problems": problems,
            }
        results: dict[str, Any] = {"experiment": self.identifier, "analysed": True, "endpoints": {}}
        for endpoint in binary:
            pairs = self._pairs(endpoint)
            b = sum(1 for a, value in pairs if value > a)
            c = sum(1 for a, value in pairs if value < a)
            estimate = stats.mcnemar(b, c)
            results["endpoints"][endpoint] = {
                **estimate.as_dict(),
                "type": "binary paired",
                "discordant": b + c,
                "primary": endpoint == self.prereg.primary_endpoint,
            }
        for endpoint in continuous:
            deltas = [value_b - value_a for value_a, value_b in self._pairs(endpoint)]
            if len(deltas) >= 10:
                estimate: Any = stats.wilcoxon_signed_rank(deltas)
                secondary = stats.bootstrap_paired(deltas)
                estimate.ci_low, estimate.ci_high = secondary.ci_low, secondary.ci_high
            else:
                estimate = stats.bootstrap_paired(deltas)
            results["endpoints"][endpoint] = {
                **estimate.as_dict(),
                "type": "continuous paired",
                "primary": endpoint == self.prereg.primary_endpoint,
            }
        unregistered = [
            endpoint
            for endpoint in results["endpoints"]
            if endpoint not in self.prereg.secondary and endpoint != self.prereg.primary_endpoint
        ]
        if unregistered:
            results["multiplicity_warning"] = {
                "endpoints_analysed_beyond_the_registration": unregistered,
                "adjustment": stats.holm(
                    [
                        (name, value["p_value"])
                        for name, value in results["endpoints"].items()
                        if value.get("p_value") is not None
                    ]
                ),
                "note": "hypothesis-generating, and must be labelled that way in any write-up",
            }
        return results


def arm_summary(rows: list[dict], arm_a: str, arm_b: str, key: str) -> dict[str, Any]:
    """Case mix beside the outcome, because the two are read together or not at all."""

    def share(arm: str) -> float | None:
        values = [row.get("arms", {}).get(arm, {}).get(key) for row in rows]
        usable = [float(value) for value in values if isinstance(value, (int, float))]
        return round(sum(usable) / len(usable), 4) if usable else None

    return {
        "attribute": key,
        arm_a: share(arm_a),
        arm_b: share(arm_b),
        "caution": "an imbalance here is a stratified-analysis requirement, not a rounding error",
    }
