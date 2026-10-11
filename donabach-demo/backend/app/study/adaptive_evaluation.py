"""The four-way evaluation (spec B5) for one household, and the value of judgment over time.

    python -m app.study.adaptive_evaluation --paths 2000 --out ../reports/adaptive_evaluation.md

On the same held-out futures (ones the strategy search never saw) it compares

1. the **typical advisor** baseline,
2. the **good RIA** baseline,
3. the **best fixed strategy** (what the search chooses from the planning style's strategy menu), and
4. the **adaptive planner**: the best fixed strategy with each year's decisions re-chosen after that year's
   returns, by rollout search,

by median and risk-adjusted advantage, the 10th-percentile outcome, lifetime taxes and the chance of running out of money. The adaptive
planner's addition over the best fixed strategy is the **value of judgment over time**: it is reported with the 90% range
over resamples of the futures, split into the part that comes from tax timing and the part from allocation, for several numbers of
rollouts, and for several sets of futures, so a reader can see how much of it is signal.
"""

from __future__ import annotations

import argparse
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from app.planner import explain
from app.planner.baseline import GOOD_RIA, TYPICAL
from app.planner.search import RISK_AVERSION, WEALTH_FLOOR, certainty_equivalent, search
from app.planner.strategies import Strategy, menu
from app.schemas import Household
from app.sim import adaptive as ad
from app.sim.simulate import SimInputs, build_inputs, run_batch
from app.study import metrics
from app.study.measure import sample_household

EVAL_SEED_OFFSET = 1_000_003
TAX_TIMING = ("conversion", "realize_gains", "goal_funding", "k401")
ALLOCATION = ("private_credit", "stock_share")
LABELS = {"typical_advisor": "Typical advisor", "good_ria": "Good RIA", "best_fixed": "Best fixed strategy", "adaptive": "Adaptive planner"}


@dataclass
class FourWay:
    """Four strategies on the same futures."""

    years: int
    risk_aversion: float
    wealth: dict[str, np.ndarray]
    taxes: dict[str, np.ndarray]
    unfunded: dict[str, np.ndarray]
    adaptive: ad.AdaptiveResult
    strategy: Strategy

    def row(self, key: str) -> dict[str, float]:
        w = self.wealth[key]
        return {
            "median": float(np.median(w)),
            "ce": float(certainty_equivalent(w, self.risk_aversion, WEALTH_FLOOR)),
            "p10": float(np.percentile(w, 10)),
            "taxes": float(np.median(self.taxes[key])),
            "shortfall": float(np.mean(self.unfunded[key] > 0)),
        }

    def advantage(self, key: str, over: str, with_range: bool = True) -> metrics.Advantage:
        return metrics.compare(self.wealth[key], self.wealth[over], self.years, self.risk_aversion, WEALTH_FLOOR, with_range=with_range)

    @property
    def judgment(self) -> metrics.Advantage:
        """The adaptive planner against the best fixed strategy: the value of judgment over time."""
        return self.advantage("adaptive", "best_fixed")


def four_way(
    household: Household,
    strategy: Strategy,
    evaluation: SimInputs,
    settings: ad.AdaptiveSettings | None = None,
    adaptive_result: ad.AdaptiveResult | None = None,
) -> FourWay:
    """Run the baselines, the best fixed strategy and the adaptive planner on `evaluation`'s futures."""
    settings = settings or ad.AdaptiveSettings()
    policy = strategy.policy()
    batch = run_batch(evaluation, [policy, GOOD_RIA.policy, TYPICAL.policy])
    result = adaptive_result or ad.run_adaptive(evaluation, policy, settings)
    keys = ("best_fixed", "good_ria", "typical_advisor")
    wealth = {key: batch.wealth[i] for i, key in enumerate(keys)} | {"adaptive": result.wealth}
    taxes = {key: batch.taxes_paid[i] + batch.pretax_owed[i] for i, key in enumerate(keys)} | {"adaptive": result.taxes_paid + result.pretax_owed}
    unfunded = {key: batch.unfunded[i] for i, key in enumerate(keys)} | {"adaptive": result.unfunded}
    return FourWay(household.horizon_years, settings.risk_aversion, wealth, taxes, unfunded, result, strategy)


def best_fixed_strategy(household: Household, seed: int = 2026, risk_aversion: float = RISK_AVERSION, style: str = "balanced") -> Strategy:
    return search(build_inputs(household, n_paths=400, seed=seed), strategies=menu(style=style), risk_aversion=risk_aversion).best.strategy


def _pct(x: float, digits: int = 2) -> str:
    return f"{x * 100:+.{digits}f}%"


def _money(x: float) -> str:
    return f"${x:,.0f}"


def _range(r: tuple[float, float]) -> str:
    return f"({_pct(r[0])} to {_pct(r[1])})"


def four_way_table(fw: FourWay) -> list[str]:
    lines = [
        "| Strategy | Median after-tax wealth at 80 | Certainty equivalent | 10th percentile | Lifetime taxes (median) | Chance of running out of money |",
        "|---|---|---|---|---|---|",
    ]
    for key in LABELS:
        r = fw.row(key)
        lines.append(f"| {LABELS[key]} | {_money(r['median'])} | {_money(r['ce'])} | {_money(r['p10'])} | {_money(r['taxes'])} | {r['shortfall']:.1%} |")
    lines += [
        "",
        "| Strategy | Median advantage over the typical advisor | Risk-adjusted advantage over the typical advisor | Median advantage over the good RIA | Risk-adjusted advantage over the good RIA |",
        "|---|---|---|---|---|",
    ]
    for key in ("good_ria", "best_fixed", "adaptive"):
        t, g = fw.advantage(key, "typical_advisor"), fw.advantage(key, "good_ria")
        lines.append(
            f"| {LABELS[key]} | {_pct(t.median)} {_range(t.median_range)} | {_pct(t.risk_adjusted)} {_range(t.risk_adjusted_range)} | "
            f"{_pct(g.median)} {_range(g.median_range)} | {_pct(g.risk_adjusted)} {_range(g.risk_adjusted_range)} |"
        )
    return lines


def judgment_line(j: metrics.Advantage) -> str:
    return (
        f"median {_pct(j.median)}/yr {_range(j.median_range)} ({_money(j.median_dollars)} at 80); "
        f"risk-adjusted {_pct(j.risk_adjusted)}/yr {_range(j.risk_adjusted_range)} ({_money(j.risk_adjusted_dollars)} at 80)"
    )


def attribution(strategy: Strategy, evaluation: SimInputs, years: int, risk_aversion: float = RISK_AVERSION) -> list[tuple[str, float, float, float, float]]:
    """Where the best fixed strategy's advantage over the good RIA comes from: the decisions switched on one at a time
    from the baseline (`explain.advantage_policies`), cumulative, on the same futures. Each row: label, median wealth at
    the horizon, certainty equivalent, and the two annualized advantages over the baseline."""
    steps = explain.advantage_policies(strategy)
    wealth = run_batch(evaluation, [policy for _, policy in steps]).wealth
    base_median, base_ce = float(np.median(wealth[0])), float(certainty_equivalent(wealth[0], risk_aversion, WEALTH_FLOOR))
    rows = []
    for (label, _), w in zip(steps, wealth, strict=True):
        median, ce = float(np.median(w)), float(certainty_equivalent(w, risk_aversion, WEALTH_FLOOR))
        rows.append((label, median, ce, metrics.annualized(median, base_median, years), metrics.annualized(ce, base_ce, years)))
    return rows


@dataclass
class Evaluation:
    household: Household
    strategy: Strategy
    main: FourWay
    n_paths: int
    steps: list[tuple[str, float, float, float, float]]
    decomposition: dict[str, metrics.Advantage]
    by_rollouts: dict[int, tuple[metrics.Advantage, float]]  # rollouts -> (value of judgment, seconds per 100 paths)
    by_futures: list[tuple[int, metrics.Advantage]]  # evaluation seed -> value of judgment
    seconds_per_100_paths: float


def run(
    n_paths: int = 2_000,
    seed: int = 2026,
    rollouts: tuple[int, ...] = (64, 128),
    extra_seeds: tuple[int, ...] = (1, 2),
    risk_aversion: float = RISK_AVERSION,
    progress: bool = False,
    style: str = "balanced",
) -> Evaluation:
    household = sample_household()
    strategy = best_fixed_strategy(household, seed, risk_aversion, style)
    evaluation = build_inputs(household, n_paths=n_paths, seed=seed + EVAL_SEED_OFFSET)
    settings = ad.AdaptiveSettings(risk_aversion=risk_aversion)

    def log(text: str) -> None:
        if progress:
            print(f"  {text}", flush=True)

    started = time.perf_counter()
    main = four_way(household, strategy, evaluation, settings)
    per_100 = (time.perf_counter() - started) / n_paths * 100.0
    log(f"main run done: {judgment_line(main.judgment)}")

    decomposition = {}
    for name, dims in (("tax timing only", TAX_TIMING), ("allocation only", ALLOCATION)):
        only = ad.run_adaptive(evaluation, strategy.policy(), ad.AdaptiveSettings(risk_aversion=risk_aversion, dimensions=dims))
        decomposition[name] = metrics.compare(only.wealth, main.wealth["best_fixed"], household.horizon_years, risk_aversion, WEALTH_FLOOR, with_range=True)
        log(f"{name}: {judgment_line(decomposition[name])}")
    decomposition["all six decisions"] = main.judgment

    by_rollouts = {settings.rollouts: (main.judgment, per_100)}
    for k in rollouts:
        t0 = time.perf_counter()
        r = ad.run_adaptive(evaluation, strategy.policy(), ad.AdaptiveSettings(k=k, risk_aversion=risk_aversion))
        by_rollouts[k] = (
            metrics.compare(r.wealth, main.wealth["best_fixed"], household.horizon_years, risk_aversion, WEALTH_FLOOR, with_range=True),
            (time.perf_counter() - t0) / n_paths * 100.0,
        )
        log(f"K={k}: {judgment_line(by_rollouts[k][0])}")

    by_futures = [(seed, main.judgment)]
    for extra in extra_seeds:
        other = build_inputs(household, n_paths=n_paths, seed=seed + extra * 7_919 + EVAL_SEED_OFFSET)
        fw = four_way(household, strategy, other, settings)
        by_futures.append((seed + extra * 7_919, fw.judgment))
        log(f"futures {extra}: {judgment_line(fw.judgment)}")
    steps = attribution(strategy, evaluation, household.horizon_years, risk_aversion)
    return Evaluation(household, strategy, main, n_paths, steps, decomposition, by_rollouts, by_futures, per_100)


def report(ev: Evaluation) -> str:
    fw = ev.main
    j = fw.judgment
    lines = [
        "# Four-way evaluation and the value of judgment over time (sample household)",
        "",
        "Generated by `python -m app.study.adaptive_evaluation`. Nothing was tuned toward a result.",
        "",
        "* Household: the demo household (two earners aged 38 and 37; $150k brokerage, $400k pre-tax, $30k Roth, $40k cash; a home purchase in 3 years, college in 10, retirement at 62). Horizon: age 80 (42 years).",
        f"* Best fixed strategy (what the search chooses from the {'1,008-strategy equity-first' if ev.strategy.reserve_years else '4,032-strategy'} menu): **{ev.strategy.describe()}**",
        f"* Evaluation: {ev.n_paths:,} simulated futures the search never saw; every strategy is run on the same futures. Risk aversion {fw.risk_aversion:g}; wealth below $50,000 counts as $50,000 in the certainty equivalent.",
        f"* The adaptive planner runs at the defaults: {ad.DEFAULT_K} rollouts per candidate, two coordinate-search passes, each proposed change re-tested on {ad.AdaptiveSettings().confirm_rollouts} fresh futures. "
        f"It took {ev.seconds_per_100_paths:.1f} seconds per 100 paths on this machine's 4 cores.",
        "* Advantages are annualized growth-rate differences (see `app/study/metrics.py`); ranges are the 5th to 95th percentile over resamples of the futures.",
        "",
        "## The four strategies",
        "",
        *four_way_table(fw),
        "",
        "## Where the best fixed strategy's advantage over the good RIA comes from",
        "",
        "The decisions switched on one at a time starting from the good RIA, cumulatively, on the same futures: what each step adds to median wealth and to certainty-equivalent wealth at 80, annualized.",
        "",
        "| Step | Median wealth at 80 | Median advantage | Certainty equivalent | Risk-adjusted advantage |",
        "|---|---|---|---|---|",
        *[f"| {label} | {_money(median)} | {_pct(adv_m)} | {_money(ce)} | {_pct(adv_ce)} |" for label, median, ce, adv_m, adv_ce in ev.steps],
        "",
        "The lower-risk allocation and private credit step is where the risk-adjusted advantage is made, and it *costs* median wealth: the plan holds the lowest stock share on the menu "
        "and a private-credit sleeve, which lowers the middle of the distribution and, above all, the chance of running out of money (certainty-equivalent wealth is dominated by that tail).",
        "",
        "## What judgment over time adds",
        "",
        f"The adaptive planner against the best fixed strategy, on the same futures: {judgment_line(j)}.",
        "",
        "### Where it comes from",
        "",
        "The planner restricted to some of its decisions (the others follow the fixed strategy):",
        "",
        "| Decisions the planner may change | Median advantage over best fixed | Risk-adjusted advantage over best fixed |",
        "|---|---|---|",
    ]
    for name, a in ev.decomposition.items():
        lines.append(f"| {name} | {_pct(a.median)} {_range(a.median_range)} | {_pct(a.risk_adjusted)} {_range(a.risk_adjusted_range)} |")
    lines += [
        "",
        "Tax timing: Roth conversions, realizing gains in the 0% bracket, how a goal is paid, the 401(k) type. Allocation: stock share and private credit.",
        "",
        "### More rollouts per candidate",
        "",
        "| Rollouts per candidate | Median advantage over best fixed | Risk-adjusted advantage over best fixed | Seconds per 100 paths |",
        "|---|---|---|---|",
    ]
    for k, (a, secs) in sorted(ev.by_rollouts.items()):
        lines.append(f"| {k} | {_pct(a.median)} {_range(a.median_range)} | {_pct(a.risk_adjusted)} {_range(a.risk_adjusted_range)} | {secs:.1f} |")
    lines += [
        "",
        "### Other futures",
        "",
        "The same household, strategy and planner on three independent sets of futures:",
        "",
        "| Futures (seed) | Median advantage over best fixed | Risk-adjusted advantage over best fixed |",
        "|---|---|---|",
    ]
    for s, a in ev.by_futures:
        lines.append(f"| {s} | {_pct(a.median)} {_range(a.median_range)} | {_pct(a.risk_adjusted)} {_range(a.risk_adjusted_range)} |")
    lines += [""]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--paths", type=int, default=2_000)
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--rollouts", default="64,128", help="extra numbers of rollouts to compare, comma-separated ('' for none)")
    parser.add_argument("--extra-seeds", type=int, default=2, help="additional independent sets of futures")
    parser.add_argument("--style", choices=("balanced", "equity_first"), default="balanced", help="the planning style whose menu the best fixed strategy is chosen from")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    rollouts = tuple(int(x) for x in args.rollouts.split(",") if x)
    ev = run(args.paths, args.seed, rollouts, tuple(range(1, args.extra_seeds + 1)), progress=True, style=args.style)
    text = report(ev)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(text)
    print(text)


if __name__ == "__main__":
    main()
