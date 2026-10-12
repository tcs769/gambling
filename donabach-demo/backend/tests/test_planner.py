"""M4: strategy menu, search, advantage attribution and per-year decision detail."""

from __future__ import annotations

import time

import numpy as np
import pytest
from tests.conftest import make_demo_household

from app.planner import explain
from app.planner.baseline import RIA_BASELINE
from app.planner.search import (
    SCREEN_KEEP,
    RISK_AVERSION,
    WEALTH_FLOOR,
    Outcome,
    certainty_equivalent,
    rank_strategies,
    search,
)
from app.planner.strategies import CHOICE_OPTIONS, CHOICES, CONVERSION_OPTIONS, Strategy, menu
from app.sim import simulate as sim
from app.sim.simulate import build_inputs, run_batch, run_detail
from app.tax import params_2026 as P

# --- Menu ----------------------------------------------------------------------------------


def test_menu_has_every_combination_exactly_once():
    strategies = menu()
    assert len(strategies) == 6 * 7 * 4 * 2 * 2 * 3 * 2 == 4032
    assert len({s.key for s in strategies}) == 4032
    assert len(CONVERSION_OPTIONS) == 7
    assert {s.stock_share for s in strategies} == {0.50, 0.60, 0.70, 0.80, 0.90, 1.00}


def test_choices_round_trip_through_the_recommender_vocabulary():
    assert tuple(CHOICE_OPTIONS) == CHOICES
    for s in menu():
        assert Strategy.from_choices(s.choices()) == s
        assert set(s.choices()) == set(CHOICES)
        for choice, option in s.choices().items():
            assert option in CHOICE_OPTIONS[choice]


def test_strategy_maps_to_the_specified_policy():
    s = Strategy(0.90, "fill22_low", 0.10, True, False)
    p = s.policy()
    assert (p.stock_share, p.glide_start_age, p.glide_drop) == (0.90, 58.0, 0.25)
    assert p.private_credit == 0.10 and p.direct_indexing and not p.goal_bonds
    assert p.conversion_top == P.TOP_OF_22 and not p.conversion_every_year
    assert p.donabach_location and p.bracket_withdrawals and not p.breakpoint_fees
    assert p.flat_fee == 0.0035 and p.withdrawal_top == P.TOP_OF_22
    none = Strategy(0.70, "none", 0.0, False, True).policy()
    assert none.conversion_top == 0.0 and none.private_credit == 0.0 and none.goal_bonds
    assert Strategy(0.8, "fill12_every", 0.0, False, False).policy().conversion_every_year


def test_strategy_sentence_reflects_the_choices():
    text = Strategy(0.90, "fill22_low", 0.10, True, True).describe()
    for phrase in ("90%", "22% bracket", "low-income years and retirement", "private credit", "direct indexing", "four years ahead"):
        assert phrase in text
    plain = Strategy(0.70, "none", 0.0, False, False).describe()
    assert "no Roth conversions" in plain and "fund level" in plain and "private credit" not in plain
    assert "every year" in Strategy(0.8, "fill24_every", 0.0, False, False).describe()


def test_private_credit_is_a_four_option_sleeve():
    assert CHOICE_OPTIONS["private_credit"] == ("0", "5", "10", "15")
    for pct, share in (("0", 0.0), ("5", 0.05), ("10", 0.10), ("15", 0.15)):
        choices = dict(Strategy(0.8, "none", share, False, False).choices())
        assert choices["private_credit"] == pct
        assert Strategy.from_choices(choices).policy().private_credit == pytest.approx(share)
    assert {s.private_credit for s in menu()} == {0.0, 0.05, 0.10, 0.15}
    with pytest.raises(ValueError):
        Strategy(0.8, "none", 0.07, False, False)
    text = Strategy(0.8, "none", 0.05, False, False).describe()
    assert "5% private credit sleeve" in text and "pre-tax account first" in text
    assert "15% private credit" in Strategy(0.8, "none", 0.15, False, False).short_label()
    assert "private credit" not in Strategy(0.8, "none", 0.0, False, False).short_label()


def test_the_401k_choice_is_part_of_the_strategy():
    assert CHOICE_OPTIONS["k401"] == ("pretax", "roth", "roth_low") and "k401" in CHOICES
    assert {s.k401 for s in menu()} == {"pretax", "roth", "roth_low"}
    assert Strategy(0.8, "none", 0.0, False, False).k401 == "pretax"  # the default is the old behaviour
    for option in ("pretax", "roth", "roth_low"):
        s = Strategy(0.8, "none", 0.0, False, False, option)
        assert Strategy.from_choices(s.choices()) == s and s.policy().k401 == option
    assert "Roth side" in Strategy(0.8, "none", 0.0, False, False, "roth").describe()
    assert "low-income years" in Strategy(0.8, "none", 0.0, False, False, "roth_low").describe()
    assert "401(k)" not in Strategy(0.8, "none", 0.0, False, False).describe()
    with pytest.raises(ValueError):
        Strategy(0.8, "none", 0.0, False, False, "after-tax")


def test_goal_funding_is_part_of_the_strategy():
    assert CHOICE_OPTIONS["goal_funding"] == ("sell", "borrow") and "goal_funding" in CHOICES
    assert {s.goal_funding for s in menu()} == {"sell", "borrow"}
    assert Strategy(0.8, "none", 0.0, False, False).goal_funding == "sell"  # the default is the old behaviour
    borrow = Strategy(0.8, "none", 0.0, False, False, "pretax", "borrow")
    assert Strategy.from_choices(borrow.choices()) == borrow and borrow.policy().goal_funding == "borrow"
    assert "box-spread loan" in borrow.describe() and "borrow for goals" in borrow.short_label()
    assert "box-spread" not in Strategy(0.8, "none", 0.0, False, False).describe()
    with pytest.raises(ValueError):
        Strategy(0.8, "none", 0.0, False, False, "pretax", "margin")


def test_unknown_conversion_option_is_rejected():
    with pytest.raises(ValueError):
        Strategy(0.9, "fill99", 0.0, False, False)


# --- Score ---------------------------------------------------------------------------------


def test_certainty_equivalent_properties():
    assert RISK_AVERSION == 3.0 and WEALTH_FLOOR == 50_000.0
    assert certainty_equivalent(np.full(100, 2_000_000.0)) == pytest.approx(2_000_000.0)  # no risk
    risky = np.array([1_000_000.0, 3_000_000.0] * 50)
    assert certainty_equivalent(risky) < risky.mean()  # risk aversion penalizes spread
    assert certainty_equivalent(risky) > risky.min()
    # By hand: u(w) = w^-2, CE = (mean w^-2)^(-1/2).
    assert certainty_equivalent(risky) == pytest.approx(((1e6**-2 + 3e6**-2) / 2) ** -0.5)


def test_certainty_equivalent_floors_wealth_at_fifty_thousand():
    assert certainty_equivalent(np.array([-500_000.0, 0.0, 10_000.0])) == pytest.approx(50_000.0)
    assert certainty_equivalent(np.array([-1.0e9] * 10)) == pytest.approx(50_000.0)


def test_more_risk_aversion_means_a_lower_certainty_equivalent():
    risky = np.array([500_000.0, 1_000_000.0, 4_000_000.0] * 30)
    scores = [certainty_equivalent(risky, g) for g in (0.5, 1.0, 3.0, 6.0)]
    assert scores == sorted(scores, reverse=True)
    assert certainty_equivalent(risky, 1.0) == pytest.approx(np.exp(np.log(risky).mean()))


def test_outcome_summarizes_the_distribution():
    wealth = np.arange(1, 1001, dtype=float) * 5_000.0
    o = Outcome.of(wealth)
    assert o.median == pytest.approx(np.median(wealth)) and o.p10 == pytest.approx(np.percentile(wealth, 10))
    assert o.p10 < o.median < o.p90 and o.score < o.median


# --- Search --------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def household():
    return make_demo_household()


@pytest.fixture(scope="module")
def futures(household):
    return build_inputs(household, n_paths=400, seed=2026)


@pytest.fixture(scope="module")
def result(futures):
    return search(futures, record_paths=False)


@pytest.fixture(scope="module")
def exhaustive(futures):
    return search(futures, exhaustive=True)


def test_search_ranks_every_strategy_by_score(exhaustive):
    ranked = exhaustive.ranked
    assert len(ranked) == 4032 and exhaustive.n_considered == 4032
    scores = [r.outcome.score for r in ranked]
    assert scores == sorted(scores, reverse=True)
    assert [r.rank for r in ranked] == list(range(1, 4033))
    assert exhaustive.best is ranked[0]
    for r in ranked[:5]:
        assert r.outcome.p10 < r.outcome.median < r.outcome.p90


def test_the_staged_search_scores_the_survivors_on_every_future(result):
    assert result.n_considered == 4032 and len(result.ranked) == SCREEN_KEEP
    scores = [r.outcome.score for r in result.ranked]
    assert scores == sorted(scores, reverse=True)
    assert [r.rank for r in result.ranked] == list(range(1, SCREEN_KEEP + 1))
    assert result.batch.wealth.shape[1] == 400  # every survivor was run on all 400 futures
    assert [s.key for s in result.strategies] == sorted((s.key for s in result.strategies), key=[m.key for m in menu()].index)


def test_the_staged_search_finds_the_exhaustive_winner(result, exhaustive):
    assert result.best.strategy == exhaustive.best.strategy
    assert result.best.outcome == exhaustive.best.outcome
    # and every one of the exhaustive top ten made it through the screen
    survivors = {r.strategy for r in result.ranked}
    assert all(r.strategy in survivors for r in exhaustive.ranked[:10])


@pytest.mark.parametrize("seed", [11, 12, 13])
def test_the_staged_search_agrees_with_the_exhaustive_one_on_other_households(seed):
    from export_training_data import sample_household

    household = sample_household(np.random.default_rng(seed))
    inputs = build_inputs(household, n_paths=300, seed=seed)
    staged, full = search(inputs), search(inputs, exhaustive=True)
    assert staged.best.outcome.score == pytest.approx(full.best.outcome.score, rel=1e-9)


def test_search_scores_come_from_the_simulated_futures(result):
    pick = result.ranked[17]
    i = result.index_of(pick.strategy)
    assert pick.outcome.score == pytest.approx(certainty_equivalent(result.batch.wealth[i]))
    assert pick.outcome.median == pytest.approx(np.median(result.batch.wealth[i]))


def test_search_is_deterministic_for_a_seed(household):
    a = search(build_inputs(household, 120, seed=3))
    b = search(build_inputs(household, 120, seed=3))
    assert [r.strategy.key for r in a.ranked] == [r.strategy.key for r in b.ranked]


def test_strategies_with_identical_results_are_marked_tied(exhaustive):
    result = exhaustive
    tied = [r for r in result.ranked if r.tied_with is not None]
    assert tied, "fill-12% every year and low-income-only give identical results for this household"
    for r in tied:
        assert r.tied_with < r.rank
        first = result.ranked[r.tied_with - 1]
        assert first.outcome.score == pytest.approx(r.outcome.score)


def test_rank_strategies_breaks_ties_in_menu_order():
    strategies = menu()[:3]
    wealth = np.tile(np.array([1_000_000.0, 2_000_000.0]), (3, 1))
    ranked = rank_strategies(strategies, wealth)
    assert [r.strategy for r in ranked] == strategies
    assert [r.tied_with for r in ranked] == [None, 1, 1]


def test_full_search_is_fast(futures):
    # The app plans in the equity-first style: its whole menu (1,008 strategies) is searched in under 2 s. The balanced menu
    # (4,032) takes about 3.3 s on four cores since the end valuation, gain harvesting and the reserve spent across accounts (1.9 s before them);
    # the bound for it is 4 s.
    reserve_menu = menu(style="equity_first")
    search(futures, strategies=reserve_menu)  # compiled and warm
    start = time.perf_counter()
    res = search(futures, strategies=reserve_menu)
    assert time.perf_counter() - start < 2.0
    assert res.elapsed_seconds < 2.0 and res.n_considered == 1008
    search(futures)
    start = time.perf_counter()
    res = search(futures)
    assert time.perf_counter() - start < 4.0
    assert res.elapsed_seconds < 4.0 and res.n_considered == 4032


def test_a_strategy_subset_can_be_searched(futures):
    subset = menu()[:6]
    res = search(futures, strategies=subset)
    assert len(res.ranked) == 6 and {r.strategy for r in res.ranked} == set(subset)


def test_best_strategy_beats_the_ria_baseline_for_the_demo_household(futures, result):
    ria = Outcome.of(run_batch(futures, [RIA_BASELINE]).wealth[0])
    assert result.best.outcome.score > ria.score
    assert result.best.outcome.median > ria.median


# --- Where the advantage comes from --------------------------------------------------------


@pytest.mark.parametrize(
    "key",
    [
        "90|fill22_low|10|on|on|pretax|sell",
        "70|none|0|off|off|pretax|sell",
        "100|fill12_every|15|off|on|roth|borrow",
        "60|none|5|on|off|roth_low|borrow",
    ],
)
def test_attribution_steps_sum_to_the_total_advantage(futures, key):
    stock, conv, pc, di, gb, k401, funding = key.split("|")
    strategy = Strategy.from_choices(
        dict(
            stock_share=stock, conversion=conv, private_credit=pc, direct_indexing=di, goal_bonds=gb,
            k401=k401, goal_funding=funding,
        )
    )
    steps = explain.advantage_steps(futures, strategy)
    assert [s.label for s in steps] == [
        "Lower fee",
        "Asset location",
        "Tax-lot selection",
        "Direct indexing",
        "Goal bonds, allocation and private credit",
        "Roth timing and withdrawal order",
    ]
    wealth = run_batch(futures, [RIA_BASELINE, strategy.policy()]).wealth
    total = np.median(wealth[1]) - np.median(wealth[0])
    assert sum(s.delta_median for s in steps) == pytest.approx(total, rel=1e-9)
    assert steps[-1].cumulative_median == pytest.approx(total)
    assert steps[0].active and steps[1].active and steps[2].active  # fee, location and the order lots are sold in always change


def test_attribution_marks_decisions_the_strategy_does_not_use(futures):
    plain = Strategy(0.80, "none", 0.0, False, False)
    steps = {s.label: s for s in explain.advantage_steps(futures, plain)}
    assert not steps["Direct indexing"].active and steps["Direct indexing"].delta_median == 0.0
    # No conversions, but the bracket-first withdrawal order is still a change from pro rata.
    assert steps["Roth timing and withdrawal order"].active
    assert steps["Goal bonds, allocation and private credit"].active  # stock path differs from the glide


def test_the_lower_fee_step_is_a_gain():
    futures = build_inputs(make_demo_household(), 200, seed=1)
    steps = explain.advantage_steps(futures, Strategy(0.9, "none", 0.10, True, True))
    assert steps[0].delta_median > 0 and steps[0].delta_p10 > 0


def test_advantage_policies_end_on_the_chosen_policy():
    s = Strategy(0.80, "fill24_every", 0.10, True, True)
    steps = explain.advantage_policies(s)
    assert steps[0][1] == RIA_BASELINE and steps[-1][1] == s.policy()
    assert len(steps) == 7
    lots = dict(steps)["Tax-lot selection"]
    assert lots.lot_method == "hifo" and RIA_BASELINE.lot_method == "fifo"  # the advisor's oldest-first becomes highest-cost-first


# --- One year of the plan ------------------------------------------------------------------


@pytest.fixture(scope="module")
def det(household):
    return build_inputs(household, deterministic=True)


@pytest.fixture(scope="module")
def conversion_strategy():
    return Strategy(0.90, "fill22_low", 0.10, True, True)


def test_year_detail_reports_decisions_tax_and_values(det, conversion_strategy):
    detail = explain.year_detail(det, conversion_strategy, 25)  # age 63, first years of retirement
    keys = [d.key for d in detail.decisions]
    assert {"conversion", "harvest", "location", "withdraw", "stock_share"} <= set(keys)
    assert detail.age == 63 and detail.year_index == 25
    valued = [d for d in detail.decisions if d.valued]
    assert valued and all(d.value is not None for d in valued)
    stock = next(d for d in detail.decisions if d.key == "stock_share")
    assert not stock.valued and stock.value is None and 0.5 < stock.amount < 0.95
    assert detail.tax_return.agi > 0 and detail.tax_return.roth_conversions > 0
    assert detail.tax_lines[-1].label == "Marginal federal rate"
    log = run_detail(det, conversion_strategy.policy()).log
    assert detail.tax_return.grand_total == pytest.approx(log["total_tax"][25], abs=0.01)
    assert detail.wealth_at_year_end == pytest.approx(log["wealth"][25])


def test_the_value_of_a_decision_is_the_wealth_change_when_it_is_removed(det, conversion_strategy):
    policy = conversion_strategy.policy()
    t = 26
    detail = explain.year_detail(det, conversion_strategy, t)
    full = run_detail(det, policy).wealth[0, 0]
    for decision in detail.decisions:
        if not decision.valued:
            continue
        gates = np.ones((1, det.n_years, sim.NGATE))
        gates[0, t, explain.DECISION_GATES[decision.key]] = 0.0
        without = run_detail(det, policy, gates[0]).wealth[0, 0]
        assert decision.value == pytest.approx(full - without, abs=1e-6), decision.key
    assert next(d for d in detail.decisions if d.key == "conversion").value != 0.0


def test_year_detail_for_a_plain_strategy_has_only_what_it_does(det):
    detail = explain.year_detail(det, Strategy(0.70, "none", 0.0, False, False), 5)
    keys = {d.key for d in detail.decisions}
    # No conversions, no bucket, no withdrawals while working; fund-level harvesting never
    # triggers on the expected-return path. Only the always-on decisions remain.
    assert keys == {"location", "stock_share"}


def test_year_detail_clips_the_year_and_early_years_have_no_withdrawals(det, conversion_strategy):
    assert explain.year_detail(det, conversion_strategy, 999).year_index == det.n_years - 1
    assert explain.year_detail(det, conversion_strategy, -4).year_index == 0
    early = explain.year_detail(det, conversion_strategy, 2)
    assert "withdraw" not in {d.key for d in early.decisions}
    assert early.tax_return.wages > 0


def test_goal_bond_funding_appears_in_the_years_it_happens(det, conversion_strategy):
    detail = explain.year_detail(det, conversion_strategy, 0)
    bucket = next(d for d in detail.decisions if d.key == "bucket")
    assert bucket.amount == pytest.approx(120_000)  # the house is due within four years: fund it now
    assert bucket.description.startswith("Moved $120,000 into the goal bond bucket")
    assert bucket.value is not None
    # Nothing is due within four years of year 4, so there is nothing to fund; college funding starts
    # in year 6 (the first payment is due in year 10).
    assert "bucket" not in {d.key for d in explain.year_detail(det, conversion_strategy, 4).decisions}
    college = next(d for d in explain.year_detail(det, conversion_strategy, 6).decisions if d.key == "bucket")
    assert college.amount == pytest.approx(35_000)


# --- Headline reason -----------------------------------------------------------------------


def test_headline_reason_is_computed_from_the_simulation(det, result):
    plain = Strategy(0.70, "none", 0.10, True, False)
    text = explain.headline_reason(det, result, plain)
    assert "pre-tax balance" in text and "%" in text and "$" in text
    assert "Roth conversions" in text and "lower" in text  # compares with the best plan using them
    with_conv = Strategy(0.90, "fill22_low", 0.10, True, True)
    text2 = explain.headline_reason(det, result, with_conv)
    assert text2.startswith("Without conversions your pre-tax balance reaches")
    assert "22% bracket" in text2
    projection = explain.pretax_projection(det, plain.policy())
    assert projection.balance > 1_000_000 and 0.05 < projection.rate < 0.30
    assert f"{projection.rate * 100:.0f}%" in text


def test_pretax_projection_drops_with_conversions(det):
    none = explain.pretax_projection(det, Strategy(0.9, "none", 0.0, False, False).policy())
    conv = explain.pretax_projection(det, Strategy(0.9, "fill22_low", 0.0, False, False).policy())
    assert conv.balance < none.balance


# --- The two advisors (spec A9) -------------------------------------------------------------


def test_the_typical_advisor_is_defined_as_the_spec_says():
    from app.planner.baseline import BASELINES, GOOD_RIA, TYPICAL, TYPICAL_ADVISOR

    p = TYPICAL_ADVISOR
    assert p.typical_fee_schedule and not p.breakpoint_fees  # the surveyed schedule: 1.15% on the first $500,000, then falling
    assert (p.fund_expense_equity, p.fund_expense_bond, p.cash_share) == (0.0060, 0.0045, 0.03)  # active funds and 3% cash
    assert not p.tax_loss_harvesting  # no tax-loss harvesting
    assert not p.donabach_location  # the same mix in every account
    assert (p.stock_share, p.glide_start_age, p.glide_drop) == (0.80, None, pytest.approx(0.30))  # 80% to 50%
    assert p.conversion_top == 0.0 and not p.bracket_withdrawals  # no conversions, proportional withdrawals
    assert not p.goal_bonds and p.private_credit == 0.0 and p.goal_funding == "sell" and p.k401 == "pretax"
    assert [b.key for b in BASELINES] == ["good_ria", "typical_advisor"] and BASELINES[0] is GOOD_RIA
    for baseline in BASELINES:
        assert baseline.definition.endswith(".") and baseline.label in ("Good RIA", "Typical advisor")
    assert "1.15%" in TYPICAL.definition and "no tax-loss harvesting" in TYPICAL.definition


def test_the_typical_advisor_never_harvests_but_the_good_ria_does_after_a_crash():
    from app.planner.baseline import TYPICAL_ADVISOR
    from app.sim import markets

    household = make_demo_household()
    rets = np.zeros((1, household.horizon_years, 3))
    rets[0, 5, markets.EQUITY] = -0.30  # a bad year: fund-level harvesting needs a fall of more than 10%
    inp = build_inputs(household, deterministic=True)
    inp.rets = np.ascontiguousarray(rets)
    typical = run_detail(inp, TYPICAL_ADVISOR).log
    ria = run_detail(inp, RIA_BASELINE).log
    assert np.all(typical["harvest"] == 0.0)
    assert ria["harvest"][5] > 0  # the good RIA harvests at fund level after a 30% fall


def test_the_typical_advisor_pays_a_flat_one_percent_and_the_good_ria_less():
    from app.planner.baseline import TYPICAL_ADVISOR

    inp = build_inputs(make_demo_household(), deterministic=True)
    # (without its funds' capital-gain distributions: their tax lowers the assets the fee is charged on, which is not what is checked)
    quiet_funds = TYPICAL_ADVISOR.replace(
        fund_distribution=0.0, fund_distribution_short_term=0.0, typical_fee_schedule=False, fund_expense_equity=0.0, fund_expense_bond=0.0, cash_share=0.0
    )  # (and the surveyed schedule, which is the next test: this one is about the flat 1.0% fee the typical advisor used to pay)
    typical = run_detail(inp, quiet_funds).log
    ria = run_detail(inp, RIA_BASELINE).log
    # The fee comes off the assets before the year's contributions go in, so compare it with the
    # balance it was charged on: once retired (no contributions) that is exactly 1.0% every year.
    after = typical["pretax"] + typical["roth"] + typical["brokerage"] + typical["bucket"]
    ratio = typical["fee"] / (after + typical["fee"])
    assert np.all(np.abs(ratio[24:] - 0.010) < 1e-9)
    assert np.all((0.0085 < ratio[:24]) & (ratio[:24] <= 0.010))  # a little under while contributions arrive
    # identical at first (the good RIA also charges 1.0% on the first $1M), then it pulls ahead on the breakpoints
    assert typical["fee"][0] == pytest.approx(ria["fee"][0])
    assert np.all(typical["fee"][8:] > ria["fee"][8:])


def test_the_typical_advisor_does_no_conversions_and_takes_withdrawals_pro_rata():
    from app.planner.baseline import TYPICAL_ADVISOR

    inp = build_inputs(make_demo_household(), deterministic=True)
    log = run_detail(inp, TYPICAL_ADVISOR).log
    assert np.all(log["conv"] == 0.0)
    assert log["equity_share"][0] == pytest.approx(0.80, abs=0.02) and log["stock_target"][32] == pytest.approx(0.50)


def test_the_typical_advisor_does_worse_than_the_good_ria_for_the_demo_household(futures):
    from app.planner.baseline import TYPICAL_ADVISOR

    wealth = run_batch(futures, [RIA_BASELINE, TYPICAL_ADVISOR]).wealth
    assert np.median(wealth[1]) < np.median(wealth[0])  # the same mechanics but a higher fee and no harvesting


# --- Measuring the advantage (spec A7) -------------------------------------------------------


def test_annualized_advantage_is_the_growth_rate_difference():
    from app.study.metrics import annualized

    assert annualized(2_000_000.0, 1_000_000.0, 10) == pytest.approx(2 ** 0.1 - 1)
    assert annualized(1_000_000.0, 1_000_000.0, 42) == 0.0
    assert annualized(1_000_000.0, 2_000_000.0, 10) < 0.0  # behind the baseline
    assert annualized(0.0, 1_000_000.0, 10) == 0.0 and annualized(1.0, 1.0, 0) == 0.0  # degenerate inputs
    # compounding the advantage over the horizon reproduces the ratio
    assert (1 + annualized(3_000_000.0, 2_000_000.0, 42)) ** 42 == pytest.approx(1.5)


def test_both_measures_use_the_right_statistic():
    from app.study.metrics import compare

    plan = np.array([1_000_000.0, 2_000_000.0, 3_000_000.0, 4_000_000.0, 100_000.0])
    base = np.array([900_000.0, 1_500_000.0, 2_000_000.0, 2_500_000.0, 100_000.0])
    adv = compare(plan, base, 20)
    assert adv.plan_median == 2_000_000.0 and adv.baseline_median == 1_500_000.0  # medians
    assert adv.median == pytest.approx((2_000_000 / 1_500_000) ** (1 / 20) - 1)
    assert adv.plan_ce == pytest.approx(certainty_equivalent(plan)) and adv.baseline_ce == pytest.approx(certainty_equivalent(base))
    assert adv.risk_adjusted == pytest.approx((adv.plan_ce / adv.baseline_ce) ** (1 / 20) - 1)
    assert adv.median_dollars == 500_000.0 and adv.risk_adjusted_dollars == pytest.approx(adv.plan_ce - adv.baseline_ce)
    # a riskier plan with the same median and a worse bad case has a smaller risk-adjusted advantage
    riskier = np.array([300_000.0, 2_000_000.0, 3_000_000.0, 4_000_000.0, 100_000.0])
    assert compare(riskier, base, 20).risk_adjusted < adv.risk_adjusted
    assert compare(riskier, base, 20).median == pytest.approx(adv.median)  # same median


def test_the_resampling_range_brackets_the_point_estimate_and_narrows_with_more_futures():
    from app.study.metrics import compare

    rng = np.random.default_rng(5)
    widths = []
    for n in (100, 1_600):
        base = rng.lognormal(14.5, 0.7, n)
        plan = base * np.exp(rng.normal(0.25, 0.15, n))
        adv = compare(plan, base, 30, with_range=True)
        lo, hi = adv.median_range
        assert lo < adv.median < hi and adv.risk_adjusted_range[0] < adv.risk_adjusted < adv.risk_adjusted_range[1]
        widths.append(hi - lo)
    assert widths[1] < widths[0]
    assert compare(plan, base, 30).median_range == (0.0, 0.0)  # off unless asked for


def test_the_risk_adjusted_measure_follows_the_risk_aversion():
    from app.study.metrics import compare

    rng = np.random.default_rng(1)
    base = rng.lognormal(14.5, 0.9, 500)
    safer = np.sort(base)[::-1] * 0 + np.exp(np.mean(np.log(base))) * 0.9  # sure thing below the median
    low, high = compare(safer, base, 30, risk_aversion=1.5), compare(safer, base, 30, risk_aversion=6.0)
    assert high.risk_adjusted > low.risk_adjusted  # the more risk-averse the household, the more the sure thing is worth
    assert high.median == pytest.approx(low.median)  # the median measure ignores risk aversion
