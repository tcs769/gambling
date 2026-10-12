"""The direct-indexing book: 100 synthetic stocks, each with its own tax lots (`app.sim.stocks`).

The kernel is checked against a plain reference written lot by lot (`Book`), against the market (the sleeve earns the market's
price return whatever the stocks do), and, through the whole simulation, against the fund's lots (`tests/test_lots.py`).
"""

from __future__ import annotations

import numpy as np
import pytest
from app.planner.strategies import Strategy
from app.sim import simulate as sim
from app.sim import stocks
from app.sim.simulate import ModelOptions, build_inputs, run_batch
from app.sim.state import (
    D_LOTC,
    D_LOTU,
    D_PRICE,
    D_UNITS,
    DI_BUCKETS,
    DI_GMIN,
    MAX_LOTS,
    N_STOCKS,
    NSTATE_DI,
    S_BBASIS,
    S_BE,
    S_LOTS,
    S_STACC,
    S_STCG,
    S_YEAR,
)

from tests.conftest import make_demo_household

N = N_STOCKS
BIN = (1.0 - DI_GMIN) / DI_BUCKETS  # the width of a bin of gain per dollar
DIV = 0.018


def opened(value=600_000.0, basis=200_000.0, year=0, short_term=False):
    st = np.zeros(NSTATE_DI)
    st[S_BE], st[S_BBASIS] = value, basis
    stocks.di_start(st)
    st[S_YEAR] = year
    st[S_STCG] = float(short_term)
    return st


def lots(st):
    """(prices, units by stock, lot units, lot costs) of the book in `st`, as arrays."""
    u = st[D_LOTU : D_LOTU + N * MAX_LOTS].reshape(N, MAX_LOTS).copy()
    c = st[D_LOTC : D_LOTC + N * MAX_LOTS].reshape(N, MAX_LOTS).copy()
    return st[D_PRICE : D_PRICE + N].copy(), st[D_UNITS : D_UNITS + N].copy(), u, c


def consistent(st, year):
    """The book's own books: units, value and basis are the sums of the lots; nothing is held in a year that has not come."""
    price, held, u, c = lots(st)
    n = min(year + 2, MAX_LOTS)
    assert (u >= 0).all() and (price > 0).all()
    assert u[:, :n].sum(axis=1) == pytest.approx(held, rel=1e-9, abs=1e-9)
    assert st[S_BE] == pytest.approx(float((price * held).sum()), rel=1e-9, abs=1e-6)
    assert st[S_BBASIS] == pytest.approx(float((u * c).sum()), rel=1e-9, abs=1e-6)
    assert not u[:, n:].any()


def movements(rng, vol=0.30):
    return np.exp(vol * rng.standard_normal(N) - 0.5 * vol * vol).astype(np.float32)


class Book:
    """The same rules, written plainly: a list of [year-bought index, units, cost] lots for each stock."""

    def __init__(self, st):
        price, _, u, c = lots(st)
        self.price = list(price)
        self.lots = [[[tau, u[i, tau], c[i, tau]] for tau in range(MAX_LOTS) if u[i, tau] > 0] for i in range(N)]

    def value(self):
        return sum(p * sum(l[1] for l in ls) for p, ls in zip(self.price, self.lots, strict=True))

    def basis(self):
        return sum(l[1] * l[2] for ls in self.lots for l in ls)

    def year_begin(self, t, price_rel, g, theta, harvest):
        weights = [p * sum(l[1] for l in ls) for p, ls in zip(self.price, self.lots, strict=True)]
        v = sum(weights)
        scale = v / sum(w * gi for w, gi in zip(weights, g, strict=True))
        loss = loss_short = 0.0
        for i in range(N):
            old = self.price[i]
            units = sum(l[1] for l in self.lots[i])
            new = old * price_rel * float(g[i]) * scale
            self.price[i] = new
            self.lots[i].append([t + 1, DIV * units * old / new, new])  # the dividend, bought back at the new price
        if harvest:
            for i in range(N):
                price = self.price[i]
                moved = 0.0
                for lot in self.lots[i]:
                    if lot[0] <= t and lot[1] > 1e-12 and lot[2] > price * (1.0 + theta):
                        amount = lot[1] * (lot[2] - price)
                        loss += amount
                        loss_short += stocks.lot_short_share(lot[0], t) * amount
                        moved += lot[1]
                        lot[1] = 0.0
                this_year = next(l for l in self.lots[i] if l[0] == t + 1)
                this_year[1] += moved
        return loss, loss_short


def test_the_book_opens_as_the_opening_position_spread_equally_over_the_stocks():
    st = opened(600_000.0, 200_000.0)
    price, held, u, c = lots(st)
    assert st[S_LOTS] == sim.LOTS_STOCK
    assert (price == 1.0).all() and held == pytest.approx(np.full(N, 6_000.0))
    assert u[:, 0] == pytest.approx(np.full(N, 6_000.0)) and c[:, 0] == pytest.approx(np.full(N, 200_000.0 / 600_000.0))
    assert not u[:, 1:].any()
    consistent(st, 0)
    empty = opened(0.0, 0.0)  # a household with no brokerage stock still has a book (for what it buys later)
    consistent(empty, 0)


def test_the_sleeve_earns_exactly_the_market_s_price_return_whatever_the_stocks_do():
    rng = np.random.default_rng(3)
    st = opened()
    stocks.di_buy(st, 40_000.0)
    for year in range(1, 30):
        st[S_YEAR] = year
        before = st[S_BE]
        r_e = float(rng.normal(0.055, 0.16))
        stocks.di_year_begin(st, year, 1.0 + r_e - DIV, movements(rng), DIV, 0.01, True)
        st[S_BBASIS] += DIV * before
        assert st[S_BE] == pytest.approx(before * (1.0 + r_e), rel=1e-12)  # the stocks net to the market, to the cent
        consistent(st, year)
        stocks.di_buy(st, 10_000.0)


def test_the_stocks_move_against_each_other_with_the_published_volatility():
    rng = np.random.default_rng(4)
    st = opened()
    logs = []
    for year in range(1, 60):
        old = st[D_PRICE : D_PRICE + N].copy()
        stocks.di_year_begin(st, min(year, MAX_LOTS - 2), 1.04, movements(rng, 0.30), DIV, 0.01, False)
        logs.append(np.log(st[D_PRICE : D_PRICE + N] / old))
    spread = float(np.std(np.concatenate(logs)))
    assert spread == pytest.approx(0.30, abs=0.015)  # a stock's own movement is the volatility the inputs draw (0.30)


def evolve(st, rng, years, start=1, harvest=True, buy=15_000.0, mean=0.04, vol=0.12):
    """Run `years` years of the book the way the simulator does (prices and dividends, harvest, then new money); returns the next year."""
    for year in range(start, start + years):
        st[S_YEAR] = year
        before = st[S_BE]
        stocks.di_year_begin(st, year, 1.0 + float(rng.normal(mean, vol)) - DIV, movements(rng), DIV, 0.01, harvest)
        st[S_BBASIS] += DIV * before  # the simulator books the dividends into the basis
        stocks.di_buy(st, buy)
    return start + years


@pytest.mark.parametrize("harvest", [False, True])
def test_a_year_begins_as_the_plain_reference_says(harvest):
    rng = np.random.default_rng(5)
    st = opened(900_000.0, 300_000.0)
    for year in range(1, 25):
        st[S_YEAR] = year
        before = Book(st)
        opening_value, opening_basis = before.value(), before.basis()
        g = movements(rng)
        price_rel = 1.0 + float(rng.normal(0.04, 0.17)) - DIV
        loss, short = stocks.di_year_begin(st, year, price_rel, g, DIV, 0.01, harvest)
        want_loss, want_short = before.year_begin(year, price_rel, g, 0.01, harvest)
        assert loss == pytest.approx(want_loss, rel=1e-9, abs=1e-6) and short == pytest.approx(want_short, rel=1e-9, abs=1e-6)
        assert st[S_BE] == pytest.approx(opening_value * (price_rel + DIV), rel=1e-12)
        assert st[S_BBASIS] == pytest.approx(opening_basis - loss, rel=1e-12)  # the harvest lowers the basis; the caller adds the dividends
        price, _, u, c = lots(st)
        for i in range(N):
            assert price[i] == pytest.approx(before.price[i], rel=1e-9)
            ref = {tau: (units, cost) for tau, units, cost in before.lots[i] if units > 1e-12}
            mine = {tau: (u[i, tau], c[i, tau]) for tau in range(MAX_LOTS) if u[i, tau] > 1e-12}
            assert mine.keys() == ref.keys()
            for tau in ref:
                assert mine[tau][0] == pytest.approx(ref[tau][0], rel=1e-9) and mine[tau][1] == pytest.approx(ref[tau][1], rel=1e-9)
        st[S_BBASIS] += DIV * opening_value
        consistent(st, year)
        stocks.di_buy(st, 20_000.0)


def test_harvesting_sells_only_the_lots_that_cost_more_than_the_price_and_keeps_the_shares():
    st = opened(1_000_000.0, 1_000_000.0)  # everything bought at today's price: any fall is a loss
    held = lots(st)[1]
    g = np.where(np.arange(N) < 50, 0.7, 1.3).astype(np.float32)  # half the stocks fall 30% against the market, half rise 30%
    loss, _ = stocks.di_year_begin(st, 1, 1.0 - DIV, g, DIV, 0.01, True)  # the market is flat in total return
    price, units, u, c = lots(st)
    fell = np.arange(N) < 50
    assert price == pytest.approx((1.0 - DIV) * g)  # the weighted mean of g is 1: the market's part is untouched
    assert loss == pytest.approx(float((held[fell] * (1.0 - price[fell])).sum()), rel=1e-9)
    assert not u[fell, 0].any() and (u[~fell, 0] > 0).all()  # the stocks that fell lost their opening lot; those that rose keep it
    assert units == pytest.approx(held + DIV * held / price, rel=1e-12)  # the shares are the same, plus the dividends' shares
    assert u[fell, 2] == pytest.approx(held[fell] + DIV * held[fell] / price[fell], rel=1e-12)  # held again, as this year's lot (year 1: lot 2)
    assert c[fell, 2] == pytest.approx(price[fell])  # at today's price
    st[S_BBASIS] += DIV * 1_000_000.0
    consistent(st, 1)


def test_a_stock_is_harvested_only_for_losses_beyond_the_threshold():
    g = np.ones(N, dtype=np.float32)
    for price_rel, loss in ((1.0, 0.0), (0.995, 0.0), (0.97, 0.03 * 100_000.0)):  # the price falls 0%, 0.5% (under the 1% threshold), 3%
        st = opened(100_000.0, 100_000.0)  # everything bought at today's price
        assert stocks.di_year_begin(st, 1, price_rel, g, 0.0, 0.01, True)[0] == pytest.approx(loss, rel=1e-9, abs=1e-9)


def test_with_no_dispersion_the_book_harvests_what_a_fund_with_those_lots_would():
    # one purchase every year at the market, no stock moving on its own: the book is 100 copies of a fund, and its harvest is
    # the fund's loss on every lot bought above today's price
    st = opened(0.0, 0.0)
    price_path = [0.9, 1.1, 1.0, 1.2, 0.95]
    fund_lots: list[tuple[float, float]] = []  # (value units, cost)
    g = np.ones(N, dtype=np.float32)
    level = 1.0
    for year, rel in enumerate(price_path):
        st[S_YEAR] = year
        level *= rel
        loss, _ = stocks.di_year_begin(st, year, rel, g, 0.0, 0.0, True)
        # a fund's lots: units and cost; its harvest sells every lot above the price
        want = sum(units * (cost - level) for units, cost in fund_lots if cost > level + 1e-12)
        fund_lots = [(units, level if cost > level + 1e-12 else cost) for units, cost in fund_lots]
        assert loss == pytest.approx(want, rel=1e-9, abs=1e-9)
        stocks.di_buy(st, 10_000.0)
        fund_lots.append((10_000.0 / level, level))


def begun(st, rng, year, harvest=False, mean=0.03, vol=0.12):
    """Start `year`: prices move and dividends are reinvested (and losses harvested, if `harvest`); the dividends go into the basis."""
    st[S_YEAR] = year
    before = st[S_BE]
    stocks.di_year_begin(st, year, 1.0 + float(rng.normal(mean, vol)) - DIV, movements(rng), DIV, 0.01, harvest)
    st[S_BBASIS] += DIV * before


def reference_sale(amount, price, u, c, last, first_lot=None):
    """The gain of selling `amount` the plain way: `first_lot` (a lot index with no gain) first if given, then lots 0 .. last - 1 by
    gain per dollar, lowest first."""
    remaining = amount
    gain = 0.0
    if first_lot is not None:
        remaining -= min(amount, float((u[:, first_lot] * price).sum()))
    order = sorted(
        ((1.0 - c[i, tau] / price[i], i, tau) for i in range(N) for tau in range(last) if u[i, tau] > 1e-12), key=lambda x: x[0]
    )
    for ratio, i, tau in order:
        if remaining <= 1e-9:
            break
        sold = min(u[i, tau] * price[i], remaining)
        gain += sold * ratio
        remaining -= sold
    return gain


def test_in_a_year_that_harvests_a_sale_takes_this_years_lot_first_then_the_least_gain_per_dollar():
    rng = np.random.default_rng(6)
    st = opened(600_000.0, 150_000.0)
    year = evolve(st, rng, 11)
    begun(st, rng, year, harvest=True)
    price, held, u, c = lots(st)
    k = year + 1
    this_year_value = float((u[:, k] * price).sum())
    assert this_year_value > 0
    for amount, label in ((0.5 * this_year_value, "less than this year's lot"), (this_year_value + 80_000.0, "past this year's lot")):
        trial = st.copy()
        gain = stocks.di_sell(trial, amount)
        want = reference_sale(amount, price, u, c, k, first_lot=k)
        assert gain == pytest.approx(want, abs=amount * BIN + 1e-6), label  # within the width of a bin of gain per dollar
        assert trial[S_BE] == pytest.approx(st[S_BE] - amount, rel=1e-9)
        consistent(trial, year)
        _, _, u2, _ = lots(trial)
        sold_ratios = [1.0 - c[i, tau] / price[i] for i in range(N) for tau in range(k) if u2[i, tau] < u[i, tau] - 1e-9]
        kept_ratios = [1.0 - c[i, tau] / price[i] for i in range(N) for tau in range(k) if u2[i, tau] > 1e-9 and u2[i, tau] >= u[i, tau] - 1e-9]
        if amount > this_year_value:
            assert sold_ratios and kept_ratios and max(sold_ratios) <= min(kept_ratios) + BIN  # nothing sold has more gain per dollar than what is kept


def test_in_a_year_that_does_not_harvest_a_sale_is_exactly_highest_cost_first_losses_included():
    rng = np.random.default_rng(16)
    st = opened(600_000.0, 150_000.0)
    year = evolve(st, rng, 11, harvest=False)
    begun(st, rng, year, harvest=False, mean=-0.10)  # a bad year, with no harvest: lots bought dearer than today's price carry losses
    price, held, u, c = lots(st)
    k = year + 1
    assert (c[:, : k + 1][u[:, : k + 1] > 0] > np.repeat(price[:, None], k + 1, axis=1)[u[:, : k + 1] > 0]).any()  # some lots have losses
    for amount in (20_000.0, 90_000.0):
        trial = st.copy()
        gain = stocks.di_sell(trial, amount)
        want = reference_sale(amount, price, u, c, k + 1)  # this year's lot is one of the lots, with no gain
        assert gain == pytest.approx(want, abs=amount * BIN + 1e-6)
        assert gain < 0  # the lots with the biggest losses went first
        consistent(trial, year)


def test_selling_everything_realizes_the_whole_unrealized_gain_and_empties_the_book():
    rng = np.random.default_rng(7)
    st = opened(500_000.0, 150_000.0)
    evolve(st, rng, 8, harvest=False, buy=20_000.0, mean=0.05, vol=0.14)
    value, basis = st[S_BE], st[S_BBASIS]
    gain = stocks.di_sell(st, value * 2.0)  # more than there is
    assert gain == pytest.approx(value - basis, rel=1e-9)
    assert st[S_BE] == 0.0 and st[S_BBASIS] == 0.0


def test_the_short_term_part_of_a_gain_follows_the_age_of_the_lot_sold():
    st = opened(0.0, 0.0, short_term=True)
    g = np.ones(N, dtype=np.float32)
    stocks.di_buy(st, 100_000.0)  # year 0: lot 1
    st[S_YEAR] = 1
    stocks.di_year_begin(st, 1, 1.20, g, 0.0, 0.01, False)  # +20%: the year-0 lot is a year old
    gain = stocks.di_sell(st, 60_000.0)
    # 60,000 of value with a 20/120 = 1/6 gain per dollar, in a lot of age one (half short-term)
    assert gain == pytest.approx(60_000.0 / 6.0, rel=1e-9)
    assert st[S_STACC] == pytest.approx(0.5 * gain, rel=1e-9)
    st[S_STACC] = 0.0
    st[S_YEAR] = 2
    stocks.di_year_begin(st, 2, 1.0, g, 0.0, 0.01, False)  # the lot is now older than a year: long-term
    gain = stocks.di_sell(st, 30_000.0)
    assert gain > 0 and st[S_STACC] == 0.0
    # a lot sold in the year it was bought has no gain, so nothing is short-term
    st[S_YEAR] = 3
    stocks.di_year_begin(st, 3, 1.0, g, 0.0, 0.01, False)
    stocks.di_buy(st, 10_000.0)
    stocks.di_sell(st, 5_000.0)
    assert st[S_STACC] == pytest.approx(0.0, abs=1e-9)


def test_buying_spreads_the_money_equally_over_the_stocks_into_this_years_lot():
    rng = np.random.default_rng(8)
    st = opened(300_000.0, 100_000.0)
    stocks.di_year_begin(st, 1, 1.05, movements(rng), DIV, 0.01, False)
    st[S_YEAR] = 1
    value, basis = st[S_BE], st[S_BBASIS]
    price, _, u0, _ = lots(st)
    stocks.di_buy(st, 50_000.0)
    price, _, u, c = lots(st)
    bought = (u[:, 2] - u0[:, 2]) * price
    assert bought == pytest.approx(np.full(N, 500.0), rel=1e-9)
    assert c[:, 2] == pytest.approx(price)
    assert st[S_BE] == pytest.approx(value + 50_000.0) and st[S_BBASIS] == pytest.approx(basis + 50_000.0)


def test_realizing_gains_raises_the_cost_of_the_most_appreciated_old_lots_and_moves_them_to_this_year():
    rng = np.random.default_rng(9)
    st = opened(400_000.0, 100_000.0)
    year = evolve(st, rng, 5, buy=10_000.0, mean=0.05, vol=0.10)
    begun(st, rng, year)
    basis, value = st[S_BBASIS], st[S_BE]
    realized = stocks.di_realize(st, 25_000.0)
    assert realized == pytest.approx(25_000.0, rel=1e-9)
    assert st[S_BBASIS] == pytest.approx(basis + realized, rel=1e-9) and st[S_BE] == pytest.approx(value)  # the value did not move
    consistent(st, year)
    price, _, u, c = lots(st)
    assert (np.abs(c[:, year + 1] - price)[u[:, year + 1] > 0] < 1e-12).all()
    assert stocks.di_realize(st, 1e12) > 0  # what long-held gain is left
    assert stocks.di_realize(st, 1e12) == pytest.approx(0.0, abs=1e-6)  # and then there is none


def test_donating_gives_the_lots_with_the_most_gain_and_realizes_nothing():
    rng = np.random.default_rng(10)
    st = opened(400_000.0, 80_000.0)
    year = evolve(st, rng, 5, buy=10_000.0, mean=0.05, vol=0.10)
    begun(st, rng, year)
    value, basis = st[S_BE], st[S_BBASIS]
    given = stocks.di_donate(st, 50_000.0)
    assert given == pytest.approx(50_000.0, rel=1e-9) and st[S_BE] == pytest.approx(value - given)
    gain_given = given - (basis - st[S_BBASIS])
    assert gain_given > 0.5 * given  # the cheapest shares: most of what was given was gain, none of which is ever taxed
    consistent(st, year)
    stocks.di_donate(st, 1e12)  # everything that can be given
    _, _, u, _ = lots(st)
    assert (u[:, year] > 0).any() and (u[:, year + 1] > 0).any()  # stock held a year or less cannot be given: it stays


# --- In the whole simulation ------------------------------------------------------------------------


def test_a_policy_that_does_not_direct_index_never_needs_the_book():
    policy = Strategy(0.8, "none", 0.0, False, False).policy()
    assert not sim.wants_book(policy.row(40.0))
    assert sim.wants_book(policy.replace(direct_indexing=True).row(40.0))
    assert not sim.wants_book(policy.replace(direct_indexing=True, di_model="aggregate").row(40.0))
    assert not sim.wants_book(policy.replace(direct_indexing=True, lot_method="average").row(40.0))  # no lots: the aggregate rule


def test_without_dispersion_and_without_harvesting_the_book_is_the_fund_s_highest_cost_first_lots():
    inputs = build_inputs(make_demo_household(), n_paths=40, seed=12, options=ModelOptions(idio_vol=0.0))
    base = Strategy(0.8, "none", 0.0, False, False).policy().replace(tax_loss_harvesting=False)
    fund = run_batch(inputs, [base]).wealth[0]
    book = run_batch(inputs, [base.replace(direct_indexing=True)]).wealth[0]
    # 100 identical stocks are one fund; the only differences are this year's lot going first and a bin's width of gain
    assert book == pytest.approx(fund, rel=2e-3)


def test_direct_indexing_with_dispersion_harvests_losses_the_fund_cannot():
    inputs = build_inputs(make_demo_household(), n_paths=120, seed=13)
    base = Strategy(0.8, "none", 0.0, False, False).policy()
    fund = run_batch(inputs, [base])
    book = run_batch(inputs, [base.replace(direct_indexing=True)])
    assert np.median(book.taxes_paid) < np.median(fund.taxes_paid)
    assert np.median(book.wealth) > np.median(fund.wealth)


def test_the_idiosyncratic_volatility_is_the_one_the_futures_are_drawn_with():
    inputs = build_inputs(make_demo_household(), n_paths=300, seed=14, options=ModelOptions(idio_vol=0.25))
    z = np.log(inputs.stock_g.astype(np.float64)) + 0.5 * 0.25**2
    assert z.std() == pytest.approx(0.25, rel=0.02) and inputs.stock_g.mean() == pytest.approx(1.0, abs=0.002)
    assert inputs.stock_g.shape == (300, inputs.n_years, N) and inputs.stock_g.dtype == np.float32
    same = build_inputs(make_demo_household(), n_paths=300, seed=14, options=ModelOptions(idio_vol=0.25))
    assert np.array_equal(inputs.stock_g, same.stock_g) and np.array_equal(inputs.rets, same.rets)  # the same futures every time
    # the returns and incomes are the ones they were before the stocks existed: their streams are untouched
    plain = build_inputs(make_demo_household(), n_paths=300, seed=14)
    assert np.array_equal(plain.rets, inputs.rets) and np.array_equal(plain.wages, inputs.wages)
