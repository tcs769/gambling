"""The figures the demo quotes for John Smith, pinned. A change in the engine that moves one of them fails here (the engine is never
changed to match a document: the document is updated). The plan is the portal's: the planner's strategy, measured on the final set of 3,000 futures."""

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
    assert round(household.people[0].wages) == 300_000
    assert round(household.liquid_wealth) == 1_860_000
    c = plan.comparison
    assert round(c.waramoug.wealth_80) == 3_354_464 and round(c.advisor.wealth_80) == 1_961_675
    assert round(c.dollars_more) == 1_392_788
    assert f"{c.rate_per_year * 100:.2f}" == "2.47"


def test_the_strategy_contributions_a_year(smith):
    household, plan = smith
    ev = build_inputs(household, n_paths=E.EVAL_PATHS, seed=2026 + E.EVAL_SEED_OFFSET)
    result = run_waterfall(ev, E._strategies[plan.plan_id], None, risk_aversion=3.0, median_only=True)
    bars = {b.key: round(b.delta_rate * 100, 3) for b in result.bars}
    assert bars == {
        "fee": 0.652, "location": 0.303, "lots": 0.039, "allocation": 0.709,  # allocation: the spending reserve with the rest in stocks
        "private_credit": 0.096, "conversions": 0.655, "withdrawals": 0.013, "borrow": 0.001,
    }
    assert "harvest" not in bars  # direct indexing is not in the plan: once the tax on the sale that starts it is charged it does not pay
    assert round(sum(bars.values()), 2) == 2.47
    dollars = {b.key: round(b.delta_dollars) for b in result.bars}
    assert dollars["conversions"] == 440_265 and dollars["allocation"] == 405_614 and dollars["fee"] == 301_446
    assert sum(dollars.values()) in range(round(plan.comparison.dollars_more) - 2, round(plan.comparison.dollars_more) + 3)


def test_the_job_loss_conversion_at_59(smith):
    household, base = smith
    job = E.get_plan(household, "job_loss", base.plan_id, "Income: job loss next year")
    before = {c.age: c.amount for c in base.portfolio.taxes.conversions}
    after = {c.age: c.amount for c in job.portfolio.taxes.conversions}
    assert round(before[59]) == 156_515 and round(after[59]) == 430_518
