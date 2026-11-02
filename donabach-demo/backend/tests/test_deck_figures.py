"""The figures the demo quotes for John Smith, pinned. A change in the engine that moves one of them fails here (the engine is never
changed to match a document: the document is updated). The plan is the portal's: the planner's strategy with direct indexing on."""

from __future__ import annotations

import pytest
from app.planner.waterfall import run_waterfall
from app.portal import engine_view as E
from app.portal import presets
from app.sim.simulate import build_inputs


@pytest.fixture(scope="module")
def smith():
    E.reset()
    household = presets.base_household()
    return household, E.get_plan(household)


def test_income_savings_wealth_and_the_advantage(smith):
    household, plan = smith
    assert round(household.people[0].wages) == 204_268
    assert round(household.liquid_wealth) == 1_193_283
    c = plan.comparison
    assert f"{c.waramoug.wealth_80 / 1e6:.2f}" == "2.43" and f"{c.advisor.wealth_80 / 1e6:.2f}" == "1.30"
    assert f"{c.dollars_more / 1e6:.2f}" == "1.13"
    assert f"{c.rate_per_year * 100:.2f}" == "2.11"


def test_the_strategy_contributions_a_year(smith):
    household, plan = smith
    ev = build_inputs(household, n_paths=2000, seed=2026 + E.EVAL_SEED_OFFSET)
    result = run_waterfall(ev, E._strategies[plan.plan_id], None, risk_aversion=3.0, median_only=True)
    bars = {b.key: round(b.delta_rate * 100, 3) for b in result.bars}
    assert round(bars["fee"], 2) == 0.76
    assert round(bars["allocation"], 2) == 0.56  # the spending reserve with the rest in stocks
    assert round(bars["location"], 2) == 0.24
    assert round(bars["private_credit"], 2) == 0.20
    assert round(bars["conversions"], 2) == 0.25
    assert round(bars["lots"], 3) == 0.086
    assert round(bars["withdrawals"], 2) == 0.04
    assert round(bars["harvest"], 3) == -0.023  # stock-by-stock harvesting at its step in the chain (its worth depends on what it follows)
    assert round(sum(bars.values()), 2) == 2.11


def test_the_job_loss_conversion_at_51(smith):
    household, base = smith
    job = E.get_plan(household, "job_loss", base.plan_id, "Income: job loss next year")
    before = {c.age: c.amount for c in base.portfolio.taxes.conversions}
    after = {c.age: c.amount for c in job.portfolio.taxes.conversions}
    assert round(before[51]) == 65_324 and round(after[51]) == 246_600
