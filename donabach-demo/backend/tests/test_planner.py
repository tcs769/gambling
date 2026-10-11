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
    assert len(strategies) == 6 * 7 * 4 * 2 * 2 * 3 == 2016
    assert len({s.key for s in strategies}) == 2016
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
    assert len(ranked) == 2016 and exhaustive.n_considered == 2016
    scores = [r.outcome.score for r in ranked]
    assert scores == sorted(scores, reverse=True)
    assert [r.rank for r in ranked] == list(range(1, 2017))
    assert exhaustive.best is ranked[0]
    for r in ranked[:5]:
        assert r.outcome.p10 < r.outcome.median < r.outcome.p90


def test_the_staged_search_scores_the_survivors_on_every_future(result):
    assert result.n_considered == 2016 and len(result.ranked) == SCREEN_KEEP
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
    search(futures)  # compiled and warm
    start = time.perf_counter()
    res = search(futures)
    assert time.perf_counter() - start < 2.0
    assert res.elapsed_seconds < 2.0 and res.n_considered == 2016


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
    "key", ["90|fill22_low|10|on|on|pretax", "70|none|0|off|off|pretax", "100|fill12_every|15|off|on|roth", "60|none|5|on|off|roth_low"]
)
def test_attribution_steps_sum_to_the_total_advantage(futures, key):
    stock, conv, pc, di, gb, k401 = key.split("|")
    strategy = Strategy.from_choices(
        dict(stock_share=stock, conversion=conv, private_credit=pc, direct_indexing=di, goal_bonds=gb, k401=k401)
    )
    steps = explain.advantage_steps(futures, strategy)
    assert [s.label for s in steps] == [
        "Lower fee",
        "Asset location",
        "Direct indexing",
        "Goal bonds, allocation and private credit",
        "Roth timing and withdrawal order",
    ]
    wealth = run_batch(futures, [RIA_BASELINE, strategy.policy()]).wealth
    total = np.median(wealth[1]) - np.median(wealth[0])
    assert sum(s.delta_median for s in steps) == pytest.approx(total, rel=1e-9)
    assert steps[-1].cumulative_median == pytest.approx(total)
    assert steps[0].active and steps[1].active  # fee and location always change


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
    assert len(steps) == 6


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
