"""The studies built for Update 4: the planner's valuation option, the household study's new columns, the diagnostics report and the
single-household measurements."""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest
from tests.conftest import make_demo_household

from app.planner.search import search
from app.planner.strategies import menu
from app.sim.simulate import build_inputs, run_batch
from app.study import diagnostics, update4
from app.study import household_study as hs
from app.study import households as hh

FUND_PLAN = next(s for s in menu(style="equity_first") if not s.direct_indexing and s.reserve_years)
DI_PLAN = next(s for s in menu(style="equity_first") if s.direct_indexing)


# --- The planner can score under either valuation ---------------------------------------------------------------------


def test_the_search_scores_the_valuation_it_is_asked_for():
    inputs = build_inputs(make_demo_household(), n_paths=60, seed=3)
    strategies = [s for s in menu(style="equity_first") if not s.direct_indexing][:30]
    liquidated = search(inputs, strategies=strategies)
    heirs = search(inputs, strategies=strategies, valuation="heirs")
    batch = run_batch(inputs, [s.policy() for s in strategies])
    for result, matrix in ((liquidated, batch.wealth), (heirs, batch.wealth_heirs)):
        top = result.best
        assert top.outcome.median == pytest.approx(float(np.median(matrix[strategies.index(top.strategy)])))
    assert heirs.best.outcome.median != liquidated.best.outcome.median or heirs.best.strategy != liquidated.best.strategy
    with pytest.raises(ValueError, match="valuation"):
        search(inputs, strategies=strategies, valuation="after the war")


# --- The household study ----------------------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def row():
    item = hh.generate(seed=10, per_type=1)[2]
    return hs.household_row(item, 2, n_search=40, n_eval=50, risk_aversion=3.0, style="equity_first", giving_share=0.01)


def test_the_row_has_both_valuations_against_both_advisors_and_the_typical_advisor_before_distributions(row):
    for key in ("good_ria", "typical_advisor", "typical_advisor_no_dist"):
        for measure in ("median", "risk_adjusted"):
            assert np.isfinite(row[f"adv_{measure}_vs_{key}"]) and np.isfinite(row[f"passed_adv_{measure}_vs_{key}"])
    assert row["passed_plan_median"] > 0 and row["valuation"] == "liquidated"
    # the typical advisor's funds pay distributions now: the plan is further ahead of it than of the advisor it was before
    assert row["adv_median_vs_typical_advisor"] > row["adv_median_vs_typical_advisor_no_dist"]


def test_the_row_values_what_giving_lots_instead_of_cash_is_worth(row):
    assert row["giving"] > 0
    assert row["plan_cash_gifts_median"] > 0
    assert np.isfinite(row["lots_for_cash_median"]) and np.isfinite(row["passed_lots_for_cash_median"])
    assert row["lots_for_cash_median"] == pytest.approx(
        (row["plan_median"] / row["plan_cash_gifts_median"]) ** (1.0 / row["years"]) - 1.0, rel=1e-9
    )


def test_the_study_report_has_a_table_of_the_two_valuations():
    columns = {}
    for key in ("good_ria", "typical_advisor", "typical_advisor_no_dist"):
        for measure in ("median", "risk_adjusted"):
            columns[f"adv_{measure}_vs_{key}"] = [0.015, 0.016, 0.017]
            columns[f"passed_adv_{measure}_vs_{key}"] = [0.02, 0.021, 0.022]
    frame = pd.DataFrame({"type": ["diversified", "diversified", "big_gains"], **columns, "valuation": ["liquidated"] * 3})
    text = "\n".join(hs.valuation_sections(frame))
    assert "The two valuations at 80" in text and "Liquidated at 80" in text and "Passed to heirs at 80" in text
    assert "Typical advisor without distributions" in text and "+1.60%" in text and "+2.10%" in text


def test_the_old_flat_rate_sensitivity_is_not_confused_with_the_engines_valuation():
    # the engine's second valuation is "passed_..." columns; a flat heirs' rate is a column that ends "_heirs24"
    assert not hs._HEIRS_RATE_COLUMN.search("passed_adv_median_vs_good_ria")
    assert hs._HEIRS_RATE_COLUMN.search("adv_median_vs_good_ria_heirs24")


# --- The diagnostics ---------------------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def diagnosed():
    return diagnostics.diagnose(make_demo_household(), "A test household", eval_paths=40, strategy=FUND_PLAN)


def test_the_diagnostics_cover_the_plan_and_both_advisors_and_serialize(diagnosed):
    assert [s["key"] for s in diagnosed["subjects"]] == ["plan", "good_ria", "typical_advisor"]
    assert diagnosed["n_paths"] == 40 and diagnosed["strategy"] == FUND_PLAN.short_label()
    json.dumps(diagnosed)


def test_the_diagnostics_add_up(diagnosed):
    for s in diagnosed["subjects"]:
        sales = s["sales"]
        by_purpose = sales["by_purpose"]
        assert sum(p["sold"] for p in by_purpose) == pytest.approx(sales["total_sold"]["mean"], rel=1e-9)
        assert sum(p["gain"] for p in by_purpose) == pytest.approx(sales["total_gain"]["mean"], rel=1e-9, abs=1e-6)
        assert sum(p["tax"] for p in by_purpose) == pytest.approx(sales["capital_gains_tax"]["mean"], rel=1e-9, abs=1e-6)
        assert sum(t["tax"] for t in s["taxes_by_type"]["by_type"]) == pytest.approx(s["taxes_by_type"]["total"]["mean"], rel=1e-9)
        assert s["taxes_by_type"]["total"]["mean"] == pytest.approx(s["lifetime_taxes_paid"]["mean"], rel=1e-9)
        lots = s["lots"]
        # a gain is realized now or left for later: the two rules end with the same total
        hifo = lots["hifo_gain"]["mean"] + lots["hifo_unrealized_at_horizon"]["mean"]
        fifo = lots["fifo_gain"]["mean"] + lots["fifo_unrealized_at_horizon"]["mean"]
        assert hifo == pytest.approx(fifo, rel=1e-8, abs=1e-3)
        assert s["horizon"]["tax_charged_when_passed_to_heirs"]["mean"] == 0.0
        assert s["horizon"]["tax_charged_when_liquidated"]["mean"] >= 0.0
        reserve = s["reserve"]
        assert reserve["average_pretax"] + reserve["average_roth"] + reserve["average_brokerage"] > 0


def test_the_advisors_are_reported_on_the_rules_they_use(diagnosed):
    plan, ria, typical = diagnosed["subjects"]
    assert plan["lots"]["run_used"].startswith("hifo") and ria["lots"]["run_used"].startswith("fifo")
    assert typical["lots"]["run_used"] == "fifo" and ria["lots"]["run_used"] == "fifo with harvesting"
    assert typical["sales"]["fund_distributions"]["mean"] > 0 and ria["sales"]["fund_distributions"]["mean"] == 0.0
    assert plan["sales"]["fund_distributions"]["mean"] == 0.0


def test_the_report_has_the_five_parts_the_diagnostics_were_asked_for(diagnosed):
    text = diagnostics.render(diagnosed)
    for heading in (
        "A. Stock sold from the brokerage account, by purpose",
        "B. The same sales under highest-cost-first and first-in-first-out",
        "C. Where the spending reserve is held",
        "D. Unrealized brokerage gain at 80",
        "E. Lifetime income tax, by the kind of income",
    ):
        assert heading in text
    for label in ("Donabach plan", "Good RIA", "Typical advisor"):
        assert label in text
    for purpose in ("Goals", "Retirement spending", "Income taxes", "Rebalancing", "Refilling the reserve"):
        assert purpose in text


def test_giving_shows_up_in_the_diagnostics_when_the_household_gives():
    household = make_demo_household()
    goals = household.goals.model_copy(update={"charitable_giving": 15_000.0})
    household = household.model_copy(update={"goals": goals})
    result = diagnostics.diagnose(household, "A giving household", eval_paths=30, strategy=FUND_PLAN)
    plan, ria, _ = result["subjects"]
    assert plan["sales"]["gifts_in_kind"]["mean"] > 0 and plan["sales"]["gain_given_away"]["mean"] > 0
    assert ria["sales"]["gifts_in_kind"]["mean"] == 0.0 and ria["sales"]["gifts_in_cash"]["mean"] > 0
    assert any(label.startswith("charitable gifts") for label in (p["purpose"] for p in plan["sales"]["by_purpose"]))


# --- The single-household measurements ----------------------------------------------------------------------------------


@pytest.fixture
def small(monkeypatch):
    monkeypatch.setattr(update4, "EVAL_PATHS", 120)
    monkeypatch.setattr(update4, "SEARCH_PATHS", 60)


def test_direct_indexing_is_measured_against_the_old_rule_and_off(small):
    household = make_demo_household()
    result = update4.direct_indexing_benefit(household, DI_PLAN)
    for valuation in ("liquidated", "heirs"):
        for key in ("old_rule", "stock_by_stock", "fitted_rule"):
            assert np.isfinite(result[valuation][key]["median"])
    harvested = result["harvested_losses"]
    assert harvested["no_direct_indexing"] >= 0.0 and harvested["old_rule"] > 0.0 and harvested["stock_by_stock"] > 0.0
    assert result["idio_vol"] == 0.25 and result["theta"] == 0.01


def test_the_stock_level_benefit_rises_with_the_stocks_own_volatility(small):
    household = make_demo_household()
    low = update4.direct_indexing_benefit(household, DI_PLAN, idio_vol=0.10)["harvested_losses"]["stock_by_stock"]
    high = update4.direct_indexing_benefit(household, DI_PLAN, idio_vol=0.40)["harvested_losses"]["stock_by_stock"]
    assert high > low


def test_the_advantages_are_given_for_both_valuations_and_both_typical_advisors(small):
    result = update4.advantages(make_demo_household(), FUND_PLAN)
    assert set(result["liquidated"]) == {"good_ria", "typical_advisor", "typical_advisor_before_distributions"} == set(result["heirs"])
    assert result["liquidated"]["typical_advisor"]["median"] > result["liquidated"]["typical_advisor_before_distributions"]["median"]
    assert result["recommendation"] == FUND_PLAN.short_label()


def test_giving_lots_instead_of_cash_is_measured(small):
    result = update4.giving_effect(make_demo_household(), 15_000.0)
    assert result["gifts_in_kind"] > 0 and result["gain_given_away"] > 0
    assert result["lots_vs_cash"]["liquidated"]["median"] > 0  # lots beat cash: the gain on them is never taxed


def test_the_single_household_report_names_the_valuations_and_the_old_rule():
    adv = {"median": 0.016, "risk_adjusted": 0.004, "median_dollars": 1.0, "plan_median": 2.0, "baseline_median": 1.0, "median_low": 0.0, "median_high": 0.02}
    plan = {
        "recommendation": "a plan", "choices": {}, "direct_indexing": False,
        "liquidated": {k: adv for k in ("good_ria", "typical_advisor", "typical_advisor_before_distributions")},
        "heirs": {k: adv for k in ("good_ria", "typical_advisor", "typical_advisor_before_distributions")},
    }
    di = {
        "liquidated": {k: adv for k in ("old_rule", "stock_by_stock", "fitted_rule")},
        "heirs": {k: adv for k in ("old_rule", "stock_by_stock", "fitted_rule")},
        "harvested_losses": {"old_rule": 3.0, "stock_by_stock": 2.0, "fitted_rule": 2.5, "no_direct_indexing": 0.0},
        "harvested_per_year_share_of_brokerage_today": {"old_rule": 0.03, "stock_by_stock": 0.02, "fitted_rule": 0.025, "no_direct_indexing": 0.0},
    }
    giving = {"giving": 10_000.0, "recommendation": "a plan", "lots_vs_cash": {"liquidated": adv, "heirs": adv}, "plan_vs_good_ria": {"liquidated": adv, "heirs": adv},
              "gifts_in_kind": 1.0, "gain_given_away": 1.0, "gifts_in_cash": 1.0}
    text = update4.render([{"household": "A household", "plan": plan, "plan_for_heirs": plan, "direct_indexing": di, "sensitivity": {"sigma=0.25": 0.01}, "giving": giving}])
    for expected in ("Liquidated at 80", "Passed to heirs at 80", "The old rule (85% of a decline plus 3% a year)", "100 stocks with lots", "Giving $10,000 a year"):
        assert expected in text
