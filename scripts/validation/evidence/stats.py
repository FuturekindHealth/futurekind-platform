"""Statistics for paired clinical measurement, with the misuse written beside the method.

Everything in here is standard library only, and every function returns the same shape:
an estimate, an interval, a p-value where one is meaningful, the method's name, its
assumptions, and a `caution` sentence naming the way this number gets misused. The last
field is the point of the module. A team that can compute a p-value but not state what it
does not license is a team that will eventually publish a claim that fails in front of a
reviewer
(`docs/FAILURE-MODES.md` FM4, `docs/CONCEPTUAL_DEBT.md` §2.2).

Why these methods and not others:

- **Paired before anything else.** The same case read by the same clinician under two
  prompts is one observation twice, not two observations. Independent-sample tests on paired
  data inflate significance, and the temptation is real because the paired design produces
  fewer usable cases. Every comparison here takes deltas.
- **McNemar for binary endpoints.** Clinical quality is mostly binary — a hallucination
  present or absent, a block correct or not — and McNemar's exact test on discordant pairs is
  the right instrument at the small n a department can actually supply.
- **Bootstrap for everything else.** Time and edit-distance distributions are skewed and
  bounded; a normal-theory interval on 20 reports would be a fiction with two decimal
  places. Percentile bootstrap with a fixed seed is reproducible on a machine that has never
  seen the data.
- **Effect size over significance.** `p` answers "could this be noise". Nobody's patient cares
  about that question. `delta` and its interval answer "how much", and the sample-size helpers
  answer "how many cases would it take to know", which is the number a study proposal needs.

Not implemented, deliberately: Bayesian hierarchical models, mixed effects, and multiplicity
correction beyond Holm. Each would be a dependency or an assumption this repository cannot
verify, and a method nobody on the project can audit is not a method.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

Z_95 = 1.959963985
Z_99 = 2.575829304


@dataclass
class Estimate:
    """One measured quantity and the honest company it keeps."""

    quantity: str
    method: str
    n: int
    estimate: float | None = None
    ci_low: float | None = None
    ci_high: float | None = None
    p_value: float | None = None
    alpha: float = 0.05
    assumptions: tuple[str, ...] = ()
    caution: str = ""

    @property
    def significant(self) -> bool | None:
        if self.p_value is None:
            return None
        return self.p_value < self.alpha

    def as_dict(self) -> dict:
        return {
            "quantity": self.quantity,
            "method": self.method,
            "n": self.n,
            "estimate": _r(self.estimate),
            "ci": [_r(self.ci_low), _r(self.ci_high)],
            "ci_level": round(1 - self.alpha, 3),
            "p_value": _r(self.p_value, 6),
            "significant": self.significant,
            "assumptions": list(self.assumptions),
            "caution": self.caution,
        }


def _r(value: float | None, places: int = 6) -> float | None:
    return None if value is None else round(value, places)


def mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def sd(values: list[float]) -> float | None:
    if len(values) < 2:
        return None
    m = mean(values)
    return math.sqrt(sum((v - m) ** 2 for v in values) / (len(values) - 1))


def wilson_interval(successes: int, n: int, z: float = Z_95) -> tuple[float, float]:
    """Wilson score interval for a proportion — never the normal-approximation Wald one.

    Wald reports an interval touching 0 for 1 success in 10 cases, which is the kind of
    statement that gets a small study written up as "no effect observed".
    """
    if n <= 0:
        raise ValueError("wilson_interval needs n > 0")
    if not 0 <= successes <= n:
        raise ValueError("successes must be between 0 and n")
    phat = successes / n
    z2 = z * z
    denominator = 1 + z2 / n
    centre = (phat + z2 / (2 * n)) / denominator
    spread = (z / denominator) * math.sqrt(phat * (1 - phat) / n + z2 / (4 * n * n))
    return max(0.0, centre - spread), min(1.0, centre + spread)


def proportion(successes: int, n: int, alpha: float = 0.05) -> Estimate:
    z = Z_95 if abs(alpha - 0.05) < 1e-9 else _z_for(alpha)
    low, high = wilson_interval(successes, n, z)
    return Estimate(
        quantity="proportion",
        method="Wilson score interval",
        n=n,
        estimate=successes / n if n else None,
        ci_low=low,
        ci_high=high,
        assumptions=("independent Bernoulli trials", "one event per case"),
        caution=(
            "a case contributing two events is not two trials; count the case, or use a "
            "per-case rate with its own denominator"
        ),
        alpha=alpha,
    )


def _z_for(alpha: float) -> float:
    """Two-sided normal quantile for the common alphas, and an error for the rest."""
    table = {0.05: Z_95, 0.01: Z_99, 0.10: 1.644853627}
    for key, value in table.items():
        if abs(alpha - key) < 1e-9:
            return value
    raise ValueError(f"no tabled quantile for alpha={alpha}; add it explicitly rather than guess")


def binomial_two_sided(successes: int, trials: int, p: float = 0.5) -> float:
    """Exact two-sided binomial p, by the "as-or-less-probable" definition.

    Doubling the one-sided tail is the common shortcut and is wrong when the distribution is
    skewed; for McNemar and the sign test p = 0.5, so both agree — but the definition is
    stated rather than assumed, because the day someone reuses this for p != 0.5 is the day a
    silent error ships.
    """
    if trials <= 0:
        raise ValueError("binomial_two_sided needs trials > 0")
    point = math.comb(trials, successes) * p**successes * (1 - p) ** (trials - successes)
    total = 0.0
    for k in range(trials + 1):
        pk = math.comb(trials, k) * p**k * (1 - p) ** (trials - k)
        if pk <= point * (1 + 1e-12):
            total += pk
    return min(1.0, total)


def mcnemar(b: int, c: int, alpha: float = 0.05) -> Estimate:
    """Paired binary comparison from discordant counts only.

    `b` = cases where arm 1 failed and arm 2 succeeded; `c` the reverse. Concordant pairs
    carry no information about which arm is better and are excluded, which is exactly why a
    McNemar study of 100 cases may have an effective n of 12 — a fact intervals here make
    visible instead of hiding behind a percentage.
    """
    n = b + c
    if n == 0:
        return Estimate(
            quantity="paired binary difference",
            method="McNemar exact",
            n=0,
            caution="zero discordant pairs: the arms are indistinguishable, not equivalent",
            alpha=alpha,
        )
    p = binomial_two_sided(min(b, c), n)
    difference = (c - b) / n
    low, high = wilson_interval(min(b, c), n, Z_95 if abs(alpha - 0.05) < 1e-9 else _z_for(alpha))
    return Estimate(
        quantity="paired binary difference",
        method="McNemar exact (binomial on discordant pairs)",
        n=n,
        estimate=difference,
        ci_low=-high,
        ci_high=-low,
        p_value=p,
        assumptions=("paired binary outcome", "the two arms applied to the same case"),
        caution=(
            f"effective sample is the {n} discordant pairs, not the total case count; "
            "and a significant McNemar says the arms differ, not which clinical endpoint moved"
        ),
        alpha=alpha,
    )


def sign_test(deltas: list[float], alpha: float = 0.05) -> Estimate:
    nonzero = [d for d in deltas if d != 0]
    plus = sum(1 for d in nonzero if d > 0)
    minus = len(nonzero) - plus
    return Estimate(
        quantity="paired shift",
        method="exact sign test",
        n=len(nonzero),
        estimate=(plus - minus) / len(nonzero) if nonzero else None,
        p_value=binomial_two_sided(min(plus, minus), len(nonzero)) if nonzero else None,
        assumptions=("paired observations", "the sign is meaningful regardless of magnitude"),
        caution="uses only direction: it is the right test for ordinal or heavily skewed pairs, "
        "and the wrong one when magnitude is the question",
        alpha=alpha,
    )


def wilcoxon_signed_rank(deltas: list[float], alpha: float = 0.05) -> Estimate:
    """Normal-approximation Wilcoxon with tie correction and continuity correction.

    The exact distribution is not implemented: it needs either enumeration or a table, and a
    method whose table nobody on the project can check is not a method. With the continuity
    correction the approximation is conservative at n >= 10, which is stated rather than
    assumed — below that, use the sign test.
    """
    nonzero = [d for d in deltas if d != 0]
    n = len(nonzero)
    if n < 10:
        return Estimate(
            quantity="paired shift",
            method="Wilcoxon signed rank (normal approximation)",
            n=n,
            caution=f"n={n} is below the approximation's floor of 10; use sign_test instead",
            alpha=alpha,
        )
    order = sorted(range(len(nonzero)), key=lambda i: abs(nonzero[i]))
    ranks = [0.0] * n
    i = 0
    ties = 0.0
    while i < n:
        j = i
        while j + 1 < n and abs(nonzero[order[j + 1]]) == abs(nonzero[order[i]]):
            j += 1
        average_rank = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[order[k]] = average_rank
        span = j - i + 1
        if span > 1:
            ties += (span**3 - span) / 12
        i = j + 1
    w_plus = sum(r for r, d in zip(ranks, nonzero, strict=True) if d > 0)
    mean_w = n * (n + 1) / 4
    var_w = n * (n + 1) * (2 * n + 1) / 24 - ties / 4
    if var_w <= 0:
        return Estimate(
            quantity="paired shift",
            method="Wilcoxon signed rank",
            n=n,
            caution="all pairs tied: no information in either direction",
            alpha=alpha,
        )
    z = (abs(w_plus - mean_w) - 0.5) / math.sqrt(var_w)
    p = math.erfc(z / math.sqrt(2))
    return Estimate(
        quantity="paired shift",
        method="Wilcoxon signed rank (normal approximation, tie+continuity corrected)",
        n=n,
        estimate=w_plus,
        p_value=p,
        assumptions=("paired, symmetric-ish distribution of nonzero differences", "n >= 10"),
        caution="no interval is reported because the estimator is a rank sum, not a location: "
        "quote the Hodges-Lehmann shift if a magnitude is needed",
        alpha=alpha,
    )


def paired_mean_diff(deltas: list[float], alpha: float = 0.05) -> Estimate:
    m = mean(deltas)
    s = sd(deltas)
    n = len(deltas)
    if m is None or s is None:
        return Estimate(
            quantity="paired mean difference",
            method="t interval",
            n=n,
            caution="fewer than two paired observations",
            alpha=alpha,
        )
    se = s / math.sqrt(n)
    return Estimate(
        quantity="paired mean difference",
        method="normal-approximation t interval",
        n=n,
        estimate=m,
        ci_low=m - Z_95 * se,
        ci_high=m + Z_95 * se,
        p_value=math.erfc(abs(m / se) / math.sqrt(2)),
        assumptions=("differences approximately normal, or n large enough for the CLT",),
        caution="on 20 skewed time measurements this interval is a guess; use bootstrap_paired",
        alpha=alpha,
    )


def bootstrap_paired(
    deltas: list[float],
    statistic=mean,
    n_resamples: int = 20000,
    seed: int = 20261009,
    alpha: float = 0.05,
) -> Estimate:
    """Percentile bootstrap. Fixed seed, so the number in the report is the number in the test.

    Resampling is the honest choice for time and edit-distance data: skewed, bounded, small,
    and nobody is going to defend a normal assumption about it in front of a reviewer.
    """
    n = len(deltas)
    if n < 2:
        return Estimate(
            quantity="bootstrapped statistic",
            method="percentile bootstrap",
            n=n,
            caution="needs at least two observations",
            alpha=alpha,
        )
    rng = random.Random(seed)
    values = []
    for _ in range(n_resamples):
        sample = [deltas[rng.randrange(n)] for _ in range(n)]
        values.append(statistic(sample))
    values.sort()
    lo = values[max(0, int((alpha / 2) * n_resamples))]
    hi = values[min(n_resamples - 1, int((1 - alpha / 2) * n_resamples))]
    return Estimate(
        quantity="bootstrapped statistic",
        method=f"percentile bootstrap ({n_resamples} resamples, seed {seed})",
        n=n,
        estimate=statistic(deltas),
        ci_low=lo,
        ci_high=hi,
        assumptions=(
            "the observations are independent between cases",
            "the statistic is not degenerate",
        ),
        caution="bootstrap intervals on a paired design still require the pairing to be real: "
        "resample cases, never measurements inside a case",
        alpha=alpha,
    )


def cohens_d(deltas: list[float]) -> Estimate:
    m = mean(deltas)
    s = sd(deltas)
    n = len(deltas)
    if m is None or s is None or s == 0:
        return Estimate(
            quantity="standardised paired effect",
            method="Cohen's d (paired)",
            n=n,
            caution="no spread to standardise against",
            alpha=0.05,
        )
    d = m / s
    # The method name promises the small-sample correction, so the number must carry it:
    # an uncorrected d on a 20-case pilot is biased upward by about 3%.
    correction = 1 - 3 / (4 * (n - 1) - 1)
    half = Z_95 * math.sqrt((1 / n) + d**2 / (2 * (n - 1)))
    return Estimate(
        quantity="standardised paired effect",
        method="Cohen's d (paired), Hedges' g small-sample corrected",
        n=n,
        estimate=d * correction,
        ci_low=(d - half) * correction,
        ci_high=(d + half) * correction,
        assumptions=("interval-scale differences",),
        caution="a standardised effect on an uncalibrated scale is comparable only inside this "
        "instrument; it does not license 'large effect' language to a journal",
        alpha=0.05,
    )


def mde_paired(n: int, alpha: float = 0.05, power: float = 0.8) -> Estimate:
    """Smallest standardised paired effect this many cases could detect.

    The question a study should ask before it collects a single case, because "we found no
    difference" from an underpowered sample is the most expensive sentence in clinical
    software: it is read as evidence of safety. `d = (z_alpha + z_beta) / sqrt(n)`, so n
    needs to quadruple to halve the smallest detectable effect — the fact that makes
    single-centre before-and-after studies the wrong tool for small quality changes.
    """
    if n < 2:
        return Estimate(
            quantity="minimum detectable standardised effect",
            method="paired normal",
            n=n,
            caution="needs n >= 2",
            alpha=alpha,
        )
    z_alpha = Z_95 if abs(alpha - 0.05) < 1e-9 else _z_for(alpha)
    z_beta = _z_for_power(power)
    return Estimate(
        quantity="minimum detectable standardised effect",
        method="paired normal approximation",
        n=n,
        estimate=round((z_alpha + z_beta) / math.sqrt(n), 4),
        assumptions=("differences roughly normal", "two-sided test", f"power {power}"),
        caution="below this effect size the study will report 'no difference' as a finding",
        alpha=alpha,
    )


def _z_for_power(power: float) -> float:
    table = {0.8: 0.841621234, 0.9: 1.281551566, 0.95: 1.644853627, 0.99: 2.326347874}
    for key, value in table.items():
        if abs(power - key) < 1e-9:
            return value
    raise ValueError(f"no tabled quantile for power={power}; choose 0.8, 0.9, 0.95 or 0.99")


def sample_size_for_mcnemar(
    discordant_rate: float, expected_difference: float, alpha: float = 0.05, power: float = 0.8
) -> Estimate:
    """Cases needed, given how often the two arms disagree at all.

    `discordant_rate` is the share of cases where the arms differ (they usually agree, and
    agreement is what makes these studies need more cases than anyone expects).
    `expected_difference` is the paired proportion difference worth detecting.
    """
    if not 0 < discordant_rate <= 1:
        raise ValueError("discordant_rate must be in (0, 1]")
    if expected_difference <= 0 or expected_difference > discordant_rate:
        raise ValueError("expected_difference must be positive and no larger than the discordance")
    z_alpha = Z_95 if abs(alpha - 0.05) < 1e-9 else _z_for(alpha)
    z_beta = 0.841621234 if abs(power - 0.8) < 1e-9 else 1.281551566
    n_pairs = (z_alpha + z_beta) ** 2 / expected_difference**2
    n_cases = n_pairs / discordant_rate
    return Estimate(
        quantity="cases required",
        method="McNemar sample size (pair-based)",
        n=int(math.ceil(n_cases)),
        estimate=round(n_cases, 1),
        assumptions=(
            f"discordant pairs occur at {discordant_rate:.0%} of cases",
            f"power {power} at alpha {alpha}",
        ),
        caution="the discordance rate is itself an estimate; a study sized on a guess here is "
        "a guess with a bigger budget",
        alpha=alpha,
    )


def holm(p_values: list[tuple[str, float]], alpha: float = 0.05) -> list[dict]:
    """Holm-Bonferroni step-down. The one multiplicity method with no assumptions to audit.

    Ordered because the honest failure of a measurement programme is not a wrong p-value but
    twenty right ones, of which the interesting two get quoted.
    """
    ordered = sorted(p_values, key=lambda item: item[1])
    m = len(ordered)
    out: list[dict] = []
    running_minimum = 1.0
    for rank, (name, p) in enumerate(ordered):
        threshold = alpha / (m - rank)
        adjusted = min(1.0, p * (m - rank))
        running_minimum = min(running_minimum, adjusted)
        out.append(
            {
                "name": name,
                "p": round(p, 6),
                "holm_threshold": round(threshold, 6),
                "adjusted": round(running_minimum, 6),
                "reject": running_minimum <= alpha,
            }
        )
    return out


@dataclass
class Preregistration:
    """What was decided before the data, and therefore what the data can actually show.

    Not bureaucracy: the alternative is a study whose conclusion depends on which of six
    analyses was run last (`docs/FAILURE-MODES.md` FM8, and the ranking block in
    `scripts/validation/run-cases.py`, written the same way for the same reason).
    """

    question: str
    primary_endpoint: str
    comparison: str
    unit_of_analysis: str
    n_planned: int
    alpha: float
    power: float
    analysis: str
    secondary: tuple[str, ...] = ()
    exclusions: tuple[str, ...] = ()
    signed_by: str = ""

    def violations(self) -> list[str]:
        problems: list[str] = []
        if not self.signed_by:
            problems.append(
                "no owner: an unsigned pre-registration is a draft, and drafts get changed"
            )
        if self.n_planned <= 0:
            problems.append("n_planned must be a number the study can actually reach")
        if not self.primary_endpoint:
            problems.append("a primary endpoint must be named before, not after")
        if self.alpha not in (0.01, 0.05, 0.10):
            problems.append("alpha must be one of the tabled values, chosen in advance")
        return problems

    def as_dict(self) -> dict:
        return {
            "question": self.question,
            "primary_endpoint": self.primary_endpoint,
            "comparison": self.comparison,
            "unit_of_analysis": self.unit_of_analysis,
            "n_planned": self.n_planned,
            "alpha": self.alpha,
            "power": self.power,
            "analysis": self.analysis,
            "secondary": list(self.secondary),
            "exclusions": list(self.exclusions),
            "signed_by": self.signed_by,
        }
