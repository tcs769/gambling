"""The equity-share and reach studies, and the household study's growth and heirs-tax options.

These are analyses, not app behavior: they must not change what the app does, and what they print must be what the
engine produces. Sample sizes are small; the effects asserted here are large relative to the noise they carry.
"""

from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from app.planner.baseline import RIA_BASELINE
from app.planner.strategies import Strategy
from app.sim import markets
from app.sim.simulate import DONABACH_FLAT_FEE, ModelOptions, build_inputs, run_batch, run_detail
from app.study import equity_share as es
from app.study import reach as rc
from app.study.households import generate
from app.study.measure import sample_household
from app.tax.engine import pretax_withdrawal_rate

SPEC_MARKET = markets.DEFAULT_ASSUMPTIONS


def strategy(share=0.5, pc=0.15, conversion="none") -> Strategy:
    return Strategy(share, conversion, pc, False, False)


def small_menu() -> list[Strategy]:
    return [strategy(s, pc, "fill24_every") for s in (0.5, 1.0) for pc in (0.0, 0.15)]


# --- How much equity a plan holds -------------------------------------------------------------------------------


def test_equity_exposure_counts_the_private_credit_sleeve_and_the_glide():
    ria = lambda age: es.equity_exposure(RIA_BASELINE, age, 38.0)  # noqa: E731
    assert ria(38) == pytest.approx(0.80) and ria(58) == pytest.approx(0.80 - 0.30 * 20 / 32) and ria(70) == ria(79) == pytest.approx(0.50)
    low = strategy(0.5, 0.15).policy()  # 50% of the money outside a 15% sleeve is 42.5% of the portfolio
    assert es.equity_exposure(low, 38, 38.0) == pytest.approx(0.425) and es.equity_exposure(low, 58, 38.0) == pytest.approx(0.425)
    assert es.equity_exposure(low, 70, 38.0) == pytest.approx(0.25 * 0.85)
    full = strategy(1.0, 0.0).policy()
    assert [es.equity_exposure(full, a, 38.0) for a in (58, 64, 70)] == pytest.approx([1.0, 0.875, 0.75])


def test_the_exposure_helper_matches_what_the_engine_holds():
    household = sample_household()
    inputs = build_inputs(household, deterministic=True)
    for policy in (strategy(0.5, 0.15).policy(), strategy(0.8, 0.0).policy(), RIA_BASELINE):
        log = run_detail(inputs, policy).log
        for t in (0, 5):
            age = household.primary_age + t
            assert log["equity_share"][t] == pytest.approx(es.equity_exposure(policy, age, household.primary_age), abs=0.02), (policy.stock_share, t)


# --- Choosing and scoring --------------------------------------------------------------------------------------


def test_pick_takes_the_largest_feasible_value_and_the_first_on_a_tie():
    values = np.array([1.0, 5.0, 5.0, 3.0])
    assert es.pick(values) == 1
    assert es.pick(values, np.array([True, False, True, True])) == 2
    assert es.pick(values, np.array([False, False, False, False])) is None


def test_the_annualized_advantage_is_the_growth_rate_difference():
    assert es.annualized(1.121, 1.0, 42) == pytest.approx(1.121 ** (1 / 42) - 1)
    assert list(es.annualized(np.array([1.0, 2.0]), 1.0, 2)) == pytest.approx([0.0, 2 ** 0.5 - 1])


def test_the_advisor_allocation_chain_changes_the_tools_and_never_the_allocation():
    target = strategy(1.0, 0.15, "fill24_every")
    chain = es.advisor_allocation_chain(target)
    assert [label for label, _ in chain][0] == "Lower fee (0.35% flat)" and len(chain) == 5
    for _, policy in chain:
        assert policy.stock_share == RIA_BASELINE.stock_share and policy.private_credit == 0.0
        assert policy.glide_start_age is None and policy.glide_drop == RIA_BASELINE.glide_drop
    first, last = chain[0][1], chain[-1][1]
    assert not first.breakpoint_fees and first.flat_fee == DONABACH_FLAT_FEE and not first.donabach_location
    assert last.donabach_location and last.conversion_top == target.policy().conversion_top and last.conversion_every_year


def test_return_equivalent_recovers_a_known_shift_and_is_zero_when_nothing_is_needed():
    held = build_inputs(sample_household(), n_paths=60, seed=5)
    shifted = replace(held, rets=held.rets + 0.01)
    target = float(np.median(run_batch(shifted, [RIA_BASELINE]).wealth[0]))
    assert es.return_equivalent(held, target, tol=1e-7) == pytest.approx(0.01, abs=2e-5)
    assert es.return_equivalent(held, 1.0) == 0.0


def test_a_small_study_finds_more_median_wealth_in_more_equity_and_prints_what_it_found():
    study = es.run_study(n_design=150, n_eval=150, strategies=small_menu(), with_return_equivalents=False)
    sweep = {result.label.split(" (")[0]: result for result in study.sweep}
    assert len(study.sweep) in (6, 12)
    assert sweep["100% stocks, 0% private credit"].raw.median > sweep["50% stocks, 0% private credit"].raw.median + 0.005
    assert sweep["100% stocks, 0% private credit"].median > sweep["50% stocks, 0% private credit"].median
    # every row of every table is scored against the same good advisor on the same futures
    assert study.baseline.raw.median == 0.0 and study.frontier[-1].label.startswith("median wealth")
    assert study.frontier[-1].exposure[0] >= study.frontier[0].exposure[0]  # maximizing the median holds at least as much equity as risk aversion 5
    text = es.render(study)
    for needle in ("## 1. The stock share", "## 2. What Donabach's tools are worth", "## 3. What each objective picks", "## 4. The best raw advantage"):
        assert needle in text
    assert "(the recommendation)" in text


def test_the_equity_assumption_scenarios_redraw_the_futures_under_each_mean():
    names = [name for name, _ in es.MARKET_SCENARIOS]
    assert names[1].startswith("Equity 5.5%") and es.MARKET_SCENARIOS[1][1] == SPEC_MARKET
    means = [market.means[markets.EQUITY] for _, market in es.MARKET_SCENARIOS]
    assert means == pytest.approx([0.045, 0.055, 0.065, 0.075])
    assert all(market.means[1:] == SPEC_MARKET.means[1:] and market.sds == SPEC_MARKET.sds for _, market in es.MARKET_SCENARIOS)


# --- What it would take to reach 2 to 3% ---------------------------------------------------------------------


def test_moving_the_equity_mean_of_drawn_futures_is_the_same_as_drawing_them_again():
    household = sample_household()
    base = build_inputs(household, n_paths=40, seed=11)
    moved = rc.with_equity_return(base, 0.065)
    again = build_inputs(household, n_paths=40, seed=11, options=ModelOptions(market=replace(SPEC_MARKET, means=(0.065, 0.015, 0.035))))
    assert np.allclose(moved.rets, again.rets, atol=1e-12)
    assert np.array_equal(base.rets[:, :, 1:], moved.rets[:, :, 1:])  # bonds and private credit are untouched
    assert base.rets[0, 0, 0] != moved.rets[0, 0, 0]  # and the original futures are not changed in place


def test_the_pretax_balance_is_recovered_from_the_tax_still_owed_on_it():
    balances = np.array([0.0, 500_000.0, 3_000_000.0, 9_000_000.0])  # (a balance below the standard deduction owes nothing, so it cannot be recovered)
    owed = np.array([b * float(pretax_withdrawal_rate(b, 30_000.0, 1.0)) for b in balances])
    recovered = rc.pretax_balance(owed, 30_000.0, 1.0)
    assert recovered[0] == 0.0
    assert recovered[1:] == pytest.approx(balances[1:], rel=1e-4)


def test_taxing_pretax_money_more_favors_the_plan_that_holds_less_of_it():
    held = build_inputs(sample_household(), n_paths=80, seed=3)
    converting = strategy(1.0, 0.0, "fill24_every").policy()
    specified = rc.raw_with(held, converting, RIA_BASELINE)
    assert rc.raw_with(held, converting, RIA_BASELINE, heirs=None) == specified == rc.raw_advantage(held, converting)
    assert rc.raw_with(held, converting, RIA_BASELINE, heirs=0.24) > specified
    assert rc.raw_with(held, converting, RIA_BASELINE, heirs=0.32) > rc.raw_with(held, converting, RIA_BASELINE, heirs=0.24)


def test_the_equity_return_needed_for_a_target_is_solved_and_unreachable_targets_say_so():
    held = build_inputs(sample_household(), n_paths=80, seed=3)
    plan = strategy(1.0, 0.0, "fill24_every").policy()
    at_7_5 = rc.advantage_at(held, 0.075, plan)
    assert at_7_5 > rc.advantage_at(held, 0.055, plan)
    assert rc.solve_equity_return(held, plan, at_7_5) == pytest.approx(0.075, abs=3e-4)
    assert rc.solve_equity_return(held, plan, -0.5) == rc.SPEC_EQUITY_RETURN  # already reached at the specified return
    assert rc.solve_equity_return(held, plan, 0.5) is None
    assert rc.advantage_at(held, 0.055, plan, fee=0.0) > rc.advantage_at(held, 0.055, plan)  # a lower fee helps


def test_the_reach_study_measures_each_lever_and_says_what_it_found():
    reach = rc.run_reach(n_design=150, n_eval=150, strategies=small_menu())
    skill, recommendation, growth, ceiling = reach.plans
    assert ceiling.raw.median >= growth.raw.median - 0.01 and growth.raw.median >= recommendation.raw.median - 0.01
    assert skill.exposure[0] == pytest.approx(0.80)
    fees = [raw for _, raw, _ in reach.fees]
    assert [fee for fee, _, _ in reach.fees] == list(rc.FEES) and fees == sorted(fees)  # a lower fee only helps
    by_advisor = [raw for _, raw, _, _ in reach.advisor_equity]
    assert by_advisor == sorted(by_advisor, reverse=True)  # the more equity the advisor holds, the less the ceiling plan beats it
    by_return = [raw for _, raw, _, _ in reach.equity_returns]
    assert by_return == sorted(by_return)  # the ceiling plan holds more equity than the advisor, so it gains from a higher return
    heirs = [raw for _, raw, _ in reach.heirs]
    assert heirs == sorted(heirs)  # taxing pre-tax money at the horizon more favors a plan that converts
    for scenario in reach.break_even.values():
        needed = [mean for _, mean in scenario if mean is not None]
        assert needed == sorted(needed)  # a bigger target needs a bigger return
    text = rc.render(reach)
    for needle in ("**Short answer.**", "## 1. The ceiling", "## 2. One lever at a time", "## 3. What the equity return would have to be", "## 4. What is not in the engine"):
        assert needle in text
    assert "adopts none of them" in text


# --- The household study at other risk settings -----------------------------------------------------------------


def test_the_household_study_can_search_at_one_risk_aversion_and_report_at_another():
    from app.study.household_study import household_row

    item = generate(seed=10, per_type=1)[0]
    same = household_row(item, 0, 60, 60, 1.0)
    other = household_row(item, 0, 60, 60, 1.0, measure_risk_aversion=3.0)
    assert same["strategy"] == other["strategy"] and same["adv_median_vs_good_ria"] == other["adv_median_vs_good_ria"]
    assert same["adv_risk_adjusted_vs_good_ria"] != other["adv_risk_adjusted_vs_good_ria"]
    assert not any("_heirs" in key for key in same)


def test_the_household_study_reports_a_heirs_tax_sensitivity_when_asked():
    import pandas as pd

    from app.study.household_study import household_row, summarize

    items = generate(seed=10, per_type=1)
    rows = [household_row(item, i, 60, 60, 1.0, measure_risk_aversion=3.0, heirs_rates=(0.24, 0.32)) for i, item in enumerate(items)]
    frame = pd.DataFrame(rows)
    for key in ("good_ria", "typical_advisor"):
        for rate in (24, 32):
            assert np.isfinite(frame[f"adv_median_vs_{key}_heirs{rate}"]).all()
    text = summarize(frame, 60, 1.0, 3.0)
    assert "## If heirs paid a flat tax on pre-tax money at the horizon (sensitivity)" in text and "Heirs at 24% | Heirs at 32%" in text
    assert "the planner searched at risk aversion 1; risk-adjusted figures are at risk aversion 3" in text
    plain = summarize(pd.DataFrame([household_row(item, i, 60, 60, 3.0) for i, item in enumerate(items)]), 60, 3.0)
    assert "heirs" not in plain.lower().replace("heirs' taxes", "")


# --- The plan sentence says how much is held in stocks ---------------------------------------------------------


def test_the_plan_sentence_says_how_much_of_the_portfolio_is_in_stocks_when_there_is_a_private_credit_sleeve():
    with_sleeve = strategy(0.5, 0.15, "fill24_every").describe()
    assert "Hold 50% of the money outside the private credit sleeve in stocks (42.5% of the portfolio) until 58" in with_sleeve
    assert "keep a 15% private credit sleeve" in with_sleeve
    assert "(63% of the portfolio)" in strategy(0.7, 0.10).describe()
    without = strategy(0.5, 0.0).describe()
    assert without.startswith("Hold 50% of long-term money in stocks until 58") and "portfolio)" not in without
