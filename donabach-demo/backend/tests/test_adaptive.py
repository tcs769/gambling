"""The year-by-year adaptive planner (spec part B): correctness rules first, behaviour second."""

from __future__ import annotations

import dataclasses

import numpy as np
import pytest
from tests.conftest import make_demo_household
from tests.test_sim import menu_policy, older_household

from app.planner.baseline import RIA_BASELINE
from app.schemas import Accounts, Goals, Person, SocialSecurity
from app.sim import adaptive as ad
from app.sim import markets
from app.sim import simulate as sim
from app.sim.simulate import build_inputs, run_batch
from app.tax import params_2026 as P

FAST = ad.AdaptiveSettings(k=8)  # a small number of rollouts keeps the tests quick; the rules do not depend on it


def short_household():
    """A household 12 years from the end: quick to plan, with a goal and a retirement inside the horizon."""
    return make_demo_household(
        people=[Person(name="A", age=67, wages=150_000), Person(name="B", age=66, wages=60_000)],
        children_ages=[],
        accounts=Accounts(brokerage_value=300_000, brokerage_basis=200_000, pretax_balance=900_000, roth_balance=50_000, cash=30_000),
        goals=Goals(home_purchase_in_years=2, home_down_payment=100_000, college_starts_in_years=None, retirement_age=69, retirement_spending=90_000),
        social_security=SocialSecurity(annual_benefit=40_000, start_age=68),
        snapshot=None,
    )


def inputs_for(household, paths=6, seed=3):
    return build_inputs(household, n_paths=paths, seed=seed)


# --- Consistency: forcing the continuation action reproduces the fixed strategy exactly --------------


@pytest.mark.parametrize(
    "policy",
    [
        RIA_BASELINE,
        menu_policy("70|fill24_every|10|on|on|pretax|sell"),
        menu_policy("60|fill22_low|15|off|off|roth_low|borrow"),
    ],
)
@pytest.mark.parametrize("household", [short_household(), older_household(), make_demo_household()])
def test_forcing_the_continuation_action_every_year_reproduces_the_fixed_strategy_exactly(policy, household):
    inputs = inputs_for(household)
    forced = ad.run_adaptive(inputs, policy, ad.AdaptiveSettings(k=8, force_continuation=True))
    fixed = run_batch(inputs, [policy], record_paths=True)
    assert np.array_equal(forced.wealth, fixed.wealth[0])
    assert np.array_equal(forced.taxes_paid, fixed.taxes_paid[0])
    assert np.array_equal(forced.pretax_owed, fixed.pretax_owed[0])
    assert np.array_equal(forced.unfunded, fixed.unfunded[0])
    assert np.array_equal(forced.path_wealth, fixed.path_wealth[0])
    assert np.array_equal(forced.chosen, forced.continuation)


def test_a_search_that_demands_overwhelming_evidence_never_leaves_the_fixed_strategy():
    inputs = inputs_for(short_household())
    policy = menu_policy("70|fill24_every|10|on|on")
    never = ad.run_adaptive(inputs, policy, ad.AdaptiveSettings(k=8, z_min=1e9))
    # Every year with a future still to imagine: nothing is convincing enough. (In the last year all the rollouts
    # coincide, so any strictly better action is better for certain and is taken.)
    assert np.array_equal(never.chosen[:, :-1], never.continuation[:, :-1])
    assert never.n_candidates.min() >= 1 and never.n_candidates[:, :-1].min() >= 2  # it did score alternatives
    before_the_end = ad.run_adaptive(inputs, policy, ad.AdaptiveSettings(k=8, z_min=1e9, force_continuation=True))
    assert np.array_equal(before_the_end.wealth, run_batch(inputs, [policy]).wealth[0])


def test_decisions_can_be_limited_to_some_dimensions():
    inputs = inputs_for(short_household())
    policy = menu_policy("70|none|10|off|off")
    only_stock = ad.run_adaptive(inputs, policy, ad.AdaptiveSettings(k=8, dimensions=("stock_share",)))
    for d, name in enumerate(ad.DIM_NAMES):
        if name != "stock_share":
            assert np.array_equal(only_stock.chosen[:, :, d], only_stock.continuation[:, :, d]), name
    with pytest.raises(ValueError):
        _ = ad.AdaptiveSettings(dimensions=("market_timing",)).dimension_mask


# --- No look-ahead -------------------------------------------------------------------------------


def perturbed_after(inputs, year):
    """The same futures up to and including `year`, a completely different world after it."""
    rets = inputs.rets.copy()
    wages = inputs.wages.copy()
    logperm = inputs.logperm.copy()
    rets[:, year + 1 :, :] = np.clip(rets[:, year + 1 :, :][:, ::-1, :] + 0.25, -0.9, 1.0)
    wages[:, year + 1 :] *= 0.4
    logperm[:, year + 1 :, :] += 0.3
    k401 = np.minimum(P.LIMIT_401K_EMPLOYEE * inputs.tv[:, sim.TV_NEARN][None, :], sim.KEEP_401K_SHARE_OF_WAGES * wages)
    wage_tax = np.zeros_like(inputs.wage_tax)
    with sim._KERNEL_LOCK:
        sim._wage_tax_table(np.ascontiguousarray(wages), np.ascontiguousarray(k401), inputs.tv, wage_tax)
    return dataclasses.replace(inputs, rets=rets, wages=wages, k401=k401, wage_tax=wage_tax, logperm=logperm)


@pytest.mark.parametrize("year", [0, 1, 4, 7])
def test_a_decision_never_sees_the_futures_returns_or_income(year):
    """Changing everything after year t changes nothing about the decisions already taken, scores included."""
    inputs = inputs_for(short_household(), paths=6, seed=11)
    policy = menu_policy("60|fill22_every|10|on|on|pretax|borrow")
    a = ad.run_adaptive(inputs, policy, FAST, record_candidates=True)
    b = ad.run_adaptive(perturbed_after(inputs, year), policy, FAST, record_candidates=True)
    upto = slice(0, year + 1)
    assert not np.array_equal(a.wealth, b.wealth)  # the futures really were different
    assert np.array_equal(a.chosen[:, upto], b.chosen[:, upto])
    assert np.array_equal(a.continuation[:, upto], b.continuation[:, upto])
    assert np.array_equal(a.ce_chosen[:, upto], b.ce_chosen[:, upto])
    assert np.array_equal(a.ce_continuation[:, upto], b.ce_continuation[:, upto])
    assert np.array_equal(a.n_candidates[:, upto], b.n_candidates[:, upto])
    assert np.array_equal(a.cand_ce[:, upto], b.cand_ce[:, upto])
    assert np.array_equal(a.path_wealth[:, upto], b.path_wealth[:, upto])  # and the path itself is the same so far


def test_the_decision_in_a_year_does_see_that_years_own_returns():
    """The planner decides after the year's returns are known (the market fell, balances are lower)."""
    inputs = inputs_for(short_household(), paths=4, seed=5)
    policy = menu_policy("60|fill22_every|10|on|on")
    rets = inputs.rets.copy()
    rets[:, 3, markets.EQUITY] = -0.40
    crashed = dataclasses.replace(inputs, rets=rets)
    a = ad.run_adaptive(inputs, policy, FAST)
    b = ad.run_adaptive(crashed, policy, FAST)
    assert np.array_equal(a.chosen[:, :3], b.chosen[:, :3])  # the earlier years knew nothing of it
    assert not np.array_equal(a.ce_chosen[:, 3], b.ce_chosen[:, 3])  # that year's decision did


def test_the_rollout_futures_depend_on_the_state_at_the_decision_not_on_the_path_ahead():
    inputs = inputs_for(short_household(), paths=2, seed=2)
    k = 8
    n_years = inputs.n_years

    def make(inp, year):
        arrays = [np.zeros((k, n_years, 3)), np.zeros((k, n_years)), np.zeros((k, n_years)), np.zeros((k, n_years, 2))]
        means, sds, chol = ad._market_arrays(None)
        stream = np.uint64(ad._decision_stream(ad.rollout_seed(inp.seed), 1, year))
        ad._make_futures(
            stream, year, k, inp.tv, means, sds, chol, inp.inc_base, inp.inc_growth, inp.inc_working, inp.n_earners,
            inp.logperm[1, year], inp.rets[1], inp.wages[1], inp.k401[1], inp.wage_tax[1], *arrays,
        )
        return arrays

    year = 4
    first = make(inputs, year)
    second = make(perturbed_after(inputs, year), year)
    for x, y in zip(first, second, strict=True):
        assert np.array_equal(x, y)  # the imagined futures are the same whatever the real future holds
    assert np.array_equal(first[0][:, year], np.tile(inputs.rets[1, year], (k, 1)))  # year t itself is the real, seen year
    assert np.array_equal(first[1][:, year], np.full(k, inputs.wages[1, year]))
    other = make(inputs, year + 1)
    assert not np.array_equal(first[0][:, year + 2], other[0][:, year + 2])  # a different decision year draws afresh


def test_the_rollout_random_stream_is_disjoint_from_the_evaluation_streams():
    seed = 2026
    rollout = ad.rollout_seed(seed)
    assert rollout != seed and rollout < 2**63
    # distinct streams for every (path, year) decision
    keys = {int(ad._decision_stream(rollout, p, t)) for p in range(200) for t in range(42)}
    assert len(keys) == 200 * 42
    # a different evaluation seed gives a different stream
    assert ad.rollout_seed(seed + 1) != rollout
    # the normals behind rollouts and the evaluation returns neither coincide nor correlate
    evaluation = markets.draw_returns(200, 42, seed)
    eval_z = ((evaluation[:, :, 0] - markets.MEANS[0]) / markets.SDS[0]).ravel()
    stream = np.uint64(ad._decision_stream(rollout, 0, 0))
    uniforms = np.array([ad._uniform(stream, n) for n in range(eval_z.size)])
    assert uniforms.min() > 0.0 and uniforms.max() < 1.0
    assert abs(np.corrcoef(uniforms, eval_z)[0, 1]) < 0.03
    assert not set(np.round(uniforms, 12)) & set(np.round(eval_z, 12))
    # the evaluation futures come from SeedSequence children 0 and 1; the rollouts from child 2
    children = np.random.SeedSequence(seed).spawn(3)
    states = [int(c.generate_state(1, dtype=np.uint64)[0]) for c in children]
    assert len(set(states)) == 3 and (states[2] & 0x7FFF_FFFF_FFFF_FFFF) == rollout


def test_rollout_futures_have_the_right_statistics():
    inputs = inputs_for(short_household(), paths=1, seed=1)
    k = 4_000
    n_years = inputs.n_years
    rets, wages, k401, wt = np.zeros((k, n_years, 3)), np.zeros((k, n_years)), np.zeros((k, n_years)), np.zeros((k, n_years, 2))
    means, sds, chol = ad._market_arrays(None)
    stream = np.uint64(ad._decision_stream(ad.rollout_seed(1), 0, 0))
    ad._make_futures(
        stream, 0, k, inputs.tv, means, sds, chol, inputs.inc_base, inputs.inc_growth, inputs.inc_working, inputs.n_earners,
        inputs.logperm[0, 0], inputs.rets[0], inputs.wages[0], inputs.k401[0], inputs.wage_tax[0], rets, wages, k401, wt,
    )
    later = rets[:, 1:, :]
    flat = later.reshape(-1, 3)
    # antithetic pairs make the average return exactly the expected return (before the -95% floor, which never binds here)
    assert flat.mean(axis=0) == pytest.approx(markets.MEANS, abs=1e-9)
    assert flat.std(axis=0) == pytest.approx(markets.SDS, rel=0.04)
    assert np.corrcoef(flat.T)[0, 1] == pytest.approx(0.1, abs=0.04) and np.corrcoef(flat.T)[0, 2] == pytest.approx(0.5, abs=0.04)
    working = inputs.inc_working[1:] > 0
    assert np.all(wages[:, 1:][:, ~working] == 0.0) and np.all(wages[:, 1:][:, working] > 0.0)
    assert np.all(k401[:, 1:] <= np.minimum(2 * P.LIMIT_401K_EMPLOYEE, 0.2 * wages[:, 1:]) + 1e-9)
    assert np.all(wt[:, 1:, 1] >= wt[:, 1:, 0] - 1e-9)  # a Roth contribution never lowers the tax on wages


# --- Determinism ---------------------------------------------------------------------------------


def test_the_same_inputs_give_identical_results_whatever_the_threads_or_chunking():
    inputs = inputs_for(short_household(), paths=9, seed=4)
    policy = menu_policy("60|fill22_every|10|on|on")
    a = ad.run_adaptive(inputs, policy, FAST, chunk=25)
    b = ad.run_adaptive(inputs, policy, FAST, chunk=25)
    c = ad.run_adaptive(inputs, policy, FAST, chunk=2)
    for other in (b, c):
        assert np.array_equal(a.wealth, other.wealth) and np.array_equal(a.chosen, other.chosen)
        assert np.array_equal(a.ce_chosen, other.ce_chosen) and np.array_equal(a.path_wealth, other.path_wealth)


def test_a_different_evaluation_seed_gives_different_decisions():
    policy = menu_policy("60|fill22_every|10|on|on")
    a = ad.run_adaptive(inputs_for(short_household(), paths=4, seed=1), policy, FAST)
    b = ad.run_adaptive(inputs_for(short_household(), paths=4, seed=2), policy, FAST)
    assert not np.array_equal(a.wealth, b.wealth)


# --- Behaviour -----------------------------------------------------------------------------------


def test_the_planner_converts_in_a_year_with_no_income_and_room_in_the_low_brackets():
    """A retiree with no income, a huge pre-tax balance and cash for the tax: converting now is clearly best."""
    household = make_demo_household(
        people=[Person(name="R", age=60, wages=0)],
        children_ages=[],
        accounts=Accounts(brokerage_value=1_500_000, brokerage_basis=1_500_000, pretax_balance=6_000_000, roth_balance=0, cash=100_000),
        goals=Goals(home_purchase_in_years=None, college_starts_in_years=None, retirement_age=61, retirement_spending=60_000),
        social_security=SocialSecurity(annual_benefit=40_000, start_age=70),
        snapshot=None,
    )
    inputs = build_inputs(household, n_paths=6, seed=1)
    never_convert = menu_policy("60|none|0|off|off")  # the continuation policy would not convert
    result = ad.run_adaptive(inputs, never_convert, ad.AdaptiveSettings(k=16), detail_path=0, record_candidates=True)
    conv = list(ad.DIM_NAMES).index("conversion")
    assert np.all(result.continuation[:, 0, conv] == 0.0)
    assert np.all(result.chosen[:, 0, conv] >= P.TOP_OF_22)  # fills at least the 22% bracket in the first year
    assert result.log["conv"][0] > 150_000
    # the rollouts value it: the chosen action beats the continuation in every path
    assert np.all(result.ce_chosen[:, 0] > 1.002 * result.ce_continuation[:, 0])
    # over the years it keeps converting while room lasts, and it ends well ahead of never converting on the same futures
    assert (result.chosen[:, :10, conv] > 0).sum() >= 12
    fixed = run_batch(inputs, [never_convert]).wealth[0]
    assert np.median(result.wealth) > 1.05 * np.median(fixed)


def test_the_planner_leaves_a_year_alone_when_nothing_beats_the_continuation():
    from app.planner.search import search

    household = short_household()
    best = search(build_inputs(household, n_paths=200, seed=2026)).best.strategy
    inputs = inputs_for(household, paths=5, seed=6)
    result = ad.run_adaptive(inputs, best.policy(), FAST)
    assert np.all(result.ce_chosen >= result.ce_continuation - 1e-6)  # never worse than the continuation in the rollouts
    unchanged = (result.chosen == result.continuation).all(axis=2)
    assert unchanged.mean() > 0.3  # with the best fixed strategy to continue, many years change nothing
    assert (~unchanged).any()  # but not all: judgment over time does sometimes depart


def test_candidate_bookkeeping():
    inputs = inputs_for(short_household(), paths=3, seed=8)
    policy = menu_policy("70|fill24_every|10|on|on")
    result = ad.run_adaptive(inputs, policy, FAST, record_candidates=True)
    assert result.n_candidates.min() >= 1 and result.n_candidates.max() <= ad.MAX_CANDIDATES
    for p in range(3):
        for t in range(inputs.n_years):
            n = result.n_candidates[p, t]
            assert np.array_equal(result.cand_actions[p, t, 0], result.continuation[p, t])  # candidate 0 is the continuation
            assert np.all(np.isfinite(result.cand_ce[p, t, :n])) and np.all(result.cand_ce[p, t, :n] > 0)
            # no duplicate candidates
            assert len({tuple(row) for row in result.cand_actions[p, t, :n]}) == n
            assert result.ce_chosen[p, t] == pytest.approx(result.cand_ce[p, t, :n].max(), rel=1e-12) or result.ce_chosen[p, t] in result.cand_ce[p, t, :n]
    assert result.cand_actions.shape[-1] == ad.ND
    assert result.settings.rollouts == 8 and ad.AdaptiveSettings(k=7).rollouts == 8 and ad.AdaptiveSettings(k=32).rollouts == 32


def test_the_adaptive_plan_respects_the_borrowing_limits_and_never_pays_conversion_tax_from_converted_dollars():
    household = make_demo_household(
        accounts=Accounts(brokerage_value=400_000, brokerage_basis=300_000, pretax_balance=500_000, roth_balance=30_000, cash=10_000)
    )
    rets = np.zeros((1, household.horizon_years, 3))
    rets[0, :, markets.EQUITY] = 0.04
    rets[0, 5, markets.EQUITY] = -0.55
    inputs = dataclasses.replace(build_inputs(household, deterministic=True), rets=np.ascontiguousarray(rets))
    result = ad.run_adaptive(inputs, menu_policy("100|fill24_every|10|on|on|pretax|borrow"), ad.AdaptiveSettings(k=16), detail_path=0)
    log = result.log
    ratio = np.where(log["brokerage"] > 1_000, log["loan"] / np.maximum(log["brokerage"], 1.0), 0.0)
    assert ratio.max() < 0.45  # the 30% / 40% rules keep it near or under 40% (year-end taxes and fees move it a little)
    for t in np.flatnonzero(log["conv"] > 0):
        assert log["roth"][t] >= log["conv"][t] * (1 - 0.0036)  # every converted dollar is still there, less only the fee
    assert np.all(log["unfunded"] == 0) if "unfunded" in log else True


def test_the_adaptive_planner_runs_on_the_demo_household_at_the_spec_defaults():
    household = make_demo_household()
    inputs = build_inputs(household, n_paths=8, seed=2026 + 1_000_003)
    policy = menu_policy("50|fill24_every|15|off|off")
    result = ad.run_adaptive(inputs, policy)  # K = 32
    assert result.settings.k == 32 and result.wealth.shape == (8,) and result.path_wealth.shape == (8, 42)
    assert np.all(np.isfinite(result.wealth)) and result.unfunded.max() == 0.0
    assert np.array_equal(result.path_wealth[:, -1], result.wealth)
    assert result.chosen.shape == (8, 42, ad.ND)
    assert ad.DEFAULT_K == 32 and ad.DEFAULT_PASSES == 2
