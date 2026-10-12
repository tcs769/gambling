"""The waterfall from the advisor's plan to Donabach's: one bar per strategy, switched on in sequence on the same futures.

Start from the good RIA's policy. Each strategy of the chosen plan is a change to the policy (the fee, asset location, the order
tax lots are sold in, ...). With the strategies a person has left on, apply them in order and run every cumulative policy on the
same simulated futures: a bar is what its strategy added to median after-tax wealth at the horizon, in dollars and as a rate a
year. The bars sum to the total, and switching one off re-runs the chain without it, so the others' bars change where the
strategies interact (a private credit sleeve needs asset location, a reserve needs the stocks it holds back).

The chain with everything on ends exactly on the chosen strategy's own policy.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

from app.planner.baseline import RIA_BASELINE
from app.planner.strategies import DONABACH_FLAT_FEE, GLIDE_START_AGE, Strategy
from app.sim.simulate import Policy, SimInputs, run_batch
from app.study import metrics


@dataclass(frozen=True)
class WaterfallStrategy:
    key: str
    label: str
    detail: str
    change: Callable[[Policy], Policy]


def _bracket(strategy: Strategy) -> str:
    return f"{strategy.conversion_bracket}%"


def waterfall_strategies(strategy: Strategy, baseline: Policy = RIA_BASELINE) -> list[WaterfallStrategy]:
    """The strategies of `strategy`'s plan that differ from the advisor's, in the order they are switched on."""
    chosen = strategy.policy()
    candidates = [
        WaterfallStrategy(
            "fee",
            "Lower, flat fee",
            "A flat 0.35% a year instead of the advisor's 1.0% falling to 0.5% as the balance grows.",
            lambda p: p.replace(breakpoint_fees=False, flat_fee=DONABACH_FLAT_FEE),
        ),
        WaterfallStrategy(
            "location",
            "Asset location",
            "Bonds and private credit sit in the pre-tax account first, stocks in the Roth and taxable accounts, so the most heavily taxed holdings are in the accounts that shelter them.",
            lambda p: p.replace(donabach_location=True),
        ),
        WaterfallStrategy(
            "lots",
            "Highest-cost lots first",
            "When stock is sold in the taxable account, sell the shares that cost the most first, so the least gain is realized (the advisor sells the oldest shares first). "
            "Gifts to charity are made with the shares that have gained the most, not with cash.",
            lambda p: p.replace(
                lot_method=chosen.lot_method, short_term_ordinary=chosen.short_term_ordinary, donate_lots=chosen.donate_lots
            ),
        ),
        WaterfallStrategy(
            "harvest",
            "Loss harvesting stock by stock",
            "Direct indexing: own the stocks themselves and harvest losses on individual holdings, not only when the whole fund falls.",
            lambda p: p.replace(direct_indexing=chosen.direct_indexing),
        ),
        WaterfallStrategy(
            "allocation",
            f"{strategy.reserve_years}-year spending reserve, the rest in stocks"
            if strategy.reserve_years
            else f"{round(strategy.stock_share * 100)}% stocks, gliding down" + (", goal bonds" if strategy.goal_bonds else ""),
            (
                f"Hold the next {strategy.reserve_years} years of what you will need to take out of the portfolio in bonds and private credit, "
                "pay expenses and taxes from them first, and keep everything else in stocks: stocks are rarely sold at a loss."
                if strategy.reserve_years
                else "The stock share and glide path of the plan instead of the advisor's 80% falling to 50%."
            ),
            lambda p: p.replace(
                stock_share=chosen.stock_share,
                glide_start_age=GLIDE_START_AGE,
                glide_drop=chosen.glide_drop,
                goal_bonds=chosen.goal_bonds,
                reserve_years=chosen.reserve_years,
                reserve_refill_after_gains=chosen.reserve_refill_after_gains,
            ),
        ),
        WaterfallStrategy(
            "private_credit",
            f"{round(strategy.private_credit * 100)}% private credit",
            "A private credit sleeve, held in the pre-tax account first, which pays more than bonds with a similar calm.",
            lambda p: p.replace(private_credit=chosen.private_credit),
        ),
        WaterfallStrategy(
            "conversions",
            "Roth conversions" if strategy.conversion_bracket is None else f"Roth conversions up to the {_bracket(strategy)} bracket",
            (
                f"Move pre-tax money to Roth up to the top of the {_bracket(strategy)} bracket "
                + ("every year" if strategy.conversion_every_year else "in low-income years and retirement")
                + ", paying today's lower rate instead of a higher one later."
            )
            if strategy.conversion_bracket is not None
            else "",
            lambda p: p.replace(conversion_top=chosen.conversion_top, conversion_every_year=chosen.conversion_every_year),
        ),
        WaterfallStrategy(
            "withdrawals",
            "Tax-aware withdrawal order",
            "Take pre-tax money up to the bracket first, then the taxable account, then Roth, so each year's income lands in a low bracket.",
            lambda p: p.replace(bracket_withdrawals=chosen.bracket_withdrawals, withdrawal_top=chosen.withdrawal_top),
        ),
        WaterfallStrategy(
            "k401",
            "Roth 401(k) contributions",
            "Contribute to the Roth side of the 401(k)" + (" only in low-income years." if strategy.k401 == "roth_low" else "."),
            lambda p: p.replace(k401=chosen.k401),
        ),
        WaterfallStrategy(
            "borrow",
            "Borrow for goals",
            "Pay for a goal with a box-spread loan against the taxable account instead of selling, and repay it from savings or in low-tax years.",
            lambda p: p.replace(goal_funding=chosen.goal_funding),
        ),
    ]
    # A strategy is a bar only if the plan uses it: it changes the policy it would be applied to.
    steps = [s for s in candidates if s.change(baseline) != baseline]
    policy = baseline
    for step in steps:
        policy = step.change(policy)
    assert policy == chosen, "the last strategy must land exactly on the chosen policy"
    return steps


@dataclass(frozen=True)
class Bar:
    key: str
    label: str
    detail: str
    enabled: bool
    delta_dollars: float  # change in median after-tax wealth at the horizon from this strategy, given the ones on before it
    delta_rate: float  # the same as a change in the annual growth-rate advantage over the baseline
    cumulative_dollars: float
    cumulative_rate: float


@dataclass(frozen=True)
class WaterfallResult:
    bars: list[Bar]
    baseline_wealth: np.ndarray  # (paths,)
    plan_wealth: np.ndarray  # (paths,) with the enabled strategies
    baseline_wealth_heirs: np.ndarray  # (paths,) the same, with the estate passed to heirs at the horizon
    plan_wealth_heirs: np.ndarray
    baseline_paths: np.ndarray  # (paths, years) after-tax wealth at each year end
    plan_paths: np.ndarray
    advantage: metrics.Advantage
    years: int
    baseline_shortfall: float  # share of futures in which the policy could not fund spending or a goal
    plan_shortfall: float


def run_waterfall(
    inputs: SimInputs,
    strategy: Strategy,
    enabled: set[str] | None = None,
    baseline: Policy = RIA_BASELINE,
    risk_aversion: float = 3.0,
    median_only: bool = False,
) -> WaterfallResult:
    """Every cumulative policy on the same futures. `enabled` is the set of strategy keys left on (None: all of them).

    With `median_only` the risk-adjusted advantage is not worked out (its fields are 0.0) and the wealth paths are not kept:
    that is the waterfall, which is about the median alone."""
    steps = waterfall_strategies(strategy, baseline)
    on = {s.key for s in steps} if enabled is None else set(enabled) & {s.key for s in steps}
    policies = [baseline]
    for step in steps:
        policies.append(step.change(policies[-1]) if step.key in on else policies[-1])
    # A strategy that is off adds nothing: it reuses the policy before it, so only the distinct ones are simulated.
    distinct = list(dict.fromkeys(policies))
    batch = run_batch(inputs, distinct, record_paths=not median_only)
    index = {p: i for i, p in enumerate(distinct)}
    years = inputs.n_years
    medians = [float(np.median(batch.wealth[index[p]])) for p in policies]
    bars = []
    for i, step in enumerate(steps, start=1):
        bars.append(
            Bar(
                key=step.key,
                label=step.label,
                detail=step.detail,
                enabled=step.key in on,
                delta_dollars=medians[i] - medians[i - 1],
                delta_rate=metrics.annualized(medians[i], medians[0], years) - metrics.annualized(medians[i - 1], medians[0], years),
                cumulative_dollars=medians[i] - medians[0],
                cumulative_rate=metrics.annualized(medians[i], medians[0], years),
            )
        )
    plan_policy = policies[-1]
    return WaterfallResult(
        bars=bars,
        baseline_wealth=batch.wealth[index[baseline]],
        plan_wealth=batch.wealth[index[plan_policy]],
        baseline_wealth_heirs=batch.wealth_heirs[index[baseline]],
        plan_wealth_heirs=batch.wealth_heirs[index[plan_policy]],
        baseline_paths=np.zeros((0, years)) if median_only else batch.path_wealth[index[baseline]],
        plan_paths=np.zeros((0, years)) if median_only else batch.path_wealth[index[plan_policy]],
        advantage=metrics.compare(
            batch.wealth[index[plan_policy]], batch.wealth[index[baseline]], years, risk_aversion, with_range=True, median_only=median_only
        ),
        years=years,
        baseline_shortfall=float(np.mean(batch.unfunded[index[baseline]] > 0)),
        plan_shortfall=float(np.mean(batch.unfunded[index[plan_policy]] > 0)),
    )
