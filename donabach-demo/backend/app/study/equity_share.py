"""Is the plan holding too little equity? The raw (median) advantage against how much equity a plan holds.

    python -m app.study.equity_share --out ../reports/equity_share.md

The planner's objective is certainty-equivalent wealth (risk aversion 3, $50,000 floor), which a handful of
futures in which money runs out dominate; it picks the lowest stock share on the menu. That costs median
wealth, so the median ("raw") advantage over the good advisor is a few tenths of a percent a year. This
study measures, without changing anything the app does:

1. how the raw and the risk-adjusted advantage move with the stock share (and with the private credit
   sleeve), holding every other choice at the recommendation's;
2. what Donabach's tools (fee, asset location, conversions, withdrawal order, goal funding) are worth on
   their own, with the advisor's own allocation, so the part of the advantage that is not extra risk is visible;
3. what each objective picks (risk aversion 5 down to 0.5, expected wealth, median wealth) and what it delivers;
4. the best raw advantage among plans that are at least as good as the advisor on the risk-adjusted measure,
   and among plans that run out of money no more often than the advisor and have no worse bad case;
5. the same advantage as the extra yearly return the advisor's portfolio would have needed;
6. how all of it moves if the equity assumption is more optimistic (never used by the app).

Plans are chosen on 2,000 futures and scored on 2,000 other futures the choice never saw. Both advantages
are annualized growth-rate differences (`app.study.metrics`); "risk-adjusted" is always at risk aversion 3
unless a column says otherwise. Nothing here is tuned toward a result.
"""

from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass, field, replace
from pathlib import Path

import numpy as np

from app.planner.baseline import RIA_BASELINE
from app.planner.search import RISK_AVERSION, WEALTH_FLOOR, certainty_equivalent, search
from app.planner.strategies import STOCK_SHARES, Strategy, menu
from app.sim import markets
from app.sim.simulate import DONABACH_FLAT_FEE, GLIDE_END_AGE, ModelOptions, Policy, SimInputs, build_inputs, run_batch, run_detail
from app.study.measure import EVAL_SEED_OFFSET, sample_household
from app.study.metrics import Advantage, compare

DESIGN_SEED_OFFSET = 7_000_001  # the futures plans are chosen on: neither the app's search nor the held-out futures
GAMMAS = (5.0, 3.0, 2.0, 1.0, 0.5)
EXPOSURE_AGES = (None, 58.0, 70.0)  # None: today
RA_THRESHOLDS = (None, 0.0, 0.5, 1.0, 1.5, 2.0, 2.5)  # risk-adjusted advantage a plan must reach (None: no requirement)


def equity_exposure(policy: Policy, age: float, current_age: float) -> float:
    """Share of the whole portfolio in stocks at `age`.

    The stock share is of long-term money; with Donabach asset location the private credit sleeve is carved out
    first, so stocks are `share x (1 - sleeve)` of the portfolio. The advisor holds no private credit.
    """
    glide_start = current_age if policy.glide_start_age is None else policy.glide_start_age
    if age <= glide_start:
        share = policy.stock_share
    else:
        share = policy.stock_share - policy.glide_drop * min(1.0, (age - glide_start) / (GLIDE_END_AGE - glide_start))
    return share * (1.0 - policy.private_credit) if policy.donabach_location else share


def exposure_of(policy: Policy, inputs: SimInputs, detail: SimInputs | None = None) -> tuple[float, ...]:
    """Stocks as a share of the portfolio today, at 58 and from 70. A fixed share and glide have a formula; with a spending
    reserve the share moves with the household's expenses, so it is read off the plan's own year log on `detail` (a
    deterministic path)."""
    current = inputs.current_age
    if policy.reserve_years and detail is not None:
        share = run_detail(detail, policy).log["equity_share"]
        last = len(share) - 1

        def at(age: float) -> int:
            return min(max(0, int(age - current)), last)

        return (float(share[0]), float(share[at(58.0)]), float(np.median(share[at(70.0):])))
    return tuple(equity_exposure(policy, age or current, current) for age in EXPOSURE_AGES)


def annualized(plan: np.ndarray | float, baseline: float, years: int) -> np.ndarray | float:
    """Yearly growth-rate difference that turns `baseline` into `plan` over `years` (vectorized)."""
    return (np.asarray(plan, dtype=float) / baseline) ** (1.0 / years) - 1.0


# --------------------------------------------------------------------------------------------
# Scoring the whole menu once, then choosing by any rule
# --------------------------------------------------------------------------------------------


@dataclass
class MenuScores:
    strategies: list[Strategy]
    median: np.ndarray
    p10: np.ndarray
    mean: np.ndarray
    shortfall: np.ndarray  # share of futures in which an obligation could not be funded
    ce: dict[float, np.ndarray]  # certainty-equivalent wealth by risk aversion


def score_menu(
    inputs: SimInputs, strategies: list[Strategy], gammas: tuple[float, ...] = GAMMAS, chunk: int = 600
) -> MenuScores:
    """Every strategy on every future (no screening), summarized per strategy."""
    n = len(strategies)
    median, p10, mean, shortfall = (np.empty(n) for _ in range(4))
    ce = {g: np.empty(n) for g in gammas}
    for start in range(0, n, chunk):
        part = strategies[start : start + chunk]
        batch = run_batch(inputs, [s.policy() for s in part])
        w = batch.wealth
        sl = slice(start, start + len(part))
        median[sl] = np.median(w, axis=1)
        p10[sl] = np.percentile(w, 10, axis=1)
        mean[sl] = w.mean(axis=1)
        shortfall[sl] = (batch.unfunded > 0).mean(axis=1)
        for g in gammas:
            ce[g][sl] = certainty_equivalent(w, g)
    return MenuScores(strategies, median, p10, mean, shortfall, ce)


def pick(values: np.ndarray, feasible: np.ndarray | None = None) -> int | None:
    """Index of the largest value among the feasible strategies (the first in menu order on a tie); None if none."""
    if feasible is not None:
        if not feasible.any():
            return None
        values = np.where(feasible, values, -np.inf)
    return int(np.argmax(values))


# --------------------------------------------------------------------------------------------
# Scoring chosen plans on the held-out futures
# --------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Result:
    label: str
    policy: Policy
    exposure: tuple[float, ...]  # stocks as a share of the portfolio today, at 58 and from 70
    median: float
    p10: float
    shortfall: float
    raw: Advantage  # against the good advisor
    adjusted: Advantage  # the same at risk aversion 3 (`raw` carries the median; this one is read for `risk_adjusted`)
    own: Advantage | None  # the same at the plan's own risk aversion, where it has one
    note: str = ""


def evaluate(
    held: SimInputs,
    rows: list[tuple[str, Policy, float | None]],
    notes: list[str] | None = None,
    baseline: Policy = RIA_BASELINE,
    detail: SimInputs | None = None,
) -> list[Result]:
    """Score `rows` (label, policy, the risk aversion it was chosen at) against `baseline` (the good advisor) on `held`.
    `detail` is a deterministic path, used to read the stock exposure of plans with a spending reserve."""
    years = held.n_years
    batch = run_batch(held, [baseline, *(policy for _, policy, _ in rows)])
    w = batch.wealth
    out = []
    for i, (label, policy, gamma) in enumerate(rows, start=1):
        out.append(
            Result(
                label=label,
                policy=policy,
                exposure=exposure_of(policy, held, detail),
                median=float(np.median(w[i])),
                p10=float(np.percentile(w[i], 10)),
                shortfall=float(np.mean(batch.unfunded[i] > 0)),
                raw=compare(w[i], w[0], years, RISK_AVERSION, WEALTH_FLOOR, with_range=True),
                adjusted=compare(w[i], w[0], years, RISK_AVERSION, WEALTH_FLOOR),
                own=compare(w[i], w[0], years, gamma, WEALTH_FLOOR) if gamma is not None else None,
                note=(notes[i - 1] if notes else ""),
            )
        )
    return out


def baseline_result(held: SimInputs) -> Result:
    batch = run_batch(held, [RIA_BASELINE])
    w = batch.wealth[0]
    zero = compare(w, w, held.n_years, RISK_AVERSION, WEALTH_FLOOR)
    return Result(
        "Good advisor",
        RIA_BASELINE,
        tuple(equity_exposure(RIA_BASELINE, age or held.current_age, held.current_age) for age in EXPOSURE_AGES),
        float(np.median(w)),
        float(np.percentile(w, 10)),
        float(np.mean(batch.unfunded[0] > 0)),
        zero,
        zero,
        None,
    )


# --------------------------------------------------------------------------------------------
# The advantage as the extra yearly return the advisor would have needed
# --------------------------------------------------------------------------------------------


def return_equivalent(held: SimInputs, target_median: float, baseline: Policy = RIA_BASELINE, tol: float = 1e-6) -> float:
    """The extra real return, every year on every asset, that the baseline would have needed to end with
    `target_median` as its median after-tax wealth at the horizon (bisection; 0 if it already does)."""

    def median_at(extra: float) -> float:
        shifted = replace(held, rets=np.maximum(held.rets + extra, markets.MIN_RETURN))
        return float(np.median(run_batch(shifted, [baseline]).wealth[0]))

    if median_at(0.0) >= target_median:
        return 0.0
    low, high = 0.0, 0.10
    while median_at(high) < target_median and high < 0.5:
        high *= 2.0
    while high - low > tol:
        mid = 0.5 * (low + high)
        if median_at(mid) < target_median:
            low = mid
        else:
            high = mid
    return 0.5 * (low + high)


# --------------------------------------------------------------------------------------------
# The studies
# --------------------------------------------------------------------------------------------


def advisor_allocation_chain(chosen: Strategy) -> list[tuple[str, Policy]]:
    """Donabach's tools switched on one at a time, cumulatively, with the allocation left at the advisor's own."""
    target = chosen.policy()
    p0 = RIA_BASELINE
    p1 = p0.replace(breakpoint_fees=False, flat_fee=DONABACH_FLAT_FEE)
    p2 = p1.replace(donabach_location=True)
    p3 = p2.replace(direct_indexing=target.direct_indexing)
    p4 = p3.replace(goal_bonds=target.goal_bonds)
    p5 = p4.replace(
        conversion_top=target.conversion_top,
        conversion_every_year=target.conversion_every_year,
        bracket_withdrawals=target.bracket_withdrawals,
        withdrawal_top=target.withdrawal_top,
        k401=target.k401,
        goal_funding=target.goal_funding,
    )
    return [
        ("Lower fee (0.35% flat)", p1),
        ("+ asset location", p2),
        ("+ direct indexing" if target.direct_indexing else "+ direct indexing (not used)", p3),
        ("+ goal bonds" if target.goal_bonds else "+ goal bonds (not used)", p4),
        ("+ Roth conversions, withdrawal order, 401(k) type, goal funding", p5),
    ]


def objectives(scores: MenuScores) -> list[tuple[str, np.ndarray, float | None]]:
    """(label, the value each strategy is ranked by, its risk aversion) for each objective compared."""
    return [
        ("risk aversion 5", scores.ce[5.0], 5.0),
        ("risk aversion 3 (the app's setting)", scores.ce[3.0], 3.0),
        ("risk aversion 2", scores.ce[2.0], 2.0),
        ("risk aversion 1", scores.ce[1.0], 1.0),
        ("risk aversion 0.5 (the lowest the API accepts)", scores.ce[0.5], 0.5),
        ("expected wealth (no risk adjustment)", scores.mean, None),
        ("median wealth (the raw measure itself)", scores.median, None),
    ]


@dataclass
class Study:
    chosen: Strategy  # the app's own recommendation (400 futures, seed 2026)
    sweep: list[Result]
    chain: list[Result]
    frontier: list[Result]
    pareto: list[Result]
    tail_matched: Result | None
    baseline: Result
    return_equivalents: list[tuple[str, float, float]]  # (plan, extra yearly return the advisor needs, raw advantage)
    seconds: float
    n_design: int = 0
    n_eval: int = 0
    reserve_frontier: list[Result] = field(default_factory=list)  # what each objective picks among the spending-reserve plans


def run_study(
    n_design: int = 6000,
    n_eval: int = 2000,
    seed: int = markets.DEFAULT_SEED,
    market: markets.Assumptions | None = None,
    strategies: list[Strategy] | None = None,
    with_return_equivalents: bool = True,
    progress=None,
) -> Study:
    started = time.perf_counter()
    say = progress or (lambda message: None)
    household = sample_household()
    options = ModelOptions(market=market)
    years = household.horizon_years
    strategies = strategies if strategies is not None else menu()

    # What the app itself recommends (its own futures), the starting point for the sweep.
    chosen = search(build_inputs(household, n_paths=400, seed=seed, options=options), strategies=strategies).best.strategy
    say(f"app recommendation: {chosen.short_label()}")

    design = build_inputs(household, n_paths=n_design, seed=seed + DESIGN_SEED_OFFSET, options=options)
    held = build_inputs(household, n_paths=n_eval, seed=seed + EVAL_SEED_OFFSET, options=options)
    det = build_inputs(household, deterministic=True, options=options)
    scores = score_menu(design, strategies)
    say(f"scored {len(strategies)} strategies on {n_design} futures")
    ria_design = run_batch(design, [RIA_BASELINE])
    ria_p10 = float(np.percentile(ria_design.wealth[0], 10))
    ria_short = float(np.mean(ria_design.unfunded[0] > 0))
    ria_ce3 = float(certainty_equivalent(ria_design.wealth[0], RISK_AVERSION))

    # 1. The sweep: stock share and private credit, everything else as the recommendation's.
    sweep_rows: list[tuple[str, Policy, float | None]] = []
    for sleeve in sorted({0.0, chosen.private_credit}):
        for share in STOCK_SHARES:
            strategy = replace(chosen, stock_share=share, private_credit=sleeve)
            mark = " (the balanced recommendation)" if strategy == chosen else ""
            sweep_rows.append((f"{round(share * 100)}% stocks, {round(sleeve * 100)}% private credit{mark}", strategy.policy(), None))
    sweep = evaluate(held, sweep_rows, detail=det)

    # 2. Donabach's tools at the advisor's own allocation.
    chain_steps = advisor_allocation_chain(chosen)
    chain = evaluate(held, [(label, policy, None) for label, policy in chain_steps])

    # 3. What each objective picks.
    frontier_rows: list[tuple[str, Policy, float | None]] = []
    notes: list[str] = []
    for label, values, gamma in objectives(scores):
        index = pick(values)
        frontier_rows.append((label, scores.strategies[index].policy(), gamma))
        notes.append(scores.strategies[index].short_label())
    frontier = evaluate(held, frontier_rows, notes, detail=det)

    # 3b. The same objectives among the spending-reserve plans (the app's default planning style).
    reserve_menu = menu(style="equity_first")
    reserve_scores = score_menu(design, reserve_menu)
    reserve_rows: list[tuple[str, Policy, float | None]] = []
    reserve_notes: list[str] = []
    for label, values, gamma in objectives(reserve_scores):
        index = pick(values)
        reserve_rows.append((label, reserve_menu[index].policy(), gamma))
        reserve_notes.append(reserve_menu[index].short_label())
    reserve_frontier = evaluate(held, reserve_rows, reserve_notes, detail=det)

    # 4a. The best raw advantage among plans at least as good as the advisor risk-adjusted by a given amount.
    ra_design = annualized(scores.ce[RISK_AVERSION], ria_ce3, years)
    pareto_rows: list[tuple[str, Policy, float | None]] = []
    pareto_notes: list[str] = []
    for threshold in RA_THRESHOLDS:
        feasible = None if threshold is None else ra_design >= threshold / 100.0
        index = pick(scores.median, feasible)
        label = "no requirement" if threshold is None else f"risk-adjusted advantage at least {threshold:+.1f}%"
        if index is None:
            continue
        pareto_rows.append((label, scores.strategies[index].policy(), None))
        pareto_notes.append(scores.strategies[index].short_label())
    pareto = evaluate(held, pareto_rows, pareto_notes)

    # 4b. The best raw advantage among plans that run out of money no more often than the advisor does and
    # whose bad case (10th percentile) is no worse.
    feasible = (scores.shortfall <= ria_short + 1e-12) & (scores.p10 >= ria_p10)
    index = pick(scores.median, feasible)
    tail_matched = None
    if index is not None:
        tail_matched = evaluate(
            held,
            [("no more shortfalls and no worse bad case than the advisor", scores.strategies[index].policy(), None)],
            [scores.strategies[index].short_label()],
        )[0]

    # 5. The same advantages as the extra yearly return the advisor would have needed.
    equivalents: list[tuple[str, float, float]] = []
    if with_return_equivalents:
        shown = [*sweep, *chain[-1:], *frontier, *pareto, *([tail_matched] if tail_matched else [])]
        done: set[tuple[float, float]] = set()
        for result in shown:
            key = (round(result.median, 2), round(result.p10, 2))
            if key in done:  # the same plan reached by another route
                continue
            done.add(key)
            equivalents.append((result.label, return_equivalent(held, result.median), result.raw.median))
        say("return equivalents done")

    return Study(
        chosen=chosen,
        sweep=sweep,
        chain=chain,
        frontier=frontier,
        pareto=pareto,
        tail_matched=tail_matched,
        baseline=baseline_result(held),
        return_equivalents=equivalents,
        seconds=time.perf_counter() - started,
        n_design=n_design,
        n_eval=n_eval,
        reserve_frontier=reserve_frontier,
    )


# --------------------------------------------------------------------------------------------
# The equity assumption (sensitivity only)
# --------------------------------------------------------------------------------------------

SPEC_MARKET = markets.DEFAULT_ASSUMPTIONS
MARKET_SCENARIOS = (
    ("Equity 4.5% real (a point lower)", replace(SPEC_MARKET, means=(0.045, *SPEC_MARKET.means[1:]))),
    ("Equity 5.5% real (as specified)", SPEC_MARKET),
    ("Equity 6.5% real (a point higher)", replace(SPEC_MARKET, means=(0.065, *SPEC_MARKET.means[1:]))),
    ("Equity 7.5% real (two points higher)", replace(SPEC_MARKET, means=(0.075, *SPEC_MARKET.means[1:]))),
)


def market_sensitivity(n_design: int = 6000, n_eval: int = 2000, progress=None) -> list[tuple[str, list[Result]]]:
    """For each equity assumption: the app's pick (risk aversion 3), the most equity the menu allows, and what
    maximizes the median. Futures are redrawn under the assumption; the advisor is on the same futures."""
    say = progress or (lambda message: None)
    household = sample_household()
    out = []
    for name, market in MARKET_SCENARIOS:
        options = ModelOptions(market=market)
        design = build_inputs(household, n_paths=n_design, seed=markets.DEFAULT_SEED + DESIGN_SEED_OFFSET, options=options)
        held = build_inputs(household, n_paths=n_eval, seed=markets.DEFAULT_SEED + EVAL_SEED_OFFSET, options=options)
        strategies = menu()
        scores = score_menu(design, strategies, gammas=(RISK_AVERSION,))
        app_pick = scores.strategies[pick(scores.ce[RISK_AVERSION])]
        median_pick = scores.strategies[pick(scores.median)]
        rows = [
            ("The app's pick (risk aversion 3)", app_pick.policy(), RISK_AVERSION),
            ("The same, 100% stocks, no private credit", replace(app_pick, stock_share=1.0, private_credit=0.0).policy(), None),
            ("The same, 100% stocks, 15% private credit", replace(app_pick, stock_share=1.0, private_credit=0.15).policy(), None),
            ("Maximizes median wealth", median_pick.policy(), None),
        ]
        notes = [app_pick.short_label(), "", "", median_pick.short_label()]
        out.append((name, evaluate(held, rows, notes)))
        say(f"market scenario done: {name}")
    return out


# --------------------------------------------------------------------------------------------
# The report
# --------------------------------------------------------------------------------------------


def _pct(x: float, digits: int = 2) -> str:
    return f"{x * 100:+.{digits}f}%"


def _dollars(x: float) -> str:
    return f"${x:,.0f}"


def _exposure(result: Result) -> str:
    today, at_58, from_70 = result.exposure
    return f"{today:.0%} / {at_58:.0%} / {from_70:.0%}"


def _table(results: list[Result], own_gamma: bool = False, plan_column: bool = False) -> list[str]:
    head = ["Plan"]
    if plan_column:
        head.append("What it holds")
    head += ["Stocks today / at 58 / from 70", "Median wealth at 80", "Raw (median) advantage", "Risk-adjusted advantage (risk aversion 3)"]
    if own_gamma:
        head.append("Risk-adjusted at its own risk aversion")
    head += ["10th percentile", "Chance of running out of money"]
    lines = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    for r in results:
        cells = [r.label]
        if plan_column:
            cells.append(r.note)
        low, high = r.raw.median_range
        cells += [
            _exposure(r),
            _dollars(r.median),
            f"{_pct(r.raw.median)} ({_pct(low)} to {_pct(high)})" if r.raw.median_range != (0.0, 0.0) else _pct(r.raw.median),
            _pct(r.adjusted.risk_adjusted),
        ]
        if own_gamma:
            cells.append(_pct(r.own.risk_adjusted) if r.own is not None else "n/a")
        cells += [_dollars(r.p10), f"{r.shortfall:.1%}"]
        lines.append("| " + " | ".join(cells) + " |")
    return lines


def render(study: Study, sensitivity: list[tuple[str, list[Result]]] | None = None) -> str:
    lines = [
        "# Is the plan holding too little equity?",
        "",
        "Generated by `python -m app.study.equity_share`. Nothing was tuned toward a result, and nothing the app does was changed.",
        "",
        "* Household: the demo household (two earners aged 38 and 37; a home purchase in 3 years, college in 10, retirement at 62). Horizon: age 80.",
        f"* Plans are chosen on {study.n_design:,} futures and scored on {study.n_eval:,} other futures they never saw; the good advisor is on the same futures as every plan.",
        f"* The balanced planning style's recommendation (the app's earlier default; risk aversion 3, 400 futures, seed 2026): **{study.chosen.describe()}**. "
        "The app now plans in the equity-first style by default; section 7 has it.",
        "* *Raw advantage*: the growth-rate difference between median after-tax wealth at 80 and the advisor's, annualized over the 42 years. "
        "*Risk-adjusted advantage*: the same on certainty-equivalent wealth at risk aversion 3 with a $50,000 floor. 'Stocks' is the share of the "
        "whole portfolio, so a 50% stock share with a 15% private credit sleeve holds 42.5% in stocks.",
        f"* The advisor: {study.baseline.exposure[0]:.0%} stocks today falling to {study.baseline.exposure[2]:.0%} by 70, no private credit; median wealth at 80 "
        f"{_dollars(study.baseline.median)}, 10th percentile {_dollars(study.baseline.p10)}, {study.baseline.shortfall:.1%} of futures run out of money.",
        "",
        "## 1. The stock share and the private credit sleeve, everything else as the recommendation's",
        "",
        "The recommendation holds less equity than the advisor does at every age (42.5% today and 21% from 70, against 80% and 50%). "
        "More equity raises the median and lowers the risk-adjusted measure, steadily:",
        "",
        *_table(study.sweep),
        "",
        "## 2. What Donabach's tools are worth at the advisor's own allocation",
        "",
        "The same tools switched on one at a time, cumulatively, with the advisor's glide path (80% falling to 50% by 70) and no private credit. "
        "This is the part of the advantage that is not extra risk.",
        "",
        *_table(study.chain),
        "",
        "## 3. What each objective picks (the balanced menu)",
        "",
        "Each row chooses the best strategy on the whole 4,032-strategy balanced menu by that objective (on the choice futures) and is scored on the held-out futures. "
        "The last two columns before the tail figures show the risk-adjusted advantage at risk aversion 3 for comparison and at the row's own risk aversion, "
        "which is what the app would print if that were its setting.",
        "",
        *_table(study.frontier, own_gamma=True, plan_column=True),
        "",
        "## 4. The best raw advantage for a given risk-adjusted advantage",
        "",
        "Among all 4,032 strategies, the one with the highest median wealth that is at least as good as the advisor risk-adjusted by the amount shown "
        "(chosen on the choice futures, scored on the held-out ones). The risk-adjusted measure rests on the few futures in which money runs out, so a plan "
        "that clears a high threshold on the choice futures usually scores a little lower on the held-out ones; the table shows the held-out figure. "
        "No plan on the menu has both measures high.",
        "",
        *_table(study.pareto, plan_column=True),
        "",
    ]
    if study.tail_matched is not None:
        lines += [
            "Among plans that run out of money no more often than the advisor and whose 10th percentile is no worse, the best raw advantage is:",
            "",
            *_table([study.tail_matched], plan_column=True),
            "",
        ]
    if study.return_equivalents:
        lines += [
            "## 5. The same advantage as extra yearly return",
            "",
            "How much more the advisor's portfolio would have had to earn, every year on every asset, to end with the same median wealth at 80 as the plan. "
            "This is the figure to compare with a quoted 'advisor alpha'; it mixes the plan's tools with the extra equity risk it may carry.",
            "",
            "| Plan | Extra yearly return the advisor would need | Raw advantage as shown above |",
            "|---|---|---|",
        ]
        for label, extra, raw in study.return_equivalents:
            lines.append(f"| {label} | {extra * 100:+.2f}% a year | {_pct(raw)} |")
        lines.append("")
    if sensitivity:
        lines += [
            "## 6. If the equity assumption were different (sensitivity only; the app never uses these)",
            "",
            "The futures are redrawn with the equity mean shown (volatility 16%, bonds 1.5%, private credit 3.5%, all as specified); the advisor is on the same futures. "
            "A higher equity return lifts the advisor too, so what matters is the advantage, not the level.",
            "",
        ]
        for name, results in sensitivity:
            lines += [f"**{name}**", "", *_table(results, plan_column=True), ""]
    if study.reserve_frontier:
        lines += [
            "## 7. The spending-reserve plans (the app's default planning style)",
            "",
            "A reserve of 2, 4 or 6 years of expenses in bonds and private credit, everything else in stocks, expenses paid from bonds and private "
            "credit first, no refill after a year stocks fell. Each row chooses the best of the 1,008 reserve strategies by that objective on the "
            "choice futures. The stock exposure is read off each plan's own year log: it moves with the household's expenses.",
            "",
            *_table(study.reserve_frontier, own_gamma=True, plan_column=True),
            "",
        ]
    lines += [f"_Computed in {study.seconds:.0f} seconds._", ""]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--n-design", type=int, default=6000)
    parser.add_argument("--n-eval", type=int, default=2000)
    parser.add_argument("--no-sensitivity", action="store_true", help="skip the equity-assumption scenarios (the slowest part)")
    args = parser.parse_args(argv)

    def progress(message: str) -> None:
        print(f"[{time.strftime('%H:%M:%S')}] {message}", file=sys.stderr, flush=True)

    study = run_study(args.n_design, args.n_eval, progress=progress)
    sensitivity = None if args.no_sensitivity else market_sensitivity(args.n_design, args.n_eval, progress=progress)
    text = render(study, sensitivity)
    args.out.write_text(text)
    print(text)


if __name__ == "__main__":
    main()
