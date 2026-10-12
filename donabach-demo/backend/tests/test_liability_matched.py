"""Update 4, section 3: the liability-matched reserve. The reserve is spent first when stocks have fallen, wherever it is held; a
forced sale in a falling year is counted; the planner picks the reserve that keeps those below 2% and ruin no likelier than the
advisor's."""

from __future__ import annotations

import numpy as np
import pytest
from app.planner import strategies as strat
from app.planner.baseline import RIA_BASELINE
from app.planner.search import FORCED_SALE_LIMIT, matched_choice, search
from app.planner.strategies import Strategy, menu
from app.sim.simulate import build_inputs, run_batch
from fastapi.testclient import TestClient
from tests.conftest import make_demo_household

from app.main import app

client = TestClient(app)


def test_the_liability_matched_menu_chooses_the_reserve_from_two_to_twelve_years():
    m = menu(style="liability_matched")
    assert {s.reserve_years for s in m} == set(strat.LIABILITY_RESERVE_YEARS) == {2, 3, 4, 5, 6, 7, 8, 9, 10, 12}
    assert len(m) == 10 * len(strat.CONVERSION_OPTIONS) * 4 * 2 * 3 * 2
    assert "liability_matched" in strat.STYLES
    assert Strategy.from_choices(m[0].choices()) == m[0]


def test_the_reserve_is_spent_first_when_stocks_fall_so_a_longer_reserve_forces_fewer_sales():
    futures = build_inputs(make_demo_household(), n_paths=300, seed=11)
    pick = lambda years: Strategy(1.0, "none", 0.0, False, False, reserve_years=years)  # noqa: E731
    policies = [pick(2).policy(), pick(6).policy(), pick(10).policy(), RIA_BASELINE]
    batch = run_batch(futures, policies)
    chance = [float(np.mean(batch.forced_years[i] > 0)) for i in range(4)]
    assert chance[0] >= chance[1] >= chance[2]
    assert chance[3] > 0.9  # the advisor sells in a falling year whenever it spends
    assert chance[2] < 0.5


def test_a_household_that_never_spends_from_its_portfolio_has_no_forced_sales():
    household = make_demo_household()
    futures = build_inputs(household, n_paths=40, seed=2)
    batch = run_batch(futures, [Strategy(1.0, "none", 0.0, False, False, reserve_years=4).policy()])
    assert batch.forced_years.shape == batch.wealth.shape and (batch.forced_years >= 0).all()


def test_the_choice_respects_both_limits_or_says_it_could_not():
    household = make_demo_household()
    futures = build_inputs(household, n_paths=200, seed=4)
    subset = [s for s in menu(style="liability_matched") if s.conversion in ("none", "fill22_low") and s.private_credit in (0.0, 0.15)
              and not s.direct_indexing and s.k401 == "pretax" and s.goal_funding == "sell"]
    result = search(futures, strategies=subset, extra_policies=[RIA_BASELINE], exhaustive=True)
    choice = matched_choice(result, result.batch.unfunded[len(result.strategies)])
    medians = np.median(result.batch.wealth[: len(result.strategies)], axis=1)
    if choice.feasible:
        assert choice.forced_sale_chance <= FORCED_SALE_LIMIT + 1e-9 and choice.ruin_chance <= choice.advisor_ruin_chance + 1e-9
        # and no strategy with a higher median meets them
        chosen = result.index_of(choice.strategy)
        for i in np.flatnonzero(medians > medians[chosen]):
            assert (np.mean(result.batch.forced_years[i] > 0) > FORCED_SALE_LIMIT) or (
                np.mean(result.batch.unfunded[i] > 0) > choice.advisor_ruin_chance)
    else:
        assert choice.forced_sale_chance > FORCED_SALE_LIMIT or choice.ruin_chance > choice.advisor_ruin_chance


@pytest.fixture(scope="module")
def matched_plan():
    body = {"household": make_demo_household().model_dump(mode="json"), "n_eval_paths": 200, "adaptive": False, "planning_style": "liability_matched"}
    r = client.post("/plan", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def test_the_matched_plan_reports_its_limits_and_the_reserve(matched_plan):
    view = matched_plan["liability"]
    assert view["forced_sale_limit"] == 0.02 and view["reserve_years"] in strat.LIABILITY_RESERVE_YEARS
    assert 0.0 <= view["forced_sale_chance"] <= 1.0 and view["advisor_forced_sale_chance"] > 0.9
    assert view["ruin_chance"] == matched_plan["stats"]["shortfall_chance"]
    assert len(view["stock_share_by_age"]) > 20
    assert matched_plan["settings"]["planning_style"] == "liability_matched"
    assert matched_plan["strategy"]["choices"]["reserve"] == str(view["reserve_years"])
