"""Writes reports/benefit_explainer.md: for each strategy of a plan, the mechanism as the engine implements it, the formula, the
assumptions it rests on (with their values, read from the code so they cannot drift) and the showcase household's own numbers: the
waterfall's bar (the strategy switched on in the waterfall's order) and its Shapley share (the order-free one).

    python -m app.study.explainer --out ../reports/benefit_explainer.md
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from app.planner import baseline as B
from app.planner.search import search
from app.planner.shapley import shapley_shares
from app.planner.strategies import DONABACH_FLAT_FEE, menu
from app.schemas import Household
from app.sim import markets
from app.sim import simulate as sim
from app.sim.simulate import build_inputs, run_batch
from app.study.metrics import annualized
from app.tax import params_2026 as P

PROSE: dict[str, dict[str, str]] = {
    "fee": {
        "title": "Lower, flat fee",
        "mechanism": "Each year, after taxes are paid, the fee is charged on the whole portfolio (every account pro rata); the slice of taxable stock sold to pay it realizes its gain, reported on the next year's return. Donabach charges one flat rate. The good RIA's rate falls with the balance; the typical advisor's is higher below $500,000.",
        "formula": "fee = rate x total assets (Donabach); fee = sum over tiers of (marginal rate x the part of the balance in the tier) (the advisors).",
    },
    "location": {
        "title": "Asset location",
        "mechanism": "At every rebalance the private credit sleeve fills the pre-tax account first (then the Roth, then taxable), bonds fill what is left of the pre-tax account, the Roth holds stocks, and the taxable account takes the stocks that remain. The advisors hold the same mix in every account.",
        "formula": "The tax drag of an asset is its taxable yield times the marginal rate (bonds 3.5% of ordinary income, private credit the same, stocks 1.8% of qualified dividends plus realized gains); location puts the highest-yield holdings where that drag is not charged.",
    },
    "lots": {
        "title": "Highest-cost lots first (and gain harvesting, and gifts of lots)",
        "mechanism": "Stock in the taxable account is a set of lots. A sale takes the lot bought at the highest price first (the advisors: the oldest first). A lot held a year or less has a short-term gain (a lot sold in the year it was bought is wholly short-term, one sold the next year half), taxed as ordinary income. Each year the plan also realizes gains up to the top of the 0% capital-gain bracket by selling the lowest-cost lots and buying them back at once, and a household that gives to charity gives the lots with the most gain instead of cash.",
        "formula": "gain of a sale = sum over lots sold of units x (price - cost); gain harvested = min(room under the 0% bracket top, unrealized gain), at 0% tax; a gift of lots deducts the market value and realizes nothing.",
    },
    "harvest": {
        "title": "Loss harvesting stock by stock (direct indexing)",
        "mechanism": f"The taxable stock is {sim.N_STOCKS} stocks, each moving with the market and with its own random movement (volatility {markets.STOCK_IDIO_VOL:.0%} a year); a lot whose cost is more than {sim.HARVEST_THRESHOLD:.0%} above its stock's price is sold at a loss and bought back at once (a lot with a new cost). The loss offsets gains, then $3,000 of income a year, and the rest carries forward.",
        "formula": "loss harvested in a year = sum over lots with cost > (1 + threshold) x price of units x (cost - price); tax saved = marginal gain rate x loss, with the carryforward valued by the same engine at the horizon.",
    },
    "allocation": {
        "title": "Spending reserve, the rest in stocks",
        "mechanism": "Bonds and private credit hold the next N years of retirement spending net of Social Security (the goals of those years are in the goal bucket) and everything else is in stocks. In a year stocks fell, spending and goals are paid from the bonds and private credit of every account first, and nothing is sold to refill the reserve; in other years the rebalance refills it.",
        "formula": "safe share = max(sum over the next N years of need / portfolio, private credit share); stock share = 1 - safe share.",
    },
    "private_credit": {
        "title": "Private credit sleeve",
        "mechanism": f"A share of the portfolio in private credit (return {markets.DEFAULT_ASSUMPTIONS.means[2]:.1%} a year after inflation, volatility {markets.DEFAULT_ASSUMPTIONS.sds[2]:.0%}, correlation 0.5 with stocks), counted toward the reserve and held in the pre-tax account first, so its income is untaxed until withdrawal.",
        "formula": "return = mean + sd x z with z correlated with the stock return; the taxable yield is the mean plus inflation.",
    },
    "conversions": {
        "title": "Roth conversions",
        "mechanism": "Each year (or in low-income years and retirement) pre-tax money is converted in kind to Roth up to the top of the chosen bracket, paying the tax from the taxable account, cash and spare wages (never from the converted dollars).",
        "formula": "converted = min(top of bracket + deduction - other ordinary income, pre-tax balance, funds / marginal rate); the tax on it is the engine's, with Illinois subtracting it from its base.",
    },
    "withdrawals": {
        "title": "Tax-aware withdrawal order",
        "mechanism": "Spending is paid from pre-tax money up to the bracket target first, then the taxable account, then the Roth (before 59 1/2: taxable, Roth, then pre-tax with the 10% penalty).",
        "formula": "pre-tax drawn = min(need, bracket top + deduction - ordinary income so far).",
    },
    "k401": {
        "title": "Roth 401(k) contributions",
        "mechanism": "Contributions go to the Roth side (always, or only in low-income years): wages are taxed now, the extra tax comes out of savings first.",
        "formula": "extra tax = tax on wages with the contribution - tax on wages without it.",
    },
    "borrow": {
        "title": "Borrow for goals",
        "mechanism": f"A goal is paid with a box-spread loan against the taxable account (up to {P.BORROWING_LIMIT:.0%} of it; sold down to {P.BORROWING_LIMIT:.0%} if it reaches {P.BORROWING_FORCED_SALE_TRIGGER:.0%}) instead of selling; the loan is repaid from savings or by realizing gains in low-tax years. Interest is booked as a capital loss.",
        "formula": f"real rate = {P.SHORT_TERM_TREASURY_NOMINAL:.2%} (1-year Treasury) + {P.BOX_SPREAD_PREMIUM:.2%} - {P.ASSUMED_INFLATION:.0%} inflation = {P.BORROWING_RATE_REAL:.2%}.",
    },
}


def fee_text() -> str:
    good = ", ".join(f"{r:.1%} to ${t / 1e6:g}M" if t != float("inf") else f"{r:.1%} above" for t, r in zip(sim.FEE_TOPS, sim.FEE_RATES, strict=True))
    typical = ", ".join(
        f"{r:.2%} to ${t / 1e3:,.0f}k" if t != float("inf") else f"{r:.2%} above" for t, r in zip(sim.TYPICAL_FEE_TOPS, sim.TYPICAL_FEE_RATES, strict=True)
    )
    return f"Donabach {DONABACH_FLAT_FEE:.2%} flat; good RIA {good}; typical advisor {typical}."


ASSUMPTIONS = {
    "fee": lambda: fee_text(),
    "location": lambda: f"Bond interest yield {markets.BOND_INTEREST_YIELD:.1%}; dividend yield {markets.DIVIDEND_YIELD:.1%}; tax brackets, deductions and the 0/15/20% gain rates of 2026 held constant in real dollars.",
    "lots": lambda: "Short-term share of a lot's gain by its age: 1, 0.5, 0. The 0% bracket tops out at $98,900 of taxable income (married filing jointly, 2026). A gift of long-term stock is deducted at market value; a household that does not itemize may deduct $2,000 of cash gifts on top of the standard deduction.",
    "harvest": lambda: f"Idiosyncratic volatility {markets.STOCK_IDIO_VOL:.0%} (an assumption read from published figures for single US stocks); harvest threshold {sim.HARVEST_THRESHOLD:.0%}; the wash-sale rule and trading costs are not in the plan's numbers and are measured as checks in `reports/overstatement.md` (24% of harvested losses disallowed: a few hundredths of a point; trading costs of 0.10% a year: about 0.05 points).",
    "allocation": lambda: "Equity return 5.5% after inflation, volatility 16%; bonds 1.5% and 5%; correlations 0.1 (stocks-bonds), 0.5 (stocks-private credit). The liability-matched style chooses N under a limit of 2% of futures with a forced sale in a falling year.",
    "private_credit": lambda: "Return 3.5% after inflation, volatility 8% (the assumption review's figures; sensitivity 2% to 5%).",
    "conversions": lambda: "Brackets are held constant in real dollars; the survivor, after the first death, files single (narrower brackets).",
    "withdrawals": lambda: "Retirement spending net of Social Security is taken to be what the household states; Social Security is taxed by the provisional-income formula.",
    "k401": lambda: "The 401(k) limit of $24,500 (2026) and a contribution of at most 20% of wages.",
    "borrow": lambda: f"Box-spread rate {P.BORROWING_RATE_REAL:.2%} real; limit {P.BORROWING_LIMIT:.0%}; forced sale trigger {P.BORROWING_FORCED_SALE_TRIGGER:.0%}.",
}


def build(household: Household, name: str) -> str:
    chosen = search(build_inputs(household, n_paths=400, seed=2026), strategies=menu(style="equity_first")).best.strategy
    held = build_inputs(household, n_paths=1_000, seed=2026 + 1_000_003)
    shares = shapley_shares(held, chosen)
    total = sum(s.shapley_rate for s in shares)
    out = [
        "# What each strategy does, and what it did for the showcase household",
        "",
        f"Household: {name}. Plan: {chosen.short_label()}. Every number is the engine's, on {held.n_paths:,} futures the strategy search never saw; "
        "the bars are annual growth-rate advantages of median after-tax wealth at 80 over the good RIA.",
        "",
        "**Two attributions.** The *waterfall bar* switches the plan's strategies on one at a time in a fixed order, so a strategy that depends on another is "
        "credited with more or less depending on where it stands. The *Shapley share* averages a strategy's added advantage over every order, so it does not "
        f"depend on the order. Both add up to the plan's whole advantage ({total:+.2%} a year).",
        "",
        "| Strategy | Waterfall bar (a year) | Shapley share (a year) | In dollars of median wealth (Shapley) |",
        "|---|---|---|---|",
    ]
    for s in shares:
        out.append(f"| {s.label} | {s.sequential_rate:+.3%} | {s.shapley_rate:+.3%} | {s.shapley_dollars:+,.0f} |")
    out += ["", "A strategy with a negative bar and a positive share (or the reverse) is one whose worth depends on what it is combined with.", ""]
    keys = {"Lower, flat fee": "fee", "Asset location": "location", "Highest-cost lots first": "lots", "Loss harvesting stock by stock": "harvest",
            "private credit": "private_credit", "Roth conversions": "conversions", "Tax-aware withdrawal order": "withdrawals",
            "Roth 401(k)": "k401", "Borrow for goals": "borrow", "spending reserve": "allocation"}
    for s in shares:
        key = next((v for k, v in keys.items() if k in s.label), None)
        if key is None:
            continue
        p = PROSE[key]
        out += [
            f"## {p['title']}",
            "",
            f"**Mechanism, as implemented.** {p['mechanism']}",
            "",
            f"**Formula.** {p['formula']}",
            "",
            f"**Key assumptions.** {ASSUMPTIONS[key]()}",
            "",
            f"**{name}'s numbers.** Waterfall bar {s.sequential_rate:+.3%} a year ({s.sequential_dollars:+,.0f} of median wealth at 80); Shapley share {s.shapley_rate:+.3%} a year ({s.shapley_dollars:+,.0f}).",
            "",
        ]
    # tools measured on their own (switched off in the plan)
    plan = chosen.policy()
    b = run_batch(held, [plan, plan.replace(gain_harvesting=False), B.RIA_BASELINE])
    years = held.n_years
    median = [float(np.median(b.wealth[i])) for i in range(3)]
    out += [
        "## Gain harvesting in the 0% bracket (part of the lots step above)",
        "",
        f"Switched off on its own, the plan's advantage over the good RIA goes from {annualized(median[0], median[2], years):+.3%} to {annualized(median[1], median[2], years):+.3%} a year.",
        "",
    ]
    return "\n".join(out)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=Path("../reports/benefit_explainer.md"))
    ap.add_argument("--showcase", type=Path, default=Path("../fixtures/showcase.json"))
    args = ap.parse_args(argv)
    fixture = json.loads(args.showcase.read_text())
    household = Household.model_validate(fixture["household"])
    args.out.write_text(build(household, fixture.get("name", "the showcase household")) + "\n")
    print(args.out.read_text())


if __name__ == "__main__":
    main()
