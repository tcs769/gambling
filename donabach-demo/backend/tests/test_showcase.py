"""The strategy waterfall and the showcase household: a card, the waterfall with strategies switched on and off, wealth over time."""

from __future__ import annotations

import json

import numpy as np
import pytest
from app import showcase
from app.planner.baseline import RIA_BASELINE
from app.planner.strategies import Strategy
from app.planner.waterfall import run_waterfall, waterfall_strategies
from app.schemas import Accounts, Goals, Household, Person, SocialSecurity
from app.sim.simulate import build_inputs, run_batch
from fastapi.testclient import TestClient
from tests.conftest import make_demo_household

client = TestClient(__import__("app.main", fromlist=["app"]).app)

STRATEGIES = {
    "equity first with conversions and borrowing": Strategy(1.0, "fill24_every", 0.15, True, False, "pretax", "borrow", reserve_years=6),
    "balanced with goal bonds, Roth 401(k)": Strategy(0.7, "fill22_low", 0.10, False, True, "roth_low"),
    "plain": Strategy(0.8, "none", 0.0, False, False),
}


# --- The waterfall -------------------------------------------------------------------------------------


@pytest.mark.parametrize("name", STRATEGIES)
def test_with_every_strategy_on_the_chain_ends_on_the_chosen_policy(name):
    strategy = STRATEGIES[name]
    policy = RIA_BASELINE
    for step in waterfall_strategies(strategy):
        policy = step.change(policy)
    assert policy == strategy.policy()


def test_only_the_strategies_the_plan_uses_are_bars():
    keys = lambda s: [step.key for step in waterfall_strategies(s)]  # noqa: E731
    assert keys(STRATEGIES["plain"]) == ["fee", "location", "lots", "allocation", "withdrawals"]
    assert keys(STRATEGIES["equity first with conversions and borrowing"]) == [
        "fee", "location", "lots", "harvest", "allocation", "private_credit", "conversions", "withdrawals", "borrow",
    ]
    assert "k401" in keys(STRATEGIES["balanced with goal bonds, Roth 401(k)"])


@pytest.fixture(scope="module")
def inputs():
    return build_inputs(make_demo_household(), n_paths=120, seed=31)


def test_the_bars_add_up_to_the_total_on_the_same_futures(inputs):
    strategy = STRATEGIES["equity first with conversions and borrowing"]
    result = run_waterfall(inputs, strategy)
    assert sum(b.delta_rate for b in result.bars) == pytest.approx(result.advantage.median, abs=1e-12)
    assert sum(b.delta_dollars for b in result.bars) == pytest.approx(result.advantage.median_dollars, abs=1e-6)
    assert result.bars[-1].cumulative_rate == pytest.approx(result.advantage.median, abs=1e-12)
    # the advisor and the plan are exactly what the engine gives them on those futures
    batch = run_batch(inputs, [RIA_BASELINE, strategy.policy()])
    assert np.array_equal(result.baseline_wealth, batch.wealth[0]) and np.array_equal(result.plan_wealth, batch.wealth[1])


def test_with_every_strategy_off_the_plan_is_the_advisor(inputs):
    result = run_waterfall(inputs, STRATEGIES["plain"], enabled=set())
    assert np.array_equal(result.plan_wealth, result.baseline_wealth)
    assert all(not b.enabled and b.delta_rate == 0.0 and b.delta_dollars == 0.0 for b in result.bars)
    assert result.advantage.median == 0.0


def test_switching_a_strategy_off_re_runs_the_chain_without_it(inputs):
    strategy = STRATEGIES["equity first with conversions and borrowing"]
    everything = run_waterfall(inputs, strategy)
    without = run_waterfall(inputs, strategy, enabled={s.key for s in waterfall_strategies(strategy)} - {"conversions"})
    off = next(b for b in without.bars if b.key == "conversions")
    assert not off.enabled and off.delta_rate == 0.0 and off.delta_dollars == 0.0
    assert sum(b.delta_rate for b in without.bars) == pytest.approx(without.advantage.median, abs=1e-12)  # the rest still add up
    assert without.advantage.median < everything.advantage.median  # conversions are worth something to this household
    # the same futures give the same answer: the plan without conversions is the chosen policy with conversions removed
    manual = run_batch(inputs, [strategy.policy().replace(conversion_top=0.0, conversion_every_year=False)])
    assert np.array_equal(without.plan_wealth, manual.wealth[0])


def test_a_strategy_that_depends_on_another_does_nothing_without_it(inputs):
    strategy = STRATEGIES["equity first with conversions and borrowing"]
    keys = {s.key for s in waterfall_strategies(strategy)}
    result = run_waterfall(inputs, strategy, enabled=keys - {"location"})
    sleeve = next(b for b in result.bars if b.key == "private_credit")
    assert abs(sleeve.delta_dollars) < 1e-6  # private credit is only ever held through asset location


# --- The card -------------------------------------------------------------------------------------------


def household(**kw) -> Household:
    base = dict(
        people=[Person(name="Dana", age=52, wages=200_000), Person(name="Eli", age=50, wages=90_000)],
        children_ages=[16],
        accounts=Accounts(brokerage_value=1_000_000, brokerage_basis=250_000, pretax_balance=1_500_000, roth_balance=100_000, cash=60_000),
        goals=Goals(home_purchase_in_years=None, college_starts_in_years=2, college_annual_cost=40_000, retirement_age=58, retirement_spending=160_000),
        social_security=SocialSecurity(annual_benefit=60_000, start_age=67),
    )
    base.update(kw)
    return Household(**base)


def test_the_card_says_what_the_household_has_and_wants():
    card = showcase.build_card(household())
    assert [p.label for p in card.people] == ["Dana", "Eli"] and card.annual_income == 290_000
    assert card.total_savings == pytest.approx(2_660_000)
    by_key = {a.key: a for a in card.accounts}
    assert by_key["taxable"].unrealized_gain == pytest.approx(750_000) and by_key["taxable"].basis == 250_000
    assert sum(a.share for a in card.accounts) == pytest.approx(1.0)
    assert [g.key for g in card.goals] == ["college", "retirement", "social_security"]  # no home purchase was asked for
    retirement = next(g for g in card.goals if g.key == "retirement")
    assert retirement.years_from_now == 6 and "58" in retirement.detail and "$160,000" in retirement.detail


def test_the_notes_are_computed_from_the_household_and_only_when_they_apply():
    notes = showcase.build_card(household()).notes
    assert any("$750,000" in n and "75%" in n for n in notes)  # the unrealized gain
    assert any("9 years before Social Security" in n for n in notes)  # retires at 58, Social Security starts at 67
    plain = showcase.build_card(
        household(accounts=Accounts(brokerage_value=100_000, brokerage_basis=95_000, pretax_balance=100_000, roth_balance=300_000, cash=0.0),
                  goals=Goals(home_purchase_in_years=None, college_starts_in_years=None, retirement_age=65))
    ).notes
    assert plain == []  # nothing stands out, so nothing is said
    single = showcase.build_card(household(people=[Person(age=45, wages=100_000)], children_ages=[]))
    assert [p.label for p in single.people] == ["Earner 1"] and single.children_ages == []


# --- The endpoints --------------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def fixture_file(tmp_path_factory):
    path = tmp_path_factory.mktemp("showcase") / "showcase.json"
    path.write_text(
        json.dumps(
            {
                "id": "test", "name": "The Tests", "type_label": "Diversified", "tagline": "A household for the tests.",
                "household": json.loads(make_demo_household().model_dump_json()),
            }
        )
    )
    return path


@pytest.fixture(scope="module")
def served(fixture_file):
    mp = pytest.MonkeyPatch()
    mp.setenv(showcase.FIXTURE_ENV, str(fixture_file))
    showcase.reset()
    yield client.get("/showcase").json()
    showcase.reset()
    mp.undo()


def test_the_showcase_comes_with_its_card_and_the_waterfall_with_every_strategy_on(served):
    assert served["name"] == "The Tests" and served["card"]["people"][0]["age"] == 38
    w = served["waterfall"]
    assert w["enabled"] == [b["key"] for b in w["bars"]] and all(b["enabled"] for b in w["bars"])
    assert sum(b["delta_rate"] for b in w["bars"]) == pytest.approx(w["advantage"]["median_rate"], abs=1e-12)
    assert sum(b["delta_dollars"] for b in w["bars"]) == pytest.approx(w["advantage"]["median_dollars"], abs=1e-6)
    assert w["n_paths"] == 2000 and w["years"] == 42 and w["horizon_age"] == 80
    assert "Hold" in served["plan_sentence"]


def test_the_waterfall_is_about_the_median_alone_and_the_risk_adjusted_advantage_is_shown_once_with_the_whole_plan(served):
    assert set(served["waterfall"]["advantage"]) == {
        "median_rate", "median_dollars", "median_low", "median_high", "plan_median_at_horizon", "advisor_median_at_horizon",
    }
    toggled = client.post("/showcase/analysis", json={"enabled": ["fee"]}).json()
    assert not any("risk" in key for key in toggled["advantage"]) and "wealth" not in toggled
    wealth = served["wealth"]
    assert wealth["risk_adjusted_label"] == "Risk-adjusted advantage" and "\n" not in wealth["risk_adjusted_explanation"]  # one line
    assert wealth["advantage"]["risk_adjusted_rate"] != 0.0


def test_the_wealth_lines_start_together_and_end_where_the_headline_ends(served):
    w, adv = served["wealth"]["wealth"], served["wealth"]["advantage"]
    assert w["ages"][0] == 38 and w["ages"][-1] == 80 and len(w["ages"]) == 43
    assert w["plan_median"][0] == w["advisor_median"][0] == w["plan_p10"][0] == w["advisor_p10"][0]
    assert w["plan_median"][-1] == pytest.approx(adv["plan_median_at_horizon"]) and w["advisor_p10"][-1] == pytest.approx(adv["advisor_p10_at_horizon"])
    assert all(m >= p for m, p in zip(w["plan_median"], w["plan_p10"], strict=True))
    assert adv["plan_median_at_horizon"] - adv["advisor_median_at_horizon"] == pytest.approx(adv["median_dollars"], abs=1e-6)
    # the waterfall with every strategy on and the wealth view of the whole plan are the same measurement
    assert served["waterfall"]["advantage"]["median_rate"] == pytest.approx(adv["median_rate"], abs=1e-12)


def test_the_headline_is_the_engine_s_number_for_the_chosen_plan(served):
    prepared = showcase.prepare()
    batch = run_batch(prepared.inputs, [RIA_BASELINE, prepared.strategy.policy()])
    a = served["wealth"]["advantage"]
    assert a["plan_median_at_horizon"] == pytest.approx(float(np.median(batch.wealth[1])))
    assert a["advisor_median_at_horizon"] == pytest.approx(float(np.median(batch.wealth[0])))
    assert a["plan_shortfall"] == pytest.approx(float(np.mean(batch.unfunded[1] > 0)))


def test_switching_strategies_off_recomputes_the_waterfall_and_nothing_else(served):
    everything = served["waterfall"]
    keys = [b["key"] for b in everything["bars"]]
    r = client.post("/showcase/analysis", json={"enabled": [k for k in keys if k != "conversions"]})
    assert r.status_code == 200
    off = r.json()
    assert off["enabled"] == [k for k in keys if k != "conversions"]
    assert next(b for b in off["bars"] if b["key"] == "conversions") == {**next(b for b in off["bars"] if b["key"] == "conversions"), "enabled": False, "delta_rate": 0.0, "delta_dollars": 0.0}
    assert off["advantage"]["median_rate"] < everything["advantage"]["median_rate"]
    assert sum(b["delta_rate"] for b in off["bars"]) == pytest.approx(off["advantage"]["median_rate"], abs=1e-12)  # the rest still add up
    none = client.post("/showcase/analysis", json={"enabled": []}).json()
    assert none["advantage"]["median_rate"] == 0.0
    assert client.post("/showcase/analysis", json={"enabled": None}).json()["advantage"] == everything["advantage"]
    assert client.post("/showcase/analysis", json={}).json()["enabled"] == keys
    # the whole-plan view does not move with the switches
    assert client.get("/showcase").json()["wealth"] == served["wealth"]


def test_an_unknown_strategy_is_refused(served):
    r = client.post("/showcase/analysis", json={"enabled": ["fee", "magic"]})
    assert r.status_code == 422 and "magic" in r.json()["detail"]


def test_the_median_only_mode_gives_the_same_bars_without_the_risk_adjusted_measure(inputs):
    strategy = STRATEGIES["equity first with conversions and borrowing"]
    full = run_waterfall(inputs, strategy, {"fee", "conversions"})
    light = run_waterfall(inputs, strategy, {"fee", "conversions"}, median_only=True)
    assert [b.delta_dollars for b in light.bars] == [b.delta_dollars for b in full.bars]
    assert light.advantage.median == full.advantage.median and light.advantage.median_range == full.advantage.median_range
    assert light.advantage.risk_adjusted == 0.0 and light.advantage.risk_adjusted_range == (0.0, 0.0)
    assert full.advantage.risk_adjusted != 0.0 and light.plan_paths.shape[0] == 0


def test_precomputing_leaves_nothing_to_simulate_for_the_screens_or_for_switching_one_strategy_off(fixture_file, monkeypatch):
    monkeypatch.setenv(showcase.FIXTURE_ENV, str(fixture_file))
    showcase.reset()
    calls = []
    real = showcase.run_waterfall
    monkeypatch.setattr(showcase, "run_waterfall", lambda *a, **k: calls.append(1) or real(*a, **k))
    prepared = showcase.precompute()
    keys = [s.key for s in waterfall_strategies(prepared.strategy)]
    assert len(calls) == 1 + len(keys)  # the whole plan, then each strategy off in turn
    calls.clear()
    showcase.showcase()
    for key in keys:
        showcase.analyze(prepared, [k for k in keys if k != key])
    showcase.analyze(prepared)
    assert calls == []  # all kept
    showcase.analyze(prepared, keys[:2])  # a set nobody asked for yet is simulated on request
    assert len(calls) == 1
    showcase.reset()


def test_the_footer_says_the_results_are_this_household_s_and_what_a_typical_household_sees(tmp_path):
    assert showcase.footer_note(0.0163) == "Results for this household. A typical household in our model sees about 1.6% a year."
    assert showcase.footer_note(0.0171) == "Results for this household. A typical household in our model sees about 1.7% a year."
    assert showcase.footer_note(None) == "Results for this household."
    table = tmp_path / "study.csv"
    table.write_text("type,index,adv_median_vs_good_ria\na,0,0.010\na,1,0.020\nb,0,0.030\n")
    assert showcase.typical_rate(table) == pytest.approx(0.020)
    assert showcase.typical_rate(tmp_path / "missing.csv") is None
    shipped = showcase.typical_rate()  # the 300-household study that ships with the repo
    assert shipped is not None and 0.0 < shipped < 0.05


def test_the_response_carries_the_typical_household_and_the_footer_line(served):
    assert served["typical_rate"] == pytest.approx(showcase.typical_rate())
    assert served["footer_note"] == showcase.footer_note(served["typical_rate"])


def test_the_shipped_fixture_is_a_valid_household_with_a_plan():
    fixture = showcase.load_fixture(showcase.FIXTURE)
    assert fixture.id and fixture.name and fixture.household.horizon_years <= 62
    assert fixture.type_label and fixture.tagline and len(fixture.household.people) >= 1
