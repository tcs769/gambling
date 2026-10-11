"""The adaptive plan as the API shows it: the year-by-year plan, why each year, and the four-way comparison.

`compute_adaptive` runs the adaptive planner twice on the same household:

* on the **plan path** (the expected-return path, with any what-if shock): one future, whose year-by-year
  decisions fill the plan table and the "Why this year" panel. Every candidate the search scored is kept, so
  the panel can show the chosen action, the next best alternatives and the score gap between them.
* on the **evaluation futures** (the same held-out futures every other result is measured on): the
  distribution of outcomes, for the four-way comparison and the value of judgment over time.

The "why" sentences are computed from the numbers the run produced (the year's market return, income against
normal, balances against the fixed strategy's own path, bracket room, the rollout scores); nothing is typed in.
"""

from __future__ import annotations

import dataclasses
import time
from collections.abc import Callable

import numpy as np

from app.api_models import (
    ActionView,
    AdaptivePlanRow,
    AdaptiveSection,
    AdvantageView,
    AlternativeView,
    StrategyOutcome,
    YearDecisionView,
)
from app.planner import explain
from app.planner.baseline import BASELINES, GOOD_RIA, TYPICAL
from app.planner.plan import EVAL_SEED_OFFSET, advantage_view, fan_series, outcome_view, plan_rows
from app.planner.search import WEALTH_FLOOR, Outcome
from app.planner.strategies import Strategy
from app.planner.explain import YearDetail
from app.schemas import Household, MarketShock
from app.sim import adaptive as ad
from app.sim.simulate import TV_EXPWAGE, TV_GOAL, build_inputs, initial_after_tax_wealth, run_batch, run_detail
from app.study import metrics
from app.tax import params_2026 as P

PLAN_PATH_FACTOR = 8  # the plan path is one path, so it gets this many times the rollouts of an evaluation path

SEARCH_SENTENCE = (
    "Each year, after that year's returns are known, the planner scores candidate actions by simulating "
    "{k} fresh futures from where the household stands: the candidate is applied for the rest of the year and "
    "the best fixed strategy is followed from then on. It starts from the fixed strategy's action and improves "
    "one decision at a time (Roth conversion, realizing gains, how a goal is paid, 401(k) type, private credit, "
    "stock share), two passes. A change is proposed only if it beats the incumbent by at least {z:g} standard "
    "error across the futures, and is kept only if it then also wins by {zc:g} standard errors on {c} further "
    "futures the search did not see (the best of several candidates on the same futures is partly luck). "
    "Half the futures are drawn from a market {tilt:g} standard deviations a year worse than expected and "
    "re-weighted, so the bad futures that decide a certainty equivalent are not missed. The plan table and "
    "this panel use {pk} futures per candidate: they follow a single path."
)

DECISION_LABELS = {
    "conversion": "Roth conversion",
    "realize_gains": "Realizing gains",
    "goal_funding": "How the goal is paid",
    "k401": "401(k) type",
    "private_credit": "Private credit",
    "stock_share": "Stock share",
}
BRACKET = {P.TOP_OF_12: 12, P.TOP_OF_22: 22, P.TOP_OF_24: 24}
_DIM_INDEX = {name: i for i, name in enumerate(ad.DIM_NAMES)}


def _money(x: float) -> str:
    if abs(x) >= 1e6:
        return f"${x / 1e6:.2f}M".replace(".00M", "M")
    if abs(x) >= 1e4:
        return f"${x / 1e3:,.0f}k"
    return f"${x:,.0f}"


def _bracket(top: float) -> int | None:
    if top <= 0.0:
        return None
    return BRACKET.get(round(top, 1), min(BRACKET.items(), key=lambda kv: abs(kv[0] - top))[1])


def action_view(vec: np.ndarray, goal_due: bool) -> ActionView:
    """A decision vector (in `ad.DIM_NAMES` order) as the API shows it."""
    conv, realize, borrow, roth, pc, stock = (float(x) for x in vec)
    bracket = _bracket(conv)
    parts = [f"{stock * 100:.0f}% stocks"]
    parts.append(f"fill {bracket}% bracket" if bracket else "no conversion")
    if pc > 0:
        parts.append(f"{pc * 100:.0f}% private credit")
    if roth > 0.5:
        parts.append("Roth 401(k)")
    if goal_due:
        parts.append("borrow for the goal" if borrow > 0.5 else "sell for the goal")
    if realize > 0.5:
        parts.append("realize gains at 0%")
    return ActionView(
        stock_share=stock,
        conversion_bracket=bracket,
        private_credit=pc,
        k401="roth" if roth > 0.5 else "pretax",
        goal_funding=("borrow" if borrow > 0.5 else "sell") if goal_due else None,
        realize_gains=realize > 0.5,
        label=", ".join(parts),
    )


def differing(a: np.ndarray, b: np.ndarray) -> list[str]:
    """Names of the decisions in which two decision vectors differ."""
    return [name for i, name in enumerate(ad.DIM_NAMES) if abs(float(a[i]) - float(b[i])) > 1e-9]


def _what_the_planner_saw(facts: dict[str, float], departures: list[str]) -> list[str]:
    """Plain facts about the year (never causes: the planner chose by the rollout scores, not by these)."""
    seen = []
    market = facts["market_return"]
    if market <= -0.10:
        seen.append(f"the market fell {abs(market) * 100:.0f}% this year")
    elif market >= 0.20:
        seen.append(f"the market rose {market * 100:.0f}% this year")
    if facts["expected_wages"] > 0 and facts["wages"] < 0.85 * facts["expected_wages"]:
        seen.append(f"income is {(1 - facts['wages'] / facts['expected_wages']) * 100:.0f}% below normal")
    if abs(facts["pretax_vs_fixed"]) >= 0.05:
        side = "above" if facts["pretax_vs_fixed"] > 0 else "below"
        seen.append(f"the pre-tax balance is {abs(facts['pretax_vs_fixed']) * 100:.0f}% {side} the fixed strategy's path")
    if abs(facts["wealth_vs_fixed"]) >= 0.05:
        side = "ahead of" if facts["wealth_vs_fixed"] > 0 else "behind"
        seen.append(f"total after-tax wealth is {abs(facts['wealth_vs_fixed']) * 100:.0f}% {side} the fixed strategy's path")
    if "conversion" in departures and facts["conversion"] > 0 and facts["room_taxable"] > 0:
        seen.append(f"taxable income before the conversion was {_money(facts['taxable_before_conversion'])}, leaving room in the lower brackets")
    return seen


def _why(
    chosen: np.ndarray,
    fixed: np.ndarray,
    departures: list[str],
    facts: dict[str, float],
    goal_label: str | None,
    ce_gain: float,
    fresh_gain: float,
    alternatives: list[AlternativeView],
    proposed: int,
    kept: int,
    confirm_k: int,
) -> str:
    next_best = [a for a in alternatives if a.differs_in]
    closest = ""
    if next_best:
        a = next_best[0]
        if abs(a.ce_gap) < 50.0:
            closest = f" Closest alternative: {a.action.label}, scored about the same."
        else:
            closest = f" Closest alternative: {a.action.label}, {_money(abs(a.ce_gap))} {'less' if a.ce_gap >= 0 else 'more, but not convincingly'}."
    if not departures:
        text = f"No change from the fixed strategy: {action_view(chosen, goal_label is not None).label}."
        if proposed > 0:
            held = "none of them" if kept == 0 else f"only {kept}"
            text += f" The search proposed {proposed} change{'s' if proposed > 1 else ''}, but {held} held up when re-tested on {confirm_k} fresh futures."
        else:
            text += " Nothing the search tried beat it by a convincing margin."
        return text + closest

    clauses = []
    for name in departures:
        i = _DIM_INDEX[name]
        new, old = float(chosen[i]), float(fixed[i])
        if name == "conversion":
            if new > 0 and old == 0:
                clauses.append(f"Converted {_money(facts['conversion'])} to Roth, filling the {_bracket(new)}% bracket")
            elif new == 0:
                clauses.append("Skipped the Roth conversion")
            else:
                clauses.append(f"Filled the {_bracket(new)}% bracket with a Roth conversion (usual: {_bracket(old) or 'none'}%)".replace("(usual: none%)", "(usual: none)"))
        elif name == "realize_gains":
            clauses.append(f"Realized {_money(facts['gains_realized'])} of gains inside the 0% bracket" if new > 0.5 else "Did not realize gains")
        elif name == "goal_funding":
            clauses.append(f"Borrowed {_money(facts['borrowed'])} for the {goal_label or 'goal'} instead of selling" if new > 0.5 else f"Sold assets for the {goal_label or 'goal'} instead of borrowing")
        elif name == "k401":
            clauses.append("Put this year's 401(k) contribution on the Roth side" if new > 0.5 else "Kept the 401(k) contribution pre-tax")
        elif name == "private_credit":
            clauses.append(f"Private credit {new * 100:.0f}% (usual: {old * 100:.0f}%)")
        elif name == "stock_share":
            clauses.append(f"{new * 100:.0f}% stocks (usual: {old * 100:.0f}%)")
    text = "; ".join(clauses) + "."
    seen = _what_the_planner_saw(facts, departures)
    if seen:
        text += " What the planner saw: " + "; ".join(seen) + "."
    text += f" The rollouts scored this {_money(ce_gain)} higher than the fixed strategy's action (certainty-equivalent wealth at the horizon)."
    if confirm_k > 0:
        text += f" Re-tested on {confirm_k} fresh futures it still came out {_money(fresh_gain)} ahead."
    return text + closest


def year_decisions(
    household: Household,
    plan_run: ad.AdaptiveResult,
    det,
    fixed_log: dict[str, np.ndarray],
) -> list[YearDecisionView]:
    """"Why this year" for every year of the plan path."""
    log = plan_run.log
    assert log is not None and plan_run.cand_actions is not None and plan_run.cand_ce is not None
    goal_names = _goal_names(household, det.n_years)
    views = []
    for t in range(det.n_years):
        chosen, fixed = plan_run.chosen[0, t], plan_run.continuation[0, t]
        goal_due = bool(det.tv[t, TV_GOAL] > 0)
        n = int(plan_run.n_candidates[0, t])
        ces = plan_run.cand_ce[0, t, :n]
        actions = plan_run.cand_actions[0, t, :n]
        ce_chosen = float(plan_run.ce_chosen[0, t])
        order = np.argsort(-ces, kind="stable")
        alternatives: list[AlternativeView] = []
        for c in order:
            if np.array_equal(actions[c], chosen):
                continue
            alternatives.append(
                AlternativeView(
                    action=action_view(actions[c], goal_due),
                    ce=float(ces[c]),
                    ce_gap=ce_chosen - float(ces[c]),
                    differs_in=differing(actions[c], chosen),
                )
            )
            if len(alternatives) == 2:
                break
        departures = differing(chosen, fixed)
        wages = float(log["wages"][t])
        expected = float(det.tv[t, TV_EXPWAGE])
        pretax_fixed = float(fixed_log["pretax"][t])
        wealth_fixed = float(fixed_log["wealth"][t])
        taxable_before = float(log["taxable_income"][t]) - float(log["conv"][t])
        facts = {
            "market_return": float(det.rets[0, t, 0]),
            "wages": wages,
            "expected_wages": expected,
            "conversion": float(log["conv"][t]),
            "gains_realized": float(log["gain_harvest"][t]),
            "borrowed": float(log["borrowed"][t]),
            "pretax_balance": float(log["pretax"][t]),
            "pretax_vs_fixed": float(log["pretax"][t]) / pretax_fixed - 1.0 if pretax_fixed > 0 else 0.0,
            "wealth_vs_fixed": float(log["wealth"][t]) / wealth_fixed - 1.0 if wealth_fixed > 0 else 0.0,
            "taxable_before_conversion": max(0.0, taxable_before),
            "room_taxable": 1.0 if taxable_before < P.TOP_OF_12 else 0.0,
        }
        ce_fixed = float(plan_run.ce_continuation[0, t])
        proposed, kept = int(plan_run.proposed[0, t]), int(plan_run.kept[0, t])
        views.append(
            YearDecisionView(
                year_index=t,
                age=int(log["age"][t]),
                chosen=action_view(chosen, goal_due),
                fixed=action_view(fixed, goal_due),
                departs=bool(departures),
                departures=departures,
                alternatives=alternatives,
                ce_chosen=ce_chosen,
                ce_fixed=ce_fixed,
                candidates_scored=n,
                changes_proposed=proposed,
                changes_kept=kept,
                ce_chosen_fresh=float(plan_run.ce_fresh_chosen[0, t]),
                ce_fixed_fresh=float(plan_run.ce_fresh_continuation[0, t]),
                why=_why(
                    chosen, fixed, departures, facts, goal_names[t], ce_chosen - ce_fixed,
                    float(plan_run.ce_fresh_chosen[0, t] - plan_run.ce_fresh_continuation[0, t]), alternatives, proposed, kept,
                    plan_run.settings.confirm_rollouts,
                ),
                facts=facts,
            )
        )
    return views


def year_details(strategy: Strategy, plan_run: ad.AdaptiveResult, n_years: int) -> list[YearDetail]:
    """What the adaptive plan did in every year of the plan path, with the year's full tax return."""
    log = plan_run.log
    assert log is not None
    base_policy = strategy.policy()
    out = []
    for t in range(n_years):
        chosen = plan_run.chosen[0, t]
        bracket = _bracket(float(chosen[_DIM_INDEX["conversion"]]))
        year_strategy = dataclasses.replace(strategy, conversion=f"fill{bracket}_every" if bracket else "none")
        year_policy = dataclasses.replace(base_policy, private_credit=float(chosen[_DIM_INDEX["private_credit"]]))
        out.append(explain.year_detail_from_log(year_strategy, year_policy, log, t))
    return out


def _goal_names(household: Household, n_years: int) -> list[str | None]:
    from app.planner.plan import goal_labels

    return goal_labels(household, n_years)


def compute_adaptive(
    household: Household,
    strategy: Strategy,
    seed: int,
    n_eval_paths: int = 200,
    shock: MarketShock | None = None,
    risk_aversion: float = 3.0,
    k: int = ad.DEFAULT_K,
    z_min: float = ad.DEFAULT_Z_MIN,
    on_progress: Callable[[float], None] | None = None,
    dimensions: tuple[str, ...] = ad.DIM_NAMES,
    settings: ad.AdaptiveSettings | None = None,
) -> AdaptiveSection:
    """Run the adaptive planner for `household`, continuing with the best fixed `strategy`."""
    started = time.perf_counter()
    eval_seed = seed + EVAL_SEED_OFFSET
    evaluation = build_inputs(household, n_paths=n_eval_paths, seed=eval_seed, shock=shock)
    det = build_inputs(household, deterministic=True, shock=shock, seed=eval_seed)
    settings = settings or ad.AdaptiveSettings(k=k, z_min=z_min, risk_aversion=risk_aversion, dimensions=dimensions)
    # the plan path is a single path: more rollouts there cost little and make the table and "Why this year" steadier
    plan_settings = dataclasses.replace(
        settings, k=settings.rollouts * PLAN_PATH_FACTOR, confirm_k=settings.confirm_rollouts * PLAN_PATH_FACTOR
    )
    policy = strategy.policy()
    years = household.horizon_years
    start_wealth = initial_after_tax_wealth(household)

    plan_run = ad.run_adaptive(det, policy, plan_settings, record_candidates=True, detail_path=0)
    fixed_log = run_detail(det, policy).log
    if on_progress:
        on_progress(0.02)
    eval_run = ad.run_adaptive(
        evaluation, policy, settings, on_progress=(lambda done, total: on_progress(0.02 + 0.96 * done / total)) if on_progress else None
    )
    batch = run_batch(evaluation, [policy, *(b.policy for b in BASELINES)], record_paths=True)

    adaptive_wealth = eval_run.wealth
    entries = [
        (TYPICAL.key, TYPICAL.label, TYPICAL.definition, batch.wealth[2], batch.taxes_paid[2] + batch.pretax_owed[2], batch.unfunded[2], batch.path_wealth[2]),
        (GOOD_RIA.key, GOOD_RIA.label, GOOD_RIA.definition, batch.wealth[1], batch.taxes_paid[1] + batch.pretax_owed[1], batch.unfunded[1], batch.path_wealth[1]),
        ("best_fixed", "Best fixed strategy", strategy.describe(), batch.wealth[0], batch.taxes_paid[0] + batch.pretax_owed[0], batch.unfunded[0], batch.path_wealth[0]),
        (
            "adaptive",
            "Adaptive planner",
            "The best fixed strategy, with each year's decisions re-chosen after that year's returns are known.",
            adaptive_wealth,
            eval_run.taxes_paid + eval_run.pretax_owed,
            eval_run.unfunded,
            eval_run.path_wealth,
        ),
    ]
    by_key = {key: wealth for key, _, _, wealth, _, _, _ in entries}
    strategies = []
    for key, label, definition, wealth, taxes, unfunded, paths in entries:
        strategies.append(
            StrategyOutcome(
                key=key,
                label=label,
                definition=definition,
                outcome=outcome_view(Outcome.of(wealth, risk_aversion)),
                lifetime_taxes=float(np.median(taxes)),
                shortfall_chance=float(np.mean(unfunded > 0)),
                fan=fan_series(paths, start_wealth, household.primary_age),
                advantage_vs_typical=advantage_view(
                    metrics.compare(wealth, by_key["typical_advisor"], years, risk_aversion, WEALTH_FLOOR, with_range=True)
                ),
                advantage_vs_ria=advantage_view(
                    metrics.compare(wealth, by_key["good_ria"], years, risk_aversion, WEALTH_FLOOR, with_range=True)
                ),
            )
        )
    value: AdvantageView = advantage_view(
        metrics.compare(adaptive_wealth, by_key["best_fixed"], years, risk_aversion, WEALTH_FLOOR, with_range=True)
    )

    decisions = year_decisions(household, plan_run, det, fixed_log)
    rows = []
    for base, d in zip(plan_rows(plan_run.log, household), decisions, strict=True):
        rows.append(AdaptivePlanRow(**base.model_dump(), departs=d.departs, departures=d.departures))

    differs = eval_run.chosen != eval_run.continuation
    elapsed = time.perf_counter() - started
    if on_progress:
        on_progress(1.0)
    return AdaptiveSection(
        k=settings.rollouts,
        n_eval_paths=n_eval_paths,
        z_min=settings.z_min,
        confirm_k=settings.confirm_rollouts,
        confirm_z=settings.confirm_z,
        tilt=settings.tilt,
        plan_path_k=plan_settings.rollouts,
        plan_path_confirm_k=plan_settings.confirm_rollouts,
        risk_aversion=settings.risk_aversion,
        elapsed_seconds=elapsed,
        seconds_per_path=eval_run.elapsed_seconds / max(1, n_eval_paths),
        search=SEARCH_SENTENCE.format(
            k=settings.rollouts, z=settings.z_min, zc=settings.confirm_z, c=settings.confirm_rollouts, tilt=settings.tilt,
            pk=plan_settings.rollouts,
        ),
        rows=rows,
        year_details=year_details(strategy, plan_run, household.horizon_years),
        decisions=decisions,
        strategies=strategies,
        value_of_judgment=value,
        departure_share=float(differs.any(axis=2).mean()),
        departure_by_decision={name: float(differs[:, :, i].mean()) for i, name in enumerate(ad.DIM_NAMES)},
        departure_by_year=[float(x) for x in differs.any(axis=2).mean(axis=0)],
        departure_by_year_and_decision={name: [float(x) for x in differs[:, :, i].mean(axis=0)] for i, name in enumerate(ad.DIM_NAMES)},
    )
