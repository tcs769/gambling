"""The same sales under another lot rule.

`app.sim.diag` records, for a path, the change in brokerage equity at every step of every year (the tape: a sale for a
goal, for spending, for the tax, a purchase with savings, and so on). Here a tape is replayed on the brokerage stock alone
with the same returns, the same stock movements, the same dividends and fund distributions and the very same dollars sold and
bought, but with a chosen lot rule: highest cost first or first in first out. What differs is only which lots a sale takes, so
the realized gains of two replays are a like-for-like comparison of the rules.

Left out, because they are not sales: loss harvesting (an advisor that does not harvest has none to compare), and anything
but the equity. Taxes are not worked out again, so the dollars sold to pay them stay what they were in the run.
"""

from __future__ import annotations

import numpy as np

from app.jit import jit, prange
from app.sim import markets
from app.sim.diag import D_TAPE, NK, TAPE_DONATE
from app.sim.simulate import (
    _KERNEL_LOCK,
    HC_HARVEST_THRESHOLD,
    NSTATE,
    NSTATE_DI,
    SP_DIST,
    SP_LOTS,
    SP_STCG,
    BatchResult,
    SimInputs,
    _lots_buy,
    _lots_donate,
    _lots_sell,
    _lots_start,
    wants_book,
)
from app.sim.state import (
    LOTS_FIFO,
    MAX_LOTS,
    S_BBASIS,
    S_BE,
    S_BEST,
    S_LOTC,
    S_LOTS,
    S_LOTU,
    S_PRICE,
    S_STACC,
    S_UNITS,
    S_YEAR,
)
from app.sim.stocks import di_sell, di_sell_fifo, di_year_begin

# columns of a replay's result
REPLAY_GAIN, REPLAY_GAIN_SHORT, REPLAY_UNREALIZED, REPLAY_EQUITY = range(4)
NREPLAY = 4


@jit
def _sell(st, amount, method, book):
    """Sell `amount` of stock the way `method` says; returns the realized gain (its short-term part lands in `S_STACC`)."""
    if book:
        if method == LOTS_FIFO:
            return di_sell_fifo(st, amount)
        return di_sell(st, amount)
    return _lots_sell(st, amount, st[S_LOTS])


@jit
def replay_path(row, tv, init, hhc, rets, g, tape, method, out):
    """Replay one path's tape under `method` (`LOTS_FIFO` or `LOTS_HIFO`) and write its `NREPLAY` results to `out`."""
    book = wants_book(row)
    if book:
        st = np.zeros(NSTATE_DI)
        st[:NSTATE] = init[:NSTATE]
    else:
        st = init.copy()
    own = row.copy()
    own[SP_LOTS] = method
    own[SP_STCG] = 1.0  # always count the short-term part: it is what is being compared
    _lots_start(st, own)
    dividend_yield = markets.DIVIDEND_YIELD
    rate = row[SP_DIST]
    realized = 0.0
    realized_short = 0.0
    n_years = tv.shape[0]
    for t in range(n_years):
        st[S_YEAR] = t
        r_e = rets[t, 0]
        dividends = dividend_yield * st[S_BE]
        if book:
            di_year_begin(st, t, 1.0 + r_e - dividend_yield, g[t], dividend_yield, hhc[HC_HARVEST_THRESHOLD], False)
            st[S_BBASIS] += dividends
        else:
            price = st[S_PRICE] * (1.0 + r_e - dividend_yield)
            st[S_PRICE] = price
            if dividends > 0.0:
                st[S_LOTU + t + 1] = dividends / price
                st[S_LOTC + t + 1] = price
                st[S_UNITS] += dividends / price
                known = int(st[S_BEST])
                if known >= 0 and price > st[S_LOTC + known]:
                    st[S_BEST] = t + 1
            st[S_BE] = price * st[S_UNITS]
            st[S_BBASIS] += dividends
            if rate > 0.0 and st[S_BE] > 0.0:
                # fund distributions raise every lot's cost by its share of them (what `_year_begin` does)
                bump = rate * st[S_PRICE]
                for i in range(min(t + 2, MAX_LOTS)):
                    if st[S_LOTU + i] > 1e-9:
                        st[S_LOTC + i] += bump
                st[S_BBASIS] += rate * st[S_BE]
        for slot in range(NK):
            change = tape[t * NK + slot]
            if change < -1e-9:
                if slot == TAPE_DONATE:
                    _lots_donate(st, -change)
                else:
                    realized += _sell(st, -change, method, book)
                    realized_short += st[S_STACC]
                    st[S_STACC] = 0.0
            elif change > 1e-9:
                _lots_buy(st, change)
    out[REPLAY_GAIN] = realized
    out[REPLAY_GAIN_SHORT] = realized_short
    out[REPLAY_UNREALIZED] = st[S_BE] - st[S_BBASIS]
    out[REPLAY_EQUITY] = st[S_BE]


@jit(parallel=True, nogil=True)
def _replay_batch(strat, tv, init, hhc, rets, zs, tapes, method, out):
    n_policies = strat.shape[0]
    n_paths = rets.shape[0]
    for i in prange(n_policies * n_paths):
        p = i // n_policies
        s = i - p * n_policies
        replay_path(strat[s], tv, init, hhc, rets[p], zs[p], tapes[s, p], method, out[s, p])


def replay_batch(inputs: SimInputs, policies, batch: BatchResult, method: float) -> np.ndarray:
    """(policies, paths, NREPLAY): every path of `batch` (run with diagnostics) replayed under `method`."""
    if batch.diag is None:
        raise ValueError("replay needs a batch run with diagnostics=True")
    strat = np.ascontiguousarray([p.row(inputs.current_age) for p in policies], dtype=np.float64)
    tapes = np.ascontiguousarray(batch.diag[:, :, D_TAPE:])
    out = np.zeros((len(policies), inputs.n_paths, NREPLAY))
    with _KERNEL_LOCK:
        _replay_batch(strat, inputs.tv, inputs.init, inputs.hhc, inputs.rets, inputs.stock_g, tapes, float(method), out)
    return out
