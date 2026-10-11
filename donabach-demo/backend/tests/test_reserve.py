"""The spending reserve: the next few years of expenses in bonds and private credit, everything else in stocks.

Mechanics (kernel): bonds and private credit are sold before stocks, the reserve is rebalanced to the next years of
retirement spending net of Social Security, the goals of those years sit in the taxable goal bucket, and after a year
stocks fell nothing is sold to build or refill either. Strategies with no reserve must give exactly the results they gave
before the reserve existed.
"""

from __future__ import annotations

import numpy as np
import pytest
from app.planner.strategies import CHOICE_OPTIONS, CHOICES, RESERVE_YEARS, STYLES, Strategy, menu
from app.schemas import Accounts, Goals, MarketShock, Person, SocialSecurity
from app.sim import simulate as sim
from app.sim.simulate import Policy, build_inputs, run_batch, run_detail

from tests.conftest import make_demo_household
from tests.test_sim import detail, state


def reserve_policy(years=4, pc=0.0, refill=True, **kw) -> Policy:
    return Strategy(1.0, kw.pop("conversion", "none"), pc, False, False, reserve_years=years, **kw).policy().replace(
        reserve_refill_after_gains=refill
    )


# --- Strategies without a reserve are unchanged --------------------------------------------------------


def test_strategies_without_a_reserve_give_exactly_the_results_they_gave_before_the_reserve_existed():
    from app.planner.baseline import RIA_BASELINE, TYPICAL_ADVISOR

    inputs = build_inputs(make_demo_household(), n_paths=150, seed=77)
    # Pinned to the average-cost lot method, which is what every result was computed with before tax lots existed.
    policies = [RIA_BASELINE, TYPICAL_ADVISOR] + [s.policy() for s in menu()[::250][:6]]
    policies = [p.replace(lot_method="average", short_term_ordinary=False) for p in policies]
    batch = run_batch(inputs, policies)
    assert [round(float(np.median(w))) for w in batch.wealth] == [2836952, 2667300, 2799253, 2824798, 2442731, 3307733, 3100390, 2957486]
    assert [round(float(np.median(t))) for t in batch.taxes_paid] == [1504864, 1497800, 1629627, 1648298, 1673934, 1616932, 1843802, 1663421]
    assert float(batch.unfunded.sum()) == 0.0


# --- The sales ---------------------------------------------------------------------------------------


def test_the_reserve_sells_bonds_and_private_credit_before_stocks_in_the_taxable_account():
    st = state(be=100_000, bbasis=60_000, bb=30_000, bp=20_000)
    sold, gain = sim._sell_brokerage(st, 40_000.0, 1.0)  # 40,000 of the 50,000 in bonds and private credit
    assert sold == pytest.approx(40_000) and gain == 0.0
    assert st[sim.S_BE] == pytest.approx(100_000) and st[sim.S_BBASIS] == pytest.approx(60_000)
    assert (st[sim.S_BB], st[sim.S_BP]) == pytest.approx((6_000, 4_000))  # pro rata between the two
    sold, gain = sim._sell_brokerage(st, 20_000.0, 1.0)  # the last 10,000 of safe assets, then 10,000 of stocks
    assert sold == pytest.approx(20_000) and st[sim.S_BB] == st[sim.S_BP] == 0.0
    assert st[sim.S_BE] == pytest.approx(90_000) and gain == pytest.approx(10_000 * 40_000 / 100_000)  # 40% of it was gain
    assert st[sim.S_BBASIS] == pytest.approx(60_000 * 0.9)


def test_the_usual_sale_is_pro_rata_and_the_reserve_changes_nothing_else_about_it():
    pro_rata, reserve = state(be=100_000, bbasis=60_000, bb=30_000, bp=20_000), state(be=100_000, bbasis=60_000, bb=30_000, bp=20_000)
    sim._sell_brokerage(pro_rata, 50_000.0, 0.0)
    assert (pro_rata[sim.S_BE], pro_rata[sim.S_BB], pro_rata[sim.S_BP]) == pytest.approx((100_000 * 2 / 3, 20_000, 20_000 * 2 / 3))  # a third of every class
    sim._sell_brokerage(reserve, 50_000.0, 1.0)  # all the safe assets and nothing else
    assert (reserve[sim.S_BE], reserve[sim.S_BB], reserve[sim.S_BP]) == pytest.approx((100_000, 0, 0))
    # a sale larger than the account takes everything and reports what it took
    assert sim._sell_brokerage(state(be=10.0, bbasis=10.0, bb=5.0), 1_000.0, 1.0)[0] == pytest.approx(15.0)


def test_the_reserve_sells_bonds_and_private_credit_before_stocks_in_the_roth_and_pretax_accounts():
    roth = state(re=100_000, rb=30_000, rp=20_000)
    assert sim._sell_roth(roth, 40_000.0, 1.0) == pytest.approx(40_000)
    assert roth[sim.S_RE] == pytest.approx(100_000) and (roth[sim.S_RB], roth[sim.S_RP]) == pytest.approx((6_000, 4_000))
    assert sim._sell_roth(roth, 30_000.0, 1.0) == pytest.approx(30_000)
    assert roth[sim.S_RB] == roth[sim.S_RP] == 0.0 and roth[sim.S_RE] == pytest.approx(80_000)
    pretax = state(pe=100_000, pb=30_000, pp=20_000)
    assert sim._sell_pretax(pretax, 40_000.0, 1.0) == pytest.approx(40_000) and pretax[sim.S_PE] == pytest.approx(100_000)
    assert sim._sell_pretax(pretax, 30_000.0, 1.0) == pytest.approx(30_000) and pretax[sim.S_PE] == pytest.approx(80_000)
    assert sim._sell_pretax(state(pe=100_000, pb=30_000, pp=20_000), 50_000.0, 0.0) == pytest.approx(50_000)  # pro rata: stocks go too


def test_taxes_are_paid_from_bonds_and_private_credit_first_inside_each_account():
    paid = state(be=100_000, bbasis=100_000, bb=30_000, bp=20_000)
    sim._pay_tax(paid, 25_000.0, 0.0, 1.0)
    assert paid[sim.S_BE] == pytest.approx(100_000) and paid[sim.S_BB] + paid[sim.S_BP] == pytest.approx(25_000)
    usual = state(be=100_000, bbasis=100_000, bb=30_000, bp=20_000)
    sim._pay_tax(usual, 25_000.0, 0.0)
    assert usual[sim.S_BE] < 100_000  # by default every class pays its share


# --- The allocation ------------------------------------------------------------------------------------


def test_stocks_are_everything_the_next_years_of_retirement_spending_leaves():
    inputs = build_inputs(make_demo_household(), deterministic=True)
    log = run_detail(inputs, reserve_policy(4)).log
    for t, years_needed in ((0, 0.0), (20, 110_000.0), (24, 440_000.0), (26, 110_000.0 * 2 + 60_000.0 * 2)):
        total = log["pretax"][t] + log["roth"][t] + log["brokerage"][t]
        needed = sum(inputs.tv[t + j, sim.TV_NEED] for j in range(1, 5) if t + j < inputs.n_years)
        assert needed == pytest.approx(years_needed)
        assert log["stock_target"][t] == pytest.approx(1.0 - needed / total, abs=0.01), t
        assert log["equity_share"][t] == pytest.approx(log["stock_target"][t], abs=0.01), t


def test_a_longer_reserve_holds_fewer_stocks_and_the_private_credit_sleeve_counts_toward_it():
    inputs = build_inputs(make_demo_household(), deterministic=True)
    at_62 = {years: run_detail(inputs, reserve_policy(years)).log["stock_target"][24] for years in (2, 4, 6)}
    assert at_62[2] > at_62[4] > at_62[6]
    sleeve = run_detail(inputs, reserve_policy(4, pc=0.15)).log
    assert sleeve["stock_target"][0] == pytest.approx(0.85) and sleeve["stock_target"][24] == pytest.approx(0.85)  # 15% beats the 9% needed
    assert sleeve["private_credit"][24] / (sleeve["pretax"][24] + sleeve["roth"][24] + sleeve["brokerage"][24]) == pytest.approx(0.15, abs=0.01)


def test_the_goals_of_the_next_years_are_held_in_the_taxable_goal_bucket_and_paid_from_it():
    inputs = build_inputs(make_demo_household(), deterministic=True)
    log = run_detail(inputs, reserve_policy(4)).log
    after_fee = 1.0 - sim.DONABACH_FLAT_FEE  # the log shows the bucket after the year's advisory fee
    assert log["bucket"][0] == pytest.approx(120_000 * after_fee)  # the home purchase is three years away
    assert log["bucket"][3] == 0.0 and log["goal_paid"][3] == 120_000  # paid from it
    assert log["bucket"][6] == pytest.approx(35_000 * after_fee) and log["bucket"][9] == pytest.approx(140_000 * after_fee)  # college
    batch = run_batch(inputs, [reserve_policy(4)])
    assert float(batch.unfunded.sum()) == 0.0
    two = run_detail(inputs, reserve_policy(2)).log
    assert two["bucket"][0] == 0.0 and two["bucket"][1] == pytest.approx(120_000 * after_fee)  # two years ahead, not four


# --- Down years ----------------------------------------------------------------------------------------


def retiree() -> object:
    """Retired from next year, with 600,000 of stocks and 200,000 of cash and bonds, nothing else, spending 100,000 a year."""
    return make_demo_household(
        people=[Person(name="A", age=60, wages=0), Person(name="B", age=60, wages=0)],
        children_ages=[],
        accounts=Accounts(brokerage_value=600_000, brokerage_basis=600_000, pretax_balance=0, roth_balance=0, cash=200_000),
        goals=Goals(home_purchase_in_years=None, college_starts_in_years=None, retirement_age=61, retirement_spending=100_000),
        social_security=SocialSecurity(annual_benefit=0, start_age=70),
        snapshot=None,
    )


def test_after_a_year_stocks_fell_spending_comes_from_bonds_and_nothing_is_sold_to_refill_them():
    crash = build_inputs(retiree(), deterministic=True, shock=MarketShock(year=1, equity_return=-0.30))
    kept = run_detail(crash, reserve_policy(2, refill=True))
    refilled = run_detail(crash, reserve_policy(2, refill=False))
    fixed = run_detail(crash, Policy(stock_share=0.75, glide_start_age=58.0, glide_drop=0.0, conversion_top=0.0))
    assert kept.log["spend_need"][1] == 100_000 and kept.log["wealth"][1] > 400_000  # (it runs out of money years later: 100,000 a year is too much)
    # about 636,000 of stocks fall 30% to about 445,000; the 100,000 comes out of about 200,000 of bonds; no stock is sold
    assert 0.79 < kept.log["equity_share"][1] < 0.84
    # the same strategy that refills every year sells stocks into the fall to rebuild the reserve
    assert refilled.log["equity_share"][1] < kept.log["equity_share"][1] - 0.10
    # a fixed 75% stock share rebalances by selling bonds too, whatever stocks did
    assert fixed.log["equity_share"][1] == pytest.approx(0.75, abs=0.02)


def test_the_reserve_is_rebuilt_in_the_first_year_stocks_do_not_fall():
    crash = build_inputs(retiree(), deterministic=True, shock=MarketShock(year=1, equity_return=-0.30))
    kept = run_detail(crash, reserve_policy(2, refill=True))
    safe = lambda log, t: 1.0 - log["equity_share"][t]  # noqa: E731
    assert safe(kept.log, 1) < 0.22  # not refilled in the fall
    assert safe(kept.log, 2) > 0.35  # refilled once stocks rose (two years of 100,000 out of about 470,000)
    # in a year with no fall the rule changes nothing
    calm = build_inputs(retiree(), deterministic=True)
    on, off = run_detail(calm, reserve_policy(2, refill=True)).log, run_detail(calm, reserve_policy(2, refill=False)).log
    assert np.allclose(on["equity_share"], off["equity_share"]) and np.allclose(on["wealth"], off["wealth"])


# --- The strategy and the menu -------------------------------------------------------------------------


def test_a_strategy_with_a_reserve_has_everything_outside_it_in_stocks_and_no_goal_bonds():
    st = Strategy(1.0, "fill24_every", 0.15, True, False, "pretax", "borrow", reserve_years=4)
    policy = st.policy()
    assert policy.reserve_years == 4 and policy.glide_drop == 0.0 and policy.stock_share == 1.0 and policy.reserve_refill_after_gains
    assert st.choices()["reserve"] == "4" and Strategy.from_choices(st.choices()) == st
    assert Strategy(0.5, "none", 0.0, False, False).choices()["reserve"] == "off"
    with pytest.raises(ValueError):
        Strategy(0.8, "none", 0.0, False, False, reserve_years=4)  # the stock share is not a choice with a reserve
    with pytest.raises(ValueError):
        Strategy(1.0, "none", 0.0, False, True, reserve_years=4)  # the reserve already covers goals
    with pytest.raises(ValueError):
        Strategy(1.0, "none", 0.0, False, False, reserve_years=3)
    assert CHOICES[-1] == "reserve" and CHOICE_OPTIONS["reserve"] == ("off", "2", "4", "6") and RESERVE_YEARS == (0, 2, 4, 6)
    assert "6-year spending reserve, the rest in stocks" in Strategy(1.0, "none", 0.0, False, False, reserve_years=6).short_label()
    text = st.describe()
    assert "next 4 years" in text and "bonds and private credit" in text and "everything else in stocks" in text and "counts toward the reserve" in text


def test_the_two_planning_styles_have_their_own_menus():
    assert STYLES == ("balanced", "equity_first")
    balanced, equity_first = menu(), menu(style="equity_first")
    assert len(balanced) == 4032 and all(s.reserve_years == 0 for s in balanced)  # the original menu, untouched
    assert len(equity_first) == 3 * 7 * 4 * 2 * 3 * 2 and all(s.reserve_years > 0 and s.stock_share == 1.0 and not s.goal_bonds for s in equity_first)
    assert len({s.key for s in equity_first}) == len(equity_first)
    with pytest.raises(ValueError):
        menu(style="aggressive")


# --- The adaptive planner and the explanations ---------------------------------------------------------


def test_the_adaptive_planner_does_not_offer_stock_shares_when_the_reserve_decides_them():
    from app.sim import adaptive as ad

    from tests.test_adaptive import inputs_for, short_household

    inputs = inputs_for(short_household(), paths=4)
    policy = reserve_policy(2, pc=0.10, conversion="fill24_every")
    result = ad.run_adaptive(inputs, policy, ad.AdaptiveSettings(k=8, dimensions=("stock_share",)))
    forced = ad.run_adaptive(inputs, policy, ad.AdaptiveSettings(k=8, force_continuation=True))
    assert np.array_equal(result.wealth, forced.wealth)  # with nothing else to choose, the planner follows the strategy exactly
    assert result.n_candidates.max() == 1 and not result.proposed.any() and not result.kept.any()  # only the continuation was scored: no stock share was tried


def test_the_advantage_steps_end_exactly_on_a_strategy_with_a_reserve():
    from app.planner import explain

    inputs = build_inputs(make_demo_household(), n_paths=40, seed=3)
    st = Strategy(1.0, "fill24_every", 0.10, False, False, reserve_years=4)
    steps = explain.advantage_policies(st)
    assert steps[-1][1] == st.policy() and steps[0][0] == "RIA baseline"
    assert steps[5][1].reserve_years == 4 and steps[4][1].reserve_years == 0  # the allocation step switches it on
    explain.advantage_steps(inputs, st)


def test_the_detailed_log_of_a_reserve_strategy_runs_through_the_year_explanations():
    from app.planner import explain

    inputs = build_inputs(make_demo_household(), deterministic=True)
    st = Strategy(1.0, "fill24_every", 0.10, False, False, reserve_years=4)
    for year in (0, 3, 24):
        detail_ = explain.year_detail(inputs, st, year)
        assert detail_.decisions  # the year's decisions are listed and valued without error
    assert detail(st.policy()).log["wealth"][-1] > 0


# --- The studies take a planning style -----------------------------------------------------------------


def test_the_household_study_can_plan_in_the_equity_first_style():
    import pandas as pd
    from app.study.household_study import household_row, summarize
    from app.study.households import generate

    items = generate(seed=10, per_type=1)
    plain = household_row(items[0], 0, 60, 60, 3.0)
    assert plain["choice_reserve"] == "off"  # the original menu is still the default
    rows = [household_row(item, i, 60, 60, 3.0, skill=True, style="equity_first") for i, item in enumerate(items)]
    frame = pd.DataFrame(rows)
    assert set(frame["choice_reserve"]) <= {"2", "4", "6"} and (frame["choice_stock_share"] == "100").all()
    assert ((frame["plan_equity_today"] > 0.5) & (frame["plan_equity_today"] <= 1.0)).all()
    assert np.isfinite(frame["skill_median_vs_good_ria"]).all() and (frame["adv_median_vs_good_ria"] > frame["skill_median_vs_good_ria"] - 0.01).any()
    text = summarize(frame, 60, 3.0, style="equity_first")
    assert "planning style: equity first" in text and "Spending reserve chosen, by type" in text
    assert "planning style" not in summarize(pd.DataFrame([household_row(item, i, 60, 60, 3.0) for i, item in enumerate(items)]), 60, 3.0)


def test_the_best_fixed_strategy_of_a_study_follows_the_planning_style():
    from app.study.adaptive_evaluation import best_fixed_strategy
    from app.study.measure import sample_household

    household = sample_household()
    assert best_fixed_strategy(household, 2026, style="balanced").reserve_years == 0
    chosen = best_fixed_strategy(household, 2026, style="equity_first")
    assert chosen.reserve_years in (2, 4, 6) and chosen.stock_share == 1.0
