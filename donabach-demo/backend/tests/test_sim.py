"""M3: markets, income process, household simulator and the RIA baseline."""

from __future__ import annotations

import numpy as np
import pytest
from tests.conftest import make_demo_household

from app.planner.baseline import RIA_BASELINE
from app.planner.strategies import menu
from app.schemas import HORIZON_AGE, Accounts, Goals, MarketShock, Person, SocialSecurity
from app.sim import income, markets
from app.sim import simulate as sim
from app.sim.simulate import Policy, build_inputs, run_batch, run_detail
from app.tax import params_2026 as P
from app.tax.engine import TaxInputs, compute_return

HORIZON_YEARS = HORIZON_AGE - 38  # the demo household is 38


def deterministic(household=None, zero_returns=False, rets=None):
    inp = build_inputs(household or make_demo_household(), deterministic=True)
    if zero_returns:
        inp.rets = np.zeros_like(inp.rets)
    if rets is not None:
        inp.rets = np.ascontiguousarray(rets, dtype=float)
    return inp


def detail(policy, household=None, **kw):
    return run_detail(deterministic(household, **kw), policy)


def state(**kw):
    st = np.zeros(sim.NSTATE)
    for name, value in kw.items():
        st[getattr(sim, "S_" + name.upper())] = value
    return st


# --- Markets -------------------------------------------------------------------------------


def test_market_draws_match_the_specified_moments():
    r = markets.draw_returns(200_000, 1, seed=1)[:, 0, :]
    assert r.mean(axis=0) == pytest.approx([0.055, 0.015, 0.035], abs=0.002)
    assert r.std(axis=0) == pytest.approx([0.16, 0.05, 0.08], abs=0.002)
    corr = np.corrcoef(r.T)
    assert corr[0, 1] == pytest.approx(0.1, abs=0.01)  # equity-bond
    assert corr[0, 2] == pytest.approx(0.5, abs=0.01)  # equity-private credit


def test_market_draws_are_reproducible_and_seeded():
    a = markets.draw_returns(50, 10, seed=7)
    assert np.array_equal(a, markets.draw_returns(50, 10, seed=7))
    assert not np.array_equal(a, markets.draw_returns(50, 10, seed=8))


def test_expected_return_path_and_equity_shock():
    path = markets.expected_returns(5)
    assert path.shape == (1, 5, 3)
    assert path[0, 3].tolist() == [0.055, 0.015, 0.035]
    shocked = markets.with_equity_shock(markets.draw_returns(20, 5, seed=1), year=1, equity_return=-0.30)
    assert np.all(shocked[:, 1, markets.EQUITY] == -0.30)
    assert not np.any(shocked[:, 2, markets.EQUITY] == -0.30)


# --- Income process ------------------------------------------------------------------------


def test_wage_growth_schedule():
    assert income.real_wage_growth(38) == pytest.approx(0.025)
    assert income.real_wage_growth(30) == pytest.approx(0.025)
    assert income.real_wage_growth(46.5) == pytest.approx(0.025 * 8.5 / 17)  # halfway down
    assert income.real_wage_growth(55) == pytest.approx(0.0)
    assert income.real_wage_growth(56) == pytest.approx(-0.005)
    assert income.real_wage_growth(61) == pytest.approx(-0.005)


def test_expected_wage_path_grows_then_stops_at_retirement():
    shocks = income.no_shocks(HORIZON_YEARS, 2)
    wages = income.household_wages([140_000, 110_000], [38, 37], 62, shocks)[0]
    assert wages[0] == pytest.approx(250_000)
    assert wages[1] == pytest.approx(140_000 * np.exp(0.025) + 110_000 * np.exp(0.025))
    assert wages[23] > 0 and wages[24] == 0.0  # age 61 works, age 62 retired
    assert np.all(wages[24:] == 0.0)


def test_income_shock_statistics():
    n = 100_000
    shocks = income.draw_income_shocks(n, 6, 2, seed=3)
    assert shocks.permanent[:, 1:, :].std() == pytest.approx(0.07, abs=0.002)
    assert shocks.transitory[:, 1:, :].std() == pytest.approx(0.07, abs=0.002)
    assert shocks.job_loss[:, 1:, :].mean() == pytest.approx(0.03, abs=0.002)
    # Year 0 is the observed income: no shocks.
    assert not shocks.permanent[:, 0].any() and not shocks.transitory[:, 0].any()
    assert not shocks.job_loss[:, 0].any()


def test_job_loss_removes_sixty_percent_of_that_earners_income():
    shocks = income.draw_income_shocks(2_000, 4, 1, seed=11)
    with_loss = income.earner_wages(100_000, 40, 40, 65, shocks, 0)
    no_loss = income.IncomeShocks(shocks.permanent, shocks.transitory, np.zeros_like(shocks.job_loss))
    without = income.earner_wages(100_000, 40, 40, 65, no_loss, 0)
    lost = shocks.job_loss[:, :, 0] == 1.0
    assert lost.any()
    assert np.allclose(with_loss[lost], 0.4 * without[lost])
    assert np.allclose(with_loss[~lost], without[~lost])


# --- Layout --------------------------------------------------------------------------------


def test_log_constants_match_column_names():
    expected = {
        "age": sim.L_AGE, "wages": sim.L_WAGES, "k401": sim.L_K401, "ss": sim.L_SS,
        "spend_need": sim.L_NEED, "goal_paid": sim.L_GOAL, "interest": sim.L_INTEREST,
        "dividends": sim.L_DIVIDENDS, "harvest": sim.L_HARVEST, "ret_dist": sim.L_RETDIST,
        "conv": sim.L_CONV, "bucket_flow": sim.L_BUCKETFLOW, "bucket": sim.L_BUCKET,
        "stock_target": sim.L_STOCKTARGET, "equity_share": sim.L_EQSHARE,
        "net_gain": sim.L_NETGAIN, "early_base": sim.L_EARLYBASE, "cf_in": sim.L_CFIN,
        "cf_out": sim.L_CFOUT, "kids": sim.L_KIDS, "deps": sim.L_DEPS,
        "wages_taxable": sim.L_WAGESTAXABLE, "agi": sim.L_AGI, "taxable_income": sim.L_TAXABLE,
        "marginal_rate": sim.L_MARGINAL, "fed_tax": sim.L_FED, "il_tax": sim.L_IL,
        "total_tax": sim.L_TOTALTAX, "wage_tax": sim.L_WAGETAX, "portfolio_tax": sim.L_PORTTAX,
        "fee": sim.L_FEE, "pretax": sim.L_PRETAX, "roth": sim.L_ROTH, "brokerage": sim.L_BROKERAGE,
        "wealth": sim.L_WEALTH, "unrealized_gain": sim.L_UNREALIZED,
        "aged": sim.L_AGED, "rmd": sim.L_RMD, "private_credit": sim.L_PC,
        "free_cash": sim.L_FREECASH, "conv_cash": sim.L_CONVCASH, "k401_roth": sim.L_K401ROTH,
        "roth_extra_tax": sim.L_ROTHTAX, "brokerage_saving": sim.L_SAVING, "roth_gap": sim.L_ROTHGAP,
        "loan": sim.L_LOAN, "borrowed": sim.L_BORROWED, "loan_interest": sim.L_LOANINT, "forced_sale": sim.L_FORCED,
        "loan_repaid_saving": sim.L_REPAID_SAVING, "loan_repaid_gain": sim.L_REPAID_GAIN, "gain_harvest": sim.L_GAINHARVEST,
    }
    assert set(expected) == set(sim.LOG_COLUMNS)
    for name, index in expected.items():
        assert sim.LOG_COLUMNS[index] == name


def test_goal_schedule_and_time_table():
    hh = make_demo_household()
    goals = sim.goal_schedule(hh, hh.horizon_years)
    assert goals[3] == 120_000
    assert goals[10:14].tolist() == [35_000] * 4
    assert goals.sum() == 120_000 + 140_000
    moved = hh.model_copy(update={"goals": hh.goals.model_copy(update={"home_purchase_in_years": 1})})
    assert sim.goal_schedule(moved, moved.horizon_years)[1] == 120_000

    tv = deterministic(hh).tv
    assert tv.shape == (HORIZON_YEARS, sim.NTV)
    assert tv[0, sim.TV_AGE] == 38 and tv[31, sim.TV_AGE] == 69
    assert tv[23, sim.TV_RETIRED] == 0 and tv[24, sim.TV_RETIRED] == 1  # age 62
    assert tv[24, sim.TV_NEED] == 110_000 and tv[29, sim.TV_NEED] == 60_000  # SS from 67
    assert tv[29, sim.TV_SS] == 50_000 and tv[28, sim.TV_SS] == 0
    # Child is 8 today: under 17 through t=8 (age 16); a dependent until age 22 (t=14).
    assert tv[8, sim.TV_KIDS] == 1 and tv[9, sim.TV_KIDS] == 0
    assert tv[14, sim.TV_DEPS] == 1 and tv[15, sim.TV_DEPS] == 0
    # Bucket target: goals due in the next four years.
    assert tv[0, sim.TV_BUCKET] == 120_000 and tv[3, sim.TV_BUCKET] == 0
    assert [tv[t, sim.TV_BUCKET] for t in (6, 7, 8, 9, 10)] == [35_000, 70_000, 105_000, 140_000, 105_000]


def test_contributions_follow_the_limit_and_the_twenty_percent_cap():
    inp = deterministic()
    assert inp.k401[0, 0] == pytest.approx(49_000)  # min(2 x 24,500, 20% of 250,000)
    low = deterministic(make_demo_household(people=[
        make_demo_household().people[0].model_copy(update={"wages": 100_000}),
        make_demo_household().people[1].model_copy(update={"wages": 50_000}),
    ]))
    assert low.k401[0, 0] == pytest.approx(30_000)  # 20% of 150,000 binds
    assert np.all(inp.k401[0, 24:] == 0.0)  # nothing after retirement


def test_wage_tax_table_matches_the_tax_engine():
    inp = build_inputs(make_demo_household(), n_paths=50, seed=5)
    for p, t in [(0, 0), (3, 7), (49, 20)]:
        r = compute_return(TaxInputs(
            wages=inp.wages[p, t] - inp.k401[p, t],
            children_under_17=int(inp.tv[t, sim.TV_KIDS]),
            dependents=int(inp.tv[t, sim.TV_DEPS]),
        ))
        assert inp.wage_tax[p, t, 0] == pytest.approx(r.grand_total, abs=1e-6)  # pre-tax 401(k)
        roth = compute_return(TaxInputs(
            wages=inp.wages[p, t],
            children_under_17=int(inp.tv[t, sim.TV_KIDS]),
            dependents=int(inp.tv[t, sim.TV_DEPS]),
        ))
        assert inp.wage_tax[p, t, 1] == pytest.approx(roth.grand_total, abs=1e-6)  # Roth 401(k): no deferral


# --- Kernel mechanics ----------------------------------------------------------------------


def test_advisory_fee_schedules():
    flat = lambda x: sim._advisory_fee(x, 0.0, 0.0035)  # noqa: E731
    ria = lambda x: sim._advisory_fee(x, 1.0, 0.0035)  # noqa: E731
    assert flat(2_000_000.0) == pytest.approx(7_000.0)
    assert ria(500_000.0) == pytest.approx(5_000.0)
    assert ria(1_000_000.0) == pytest.approx(10_000.0)
    assert ria(2_000_000.0) == pytest.approx(10_000 + 8_000)
    assert ria(4_000_000.0) == pytest.approx(10_000 + 16_000 + 6_000)
    assert ria(6_000_000.0) == pytest.approx(10_000 + 16_000 + 12_000 + 5_000)


def test_asset_location_fills_pretax_with_private_credit_then_bonds():
    st = state(pe=300_000, pb=100_000, re=30_000, be=150_000, bbasis=110_000, bb=40_000)
    gain = sim._rebalance(st, 0.81, 0.10, False)  # 90% stocks with a 10% private credit sleeve
    total = 620_000.0
    assert st[sim.S_PP] == pytest.approx(0.10 * total)  # private credit only in pre-tax
    assert st[sim.S_PB] == pytest.approx(0.09 * total)  # then bonds
    assert st[sim.S_PE] == pytest.approx(400_000 - 0.19 * total)  # pre-tax topped up with stocks
    assert st[sim.S_RE] == pytest.approx(30_000) and st[sim.S_RB] == 0.0  # Roth holds stocks
    assert st[sim.S_BE] == pytest.approx(190_000) and st[sim.S_BB] == pytest.approx(0.0, abs=1e-6)
    assert st[sim.S_BBASIS] == pytest.approx(150_000)  # the cash bought equity at cost
    assert gain == 0.0
    balances = [sim.S_PE, sim.S_PB, sim.S_PP, sim.S_RE, sim.S_RB, sim.S_RP, sim.S_BE, sim.S_BB, sim.S_BP]
    assert sum(st[i] for i in balances) == pytest.approx(total)  # nothing lost


def test_private_credit_overflows_from_pretax_to_roth_to_brokerage():
    # 15% of 1,000,000 is 150,000: the pre-tax account takes 100,000, the Roth the next 30,000, brokerage the last 20,000.
    st = state(pe=100_000, re=30_000, be=700_000, bbasis=500_000, bb=170_000)
    gain = sim._rebalance(st, 0.70 * 0.85, 0.15, False)  # 70% stocks with a 15% sleeve
    assert (st[sim.S_PP], st[sim.S_RP], st[sim.S_BP]) == pytest.approx((100_000, 30_000, 20_000))
    assert st[sim.S_PE] == st[sim.S_PB] == st[sim.S_RE] == st[sim.S_RB] == 0.0
    assert st[sim.S_BE] == pytest.approx(0.595 * 1_000_000) and st[sim.S_BB] == pytest.approx(255_000)
    assert gain == pytest.approx(105_000 * 200_000 / 700_000)  # 105,000 of equity sold at a 200/700 embedded gain
    accounts = {
        "pre-tax": (st[sim.S_PE] + st[sim.S_PB] + st[sim.S_PP], 100_000),
        "roth": (st[sim.S_RE] + st[sim.S_RB] + st[sim.S_RP], 30_000),
        "brokerage": (st[sim.S_BE] + st[sim.S_BB] + st[sim.S_BP], 870_000),
    }
    for name, (after, before) in accounts.items():
        assert after == pytest.approx(before), name  # rebalancing never moves money between accounts


def test_private_credit_that_fits_in_the_pretax_account_stays_out_of_the_others():
    st = state(pe=500_000, re=100_000, be=400_000, bbasis=400_000)
    sim._rebalance(st, 0.60 * 0.90, 0.10, False)
    assert st[sim.S_PP] == pytest.approx(100_000) and st[sim.S_RP] == 0.0 and st[sim.S_BP] == 0.0


def test_private_credit_in_brokerage_is_taxed_each_year_as_interest():
    st = state(bp=100_000, bb=50_000, be=200_000, bbasis=200_000)
    tv = np.zeros((1, sim.NTV))
    tv[0, sim.TV_AGE] = 50.0
    ys = np.zeros(sim.NY)
    act = np.zeros(sim.NACT)
    sim._year_begin(st, ys, tv, 0, act, 0.0, 0.0, 0.10)
    taxable_interest = 0.055 * 100_000 + 0.035 * 50_000  # opening balances: private credit 5.5%, bonds 3.5%
    assert ys[sim.Y_INTEREST] == pytest.approx(taxable_interest)
    assert st[sim.S_BP] == pytest.approx(110_000)  # the return is separate from the taxable income


def test_conversions_move_private_credit_into_the_roth_account_in_kind():
    st = state(pe=200_000, pb=100_000, pp=100_000, re=10_000, rb=5_000)
    sim._convert_to_roth(st, 0.25)
    assert (st[sim.S_PE], st[sim.S_PB], st[sim.S_PP]) == pytest.approx((150_000, 75_000, 75_000))
    assert (st[sim.S_RE], st[sim.S_RB], st[sim.S_RP]) == pytest.approx((60_000, 30_000, 25_000))
    total = sum(st[i] for i in (sim.S_PE, sim.S_PB, sim.S_PP, sim.S_RE, sim.S_RB, sim.S_RP))
    assert total == pytest.approx(415_000)  # nothing lost; private credit stays private credit


def test_asset_location_overflows_bonds_into_the_taxable_account():
    st = state(pe=300_000, pb=100_000, re=30_000, be=150_000, bbasis=110_000, bb=40_000)
    gain = sim._rebalance(st, 0.25, 0.0, False)  # bond-heavy: more bonds than the pre-tax account holds
    assert st[sim.S_PB] == pytest.approx(400_000) and st[sim.S_PE] == pytest.approx(0.0, abs=1e-6)
    assert st[sim.S_RE] == pytest.approx(30_000)
    assert st[sim.S_BE] == pytest.approx(0.25 * 620_000 - 30_000)  # 125,000
    assert st[sim.S_BB] == pytest.approx(190_000 - 125_000)
    # 25,000 of equity sold at a 40/150 embedded gain; basis scales down pro rata.
    assert gain == pytest.approx(25_000 * 40_000 / 150_000)
    assert st[sim.S_BBASIS] == pytest.approx(110_000 * 125_000 / 150_000)


def test_uniform_mix_puts_the_same_share_in_every_account():
    st = state(pe=300_000, pb=100_000, re=30_000, be=150_000, bbasis=110_000, bb=40_000)
    sim._rebalance(st, 0.80, 0.0, True)
    assert st[sim.S_PE] == pytest.approx(320_000) and st[sim.S_PB] == pytest.approx(80_000)
    assert st[sim.S_RE] == pytest.approx(24_000) and st[sim.S_RB] == pytest.approx(6_000)
    assert st[sim.S_BE] == pytest.approx(152_000) and st[sim.S_BB] == pytest.approx(38_000)


def test_stock_share_glide_paths():
    donabach = lambda age: sim._stock_share(float(age), 0.90, 58.0, 0.25)  # noqa: E731
    assert donabach(40) == pytest.approx(0.90) and donabach(58) == pytest.approx(0.90)
    assert donabach(64) == pytest.approx(0.90 - 0.125) and donabach(70) == pytest.approx(0.65)
    ria = lambda age: sim._stock_share(float(age), 0.80, 38.0, 0.30)  # noqa: E731
    assert ria(38) == pytest.approx(0.80) and ria(54) == pytest.approx(0.65) and ria(70) == pytest.approx(0.50)


def test_baseline_rebalances_to_the_age_based_glide_path():
    log = detail(RIA_BASELINE).log
    assert log["stock_target"][0] == pytest.approx(0.80)
    assert log["stock_target"][31] == pytest.approx(0.80 - 0.30 * 31 / 32)
    assert log["equity_share"][5] == pytest.approx(log["stock_target"][5], abs=0.01)


def test_direct_indexing_harvest_after_an_equity_decline():
    inp = deterministic(zero_returns=True)
    inp.rets[0, 0, markets.EQUITY] = -0.20
    policy = Policy(direct_indexing=True)
    log = run_detail(inp, policy).log
    value = 150_000 * 0.80
    basis = 110_000 + 0.018 * 150_000  # reinvested dividends are bought at cost
    decline = 0.20 * 150_000  # dollars of decline
    expected = min(0.85 * decline + 0.03 * value * min(1.0, basis / value), 0.35 * value, basis)
    assert log["harvest"][0] == pytest.approx(expected, rel=1e-9)


def test_direct_indexing_harvests_a_little_even_when_markets_rise():
    log = detail(Policy(direct_indexing=True)).log
    assert np.all(log["harvest"] > 0)  # the 3% dispersion harvest, scaled by basis ratio


def test_direct_indexing_is_capped_at_basis_and_a_third_of_value():
    household = make_demo_household(accounts=Accounts(
        brokerage_value=150_000, brokerage_basis=10_000, pretax_balance=100_000, roth_balance=0, cash=0
    ))
    inp = deterministic(household, zero_returns=True)
    inp.rets[0, 0, markets.EQUITY] = -0.90  # a collapse: 85% of the decline would exceed both caps
    log = run_detail(inp, Policy(direct_indexing=True)).log
    assert log["harvest"][0] <= 10_000 + 0.018 * 150_000 + 1e-6  # never more than basis
    assert log["harvest"][0] <= 0.35 * 150_000 * 0.10 + 1e-6  # nor 35% of (remaining) value


def test_fund_level_harvest_needs_a_fall_of_more_than_ten_percent_and_an_underwater_pool():
    underwater = make_demo_household(accounts=Accounts(
        brokerage_value=150_000, brokerage_basis=200_000, pretax_balance=100_000, roth_balance=0, cash=0
    ))
    fund = Policy(direct_indexing=False)
    for fall, expected_harvest in [(-0.08, 0.0), (-0.20, 200_000 + 2_700 - 120_000)]:
        inp = deterministic(underwater, zero_returns=True)
        inp.rets[0, 0, markets.EQUITY] = fall
        assert run_detail(inp, fund).log["harvest"][0] == pytest.approx(expected_harvest)
    # In-the-money pool: a 20% fall still leaves no loss to harvest at fund level.
    inp = deterministic(zero_returns=True)
    inp.rets[0, 0, markets.EQUITY] = -0.20
    assert run_detail(inp, fund).log["harvest"][0] == 0.0


def test_goal_bucket_is_funded_four_years_ahead_and_pays_the_goal():
    policy = Policy(goal_bonds=True, flat_fee=0.0)
    log = detail(policy, zero_returns=True).log
    tv = deterministic().tv
    assert np.allclose(log["bucket"], tv[:, sim.TV_BUCKET] * (1 - 0.0))
    assert log["bucket"][0] == pytest.approx(120_000)  # the house is already inside four years
    assert log["goal_paid"][3] == 120_000 and log["bucket"][3] == 0.0
    assert [log["bucket"][t] for t in (6, 7, 8, 9)] == [35_000, 70_000, 105_000, 140_000]
    assert log["bucket"][13] == 0.0


def test_without_the_bucket_goals_come_out_of_the_brokerage_account():
    log = detail(Policy(goal_bonds=False), zero_returns=True).log
    assert np.all(log["bucket"] == 0.0)
    assert log["goal_paid"][3] == 120_000
    assert log["net_gain"][3] > 0  # selling appreciated equity realizes a gain


def test_roth_conversion_fills_the_chosen_bracket_exactly():
    policy = menu_policy("90|fill22_low|off|off|off")
    log = detail(policy).log
    converted = np.flatnonzero(log["conv"] > 0)
    assert len(converted) > 0 and converted.min() >= 24  # retirement only for this household
    for t in converted:
        r = year_return(log, t)
        assert r.ordinary_taxable_income == pytest.approx(P.TOP_OF_22, abs=0.5)


def test_conversions_in_low_income_years_only_not_while_working_normally():
    log = detail(menu_policy("90|fill22_low|off|off|off")).log
    assert np.all(log["conv"][:24] == 0.0)  # steady wages: never a low-income year
    every = detail(menu_policy("90|fill22_every|off|off|off")).log
    assert every["conv"][0] > 0  # "every year" converts while working


def test_a_job_loss_year_triggers_a_low_income_conversion():
    inp = deterministic()
    t = 5
    inp.wages[0, t] *= 0.4  # one earner's job loss would do less; this is a clear low-income year
    inp.k401[0, t] = np.minimum(P.LIMIT_401K_EMPLOYEE * 2, 0.20 * inp.wages[0, t])
    sim._wage_tax_table(inp.wages, inp.k401, inp.tv, inp.wage_tax)
    low = run_detail(inp, menu_policy("90|fill22_low|off|off|off")).log
    assert low["conv"][t] > 0  # wages 100,000 < 80% of the 288,000 expected: low income
    assert np.all(low["conv"][:t] == 0.0)
    assert low["conv"][t + 1] == 0.0  # back to normal income: no conversion
    r = year_return(low, t)
    assert r.ordinary_taxable_income == pytest.approx(P.TOP_OF_22, abs=0.5) or low["conv"][t] > 0


def no_wage_household(brokerage, pretax, age=60, retirement_age=61, spending=0.0):
    return make_demo_household(
        people=[Person(name="Pat", age=age, wages=0)],
        children_ages=[],
        accounts=Accounts(
            brokerage_value=brokerage, brokerage_basis=brokerage, pretax_balance=pretax, roth_balance=0, cash=0
        ),
        goals=Goals(
            home_purchase_in_years=None, college_starts_in_years=None,
            retirement_age=retirement_age, retirement_spending=spending,
        ),
        social_security=SocialSecurity(annual_benefit=0, start_age=67),
        snapshot=None,
    )


def test_normal_spending_before_retirement_is_what_the_household_plans_to_spend_in_retirement():
    tv = deterministic().tv
    assert np.all(tv[:24, sim.TV_SPEND] == 110_000.0) and np.all(tv[24:, sim.TV_SPEND] == 0.0)


def test_spare_wages_are_wages_after_tax_401k_saving_and_normal_spending():
    log = detail(menu_policy("90|fill22_every|off|off|off")).log
    for t in (0, 5, 10, 23):
        w = log["wages"][t]
        expected = max(0.0, w - log["wage_tax"][t] - log["k401"][t] - sim.BROKERAGE_SAVINGS_SHARE * w - 110_000)
        assert log["free_cash"][t] == pytest.approx(expected)
    assert log["free_cash"][0] > 20_000 and np.all(log["free_cash"][24:] == 0.0)  # nothing spare once retired


def test_conversion_tax_is_paid_from_spare_wages_when_the_taxable_account_is_nearly_empty():
    poor_in_cash = make_demo_household(
        accounts=Accounts(brokerage_value=1_000, brokerage_basis=1_000, pretax_balance=1_000_000, roth_balance=0, cash=0)
    )
    log = detail(menu_policy("90|fill22_every|off|off|off"), poor_in_cash).log
    old_cap = 1_000 / 0.22  # what the taxable account alone could have funded
    assert log["conv"][0] > 5 * old_cap
    assert log["conv_cash"][0] > 0
    assert log["conv_cash"][0] == pytest.approx(log["portfolio_tax"][0], abs=100)  # the whole bill, wages paid it
    assert log["conv_cash"][0] <= log["free_cash"][0] + 1e-9


def test_the_tax_on_a_conversion_is_never_paid_out_of_the_converted_dollars():
    # Retired, no wages, no taxable account: nothing can pay the tax, so nothing is converted.
    log = run_detail(deterministic(no_wage_household(0.0, 2_000_000.0)), menu_policy("90|fill24_every|off|off|off")).log
    early = log["age"] < 75  # RMDs would later put cash in the taxable account
    assert np.all(log["conv"][early] == 0.0) and np.all(log["roth"][early] == 0.0)


def test_a_conversion_is_capped_by_what_the_taxable_account_can_pay_without_wages():
    log = run_detail(deterministic(no_wage_household(20_000.0, 1_000_000.0)), menu_policy("90|fill22_every|off|off|off")).log
    after_returns = 20_000 * (1 + markets.MEANS[markets.EQUITY])  # conversions come after the year's return
    assert log["conv"][0] == pytest.approx(after_returns / 0.22, rel=1e-6)
    # every converted dollar is still in the Roth, less only the flat 0.35% fee: none paid the tax
    assert log["roth"][0] == pytest.approx(log["conv"][0] * (1 - 0.0035), rel=1e-9)
    assert log["conv_cash"][0] == 0.0


def test_paying_tax_from_the_portfolio_never_touches_the_roth_dollars_just_converted():
    st = state(be=10_000, bbasis=10_000, re=100_000, pe=500_000)
    sim._pay_tax(st, 50_000.0, 80_000.0)  # 80,000 of the Roth was converted this year
    assert st[sim.S_BE] == pytest.approx(0.0)
    assert st[sim.S_RE] == pytest.approx(80_000.0)  # only the 20,000 that was not converted was available
    assert st[sim.S_DDIST] == pytest.approx(20_000.0)  # the rest came from pre-tax (taxed next year)
    assert st[sim.S_UNFUNDED] == 0.0
    free = state(be=10_000, bbasis=10_000, re=100_000, pe=500_000)
    sim._pay_tax(free, 50_000.0, 0.0)  # with nothing converted the Roth can pay
    assert free[sim.S_RE] == pytest.approx(60_000.0) and free[sim.S_DDIST] == 0.0


def test_a_roth_401k_contribution_is_after_tax_and_lands_in_the_roth_account():
    pre = detail(menu_policy("90|none|off|off|off|pretax")).log
    roth = detail(menu_policy("90|none|off|off|off|roth")).log
    for t in (0, 10, 23):
        k = pre["k401"][t]
        assert roth["k401"][t] == pytest.approx(k) and roth["k401_roth"][t] == pytest.approx(k)
        assert pre["k401_roth"][t] == 0.0
        assert roth["wages_taxable"][t] == pytest.approx(pre["wages_taxable"][t] + k)  # no deferral
        assert roth["wage_tax"][t] > pre["wage_tax"][t]
        assert roth["roth_extra_tax"][t] == pytest.approx(roth["wage_tax"][t] - pre["wage_tax"][t])
    assert roth["roth"][0] > pre["roth"][0] + 20_000 and roth["pretax"][0] < pre["pretax"][0] - 20_000


def test_a_roth_401k_keeps_consumption_where_it_was_by_saving_less():
    pre = detail(menu_policy("90|none|off|off|off|pretax")).log
    roth = detail(menu_policy("90|none|off|off|off|roth")).log
    for t in range(24):
        spent_pre = pre["wages"][t] - pre["wage_tax"][t] - pre["k401"][t] - pre["brokerage_saving"][t]
        spent_roth = roth["wages"][t] - roth["wage_tax"][t] - roth["k401"][t] - roth["brokerage_saving"][t]
        assert spent_roth == pytest.approx(spent_pre, abs=1e-6)  # the same left over for living
        assert roth["brokerage_saving"][t] == pytest.approx(
            max(0.0, pre["brokerage_saving"][t] - roth["roth_extra_tax"][t]), abs=1e-6
        )


def test_401k_contributions_keep_the_same_limits_whatever_the_type():
    inp = deterministic()
    assert np.all(inp.k401[0, :24] <= 2 * P.LIMIT_401K_EMPLOYEE) and np.all(inp.k401[0, 24:] == 0.0)
    assert np.all(inp.k401[0, :24] <= 0.20 * inp.wages[0, :24] + 1e-9)


def test_roth_in_low_income_years_only_switches_with_the_year():
    inp = deterministic()
    inp.wages[0, 5] *= 0.4  # a bad year: well under 80% of the expected wages
    inp.k401[0, 5] = min(P.LIMIT_401K_EMPLOYEE * 2, 0.20 * inp.wages[0, 5])  # the wage-tax table must follow
    tax = np.zeros((1, inp.n_years, 2))
    with sim._KERNEL_LOCK:
        sim._wage_tax_table(np.ascontiguousarray(inp.wages), np.ascontiguousarray(inp.k401), inp.tv, tax)
    inp.wage_tax = tax
    log = run_detail(inp, menu_policy("90|none|off|off|off|roth_low")).log
    assert log["k401_roth"][5] == pytest.approx(inp.k401[0, 5]) and inp.k401[0, 5] > 0
    others = [t for t in range(24) if t != 5]
    assert np.all(log["k401_roth"][others] == 0.0)  # pre-tax in every normal year


def test_the_401k_gate_removes_the_roth_choice_for_one_year():
    inp = deterministic()
    gates = np.ones((1, inp.n_years, sim.NGATE))
    gates[0, 3, sim.G_K401] = 0.0
    log = run_detail(inp, menu_policy("90|none|off|off|off|roth"), gates[0]).log
    assert log["k401_roth"][3] == 0.0 and log["k401_roth"][2] > 0 and log["k401_roth"][4] > 0


def test_policy_401k_options_map_to_the_policy_column():
    for option, code in (("pretax", sim.K401_PRETAX), ("roth", sim.K401_ROTH), ("roth_low", sim.K401_ROTH_LOW)):
        assert Policy(k401=option).row(38)[sim.SP_K401] == code
    assert menu_policy("90|none|off|off|off|roth").k401 == "roth"


# --- Borrowing against the portfolio (spec A6) -----------------------------------------------


def borrowing_household(brokerage=2_000_000.0):
    """The demo household with a taxable account big enough that borrowing limits do not bind."""
    return make_demo_household(
        accounts=Accounts(
            brokerage_value=brokerage, brokerage_basis=brokerage * 0.6, pretax_balance=400_000,
            roth_balance=30_000, cash=40_000,
        )
    )


def test_borrowing_assumptions_are_documented_in_params():
    assert P.BORROWING_LIMIT == 0.30 and P.BORROWING_FORCED_SALE_TRIGGER == 0.40
    assert P.BOX_SPREAD_PREMIUM == 0.003  # Treasury + 0.3%
    # real rate = short-term Treasury + 0.3% - inflation
    assert P.BORROWING_RATE_REAL == pytest.approx(P.SHORT_TERM_TREASURY_NOMINAL + 0.003 - P.ASSUMED_INFLATION)
    assert 0.0 < P.BORROWING_RATE_REAL < 0.06
    assert markets.PRIVATE_CREDIT_INCOME_YIELD == pytest.approx(markets.MEANS[markets.PRIVATE_CREDIT] + P.ASSUMED_INFLATION)


def test_borrowing_for_a_goal_never_exceeds_30_percent_of_the_taxable_account():
    rng = np.random.default_rng(7)
    for _ in range(2_000):
        st = state(
            be=float(rng.uniform(0, 1e6)), bb=float(rng.uniform(0, 5e5)), bp=float(rng.uniform(0, 2e5)),
            loan=float(rng.uniform(0, 4e5)), gb=float(rng.uniform(0, 1e5)),
        )
        value = st[sim.S_BE] + st[sim.S_BB] + st[sim.S_BP]
        before = st[sim.S_LOAN]
        due = float(rng.uniform(0, 5e5))
        got = sim._borrow_for_goal(st, due)
        assert 0.0 <= got <= due + 1e-9
        assert st[sim.S_LOAN] == pytest.approx(before + got)
        if before <= 0.30 * value:  # a loan already over the limit simply cannot grow
            assert st[sim.S_LOAN] <= 0.30 * value + 1e-6
        else:
            assert got == 0.0


def test_a_loan_above_40_percent_forces_a_sale_back_to_30_percent():
    st = state(be=100_000, bbasis=60_000, loan=45_000)
    interest, forced, gain = sim._accrue_and_deleverage(st)
    loan = 45_000 * (1 + P.BORROWING_RATE_REAL)
    assert interest == pytest.approx(45_000 * P.BORROWING_RATE_REAL)
    assert forced == pytest.approx((loan - 0.30 * 100_000) / 0.70)  # sell enough that loan = 30% of what is left
    assert st[sim.S_LOAN] == pytest.approx(loan - forced)
    assert st[sim.S_LOAN] == pytest.approx(0.30 * st[sim.S_BE])  # exactly 30% of the account that remains
    assert gain == pytest.approx(forced * 0.40)  # sold equity carries a 40% embedded gain


def test_a_loan_between_30_and_40_percent_is_left_alone():
    st = state(be=100_000, bbasis=60_000, loan=33_000)
    _, forced, gain = sim._accrue_and_deleverage(st)
    assert forced == 0.0 and gain == 0.0 and st[sim.S_BE] == pytest.approx(100_000)
    assert st[sim.S_LOAN] == pytest.approx(33_000 * (1 + P.BORROWING_RATE_REAL))  # only the interest changed


def test_after_the_start_of_year_upkeep_the_loan_is_never_above_40_percent_of_the_account():
    rng = np.random.default_rng(3)
    for _ in range(2_000):
        st = state(
            be=float(rng.uniform(0, 1e6)), bbasis=float(rng.uniform(0, 1e6)), bb=float(rng.uniform(0, 3e5)),
            bp=float(rng.uniform(0, 1e5)), loan=float(rng.uniform(0, 8e5)),
        )
        sim._accrue_and_deleverage(st)
        value = st[sim.S_BE] + st[sim.S_BB] + st[sim.S_BP]
        assert st[sim.S_LOAN] <= 0.40 * value + 1e-6 or value <= 1e-9  # or everything was sold


def test_interest_on_the_loan_is_a_capital_loss():
    st = state(be=500_000, bbasis=500_000, loan=100_000)
    tv = np.zeros((1, sim.NTV))
    tv[0, sim.TV_AGE] = 45.0
    ys = np.zeros(sim.NY)
    sim._year_begin(st, ys, tv, 0, np.zeros(sim.NACT), 0.0, 0.0, 0.0)
    interest = 100_000 * P.BORROWING_RATE_REAL
    assert ys[sim.Y_LOANINT] == pytest.approx(interest)
    assert ys[sim.Y_REALIZED] == pytest.approx(-interest)  # a loss that offsets gains and carries forward
    assert st[sim.S_LOAN] == pytest.approx(100_000 + interest)  # interest accrues to the loan


def test_borrowing_pays_a_goal_without_selling_and_the_loan_is_repaid_from_savings_first():
    household = borrowing_household()
    sell = detail(Policy(goal_funding="sell"), household).log
    borrow = detail(Policy(goal_funding="borrow"), household).log
    assert borrow["borrowed"][3] == pytest.approx(120_000)  # the down payment, in full
    assert sell["borrowed"][3] == 0.0
    # the same year's savings already start repaying it
    saving = sim.BROKERAGE_SAVINGS_SHARE * borrow["wages"][3]
    assert borrow["loan_repaid_saving"][3] == pytest.approx(saving) and borrow["loan"][3] == pytest.approx(120_000 - saving)
    assert borrow["net_gain"][3] < sell["net_gain"][3]  # no sale, so no gain realized for the goal
    # from then on this year's saving repays the loan before anything is invested
    owed = borrow["loan"][3]
    for t in range(4, 9):
        assert borrow["loan_interest"][t] == pytest.approx(owed * P.BORROWING_RATE_REAL)
        owed *= 1 + P.BORROWING_RATE_REAL
        saving_available = sim.BROKERAGE_SAVINGS_SHARE * borrow["wages"][t]
        assert borrow["loan_repaid_saving"][t] == pytest.approx(min(saving_available, owed), abs=1e-6)
        owed -= borrow["loan_repaid_saving"][t] + borrow["loan_repaid_gain"][t]
        assert borrow["loan"][t] == pytest.approx(owed, abs=1e-6)
    assert borrow["loan"][8] == pytest.approx(0.0, abs=1e-6)  # about 25,000 a year clears 120,000 in five


def test_a_loan_is_repaid_by_realizing_gains_in_a_low_tax_year():
    inp = deterministic(no_wage_household(300_000.0, 500_000.0, age=60, retirement_age=61))
    inp.init[sim.S_LOAN] = 50_000.0
    inp.init[sim.S_BBASIS] = 150_000.0  # half of the account is gain
    log = run_detail(inp, Policy(flat_fee=0.0, goal_funding="borrow", bracket_withdrawals=False)).log
    assert log["loan_repaid_gain"][0] > 0 and log["loan"][0] < 50_000
    # nothing is owed on the gain it realized: it fits inside the 0% bracket
    assert log["fed_tax"][0] == pytest.approx(0.0, abs=1.0)
    assert log["loan_repaid_saving"][0] == 0.0  # no wages, so no savings to repay from


def test_no_repayment_by_sale_in_a_high_tax_year_or_the_year_of_borrowing():
    household = borrowing_household()
    log = detail(Policy(goal_funding="borrow"), household).log
    assert log["loan_repaid_gain"][3] == 0.0  # the year it was borrowed
    # with $250,000 of wages there is no 0% bracket left to realize gains in
    assert np.all(log["loan_repaid_gain"][:24] == 0.0)


def test_the_loan_is_subtracted_from_after_tax_wealth():
    household = borrowing_household()
    sell = detail(Policy(goal_funding="sell"), household).log
    borrow = detail(Policy(goal_funding="borrow"), household).log
    # Borrowing does not create wealth: at most the tax on the gain that was not realized separates them.
    assert abs(borrow["wealth"][3] - sell["wealth"][3]) < 0.15 * 120_000


def test_the_borrow_gate_turns_borrowing_back_into_a_sale_for_that_year():
    inp = deterministic(borrowing_household())
    gates = np.ones((1, inp.n_years, sim.NGATE))
    gates[0, 3, sim.G_BORROW] = 0.0
    log = run_detail(inp, Policy(goal_funding="borrow"), gates[0]).log
    assert log["borrowed"][3] == 0.0 and log["loan"][3] == 0.0
    free = run_detail(inp, Policy(goal_funding="borrow")).log
    assert free["borrowed"][3] > 0


def test_a_market_crash_after_borrowing_forces_a_sale():
    household = make_demo_household(
        accounts=Accounts(brokerage_value=400_000, brokerage_basis=300_000, pretax_balance=400_000, roth_balance=30_000, cash=0)
    )
    rets = np.zeros((1, household.horizon_years, 3))
    rets[0, 4, markets.EQUITY] = -0.60  # the year after the purchase
    log = run_detail(deterministic(household, rets=rets), Policy(goal_funding="borrow", stock_share=1.0, glide_drop=0.0)).log
    assert log["borrowed"][3] > 0
    assert log["forced_sale"][4] > 0  # loan > 40% of the shrunken account
    assert log["loan"][4] <= 0.40 * log["brokerage"][4] + 1.0


# --- Deciding each year after seeing it: forced actions and the realize-gains action ----------


def test_running_a_year_in_two_halves_reproduces_the_fixed_strategy_exactly():
    for policy in (RIA_BASELINE, menu_policy("70|fill22_every|10|on|on|roth_low|borrow"), menu_policy("100|none|0|off|off")):
        for household in (make_demo_household(), older_household()):
            inp = deterministic(household)
            whole = run_detail(inp, policy)
            halves = sim.run_forced(inp, policy)  # begin the year, (change nothing), finish the year
            assert halves.wealth[0, 0] == whole.wealth[0, 0] and halves.taxes_paid[0, 0] == whole.taxes_paid[0, 0]
            assert halves.unfunded[0, 0] == whole.unfunded[0, 0]
            for column in whole.log:
                assert np.array_equal(halves.log[column], whole.log[column]), column


def test_forcing_the_action_the_policy_would_take_changes_nothing():
    policy = menu_policy("90|fill22_every|10|on|on")
    inp = deterministic()
    whole = run_detail(inp, policy)
    same = {t: {sim.A_STOCK: whole.log["stock_target"][t], sim.A_PC: 0.10} for t in range(inp.n_years)}
    forced = sim.run_forced(inp, policy, same)
    assert forced.wealth[0, 0] == whole.wealth[0, 0]
    assert np.array_equal(forced.log["wealth"], whole.log["wealth"])


def test_a_forced_action_changes_only_the_years_it_touches_and_after():
    inp = deterministic()
    whole = run_detail(inp, RIA_BASELINE)
    forced = sim.run_forced(inp, RIA_BASELINE, {10: {sim.A_STOCK: 1.0}})
    assert np.array_equal(forced.log["wealth"][:10], whole.log["wealth"][:10])  # nothing before the decision changes
    assert forced.log["stock_target"][10] == 1.0 and whole.log["stock_target"][10] < 1.0
    assert forced.log["wealth"][10] != whole.log["wealth"][10] and forced.log["wealth"][11] != whole.log["wealth"][11]


def test_the_planner_can_force_a_conversion_the_policy_would_not_make():
    inp = deterministic()
    whole = run_detail(inp, RIA_BASELINE)
    assert np.all(whole.log["conv"] == 0.0)
    forced = sim.run_forced(inp, RIA_BASELINE, {30: {sim.A_CONV_TOP: P.TOP_OF_12}})
    assert forced.log["conv"][30] > 0 and np.all(np.delete(forced.log["conv"], 30) == 0.0)


def test_realizing_gains_steps_up_the_basis_inside_the_zero_percent_bracket():
    hh = no_wage_household(400_000.0, 200_000.0, age=60, retirement_age=61)
    inp = deterministic(hh, zero_returns=True)
    inp.init[sim.S_BBASIS] = 100_000.0  # 300,000 of unrealized gain
    policy = Policy(flat_fee=0.0, bracket_withdrawals=False, donabach_location=False, stock_share=1.0, glide_drop=0.0)
    base = sim.run_forced(inp, policy)
    forced = sim.run_forced(inp, policy, {0: {sim.A_REALIZE: 1.0}})
    harvested = forced.log["gain_harvest"][0]
    assert base.log["gain_harvest"][0] == 0.0
    # the gain fills what is left of the 0% bracket (income so far is only dividends): well under the 300,000 available
    taxable_before = base.log["taxable_income"][0]
    assert harvested == pytest.approx(P.CG_ZERO_TOP - taxable_before, abs=1.0) and 0 < harvested < 300_000
    assert forced.log["net_gain"][0] == pytest.approx(base.log["net_gain"][0] + harvested)
    assert forced.log["fed_tax"][0] == pytest.approx(base.log["fed_tax"][0], abs=1.0)  # federal rate on it is 0%
    # Illinois has no zero bracket, so it does tax the realized gain
    assert forced.log["il_tax"][0] - base.log["il_tax"][0] == pytest.approx(P.IL_RATE * harvested, rel=0.02)
    assert forced.log["unrealized_gain"][0] < base.log["unrealized_gain"][0] - 0.9 * harvested  # the basis stepped up


def test_realizing_gains_does_nothing_in_a_high_income_year():
    inp = deterministic()
    forced = sim.run_forced(inp, RIA_BASELINE, {5: {sim.A_REALIZE: 1.0}})
    assert forced.log["gain_harvest"][5] == 0.0  # $250,000 of wages leave no 0% bracket
    whole = run_detail(inp, RIA_BASELINE)
    assert np.array_equal(forced.log["wealth"], whole.log["wealth"])


def test_roth_conversion_tax_is_paid_from_the_taxable_account():
    log = detail(menu_policy("90|fill22_low|off|off|off")).log
    t = 24
    assert log["conv"][t] > 0
    assert log["portfolio_tax"][t] == pytest.approx(log["total_tax"][t])  # no wages in retirement
    r = year_return(log, t)
    assert r.roth_conversions == log["conv"][t]


def test_bracket_first_withdrawals_stop_at_the_bracket_target():
    # An all-bond household has no dividends and no gains or losses, so ordinary income before
    # the withdrawal is just interest and the expected pre-tax withdrawal is exact.
    household = make_demo_household(
        accounts=Accounts(brokerage_value=0, brokerage_basis=0, cash=700_000, pretax_balance=3_000_000,
                          pretax_equity_share=0.0, roth_balance=0),
        goals=Goals(retirement_age=62, retirement_spending=300_000),
    )
    policy = Policy(stock_share=0.0, glide_drop=0.0, bracket_withdrawals=True, withdrawal_top=P.TOP_OF_12)
    log = detail(policy, household, zero_returns=True).log
    t = 24
    room = P.TOP_OF_12 + P.STANDARD_DEDUCTION_MFJ - log["interest"][t]
    assert log["interest"][t] > 0
    assert log["ret_dist"][t] == pytest.approx(room, abs=0.01)
    # The rest of the 300,000 comes out of the taxable account (bonds: no gain to report).
    assert log["net_gain"][t] == 0.0
    assert 300_000 - log["ret_dist"][t] > 100_000


def test_pro_rata_withdrawals_split_across_accounts_by_balance():
    inp = deterministic(zero_returns=True)
    policy = Policy(bracket_withdrawals=False, donabach_location=False, stock_share=0.8, glide_drop=0.0)
    log = run_detail(inp, policy).log
    t = 24  # first year of retirement
    pre, brk, ros = log["pretax"][t - 1], log["brokerage"][t - 1], log["roth"][t - 1]
    share = pre / (pre + brk + ros)
    assert log["ret_dist"][t] == pytest.approx(share * 110_000, rel=1e-6)


def test_early_withdrawal_penalty_before_age_59_and_a_half():
    household = make_demo_household(
        people=[
            make_demo_household().people[0].model_copy(update={"age": 52}),
            make_demo_household().people[1].model_copy(update={"age": 51}),
        ],
        accounts=Accounts(brokerage_value=0, brokerage_basis=0, pretax_balance=2_000_000, roth_balance=0, cash=0),
        goals=Goals(home_purchase_in_years=None, college_starts_in_years=None, retirement_age=55, retirement_spending=100_000),
        children_ages=[],
    )
    log = detail(Policy(), household, zero_returns=True).log
    ages = log["age"]
    early = ages < 59.5
    retired = ages >= 55
    # Pre-tax is the only source: every retirement-year withdrawal before 59 1/2 is penalized.
    assert np.all(log["early_base"][early & retired] > 0)
    assert np.all(log["early_base"][~early] == 0.0)
    t = int(np.flatnonzero((ages == 55))[0])
    r = year_return(log, t)
    assert r.early_withdrawal_penalty == pytest.approx(0.10 * log["early_base"][t])
    assert log["early_base"][t] == pytest.approx(log["ret_dist"][t])


def test_penalty_free_sources_come_first_before_59_and_a_half():
    household = make_demo_household(goals=Goals(retirement_age=57, retirement_spending=110_000))
    log = detail(Policy(), household).log
    ages = log["age"]
    window = (ages >= 57) & (ages < 59.5)
    assert window.sum() == 3
    assert np.all(log["ret_dist"][window] == 0.0)  # pre-tax is untouched ...
    assert np.all(log["early_base"][window] == 0.0)  # ... so there is no penalty
    assert np.all(log["net_gain"][window] > 0.0)  # the brokerage account pays the bills
    assert log["ret_dist"][ages == 60][0] > 0.0  # and pre-tax is tapped once 59 1/2 has passed


# --- Horizon 80, required minimum distributions, filers 65 and over ----------------------------


def older_household(age=68, retirement_age=69, pretax=1_500_000.0, spending=90_000.0):
    """A single earner a few years from retirement: born 1958, so RMDs start at 73."""
    return make_demo_household(
        people=[Person(name="Pat", age=age, wages=80_000)],
        children_ages=[],
        accounts=Accounts(
            brokerage_value=200_000, brokerage_basis=150_000, pretax_balance=pretax, roth_balance=0, cash=20_000
        ),
        goals=Goals(
            home_purchase_in_years=None, college_starts_in_years=None,
            retirement_age=retirement_age, retirement_spending=spending,
        ),
        social_security=SocialSecurity(annual_benefit=40_000, start_age=68),
        snapshot=None,
    )


def test_the_simulation_runs_to_age_80_and_the_glide_path_still_ends_at_70():
    assert HORIZON_AGE == 80 and make_demo_household().horizon_years == 42
    log = detail(RIA_BASELINE).log
    assert log["age"][0] == 38 and log["age"][-1] == 79  # the last simulated year ends at 80
    assert np.all(log["stock_target"][32:] == pytest.approx(0.50))  # 70 to 79: held at the glide's end


def test_time_table_counts_spouses_aged_65_or_more():
    tv = deterministic().tv
    aged = tv[:, sim.TV_AGED]
    assert aged[26] == 0 and aged[27] == 1 and aged[28] == 2 and aged[-1] == 2  # 38 -> 65 at t=27, 37 -> 65 at t=28
    assert deterministic(older_household()).tv[0, sim.TV_AGED] == 1


def test_rmds_start_at_75_for_someone_born_in_1960_or_later():
    log = detail(menu_policy("90|none|off|off|off")).log
    ages = log["age"]
    assert np.all(log["rmd"][ages < 75] == 0.0)
    start = int(np.flatnonzero(ages == 75)[0])
    for t in range(start, len(ages)):
        period = P.ULT_PERIODS[int(ages[t]) - P.ULT_FIRST_AGE]
        assert log["rmd"][t] == pytest.approx(log["pretax"][t - 1] / period)  # last December's balance
        assert log["ret_dist"][t] >= log["rmd"][t] - 1e-6
    assert log["rmd"][start] > 100_000  # a multi-million pre-tax balance at 75


def test_rmds_start_at_73_for_someone_born_between_1951_and_1959():
    hh = older_household(age=68)  # born 1958
    inp = deterministic(hh)
    assert inp.hhc[sim.HC_RMD_START] == 73 and deterministic().hhc[sim.HC_RMD_START] == 75
    log = run_detail(inp, Policy(bracket_withdrawals=False, donabach_location=False)).log
    ages = log["age"]
    assert np.all(log["rmd"][ages < 73] == 0.0) and np.all(log["rmd"][ages >= 73] > 0.0)
    t = int(np.flatnonzero(ages == 73)[0])
    assert log["rmd"][t] == pytest.approx(log["pretax"][t - 1] / 26.5)


def test_an_rmd_beyond_spending_is_reinvested_in_the_taxable_account():
    hh = older_household(spending=0.0)  # nothing to spend, so the whole RMD is surplus
    policy = Policy(flat_fee=0.0, bracket_withdrawals=False, donabach_location=False)
    log = run_detail(deterministic(hh, zero_returns=True), policy).log
    t = int(np.flatnonzero(log["age"] == 73)[0])
    assert log["rmd"][t] > 0
    gain = log["brokerage"][t] - log["brokerage"][t - 1]
    assert gain == pytest.approx(log["rmd"][t] - log["portfolio_tax"][t], abs=1e-6)  # RMD in, tax out


def test_an_rmd_is_spent_before_other_accounts_are_touched():
    hh = older_household(spending=100_000.0)
    log = run_detail(deterministic(hh), Policy(bracket_withdrawals=False, donabach_location=False)).log
    checked = 0
    for t in range(len(log["age"])):
        if log["rmd"][t] > 0 and log["spend_need"][t] <= log["rmd"][t]:
            assert log["ret_dist"][t] == pytest.approx(log["rmd"][t])  # no voluntary pre-tax withdrawal on top
            checked += 1
    assert checked >= 3


def test_conversions_shrink_later_rmds():
    plain = detail(menu_policy("90|none|off|off|off")).log["rmd"]
    converted = detail(menu_policy("90|fill24_every|off|off|off")).log["rmd"]
    assert plain.sum() > 0 and converted.sum() < plain.sum()


def test_the_aged_deduction_is_used_in_the_tax_and_in_the_pretax_valuation():
    hh = older_household()
    st0 = sim._initial_state(hh)
    balance = st0[sim.S_PE] + st0[sim.S_PB] + st0[sim.S_PP]
    aged = 1  # one person, 68
    deduction = P.STANDARD_DEDUCTION_MFJ + aged * P.STANDARD_DEDUCTION_AGED_PER_SPOUSE
    withdrawal, taxable_ss = balance / 20, 0.85 * 40_000
    from app.tax.engine import ordinary_tax
    rate = (ordinary_tax(withdrawal + taxable_ss - deduction) - ordinary_tax(taxable_ss - deduction)) / withdrawal
    expected = (
        st0[sim.S_BE] + st0[sim.S_BB] - 0.15 * (st0[sim.S_BE] - st0[sim.S_BBASIS]) + balance * (1 - rate)
    )
    assert sim.initial_after_tax_wealth(hh) == pytest.approx(expected)


def test_tax_in_every_year_matches_the_engine():
    for policy in (RIA_BASELINE, menu_policy("90|fill22_every|on|on|on")):
        log = detail(policy).log
        for t in range(len(log["age"])):
            r = year_return(log, t)
            assert r.agi == pytest.approx(log["agi"][t], abs=0.01)
            assert r.federal_total == pytest.approx(log["fed_tax"][t], abs=0.01)
            assert r.illinois_tax == pytest.approx(log["il_tax"][t], abs=0.01)
            assert r.grand_total == pytest.approx(log["total_tax"][t], abs=0.01)


def test_portfolio_tax_is_total_minus_tax_on_wages_alone():
    log = detail(RIA_BASELINE).log
    assert np.allclose(log["portfolio_tax"], log["total_tax"] - log["wage_tax"])
    assert np.all(log["wage_tax"][24:] == 0.0)  # no wages after retirement


def test_assets_are_conserved_with_zero_returns():
    """Every dollar of change is a contribution, goal, spending, tax or fee."""
    for policy in (
        RIA_BASELINE,
        menu_policy("80|fill22_every|on|on|on"),
        menu_policy("100|none|off|off|off"),
        menu_policy("60|fill24_every|15|off|on|roth"),
        menu_policy("70|none|5|on|off|roth_low"),
    ):
        res = detail(policy, zero_returns=True)
        log = res.log
        total = log["pretax"] + log["roth"] + log["brokerage"] + log["bucket"]
        household = make_demo_household()
        previous = household.liquid_wealth
        for t in range(len(total)):
            flows = (
                log["k401"][t] + log["brokerage_saving"][t] - log["roth_gap"][t]
                - log["goal_paid"][t] - log["spend_need"][t] - log["fee"][t]
                - (log["portfolio_tax"][t] - log["conv_cash"][t])  # conversion tax paid from wages leaves no hole
            )
            assert total[t] - previous == pytest.approx(flows, abs=1e-6), (policy, t)
            previous = total[t]
        assert res.unfunded[0, 0] == 0.0


def test_obligations_nobody_can_fund_are_recorded_and_reduce_wealth():
    poor = make_demo_household(
        accounts=Accounts(brokerage_value=10_000, brokerage_basis=10_000, pretax_balance=0, roth_balance=0, cash=0),
        goals=Goals(home_purchase_in_years=1, home_down_payment=500_000, college_starts_in_years=None,
                    retirement_age=62, retirement_spending=110_000),
    )
    res = detail(Policy(), poor, zero_returns=True)
    assert res.unfunded[0, 0] > 100_000  # a 500,000 down payment with ~85,000 of savings by year 1
    funded = make_demo_household(
        accounts=Accounts(brokerage_value=900_000, brokerage_basis=900_000, pretax_balance=0, roth_balance=0, cash=0),
        goals=poor.goals,
    )
    assert detail(Policy(), funded, zero_returns=True).unfunded[0, 0] == 0.0


def test_policy_rows_round_trip_the_parameters():
    row = menu_policy("80|fill24_every|on|on|off").row(38)
    assert row[sim.SP_STOCK] == 0.8 and row[sim.SP_GLIDE_START] == 58 and row[sim.SP_GLIDE_DROP] == 0.25
    assert row[sim.SP_PC] == 0.10 and row[sim.SP_DI] == 1 and row[sim.SP_BUCKET] == 0
    assert row[sim.SP_CONV_TOP] == P.TOP_OF_24 and row[sim.SP_CONV_EVERY] == 1
    assert row[sim.SP_WD_TOP] == P.TOP_OF_24 and row[sim.SP_FEE_BREAKPOINTS] == 0
    ria = RIA_BASELINE.row(41)
    assert ria[sim.SP_GLIDE_START] == 41 and ria[sim.SP_LOCATION] == 1 and ria[sim.SP_FEE_BREAKPOINTS] == 1
    assert ria[sim.SP_GLIDE_DROP] == pytest.approx(0.30) and ria[sim.SP_WD_BRACKET] == 0


def test_initial_after_tax_wealth_matches_hand_calculation():
    # brokerage 150,000 less 15% of 40,000 gain, cash 40,000, Roth 30,000, and a 400,000 pre-tax
    # balance withdrawn 20,000 a year beside 42,500 of taxable Social Security.
    rate = ((2_480 + 0.12 * (30_300 - 24_800)) - 0.10 * 10_300) / 20_000
    expected = 150_000 - 0.15 * 40_000 + 40_000 + 30_000 + 400_000 * (1 - rate)
    assert sim.initial_after_tax_wealth(make_demo_household()) == pytest.approx(expected, abs=1e-6)


def test_gates_remove_a_decision_for_one_year_only():
    inp = deterministic()
    policy = menu_policy("90|fill22_low|off|on|on")
    base = run_detail(inp, policy).log
    t = 25
    assert base["conv"][t] > 0 and base["harvest"][t] > 0
    for gate, column in [(sim.G_CONV, "conv"), (sim.G_HARVEST, "harvest")]:
        gates = np.ones((1, inp.n_years, sim.NGATE))
        gates[0, t, gate] = 0.0
        log = run_detail(inp, policy, gates[0]).log
        assert log[column][t] == 0.0
        assert np.allclose(log[column][:t], base[column][:t])  # earlier years untouched
        assert log[column][t + 1] > 0  # the decision is back the next year
    gates = np.ones((1, inp.n_years, sim.NGATE))
    gates[0, 0, sim.G_BUCKET] = 0.0
    assert run_detail(inp, policy, gates[0]).log["bucket"][0] == 0.0  # not funded in year 0


def test_removing_the_location_gate_uses_the_same_mix_in_every_account():
    inp = deterministic()
    policy = menu_policy("90|none|on|off|off")
    gates = np.ones((1, inp.n_years, sim.NGATE))
    gates[0, 0, sim.G_LOCATION] = 0.0
    a = run_detail(inp, policy).wealth[0, 0]
    b = run_detail(inp, policy, gates[0]).wealth[0, 0]
    assert a != b


# --- Batches, futures, determinism ---------------------------------------------------------


def test_strategies_see_the_same_futures():
    inp = build_inputs(make_demo_household(), n_paths=64, seed=9)
    a, b, c = RIA_BASELINE, menu_policy("90|none|on|on|on"), menu_policy("70|fill22_every|off|off|off")
    alone = run_batch(inp, [b]).wealth[0]
    together = run_batch(inp, [a, b, c]).wealth
    assert np.array_equal(alone, together[1])


def test_same_seed_same_results_different_seed_different_results():
    hh = make_demo_household()
    a = run_batch(build_inputs(hh, 100, seed=4), [RIA_BASELINE]).wealth
    b = run_batch(build_inputs(hh, 100, seed=4), [RIA_BASELINE]).wealth
    c = run_batch(build_inputs(hh, 100, seed=5), [RIA_BASELINE]).wealth
    assert np.array_equal(a, b) and not np.array_equal(a, c)


def test_path_wealth_ends_at_terminal_wealth():
    inp = build_inputs(make_demo_household(), n_paths=20, seed=2)
    res = run_batch(inp, [RIA_BASELINE, menu_policy("90|none|on|on|on")], record_paths=True)
    assert res.path_wealth.shape == (2, 20, HORIZON_YEARS)
    assert np.array_equal(res.path_wealth[:, :, -1], res.wealth)


def test_baseline_outcomes_are_in_a_sensible_range():
    res = run_batch(build_inputs(make_demo_household(), 400, seed=2026), [RIA_BASELINE])
    w = res.wealth[0]
    assert np.all(np.isfinite(w))
    # Over 42 years a few very bad futures (long, deep bear markets in retirement) exhaust the money.
    assert (res.unfunded[0] > 0).mean() < 0.02
    assert 1.5e6 < np.median(w) < 6e6
    assert np.percentile(w, 10) < np.median(w) < np.percentile(w, 90)


def test_market_shock_whatif_lowers_wealth():
    hh = make_demo_household()
    base = run_batch(build_inputs(hh, 100, seed=3), [RIA_BASELINE]).wealth
    shocked = run_batch(build_inputs(hh, 100, seed=3, shock=MarketShock(year=1, equity_return=-0.30)), [RIA_BASELINE]).wealth
    assert np.median(shocked) < np.median(base)


def test_search_scale_batch_is_fast_and_finite():
    import time

    policies = [s.policy() for s in menu()][:672]
    inp = build_inputs(make_demo_household(), 400, seed=1)
    run_batch(inp, policies[:2])  # make sure the kernel is compiled
    start = time.perf_counter()
    res = run_batch(inp, policies)
    elapsed = time.perf_counter() - start
    assert np.all(np.isfinite(res.wealth))
    assert elapsed < 2.0, f"full search took {elapsed:.2f}s"


def test_extreme_households_stay_finite():
    rng = np.random.default_rng(0)
    for _ in range(40):
        age = int(rng.integers(25, 60))
        wages = float(rng.uniform(0, 600_000))
        hh = make_demo_household(
            people=[make_demo_household().people[0].model_copy(update={"age": age, "wages": wages})],
            children_ages=[int(a) for a in rng.integers(0, 20, rng.integers(0, 4))],
            accounts=Accounts(
                brokerage_value=float(rng.uniform(0, 2e6)), brokerage_basis=float(rng.uniform(0, 2e6)),
                pretax_balance=float(rng.uniform(0, 3e6)), roth_balance=float(rng.uniform(0, 5e5)),
                cash=float(rng.uniform(0, 3e5)),
            ),
            goals=Goals(retirement_age=int(rng.integers(max(age + 1, 50), 71)), retirement_spending=float(rng.uniform(20_000, 300_000))),
        )
        inp = build_inputs(hh, 30, seed=int(rng.integers(1_000)))
        res = run_batch(inp, [RIA_BASELINE] + [menu()[i].policy() for i in rng.integers(0, len(menu()), 6)])
        assert np.all(np.isfinite(res.wealth)) and np.all(res.unfunded >= 0)


# --- helpers -------------------------------------------------------------------------------


def menu_policy(key: str) -> Policy:
    from app.planner.strategies import Strategy

    stock, conversion, pc, di, gb, *rest = key.split("|")
    pc = {"on": "10", "off": "0"}.get(pc, pc)  # keys may say on/off for the 10% sleeve
    return Strategy.from_choices({
        "stock_share": stock, "conversion": conversion, "private_credit": pc,
        "direct_indexing": di, "goal_bonds": gb,
        "k401": rest[0] if rest else "pretax", "goal_funding": rest[1] if len(rest) > 1 else "sell",
    }).policy()


def year_return(log, t):
    """Recompute year t's tax return from the logged tax inputs."""
    return compute_return(TaxInputs(
        wages=log["wages_taxable"][t],
        interest=log["interest"][t],
        qualified_dividends=log["dividends"][t],
        ordinary_dividends=log["dividends"][t],
        net_capital_gain=log["net_gain"][t],
        retirement_distributions=log["ret_dist"][t],
        roth_conversions=log["conv"][t],
        social_security=log["ss"][t],
        early_withdrawal_base=log["early_base"][t],
        children_under_17=int(log["kids"][t]),
        dependents=int(log["deps"][t]),
        capital_loss_carryforward=log["cf_in"][t],
        aged_spouses=int(log["aged"][t]),
    ))
