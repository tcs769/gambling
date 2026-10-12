"""Update 4: the passed-to-heirs valuation, gifts to charity (and giving appreciated lots instead of cash), the typical
advisor's fund distributions, and the diagnostics (what was sold and why, the tax by kind of income, the same sales under
another lot rule)."""

from __future__ import annotations

import numpy as np
import pytest
from tests.conftest import make_demo_household
from tests.test_lots import lot_state

from app.planner.baseline import ACTIVE_FUND_DISTRIBUTION, ACTIVE_FUND_SHORT_TERM_SHARE, RIA_BASELINE, TYPICAL_ADVISOR
from app.planner.search import REFINE_DIRECT_INDEXING, SCREEN_KEEP, _by_stock, search
from app.planner.strategies import menu
from app.schemas import Goals
from app.sim import diag as D
from app.sim import markets
from app.sim import simulate as sim
from app.sim.replay import REPLAY_GAIN, REPLAY_UNREALIZED, replay_batch
from app.sim.simulate import ModelOptions, Policy, build_inputs, run_batch
from app.sim.state import LOTS_FIFO, LOTS_HIFO, MAX_LOTS
from app.sim.stocks import di_donate, di_start, di_year_begin
from app.tax.engine import TaxInputs, compute_return

NO_STOCKS = np.ones(sim.N_STOCKS, dtype=np.float32)
DONABACH_POLICIES = [s.policy() for s in menu(style="equity_first")]
DI_PLAN = next(p for p in DONABACH_POLICIES if p.direct_indexing)  # a strategy that direct-indexes (the stock-level book)
FUND_PLAN = next(p for p in DONABACH_POLICIES if not p.direct_indexing)


def deterministic(household=None):
    return build_inputs(household or make_demo_household(), deterministic=True)


def with_giving(giving, brokerage=600_000.0, basis=100_000.0, **goals):
    base = make_demo_household()
    accounts = base.accounts.model_copy(update={"brokerage_value": brokerage, "brokerage_basis": basis})
    new_goals = base.goals.model_copy(update={"charitable_giving": giving, **goals})
    return base.model_copy(update={"accounts": accounts, "goals": new_goals})


# --- What is chosen and what is cited ----------------------------------------------------------------------------


def test_the_policies_say_who_gives_lots_and_whose_funds_distribute():
    assert all(p.donate_lots for p in DONABACH_POLICIES)  # Donabach gives its lowest-basis lots instead of cash ...
    assert not RIA_BASELINE.donate_lots and not TYPICAL_ADVISOR.donate_lots  # ... the advisors give cash
    assert RIA_BASELINE.fund_distribution == 0.0 and RIA_BASELINE.fund_distribution_short_term == 0.0  # index funds
    assert TYPICAL_ADVISOR.fund_distribution == ACTIVE_FUND_DISTRIBUTION == 0.055
    assert TYPICAL_ADVISOR.fund_distribution_short_term == ACTIVE_FUND_SHORT_TERM_SHARE == 0.12
    assert all(p.fund_distribution == 0.0 for p in DONABACH_POLICIES)
    row = TYPICAL_ADVISOR.row(40.0)
    assert row[sim.SP_DIST] == 0.055 and row[sim.SP_DISTST] == 0.12 and row[sim.SP_DONATE] == 0.0
    assert DI_PLAN.row(40.0)[sim.SP_DONATE] == 1.0


def test_the_stock_volatility_is_the_cited_one_and_the_heirs_rate_is_stated():
    assert markets.STOCK_IDIO_VOL == 0.25 and ModelOptions().idio_vol == 0.25
    assert sim.HEIRS_TAX_RATE == 0.24 and ModelOptions().heirs_rate == 0.24


# --- The second valuation: passed to heirs ---------------------------------------------------------------------


def test_heirs_wealth_steps_up_the_brokerage_account_and_taxes_the_pretax_balance_at_the_heirs_rate():
    st = np.zeros(sim.NSTATE)
    st[sim.S_PE], st[sim.S_PB] = 300_000.0, 100_000.0
    st[sim.S_RE], st[sim.S_RB] = 50_000.0, 10_000.0
    st[sim.S_BE], st[sim.S_BBASIS], st[sim.S_BB], st[sim.S_GB] = 200_000.0, 80_000.0, 5_000.0, 7_000.0
    st[sim.S_LOAN], st[sim.S_DGAIN], st[sim.S_UNFUNDED], st[sim.S_CF] = 3_000.0, 10_000.0, 1_000.0, 50_000.0
    hhc = np.zeros(sim.NHC)
    hhc[sim.HC_HEIRS_RATE], hhc[sim.HC_VALUATION] = 0.24, 1.0  # the flat valuation: the gains already realized cost 15%
    expected = 200_000 + 5_000 + 7_000 + 60_000 + 400_000 * (1 - 0.24) - 3_000 - 0.15 * 10_000 - 1_000
    # no tax on the 120,000 of unrealized gain, and the 50,000 of loss carryforward is worth nothing to them
    assert sim.heirs_wealth(st, hhc, 0.0, 0.0, 0.0, 0.0, 0.0) == pytest.approx(expected)
    # the engine's valuation taxes those realized gains on the owner's last return instead
    hhc[sim.HC_VALUATION] = 0.0
    engine = sim.heirs_wealth(st, hhc, 0.0, 0.0, 0.0, 0.0, 0.0)
    assert engine == pytest.approx(expected + 0.15 * 10_000 - compute_return(TaxInputs(net_capital_gain=10_000.0)).grand_total)


@pytest.mark.parametrize("policy", [RIA_BASELINE, TYPICAL_ADVISOR, FUND_PLAN, DI_PLAN], ids=["ria", "typical", "plan", "di plan"])
def test_the_two_valuations_differ_by_the_step_up_the_heirs_rate_and_the_carryforward(policy):
    inputs = build_inputs(make_demo_household(), deterministic=True, options=ModelOptions(valuation="flat"))  # the identity is the flat valuation's
    batch = run_batch(inputs, [policy], log_for=(0, 0))
    log = batch.log
    rate = float(inputs.hhc[sim.HC_HEIRS_RATE])
    expected = (
        0.15 * max(0.0, log["unrealized_gain"][-1])  # liquidating taxes the unrealized gain; a step-up does not
        - 0.15 * log["cf_out"][-1]  # the carryforward is worth 15% to the owner, nothing to the heirs
        + batch.pretax_owed[0, 0]  # liquidating charges the effective rate on the pre-tax balance ...
        - rate * log["pretax"][-1]  # ... and the heirs' flat rate replaces it
    )
    assert batch.wealth_heirs[0, 0] - batch.wealth[0, 0] == pytest.approx(expected, abs=1e-6)
    assert batch.wealth_heirs.shape == batch.wealth.shape


def test_the_heirs_rate_moves_only_the_second_valuation():
    household = make_demo_household()
    base = run_batch(build_inputs(household, n_paths=30, seed=3), [RIA_BASELINE])
    other = run_batch(build_inputs(household, n_paths=30, seed=3, options=ModelOptions(heirs_rate=0.0)), [RIA_BASELINE])
    assert np.array_equal(base.wealth, other.wealth) and np.array_equal(base.taxes_paid, other.taxes_paid)
    assert (other.wealth_heirs > base.wealth_heirs).all()


def test_roth_conversions_are_worth_more_to_heirs_than_to_an_owner_who_liquidates():
    # the heirs' flat 24% is more than the effective rate on a pre-tax balance spread over 20 years, so a plan that has
    # converted to Roth gains on the plan that did not when the valuation moves from "liquidated" to "passed to heirs"
    inputs = build_inputs(make_demo_household(), n_paths=60, seed=5)
    converting = next(p for p in DONABACH_POLICIES if p.conversion_top > 0 and not p.direct_indexing)
    batch = run_batch(inputs, [converting, RIA_BASELINE])
    gap_liquidated = np.median(batch.wealth[0] - batch.wealth[1])
    gap_heirs = np.median(batch.wealth_heirs[0] - batch.wealth_heirs[1])
    assert gap_heirs > gap_liquidated


# --- Gifts to charity ----------------------------------------------------------------------------------------------


def hifo_cash(**kw):
    return RIA_BASELINE.replace(lot_method="hifo", **kw)


def test_a_gift_is_paid_in_cash_by_a_policy_that_does_not_give_lots():
    log = run_batch(deterministic(with_giving(20_000.0)), [hifo_cash(donate_lots=False)], log_for=(0, 0)).log
    assert np.allclose(log["gift_cash"], 20_000.0) and np.allclose(log["gift_stock"], 0.0)


def test_a_policy_that_gives_lots_gives_stock_held_over_a_year_and_pays_the_rest_in_cash():
    log = run_batch(deterministic(with_giving(20_000.0)), [hifo_cash(donate_lots=True)], log_for=(0, 0)).log
    assert np.allclose(log["gift_stock"] + log["gift_cash"], 20_000.0)  # the gift is the same either way
    assert log["gift_stock"][0] == pytest.approx(20_000.0)  # the opening position is long-term and has a gain: all of it, in kind
    assert log["gift_stock"].sum() > 0.5 * 20_000.0 * len(log["age"])  # and most years after


def test_giving_lots_beats_giving_cash_by_the_gains_that_would_have_been_realized():
    inputs = build_inputs(with_giving(20_000.0), n_paths=80, seed=8)
    batch = run_batch(inputs, [hifo_cash(donate_lots=False), hifo_cash(donate_lots=True)])
    assert np.median(batch.taxes_paid[1] - batch.taxes_paid[0]) < 0  # fewer taxes on gains, along the way ...
    assert np.median(batch.wealth[1] - batch.wealth[0]) > 0  # ... and more after-tax wealth when everything is sold
    assert np.median(batch.wealth_heirs[1] - batch.wealth_heirs[0]) > 0  # and, with a step-up, still more


def test_without_gifts_giving_lots_changes_nothing():
    inputs = build_inputs(with_giving(0.0), n_paths=30, seed=2)
    batch = run_batch(inputs, [hifo_cash(donate_lots=False), hifo_cash(donate_lots=True)])
    assert np.array_equal(batch.wealth[0], batch.wealth[1]) and np.array_equal(batch.wealth_heirs[0], batch.wealth_heirs[1])


def test_a_household_with_no_gains_pays_cash_even_if_its_plan_gives_lots():
    inputs = deterministic(with_giving(15_000.0, brokerage=300_000.0, basis=300_000.0))
    inputs.rets = np.zeros_like(inputs.rets)  # nothing grows: the price falls by the dividends paid, so every lot is at a loss
    log = run_batch(inputs, [hifo_cash(donate_lots=True)], log_for=(0, 0)).log
    assert log["gift_stock"][0] == 0.0 and log["gift_cash"][0] == 15_000.0  # nothing to give but cost


def test_spare_wages_pay_the_gift_first_so_it_costs_the_portfolio_nothing_while_they_last():
    giving = 8_000.0
    without = run_batch(deterministic(with_giving(0.0)), [hifo_cash()], log_for=(0, 0)).log
    gives = run_batch(deterministic(with_giving(giving)), [hifo_cash()], log_for=(0, 0)).log
    assert without["free_cash"][0] - gives["free_cash"][0] == pytest.approx(giving)  # it came out of spare wages
    # the portfolio was not touched: all it gained is the tax the deduction saved (at most 40% of the 2,000 allowance)
    assert 0.0 <= gives["brokerage"][0] - without["brokerage"][0] < 0.40 * 2_000.0


def test_the_cash_a_gift_of_stock_saves_the_household_is_saved():
    giving = 8_000.0
    inputs = deterministic(with_giving(giving))
    cash = run_batch(inputs, [hifo_cash(donate_lots=False)], log_for=(0, 0)).log
    lots = run_batch(inputs, [hifo_cash(donate_lots=True)], log_for=(0, 0)).log
    t = 0
    assert lots["gift_stock"][t] == pytest.approx(giving)
    # the household keeps the cash it would have given out of its wages and saves it in the brokerage account
    assert lots["brokerage_saving"][t] - cash["brokerage_saving"][t] == pytest.approx(giving)


def test_the_year_return_shows_the_gifts_and_matches_the_kernels_tax():
    from tests.test_sim import year_return

    household = with_giving(40_000.0)
    for policy in (hifo_cash(donate_lots=False), hifo_cash(donate_lots=True)):
        log = run_batch(deterministic(household), [policy], log_for=(0, 0)).log
        for t in range(0, len(log["age"]), 4):
            assert year_return(log, t).grand_total == pytest.approx(log["total_tax"][t], abs=0.01)
        assert (log["itemized"] > 0).any()  # 40,000 beats the standard deduction once the floor is taken off


# --- Giving lots: the helpers --------------------------------------------------------------------------------------


def test_a_gift_takes_the_lowest_cost_lots_held_over_a_year_and_realizes_nothing():
    st = lot_state([(100_000, 40_000), (50_000, 45_000), (20_000, 20_000)], year=9, method=sim.LOTS_HIFO)
    given = sim._lots_donate(st, 60_000.0)
    assert given == pytest.approx(60_000.0)
    assert st[sim.S_LOTU] == pytest.approx(40_000.0) and st[sim.S_LOTU + 1] == pytest.approx(50_000.0)  # the opening lot went
    assert st[sim.S_BE] == pytest.approx(110_000.0) and st[sim.S_BBASIS] == pytest.approx(0.4 * 40_000 + 45_000 + 20_000)
    assert st[sim.S_UNITS] == pytest.approx(110_000.0) and st[sim.S_BE] == pytest.approx(st[sim.S_PRICE] * st[sim.S_UNITS])


def test_a_gift_never_takes_a_lot_without_a_gain_or_one_held_a_year_or_less():
    # lots: opening (100,000 at 40%), a lot with no gain, a lot with a loss, a lot bought this year with a gain
    st = lot_state([(100_000, 40_000), (30_000, 30_000), (30_000, 45_000), (0, 0)], year=2, method=sim.LOTS_HIFO)
    st[sim.S_LOTU + 3], st[sim.S_LOTC + 3] = 10_000.0, 0.5  # lot 3 is year 2's own: a gain, but short-term
    st[sim.S_UNITS] += 10_000.0
    st[sim.S_BE] = st[sim.S_UNITS]
    st[sim.S_BBASIS] += 5_000.0
    given = sim._lots_donate(st, 1e9)
    assert given == pytest.approx(100_000.0)  # only the opening position qualifies
    assert st[sim.S_LOTU + 1] == pytest.approx(30_000.0) and st[sim.S_LOTU + 2] == pytest.approx(30_000.0)
    assert st[sim.S_LOTU + 3] == pytest.approx(10_000.0)
    cost = sum(st[sim.S_LOTC + i] * st[sim.S_LOTU + i] for i in range(MAX_LOTS))
    assert st[sim.S_BBASIS] == pytest.approx(cost)


def test_an_account_without_lots_gives_pro_rata_and_only_when_it_has_a_gain():
    st = np.zeros(sim.NSTATE)
    st[sim.S_BE], st[sim.S_BBASIS] = 100_000.0, 40_000.0
    assert sim._lots_donate(st, 30_000.0) == pytest.approx(30_000.0)
    assert st[sim.S_BE] == pytest.approx(70_000.0) and st[sim.S_BBASIS] == pytest.approx(28_000.0)
    flat = np.zeros(sim.NSTATE)
    flat[sim.S_BE], flat[sim.S_BBASIS] = 100_000.0, 100_000.0
    assert sim._lots_donate(flat, 30_000.0) == 0.0 and flat[sim.S_BE] == 100_000.0


def book_with_half_up():
    st = np.zeros(sim.NSTATE_DI)
    st[sim.S_BE], st[sim.S_BBASIS] = 100_000.0, 100_000.0
    di_start(st)
    g = np.ones(sim.N_STOCKS, dtype=np.float32)
    g[: sim.N_STOCKS // 2] = 1.5  # half the stocks go up 50% and half down 50%: the sleeve is where it was
    g[sim.N_STOCKS // 2 :] = 0.5
    di_year_begin(st, 0, 1.0, g, 0.0, 0.01, False)
    st[sim.S_YEAR] = 1
    return st


def test_the_book_gives_only_lots_with_a_gain():
    st = book_with_half_up()
    given = di_donate(st, 1e9)
    assert given == pytest.approx(75_000.0)  # the 50 stocks that rose: 50,000 at cost, worth 75,000
    assert st[sim.S_BE] == pytest.approx(25_000.0) and st[sim.S_BBASIS] == pytest.approx(50_000.0)  # the losers stay


def test_the_book_gives_nothing_when_every_lot_is_under_water():
    st = np.zeros(sim.NSTATE_DI)
    st[sim.S_BE], st[sim.S_BBASIS] = 100_000.0, 100_000.0
    di_start(st)
    di_year_begin(st, 0, 0.5, NO_STOCKS, 0.0, 0.01, False)
    st[sim.S_YEAR] = 1
    before = st.copy()
    assert di_donate(st, 10_000.0) == 0.0 and np.array_equal(st, before)


# --- Fund distributions -------------------------------------------------------------------------------------------


def test_a_fund_distribution_is_realized_without_a_sale_and_raises_every_lots_cost():
    st = lot_state([(100_000, 40_000), (50_000, 45_000)], year=3, method=sim.LOTS_FIFO)
    tv = np.zeros((4, sim.NTV))
    tv[:, sim.TV_AGE] = 50.0
    ys, act = np.zeros(sim.NY), np.zeros(sim.NACT)
    act[sim.A_DIST], act[sim.A_DISTST] = 0.05, 0.20
    sim._year_begin(st, ys, tv, 3, np.zeros(sim.NHC), act, 0.0, 0.0, 0.0, NO_STOCKS)  # a flat market: the value is 150,000
    assert st[sim.S_BE] == pytest.approx(150_000.0)
    assert ys[sim.Y_DIST] == pytest.approx(7_500.0) and ys[sim.Y_DISTST] == pytest.approx(1_500.0)
    assert ys[sim.Y_REALIZED] == pytest.approx(6_000.0)  # the long-term part is a gain on the return; the rest is dividends
    cost = sum(st[sim.S_LOTC + i] * st[sim.S_LOTU + i] for i in range(MAX_LOTS))
    assert st[sim.S_BBASIS] == pytest.approx(cost)  # the account's basis is still its lots'
    assert st[sim.S_BBASIS] == pytest.approx(85_000.0 + 2_700.0 + 7_500.0)  # the dividends and the distribution, reinvested
    assert st[sim.S_LOTC] == pytest.approx(0.4 + 0.05 * st[sim.S_PRICE])  # every lot's cost per unit rose by 5% of the price


def test_an_account_without_lots_adds_the_distribution_to_its_basis():
    st = np.zeros(sim.NSTATE)
    st[sim.S_BE], st[sim.S_BBASIS] = 100_000.0, 60_000.0
    tv = np.zeros((1, sim.NTV))
    tv[0, sim.TV_AGE] = 50.0
    ys, act = np.zeros(sim.NY), np.zeros(sim.NACT)
    act[sim.A_DIST] = 0.04
    sim._year_begin(st, ys, tv, 0, np.zeros(sim.NHC), act, 0.0, 0.0, 0.0, NO_STOCKS)
    assert ys[sim.Y_DIST] == pytest.approx(4_000.0) and ys[sim.Y_DISTST] == 0.0
    assert st[sim.S_BBASIS] == pytest.approx(60_000.0 + 1_800.0 + 4_000.0)


def test_funds_that_distribute_cost_the_typical_advisor_tax_and_wealth():
    inputs = build_inputs(make_demo_household(), n_paths=40, seed=9)
    none = TYPICAL_ADVISOR.replace(fund_distribution=0.0, fund_distribution_short_term=0.0)
    batch = run_batch(inputs, [TYPICAL_ADVISOR, none])
    assert (batch.taxes_paid[0] > batch.taxes_paid[1]).all()
    assert np.median(batch.wealth[0]) < np.median(batch.wealth[1])


def test_the_short_term_part_of_a_distribution_is_taxed_as_an_ordinary_dividend():
    inputs = deterministic()
    log = run_batch(inputs, [TYPICAL_ADVISOR], log_for=(0, 0)).log
    assert log["fund_distribution_short_term"] == pytest.approx(0.12 * log["fund_distribution"])
    from tests.test_sim import year_return

    for t in range(0, len(log["age"]), 3):
        assert year_return(log, t).grand_total == pytest.approx(log["total_tax"][t], abs=0.01)
        r = year_return(log, t)
        assert r.ordinary_dividends == pytest.approx(log["dividends"][t] + log["fund_distribution_short_term"][t])


def test_the_direct_indexing_book_holds_stocks_which_distribute_nothing():
    policy = DI_PLAN.replace(fund_distribution=0.05, fund_distribution_short_term=0.1)
    batch = run_batch(deterministic(), [policy], diagnostics=True)
    assert batch.diag[0, 0, D.D_FUNDDIST] == 0.0


# --- Diagnostics ------------------------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def run():
    household = make_demo_household()
    inputs = build_inputs(household, n_paths=40, seed=11)
    policies = [DI_PLAN, FUND_PLAN, RIA_BASELINE, TYPICAL_ADVISOR]
    return inputs, policies, run_batch(inputs, policies, diagnostics=True)


def test_asking_for_diagnostics_changes_no_result(run):
    inputs, policies, with_diag = run
    plain = run_batch(inputs, policies)
    assert plain.diag is None and with_diag.diag.shape == (4, 40, D.DG_SIZE)
    assert np.array_equal(plain.wealth, with_diag.wealth) and np.array_equal(plain.wealth_heirs, with_diag.wealth_heirs)
    assert np.array_equal(plain.taxes_paid, with_diag.taxes_paid)


def test_the_tax_by_kind_of_income_adds_up_to_the_taxes_paid(run):
    _, _, batch = run
    by_type = batch.diag[:, :, D.D_TYPE : D.D_TYPE + D.N_TYPES].sum(axis=2)
    assert np.allclose(by_type, batch.taxes_paid, rtol=1e-9, atol=1e-6)


def test_the_tax_on_capital_gains_by_purpose_adds_up_to_the_tax_on_short_and_long_term_gains(run):
    _, _, batch = run
    d = batch.diag
    by_purpose = d[:, :, D.D_TAX : D.D_TAX + D.N_PURPOSES].sum(axis=2)
    assert np.allclose(by_purpose, d[:, :, D.D_TYPE + D.T_SHORT_TERM] + d[:, :, D.D_TYPE + D.T_LONG_TERM], rtol=1e-9, atol=1e-6)


def test_what_was_sold_for_each_purpose_adds_up_to_what_the_tape_says_was_sold(run):
    _, _, batch = run
    d = batch.diag
    tape = d[:, :, D.D_TAPE :].reshape(*d.shape[:2], MAX_LOTS, D.NK)
    sold = np.maximum(0.0, -tape)
    sold[..., [D.TAPE_DONATE, D.TAPE_SAVING]] = 0.0  # a gift of stock is not a sale and a purchase is not a sale
    assert np.allclose(sold.sum(axis=(2, 3)), d[:, :, D.D_SOLD : D.D_SOLD + D.N_PURPOSES].sum(axis=2), rtol=1e-9, atol=1e-6)
    assert (d[:, :, D.D_SOLD : D.D_SOLD + D.N_PURPOSES] >= 0).all()


@pytest.mark.parametrize("policy", [DI_PLAN, FUND_PLAN, RIA_BASELINE, TYPICAL_ADVISOR], ids=["di plan", "plan", "ria", "typical"])
def test_the_gains_by_purpose_reconcile_with_the_gains_on_the_tax_returns(policy):
    inputs = deterministic(with_giving(10_000.0))
    batch = run_batch(inputs, [policy], log_for=(0, 0), diagnostics=True)
    d = batch.diag[0, 0]
    reported = batch.log["net_gain"].sum()
    realized = d[D.D_GAIN : D.D_GAIN + D.N_PURPOSES].sum()
    not_yet_reported = d[D.D_CARRY_TAX] + d[D.D_CARRY_FEE]  # gains from selling for the last year's tax and fee
    assert reported == pytest.approx(realized - not_yet_reported, abs=1e-6 * max(1.0, abs(realized)))


def own_rule(base: Policy, method: float) -> Policy:
    """`base` with nothing but sales: no harvesting, no gifts, no loan, and the lot rule `method`."""
    return base.replace(
        lot_method="hifo" if method == LOTS_HIFO else "fifo", tax_loss_harvesting=False, donate_lots=False, goal_funding="sell"
    )


@pytest.mark.parametrize(
    ("method", "direct"),
    [(LOTS_FIFO, False), (LOTS_HIFO, False), (LOTS_HIFO, True)],
    ids=["fifo fund lots", "hifo fund lots", "hifo book"],  # the book always sells highest cost first
)
def test_replaying_the_sales_under_the_rule_the_run_used_gives_the_gains_it_realized(method, direct):
    inputs = build_inputs(make_demo_household(), n_paths=12, seed=4)
    policy = own_rule(DI_PLAN if direct else FUND_PLAN, method)
    assert sim.wants_book(policy.row(38.0)) == direct
    batch = run_batch(inputs, [policy], diagnostics=True)
    replayed = replay_batch(inputs, [policy], batch, method)
    d = batch.diag[0]
    sales = [p for p in range(D.N_PURPOSES) if p not in (D.P_HARVEST, D.P_DISTRIBUTIONS)]
    realized = sum(d[:, D.D_GAIN + p] for p in sales)
    assert np.allclose(replayed[0, :, REPLAY_GAIN], realized, rtol=1e-7, atol=1e-3)
    assert np.allclose(replayed[0, :, REPLAY_UNREALIZED], d[:, D.D_END_BE] - d[:, D.D_END_BASIS], rtol=1e-7, atol=1e-3)


@pytest.mark.parametrize("direct", [False, True], ids=["fund lots", "the book"])
def test_on_the_same_sales_the_two_rules_end_with_the_same_total_gain_split_differently(run, direct):
    inputs, _, _ = run
    policy = own_rule(DI_PLAN if direct else RIA_BASELINE, LOTS_HIFO)
    batch = run_batch(inputs, [policy], diagnostics=True)
    hifo = replay_batch(inputs, [policy], batch, LOTS_HIFO)[0]
    fifo = replay_batch(inputs, [policy], batch, LOTS_FIFO)[0]
    total_hifo = hifo[:, REPLAY_GAIN] + hifo[:, REPLAY_UNREALIZED]
    total_fifo = fifo[:, REPLAY_GAIN] + fifo[:, REPLAY_UNREALIZED]
    assert np.allclose(total_hifo, total_fifo, rtol=1e-8, atol=1e-3)  # a gain is realized now or left for later: no more
    assert np.median(hifo[:, REPLAY_GAIN]) <= np.median(fifo[:, REPLAY_GAIN])  # highest cost first realizes less ...
    assert np.median(hifo[:, REPLAY_UNREALIZED]) >= np.median(fifo[:, REPLAY_UNREALIZED])  # ... and leaves more


def test_the_replay_needs_a_batch_run_with_diagnostics():
    inputs = build_inputs(make_demo_household(), n_paths=4, seed=1)
    batch = run_batch(inputs, [RIA_BASELINE])
    with pytest.raises(ValueError, match="diagnostics"):
        replay_batch(inputs, [RIA_BASELINE], batch, LOTS_HIFO)


def early_retiree(retirement_age=50):
    base = make_demo_household()
    accounts = base.accounts.model_copy(update={"brokerage_value": 40_000.0, "brokerage_basis": 30_000.0, "cash": 10_000.0})
    goals = Goals(retirement_age=retirement_age, retirement_spending=110_000.0, home_purchase_in_years=None, college_starts_in_years=None)
    return base.model_copy(update={"accounts": accounts, "goals": goals})


def test_pretax_money_spent_before_59_and_a_half_pays_the_penalty_and_the_diagnostics_say_so():
    inputs = build_inputs(early_retiree(), n_paths=12, seed=6)
    batch = run_batch(inputs, [RIA_BASELINE], diagnostics=True)
    d = batch.diag[0]
    assert (d[:, D.D_EARLY] > 0).all()  # a household of 38 retiring at 50 with little outside the pre-tax account
    assert np.allclose(d[:, D.D_PENALTY], 0.10 * d[:, D.D_EARLY], rtol=1e-9)
    withdrawn = d[:, D.D_PTW : D.D_PTW + D.N_WITHDRAWALS]
    assert (withdrawn[:, D.W_SPENDING] > 0).all() and (withdrawn >= 0).all()
    assert (d[:, D.D_TYPE + D.T_WITHDRAWALS] > 0).all()  # the tax on those withdrawals, penalty included


def test_the_spending_reserve_is_found_in_the_accounts_it_is_held_in():
    inputs = build_inputs(make_demo_household(), n_paths=12, seed=6)
    reserve = next(p for p in DONABACH_POLICIES if p.reserve_years and not p.direct_indexing)
    batch = run_batch(inputs, [reserve, RIA_BASELINE], diagnostics=True)
    retired_years = HORIZON - 62
    for s in range(2):
        d = batch.diag[s]
        assert np.all(d[:, D.D_RES_YEARS] == retired_years)
        held = d[:, [D.D_RES_PRETAX, D.D_RES_ROTH, D.D_RES_BROKERAGE]]
        assert (held >= 0).all() and (held.sum(axis=1) > 0).all()
        assert (d[:, D.D_RES0_SET] == 1.0).all()


HORIZON = 80


# --- The planner's search with the stock-level book -------------------------------------------------------------------


def test_the_staged_search_ranks_only_scores_from_the_stock_level_book():
    inputs = build_inputs(make_demo_household(), n_paths=300, seed=2026)
    result = search(inputs, strategies=menu(style="equity_first"))
    stocks = [r for r in result.ranked if _by_stock(r.strategy)]
    assert len(result.ranked) == SCREEN_KEEP and 0 < len(stocks) <= REFINE_DIRECT_INDEXING
    for r in stocks[:3]:
        direct = run_batch(inputs, [r.strategy.policy()]).wealth[0]
        assert r.outcome.median == pytest.approx(float(np.median(direct)))  # the book's own number, not the rule it was screened with


def test_a_small_menu_is_run_in_full_on_the_book():
    inputs = build_inputs(make_demo_household(), n_paths=60, seed=5)
    strategies = [s for s in menu(style="equity_first") if s.direct_indexing][:6]
    result = search(inputs, strategies=strategies)
    assert len(result.ranked) == 6 and all(_by_stock(r.strategy) for r in result.ranked)
    for r in result.ranked:
        assert r.outcome.median == pytest.approx(float(np.median(run_batch(inputs, [r.strategy.policy()]).wealth[0])))


# --- The answers ---------------------------------------------------------------------------------------------


def test_the_annual_giving_input_defaults_to_nothing_and_reaches_the_household():
    from app.api_models import Answers
    from app.schemas import Goals as HouseholdGoals

    assert Answers().charitable_giving == 0.0 and HouseholdGoals().charitable_giving == 0.0
    assert make_demo_household().goals.charitable_giving == 0.0
    inputs = deterministic(with_giving(12_345.0))
    assert np.allclose(inputs.tv[:, sim.TV_GIFT], 12_345.0)
    assert np.allclose(deterministic().tv[:, sim.TV_GIFT], 0.0)


def test_compute_return_takes_the_gifts_of_the_year():
    r = compute_return(TaxInputs(wages=200_000, cash_gifts=50_000))
    assert r.itemized and r.charitable_deduction > 0
