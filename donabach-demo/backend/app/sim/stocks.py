"""A direct-indexed brokerage sleeve: 100 synthetic stocks, each with its own tax lots.

The aggregate rule it replaces said that a direct-indexed account harvests 85% of an equity decline plus a flat 3% "dispersion"
harvest each year. Here the dispersion is simulated. The brokerage equity is `N_STOCKS` stocks. Every year a stock's price
moves with the market and with a movement of its own, `g` (a lognormal draw with mean 1 and the idiosyncratic volatility
of `markets.STOCK_IDIO_VOL`), scaled so that the sleeve as a whole earns exactly the market's price return: the stocks move
against each other, never the sleeve against the market. Each stock keeps its lots, by the year they were bought (or last
harvested); a lot has units and a cost per unit.

* Dividends are paid by every stock at the portfolio's yield and bought back at the new price: a new lot in every stock.
* Harvesting. At the start of the year, after prices move, every lot whose cost is more than `theta` above its stock's
  price is sold at a loss and the same shares are held again as this year's lot at today's price. The model has one step a
  year, so the 31-day wash-sale window is not played out: the proceeds are taken to sit in a substitute with the stock's
  market return and to return to the stock afterwards, which restarts the holding period. The basis falls by the loss.
* Buying spreads the money equally over the stocks, into this year's lot.
* Selling takes the lots with the least gain per dollar first (the highest cost relative to price): lots are sorted into bins
  of gain per dollar and the sale stops in the bin where the money runs out, pro rata within it (a bin is 0.4 points of gain
  per dollar wide). In a year that harvests, this year's lot goes first without any sorting: it has no gain at all (its cost
  is today's price) and every lot with a loss of more than the threshold has been harvested, so nothing else is better than
  it by more than the threshold (the sale gives up at most the threshold times its size in realized loss).
* Realizing gains (the 0% bracket) takes the lots with the most gain per dollar that have been held over a year and
  buys the shares back at once, which raises their cost to today's price.
* Donating takes the same lots, the most gain per dollar (only lots with a gain), and gives the shares away: no gain is realized.

A lot's short-term share is by its age, as for the fund's lots (`lot_short_share`).
"""

from __future__ import annotations

import numpy as np

from app.jit import jit
from app.sim.state import (
    D_LIST,
    D_LOTC,
    D_LOTU,
    D_MAXC,
    D_NLOTS,
    D_PRICE,
    D_UNITS,
    DI_BUCKETS,
    DI_GMIN,
    LOTS_STOCK,
    MAX_LOTS,
    N_STOCKS,
    S_BBASIS,
    S_BE,
    S_BEST,
    S_LOTS,
    S_STACC,
    S_STCG,
    S_YEAR,
)

_INV_BIN = DI_BUCKETS / (1.0 - DI_GMIN)
_TINY = 1e-12
_EMPTY = 1e-6  # a book worth less than this (in dollars) is empty: what is left is rounding


@jit(inline="always")
def lot_short_share(lot, year):
    """The share of a gain on `lot` that is short-term when it is sold in `year`: none for the opening position, all of it in
    the year the lot was bought, half the year after (purchases and sales are spread through a year, so a lot sold the next
    year has been held more than a year half the time), none after that."""
    if lot == 0:
        return 0.0
    age = year - (lot - 1)
    if age <= 0:
        return 1.0
    if age == 1:
        return 0.5
    return 0.0


@jit(inline="always")
def _bin(gain_per_dollar):
    b = int((gain_per_dollar - DI_GMIN) * _INV_BIN)
    return min(max(b, 0), DI_BUCKETS - 1)


@jit(inline="always")
def _list_add(st, i, tau):
    """Put lot `tau` of stock `i` on its list unless it is the last entry (a lot is opened in the year it is first needed, and the
    years only go up, so the list stays in ascending order and the newest lot is last)."""
    n = int(st[D_NLOTS + i])
    base = D_LIST + i * MAX_LOTS
    if n > 0 and int(st[base + n - 1]) == tau:
        return
    st[base + n] = tau
    st[D_NLOTS + i] = n + 1


@jit
def di_start(st):
    """Open the book: the whole opening brokerage equity position, spread equally over the stocks, as lot 0 at the position's
    average cost (long-term). Every stock starts at a price of 1."""
    value = st[S_BE]
    cost = st[S_BBASIS] / value if value > 0.0 else 1.0
    units = value / N_STOCKS
    for i in range(N_STOCKS):
        st[D_PRICE + i] = 1.0
        st[D_UNITS + i] = units
        st[D_MAXC + i] = cost
        st[D_LOTU + i * MAX_LOTS] = units
        st[D_LOTC + i * MAX_LOTS] = cost
        st[D_LIST + i * MAX_LOTS] = 0.0
        st[D_NLOTS + i] = 1.0
    st[S_LOTS] = LOTS_STOCK
    st[S_BEST] = -1.0


@jit
def di_year_begin(st, t, price_rel, g, div_yield, theta, harvest):
    """The year's price moves, dividends, and (if `harvest`) the harvest of losses. `price_rel` is the market's price relative
    (1 + the return - the dividend yield), `g` each stock's own movement (mean 1). Returns the loss harvested and its
    short-term part; `S_BE` is updated and `S_BBASIS` is lowered by the loss (the caller adds the dividends to the basis)."""
    value = 0.0
    weighted = 0.0
    for i in range(N_STOCKS):
        pv = st[D_PRICE + i] * st[D_UNITS + i]
        value += pv
        weighted += pv * g[i]
    if value > _EMPTY and weighted > 0.0:
        scale = value / weighted
    else:
        # an empty book still has prices (for what is bought later): its stocks are weighted equally
        total = 0.0
        for i in range(N_STOCKS):
            total += g[i]
        scale = N_STOCKS / total
    new_value = 0.0
    for i in range(N_STOCKS):
        old = st[D_PRICE + i]
        units = st[D_UNITS + i]
        price = old * price_rel * g[i] * scale
        st[D_PRICE + i] = price
        extra = div_yield * units * old / price  # the dividend, bought back at the new price: this year's lot
        slot = i * MAX_LOTS + t + 1
        st[D_LOTU + slot] = extra
        st[D_LOTC + slot] = price
        if extra > _TINY:
            _list_add(st, i, t + 1)
        st[D_UNITS + i] = units + extra
        if price > st[D_MAXC + i]:
            st[D_MAXC + i] = price
        new_value += price * (units + extra)
    st[S_BE] = new_value

    loss_total = 0.0
    loss_short = 0.0
    st[S_BEST] = theta if harvest else -1.0  # the threshold in force this year, or -1: losses are not harvested (see di_sell)
    if harvest:
        for i in range(N_STOCKS):
            price = st[D_PRICE + i]
            limit = price * (1.0 + theta)
            if st[D_MAXC + i] <= limit:
                continue
            row = i * MAX_LOTS
            base = D_LIST + row
            moved = 0.0
            highest = price
            kept = 0
            for j in range(int(st[D_NLOTS + i])):
                tau = int(st[base + j])
                u = st[D_LOTU + row + tau]
                if u <= _TINY:
                    continue  # sold out: off the list
                c = st[D_LOTC + row + tau]
                if c > limit:
                    loss = u * (c - price)
                    loss_total += loss
                    loss_short += lot_short_share(tau, t) * loss
                    moved += u
                    st[D_LOTU + row + tau] = 0.0
                    continue  # harvested: off the list
                if c > highest:
                    highest = c
                st[base + kept] = tau
                kept += 1
            st[D_NLOTS + i] = kept
            if moved > 0.0:
                st[D_LOTU + row + t + 1] += moved  # the same shares, held again from today at today's price
                _list_add(st, i, t + 1)
            st[D_MAXC + i] = highest
        st[S_BBASIS] -= loss_total
    return loss_total, loss_short


@jit
def di_buy(st, amount):
    """Buy `amount` of stock, the same dollars of each stock, into this year's lot."""
    if amount <= 0.0:
        return
    year = int(st[S_YEAR])
    k = min(year + 1, MAX_LOTS - 1)
    each = amount / N_STOCKS
    for i in range(N_STOCKS):
        price = st[D_PRICE + i]
        slot = i * MAX_LOTS + k
        st[D_LOTU + slot] += each / price
        st[D_LOTC + slot] = price
        _list_add(st, i, k)
        st[D_UNITS + i] += each / price
        if price > st[D_MAXC + i]:
            st[D_MAXC + i] = price
    st[S_BE] += amount
    st[S_BBASIS] += amount


@jit
def di_sell(st, amount):
    """Sell `amount` of stock, the lots with the least gain per dollar first. Returns the realized gain; its short-term part,
    when the policy taxes short-term gains as ordinary income, is added to `S_STACC`."""
    value = st[S_BE]
    if amount <= 0.0 or value <= 0.0:
        return 0.0
    remaining = min(amount, value)
    year = int(st[S_YEAR])
    k = min(year + 1, MAX_LOTS - 1)
    short_on = st[S_STCG] > 0.5
    gain = 0.0
    sold_value = 0.0
    sold_basis = 0.0

    # In a year that harvests, this year's lot goes first: it has no gain (its cost is today's price) and no lot has a loss of
    # more than the threshold. Otherwise every lot, this year's too, takes its place in the sort below.
    first = st[S_BEST] >= 0.0
    last = k if first else k + 1  # the lots the sort covers: 0 .. last - 1
    here = 0.0
    if first:
        for i in range(N_STOCKS):
            here += st[D_LOTU + i * MAX_LOTS + k] * st[D_PRICE + i]
    if here > 0.0:
        share = min(1.0, remaining / here)
        for i in range(N_STOCKS):
            slot = D_LOTU + i * MAX_LOTS + k
            take = share * st[slot]
            st[slot] = max(0.0, st[slot] - take)
            st[D_UNITS + i] = max(0.0, st[D_UNITS + i] - take)
        sold_value += share * here
        sold_basis += share * here
        remaining -= share * here

    if remaining > 1e-9:
        bins = np.zeros(DI_BUCKETS)
        for i in range(N_STOCKS):
            price = st[D_PRICE + i]
            inv = 1.0 / price
            row = i * MAX_LOTS
            base = D_LIST + row
            kept = 0
            for j in range(int(st[D_NLOTS + i])):
                tau = int(st[base + j])
                u = st[D_LOTU + row + tau]
                if u <= _TINY:
                    continue  # sold out: off the list
                st[base + kept] = tau
                kept += 1
                if tau < last:
                    bins[_bin(1.0 - st[D_LOTC + row + tau] * inv)] += u * price
            st[D_NLOTS + i] = kept
        below = 0.0
        stop = DI_BUCKETS - 1
        for b in range(DI_BUCKETS):
            if below + bins[b] >= remaining:
                stop = b
                break
            below += bins[b]
        partial = 0.0
        if bins[stop] > 0.0:
            partial = min(1.0, max(0.0, (remaining - below) / bins[stop]))
        for i in range(N_STOCKS):
            price = st[D_PRICE + i]
            inv = 1.0 / price
            row = i * MAX_LOTS
            base = D_LIST + row
            for j in range(int(st[D_NLOTS + i])):
                tau = int(st[base + j])
                if tau >= last:
                    continue
                u = st[D_LOTU + row + tau]
                if u <= _TINY:
                    continue
                cost = st[D_LOTC + row + tau]
                b = _bin(1.0 - cost * inv)
                if b > stop:
                    continue
                take = u if b < stop else partial * u
                if take <= 0.0:
                    continue
                st[D_LOTU + row + tau] = max(0.0, u - take)
                st[D_UNITS + i] = max(0.0, st[D_UNITS + i] - take)
                g = take * (price - cost)
                gain += g
                if short_on:
                    st[S_STACC] += lot_short_share(tau, year) * g
                sold_value += take * price
                sold_basis += take * cost
    st[S_BE] -= sold_value
    st[S_BBASIS] -= sold_basis
    if st[S_BE] < 1e-9:
        st[S_BE] = 0.0
        st[S_BBASIS] = 0.0
    return gain


@jit
def di_realize(st, room):
    """Realize up to `room` of gain in lots held more than a year (long-term): the lots with the most gain per dollar are sold and
    bought back at once, so their cost rises to today's price and they become this year's lot. Returns the gain realized."""
    year = int(st[S_YEAR])
    k = min(year + 1, MAX_LOTS - 1)
    if room <= 0.0:
        return 0.0
    gains = np.zeros(DI_BUCKETS)
    total = 0.0
    for i in range(N_STOCKS):
        price = st[D_PRICE + i]
        inv = 1.0 / price
        row = i * MAX_LOTS
        base = D_LIST + row
        for j in range(int(st[D_NLOTS + i])):
            tau = int(st[base + j])
            if tau >= year:  # lots held over a year: the opening position and every lot bought before last year
                continue
            u = st[D_LOTU + row + tau]
            if u <= _TINY:
                continue
            cost = st[D_LOTC + row + tau]
            if price - cost <= _TINY:
                continue
            gains[_bin(1.0 - cost * inv)] += u * (price - cost)
            total += u * (price - cost)
    if total <= 0.0:
        return 0.0
    room = min(room, total)
    above = 0.0
    stop = 0
    for b in range(DI_BUCKETS - 1, -1, -1):
        if above + gains[b] >= room:
            stop = b
            break
        above += gains[b]
    partial = 0.0
    if gains[stop] > 0.0:
        partial = min(1.0, max(0.0, (room - above) / gains[stop]))
    realized = 0.0
    for i in range(N_STOCKS):
        price = st[D_PRICE + i]
        inv = 1.0 / price
        row = i * MAX_LOTS
        base = D_LIST + row
        moved = 0.0
        for j in range(int(st[D_NLOTS + i])):
            tau = int(st[base + j])
            if tau >= year:
                continue
            u = st[D_LOTU + row + tau]
            if u <= _TINY:
                continue
            cost = st[D_LOTC + row + tau]
            if price - cost <= _TINY:
                continue
            b = _bin(1.0 - cost * inv)
            if b < stop:
                continue
            take = u if b > stop else partial * u
            if take <= 0.0:
                continue
            st[D_LOTU + row + tau] = max(0.0, u - take)
            realized += take * (price - cost)
            moved += take
        if moved > 0.0:
            slot = row + k
            st[D_LOTU + slot] += moved
            st[D_LOTC + slot] = price
            _list_add(st, i, k)
            if price > st[D_MAXC + i]:
                st[D_MAXC + i] = price
    st[S_BBASIS] += realized
    return realized


@jit
def di_donate(st, amount):
    """Give away `amount` of stock held more than a year, the lots with the most gain per dollar first (they cost the least):
    the gain is never realized. Only lots with a gain are given (a lot with a loss is worth more sold). Returns the value
    given (less than `amount` if there is not enough such stock)."""
    year = int(st[S_YEAR])
    if amount <= 0.0 or st[S_BE] <= 0.0:
        return 0.0
    values = np.zeros(DI_BUCKETS)
    total = 0.0
    for i in range(N_STOCKS):
        price = st[D_PRICE + i]
        inv = 1.0 / price
        row = i * MAX_LOTS
        base = D_LIST + row
        for j in range(int(st[D_NLOTS + i])):
            tau = int(st[base + j])
            if tau >= year:
                continue
            u = st[D_LOTU + row + tau]
            if u <= _TINY or st[D_LOTC + row + tau] >= price:
                continue
            values[_bin(1.0 - st[D_LOTC + row + tau] * inv)] += u * price
            total += u * price
    if total <= 0.0:
        return 0.0
    amount = min(amount, total)
    above = 0.0
    stop = 0
    for b in range(DI_BUCKETS - 1, -1, -1):
        if above + values[b] >= amount:
            stop = b
            break
        above += values[b]
    partial = 0.0
    if values[stop] > 0.0:
        partial = min(1.0, max(0.0, (amount - above) / values[stop]))
    given = 0.0
    basis = 0.0
    for i in range(N_STOCKS):
        price = st[D_PRICE + i]
        inv = 1.0 / price
        row = i * MAX_LOTS
        base = D_LIST + row
        for j in range(int(st[D_NLOTS + i])):
            tau = int(st[base + j])
            if tau >= year:
                continue
            u = st[D_LOTU + row + tau]
            if u <= _TINY:
                continue
            cost = st[D_LOTC + row + tau]
            if cost >= price:
                continue
            b = _bin(1.0 - cost * inv)
            if b < stop:
                continue
            take = u if b > stop else partial * u
            if take <= 0.0:
                continue
            st[D_LOTU + row + tau] = max(0.0, u - take)
            st[D_UNITS + i] = max(0.0, st[D_UNITS + i] - take)
            given += take * price
            basis += take * cost
    st[S_BE] -= given
    st[S_BBASIS] -= basis
    if st[S_BE] < 1e-9:
        st[S_BE] = 0.0
        st[S_BBASIS] = 0.0
    return given


@jit
def di_sell_fifo(st, amount):
    """Sell `amount` of stock the first-in-first-out way: the oldest lots first, every stock's together (pro rata within a
    lot's age). Not what the book does (it sells the highest cost first, `di_sell`): it is the comparison the diagnostics make
    on the same sales (`app.sim.replay`). Returns the realized gain, with its short-term part added to `S_STACC` as `di_sell` does."""
    value = st[S_BE]
    if amount <= 0.0 or value <= 0.0:
        return 0.0
    remaining = min(amount, value)
    year = int(st[S_YEAR])
    k = min(year + 1, MAX_LOTS - 1)
    short_on = st[S_STCG] > 0.5
    gain = 0.0
    sold_value = 0.0
    sold_basis = 0.0
    for tau in range(k + 1):
        if remaining <= 1e-9:
            break
        here = 0.0
        for i in range(N_STOCKS):
            here += st[D_LOTU + i * MAX_LOTS + tau] * st[D_PRICE + i]
        if here <= 0.0:
            continue
        share = min(1.0, remaining / here)
        for i in range(N_STOCKS):
            slot = D_LOTU + i * MAX_LOTS + tau
            u = st[slot]
            if u <= _TINY:
                continue
            take = share * u
            price = st[D_PRICE + i]
            cost = st[D_LOTC + i * MAX_LOTS + tau]
            st[slot] = max(0.0, u - take)
            st[D_UNITS + i] = max(0.0, st[D_UNITS + i] - take)
            g = take * (price - cost)
            gain += g
            if short_on:
                st[S_STACC] += lot_short_share(tau, year) * g
            sold_value += take * price
            sold_basis += take * cost
        remaining -= share * here
    st[S_BE] -= sold_value
    st[S_BBASIS] -= sold_basis
    if st[S_BE] < 1e-9:
        st[S_BE] = 0.0
        st[S_BBASIS] = 0.0
    return gain
