"""Update 4, section 4: the biggest gap Donabach can open over the good RIA, two ways, with no assumption changed.

For a household the search takes every strategy of every planning style (balanced, equity-first, liability-matched: one menu with
the duplicates removed) and picks, on the futures it searches (the held-out design: 400 futures; the picks are then measured on 2,000
others):

* unconstrained: the strategy with the highest median after-tax wealth at the horizon, whatever its risk;
* risk-matched: the strategy with the highest median among those whose chance of running out of money is no higher than the good
  RIA's and whose 10th-percentile wealth is no lower than the good RIA's.

The adaptive planner (a policy that chooses each year's action after seeing the year) is a different kind of object and is measured
by `app.study.adaptive_evaluation`; it is not part of this menu search.

    python -m app.study.max_gap --per-type 4 --out ../reports/max_gap
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd

from app.planner.baseline import RIA_BASELINE, TYPICAL_ADVISOR
from app.planner.search import median_wealth, search, subset_inputs
from app.planner.strategies import STYLES, Strategy, menu
from app.schemas import Household
from app.sim.simulate import BatchResult, build_inputs, run_batch
from app.study import households as hh_module
from app.study.metrics import compare

SEARCH_PATHS = 400
EVAL_PATHS = 2_000
SEED = 2026
EVAL_OFFSET = 1_000_003


def full_menu() -> list[Strategy]:
    seen: dict[str, Strategy] = {}
    for style in STYLES:
        for s in menu(style=style):
            seen.setdefault(s.key, s)
    return list(seen.values())


def _p10(w: np.ndarray) -> np.ndarray:
    return np.percentile(w, 10, axis=-1)


def picks(household: Household, strategies: list[Strategy]) -> dict[str, Strategy | None]:
    futures = build_inputs(household, n_paths=SEARCH_PATHS, seed=SEED)
    advisor = run_batch(futures, [RIA_BASELINE])
    adv_ruin = float(np.mean(advisor.unfunded[0] > 0))
    adv_p10 = float(np.percentile(advisor.wealth[0], 10))
    screen_advisor = run_batch(subset_inputs(futures, 100), [RIA_BASELINE])
    screen_ruin = float(np.mean(screen_advisor.unfunded[0] > 0))
    screen_p10 = float(np.percentile(screen_advisor.wealth[0], 10))

    unconstrained = search(futures, strategies=strategies, criterion=median_wealth).best.strategy

    def screen_mask(batch: BatchResult) -> np.ndarray:  # the screen keeps those that look feasible on its 100 futures (a little slack)
        return (np.mean(batch.unfunded > 0, axis=1) <= screen_ruin + 0.02) & (_p10(batch.wealth) >= 0.9 * screen_p10)

    result = search(futures, strategies=strategies, criterion=median_wealth, screen_mask=screen_mask)
    n = len(result.strategies)
    ruin = np.mean(result.batch.unfunded[:n] > 0, axis=1)
    p10 = _p10(result.batch.wealth[:n])
    ok = (ruin <= adv_ruin + 1e-12) & (p10 >= adv_p10)
    matched = next((r.strategy for r in result.ranked if ok[result.index_of(r.strategy)]), None)
    return {"unconstrained": unconstrained, "risk_matched": matched}


def measure(household: Household, strategy: Strategy | None) -> dict:
    if strategy is None:
        return {"found": False}
    held = build_inputs(household, n_paths=EVAL_PATHS, seed=SEED + EVAL_OFFSET)
    b = run_batch(held, [strategy.policy(), RIA_BASELINE, TYPICAL_ADVISOR])
    years = household.horizon_years
    a = compare(b.wealth[0], b.wealth[1], years, 3.0)
    t = compare(b.wealth[0], b.wealth[2], years, 3.0)
    return {
        "found": True,
        "strategy": strategy.short_label(),
        "reserve_years": strategy.reserve_years,
        "stock_share": strategy.stock_share,
        "median_vs_ria": a.median,
        "risk_adjusted_vs_ria": a.risk_adjusted,
        "median_vs_typical": t.median,
        "risk_adjusted_vs_typical": t.risk_adjusted,
        "ruin": float(np.mean(b.unfunded[0] > 0)),
        "ria_ruin": float(np.mean(b.unfunded[1] > 0)),
        "p10": float(np.percentile(b.wealth[0], 10)),
        "ria_p10": float(np.percentile(b.wealth[1], 10)),
        "forced_sale": float(np.mean(b.forced_years[0] > 0)),
    }


def study_households(per_type: int, showcase: Path | None) -> list[tuple[str, str, Household]]:
    out: list[tuple[str, str, Household]] = []
    if showcase is not None and showcase.exists():
        out.append(("showcase", "Tanaka", Household.model_validate(json.loads(showcase.read_text())["household"])))
    taken: dict[str, int] = {}
    for item in hh_module.generate(seed=10, per_type=50):
        if taken.get(item.type, 0) < per_type:
            taken[item.type] = taken.get(item.type, 0) + 1
            out.append((item.type, f"{item.type}-{item.index}", item.household))
    return out


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-type", type=int, default=4)
    ap.add_argument("--out", type=Path, default=Path("../reports/max_gap"))
    ap.add_argument("--showcase", type=Path, default=Path("../fixtures/showcase.json"))
    args = ap.parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)
    strategies = full_menu()
    rows = []
    for kind, name, household in study_households(args.per_type, args.showcase):
        t0 = time.perf_counter()
        chosen = picks(household, strategies)
        for rule, strategy in chosen.items():
            rows.append({"type": kind, "household": name, "rule": rule, **measure(household, strategy)})
        print(f"{name:22s} {time.perf_counter() - t0:5.0f}s", flush=True)
    frame = pd.DataFrame(rows)
    frame.to_csv(args.out / "max_gap.csv", index=False)
    (args.out / "max_gap.md").write_text(summarize(frame))
    print((args.out / "max_gap.md").read_text())


def summarize(frame: pd.DataFrame) -> str:
    def pct(x: float) -> str:
        return f"{x * 100:.2f}%"

    lines = [
        "# Maximum gap, two ways",
        "",
        f"Every strategy of every planning style ({len(full_menu()):,} after removing duplicates), picked on {SEARCH_PATHS} futures and measured on "
        f"{EVAL_PATHS:,} others, over the good RIA. *Unconstrained*: highest median wealth at the horizon. *Risk-matched*: highest median "
        "among strategies whose chance of running out of money is no higher than the advisor's and whose 10th-percentile wealth is no lower. "
        "Advantages are annualized (median after-tax wealth, and the certainty equivalent at risk aversion 3).",
        "",
        "| Household type | Rule | Median adv. vs RIA | Risk-adj. adv. vs RIA | Ruin chance (RIA) | 10th pct vs RIA's | Forced-sale chance | Households |",
        "|---|---|---|---|---|---|---|---|",
    ]
    found = frame[frame["found"] == True]  # noqa: E712
    for (kind, rule), g in found.groupby(["type", "rule"], sort=False):
        lines.append(
            f"| {kind} | {rule.replace('_', '-')} | {pct(g.median_vs_ria.mean())} | {pct(g.risk_adjusted_vs_ria.mean())} | "
            f"{pct(g.ruin.mean())} ({pct(g.ria_ruin.mean())}) | {g.p10.mean() / g.ria_p10.mean():.2f}x | {pct(g.forced_sale.mean())} | {len(g)} |"
        )
    missing = frame[frame["found"] == False]  # noqa: E712
    if len(missing):
        lines += ["", f"No strategy met the risk-matched limits for {len(missing)} household(s): " + ", ".join(sorted(missing.household)) + "."]
    lines += ["", "## Showcase household", ""]
    for _, r in frame[frame["type"] == "showcase"].iterrows():
        if r["found"]:
            lines.append(f"* **{r['rule'].replace('_', '-')}**: {r['strategy']}: {pct(r.median_vs_ria)} a year at the median, {pct(r.risk_adjusted_vs_ria)} risk-adjusted; ruin {pct(r.ruin)} (RIA {pct(r.ria_ruin)}).")
        else:
            lines.append(f"* **{r['rule'].replace('_', '-')}**: no strategy met the limits.")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    main()
