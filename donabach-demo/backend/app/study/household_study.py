"""The household-type study (spec A10): the planner on 300 synthetic households of six types.

    python -m app.study.household_study --per-type 50 --out-dir ../reports

For each household: search the strategy menu on 400 futures, then score the winner and both
advisors on `n_eval` fresh futures the search never saw. Writes `household_study.csv` (one row per
household) and `household_study.md` (the summary by type). Nothing is tuned.

Annualized advantage and the two measures are defined in `app.study.metrics`.
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import numpy as np
import pandas as pd

from app.planner.baseline import BASELINES
from app.planner.search import RISK_AVERSION, WEALTH_FLOOR, search
from app.sim.simulate import build_inputs, run_batch
from app.study import households as hh
from app.study.metrics import compare

EVAL_SEED_OFFSET = 1_000_003
DEFAULT_N_EVAL = 1_000


def household_row(item: hh.StudyHousehold, position: int, n_search: int, n_eval: int, risk_aversion: float) -> dict:
    household = item.household
    seed = 5_000 + position
    years = household.horizon_years
    futures = build_inputs(household, n_paths=n_search, seed=seed)
    chosen = search(futures, risk_aversion=risk_aversion).best.strategy
    held = build_inputs(household, n_paths=n_eval, seed=seed + EVAL_SEED_OFFSET)
    policies = [chosen.policy(), *(b.policy for b in BASELINES)]
    batch = run_batch(held, policies)
    a = household.accounts
    liquid = household.liquid_wealth
    row = {
        "type": item.type,
        "index": item.index,
        "note": item.note,
        "age": household.primary_age,
        "wages": household.total_wages,
        "liquid_wealth": liquid,
        "pretax": a.pretax_balance,
        "roth": a.roth_balance,
        "brokerage": a.brokerage_value,
        "basis_ratio": a.brokerage_basis / a.brokerage_value if a.brokerage_value else 0.0,
        "cash": a.cash,
        "retirement_age": household.goals.retirement_age,
        "years": years,
        "strategy": chosen.short_label(),
        **{f"choice_{k}": v for k, v in chosen.choices().items()},
        "plan_median": float(np.median(batch.wealth[0])),
        "plan_p10": float(np.percentile(batch.wealth[0], 10)),
        "plan_taxes": float(np.median(batch.taxes_paid[0] + batch.pretax_owed[0])),
        "plan_shortfall": float(np.mean(batch.unfunded[0] > 0)),
    }
    for i, baseline in enumerate(BASELINES, start=1):
        adv = compare(batch.wealth[0], batch.wealth[i], years, risk_aversion)
        key = baseline.key
        row[f"{key}_median"] = adv.baseline_median
        row[f"{key}_p10"] = float(np.percentile(batch.wealth[i], 10))
        row[f"{key}_taxes"] = float(np.median(batch.taxes_paid[i] + batch.pretax_owed[i]))
        row[f"{key}_shortfall"] = float(np.mean(batch.unfunded[i] > 0))
        row[f"adv_median_vs_{key}"] = adv.median
        row[f"adv_risk_adjusted_vs_{key}"] = adv.risk_adjusted
    # households that run out of money in most futures: the floored objective stops being informative
    row["underfunded"] = bool(row["plan_median"] < WEALTH_FLOOR)
    return row


def run(
    per_type: int = 50,
    n_search: int = 400,
    n_eval: int = DEFAULT_N_EVAL,
    risk_aversion: float = RISK_AVERSION,
    seed: int = 10,
    progress: bool = False,
) -> pd.DataFrame:
    items = hh.generate(seed=seed, per_type=per_type)
    rows = []
    started = time.perf_counter()
    for position, item in enumerate(items):
        rows.append(household_row(item, position, n_search, n_eval, risk_aversion))
        if progress and (position + 1) % 25 == 0:
            elapsed = time.perf_counter() - started
            print(f"  {position + 1}/{len(items)} households ({elapsed / (position + 1):.1f}s each)", flush=True)
    return pd.DataFrame(rows)


def _pct(x: float) -> str:
    return f"{x * 100:+.2f}%"


def _share(frame: pd.DataFrame, column: str, predicate) -> float:
    return float(frame[column].map(predicate).mean())


def summarize(frame: pd.DataFrame, n_eval: int, risk_aversion: float) -> str:
    lines = [
        "# Household-type study",
        "",
        f"{len(frame)} synthetic households ({frame.groupby('type').size().iloc[0]} of each of six types), all fictional. For each, the planner searched",
        f"its strategy menu on 400 simulated futures and the winner was scored against both advisors on {n_eval:,} fresh",
        f"futures it never saw (risk aversion {risk_aversion:g}). Nothing was tuned; the households were drawn from fixed ranges",
        "that make each a clear example of its type (see `backend/app/study/households.py`).",
        "",
        "* **Median advantage**: difference in median after-tax wealth at the horizon, annualized as a growth-rate difference.",
        "* **Risk-adjusted advantage**: the same on certainty-equivalent wealth (the planner's objective).",
        "* Each cell is the **median across the households of that type** (with the 10th to 90th percentile across households).",
        "  Dollar-weighted or pooled figures would differ; this is the typical household of the type.",
        "",
    ]
    for baseline in BASELINES:
        key = baseline.key
        lines += [
            f"## Against the {baseline.label.lower()}",
            "",
            f"{baseline.definition}",
            "",
            "| Type | Households | Median advantage | Risk-adjusted advantage | Share ahead on median | Share ahead risk-adjusted |",
            "|---|---|---|---|---|---|",
        ]
        for t, title in hh.TYPES.items():
            sub = frame[frame["type"] == t]
            m = sub[f"adv_median_vs_{key}"]
            r = sub[f"adv_risk_adjusted_vs_{key}"]
            lines.append(
                f"| {title} | {len(sub)} | {_pct(m.median())} ({_pct(m.quantile(0.1))} to {_pct(m.quantile(0.9))}) | "
                f"{_pct(r.median())} ({_pct(r.quantile(0.1))} to {_pct(r.quantile(0.9))}) | "
                f"{(m > 0).mean() * 100:.0f}% | {(r > 0).mean() * 100:.0f}% |"
            )
        m, r = frame[f"adv_median_vs_{key}"], frame[f"adv_risk_adjusted_vs_{key}"]
        lines += [
            f"| **All {len(frame)} households** | {len(frame)} | **{_pct(m.median())}** ({_pct(m.quantile(0.1))} to {_pct(m.quantile(0.9))}) | "
            f"**{_pct(r.median())}** ({_pct(r.quantile(0.1))} to {_pct(r.quantile(0.9))}) | {(m > 0).mean() * 100:.0f}% | {(r > 0).mean() * 100:.0f}% |",
            "",
        ]

    lines += [
        "## What the planner chose, by type",
        "",
        "Share of households of each type whose winning strategy uses each option.",
        "",
        "| Type | Lowest stock share (50%) | Stock share 80%+ | Roth conversions | Private credit 15% | Direct indexing | Goal bonds | Roth 401(k) (any) | Borrow for goals |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for t, title in hh.TYPES.items():
        sub = frame[frame["type"] == t]
        lines.append(
            f"| {title} | {_share(sub, 'choice_stock_share', lambda v: v == '50') * 100:.0f}% | "
            f"{_share(sub, 'choice_stock_share', lambda v: int(v) >= 80) * 100:.0f}% | "
            f"{_share(sub, 'choice_conversion', lambda v: v != 'none') * 100:.0f}% | "
            f"{_share(sub, 'choice_private_credit', lambda v: v == '15') * 100:.0f}% | "
            f"{_share(sub, 'choice_direct_indexing', lambda v: v == 'on') * 100:.0f}% | "
            f"{_share(sub, 'choice_goal_bonds', lambda v: v == 'on') * 100:.0f}% | "
            f"{_share(sub, 'choice_k401', lambda v: v != 'pretax') * 100:.0f}% | "
            f"{_share(sub, 'choice_goal_funding', lambda v: v == 'borrow') * 100:.0f}% |"
        )
    lines += [
        "",
        "## Reading these numbers",
        "",
        f"* **Underfunded households.** {int(frame['underfunded'].sum())} of {len(frame)} households have a median after-tax wealth at the horizon below the "
        f"${WEALTH_FLOOR:,.0f} floor: their plans run out of money in most futures. With a floored objective losing more costs nothing, so "
        "for them the risk-adjusted figures are not informative. Chance of running out of money (a shortfall in at least one future) by type: "
        + ", ".join(
            f"{title.split(' (')[0].split(',')[0]} {frame[frame['type'] == t]['plan_shortfall'].mean() * 100:.1f}% for the plan vs "
            f"{frame[frame['type'] == t]['good_ria_shortfall'].mean() * 100:.1f}% for the good RIA"
            for t, title in hh.TYPES.items()
        )
        + ".",
        "* **Concentrated single stock.** The simulator holds all brokerage equity as the diversified market, so the extra "
        "risk of one stock is not modelled; for that type the result reflects the tax side only, and understates the value of diversifying.",
        "* **Not modelled:** survivor years and heirs' taxes (both favor Roth conversions).",
        "",
    ]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--per-type", type=int, default=50)
    parser.add_argument("--n-eval", type=int, default=DEFAULT_N_EVAL)
    parser.add_argument("--seed", type=int, default=10)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    frame = run(per_type=args.per_type, n_eval=args.n_eval, seed=args.seed, progress=True)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    frame.to_csv(args.out_dir / "household_study.csv", index=False)
    text = summarize(frame, args.n_eval, RISK_AVERSION)
    (args.out_dir / "household_study.md").write_text(text)
    print(text)


if __name__ == "__main__":
    main()
