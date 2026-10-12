"""Update 4, 12.9: checks for overstatement. The chosen plan of each household, fixed, on the same fresh futures, with one assumption
that could be flattering Donabach made less so: direct-indexing trading costs, the wash-sale rule, a lower private-credit return, a
more volatile private-credit sleeve, and less (or more) stock-specific movement behind the harvesting. The advantage over the good
RIA is read at each; nothing is tuned and the plan is not searched again, so what moves is the assumption's own worth to the plan.

    python -m app.study.overstatement --out ../reports/overstatement.md
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from app.planner.baseline import RIA_BASELINE
from app.planner.search import search
from app.planner.strategies import menu
from app.schemas import Household
from app.sim import markets
from app.sim.simulate import ModelOptions, build_inputs, run_batch
from app.study.measure import sample_household
from app.study.metrics import compare


def variants() -> list[tuple[str, ModelOptions]]:
    base = markets.DEFAULT_ASSUMPTIONS
    pc = lambda mean=None, sd=None: markets.Assumptions(  # noqa: E731
        means=(base.means[0], base.means[1], base.means[2] if mean is None else mean),
        sds=(base.sds[0], base.sds[1], base.sds[2] if sd is None else sd),
    )
    return [
        ("as specified", ModelOptions()),
        ("direct indexing costs 0.10% a year in trading", ModelOptions(di_fee_premium=0.001)),
        ("direct indexing costs 0.15% a year in trading", ModelOptions(di_fee_premium=0.0015)),
        ("wash-sale rule disallows 24% of harvested losses", ModelOptions(harvest_haircut=0.24)),
        ("private credit returns 2.0% (not 3.5%)", ModelOptions(market=pc(mean=0.02))),
        ("private credit returns 5.0%", ModelOptions(market=pc(mean=0.05))),
        ("private credit volatility 12% (not 8%)", ModelOptions(market=pc(sd=0.12))),
        ("stocks' own movement 15% a year (not 25%)", ModelOptions(idio_vol=0.15)),
        ("stocks' own movement 35% a year", ModelOptions(idio_vol=0.35)),
        ("trading cost 0.10%, wash sale 24% and private credit 2.0% together", ModelOptions(di_fee_premium=0.001, harvest_haircut=0.24, market=pc(mean=0.02))),
    ]


def measure(household: Household) -> list[tuple[str, float, float, float]]:
    chosen = search(build_inputs(household, n_paths=400, seed=2026), strategies=menu(style="equity_first")).best.strategy
    rows = []
    for label, options in variants():
        held = build_inputs(household, n_paths=2_000, seed=2026 + 1_000_003, options=options)
        b = run_batch(held, [chosen.policy(), RIA_BASELINE])
        c = compare(b.wealth[0], b.wealth[1], household.horizon_years, 3.0)
        rows.append((label, c.median, c.risk_adjusted, float(np.mean(b.unfunded[0] > 0))))
    return rows, chosen.short_label()


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--showcase", type=Path, default=Path("../fixtures/showcase.json"))
    args = ap.parse_args(argv)
    tanaka = Household.model_validate(json.loads(args.showcase.read_text())["household"])
    lines = ["# Overstatement checks", "", "The plan chosen under the specified assumptions, held fixed, on 2,000 fresh futures; one assumption changed at a time. Median and risk-adjusted advantage over the good RIA, a year.", ""]
    for name, household in (("The showcase household (Tanaka)", tanaka), ("The sample household", sample_household())):
        rows, plan = measure(household)
        lines += [f"## {name}", "", f"Plan: {plan}.", "", "| Assumption | Median advantage | Risk-adjusted | Ruin chance |", "|---|---|---|---|"]
        base = rows[0][1]
        for label, median, ra, ruin in rows:
            delta = "" if label == rows[0][0] else f" ({(median - base) * 100:+.2f} points)"
            lines.append(f"| {label} | {median:.2%}{delta} | {ra:.2%} | {ruin:.1%} |")
        lines.append("")
    args.out.write_text("\n".join(lines) + "\n")
    print(args.out.read_text())


if __name__ == "__main__":
    main()
