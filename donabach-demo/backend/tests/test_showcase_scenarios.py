"""The showcase household after an event: a job lost next year, a stock market that falls 30% next year."""

from __future__ import annotations

import numpy as np
import pytest
from app import showcase, showcase_scenarios
from app.api_models import PlanRow
from app.schemas import JobLoss, MarketShock
from app.sim.simulate import TV_EXPWAGE, build_inputs
from fastapi.testclient import TestClient
from tests.conftest import make_demo_household

client = TestClient(__import__("app.main", fromlist=["app"]).app)


# --- The events, applied to the futures ---------------------------------------------------------------


def test_a_job_loss_removes_the_wages_of_those_years_and_nothing_else():
    household = make_demo_household()
    plain = build_inputs(household, n_paths=40, seed=5)
    lost = build_inputs(household, n_paths=40, seed=5, job_loss=JobLoss(year=1, years=2, keep=0.0))
    assert np.all(lost.wages[:, 1:3] == 0.0)
    assert np.all(lost.k401[:, 1:3] == 0.0)  # no pay, no 401(k) contribution
    assert np.array_equal(lost.wages[:, [0, *range(3, lost.n_years)]], plain.wages[:, [0, *range(3, plain.n_years)]])
    assert np.array_equal(lost.rets, plain.rets)  # the markets are the same futures
    assert np.array_equal(lost.tv[:, TV_EXPWAGE], plain.tv[:, TV_EXPWAGE])  # the household still expected its pay: the spell is a surprise
    assert np.all(lost.wage_tax[:, 1:3] == 0.0)  # and no tax is withheld on it


def test_a_partial_job_loss_keeps_a_share_of_the_wages_and_the_deterministic_path_follows():
    household = make_demo_household()
    plain = build_inputs(household, deterministic=True)
    lost = build_inputs(household, deterministic=True, job_loss=JobLoss(year=1, years=1, keep=0.25))
    assert lost.wages[0, 1] == pytest.approx(0.25 * plain.wages[0, 1])
    assert lost.wages[0, 2] == plain.wages[0, 2]


def test_a_market_drop_forces_the_equity_return_of_next_year_in_every_future():
    inputs = build_inputs(make_demo_household(), n_paths=40, seed=5, shock=MarketShock(year=1, equity_return=-0.30))
    assert np.all(inputs.rets[:, 1, 0] == pytest.approx(-0.30))


# --- Comparing the years ---------------------------------------------------------------------------------


def _row(t, **kw) -> PlanRow:
    base = dict(
        year_index=t, age=50 + t, income=0, wages=100_000, roth_conversion=0, losses_harvested=0, goal_bonds_balance=0, goal_bonds_flow=0,
        goal_paid=0, stock_share=0.8, total_tax=0, federal_tax=0, illinois_tax=0, wealth=1_000_000, gains_realized_tax_free=0,
    )
    base.update(kw)
    return PlanRow(**base)


def test_only_material_differences_are_marked_and_each_is_attributed_to_its_source():
    base = [_row(0), _row(1), _row(2)]
    held = [_row(0), _row(1, wages=0, roth_conversion=200_000), _row(2, roth_conversion=500)]  # $500 is not material
    new = [_row(0), _row(1, wages=0, roth_conversion=200_000), _row(2, stock_share=0.7)]
    years, changes = showcase_scenarios.compare_rows(base, held, new)
    assert [y.responded for y in years] == [[], ["wages", "roth_conversion"], []]
    assert [y.replanned for y in years] == [[], [], ["stock_share"]]
    assert [(c.age, c.key, c.source) for c in changes] == [(51, "wages", "event"), (51, "roth_conversion", "event"), (52, "stock_share", "replan")]
    roth = changes[1]
    assert (roth.before, roth.after) == (0.0, 200_000.0)
    assert "$200,000" in roth.text and "$0" in roth.text
    # a year's three plans are all on the row
    assert (years[1].base_roth_conversion, years[1].held_roth_conversion, years[1].roth_conversion) == (0, 200_000, 200_000)


def test_the_summary_is_the_largest_difference_of_each_kind_without_the_wages():
    base = [_row(0), _row(1), _row(2)]
    held = [_row(0, roth_conversion=10_000), _row(1, wages=0, roth_conversion=90_000, losses_harvested=5_000), _row(2)]
    _, changes = showcase_scenarios.compare_rows(base, held, held)
    lines = showcase_scenarios.summarize(changes, "event")
    assert lines[0].startswith("At 51 $90,000 is converted")
    assert any("losses" in line for line in lines)
    assert not any("wages" in line for line in lines)
    assert showcase_scenarios.summarize(changes, "replan") == []


# --- The answer ----------------------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def answers():
    showcase.reset()
    return {key: client.get(f"/showcase/scenarios/{key}") for key in ("job_loss", "market_drop")}


def test_the_events_are_listed_and_an_unknown_one_is_not_found():
    listed = client.get("/showcase/scenarios").json()
    assert [s["key"] for s in listed] == ["job_loss", "market_drop"]
    assert [s["label"] for s in listed] == ["Job loss next year", "Market drops 30% next year"]
    assert client.get("/showcase/scenarios/nope").status_code == 404


def test_each_scenario_answers_with_the_plan_before_and_after_and_the_years(answers):
    base = showcase.showcase()
    for key, response in answers.items():
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["key"] == key
        years = body["years"]
        assert len(years) == len(base.wealth.wealth.ages) - 1
        assert [y["age"] for y in years][0] == base.household.primary_age
        # the same household: the wealth lines start where the unchanged household's start
        assert body["wealth"]["wealth"]["plan_median"][0] == pytest.approx(base.wealth.wealth.plan_median[0])
        # the plan before the event is the showcase's own plan, year for year
        assert years[1]["base_wealth"] == pytest.approx(
            showcase_scenarios._base(showcase.prepare())[1].wealth
        )
        assert body["original_plan_label"] == base.plan_label
        # the re-planned plan is worked out on the shocked futures
        replan = body["replan"]
        assert replan["median_dollars"] == pytest.approx(replan["replanned_median_at_horizon"] - replan["original_plan_median_at_horizon"])
        # every change listed has a year row that carries its flag
        for change in body["changes"]:
            row = next(y for y in years if y["age"] == change["age"])
            assert change["key"] in (row["responded"] if change["source"] == "event" else row["replanned"])


def test_a_job_loss_shows_in_the_wages_of_next_year_and_the_plan_responds_that_year(answers):
    body = answers["job_loss"].json()
    year = body["years"][1]
    assert year["wages"] == 0.0 and year["base_wages"] > 0
    assert "wages" in year["responded"]
    assert [y["wages"] for y in body["years"]][2] == body["years"][2]["base_wages"]  # back to the usual pay


def test_the_market_drop_cuts_the_wealth_of_both_sides_against_the_unchanged_household(answers):
    base = showcase.showcase().wealth.advantage
    scenario = answers["market_drop"].json()["wealth"]["advantage"]
    assert scenario["advisor_median_at_horizon"] < base.advisor_median_at_horizon
    assert scenario["plan_median_at_horizon"] < base.plan_median_at_horizon


def test_a_scenario_is_worked_out_once_and_kept(answers):
    first = showcase_scenarios.scenario("job_loss")
    assert showcase_scenarios.scenario("job_loss") is first
