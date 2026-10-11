"""What would have to change for the raw advantage over the good advisor to reach 2-3% a year?

    python -m app.study.reach --out ../reports/path_to_2_3_percent.md

This is a diagnostic. It changes nothing the app does and adopts none of the changes it measures: a change
made because it moves the output toward a target is tuning, and each one below is a different assumption (or a
different amount of risk), not a better plan. What it answers is how far each lever goes, and what would have
to be true for the sample household to show 2%, 2.5% and 3% in median wealth.

1. The ceiling: the plan with the highest median wealth anywhere on the 4,032-strategy menu, at the specified
   assumptions, and how much of that is Donabach's tools and how much is simply more equity than the advisor holds.
2. One lever at a time on that plan: the Donabach fee, the equity return, the tax heirs pay on pre-tax money,
   and how much equity the advisor holds.
3. The equity return the ceiling plan would need for 2%, 2.5% and 3%, with the specified fee and tax rule and
   with a lower fee and a heavier heirs' tax together.

Plans are chosen on 6,000 futures and scored on 2,000 others the choice never saw. The advantage is the
annualized growth-rate difference between median after-tax wealth at 80 (`app.study.metrics`).
"""

from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass, replace
from pathlib import Path

import numpy as np

from app.planner.baseline import RIA_BASELINE, TYPICAL_ADVISOR
from app.planner.search import RISK_AVERSION, WEALTH_FLOOR, search
from app.planner.strategies import Strategy, menu
from app.sim import markets
from app.sim.simulate import HC_SS, TV_AGED, Policy, SimInputs, build_inputs, run_batch
from app.study.equity_share import (
    DESIGN_SEED_OFFSET,
    Result,
    advisor_allocation_chain,
    annualized,
    baseline_result,
    evaluate,
    pick,
    score_menu,
)
from app.study.measure import EVAL_SEED_OFFSET, sample_household
from app.study.metrics import compare
from app.tax.engine import pretax_withdrawal_rate

TARGETS = (0.02, 0.025, 0.03)
GROWTH_RISK_AVERSION = 1.0  # log utility: the planner's setting for a household that wants growth
FEES = (0.0035, 0.0025, 0.0015, 0.0)  # the specified flat fee first
EQUITY_RETURNS = (0.055, 0.065, 0.075, 0.085, 0.095, 0.105)  # real arithmetic mean; the specified one first
HEIRS_RATES = (None, 0.24, 0.32)  # None: the specified 20-year spread beside Social Security
ADVISOR_GLIDES = ((0.60, 0.30), (0.70, 0.40), (0.80, 0.50), (0.90, 0.60), (1.00, 0.75))  # (stocks today, from 70)
SPEC_EQUITY_RETURN = float(markets.DEFAULT_ASSUMPTIONS.means[markets.EQUITY])


# --------------------------------------------------------------------------------------------
# Changing one assumption on futures that are already drawn
# --------------------------------------------------------------------------------------------


def with_equity_return(inputs: SimInputs, mean: float) -> SimInputs:
    """The same futures with the equity mean `mean` instead of the specified one.

    Returns are `mean + sd x z` with the same draws `z`, so moving the mean shifts every equity return by the same
    amount; no equity return is anywhere near the -95% floor, so this is exactly what drawing them again would give.
    """
    rets = inputs.rets.copy()
    rets[:, :, markets.EQUITY] += mean - SPEC_EQUITY_RETURN
    return replace(inputs, rets=rets)


def pretax_balance(owed: np.ndarray, social_security: float, aged: float) -> np.ndarray:
    """Pre-tax balances at the horizon from the tax still owed on them (owed = balance x the 20-year-spread rate)."""
    out = np.zeros_like(owed, dtype=float)
    for i, due in enumerate(owed):
        if due <= 0.0:
            continue
        low, high = 0.0, max(1.0, due) * 100.0
        while high - low > 0.01:
            mid = 0.5 * (low + high)
            if mid * float(pretax_withdrawal_rate(mid, social_security, aged)) < due:
                low = mid
            else:
                high = mid
        out[i] = 0.5 * (low + high)
    return out


def raw_advantage(held: SimInputs, plan: Policy, baseline: Policy = RIA_BASELINE) -> float:
    w = run_batch(held, [plan, baseline]).wealth
    return float(annualized(np.median(w[0]), float(np.median(w[1])), held.n_years))


def raw_with(held: SimInputs, plan: Policy, baseline: Policy, heirs: float | None = None) -> float:
    """Raw advantage of `plan` over `baseline`; with `heirs`, the pre-tax balance at the horizon is taxed at that flat
    rate instead of the specified 20-year spread (the tax already counted is added back, the heirs' tax taken off)."""
    batch = run_batch(held, [plan, baseline])
    wealth = batch.wealth
    if heirs is not None:
        ss, aged = float(held.hhc[HC_SS]), float(held.tv[-1, TV_AGED])
        balances = np.vstack([pretax_balance(batch.pretax_owed[i], ss, aged) for i in range(2)])
        wealth = wealth + batch.pretax_owed - heirs * balances
    return float(annualized(np.median(wealth[0]), float(np.median(wealth[1])), held.n_years))


def advantage_at(
    held: SimInputs, mean: float, plan: Policy, baseline: Policy = RIA_BASELINE, fee: float | None = None, heirs: float | None = None
) -> float:
    """Raw advantage on the same futures with the equity mean `mean`, optionally another Donabach fee and an heirs' tax rate."""
    return raw_with(with_equity_return(held, mean), plan if fee is None else plan.replace(flat_fee=fee), baseline, heirs)


def solve_equity_return(
    held: SimInputs, plan: Policy, target: float, fee: float | None = None, heirs: float | None = None, tol: float = 1e-4
) -> float | None:
    """The equity return at which the plan's raw advantage over the good advisor equals `target`: None if even 40% a year
    falls short, the specified return if it is already reached."""

    def at(mean: float) -> float:
        return advantage_at(held, mean, plan, RIA_BASELINE, fee, heirs)

    low, high = SPEC_EQUITY_RETURN, 0.40
    if at(high) < target:
        return None
    if at(low) >= target:
        return low
    while high - low > tol:
        mid = 0.5 * (low + high)
        if at(mid) < target:
            low = mid
        else:
            high = mid
    return 0.5 * (low + high)


# --------------------------------------------------------------------------------------------
# The study
# --------------------------------------------------------------------------------------------


@dataclass
class Reach:
    recommendation: Strategy  # what the app recommends today
    ceiling: Strategy  # the highest median on the menu
    growth: Strategy  # what the planner picks at risk aversion 1
    advisor: Result  # the good advisor on the held-out futures
    spread_rate: float  # the specified tax rate on the advisor's pre-tax balance at 80 (median over futures)
    plans: list[Result]  # tools at the advisor's allocation, the recommendation, the growth pick, the ceiling (against the good advisor)
    typical: dict[str, float]  # raw advantage of each plan over the typical advisor
    fees: list[tuple[float, float, float]]  # fee, raw advantage of the ceiling plan, of the recommendation
    advisor_equity: list[tuple[tuple[float, float], float, float, float]]  # glide, ceiling raw, recommendation raw, ceiling risk-adjusted
    equity_returns: list[tuple[float, float, float, float]]  # mean, ceiling raw, recommendation raw, ceiling shortfall
    heirs: list[tuple[float | None, float, float]]  # rate, ceiling raw, recommendation raw
    break_even: dict[str, list[tuple[float, float | None]]]  # scenario -> [(target, equity return needed)]
    seconds: float


def run_reach(
    n_design: int = 6000,
    n_eval: int = 2000,
    seed: int = markets.DEFAULT_SEED,
    strategies: list[Strategy] | None = None,
    progress=None,
) -> Reach:
    started = time.perf_counter()
    say = progress or (lambda message: None)
    household = sample_household()
    strategies = strategies if strategies is not None else menu()

    recommendation = search(build_inputs(household, n_paths=400, seed=seed), strategies=strategies).best.strategy
    design = build_inputs(household, n_paths=n_design, seed=seed + DESIGN_SEED_OFFSET)
    held = build_inputs(household, n_paths=n_eval, seed=seed + EVAL_SEED_OFFSET)
    scores = score_menu(design, strategies, gammas=(RISK_AVERSION, GROWTH_RISK_AVERSION))
    growth = scores.strategies[pick(scores.ce[GROWTH_RISK_AVERSION])]
    ceiling = scores.strategies[pick(scores.median)]
    say(f"recommendation: {recommendation.short_label()}; growth: {growth.short_label()}; ceiling: {ceiling.short_label()}")

    skill_label, skill_policy = advisor_allocation_chain(ceiling)[-1]
    plans = evaluate(
        held,
        [
            ("Donabach's tools at the advisor's own allocation (no extra equity)", skill_policy, None),
            ("The app's recommendation (risk aversion 3)", recommendation.policy(), RISK_AVERSION),
            ("What the planner picks at risk aversion 1", growth.policy(), GROWTH_RISK_AVERSION),
            ("The ceiling: the most median wealth on the menu", ceiling.policy(), None),
        ],
        ["", recommendation.short_label(), growth.short_label(), ceiling.short_label()],
    )
    typical_batch = run_batch(held, [TYPICAL_ADVISOR, skill_policy, recommendation.policy(), growth.policy(), ceiling.policy()])
    typical = {
        result.label: float(compare(typical_batch.wealth[i], typical_batch.wealth[0], held.n_years, RISK_AVERSION, WEALTH_FLOOR).median)
        for i, result in enumerate(plans, start=1)
    }

    rec, top = recommendation.policy(), ceiling.policy()
    fees = []
    for fee in FEES:
        fees.append((fee, raw_advantage(held, top.replace(flat_fee=fee)), raw_advantage(held, rec.replace(flat_fee=fee))))
    say("fees done")

    advisor_equity = []
    for start_share, end_share in ADVISOR_GLIDES:
        advisor = RIA_BASELINE.replace(stock_share=start_share, glide_drop=start_share - end_share)
        row = evaluate(held, [("ceiling", top, None), ("recommendation", rec, None)], baseline=advisor)
        advisor_equity.append(((start_share, end_share), row[0].raw.median, row[1].raw.median, row[0].adjusted.risk_adjusted))
    say("advisor equity done")

    equity_returns = []
    for mean in EQUITY_RETURNS:
        shifted = with_equity_return(held, mean)
        row = evaluate(shifted, [("ceiling", top, None), ("recommendation", rec, None)])
        equity_returns.append((mean, row[0].raw.median, row[1].raw.median, row[0].shortfall))
    say("equity returns done")

    heirs = [(rate, raw_with(held, top, RIA_BASELINE, rate), raw_with(held, rec, RIA_BASELINE, rate)) for rate in HEIRS_RATES]
    say("heirs done")


    break_even: dict[str, list[tuple[float, float | None]]] = {}
    scenarios = {
        "the specified fee and tax rule": {},
        "a 0.25% fee and heirs taxed at 32%": {"fee": 0.0025, "heirs": 0.32},
    }
    for name, options in scenarios.items():
        break_even[name] = [(target, solve_equity_return(held, top, target, **options)) for target in TARGETS]
    say("break-even done")

    advisor_batch = run_batch(held, [RIA_BASELINE])
    balances = pretax_balance(advisor_batch.pretax_owed[0], float(held.hhc[HC_SS]), float(held.tv[-1, TV_AGED]))
    spread_rate = float(np.median(advisor_batch.pretax_owed[0][balances > 0] / balances[balances > 0])) if (balances > 0).any() else 0.0

    return Reach(
        recommendation=recommendation,
        ceiling=ceiling,
        growth=growth,
        advisor=baseline_result(held),
        spread_rate=spread_rate,
        plans=plans,
        typical=typical,
        fees=fees,
        advisor_equity=advisor_equity,
        equity_returns=equity_returns,
        heirs=heirs,
        break_even=break_even,
        seconds=time.perf_counter() - started,
    )


# --------------------------------------------------------------------------------------------
# The report
# --------------------------------------------------------------------------------------------


def _pct(x: float, digits: int = 2) -> str:
    return f"{x * 100:+.{digits}f}%"


def _share(x: float) -> str:
    return f"{x * 100:.1f}%"


def render(reach: Reach) -> str:
    skill, _recommendation, growth, top = reach.plans
    extra_equity = top.raw.median - skill.raw.median
    lines = [
        "# What would have to change to reach 2 to 3% a year?",
        "",
        "Generated by `python -m app.study.reach`. This is a diagnostic: it measures how far each lever goes and adopts none of them. "
        "Nothing the app does was changed, and nothing was tuned toward a result.",
        "",
        f"**Short answer.** With the strategies on the menu and the market assumptions as specified, the most median wealth any plan produces "
        f"is **{_pct(top.raw.median)} a year** over the good advisor (the sample household, futures the plan never saw). About "
        f"{_pct(skill.raw.median)} of that is Donabach's tools (fee, asset location, conversions, withdrawal order, goal funding). The other "
        f"{_pct(extra_equity)} is only that the plan holds {top.exposure[0]:.0%} stocks against the advisor's {skill.exposure[0]:.0%} today "
        f"and {top.exposure[2]:.0%} against {skill.exposure[2]:.0%} from 70, which is more risk: it runs out of money in {top.shortfall:.1%} of "
        f"futures against the advisor's {reach.advisor.shortfall:.1%}. At risk aversion 1 the planner itself picks a plan with {growth.exposure[0]:.0%} stocks that is "
        f"{_pct(growth.raw.median)} ahead and runs out of money in {growth.shortfall:.1%} of futures (the advisor's rate is {reach.advisor.shortfall:.1%}), with a "
        f"10th percentile of ${growth.p10:,.0f} against the advisor's ${reach.advisor.p10:,.0f}; its risk-adjusted advantage is {_pct(growth.adjusted.risk_adjusted)}. "
        "No choice on the menu reaches 2%.",
        "",
        "## 1. The ceiling, and where it comes from",
        "",
        "| Plan | What it holds | Stocks today / at 58 / from 70 | Raw advantage over the good advisor | Over the typical advisor | Risk-adjusted (risk aversion 3) | 10th percentile | Chance of running out of money |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for result in reach.plans:
        today, at_58, from_70 = result.exposure
        low, high = result.raw.median_range
        lines.append(
            f"| {result.label} | {result.note} | {today:.0%} / {at_58:.0%} / {from_70:.0%} | {_pct(result.raw.median)} ({_pct(low)} to {_pct(high)}) | "
            f"{_pct(reach.typical[result.label])} | {_pct(result.adjusted.risk_adjusted)} | ${result.p10:,.0f} | {result.shortfall:.1%} |"
        )
    lines += [
        "",
        "## 2. One lever at a time",
        "",
        "Each table changes one thing and measures the ceiling plan and the app's recommendation against the same good advisor, "
        "on the same futures. None of these changes is in the app.",
        "",
        "**The Donabach fee** (specified: 0.35% flat; the advisor's is 1.0% falling to 0.5%)",
        "",
        "| Fee | Ceiling plan | Recommendation |",
        "|---|---|---|",
    ]
    lines += [f"| {fee:.2%}{' (specified)' if i == 0 else ''} | {_pct(a)} | {_pct(b)} |" for i, (fee, a, b) in enumerate(reach.fees)]
    lines += [
        "",
        "**How much equity the advisor holds** (specified: 80% stocks today falling to 50% from 70). The same two plans against advisors that hold "
        "more or less equity: most of the raw advantage is the difference in equity, not skill.",
        "",
        "| Advisor's stocks today / from 70 | Ceiling plan: raw | Recommendation: raw | Ceiling plan: risk-adjusted |",
        "|---|---|---|---|",
    ]
    lines += [
        f"| {s:.0%} / {e:.0%}{' (specified)' if (s, e) == (0.80, 0.50) else ''} | {_pct(a)} | {_pct(b)} | {_pct(c)} |"
        for (s, e), a, b, c in reach.advisor_equity
    ]
    lines += [
        "",
        "**The equity return** (real, arithmetic mean; specified 5.5%, volatility 16%). The advisor is on the same futures, so a higher return lifts both; "
        "it widens the gap only because the plan holds more equity.",
        "",
        "| Equity return | Ceiling plan: raw | Recommendation: raw | Ceiling plan: chance of running out of money |",
        "|---|---|---|---|",
    ]
    lines += [
        f"| {m:.1%}{' (specified)' if abs(m - SPEC_EQUITY_RETURN) < 1e-9 else ''} | {_pct(a)} | {_pct(b)} | {c:.1%} |"
        for m, a, b, c in reach.equity_returns
    ]
    lines += [
        "",
        f"**The tax heirs pay on pre-tax money** (specified: the balance at 80 is valued as if withdrawn evenly over 20 years beside Social Security, "
        f"which is a rate of about {reach.spread_rate:.0%} for the advisor's balance; a non-spouse heir must empty an inherited account within ten years and "
        "may be in the 24% or 32% bracket). Not modelled: a survivor's single-filer brackets, which favor conversions in the same way.",
        "",
        "| Tax on pre-tax money at 80 | Ceiling plan: raw | Recommendation: raw |",
        "|---|---|---|",
    ]
    lines += [
        f"| {'the specified 20-year spread' if r is None else f'{r:.0%} flat'} | {_pct(a)} | {_pct(b)} |"
        for r, a, b in reach.heirs
    ]
    lines += [
        "",
        "## 3. What the equity return would have to be",
        "",
        "The equity return at which the ceiling plan's raw advantage reaches each target, everything else as specified except where the row says so. "
        "'Not reachable' means 40% a year real is still not enough.",
        "",
        "| Target | " + " | ".join(reach.break_even) + " |",
        "|---|" + "---|" * len(reach.break_even),
    ]
    for i, target in enumerate(TARGETS):
        cells = []
        for scenario in reach.break_even.values():
            mean = scenario[i][1]
            if mean is None:
                cells.append("not reachable")
            elif mean <= SPEC_EQUITY_RETURN + 1e-9:
                cells.append(f"already reached at the specified {SPEC_EQUITY_RETURN:.1%}")
            else:
                cells.append(f"{mean:.1%} real")
        lines.append(f"| {target:.1%} | " + " | ".join(cells) + " |")
    lines += [
        "",
        f"For comparison, the specified 5.5% arithmetic with 16% volatility compounds to about {(SPEC_EQUITY_RETURN - 0.16 ** 2 / 2):.1%} a year; "
        "the Global Investment Returns Yearbook's forward-looking premium over bills is about 5% arithmetic (3.5% geometric), which is "
        "close to what is specified (search-result excerpt, not verified at the page).",
        "",
        "## 4. What is not in the engine",
        "",
        "These would add to an advantage but the engine does not compute them, so none is included and none is assumed: behavioral coaching "
        "(Vanguard's 'Advisor's Alpha' puts it at about 1.5% a year of its 'up to 3%', and says its components are not additive and the total is irregular, "
        "not annual; the estimate is contested), a dynamic spending rule (0 to 1.1% in the same table), Social Security claiming, a survivor's tax brackets, "
        "and diversifying a concentrated stock (the simulator holds the diversified market). Borrowing to hold more than 100% stocks would raise the "
        "median further, mechanically, by taking more risk; it is not among the strategies and is not advice.",
        "",
        f"_Computed in {reach.seconds:.0f} seconds._",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--n-design", type=int, default=6000)
    parser.add_argument("--n-eval", type=int, default=2000)
    args = parser.parse_args(argv)

    def progress(message: str) -> None:
        print(f"[{time.strftime('%H:%M:%S')}] {message}", file=sys.stderr, flush=True)

    reach = run_reach(args.n_design, args.n_eval, progress=progress)
    text = render(reach)
    args.out.write_text(text)
    print(text)


if __name__ == "__main__":
    main()
