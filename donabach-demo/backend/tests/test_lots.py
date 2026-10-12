"""Tax lots: the brokerage stock is a set of lots, sold oldest first (FIFO) or highest cost first (HIFO), and a gain on a
lot held a year or less is short-term, taxed as ordinary income. The "average" method (no lots) is what every result
used before lots existed and is unchanged."""

from __future__ import annotations

import numpy as np
import pytest
from app.planner.baseline import RIA_BASELINE, TYPICAL_ADVISOR
from app.planner.strategies import Strategy
from app.sim import simulate as sim
from app.sim.simulate import Policy, build_inputs, run_batch, run_detail
from app.tax.engine import TaxInputs, compute_return
from tests.conftest import make_demo_household

# --- The tax engine: short-term gains are ordinary income -------------------------------------------------


def _federal(**kw):
    return compute_return(TaxInputs(wages=200_000, **kw))


def test_a_short_term_gain_is_taxed_like_the_same_amount_of_ordinary_income():
    short = _federal(net_capital_gain=20_000, short_term_gain=20_000)
    long = _federal(net_capital_gain=20_000)
    ordinary = compute_return(TaxInputs(wages=220_000))
    assert short.ordinary_taxable_income == pytest.approx(ordinary.ordinary_taxable_income)
    assert short.ordinary_tax == pytest.approx(ordinary.ordinary_tax)
    assert short.preferential_income == 0.0 and short.capital_gains_tax == 0.0
    assert short.short_term_gain_ordinary == pytest.approx(20_000)
    assert long.preferential_income == pytest.approx(20_000) and long.short_term_gain_ordinary == 0.0
    assert short.federal_total > long.federal_total  # 24% against 15%
    assert short.agi == pytest.approx(long.agi)  # the same income either way; only its rate differs


def test_without_a_short_term_part_nothing_changes():
    assert _federal(net_capital_gain=20_000).model_dump() == _federal(net_capital_gain=20_000, short_term_gain=0.0).model_dump()


def test_short_term_and_long_term_losses_offset_each_other_before_anything_is_taxed():
    # long-term +15,000 and short-term -10,000: a net 5,000 gain, all long-term
    a = _federal(net_capital_gain=5_000, short_term_gain=-10_000)
    assert a.short_term_gain_ordinary == 0.0 and a.preferential_income == pytest.approx(5_000)
    # short-term +10,000 and long-term -4,000: a net 6,000 gain, all short-term (ordinary income)
    b = _federal(net_capital_gain=6_000, short_term_gain=10_000)
    assert b.short_term_gain_ordinary == pytest.approx(6_000) and b.preferential_income == 0.0
    # short-term +5,000 and long-term -20,000: a net loss; $3,000 comes off ordinary income, the rest carries
    c = _federal(net_capital_gain=-15_000, short_term_gain=5_000)
    assert c.short_term_gain_ordinary == 0.0 and c.capital_loss_deducted == pytest.approx(3_000)
    assert c.capital_loss_carryforward_out == pytest.approx(12_000)


def test_a_loss_carryforward_absorbs_short_term_gains_first():
    r = _federal(net_capital_gain=10_000, short_term_gain=10_000, capital_loss_carryforward=4_000)
    assert r.short_term_gain_ordinary == pytest.approx(6_000) and r.capital_gain_line == pytest.approx(6_000)


def test_illinois_and_the_investment_income_tax_treat_both_kinds_of_gain_alike():
    short = _federal(net_capital_gain=30_000, short_term_gain=30_000)
    long = _federal(net_capital_gain=30_000)
    assert short.illinois_tax == pytest.approx(long.illinois_tax)
    assert short.niit == pytest.approx(long.niit)


def test_the_return_shows_the_short_term_part_only_when_there_is_one():
    labels = [line.label for line in _federal(net_capital_gain=20_000, short_term_gain=20_000).lines()]
    assert "of which short-term, taxed as ordinary income" in labels
    assert "of which short-term, taxed as ordinary income" not in [line.label for line in _federal(net_capital_gain=20_000).lines()]


# --- The lot helpers ---------------------------------------------------------------------------------


def lot_state(lots, year, method, short=True):
    """A state at price 1 whose lots are `lots`, a list of (value, basis) by acquisition: lot 0 is the opening position
    and lot 1 + t was bought in year t."""
    st = np.zeros(sim.NSTATE)
    st[sim.S_LOTS] = method
    st[sim.S_STCG] = float(short)
    st[sim.S_YEAR] = year
    st[sim.S_PRICE] = 1.0
    for i, (value, basis) in enumerate(lots):
        st[sim.S_LOTU + i] = value
        st[sim.S_LOTC + i] = basis / value if value else 1.0
    st[sim.S_UNITS] = sum(v for v, _ in lots)
    st[sim.S_BE] = st[sim.S_UNITS]
    st[sim.S_BBASIS] = sum(b for _, b in lots)
    st[sim.S_BEST] = -1.0
    return st


OLD_LOTS = [(100_000, 40_000), (50_000, 45_000), (20_000, 20_000)]  # opening position, bought in years 0 and 1


def test_fifo_sells_the_oldest_lot_first():
    st = lot_state(OLD_LOTS, year=9, method=sim.LOTS_FIFO)
    gain = sim._lots_sell(st, 60_000.0, sim.LOTS_FIFO)
    assert gain == pytest.approx(60_000 * (1 - 0.4))  # 36,000 of the opening position's 60% gain
    assert st[sim.S_LOTU] == pytest.approx(40_000) and st[sim.S_LOTU + 1] == pytest.approx(50_000)
    assert st[sim.S_BE] == pytest.approx(110_000) and st[sim.S_BBASIS] == pytest.approx(40_000 * 0.4 + 45_000 + 20_000)


def test_hifo_sells_the_lot_that_cost_the_most_per_dollar_first():
    st = lot_state(OLD_LOTS, year=9, method=sim.LOTS_HIFO)
    gain = sim._lots_sell(st, 60_000.0, sim.LOTS_HIFO)
    # all 20,000 of the lot with no gain, then 40,000 of the lot that cost 90 cents on the dollar
    assert gain == pytest.approx(40_000 * 0.10)
    assert st[sim.S_LOTU + 2] == 0.0 and st[sim.S_LOTU + 1] == pytest.approx(10_000) and st[sim.S_LOTU] == pytest.approx(100_000)
    assert st[sim.S_BE] == pytest.approx(110_000) and st[sim.S_BBASIS] == pytest.approx(40_000 + 45_000 / 5)


@pytest.mark.parametrize("method", [sim.LOTS_FIFO, sim.LOTS_HIFO])
def test_selling_the_whole_position_realizes_the_whole_gain_in_any_order(method):
    st = lot_state(OLD_LOTS, year=9, method=method)
    assert sim._lots_sell(st, 1e9, method) == pytest.approx(170_000 - 105_000)
    assert st[sim.S_BE] == 0.0 and st[sim.S_BBASIS] == 0.0 and st[sim.S_UNITS] == 0.0


@pytest.mark.parametrize("method", [sim.LOTS_FIFO, sim.LOTS_HIFO])
def test_with_one_lot_every_method_is_the_old_pro_rata_sale(method):
    one = lot_state([(100_000, 60_000)], year=3, method=method)
    average = np.zeros(sim.NSTATE)
    average[sim.S_BE], average[sim.S_BBASIS] = 100_000, 60_000
    lot_sale = sim._sell_brokerage(one, 30_000.0, 0.0)
    old_sale = sim._sell_brokerage(average, 30_000.0, 0.0)
    assert lot_sale == pytest.approx(old_sale)
    assert (one[sim.S_BE], one[sim.S_BBASIS]) == pytest.approx((average[sim.S_BE], average[sim.S_BBASIS]))


def test_a_lot_is_short_term_in_the_year_it_was_bought_half_the_next_and_long_term_after():
    for year, expected in ((1, 1.0), (2, 0.5), (3, 0.0)):  # lot 2 was bought in year 1
        st = lot_state([(100_000, 40_000), (10_000, 5_000), (10_000, 5_000)], year=year, method=sim.LOTS_HIFO)
        # HIFO takes the lots bought at the same price in index order, so make lot 2 the one that goes first
        st[sim.S_LOTC + 2] = 0.9
        gain = sim._lots_sell(st, 10_000.0, sim.LOTS_HIFO)
        assert gain == pytest.approx(1_000)
        assert st[sim.S_STACC] == pytest.approx(expected * 1_000)
    opening = lot_state([(100_000, 40_000)], year=0, method=sim.LOTS_FIFO)
    sim._lots_sell(opening, 50_000.0, sim.LOTS_FIFO)
    assert opening[sim.S_STACC] == 0.0  # the opening position is long-term


def test_short_term_gains_are_only_set_aside_when_the_policy_taxes_them():
    st = lot_state([(100_000, 40_000), (10_000, 5_000)], year=1, method=sim.LOTS_HIFO, short=False)
    assert sim._lots_sell(st, 10_000.0, sim.LOTS_HIFO) == pytest.approx(5_000)
    assert st[sim.S_STACC] == 0.0


def test_the_account_follows_its_lots_through_buys_and_sales_against_a_plain_reference():
    """Random years of growth, purchases and sales, FIFO and HIFO, against a straightforward reference."""
    rng = np.random.default_rng(5)
    for method in (sim.LOTS_FIFO, sim.LOTS_HIFO):
        st = lot_state([(300_000, 90_000)], year=0, method=method)
        ref = [[300_000.0, 0.3]]  # [units, cost per unit]; lot i is the opening position (0) or bought in year i - 1
        price = 1.0
        for year in range(30):
            st[sim.S_YEAR] = year
            growth = 1.0 + rng.normal(0.05, 0.18)
            price *= growth
            st[sim.S_PRICE] = price
            st[sim.S_BE] = price * st[sim.S_UNITS]  # what `_year_begin` does with no dividends
            if rng.random() < 0.8:
                amount = rng.uniform(0, 40_000)
                sim._lots_buy(st, amount)
                units = amount / price
                for lot in ref:
                    if len(lot) == 3 and lot[2] == year:
                        lot[1] = (lot[1] * lot[0] + amount) / (lot[0] + units)
                        lot[0] += units
                        break
                else:
                    ref.append([units, price, year])
            if rng.random() < 0.7 and st[sim.S_BE] > 0:
                amount = rng.uniform(0, 1.2 * st[sim.S_BE]) if rng.random() < 0.15 else rng.uniform(0, 0.15 * st[sim.S_BE])
                gain = sim._lots_sell(st, amount, method)
                remaining = min(amount, price * sum(lot[0] for lot in ref)) / price
                expected_gain = 0.0
                while remaining > 1e-9:
                    live = [lot for lot in ref if lot[0] > 1e-9]
                    if not live:
                        break
                    lot = live[0] if method == sim.LOTS_FIFO else max(live, key=lambda x: (x[1], -ref.index(x)))
                    take = min(lot[0], remaining)
                    expected_gain += take * (price - lot[1])
                    lot[0] -= take
                    remaining -= take
                assert gain == pytest.approx(expected_gain, abs=1e-5, rel=1e-9)
            units = sum(lot[0] for lot in ref)
            assert st[sim.S_UNITS] == pytest.approx(units, abs=1e-6, rel=1e-9)
            assert st[sim.S_BE] == pytest.approx(price * units, abs=1e-4, rel=1e-9)
            assert st[sim.S_BBASIS] == pytest.approx(sum(lot[0] * lot[1] for lot in ref), abs=1e-4, rel=1e-9)


def test_loss_harvesting_lowers_every_lots_cost_in_proportion():
    st = lot_state(OLD_LOTS, year=9, method=sim.LOTS_HIFO)
    sim._lots_set_basis(st, 52_500.0)  # half of the 105,000 basis
    assert st[sim.S_BBASIS] == pytest.approx(52_500)
    assert [st[sim.S_LOTC + i] for i in range(3)] == pytest.approx([0.2, 0.45, 0.5])


def test_realizing_gains_sells_the_cheapest_long_held_lots_and_buys_them_back_into_this_years_lot():
    st = lot_state([(100_000, 40_000), (50_000, 45_000), (20_000, 20_000)], year=9, method=sim.LOTS_HIFO)
    realized = sim._lots_realize(st, 6_000.0)
    assert realized == pytest.approx(6_000)  # from the opening position: 10,000 of it carries 6,000 of gain
    assert st[sim.S_BE] == pytest.approx(170_000)  # nothing leaves the account
    assert st[sim.S_BBASIS] == pytest.approx(105_000 + 6_000)  # only the basis steps up
    assert st[sim.S_LOTU] == pytest.approx(90_000) and st[sim.S_LOTU + 10] == pytest.approx(10_000)  # this year's lot (year 9)
    assert st[sim.S_LOTC + 10] == pytest.approx(1.0)
    # the lots held a year or less are not touched: their gains would be short-term
    recent = lot_state([(100_000, 40_000), (50_000, 20_000)], year=1, method=sim.LOTS_HIFO)
    assert sim._lots_realize(recent, 1e9) == pytest.approx(60_000)  # only the opening position's gain
    assert recent[sim.S_LOTU + 1] == pytest.approx(50_000) and recent[sim.S_LOTU] == 0.0
    assert recent[sim.S_LOTU + 2] == pytest.approx(100_000)  # bought back into this year's lot


# --- The policy -----------------------------------------------------------------------------------------


def test_policies_choose_their_lot_method():
    assert Policy().lot_method == "average" and Policy().row(40.0)[sim.SP_LOTS] == sim.LOTS_AVERAGE
    donabach = Strategy(1.0, "none", 0.0, False, False, reserve_years=2).policy()
    assert donabach.lot_method == "hifo" and donabach.short_term_ordinary
    assert donabach.row(40.0)[sim.SP_LOTS] == sim.LOTS_HIFO and donabach.row(40.0)[sim.SP_STCG] == 1.0
    for baseline in (RIA_BASELINE, TYPICAL_ADVISOR):
        assert baseline.lot_method == "fifo" and baseline.short_term_ordinary
    # short-term gains need lots to be short-term
    assert Policy(short_term_ordinary=True).row(40.0)[sim.SP_STCG] == 0.0


# --- Through the whole simulation -----------------------------------------------------------------------


def walk(inputs, policy, path=0):
    """The state after each simulated year of one path."""
    n_years = inputs.n_years
    row = policy.row(inputs.current_age)
    if sim.wants_book(row):
        st = np.zeros(sim.NSTATE_DI)
        st[: sim.NSTATE] = inputs.init
    else:
        st = inputs.init.copy()
    sim._lots_start(st, row)
    ys, act = np.zeros(sim.NY), np.zeros(sim.NACT)
    gates, scratch, log = np.ones((n_years, sim.NGATE)), np.zeros(n_years), np.zeros((n_years, sim.NLOG))
    common = (
        inputs.tv, inputs.hhc, row, gates, inputs.rets[path], inputs.wages[path], inputs.k401[path], inputs.wage_tax[path],
        inputs.stock_g[path],
    )
    for t in range(n_years):
        sim._run_years(st, ys, act, *common, t, t + 1, sim.RUN_FULL, False, False, scratch, False, log, np.zeros(1), False)
        yield t, st


POLICIES = {
    "good RIA": RIA_BASELINE,
    "typical advisor": TYPICAL_ADVISOR,
    "reserve, conversions, borrowing": Strategy(1.0, "fill24_every", 0.15, False, False, "pretax", "borrow", reserve_years=4).policy(),
    "balanced with direct indexing": Strategy(0.8, "fill22_low", 0.10, True, True).policy(),
    "balanced Roth 401(k)": Strategy(0.6, "none", 0.0, False, False, "roth").policy(),
}


@pytest.mark.parametrize("name", POLICIES)
def test_the_account_is_always_its_lots(name):
    inputs = build_inputs(make_demo_household(), n_paths=4, seed=11)
    book = sim.wants_book(POLICIES[name].row(inputs.current_age))
    for path in range(4):
        for t, st in walk(inputs, POLICIES[name], path):
            n = min(t + 2, sim.MAX_LOTS)
            if book:
                # the direct-indexing book: 100 stocks, each with its price, its units and its lots
                units = st[sim.D_LOTU : sim.D_LOTU + sim.N_STOCKS * sim.MAX_LOTS].reshape(sim.N_STOCKS, sim.MAX_LOTS)
                cost = st[sim.D_LOTC : sim.D_LOTC + sim.N_STOCKS * sim.MAX_LOTS].reshape(sim.N_STOCKS, sim.MAX_LOTS)
                price = st[sim.D_PRICE : sim.D_PRICE + sim.N_STOCKS]
                held = st[sim.D_UNITS : sim.D_UNITS + sim.N_STOCKS]
                assert (units >= -1e-9).all() and (cost >= -1e-12).all() and (price > 0).all()
                assert units[:, :n].sum(axis=1) == pytest.approx(held, abs=1e-6, rel=1e-9)
                assert st[sim.S_BE] == pytest.approx(float((price * held).sum()), abs=1e-3, rel=1e-9)
                assert st[sim.S_BBASIS] == pytest.approx(float((units * cost).sum()), abs=1e-3, rel=1e-8)
                assert not units[:, n:].any()
                assert st[sim.S_LOTS] == sim.LOTS_STOCK and st[sim.S_STACC] == 0.0
                continue
            units = st[sim.S_LOTU : sim.S_LOTU + n]
            cost = st[sim.S_LOTC : sim.S_LOTC + n]
            assert (units >= -1e-9).all() and (cost >= -1e-12).all()
            assert units.sum() == pytest.approx(st[sim.S_UNITS], abs=1e-6, rel=1e-9)
            assert st[sim.S_BE] == pytest.approx(st[sim.S_PRICE] * st[sim.S_UNITS], abs=1e-4, rel=1e-9)
            assert st[sim.S_BBASIS] == pytest.approx(float((units * cost).sum()), abs=1e-3, rel=1e-8)
            assert not st[sim.S_LOTU + n : sim.S_LOTU + sim.MAX_LOTS].any()  # nothing is held in a year that has not come
            assert not st[sim.S_LOTC + n : sim.S_LOTC + sim.MAX_LOTS].any()
            assert st[sim.S_STACC] == 0.0  # the short-term gains of a year's sales are all in its return or deferred


def test_the_average_method_keeps_no_lots():
    inputs = build_inputs(make_demo_household(), n_paths=1, seed=11)
    legacy = RIA_BASELINE.replace(lot_method="average", short_term_ordinary=False)
    for _, st in walk(inputs, legacy):
        assert st[sim.S_LOTS] == 0.0 and not st[sim.S_LOTU :].any() and st[sim.S_STACC] == 0.0 and st[sim.S_DGAIN_ST] == 0.0


def test_short_term_gains_reach_the_log_and_the_year_s_tax_return():
    from app.planner import explain

    strategies = [
        Strategy(1.0, "fill24_every", 0.15, False, False, reserve_years=6),
        Strategy(1.0, "none", 0.0, False, False),
        Strategy(0.8, "none", 0.0, True, False),  # direct indexing: harvested losses often absorb the short-term gains
    ]
    inputs = build_inputs(make_demo_household(), deterministic=True)
    taxed_as_ordinary = 0.0
    for strategy in strategies:
        log = run_detail(inputs, strategy.policy()).log
        for t in np.flatnonzero(np.abs(log["short_term_gain"]) > 1.0):
            ret = explain.tax_return_for_year(log, int(t))
            assert ret.grand_total == pytest.approx(log["total_tax"][t], rel=1e-9, abs=1e-6)  # the rebuilt return is the simulator's tax
            taxed_as_ordinary = max(taxed_as_ordinary, ret.short_term_gain_ordinary)
    assert taxed_as_ordinary > 0


def test_a_large_embedded_gain_makes_highest_cost_first_pay_less_tax_than_first_in_first_out():
    inputs = build_inputs(make_demo_household(), n_paths=120, seed=21)
    inputs.init[sim.S_BE], inputs.init[sim.S_BBASIS] = 600_000.0, 120_000.0
    donabach = Strategy(0.8, "none", 0.0, False, False).policy()
    results = {m: run_batch(inputs, [donabach.replace(lot_method=m)]) for m in ("fifo", "hifo")}
    taxes = {m: float(np.median(r.taxes_paid)) for m, r in results.items()}
    wealth = {m: float(np.median(r.wealth)) for m, r in results.items()}
    assert taxes["hifo"] < taxes["fifo"] and wealth["hifo"] > wealth["fifo"]


def test_short_term_gains_cost_something_to_a_strategy_that_sells_recent_lots():
    inputs = build_inputs(make_demo_household(), n_paths=120, seed=21)
    policy = Strategy(0.8, "none", 0.0, False, False).policy()  # no direct indexing: its harvested lots carry no gain to tax
    taxed = run_batch(inputs, [policy])
    free = run_batch(inputs, [policy.replace(short_term_ordinary=False)])
    assert np.mean(taxed.taxes_paid) > np.mean(free.taxes_paid)  # (the means: the two medians can fall on the same path and tie)
    assert np.mean(taxed.wealth) < np.mean(free.wealth)


def test_a_young_household_has_a_lot_for_every_year():
    young = make_demo_household().model_copy(deep=True)
    for person in young.people:
        person.age = 18
    inputs = build_inputs(young, n_paths=2, seed=1)
    assert inputs.n_years + 1 <= sim.MAX_LOTS
    for _ in walk(inputs, POLICIES["balanced with direct indexing"]):
        pass
