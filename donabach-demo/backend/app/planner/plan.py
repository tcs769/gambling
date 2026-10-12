"""Assemble a full plan: search, compare against the RIA baseline, explain.

Without a recommender the planner searches the whole menu and labels the result "Search planner
(model not connected)". With one connected it scores the model's top recommendation and its
five nearest alternatives with the engine and shows what the model recommended next to what the
engine verified.
"""

from __future__ import annotations

import secrets
import time

import numpy as np

from app.api_models import (
    AdvantageView,
    BaselineView,
    FanSeries,
    LiabilityView,
    OutcomeView,
    PlanResponse,
    PlanRow,
    PlanSettings,
    RankedRow,
    RecommenderPanel,
    StatCards,
    StrategyView,
)
from app.api_models import ModelStatus as ModelStatusView
from app.ml import adapters
from app.ml.adapters import ModelContractError, NotConnected
from app.planner import explain, guided
from app.planner.baseline import BASELINES, GOOD_RIA, GOOD_RIA_SENTENCE
from app.planner.search import (
    FORCED_SALE_LIMIT,
    RISK_AVERSION,
    WEALTH_FLOOR,
    MatchedChoice,
    Outcome,
    RankedStrategy,
    SearchResult,
    search_matched,
    search,
)
from app.planner.strategies import Strategy, menu
from app.schemas import HORIZON_AGE, Household, MarketShock
from app.tax import params_2026 as P
from app.sim import markets
from app.sim import simulate as sim
from app.sim.simulate import SimInputs, build_inputs, initial_after_tax_wealth, run_batch, run_detail
from app.study import metrics

DEMO_SEED = markets.DEFAULT_SEED
EVAL_SEED_OFFSET = 1_000_003  # the evaluation futures use the search seed plus this
SEARCH_LABEL = "Search planner (model not connected)"
VALIDATION_PATHS = 1_200  # the liability-matched search checks its limits on this many futures it did not search on
VALIDATION_SEED_OFFSET = 2_000_003
DEFAULT_STYLE = "equity_first"  # what the app plans with unless asked for "balanced" (see `app.planner.strategies.menu`)
GUIDED_LABEL = "Model-guided planner (model recommended, engine verified)"
RIA_SENTENCE = GOOD_RIA_SENTENCE
LIQUIDATED_LABEL = f"Liquidated at {HORIZON_AGE}"
HEIRS_LABEL = f"Passed to heirs at {HORIZON_AGE}"


def heirs_note(rate: float = sim.HEIRS_TAX_RATE) -> str:
    """What "passed to heirs" assumes, and why the rate is what it is."""
    tops = [(top, r) for top, r in P.FED_BRACKETS_MFJ if top != float("inf")]
    index = min(range(len(tops)), key=lambda i: abs(tops[i][1] - rate))
    bracket = (tops[index][0], tops[index][1], tops[index - 1][0] if index > 0 else 0.0)
    return (
        "The taxable account is valued with a step-up in basis, so its unrealized gains are never taxed; the Roth is valued as it stands; "
        f"the 401(k) and IRA are valued after a flat {rate * 100:.0f}% federal tax. Heirs must empty an inherited retirement account within ten "
        f"years, they are usually in their prime earning years, and a 2026 married couple's income in the {bracket[1] * 100:.0f}% bracket runs from "
        f"${bracket[2]:,.0f} to ${bracket[0]:,.0f}: spread over those years, an inheritance of this size lands mostly there (22% to 32%). State tax and estate "
        "tax are left out, and so is an unused capital-loss carryforward, which ends with the owner."
    )


def resolve_seed(demo_mode: bool, seed: int | None) -> int:
    if seed is not None:
        return seed
    return DEMO_SEED if demo_mode else secrets.randbelow(2**31 - 1)


def outcome_view(o: Outcome) -> OutcomeView:
    return OutcomeView(median=o.median, p10=o.p10, p90=o.p90, score=o.score)


def strategy_view(strategy: Strategy, outcome: Outcome) -> StrategyView:
    return StrategyView(
        choices=strategy.choices(),
        label=strategy.short_label(),
        sentence=strategy.describe(),
        outcome=outcome_view(outcome),
    )


def ranked_rows(ranked: list[RankedStrategy], chosen: Strategy, model_pick: Strategy | None = None) -> list[RankedRow]:
    return [
        RankedRow(
            rank=r.rank,
            choices=r.strategy.choices(),
            label=r.strategy.short_label(),
            median=r.outcome.median,
            p10=r.outcome.p10,
            p90=r.outcome.p90,
            score=r.outcome.score,
            tied_with=r.tied_with,
            is_chosen=r.strategy == chosen,
            is_model_pick=model_pick is not None and r.strategy == model_pick,
        )
        for r in ranked
    ]


def goal_labels(household: Household, n_years: int) -> list[str | None]:
    """Which goal(s) are paid in each simulated year (None when nothing is due)."""
    g = household.goals
    names: list[list[str]] = [[] for _ in range(n_years)]
    if g.home_purchase_in_years is not None and g.home_purchase_in_years < n_years and g.home_down_payment > 0:
        names[g.home_purchase_in_years].append("Home purchase")
    if g.college_starts_in_years is not None and g.college_annual_cost > 0:
        for t in range(g.college_starts_in_years, g.college_starts_in_years + g.college_years):
            if t < n_years:
                names[t].append("College")
    return [" and ".join(n) or None for n in names]


def plan_rows(log: dict[str, np.ndarray], household: Household) -> list[PlanRow]:
    labels = goal_labels(household, len(log["age"]))
    rows = []
    for t in range(len(log["age"])):
        income = log["wages"][t] + log["ss"][t] + log["ret_dist"][t] + log["interest"][t] + log["dividends"][t]
        rows.append(
            PlanRow(
                year_index=t,
                age=int(log["age"][t]),
                income=float(income),
                wages=float(log["wages"][t]),
                roth_conversion=float(log["conv"][t]),
                losses_harvested=float(log["harvest"][t]),
                goal_bonds_balance=float(log["bucket"][t]),
                goal_bonds_flow=float(log["bucket_flow"][t]),
                goal_paid=float(log["goal_paid"][t]),
                goal_label=labels[t] if log["goal_paid"][t] > 0 else None,
                stock_share=float(log["stock_target"][t]),
                total_tax=float(log["total_tax"][t]),
                federal_tax=float(log["fed_tax"][t]),
                illinois_tax=float(log["il_tax"][t]),
                wealth=float(log["wealth"][t]),
                required_distribution=float(log["rmd"][t]),
                private_credit_balance=float(log["private_credit"][t]),
                roth_401k_contribution=float(log["k401_roth"][t]),
                borrowed=float(log["borrowed"][t]),
                loan_balance=float(log["loan"][t]),
                gains_realized_tax_free=float(log["gain_harvest"][t]),
            )
        )
    return rows


def fan_series(path_wealth: np.ndarray, start_wealth: float, current_age: int) -> FanSeries:
    """After-tax wealth quantiles by age; the first point is today's (the same for every path)."""
    q = np.percentile(path_wealth, [10, 25, 50, 75, 90], axis=0)
    ages = [current_age] + [current_age + t + 1 for t in range(path_wealth.shape[1])]
    series = {name: [start_wealth] + [float(v) for v in row] for name, row in zip(("p10", "p25", "p50", "p75", "p90"), q, strict=True)}
    return FanSeries(ages=ages, **series)


def _recommender_panel(
    household: Household, futures: SimInputs, style: str
) -> tuple[RecommenderPanel, SearchResult | None, Strategy | None]:
    """Consult the recommender if connected. Returns the panel and, if it produced candidates, their search.

    The model's own pick is scored as it is; the five alternatives come from the planning style's menu."""
    model = adapters.load_recommender()
    if isinstance(model, NotConnected):
        status = ModelStatusView(model="recommender", connected=False, reason=model.reason, expected_path=model.expected_path)
        return RecommenderPanel(status=status), None, None
    try:
        recommendation = model.recommend(household)
    except ModelContractError as exc:
        failure = adapters.not_connected("recommender", str(exc))
    except Exception as exc:  # a model that crashes is reported, not papered over
        failure = adapters.not_connected("recommender", f"The recommender failed: {type(exc).__name__}: {exc}")
    else:
        top, alternatives = guided.candidates(recommendation, style=style)
        result = search(futures, strategies=[top, *alternatives])
        model_outcome = result.outcome_of(top)
        verified = result.best
        status = ModelStatusView(model="recommender", connected=True)
        panel = RecommenderPanel(
            status=status,
            recommendation=recommendation,
            model_strategy=strategy_view(top, model_outcome),
            verified_strategy=strategy_view(verified.strategy, verified.outcome),
            agrees=verified.strategy == top,
            candidates=ranked_rows(result.ranked, verified.strategy, top),
        )
        return panel, result, top
    status = ModelStatusView(model="recommender", connected=False, reason=failure.reason, expected_path=failure.expected_path)
    return RecommenderPanel(status=status), None, None


def advantage_view(adv: metrics.Advantage) -> AdvantageView:
    return AdvantageView(
        median=adv.median,
        risk_adjusted=adv.risk_adjusted,
        median_dollars=adv.median_dollars,
        risk_adjusted_dollars=adv.risk_adjusted_dollars,
        median_low=adv.median_range[0],
        median_high=adv.median_range[1],
        risk_adjusted_low=adv.risk_adjusted_range[0],
        risk_adjusted_high=adv.risk_adjusted_range[1],
    )


def build_plan(
    household: Household,
    n_paths: int = 400,
    demo_mode: bool = True,
    seed: int | None = None,
    shock: MarketShock | None = None,
    n_eval_paths: int = 200,
    risk_aversion: float = RISK_AVERSION,
    style: str = DEFAULT_STYLE,
) -> PlanResponse:
    started = time.perf_counter()
    seed = resolve_seed(demo_mode, seed)
    eval_seed = seed + EVAL_SEED_OFFSET
    futures = build_inputs(household, n_paths=n_paths, seed=seed, shock=shock)
    evaluation = build_inputs(household, n_paths=n_eval_paths, seed=eval_seed, shock=shock)
    det = build_inputs(household, deterministic=True, shock=shock)

    matched: MatchedChoice | None = None
    if style == "liability_matched":
        # the planner's own search, under two limits (a forced sale in a falling year at most 2% of futures, ruin no more likely than
        # with the good advisor); the recommender model, trained on the other families, is not consulted
        panel = RecommenderPanel(status=ModelStatusView(model="recommender", connected=False, reason="Not consulted for the liability-matched style.", expected_path=""))
        model_pick = None
        validation = build_inputs(household, n_paths=VALIDATION_PATHS, seed=seed + VALIDATION_SEED_OFFSET, shock=shock)
        result, matched = search_matched(futures, validation, menu(style=style))
        label = SEARCH_LABEL
        chosen = matched.strategy
    else:
        panel, guided_result, model_pick = _recommender_panel(household, futures, style)
        if guided_result is not None:
            result, label = guided_result, GUIDED_LABEL
        else:
            result, label = search(futures, strategies=menu(style=style), risk_aversion=risk_aversion), SEARCH_LABEL
        chosen = result.best.strategy

    # The chosen strategy and both advisors on futures the search never saw, with the full wealth
    # path for the fan charts. Choosing the best of thousands of strategies on the futures they are
    # then scored on would flatter the winner.
    policies = [chosen.policy(), *(b.policy for b in BASELINES)]
    batch = run_batch(evaluation, policies, record_paths=True)
    plan_wealth = batch.wealth[0]
    plan_wealth_heirs = batch.wealth_heirs[0]
    plan_outcome = Outcome.of(plan_wealth, risk_aversion)
    plan_outcome_heirs = Outcome.of(plan_wealth_heirs, risk_aversion)
    years = household.horizon_years
    start_wealth = initial_after_tax_wealth(household)
    age = household.primary_age

    baselines = []
    for i, baseline in enumerate(BASELINES, start=1):
        outcome = Outcome.of(batch.wealth[i], risk_aversion)
        outcome_heirs = Outcome.of(batch.wealth_heirs[i], risk_aversion)
        baselines.append(
            BaselineView(
                key=baseline.key,
                label=baseline.label,
                definition=baseline.definition,
                outcome=outcome_view(outcome),
                outcome_heirs=outcome_view(outcome_heirs),
                lifetime_taxes=float(np.median(batch.taxes_paid[i] + batch.pretax_owed[i])),
                shortfall_chance=float(np.mean(batch.unfunded[i] > 0)),
                forced_sale_chance=float(np.mean(batch.forced_years[i] > 0)),
                advantage=advantage_view(
                    metrics.compare(plan_wealth, batch.wealth[i], years, risk_aversion, WEALTH_FLOOR, with_range=True)
                ),
                advantage_heirs=advantage_view(
                    metrics.compare(plan_wealth_heirs, batch.wealth_heirs[i], years, risk_aversion, WEALTH_FLOOR, with_range=True)
                ),
                fan=fan_series(batch.path_wealth[i], start_wealth, age),
            )
        )
    ria = next(b for b in baselines if b.key == GOOD_RIA.key)
    ria_index = 1 + next(i for i, b in enumerate(BASELINES) if b.key == GOOD_RIA.key)

    # Difference of medians: it is the gap between the two outcome cards and the sum of the
    # attribution steps, so the Compare screen never shows two different "advantages".
    advantage = plan_outcome.median - ria.outcome.median
    stats = StatCards(
        typical_outcome=outcome_view(plan_outcome),
        ria_typical_outcome=ria.outcome,
        typical_outcome_heirs=outcome_view(plan_outcome_heirs),
        ria_typical_outcome_heirs=ria.outcome_heirs,
        advantage_per_year=float(advantage / years),
        advantage_total=float(advantage),
        lifetime_taxes=float(np.median(batch.taxes_paid[0] + batch.pretax_owed[0])),
        ria_lifetime_taxes=ria.lifetime_taxes,
        years=years,
        shortfall_chance=float(np.mean(batch.unfunded[0] > 0)),
        forced_sale_chance=float(np.mean(batch.forced_years[0] > 0)),
        ria_forced_sale_chance=float(np.mean(batch.forced_years[ria_index] > 0)),
        advantage=ria.advantage,
        advantage_heirs=ria.advantage_heirs,
    )

    log = run_detail(det, chosen.policy()).log
    liability = None
    if matched is not None:
        liability = LiabilityView(
            reserve_years=chosen.reserve_years,
            forced_sale_limit=FORCED_SALE_LIMIT,
            forced_sale_chance=stats.forced_sale_chance,
            advisor_forced_sale_chance=stats.ria_forced_sale_chance,
            ruin_chance=stats.shortfall_chance,
            advisor_ruin_chance=ria.shortfall_chance,
            chosen_on_forced_sale_chance=matched.forced_sale_chance,
            chosen_on_ruin_chance=matched.ruin_chance,
            chosen_on_advisor_ruin_chance=matched.advisor_ruin_chance,
            feasible=matched.feasible,
            stock_share_by_age=[(int(a), float(e)) for a, e in zip(log["age"], log["equity_share"], strict=True)],
        )
    return PlanResponse(
        planner_label=label,
        strategy=strategy_view(chosen, plan_outcome),
        reason=explain.headline_reason(det, result, chosen),
        recommender=panel,
        ria=StrategyView(
            choices={},
            label="Good RIA baseline",
            sentence=GOOD_RIA.definition,
            outcome=ria.outcome,
        ),
        rows=plan_rows(log, household),
        stats=stats,
        fan=fan_series(batch.path_wealth[0], start_wealth, age),
        ria_fan=baselines[ria_index - 1].fan,
        baselines=baselines,
        liability=liability,
        advantage=explain.advantage_steps(evaluation, chosen),
        searched=ranked_rows(result.ranked, chosen, model_pick),
        settings=PlanSettings(
            n_paths=n_paths,
            n_eval_paths=n_eval_paths,
            seed=seed,
            eval_seed=eval_seed,
            demo_mode=demo_mode,
            elapsed_seconds=time.perf_counter() - started,
            current_age=household.primary_age,
            horizon_age=HORIZON_AGE,
            strategies_searched=result.n_considered or len(result.ranked),
            risk_aversion=risk_aversion,
            wealth_floor=WEALTH_FLOOR,
            market_shock=shock,
            planning_style=style,
            heirs_rate=sim.HEIRS_TAX_RATE,
            liquidated_label=LIQUIDATED_LABEL,
            heirs_label=HEIRS_LABEL,
            heirs_note=heirs_note(),
        ),
    )
