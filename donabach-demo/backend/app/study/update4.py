"""Update 4's measurements for single households (the sample household and the showcase household).

    python -m app.study.update4 --out ../reports/update4_households.md

For each household, on the app's own settings (the plan searched on 400 futures, everything measured on 2,000 others):

* the plan and its advantage over both advisors under both valuations at 80, with the typical advisor as it is now (its funds pay
  capital-gains distributions) and as it was before;
* what stock-by-stock direct indexing is worth against the old assumption (the aggregate rule with 3% "dispersion" harvest), for the
  same plan with direct indexing on and off, and how much each harvests;
* what changes if the stocks' own volatility or the harvest threshold were different;
* what a gift of appreciated lots instead of cash is worth, when the household gives to charity.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np

from app.planner import plan as planner
from app.planner.baseline import RIA_BASELINE, TYPICAL_ADVISOR
from app.planner.search import RISK_AVERSION, WEALTH_FLOOR, search
from app.planner.strategies import Strategy, menu
from app.schemas import Household
from app.sim import diag as D
from app.sim import markets
from app.sim import simulate as sim
from app.sim.simulate import ModelOptions, build_inputs, run_batch
from app.study.metrics import compare

SEARCH_PATHS = 400
EVAL_PATHS = 2000
SEED = 2026
TYPICAL_NO_DISTRIBUTIONS = TYPICAL_ADVISOR.replace(fund_distribution=0.0, fund_distribution_short_term=0.0)


def with_giving(household: Household, giving: float) -> Household:
    return household.model_copy(update={"goals": household.goals.model_copy(update={"charitable_giving": giving})})


def find_plan(household: Household, valuation: str = "liquidated", seed: int = SEED) -> Strategy:
    futures = build_inputs(household, n_paths=SEARCH_PATHS, seed=seed)
    return search(futures, strategies=menu(style=planner.DEFAULT_STYLE), valuation=valuation).best.strategy


def evaluation(household: Household, options: ModelOptions | None = None, seed: int = SEED):
    return build_inputs(household, n_paths=EVAL_PATHS, seed=seed + planner.EVAL_SEED_OFFSET, options=options)


def _adv(plan: np.ndarray, baseline: np.ndarray, years: int) -> dict[str, float]:
    a = compare(plan, baseline, years, RISK_AVERSION, WEALTH_FLOOR, with_range=True)
    return {
        "median": a.median,
        "risk_adjusted": a.risk_adjusted,
        "median_dollars": a.median_dollars,
        "plan_median": a.plan_median,
        "baseline_median": a.baseline_median,
        "median_low": a.median_range[0],
        "median_high": a.median_range[1],
    }


def advantages(household: Household, strategy: Strategy) -> dict:
    """The plan against both advisors (and the typical advisor before its funds paid distributions), under both valuations."""
    inputs = evaluation(household)
    policies = [strategy.policy(), RIA_BASELINE, TYPICAL_ADVISOR, TYPICAL_NO_DISTRIBUTIONS]
    batch = run_batch(inputs, policies)
    years = household.horizon_years
    out: dict = {"recommendation": strategy.short_label(), "choices": strategy.choices(), "direct_indexing": strategy.direct_indexing}
    for valuation, wealth in (("liquidated", batch.wealth), ("heirs", batch.wealth_heirs)):
        out[valuation] = {
            "good_ria": _adv(wealth[0], wealth[1], years),
            "typical_advisor": _adv(wealth[0], wealth[2], years),
            "typical_advisor_before_distributions": _adv(wealth[0], wealth[3], years),
        }
    out["shortfall"] = {
        "plan": float(np.mean(batch.unfunded[0] > 0)),
        "good_ria": float(np.mean(batch.unfunded[1] > 0)),
        "typical_advisor": float(np.mean(batch.unfunded[2] > 0)),
    }
    out["p10"] = {"plan": float(np.percentile(batch.wealth[0], 10)), "good_ria": float(np.percentile(batch.wealth[1], 10))}
    return out


def _harvested(batch, index: int) -> float:
    return float(-batch.diag[index, :, D.D_GAIN + D.P_HARVEST].mean())


def direct_indexing_benefit(household: Household, strategy: Strategy, idio_vol: float = markets.STOCK_IDIO_VOL, theta: float = sim.HARVEST_THRESHOLD) -> dict:
    """The same plan with direct indexing off, on with the old rule (85% of a decline plus 3% of the value a year, scaled by the basis
    ratio) and on stock by stock: the annual growth-rate difference in median wealth at 80 that direct indexing makes under each,
    and the losses each harvests over the plan."""
    years = household.horizon_years
    base = strategy.policy().replace(direct_indexing=True)
    off = base.replace(direct_indexing=False)
    old = base.replace(di_model="aggregate")
    stock = base.replace(di_model="stock")
    book_options = ModelOptions(idio_vol=idio_vol, harvest_threshold=theta)
    new_inputs = evaluation(household, book_options)
    old_inputs = evaluation(household, ModelOptions(harvest_model="spec", idio_vol=idio_vol, harvest_threshold=theta))
    new_batch = run_batch(new_inputs, [off, stock, base.replace(di_model="aggregate")], diagnostics=True)  # off, the book, the fitted rule
    old_batch = run_batch(old_inputs, [off, old], diagnostics=True)  # off, the old rule (3% a year)
    out = {"idio_vol": idio_vol, "theta": theta, "plan_has_direct_indexing": strategy.direct_indexing}
    for valuation, getter in (("liquidated", lambda b: b.wealth), ("heirs", lambda b: b.wealth_heirs)):
        out[valuation] = {
            "old_rule": _adv(getter(old_batch)[1], getter(old_batch)[0], years),
            "stock_by_stock": _adv(getter(new_batch)[1], getter(new_batch)[0], years),
            "fitted_rule": _adv(getter(new_batch)[2], getter(new_batch)[0], years),
        }
    out["harvested_losses"] = {
        "old_rule": _harvested(old_batch, 1),
        "stock_by_stock": _harvested(new_batch, 1),
        "fitted_rule": _harvested(new_batch, 2),
        "no_direct_indexing": _harvested(new_batch, 0),
    }
    brokerage = household.accounts.brokerage_value
    out["brokerage_value_today"] = brokerage
    out["harvested_per_year_share_of_brokerage_today"] = {
        k: v / years / brokerage if brokerage > 0 else 0.0 for k, v in out["harvested_losses"].items()
    }
    return out


def sensitivity(household: Household, strategy: Strategy) -> dict:
    """What the stock-level benefit is if the stocks' own volatility, or the harvest threshold, were different."""
    grid = {}
    for sigma in (0.20, 0.25, 0.30, 0.35):
        grid[f"sigma={sigma:.2f}"] = direct_indexing_benefit(household, strategy, idio_vol=sigma)["liquidated"]["stock_by_stock"]["median"]
    for theta in (0.0, 0.01, 0.02, 0.05, 0.10):  # 10%: the one published rule of thumb (Israelov and Lu, monthly scans)
        grid[f"theta={theta:.2f}"] = direct_indexing_benefit(household, strategy, theta=theta)["liquidated"]["stock_by_stock"]["median"]
    return grid


def giving_effect(household: Household, giving: float) -> dict:
    """With annual giving, the plan the planner chooses, giving lots as it does and giving cash, and both advisors giving cash."""
    household = with_giving(household, giving)
    strategy = find_plan(household)
    inputs = evaluation(household)
    years = household.horizon_years
    lots = strategy.policy()
    cash = lots.replace(donate_lots=False)
    batch = run_batch(inputs, [lots, cash, RIA_BASELINE, TYPICAL_ADVISOR], diagnostics=True)
    out = {
        "giving": giving,
        "recommendation": strategy.short_label(),
        "lots_vs_cash": {
            "liquidated": _adv(batch.wealth[0], batch.wealth[1], years),
            "heirs": _adv(batch.wealth_heirs[0], batch.wealth_heirs[1], years),
        },
        "plan_vs_good_ria": {
            "liquidated": _adv(batch.wealth[0], batch.wealth[2], years),
            "heirs": _adv(batch.wealth_heirs[0], batch.wealth_heirs[2], years),
        },
        "gifts_in_kind": float(batch.diag[0, :, D.D_DONATED].mean()),
        "gain_given_away": float(batch.diag[0, :, D.D_DONATED_GAIN].mean()),
        "gifts_in_cash": float(batch.diag[0, :, D.D_CASHGIFT].mean()),
        "tax_lots_vs_cash_median": float(np.median(batch.taxes_paid[0] - batch.taxes_paid[1])),
    }
    return out


def measure(household: Household, name: str, giving: float = 20_000.0) -> dict:
    started = time.perf_counter()
    strategy = find_plan(household)
    result = {"household": name, "years": household.horizon_years, "age": household.primary_age}
    result["plan"] = advantages(household, strategy)
    result["plan_for_heirs"] = advantages(household, find_plan(household, "heirs"))
    result["direct_indexing"] = direct_indexing_benefit(household, strategy)
    result["sensitivity"] = sensitivity(household, strategy)
    result["giving"] = giving_effect(household, giving)
    result["seconds"] = time.perf_counter() - started
    return result


# --- Report --------------------------------------------------------------------------------------------------------


def _p(x: float) -> str:
    return f"{x * 100:+.2f}%"


def _d(x: float) -> str:
    return f"${x:,.0f}"


def render(results: list[dict]) -> str:
    out = ["# Update 4: single-household measurements", ""]
    for r in results:
        plan = r["plan"]
        out += [f"## {r['household']}", ""]
        out += [f"**The plan the planner recommends:** {plan['recommendation']} (direct indexing {'on' if plan['direct_indexing'] else 'off'}).", ""]
        out += ["Annualized advantage in wealth at 80, median / risk-adjusted, on 2,000 futures the plan was not searched on:", ""]
        out += ["| Against | Liquidated at 80 | Passed to heirs at 80 |", "|---|---|---|"]
        for key, label in (
            ("good_ria", "Good advisor"),
            ("typical_advisor", "Typical advisor (its funds pay capital-gain distributions)"),
            ("typical_advisor_before_distributions", "Typical advisor before distributions were added"),
        ):
            a, h = plan["liquidated"][key], plan["heirs"][key]
            out.append(f"| {label} | {_p(a['median'])} / {_p(a['risk_adjusted'])} | {_p(h['median'])} / {_p(h['risk_adjusted'])} |")
        out += [""]
        ph = r["plan_for_heirs"]
        out += [
            f"Choosing the plan for the heirs' valuation instead gives: {ph['recommendation']}; "
            f"{_p(ph['liquidated']['good_ria']['median'])} liquidated and {_p(ph['heirs']['good_ria']['median'])} passed to heirs over the good advisor.",
            "",
        ]
        di = r["direct_indexing"]
        out += ["**What direct indexing is worth** (the same plan with direct indexing on against off, median wealth at 80, liquidated / heirs):", ""]
        out += ["| Direct indexing | Growth-rate advantage | Losses harvested over the plan | Per year, share of today's taxable account |", "|---|---|---|---|"]
        for key, label in (("old_rule", "The old rule (85% of a decline plus 3% a year)"), ("stock_by_stock", "100 stocks with lots (the engine now)"), ("fitted_rule", "The aggregate rule fitted to the stocks")):
            share = di["harvested_per_year_share_of_brokerage_today"][key]
            out.append(
                f"| {label} | {_p(di['liquidated'][key]['median'])} / {_p(di['heirs'][key]['median'])} | {_d(di['harvested_losses'][key])} | {share * 100:.1f}% |"
            )
        out += [""]
        sens = r["sensitivity"]
        out += ["Stock-level benefit (liquidated) if the stocks' own volatility, or the harvest threshold, were different: " + "; ".join(f"{k}: {_p(v)}" for k, v in sens.items()) + ".", ""]
        g = r["giving"]
        lv, hv = g["lots_vs_cash"]["liquidated"], g["lots_vs_cash"]["heirs"]
        out += [
            f"**Giving ${g['giving']:,.0f} a year:** the plan ({g['recommendation']}) gives lots instead of cash worth {_p(lv['median'])} a year liquidated and {_p(hv['median'])} "
            f"passed to heirs; it gives {_d(g['gifts_in_kind'])} of stock over the plan (an unrealized gain of {_d(g['gain_given_away'])} never taxed) and {_d(g['gifts_in_cash'])} in cash. "
            f"Against the good advisor (who gives cash): {_p(g['plan_vs_good_ria']['liquidated']['median'])} liquidated, {_p(g['plan_vs_good_ria']['heirs']['median'])} passed to heirs.",
            "",
        ]
    return "\n".join(out)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--out", type=Path, default=Path("../reports/update4_households.md"))
    parser.add_argument("--json", type=Path, default=Path("../reports/update4_households.json"))
    parser.add_argument("--giving", type=float, default=20_000.0)
    args = parser.parse_args()
    from app import showcase
    from app.study.measure import sample_household

    results = []
    for name, household in (
        ("The sample household (Alex and Jordan Sample)", sample_household()),
        ("The showcase household (the Tanaka family)", showcase.load_fixture().household),
    ):
        results.append(measure(household, name, args.giving))
        print(f"{name}: {results[-1]['seconds']:.0f} s", flush=True)
    args.json.write_text(json.dumps(results, indent=2))
    args.out.write_text(render(results))


if __name__ == "__main__":
    main()
