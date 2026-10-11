"""The showcase household: a summary card, the strategy waterfall and wealth over time against the advisor.

One household (`fixtures/showcase.json`) is the demo's subject. Its plan is searched once (the app's default planning style, 400
futures, seed 2026) and everything else is measured on 2,000 other futures the search never saw, the same for the advisor, every
bar of the waterfall and the wealth lines, so the bars add up to the headline and the lines end where the bars end.
"""

from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from pydantic import BaseModel

from app.api_models import (
    CardAccount,
    CardGoal,
    CardPerson,
    HouseholdCard,
    ShowcaseAdvantage,
    ShowcaseAnalysis,
    ShowcaseBar,
    ShowcaseResponse,
    WealthLines,
)
from app.planner import plan as planner
from app.planner.search import RISK_AVERSION, WEALTH_FLOOR, search
from app.planner.strategies import Strategy, menu
from app.planner.waterfall import run_waterfall, waterfall_strategies
from app.schemas import HORIZON_AGE, Household
from app.sim.simulate import SimInputs, build_inputs, initial_after_tax_wealth

FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "showcase.json"
FIXTURE_ENV = "DONABACH_SHOWCASE"
SEARCH_PATHS = 400
EVAL_PATHS = 2000
SEED = 2026
ADVISOR_LABEL = "Good advisor"


class Fixture(BaseModel):
    id: str
    name: str
    type_label: str
    tagline: str
    household: Household


def load_fixture(path: Path | None = None) -> Fixture:
    path = path or Path(os.environ.get(FIXTURE_ENV) or FIXTURE)
    return Fixture.model_validate(json.loads(path.read_text()))


def _money(x: float) -> str:
    return f"${x:,.0f}"


def _pct(x: float) -> str:
    return f"{x * 100:.0f}%"


def build_card(household: Household) -> HouseholdCard:
    """The summary card: who they are, what they have, what they are saving for, and what stands out."""
    a, g = household.accounts, household.goals
    savings = household.liquid_wealth
    gain = max(0.0, a.brokerage_value - a.brokerage_basis)
    people = [
        CardPerson(label=p.name or f"Earner {i + 1}", age=p.age, wages=p.wages) for i, p in enumerate(household.people)
    ]
    accounts = [
        CardAccount(
            key="taxable", label="Taxable brokerage", value=a.brokerage_value, share=a.brokerage_value / savings if savings else 0.0,
            basis=a.brokerage_basis, unrealized_gain=gain,
        ),
        CardAccount(key="pretax", label="401(k) and IRA (pre-tax)", value=a.pretax_balance, share=a.pretax_balance / savings if savings else 0.0),
        CardAccount(key="roth", label="Roth", value=a.roth_balance, share=a.roth_balance / savings if savings else 0.0),
        CardAccount(key="cash", label="Cash", value=a.cash, share=a.cash / savings if savings else 0.0),
    ]
    goals: list[CardGoal] = []
    if g.home_purchase_in_years is not None and g.home_down_payment > 0:
        goals.append(
            CardGoal(
                key="home", label="Home purchase", detail=f"{_money(g.home_down_payment)} down payment in {g.home_purchase_in_years} years",
                years_from_now=g.home_purchase_in_years, amount=g.home_down_payment,
            )
        )
    if g.college_starts_in_years is not None and g.college_annual_cost > 0:
        goals.append(
            CardGoal(
                key="college", label="College",
                detail=f"{_money(g.college_annual_cost)} a year for {g.college_years} years, starting in {g.college_starts_in_years} years",
                years_from_now=g.college_starts_in_years, amount=g.college_annual_cost,
            )
        )
    until_retirement = g.retirement_age - household.primary_age
    goals.append(
        CardGoal(
            key="retirement", label="Retirement",
            detail=f"Retire at {g.retirement_age} (in {until_retirement} years), spending {_money(g.retirement_spending)} a year",
            years_from_now=until_retirement, amount=g.retirement_spending,
        )
    )
    ss = household.social_security
    goals.append(
        CardGoal(
            key="social_security", label="Social Security",
            detail=f"{_money(ss.annual_benefit)} a year from age {ss.start_age}",
            years_from_now=ss.start_age - household.primary_age, amount=ss.annual_benefit,
        )
    )

    notes: list[str] = []
    if a.brokerage_value > 0 and gain / a.brokerage_value >= 0.2:
        notes.append(
            f"{_money(gain)} of the taxable account is unrealized gain ({_pct(gain / a.brokerage_value)} of its value), "
            "so which shares are sold first decides how much of it is taxed."
        )
    if savings > 0 and a.pretax_balance / savings >= 0.45:
        notes.append(
            f"{_pct(a.pretax_balance / savings)} of savings is pre-tax: every dollar spent from it in retirement is taxed as ordinary income "
            "unless it is moved to Roth in a lower-income year."
        )
    investable = a.brokerage_value + a.cash
    if g.home_purchase_in_years is not None and investable > 0 and g.home_down_payment / investable >= 0.25:
        notes.append(
            f"The {_money(g.home_down_payment)} home purchase in {g.home_purchase_in_years} years is {_pct(g.home_down_payment / investable)} "
            "of the money outside retirement accounts."
        )
    before_ss = ss.start_age - g.retirement_age
    if before_ss >= 5:
        notes.append(
            f"Retirement at {g.retirement_age} leaves {before_ss} years before Social Security starts at {ss.start_age}: "
            "years of low taxable income that suit Roth conversions."
        )
    return HouseholdCard(
        people=people,
        children_ages=list(household.children_ages),
        annual_income=household.total_wages,
        total_savings=savings,
        accounts=accounts,
        goals=goals,
        notes=notes[:3],
    )


@dataclass
class Prepared:
    fixture: Fixture
    strategy: Strategy
    inputs: SimInputs  # the 2,000 futures everything is measured on


_lock = threading.Lock()
_prepared: dict[str, Prepared] = {}
_analyses: dict[tuple[str, tuple[str, ...]], ShowcaseAnalysis] = {}


def prepare(fixture: Fixture | None = None) -> Prepared:
    """Search the household's plan and draw the futures it is measured on (once per household)."""
    fixture = fixture or load_fixture()
    with _lock:
        cached = _prepared.get(fixture.id)
        if cached is not None:
            return cached
    futures = build_inputs(fixture.household, n_paths=SEARCH_PATHS, seed=SEED)
    strategy = search(futures, strategies=menu(style=planner.DEFAULT_STYLE), risk_aversion=RISK_AVERSION).best.strategy
    inputs = build_inputs(fixture.household, n_paths=EVAL_PATHS, seed=SEED + planner.EVAL_SEED_OFFSET)
    prepared = Prepared(fixture, strategy, inputs)
    with _lock:
        _prepared[fixture.id] = prepared
    return prepared


def analyze(prepared: Prepared, enabled: list[str] | None = None) -> ShowcaseAnalysis:
    """The waterfall, the headline and the wealth lines with the strategies in `enabled` left on (None: all)."""
    steps = waterfall_strategies(prepared.strategy)
    keys = [s.key for s in steps]
    on = keys if enabled is None else [k for k in keys if k in set(enabled)]
    cache_key = (prepared.fixture.id, tuple(on))
    with _lock:
        cached = _analyses.get(cache_key)
    if cached is not None:
        return cached

    result = run_waterfall(prepared.inputs, prepared.strategy, set(on), risk_aversion=RISK_AVERSION)
    household = prepared.fixture.household
    start = initial_after_tax_wealth(household)
    ages = [household.primary_age] + [household.primary_age + t + 1 for t in range(result.years)]

    def lines(paths: np.ndarray) -> tuple[list[float], list[float]]:
        p10, median = np.percentile(paths, [10, 50], axis=0)
        return [start, *map(float, median)], [start, *map(float, p10)]

    plan_median, plan_p10 = lines(result.plan_paths)
    advisor_median, advisor_p10 = lines(result.baseline_paths)
    adv = result.advantage
    analysis = ShowcaseAnalysis(
        enabled=on,
        bars=[
            ShowcaseBar(
                key=b.key, label=b.label, detail=b.detail, enabled=b.enabled, delta_rate=b.delta_rate, delta_dollars=b.delta_dollars,
                cumulative_rate=b.cumulative_rate, cumulative_dollars=b.cumulative_dollars,
            )
            for b in result.bars
        ],
        advantage=ShowcaseAdvantage(
            median_rate=adv.median,
            median_dollars=adv.median_dollars,
            median_low=adv.median_range[0],
            median_high=adv.median_range[1],
            risk_adjusted_rate=adv.risk_adjusted,
            risk_adjusted_dollars=adv.risk_adjusted_dollars,
            plan_median_at_horizon=float(np.median(result.plan_wealth)),
            advisor_median_at_horizon=float(np.median(result.baseline_wealth)),
            plan_p10_at_horizon=float(np.percentile(result.plan_wealth, 10)),
            advisor_p10_at_horizon=float(np.percentile(result.baseline_wealth, 10)),
            plan_shortfall=result.plan_shortfall,
            advisor_shortfall=result.baseline_shortfall,
        ),
        wealth=WealthLines(ages=ages, plan_median=plan_median, plan_p10=plan_p10, advisor_median=advisor_median, advisor_p10=advisor_p10),
        risk_adjusted_label="Risk-adjusted advantage",
        risk_adjusted_explanation=(
            "The same comparison on the wealth you can count on: bad futures weigh more than good ones "
            f"(risk aversion {RISK_AVERSION:g}, a {_money(WEALTH_FLOOR)} floor), so a plan that takes more risk is credited less for what it earns."
        ),
        n_paths=prepared.inputs.n_paths,
        years=result.years,
        horizon_age=HORIZON_AGE,
        risk_aversion=RISK_AVERSION,
        advisor_label=ADVISOR_LABEL,
        plan_label=prepared.strategy.short_label(),
        plan_sentence=prepared.strategy.describe(),
    )
    with _lock:
        if len(_analyses) > 256:
            _analyses.clear()
        _analyses[cache_key] = analysis
    return analysis


def showcase(enabled: list[str] | None = None) -> ShowcaseResponse:
    prepared = prepare()
    f = prepared.fixture
    return ShowcaseResponse(
        id=f.id, name=f.name, type_label=f.type_label, tagline=f.tagline, household=f.household,
        card=build_card(f.household), analysis=analyze(prepared, enabled),
    )


def reset() -> None:
    """Forget what was prepared (tests, and a changed fixture)."""
    with _lock:
        _prepared.clear()
        _analyses.clear()
