"""The figures the pitch deck quotes for John Smith, pinned. A change in the engine that moves one of them fails here (the engine is never
changed to match the deck: the deck is updated)."""

from __future__ import annotations

import pytest
from app import showcase
from app.portal import engine_view as E
from app.portal import presets

SHOWCASE = None


@pytest.fixture(scope="module")
def smith():
    showcase.reset()
    return showcase.showcase()


def test_income_savings_wealth_and_the_advantage(smith):
    assert round(smith.card.annual_income) == 204_268
    assert round(smith.card.total_savings) == 1_193_283
    a = smith.wealth.advantage
    assert round(a.plan_median_at_horizon, -4) == 2_380_000 and f"{a.plan_median_at_horizon / 1e6:.2f}" == "2.38"
    assert f"{a.advisor_median_at_horizon / 1e6:.2f}" == "1.30"
    assert f"{a.median_dollars / 1e6:.2f}" == "1.09"
    assert f"{a.median_rate * 100:.2f}" == "2.05"
    assert f"{showcase.typical_rate() * 100:.1f}" == "1.7"


def test_the_strategy_contributions_a_year(smith):
    bars = {b.key: round(b.delta_rate * 100, 3) for b in smith.waterfall.bars}
    assert [round(v, 2) for k, v in bars.items() if k == "fee"] == [0.76]
    assert round(bars["allocation"], 2) == 0.56  # the spending reserve with the rest in stocks
    assert round(bars["location"], 2) == 0.24
    assert round(bars["private_credit"], 2) == 0.20
    assert round(bars["conversions"], 2) == 0.18
    assert round(bars["lots"], 3) == 0.086
    assert round(bars["withdrawals"], 2) == 0.03


def test_the_job_loss_conversion_at_51():
    E.reset()
    base = E.get_plan(presets.base_household())
    job = E.get_plan(presets.base_household(), "job_loss", base.plan_id, "Income: job loss next year")
    before = {c.age: c.amount for c in base.portfolio.taxes.conversions}
    after = {c.age: c.amount for c in job.portfolio.taxes.conversions}
    assert round(before[51]) == 62_324 and round(after[51]) == 243_600
