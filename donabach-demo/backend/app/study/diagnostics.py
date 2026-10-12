"""Selling and liquidation diagnostics (Update 4, item 2).

    python -m app.study.diagnostics --out ../reports/diagnostics.md

For a household: search its plan (the app's default style, 400 futures, seed 2026), then run the plan and both advisors on 2,000
futures the search never saw with the simulator's diagnostics on, and report, for each of the three:

* the stock sold from the brokerage account over the plan, the gains it realized and the tax on them, by purpose;
* the realized gains of those very sales under highest-cost-first and under first-in-first-out (`app.sim.replay`);
* where the spending reserve is held, and the tax and penalty on paying expenses out of the pre-tax account;
* the unrealized gain left at the horizon and the tax charged on it when wealth is valued;
* the whole of the income tax, by the kind of income it was charged on.

Every figure is the average over the 2,000 futures (so that a column adds up), with the median beside it where a median is
what a household would call typical. Nothing here changes a result: the diagnostics only read what the simulator did.
"""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from app.planner import plan as planner
from app.planner.baseline import RIA_BASELINE, TYPICAL_ADVISOR
from app.planner.search import RISK_AVERSION, search
from app.planner.strategies import Strategy, menu
from app.schemas import Household
from app.sim import diag as D
from app.sim.replay import REPLAY_GAIN, REPLAY_GAIN_SHORT, REPLAY_UNREALIZED, replay_batch
from app.sim.simulate import Policy, SimInputs, build_inputs, run_batch
from app.sim.state import LOTS_FIFO, LOTS_HIFO
from app.tax import params_2026 as P

SEARCH_PATHS = 400
EVAL_PATHS = 2000
SEED = 2026
SALE_PURPOSES = [p for p in range(D.N_PURPOSES) if p not in (D.P_HARVEST, D.P_DISTRIBUTIONS)]
LABELS = {"plan": "Donabach plan", "good_ria": "Good RIA", "typical_advisor": "Typical advisor"}


@dataclass
class Subject:
    """One plan or advisor, as run."""

    key: str
    label: str
    policy: Policy


def plan_for(
    household: Household, search_paths: int = SEARCH_PATHS, seed: int = SEED, eval_paths: int = EVAL_PATHS, strategy: Strategy | None = None
) -> tuple[Strategy, SimInputs]:
    """The household's plan as the app finds it (or the given `strategy`), and the futures it is measured on (never the ones it was
    searched on)."""
    if strategy is None:
        futures = build_inputs(household, n_paths=search_paths, seed=seed)
        strategy = search(futures, strategies=menu(style=planner.DEFAULT_STYLE), risk_aversion=RISK_AVERSION).best.strategy
    return strategy, build_inputs(household, n_paths=eval_paths, seed=seed + planner.EVAL_SEED_OFFSET)


def subjects(strategy: Strategy) -> list[Subject]:
    return [
        Subject("plan", LABELS["plan"], strategy.policy()),
        Subject("good_ria", LABELS["good_ria"], RIA_BASELINE),
        Subject("typical_advisor", LABELS["typical_advisor"], TYPICAL_ADVISOR),
    ]


def _both(x: np.ndarray) -> dict[str, float]:
    return {"mean": float(np.mean(x)), "median": float(np.median(x))}


def summarize(subject: Subject, inputs: SimInputs, batch, replays: dict[str, np.ndarray], index: int) -> dict:
    """The diagnostics of subject number `index` of `batch` (run with diagnostics) as plain numbers."""
    d = batch.diag[index]
    sold = d[:, D.D_SOLD : D.D_SOLD + D.N_PURPOSES]
    gain = d[:, D.D_GAIN : D.D_GAIN + D.N_PURPOSES]
    tax = d[:, D.D_TAX : D.D_TAX + D.N_PURPOSES]
    total_sold = sold.sum(axis=1)
    purposes = []
    for p, name in enumerate(D.PURPOSES):
        purposes.append(
            {
                "purpose": name,
                "sold": float(sold[:, p].mean()),
                "share_of_sold": float(sold[:, p].mean() / total_sold.mean()) if total_sold.mean() > 0 else 0.0,
                "gain": float(gain[:, p].mean()),
                "tax": float(tax[:, p].mean()),
            }
        )
    sale_gain = gain[:, SALE_PURPOSES].sum(axis=1)
    hifo, fifo = replays["hifo"][index], replays["fifo"][index]
    unrealized = d[:, D.D_END_BE] - d[:, D.D_END_BASIS]
    valuation_tax = P.UNREALIZED_GAIN_TAX_RATE * np.maximum(0.0, unrealized)
    held = d[:, [D.D_RES_PRETAX, D.D_RES_ROTH, D.D_RES_BROKERAGE]]
    years = np.maximum(d[:, D.D_RES_YEARS], 1.0)
    average_held = held / years[:, None]
    start_held = d[:, [D.D_RES0_PRETAX, D.D_RES0_ROTH, D.D_RES0_BROKERAGE]]
    withdrawn = d[:, D.D_PTW : D.D_PTW + D.N_WITHDRAWALS]
    types = d[:, D.D_TYPE : D.D_TYPE + D.N_TYPES]
    penalty = d[:, D.D_PENALTY]
    return {
        "key": subject.key,
        "label": subject.label,
        "wealth_liquidated": _both(batch.wealth[index]),
        "wealth_heirs": _both(batch.wealth_heirs[index]),
        "lifetime_taxes_paid": _both(batch.taxes_paid[index]),
        "tax_owed_on_pretax_at_horizon": _both(batch.pretax_owed[index]),
        "sales": {
            "by_purpose": purposes,
            "total_sold": _both(total_sold),
            "total_gain": _both(gain.sum(axis=1)),
            "gain_from_sales": _both(sale_gain),
            "capital_gains_tax": _both(tax.sum(axis=1)),
            "gifts_in_kind": _both(d[:, D.D_DONATED]),
            "gain_given_away": _both(d[:, D.D_DONATED_GAIN]),
            "gifts_in_cash": _both(d[:, D.D_CASHGIFT]),
            "fund_distributions": _both(d[:, D.D_FUNDDIST]),
        },
        "lots": {
            "actual_gain_from_sales": _both(sale_gain),
            "hifo_gain": _both(hifo[:, REPLAY_GAIN]),
            "fifo_gain": _both(fifo[:, REPLAY_GAIN]),
            "hifo_short_term_gain": _both(hifo[:, REPLAY_GAIN_SHORT]),
            "fifo_short_term_gain": _both(fifo[:, REPLAY_GAIN_SHORT]),
            "hifo_unrealized_at_horizon": _both(hifo[:, REPLAY_UNREALIZED]),
            "fifo_unrealized_at_horizon": _both(fifo[:, REPLAY_UNREALIZED]),
            "gain_avoided_by_hifo": _both(fifo[:, REPLAY_GAIN] - hifo[:, REPLAY_GAIN]),
            "unrealized_added_by_hifo": _both(hifo[:, REPLAY_UNREALIZED] - fifo[:, REPLAY_UNREALIZED]),
            "run_used": subject.policy.lot_method + (" with harvesting" if subject.policy.tax_loss_harvesting else ""),
        },
        "reserve": {
            "average_pretax": float(average_held[:, 0].mean()),
            "average_roth": float(average_held[:, 1].mean()),
            "average_brokerage": float(average_held[:, 2].mean()),
            "at_retirement_pretax": float(start_held[:, 0].mean()),
            "at_retirement_roth": float(start_held[:, 1].mean()),
            "at_retirement_brokerage": float(start_held[:, 2].mean()),
        },
        "pretax_withdrawals": {
            "for_goals": float(withdrawn[:, D.W_GOALS].mean()),
            "for_spending": float(withdrawn[:, D.W_SPENDING].mean()),
            "for_gifts": float(withdrawn[:, D.W_GIFTS].mean()),
            "for_taxes": float(withdrawn[:, D.W_TAXES].mean()),
            "required": float(withdrawn[:, D.W_REQUIRED].mean()),
            "before_59_and_a_half": float(d[:, D.D_EARLY].mean()),
            "early_withdrawal_penalty": _both(penalty),
            "futures_with_a_penalty": float(np.mean(penalty > 0.0)),
            "tax_on_optional_withdrawals_with_penalty": float(types[:, D.T_WITHDRAWALS].mean()),
        },
        "horizon": {
            "unrealized_gain": _both(unrealized),
            "tax_charged_when_liquidated": _both(valuation_tax),
            "tax_charged_when_passed_to_heirs": {"mean": 0.0, "median": 0.0},
            "brokerage_equity": _both(d[:, D.D_END_BE]),
            "basis": _both(d[:, D.D_END_BASIS]),
        },
        "taxes_by_type": {
            "by_type": [{"type": name, "tax": float(types[:, k].mean())} for k, name in enumerate(D.TAX_TYPES)],
            "total": _both(types.sum(axis=1)),
            "tax_on_wages_alone": float(d[:, D.D_WAGETAX].mean()),
        },
    }


def diagnose(
    household: Household, name: str, search_paths: int = SEARCH_PATHS, seed: int = SEED, eval_paths: int = EVAL_PATHS, strategy: Strategy | None = None
) -> dict:
    """Everything for one household: its plan, and the three subjects' diagnostics."""
    started = time.perf_counter()
    strategy, inputs = plan_for(household, search_paths, seed, eval_paths, strategy)
    people = subjects(strategy)
    policies = [s.policy for s in people]
    batch = run_batch(inputs, policies, diagnostics=True)
    replays = {"hifo": replay_batch(inputs, policies, batch, LOTS_HIFO), "fifo": replay_batch(inputs, policies, batch, LOTS_FIFO)}
    return {
        "household": name,
        "strategy": strategy.short_label(),
        "choices": strategy.choices(),
        "n_paths": inputs.n_paths,
        "years": household.horizon_years,
        "retirement_age": household.goals.retirement_age,
        "age": household.primary_age,
        "giving": household.goals.charitable_giving,
        "subjects": [summarize(s, inputs, batch, replays, i) for i, s in enumerate(people)],
        "seconds": time.perf_counter() - started,
    }


# --- The report --------------------------------------------------------------------------------------------------


def _m(x: float) -> str:
    return f"${x:,.0f}" if x >= 0 else f"-${-x:,.0f}"


def _k(x: float) -> str:
    return f"${x / 1000:,.0f}k" if x >= 0 else f"-${-x / 1000:,.0f}k"


def render(result: dict) -> str:
    subs = result["subjects"]
    heads = [s["label"] for s in subs]
    out = [f"### {result['household']}", ""]
    out.append(
        f"The plan: {result['strategy']}. Households aged {result['age']}, retiring at {result['retirement_age']}, "
        f"{result['years']} years to 80, {result['n_paths']:,} futures the plan was not searched on. "
        + (f"Annual giving ${result['giving']:,.0f}. " if result["giving"] else "No charitable giving. ")
        + "Dollars are real 2026 dollars, summed over the plan and averaged over the futures."
    )
    out.append("")

    out.append("**A. Stock sold from the brokerage account, by purpose** (sold / gain realized / capital-gains tax)")
    out.append("")
    out.append("| Purpose | " + " | ".join(heads) + " |")
    out.append("|---|" + "---|" * len(heads))
    for p, name in enumerate(D.PURPOSES):
        cells = []
        for s in subs:
            row = s["sales"]["by_purpose"][p]
            if abs(row["sold"]) < 0.5 and abs(row["gain"]) < 0.5 and abs(row["tax"]) < 0.5:
                cells.append("—")
            elif p in (D.P_HARVEST, D.P_DISTRIBUTIONS):
                cells.append(f"(no sale) / {_k(row['gain'])} / {_k(row['tax'])}")
            else:
                cells.append(f"{_k(row['sold'])} / {_k(row['gain'])} / {_k(row['tax'])}")
        out.append(f"| {name[0].upper() + name[1:]} | " + " | ".join(cells) + " |")
    totals = [
        f"**{_k(s['sales']['total_sold']['mean'])}** / **{_k(s['sales']['total_gain']['mean'])}** / **{_k(s['sales']['capital_gains_tax']['mean'])}**"
        for s in subs
    ]
    out.append("| **Total** | " + " | ".join(totals) + " |")
    out.append("")
    out.append(
        "Gains are net of harvested losses and fund distributions (shown on their own lines). The tax on gains is the year's tax on its "
        "gains (the tax with them less the tax without), shared among that year's sales in proportion to their gains; losses harvested "
        "get the tax they saved, which is negative. A gain realized selling for the tax or the fee is reported, and taxed, the next year."
    )
    out.append("")

    out.append("**B. The same sales under highest-cost-first and first-in-first-out** (lifetime gain realized by the sales / still unrealized at 80)")
    out.append("")
    out.append("| | " + " | ".join(heads) + " |")
    out.append("|---|" + "---|" * len(heads))

    def row(label: str, f) -> None:
        out.append(f"| {label} | " + " | ".join(f(s) for s in subs) + " |")

    row("What the run did", lambda s: f"{s['lots']['run_used']}: {_k(s['lots']['actual_gain_from_sales']['mean'])} realized")
    row("Replayed highest cost first", lambda s: f"{_k(s['lots']['hifo_gain']['mean'])} / {_k(s['lots']['hifo_unrealized_at_horizon']['mean'])}")
    row("Replayed first in, first out", lambda s: f"{_k(s['lots']['fifo_gain']['mean'])} / {_k(s['lots']['fifo_unrealized_at_horizon']['mean'])}")
    row("Gain avoided by highest cost first", lambda s: _k(s["lots"]["gain_avoided_by_hifo"]["mean"]))
    row("Unrealized gain it leaves behind", lambda s: _k(s["lots"]["unrealized_added_by_hifo"]["mean"]))
    out.append("")
    out.append(
        "Both replays use the run's own dollars sold and bought, year by year, with the same returns and stock movements, no loss "
        "harvesting and no taxes worked out again: only which lots a sale takes differs. A gain is realized now or left for later, so "
        "the two columns of each replay add up to the same total."
    )
    out.append("")

    out.append("**C. Where the spending reserve is held, and paying expenses out of the pre-tax account**")
    out.append("")
    out.append("| | " + " | ".join(heads) + " |")
    out.append("|---|" + "---|" * len(heads))

    def reserve(s, key):
        r = s["reserve"]
        parts = [r[f"{key}_pretax"], r[f"{key}_roth"], r[f"{key}_brokerage"]]
        total = sum(parts)
        if total <= 0:
            return "—"
        return " / ".join(f"{_k(x)} ({x / total * 100:.0f}%)" for x in parts)

    row("Reserve held, pre-tax / Roth / brokerage, average over retired years", lambda s: reserve(s, "average"))
    row("Reserve held at the end of the first retired year", lambda s: reserve(s, "at_retirement"))
    row("Pre-tax withdrawn for goals / spending / gifts / taxes", lambda s: " / ".join(_k(s["pretax_withdrawals"][k]) for k in ("for_goals", "for_spending", "for_gifts", "for_taxes")))
    row("Required minimum distributions", lambda s: _k(s["pretax_withdrawals"]["required"]))
    row("Pre-tax withdrawn before 59½", lambda s: _k(s["pretax_withdrawals"]["before_59_and_a_half"]))
    row("Early-withdrawal penalty (futures with one)", lambda s: f"{_m(s['pretax_withdrawals']['early_withdrawal_penalty']['mean'])} ({s['pretax_withdrawals']['futures_with_a_penalty'] * 100:.0f}%)")
    row("Tax on pre-tax withdrawals other than required ones, penalty included", lambda s: _k(s["pretax_withdrawals"]["tax_on_optional_withdrawals_with_penalty"]))
    out.append("")
    out.append("The reserve is the bonds and private credit (and the goal bucket) the household holds; asset location puts them in the pre-tax account first.")
    out.append("")

    out.append("**D. Unrealized brokerage gain at 80, and the tax charged on it**")
    out.append("")
    out.append("| | " + " | ".join(heads) + " |")
    out.append("|---|" + "---|" * len(heads))
    row("Unrealized gain at 80 (mean / median)", lambda s: f"{_k(s['horizon']['unrealized_gain']['mean'])} / {_k(s['horizon']['unrealized_gain']['median'])}")
    row("Tax charged when everything is liquidated (15%)", lambda s: _k(s["horizon"]["tax_charged_when_liquidated"]["mean"]))
    row("Tax charged when passed to heirs (step-up)", lambda s: "$0")
    row("After-tax wealth at 80, liquidated (median)", lambda s: _k(s["wealth_liquidated"]["median"]))
    row("After-tax wealth at 80, passed to heirs (median)", lambda s: _k(s["wealth_heirs"]["median"]))
    out.append("")

    out.append("**E. Lifetime income tax, by the kind of income it was charged on**")
    out.append("")
    out.append("| | " + " | ".join(heads) + " |")
    out.append("|---|" + "---|" * len(heads))
    for k, name in enumerate(D.TAX_TYPES):
        out.append(f"| {name[0].upper() + name[1:]} | " + " | ".join(_k(s["taxes_by_type"]["by_type"][k]["tax"]) for s in subs) + " |")
    out.append("| **Total income tax paid** | " + " | ".join(f"**{_k(s['taxes_by_type']['total']['mean'])}**" for s in subs) + " |")
    out.append("| Tax on wages alone, in that | " + " | ".join(_k(s["taxes_by_type"]["tax_on_wages_alone"]) for s in subs) + " |")
    out.append("| Tax still owed on the pre-tax balance at 80 (valuation) | " + " | ".join(_k(s["tax_owed_on_pretax_at_horizon"]["mean"]) for s in subs) + " |")
    out.append("")
    out.append(
        "The income is stacked in the order the tax is worked out (wages, interest and Social Security; pre-tax withdrawals; required "
        "distributions; conversions; short-term gains; dividends; long-term gains) and each kind's share is what it added to the tax, so "
        "the rows add up to the total exactly. The charitable deduction's saving comes last and is negative."
    )
    out.append("")
    return "\n".join(out)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--out", default="../reports/diagnostics.md")
    parser.add_argument("--json-dir", default="../reports/diagnostics")
    parser.add_argument("--giving", type=float, default=0.0, help="annual charitable giving to give the households")
    args = parser.parse_args()
    from app import showcase
    from app.study.measure import sample_household

    households = {
        "The Tanaka family (the showcase household)": showcase.load_fixture().household,
        "Alex and Jordan Sample (the sample household)": sample_household(),
    }
    json_dir = Path(args.json_dir)
    json_dir.mkdir(parents=True, exist_ok=True)
    sections = []
    for name, household in households.items():
        if args.giving:
            household = household.model_copy(update={"goals": household.goals.model_copy(update={"charitable_giving": args.giving})})
        result = diagnose(household, name)
        slug = name.split(" (")[0].lower().replace(" ", "_")
        (json_dir / f"{slug}.json").write_text(json.dumps(result, indent=2))
        sections.append(render(result))
        print(f"{name}: {result['seconds']:.1f} s")
    Path(args.out).write_text("\n".join(sections))


if __name__ == "__main__":
    main()
