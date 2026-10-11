"""How the advantage over a baseline is measured and reported.

Two measures, always reported together (spec A7):

* **Median advantage** compares median after-tax wealth at the horizon.
* **Risk-adjusted advantage** compares certainty-equivalent wealth (the planner's own objective:
  CRRA utility, so a plan is penalized for a fat lower tail).

Each is annualized as a growth-rate difference: the constant yearly rate by which the plan's
wealth would have to outgrow the baseline's to open the observed gap over the horizon,

    advantage = (W_plan / W_baseline) ** (1 / years) - 1.

This is the difference of the two compound growth rates, to first order (it does not depend on
today's wealth). It is a statement about the whole household's wealth path, which includes
savings and spending, not about investment return alone.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from app.planner.search import RISK_AVERSION, WEALTH_FLOOR, certainty_equivalent


def annualized(plan: float, baseline: float, years: int) -> float:
    """Yearly growth-rate difference that turns `baseline` into `plan` over `years`."""
    if years <= 0 or plan <= 0.0 or baseline <= 0.0:
        return 0.0
    return float((plan / baseline) ** (1.0 / years) - 1.0)


@dataclass(frozen=True)
class Advantage:
    """A plan against one baseline on the same futures."""

    median: float  # annualized, from median after-tax wealth
    risk_adjusted: float  # annualized, from certainty-equivalent wealth
    median_dollars: float  # plan median minus baseline median at the horizon
    risk_adjusted_dollars: float  # plan CE minus baseline CE at the horizon
    plan_median: float
    baseline_median: float
    plan_ce: float
    baseline_ce: float
    years: int
    # 90% range of the two annualized measures when the futures are resampled (paired bootstrap)
    median_range: tuple[float, float] = (0.0, 0.0)
    risk_adjusted_range: tuple[float, float] = (0.0, 0.0)


def compare(
    plan_wealth: np.ndarray,
    baseline_wealth: np.ndarray,
    years: int,
    risk_aversion: float = RISK_AVERSION,
    floor: float = WEALTH_FLOOR,
    with_range: bool = False,
) -> Advantage:
    """Both advantage measures for `plan_wealth` against `baseline_wealth` (same futures, same order)."""
    plan_median = float(np.median(plan_wealth))
    base_median = float(np.median(baseline_wealth))
    plan_ce = float(certainty_equivalent(plan_wealth, risk_aversion, floor))
    base_ce = float(certainty_equivalent(baseline_wealth, risk_aversion, floor))
    ranges = bootstrap_range(plan_wealth, baseline_wealth, years, risk_aversion, floor) if with_range else ((0.0, 0.0), (0.0, 0.0))
    return Advantage(
        median=annualized(plan_median, base_median, years),
        risk_adjusted=annualized(plan_ce, base_ce, years),
        median_dollars=plan_median - base_median,
        risk_adjusted_dollars=plan_ce - base_ce,
        plan_median=plan_median,
        baseline_median=base_median,
        plan_ce=plan_ce,
        baseline_ce=base_ce,
        years=years,
        median_range=ranges[0],
        risk_adjusted_range=ranges[1],
    )


def bootstrap_range(
    plan_wealth: np.ndarray,
    baseline_wealth: np.ndarray,
    years: int,
    risk_aversion: float = RISK_AVERSION,
    floor: float = WEALTH_FLOOR,
    n_boot: int = 300,
    seed: int = 0,
) -> tuple[tuple[float, float], tuple[float, float]]:
    """5th-95th percentile of both annualized advantages over resamples of the futures.

    The same resampled futures are used for the plan and the baseline (they were simulated on common
    random numbers), so this is the uncertainty in the difference, not in either wealth alone.
    """
    n = len(plan_wealth)
    idx = np.random.default_rng(seed).integers(0, n, size=(n_boot, n))
    plan, base = plan_wealth[idx], baseline_wealth[idx]
    med_p, med_b = np.median(plan, axis=1), np.median(base, axis=1)
    ce_p = certainty_equivalent(plan, risk_aversion, floor)
    ce_b = certainty_equivalent(base, risk_aversion, floor)
    medians = np.array([annualized(a, b, years) for a, b in zip(med_p, med_b, strict=True)])
    ces = np.array([annualized(a, b, years) for a, b in zip(ce_p, ce_b, strict=True)])
    m_lo, m_hi = np.percentile(medians, [5, 95])
    c_lo, c_hi = np.percentile(ces, [5, 95])
    return (float(m_lo), float(m_hi)), (float(c_lo), float(c_hi))
