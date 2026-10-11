"""Year-by-year household simulator (real 2026 dollars, tax brackets held constant).

One scalar kernel simulates one household on one future under one policy; numba runs it over
every (policy, path) pair in parallel. A policy is a row of floats (`Policy.row`), so the
Donabach strategies and the RIA baseline share a single code path.

Each year, in order (spec section 5.3):
  1 apply returns            2 harvest losses          3 required minimum distribution, goals due
  4 withdraw spending        5 Roth conversion         6 fund/release the goal bucket
  7 rebalance + locate       8 compute taxes           9 pay portfolio-caused tax
 10 charge fees             11 add contributions
The simulation runs until the primary earner reaches `HORIZON_AGE` (80).

After-tax wealth = brokerage + goal bucket - 15% of unrealized gains + Roth
                   + pre-tax x (1 - effective federal rate on a 20-year evenly spread withdrawal
                     alongside Social Security) + 15% of unused loss carryforward.

Simplifications worth knowing (all applied identically to every policy):
* Brokerage sales (goals, spending, taxes) are pro rata across the account's equity and bonds;
  gains realized while selling to pay tax or fees are reported the following year.
* Tax lots (`Policy.lot_method`). The brokerage equity is a set of lots: the opening position (long-term) and
  one lot per simulated year, which takes that year's reinvested dividends, rebalancing purchases and savings at
  cost. "fifo" sells the oldest lot first, "hifo" the lot with the highest cost per dollar first, and "average"
  (the default, and what every result before lots existed used) sells every lot pro rata, tracks nothing and treats
  every gain as long-term. With lots, a lot sold in the year it was bought has a short-term gain, one sold the next
  year a half-short-term gain (purchases and sales are spread through the year, so it has been held more than a year
  half the time) and an older one a long-term gain; `Policy.short_term_ordinary` taxes the short-term part as
  ordinary income. Loss harvesting is still the aggregate rule below: it lowers every lot's basis in proportion.
* Dividends and interest are computed on opening balances and reinvested (reinvested dividends
  raise basis). Bonds carry no gain or loss for tax purposes.
* Private credit is only ever held in the pre-tax account; yields there are untaxed until
  withdrawal. Roth conversions are in kind.
* All dollar amounts, limits and brackets are constant in real terms.
* Required minimum distributions use the primary earner's age and the Uniform Lifetime Table on
  the household's combined pre-tax balance.
* Not modelled: the years after the first spouse dies (single-filer brackets) and taxes paid by
  heirs. Both generally favor Roth conversions, so the advantage of conversion strategies is
  understated.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, replace

import numpy as np

from app.jit import jit, prange
from app.schemas import Household, MarketShock
from app.sim import income, markets
from app.tax import params_2026 as P
from app.tax.engine import marginal_rate, pretax_withdrawal_rate, tax_core

# --------------------------------------------------------------------------------------------
# Layout constants shared by the kernel and the Python wrappers
# --------------------------------------------------------------------------------------------

# State vector. Indices 0..10 are balances that scale together when a fee is charged (the brokerage
# basis, a memo item, is skipped). Account letters: P pre-tax, R Roth, B brokerage; asset letters:
# E equity, B bonds, P private credit (the brokerage bonds also hold cash); GB is the goal bucket.
(S_PE, S_PB, S_PP, S_RE, S_RB, S_RP, S_BE, S_BBASIS, S_BB, S_BP, S_GB) = range(11)
S_CF, S_DGAIN, S_DDIST, S_UNFUNDED, S_LOAN = 11, 12, 13, 14, 15
# Tax lots. The path's lot method and short-term switch (set from the policy at the start), the year being simulated,
# the short-term gains realized so far by sales that are not yet in a year's tax return, and the short-term part of
# the deferred gains (S_DGAIN is the whole of them). The brokerage stock is a number of units at a price that moves
# with the market (S_PRICE, 1 at the start; S_UNITS is the total), so a year's growth touches no lot. Lot i holds
# S_LOTU + i units bought at S_LOTC + i per unit: lot 0 is the opening position and lot 1 + t takes year t's purchases.
# The account's value S_BE is S_PRICE x S_UNITS and its basis S_BBASIS is the sum of cost x units over the lots.
# S_BEST remembers which live lot has the highest cost per unit (-1: not known), so a sale need not look for it.
S_LOTS, S_STCG, S_YEAR, S_STACC, S_DGAIN_ST, S_PRICE, S_UNITS, S_BEST = 16, 17, 18, 19, 20, 21, 22, 23
N_SCALARS = 24
MAX_LOTS = 64  # a household can be as young as 18, so the horizon is at most 62 years: lots 0 to 63
S_LOTU = N_SCALARS
S_LOTC = S_LOTU + MAX_LOTS
NSTATE = S_LOTC + MAX_LOTS
N_BALANCES = 11

# Lot methods (S_LOTS, SP_LOTS) and the order a sale takes lots in.
LOTS_AVERAGE, LOTS_FIFO, LOTS_HIFO = 0.0, 1.0, 2.0

# Time-varying inputs, one row per simulated year.
(TV_AGE, TV_RETIRED, TV_SS, TV_NEED, TV_GOAL, TV_BUCKET, TV_EXPWAGE, TV_KIDS, TV_DEPS, TV_NEARN, TV_AGED, TV_SPEND) = range(12)
NTV = 12

# Policy columns.
(
    SP_STOCK,
    SP_GLIDE_START,
    SP_GLIDE_DROP,
    SP_PC,
    SP_DI,
    SP_BUCKET,
    SP_LOCATION,
    SP_CONV_TOP,
    SP_CONV_EVERY,
    SP_WD_BRACKET,
    SP_WD_TOP,
    SP_FEE_BREAKPOINTS,
    SP_FEE_FLAT,
    SP_K401,
    SP_BORROW,
    SP_TLH,
    SP_RESERVE,
    SP_REFILL,
    SP_LOTS,
    SP_STCG,
) = range(20)
NSP = 20

# 401(k) contribution type (SP_K401).
K401_PRETAX, K401_ROTH, K401_ROTH_LOW = 0.0, 1.0, 2.0

# Per-(policy, year) switches. 1.0 = the decision is taken, 0.0 = removed for that year.
G_CONV, G_HARVEST, G_BUCKET, G_LOCATION, G_WITHDRAW, G_K401, G_BORROW = range(7)
NGATE = 7
GATE_NAMES = ("conversion", "harvest", "bucket", "location", "withdraw", "k401", "borrow")

# One year's action. The first six are the decisions the adaptive planner chooses among each year
# (spec B3); the last four come from the fixed policy the planner continues with (and its gates).
(
    A_STOCK,  # stock share of long-term money at this year's rebalance
    A_PC,  # private credit share of long-term money
    A_CONV_TOP,  # Roth conversion: top of the bracket to fill (0 = none)
    A_K401_ROTH,  # 1.0 = this year's 401(k) contribution is Roth
    A_BORROW,  # 1.0 = fund this year's goal by borrowing against the portfolio
    A_REALIZE,  # 1.0 = realize gains up to the top of the 0% capital-gain bracket
    A_HARVEST,  # loss harvesting: 0 none, 1 fund level, 2 stock by stock
    A_BUCKET,  # 1.0 = maintain the goal bond bucket
    A_LOCATION,  # 1.0 = Donabach asset location (else the same mix in every account)
    A_WDBRACKET,  # 1.0 = withdraw pre-tax up to the bracket target first
    A_RESERVE,  # spending reserve: years of expenses held in bonds and private credit, the rest in stocks (0 = none)
    A_REFILL,  # 1.0 = do not sell stocks to refill the reserve in a year stocks fell
) = range(12)
NACT = 12

# Scratch carried from the start of a year to its end (what the household saw, then did).
(Y_REALIZED, Y_RETDIST, Y_EARLYBASE, Y_CFIN, Y_DIVIDENDS, Y_INTEREST, Y_HARVEST, Y_PRETAX_OPEN, Y_LOANINT, Y_FORCED, Y_EQRET, Y_REALIZED_ST) = range(12)
NY = 12

# Household constants.
HC_SS = 0
HC_RMD_START = 1  # age at which required minimum distributions begin
HC_HARVEST_MODEL = 2  # 0: the specification's direct-indexing harvest rule; 1: the evidence-based alternative
HC_DI_FEE_PREMIUM = 3  # extra yearly fee on direct-indexed equity (0 in the specification)
NHC = 4

# Kernel result columns.
R_WEALTH, R_TAXES, R_PRETAX_OWED, R_UNFUNDED = range(4)
NRESULT = 4

# Detailed year-log columns (deterministic path).
LOG_COLUMNS = (
    "age",
    "wages",
    "k401",
    "ss",
    "spend_need",
    "goal_paid",
    "interest",
    "dividends",
    "harvest",
    "ret_dist",
    "conv",
    "bucket_flow",
    "bucket",
    "stock_target",
    "equity_share",
    "net_gain",
    "early_base",
    "cf_in",
    "cf_out",
    "kids",
    "deps",
    "wages_taxable",
    "agi",
    "taxable_income",
    "marginal_rate",
    "fed_tax",
    "il_tax",
    "total_tax",
    "wage_tax",
    "portfolio_tax",
    "fee",
    "pretax",
    "roth",
    "brokerage",
    "wealth",
    "unrealized_gain",
    "aged",
    "rmd",
    "private_credit",
    "free_cash",
    "conv_cash",
    "k401_roth",
    "roth_extra_tax",
    "brokerage_saving",
    "roth_gap",
    "loan",
    "borrowed",
    "loan_interest",
    "forced_sale",
    "loan_repaid_saving",
    "loan_repaid_gain",
    "gain_harvest",
    "short_term_gain",
)
NLOG = len(LOG_COLUMNS)
(
    L_AGE,
    L_WAGES,
    L_K401,
    L_SS,
    L_NEED,
    L_GOAL,
    L_INTEREST,
    L_DIVIDENDS,
    L_HARVEST,
    L_RETDIST,
    L_CONV,
    L_BUCKETFLOW,
    L_BUCKET,
    L_STOCKTARGET,
    L_EQSHARE,
    L_NETGAIN,
    L_EARLYBASE,
    L_CFIN,
    L_CFOUT,
    L_KIDS,
    L_DEPS,
    L_WAGESTAXABLE,
    L_AGI,
    L_TAXABLE,
    L_MARGINAL,
    L_FED,
    L_IL,
    L_TOTALTAX,
    L_WAGETAX,
    L_PORTTAX,
    L_FEE,
    L_PRETAX,
    L_ROTH,
    L_BROKERAGE,
    L_WEALTH,
    L_UNREALIZED,
    L_AGED,
    L_RMD,
    L_PC,
    L_FREECASH,
    L_CONVCASH,
    L_K401ROTH,
    L_ROTHTAX,
    L_SAVING,
    L_ROTHGAP,
    L_LOAN,
    L_BORROWED,
    L_LOANINT,
    L_FORCED,
    L_REPAID_SAVING,
    L_REPAID_GAIN,
    L_GAINHARVEST,
    L_STGAIN,
) = range(NLOG)

# --------------------------------------------------------------------------------------------
# Rules of the model
# --------------------------------------------------------------------------------------------

KEEP_401K_SHARE_OF_WAGES = 0.20  # 401(k) contributions are capped at 20% of wages ...
BROKERAGE_SAVINGS_SHARE = 0.10  # ... plus 10% of wages saved in the brokerage account
LOW_INCOME_SHARE = 0.80  # a "low-income year" is wages below 80% of the expected level
BUCKET_YEARS_AHEAD = 4  # goal-matched bonds fully fund each goal four years ahead
HARVEST_DECLINE_SHARE = 0.85  # direct indexing harvests 85% of an equity decline ...
HARVEST_DISPERSION = 0.03  # ... plus 3% "dispersion" harvest scaled by basis ratio
HARVEST_CAP_OF_VALUE = 0.35  # ... capped at 35% of value (and at basis)
FUND_HARVEST_TRIGGER = -0.10  # fund-level harvesting only when equities fall more than 10%
GLIDE_END_AGE = 70.0  # glide paths end here, as before the horizon moved from 70 to 80

# Breakpoint advisory fee schedule used by the RIA baseline: (upper bound, marginal fee rate).
FEE_TOPS = np.array([1_000_000.0, 3_000_000.0, 5_000_000.0, np.inf])
FEE_RATES = np.array([0.010, 0.008, 0.006, 0.005])
DONABACH_FLAT_FEE = 0.0035

_EARLY_AGE = P.EARLY_WITHDRAWAL_AGE
_LTCG_RATE = P.UNREALIZED_GAIN_TAX_RATE


# --------------------------------------------------------------------------------------------
# Kernel helpers (all mutate the state vector in place)
# --------------------------------------------------------------------------------------------


@jit
def _shortfall(amount):
    """An obligation that no account could fund (sub-cent residue is rounding, not a shortfall)."""
    return amount if amount > 0.005 else 0.0


@jit
def _lots_start(st, row):
    """Start a path: the policy's lot method and short-term switch go into the state, and with lots the whole opening
    brokerage stock position is lot 0 (long-term), at a price of 1 a unit."""
    st[S_LOTS] = row[SP_LOTS]
    st[S_STCG] = row[SP_STCG]
    if row[SP_LOTS] > 0.5:
        be = st[S_BE]
        st[S_PRICE] = 1.0
        st[S_UNITS] = be
        st[S_LOTU] = be
        st[S_LOTC] = st[S_BBASIS] / be if be > 0.0 else 1.0
        st[S_BEST] = 0.0 if be > 0.0 else -1.0


@jit(inline="always")
def _lot_short_share(lot, year):
    """The share of a gain on `lot` that is short-term when it is sold in `year`: none for the opening position, all of
    it in the year the lot was bought, half the year after (purchases and sales are spread through a year, so a lot
    sold the next year has been held more than a year half the time), none after that."""
    if lot == 0:
        return 0.0
    age = year - (lot - 1)
    if age <= 0:
        return 1.0
    if age == 1:
        return 0.5
    return 0.0


@jit(inline="always")
def _lots_sell(st, amount, order):
    """Sell `amount` of brokerage stock from its lots, `order` LOTS_FIFO (oldest lot first) or LOTS_HIFO (the lot bought at
    the highest price first, which is the one with the highest cost per dollar of value). Returns the realized gain; its
    short-term part, when short-term gains are taxed as ordinary income, is added to `st[S_STACC]`."""
    year = int(st[S_YEAR])
    n = min(year + 2, MAX_LOTS)
    price = st[S_PRICE]
    short_on = st[S_STCG] > 0.5
    gain = 0.0
    basis_sold = 0.0
    units_sold = 0.0
    hifo = order == LOTS_HIFO
    remaining = amount / price
    while remaining > 1e-9:
        best = -1
        if hifo:
            known = int(st[S_BEST])
            if known >= 0 and st[S_LOTU + known] > 1e-9:
                best = known
        if best < 0:
            for i in range(n):
                u = st[S_LOTU + i]
                if u <= 1e-9:
                    continue
                if best < 0:
                    best = i
                    if not hifo:
                        break
                elif st[S_LOTC + i] > st[S_LOTC + best]:
                    best = i
            if best < 0:
                break
            if hifo:
                st[S_BEST] = best
        best_u = st[S_LOTU + best]
        best_c = st[S_LOTC + best]
        take = min(best_u, remaining)
        if take >= best_u:
            st[S_LOTU + best] = 0.0
            st[S_BEST] = -1.0 if hifo else st[S_BEST]
        else:
            st[S_LOTU + best] = best_u - take
        g = take * (price - best_c)
        gain += g
        basis_sold += take * best_c
        units_sold += take
        if short_on:
            st[S_STACC] += _lot_short_share(best, year) * g
        remaining -= take
    units = st[S_UNITS] - units_sold
    if units <= 1e-9:
        units = 0.0
        st[S_BBASIS] = 0.0
    else:
        st[S_BBASIS] -= basis_sold
    st[S_UNITS] = units
    st[S_BE] = price * units
    return gain


@jit(inline="always")
def _lots_buy(st, amount):
    """Buy `amount` of brokerage stock at cost: it goes into this year's lot (every purchase in a year is at the same price)."""
    if amount <= 0.0:
        return
    k = min(int(st[S_YEAR]) + 1, MAX_LOTS - 1)
    price = st[S_PRICE]
    units = amount / price
    held = st[S_LOTU + k]
    st[S_LOTC + k] = (st[S_LOTC + k] * held + amount) / (held + units)
    st[S_LOTU + k] = held + units
    known = int(st[S_BEST])
    if known >= 0 and st[S_LOTC + k] > st[S_LOTC + known]:
        st[S_BEST] = k
    st[S_UNITS] += units
    st[S_BE] = price * st[S_UNITS]
    st[S_BBASIS] += amount


@jit(inline="always")
def _lots_set_basis(st, total):
    """Lower the account's total basis to `total` (loss harvesting): every lot's cost falls in proportion."""
    old = st[S_BBASIS]
    if old > 0.0:
        f = total / old
        n = min(int(st[S_YEAR]) + 2, MAX_LOTS)
        for i in range(n):
            st[S_LOTC + i] *= f
    st[S_BBASIS] = total


@jit(inline="always")
def _lots_realize(st, room):
    """Realize up to `room` of gain in lots held more than a year (so the gain is long-term): sell the lots bought at the
    lowest prices (the most gain per dollar) and buy the same shares back at once. Only their basis steps up, and the shares
    become part of this year's lot. Returns the gain realized."""
    year = int(st[S_YEAR])
    n = min(year + 2, MAX_LOTS)
    price = st[S_PRICE]
    realized = 0.0
    moved = 0.0
    while realized < room - 1e-9:
        best = -1
        best_u = 0.0
        best_c = 0.0
        for i in range(n):
            if _lot_short_share(i, year) > 0.0:
                continue
            u = st[S_LOTU + i]
            c = st[S_LOTC + i]
            if u <= 1e-9 or price - c <= 1e-12:
                continue
            if best < 0 or c < best_c:
                best = i
                best_u = u
                best_c = c
        if best < 0:
            break
        take_gain = min(room - realized, best_u * (price - best_c))
        take = min(best_u, take_gain / (price - best_c))
        st[S_LOTU + best] = best_u - take
        realized += take_gain
        moved += take
    if moved > 0.0:
        k = min(year + 1, MAX_LOTS - 1)
        held = st[S_LOTU + k]
        st[S_LOTC + k] = (st[S_LOTC + k] * held + moved * price) / (held + moved)
        st[S_LOTU + k] = held + moved
        st[S_BBASIS] += realized
        st[S_BEST] = -1.0
    return realized


@jit
def _sell_brokerage(st, amount, ne=0.0):
    """Sell `amount` across brokerage equity, bonds and private credit: pro rata, or (`ne` > 0.5, the spending reserve)
    bonds and private credit first and equity only for what they cannot cover. Returns (sold, realized gain)."""
    be = st[S_BE]
    total = be + st[S_BB] + st[S_BP]
    if amount <= 0.0 or total <= 0.0:
        return 0.0, 0.0
    lots = st[S_LOTS] > 0.5
    if ne > 0.5:
        safe = st[S_BB] + st[S_BP]
        from_safe = min(amount, safe)
        if safe > 0.0:
            g = from_safe / safe
            st[S_BB] *= 1.0 - g
            st[S_BP] *= 1.0 - g
        rest = min(amount - from_safe, be)
        gain = 0.0
        if rest > 0.0:
            if lots:
                gain = _lots_sell(st, rest, st[S_LOTS])
            else:
                h = rest / be
                gain = h * (be - st[S_BBASIS])
                st[S_BBASIS] *= 1.0 - h
                st[S_BE] = be * (1.0 - h)
        return from_safe + rest, gain
    f = min(1.0, amount / total)
    if lots:
        gain = _lots_sell(st, f * be, st[S_LOTS])
    else:
        gain = f * (be - st[S_BBASIS])
        st[S_BBASIS] *= 1.0 - f
        st[S_BE] = be * (1.0 - f)
    st[S_BB] *= 1.0 - f
    st[S_BP] *= 1.0 - f
    return f * total, gain


@jit
def _sell_roth(st, amount, ne=0.0):
    total = st[S_RE] + st[S_RB] + st[S_RP]
    if amount <= 0.0 or total <= 0.0:
        return 0.0
    if ne > 0.5:
        safe = st[S_RB] + st[S_RP]
        from_safe = min(amount, safe)
        if safe > 0.0:
            g = from_safe / safe
            st[S_RB] *= 1.0 - g
            st[S_RP] *= 1.0 - g
        rest = min(amount - from_safe, st[S_RE])
        st[S_RE] -= rest
        return from_safe + rest
    f = min(1.0, amount / total)
    st[S_RE] *= 1.0 - f
    st[S_RB] *= 1.0 - f
    st[S_RP] *= 1.0 - f
    return f * total


@jit
def _sell_pretax(st, amount, ne=0.0):
    total = st[S_PE] + st[S_PB] + st[S_PP]
    if amount <= 0.0 or total <= 0.0:
        return 0.0
    if ne > 0.5:
        safe = st[S_PB] + st[S_PP]
        from_safe = min(amount, safe)
        if safe > 0.0:
            g = from_safe / safe
            st[S_PB] *= 1.0 - g
            st[S_PP] *= 1.0 - g
        rest = min(amount - from_safe, st[S_PE])
        st[S_PE] -= rest
        return from_safe + rest
    f = min(1.0, amount / total)
    st[S_PE] *= 1.0 - f
    st[S_PB] *= 1.0 - f
    st[S_PP] *= 1.0 - f
    return f * total


@jit
def _convert_to_roth(st, fraction):
    """Convert `fraction` of the pre-tax account to Roth, in kind: each asset class stays what it is."""
    st[S_RE] += fraction * st[S_PE]
    st[S_RB] += fraction * st[S_PB]
    st[S_RP] += fraction * st[S_PP]
    st[S_PE] *= 1.0 - fraction
    st[S_PB] *= 1.0 - fraction
    st[S_PP] *= 1.0 - fraction


@jit
def _accrue_and_deleverage(st):
    """Start-of-year loan upkeep. Returns (interest accrued, assets sold in a forced sale, gain realized by it).

    Interest accrues on the loan (it is booked as a capital loss by the caller). If the loan then exceeds
    40% of the taxable account (stocks, bonds and private credit), assets are sold to bring it back to 30%.
    """
    loan = st[S_LOAN]
    if loan <= 0.0:
        return 0.0, 0.0, 0.0
    interest = loan * P.BORROWING_RATE_REAL
    loan += interest
    forced = 0.0
    gain = 0.0
    value = st[S_BE] + st[S_BB] + st[S_BP]
    if loan > P.BORROWING_FORCED_SALE_TRIGGER * value:
        wanted = (loan - P.BORROWING_LIMIT * value) / (1.0 - P.BORROWING_LIMIT)
        forced, gain = _sell_brokerage(st, min(wanted, value), 0.0)
        loan = max(0.0, loan - forced)
    st[S_LOAN] = loan
    return interest, forced, gain


@jit
def _borrow_for_goal(st, due):
    """Borrow up to `due` against the taxable account without the loan passing 30% of its value."""
    value = st[S_BE] + st[S_BB] + st[S_BP]
    borrowed = min(due, max(0.0, P.BORROWING_LIMIT * value - st[S_LOAN]))
    st[S_LOAN] += borrowed
    return borrowed


@jit
def _zero_gain_room(wages_taxable, interest, dividends, taxable_ss, ret_dist, conv, realized, realized_st, cf, std):
    """Dollars of further long-term gain that would still be taxed at 0% this year (income so far
    stacked under them: ordinary income, qualified dividends, gains already realized)."""
    ordinary = _ordinary_income(wages_taxable, interest, taxable_ss, ret_dist, conv, realized, realized_st, cf)
    taxable = max(0.0, ordinary + max(0.0, realized - cf) - _short_in_net(realized, realized_st, cf) + dividends - std)
    return max(0.0, P.CG_ZERO_TOP - taxable)


@jit
def _pay_tax(st, due, protected_roth, ne=0.0):
    """Pay `due` of income tax from the portfolio: brokerage, then Roth, then pre-tax (each bonds and private credit
    first when `ne` > 0.5, the spending reserve).

    Roth dollars converted this year (`protected_roth`) are never used: conversion tax is not paid
    out of the converted amount. Gains realized by selling to pay it are taxed next year; so are
    pre-tax withdrawals. Whatever no account can fund is recorded as unfunded.
    """
    sold, gain = _sell_brokerage(st, due, ne)
    st[S_DGAIN] += gain
    due -= sold
    if due > 0.0:
        roth = st[S_RE] + st[S_RB] + st[S_RP]
        due -= _sell_roth(st, min(due, max(0.0, roth - protected_roth)), ne)
    if due > 0.0:
        taken = _sell_pretax(st, due, ne)
        st[S_DDIST] += taken
        due -= taken
    st[S_UNFUNDED] += _shortfall(due)


@jit(inline="always")
def _short_in_net(realized, realized_st, cf):
    """The short-term part of the net capital gain so far, which is ordinary income: `realized_st` is a part of
    `realized`, and a long-term loss or loss carryforward absorbs short-term gains before anything is taxed."""
    net = realized - cf
    if net > 0.0 and realized_st > 0.0:
        return min(realized_st, net)
    return 0.0


@jit
def _ordinary_income(wages_taxable, interest, taxable_ss, ret_dist, conv, realized, realized_st, cf):
    """Ordinary income so far: wages, interest, SS, withdrawals, conversions, short-term gains, and any capital
    loss deduction (net losses offset up to $3,000 of ordinary income)."""
    net = realized - cf
    loss_deduction = 0.0
    if net < 0.0:
        loss_deduction = min(P.CAP_LOSS_LIMIT, -net)
    return wages_taxable + interest + taxable_ss + ret_dist + conv + _short_in_net(realized, realized_st, cf) - loss_deduction


@jit
def _ult_period(age):
    """Uniform Lifetime Table distribution period for the age reached this year."""
    i = int(min(max(age, P.ULT_FIRST_AGE), P.ULT_LAST_AGE)) - P.ULT_FIRST_AGE
    return P.ULT_PERIODS[i]


@jit
def _stock_share(age, stock, glide_start, glide_drop):
    """Stock share of long-term money: flat, then gliding down linearly to GLIDE_END_AGE."""
    if age <= glide_start:
        return stock
    frac = min(1.0, (age - glide_start) / (GLIDE_END_AGE - glide_start))
    return stock - glide_drop * frac


@jit
def _advisory_fee(total, breakpoints, flat):
    if breakpoints < 0.5:
        return flat * total
    fee = 0.0
    lower = 0.0
    for i in range(FEE_TOPS.shape[0]):
        top = FEE_TOPS[i]
        if total > lower:
            fee += (min(total, top) - lower) * FEE_RATES[i]
        lower = top
    return fee


@jit
def _rebalance(st, equity, private_credit, uniform):
    """Move every account to the target mix. Returns the capital gain realized in brokerage.

    uniform: the same mix in every account (the RIA approach; no private credit).
    Otherwise Donabach asset location: private credit goes in the pre-tax account first, overflowing
    to the Roth and then to brokerage; bonds fill what is left of the pre-tax account; the Roth
    holds stocks (after any private credit); brokerage takes the remainder.
    """
    pe, pb, pp = st[S_PE], st[S_PB], st[S_PP]
    re, rb, rp = st[S_RE], st[S_RB], st[S_RP]
    be, bb, bp = st[S_BE], st[S_BB], st[S_BP]
    pre = pe + pb + pp
    ros = re + rb + rp
    brk = be + bb + bp
    total = pre + ros + brk
    if total <= 0.0:
        return 0.0

    if uniform:
        pe_n, pb_n, pp_n = pre * equity, pre * (1.0 - equity), 0.0
        re_n, rb_n, rp_n = ros * equity, ros * (1.0 - equity), 0.0
        be_n = brk * equity
        bp_n = 0.0
    else:
        equity_target = equity * total
        pc_target = private_credit * total
        bonds_target = max(0.0, total - equity_target - pc_target)
        pp_n = min(pc_target, pre)
        rp_n = min(pc_target - pp_n, ros)
        bp_n = pc_target - pp_n - rp_n
        pb_n = min(bonds_target, pre - pp_n)
        pe_n = pre - pp_n - pb_n
        re_n = min(ros - rp_n, max(equity_target - pe_n, 0.0))
        rb_n = ros - rp_n - re_n
        be_n = equity_target - pe_n - re_n
    be_n = min(max(be_n, 0.0), brk - bp_n)  # guard against floating-point drift
    bb_n = brk - be_n - bp_n

    gain = 0.0
    lots = st[S_LOTS] > 0.5
    if be_n < be:
        if lots:
            gain = _lots_sell(st, be - be_n, st[S_LOTS])
        else:
            gain = (be - be_n) * (be - st[S_BBASIS]) / be
            st[S_BBASIS] *= be_n / be
    elif be_n > be:
        if lots:
            _lots_buy(st, be_n - be)
        else:
            st[S_BBASIS] += be_n - be
    st[S_PE], st[S_PB], st[S_PP] = pe_n, pb_n, pp_n
    st[S_RE], st[S_RB], st[S_RP] = re_n, rb_n, rp_n
    st[S_BB], st[S_BP] = bb_n, bp_n
    if not lots:
        st[S_BE] = be_n  # with lots the account's value is the sum of the lots, which the sale or purchase has just set
    return gain


# --------------------------------------------------------------------------------------------
# One household, one future: the year, in two halves
# --------------------------------------------------------------------------------------------
#
# (The three year functions are inlined into `_run_years`, the one place that runs them: as separate calls
# each argument array is reference-counted on entry and exit, which made the kernel about 40% slower.)
#
# A year is simulated by `_year_begin` (returns and loss harvesting: what the household sees
# before it decides anything) and `_year_rest` (everything it then does, given an action). A fixed
# policy turns its row into the year's action with `_policy_action`; the adaptive planner chooses
# the action itself after `_year_begin`, from what has happened so far. Both go through the same
# two functions, so a forced action reproduces a fixed policy exactly.


@jit(inline="always")
def _policy_action(row, gates_row, tv, t, w, act):
    """Fill `act` with what the fixed policy `row` does in year `t` (a gate of 0 removes a decision)."""
    age = tv[t, TV_AGE]
    act[A_STOCK] = _stock_share(age, row[SP_STOCK], row[SP_GLIDE_START], row[SP_GLIDE_DROP])
    act[A_PC] = row[SP_PC]
    conv_top = 0.0
    if row[SP_CONV_TOP] > 0.0 and gates_row[G_CONV] > 0.5:
        low_income = w < LOW_INCOME_SHARE * tv[t, TV_EXPWAGE]
        if row[SP_CONV_EVERY] > 0.5 or tv[t, TV_RETIRED] > 0.5 or low_income:
            conv_top = row[SP_CONV_TOP]
    act[A_CONV_TOP] = conv_top
    roth = 0.0
    if gates_row[G_K401] > 0.5:
        if row[SP_K401] == K401_ROTH:
            roth = 1.0
        elif row[SP_K401] == K401_ROTH_LOW and w < LOW_INCOME_SHARE * tv[t, TV_EXPWAGE]:
            roth = 1.0
    act[A_K401_ROTH] = roth
    act[A_BORROW] = 1.0 if (row[SP_BORROW] > 0.5 and gates_row[G_BORROW] > 0.5) else 0.0
    act[A_REALIZE] = 0.0
    harvest = 0.0
    if gates_row[G_HARVEST] > 0.5 and row[SP_TLH] > 0.5:
        harvest = 2.0 if row[SP_DI] > 0.5 else 1.0
    act[A_HARVEST] = harvest
    act[A_BUCKET] = 1.0 if ((row[SP_BUCKET] > 0.5 or row[SP_RESERVE] > 0.5) and gates_row[G_BUCKET] > 0.5) else 0.0
    act[A_LOCATION] = 1.0 if (row[SP_LOCATION] < 0.5 and gates_row[G_LOCATION] > 0.5) else 0.0
    act[A_WDBRACKET] = 1.0 if (row[SP_WD_BRACKET] > 0.5 and gates_row[G_WITHDRAW] > 0.5) else 0.0
    act[A_RESERVE] = row[SP_RESERVE]
    act[A_REFILL] = row[SP_REFILL]


@jit(inline="always")
def _year_begin(st, ys, tv, t, hhc, act, r_e, r_b, r_c):
    """Steps 1-2: apply this year's returns, then harvest losses. Fills the year scratch `ys`."""
    age = tv[t, TV_AGE]
    early = age < _EARLY_AGE
    equity_open = st[S_BE]
    basis_open = st[S_BBASIS]
    st[S_YEAR] = t

    # Gains and withdrawals deferred from paying last year's tax and fees land in this year.
    realized = st[S_DGAIN]
    realized_st = st[S_DGAIN_ST]  # the short-term part of those gains
    ret_dist = st[S_DDIST]
    st[S_DGAIN] = 0.0
    st[S_DGAIN_ST] = 0.0
    st[S_DDIST] = 0.0
    ys[Y_EARLYBASE] = ret_dist if early else 0.0
    ys[Y_CFIN] = st[S_CF]
    ys[Y_PRETAX_OPEN] = st[S_PE] + st[S_PB] + st[S_PP]  # last December 31 balance: the RMD base

    # Opening balances drive this year's dividends and interest.
    dividends = markets.DIVIDEND_YIELD * st[S_BE]
    interest = markets.BOND_INTEREST_YIELD * (st[S_BB] + st[S_GB]) + markets.PRIVATE_CREDIT_INCOME_YIELD * st[S_BP]

    # 1. Returns.
    st[S_PE] *= 1.0 + r_e
    st[S_PB] *= 1.0 + r_b
    st[S_PP] *= 1.0 + r_c
    st[S_RE] *= 1.0 + r_e
    st[S_RB] *= 1.0 + r_b
    st[S_RP] *= 1.0 + r_c
    if st[S_LOTS] > 0.5:
        # The price earns the price return; the dividends are paid out of the total return and bought back at the new
        # price, which makes them this year's lot (a fresh lot: nothing was bought in it earlier this year).
        price = st[S_PRICE] * (1.0 + r_e - markets.DIVIDEND_YIELD)
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
    else:
        st[S_BE] *= 1.0 + r_e
        st[S_BBASIS] += dividends  # reinvested dividends are bought at cost
    st[S_BB] *= 1.0 + r_b
    st[S_BP] *= 1.0 + r_c
    st[S_GB] *= 1.0 + r_b

    # 2. Harvest losses (0 = none, 1 = fund level, 2 = stock by stock).
    harvest = 0.0
    be = st[S_BE]
    basis = st[S_BBASIS]
    mode = act[A_HARVEST]
    if mode > 0.5 and be > 0.0:
        if mode > 1.5:
            decline = max(0.0, -r_e) * be / (1.0 + r_e)
            if hhc[HC_HARVEST_MODEL] > 0.5:
                # Sensitivity only (reports/assumption_review.md): harvesting shrinks steeply as the basis rises to
                # the value, and only a part of a decline is harvestable once lots have gains.
                b_open = min(1.0, basis_open / equity_open) if equity_open > 0.0 else 1.0
                b_now = min(1.0, basis / be)
                wanted = 0.85 * b_open**3 * decline + 0.14 * be * b_now**14
            else:
                dispersion = HARVEST_DISPERSION * be * min(1.0, basis / be)
                wanted = HARVEST_DECLINE_SHARE * decline + dispersion
            harvest = min(wanted, HARVEST_CAP_OF_VALUE * be, basis)
        elif r_e < FUND_HARVEST_TRIGGER:
            harvest = max(0.0, basis - be)
        harvest = max(0.0, harvest)
        realized -= harvest
        if st[S_LOTS] > 0.5:
            if harvest > 0.0:
                _lots_set_basis(st, basis - harvest)
        else:
            st[S_BBASIS] = basis - harvest

    # 2b. The box-spread loan: interest accrues (and is booked as a capital loss), and if a market
    # drop pushes the loan above 40% of the taxable account, assets are sold to bring it back to 30%.
    loan_interest, forced, forced_gain = _accrue_and_deleverage(st)
    realized += forced_gain - loan_interest
    realized_st += st[S_STACC]
    st[S_STACC] = 0.0

    ys[Y_EQRET] = r_e
    ys[Y_LOANINT] = loan_interest
    ys[Y_FORCED] = forced
    ys[Y_REALIZED] = realized
    ys[Y_REALIZED_ST] = realized_st
    ys[Y_RETDIST] = ret_dist
    ys[Y_DIVIDENDS] = dividends
    ys[Y_INTEREST] = interest
    ys[Y_HARVEST] = harvest


@jit(inline="always")
def _year_rest(st, ys, tv, t, hhc, row, act, w, k, wt_pre, wt_roth, want_wealth, do_log, log):
    """Steps 3-11 for the action `act`. Returns (after-tax wealth if `want_wealth`, total income tax)."""
    age = tv[t, TV_AGE]
    ss = tv[t, TV_SS]
    taxable_ss = P.SS_TAXABLE_SHARE * ss
    ne = 1.0 if act[A_RESERVE] > 0.5 else 0.0  # spending reserve: expenses come from bonds and private credit first
    kids = tv[t, TV_KIDS]
    deps = tv[t, TV_DEPS]
    # A Roth 401(k) contribution is made from after-tax pay: taxable wages are not reduced by it, and
    # the extra tax comes out of brokerage saving first, so consumption stays where it was.
    roth_401k = act[A_K401_ROTH] > 0.5 and k > 0.0
    wages_taxable = w if roth_401k else w - k
    wage_tax_t = wt_roth if roth_401k else wt_pre
    extra_tax = wt_roth - wt_pre if roth_401k else 0.0
    saved = BROKERAGE_SAVINGS_SHARE * w
    saved_net = max(0.0, saved - extra_tax)
    uncovered = extra_tax - (saved - saved_net)  # extra tax that brokerage saving does not cover
    spare = max(0.0, w - wt_pre - k - saved - tv[t, TV_SPEND])  # spare wages before any Roth extra tax
    free_cash = max(0.0, spare - uncovered)
    roth_gap = max(0.0, uncovered - spare)  # extra tax even spare wages cannot cover: paid from the portfolio
    early = age < _EARLY_AGE
    ss_annual = hhc[HC_SS]
    aged = tv[t, TV_AGED]
    std = P.STANDARD_DEDUCTION_MFJ + P.STANDARD_DEDUCTION_AGED_PER_SPOUSE * aged

    realized = ys[Y_REALIZED]
    ret_dist = ys[Y_RETDIST]
    early_base = ys[Y_EARLYBASE]
    cf_in = ys[Y_CFIN]
    dividends = ys[Y_DIVIDENDS]
    interest = ys[Y_INTEREST]
    harvest = ys[Y_HARVEST]
    wd_bracket = act[A_WDBRACKET] > 0.5
    wd_top = row[SP_WD_TOP]
    conv_top = act[A_CONV_TOP]

    # 3a. Required minimum distribution: the prior year-end pre-tax balance over the Uniform
    # Lifetime Table period, withdrawn from pre-tax (taxable income) and spent first on goals
    # and spending; whatever is not needed goes to the brokerage account.
    rmd = 0.0
    if age >= hhc[HC_RMD_START]:
        rmd = _sell_pretax(st, ys[Y_PRETAX_OPEN] / _ult_period(age), ne)
        ret_dist += rmd
    rmd_cash = rmd

    # 3b. Pay goals that are due: RMD cash, bucket, then brokerage pro rata, then Roth, then pre-tax.
    goal = tv[t, TV_GOAL]
    borrowed = 0.0
    if goal > 0.0:
        due = goal
        from_rmd = min(rmd_cash, due)
        rmd_cash -= from_rmd
        due -= from_rmd
        from_bucket = min(st[S_GB], due)
        st[S_GB] -= from_bucket
        due -= from_bucket
        if due > 0.0 and act[A_BORROW] > 0.5:
            # Borrow against the taxable account instead of selling, up to 30% of its value.
            borrowed = _borrow_for_goal(st, due)
            due -= borrowed
        if due > 0.0:
            sold, gain = _sell_brokerage(st, due, ne)
            realized += gain
            due -= sold
        if due > 0.0:
            due -= _sell_roth(st, due, ne)
        if due > 0.0:
            taken = _sell_pretax(st, due, ne)
            ret_dist += taken
            if early:
                early_base += taken
            due -= taken
        st[S_UNFUNDED] += _shortfall(due)

    # 4. Withdraw retirement spending (net of Social Security).
    need = tv[t, TV_NEED]
    if need > 0.0:
        from_rmd = min(rmd_cash, need)
        rmd_cash -= from_rmd
        remaining = need - from_rmd
        if remaining <= 0.0:
            pass
        elif early:
            # Before 59 1/2: taxable account, then Roth, then pre-tax with the 10% penalty.
            sold, gain = _sell_brokerage(st, remaining, ne)
            realized += gain
            remaining -= sold
            if remaining > 0.0:
                remaining -= _sell_roth(st, remaining, ne)
            if remaining > 0.0:
                taken = _sell_pretax(st, remaining, ne)
                ret_dist += taken
                early_base += taken
                remaining -= taken
        elif wd_bracket:
            # Pre-tax up to the bracket target, then brokerage, then Roth.
            ordinary = _ordinary_income(wages_taxable, interest, taxable_ss, ret_dist, 0.0, realized, ys[Y_REALIZED_ST] + st[S_STACC], cf_in)
            room = max(0.0, wd_top + std - ordinary)
            taken = _sell_pretax(st, min(remaining, room), ne)
            ret_dist += taken
            remaining -= taken
            if remaining > 0.0:
                sold, gain = _sell_brokerage(st, remaining, ne)
                realized += gain
                remaining -= sold
            if remaining > 0.0:
                remaining -= _sell_roth(st, remaining, ne)
            if remaining > 0.0:
                taken = _sell_pretax(st, remaining, ne)
                ret_dist += taken
                remaining -= taken
        else:
            # Pro rata across pre-tax, brokerage and Roth.
            pre = st[S_PE] + st[S_PB] + st[S_PP]
            brk = st[S_BE] + st[S_BB] + st[S_BP]
            ros = st[S_RE] + st[S_RB] + st[S_RP]
            total = pre + brk + ros
            if total > 0.0:
                f = min(1.0, remaining / total)
                taken = _sell_pretax(st, f * pre, ne)
                ret_dist += taken
                sold, gain = _sell_brokerage(st, f * brk, ne)
                realized += gain
                got = _sell_roth(st, f * ros, ne)
                remaining -= taken + sold + got
        st[S_UNFUNDED] += _shortfall(remaining)
    if rmd_cash > 0.0:
        st[S_BB] += rmd_cash  # an RMD that exceeds spending is reinvested in the taxable account

    # 5. Roth conversion: fill the chosen bracket, if the action asks for it. The tax on it can be
    # paid from the taxable account (cash included) and from this year's wages once taxes, 401(k),
    # brokerage savings and normal spending are covered, but never out of the converted dollars.
    # Before retirement normal spending is taken to be what the household plans to spend in
    # retirement; the documents do not say what it spends today.
    conv = 0.0
    if conv_top > 0.0:
        ordinary = _ordinary_income(wages_taxable, interest, taxable_ss, ret_dist, 0.0, realized, ys[Y_REALIZED_ST] + st[S_STACC], cf_in)
        room = max(0.0, conv_top + std - ordinary)
        pre = st[S_PE] + st[S_PB] + st[S_PP]
        funds = st[S_BE] + st[S_BB] + st[S_BP] + free_cash
        affordable = funds / marginal_rate(conv_top - 1.0)
        conv = min(room, pre, affordable)
        if conv > 0.0:
            _convert_to_roth(st, conv / pre)

    # 5b. Realize gains up to the top of the 0% capital-gain bracket (an action only the adaptive planner
    # takes): sell and immediately rebuy the equity, so nothing moves but the basis, which steps up.
    gain_harvest = 0.0
    if act[A_REALIZE] > 0.5:
        unrealized = st[S_BE] - st[S_BBASIS]
        if unrealized > 0.0:
            room = _zero_gain_room(wages_taxable, interest, dividends, taxable_ss, ret_dist, conv, realized, ys[Y_REALIZED_ST] + st[S_STACC], cf_in, std)
            if st[S_LOTS] > 0.5:
                gain_harvest = _lots_realize(st, min(room, unrealized))
            else:
                gain_harvest = min(room, unrealized)
                st[S_BBASIS] += gain_harvest
            realized += gain_harvest

    # 6. Fund or release the goal bucket (bonds held in the taxable account). With a spending reserve it covers the goals of
    # the next `A_RESERVE` years (the retirement spending part of the reserve is held in step 7) and, like the rest of the
    # reserve, is not built by selling stocks in a year stocks fell.
    bucket_flow = 0.0
    if act[A_BUCKET] > 0.5:
        target = tv[t, TV_BUCKET]
        build = True
        if act[A_RESERVE] > 0.5:
            target = 0.0
            for j in range(1, int(act[A_RESERVE] + 0.5) + 1):
                if t + j < tv.shape[0]:
                    target += tv[t + j, TV_GOAL]
            build = not (act[A_REFILL] > 0.5 and ys[Y_EQRET] < 0.0)
        held = st[S_GB]
        if held < target:
            if build:
                sold, gain = _sell_brokerage(st, target - held, 0.0)
                realized += gain
                st[S_GB] += sold
                bucket_flow = sold
        elif held > target:
            st[S_GB] = target
            st[S_BB] += held - target
            bucket_flow = target - held

    # 6b. Repay the loan in a low-tax year by selling appreciated holdings: realize gains only up to
    # the top of the 0% capital-gain bracket (nothing to realize means the sale is tax-free anyway).
    repaid_gain = 0.0
    if st[S_LOAN] > 0.0 and borrowed <= 0.0:  # not in the year it was borrowed
        room = _zero_gain_room(wages_taxable, interest, dividends, taxable_ss, ret_dist, conv, realized, ys[Y_REALIZED_ST] + st[S_STACC], cf_in, std)
        if room > 0.0:
            value = st[S_BE] + st[S_BB] + st[S_BP]
            embedded = (st[S_BE] - st[S_BBASIS]) / value if value > 0.0 else 0.0
            amount = st[S_LOAN] if embedded <= 0.0 else min(st[S_LOAN], room / embedded)
            repaid_gain, gain = _sell_brokerage(st, amount, 0.0)
            realized += gain
            st[S_LOAN] -= repaid_gain

    # 7. Rebalance to the target allocation and asset location.
    share = act[A_STOCK]
    pc_share = act[A_PC]
    stock_logged = share
    if act[A_RESERVE] > 0.5:
        # Spending reserve: bonds and private credit hold the next `A_RESERVE` years of retirement spending net of Social
        # Security (the goals of those years are in the goal bucket, step 6) and everything else is stocks. The private credit
        # sleeve counts toward the reserve. After a year stocks fell the reserve is not refilled by selling them (what is
        # above target still goes into stocks).
        total = st[S_PE] + st[S_PB] + st[S_PP] + st[S_RE] + st[S_RB] + st[S_RP] + st[S_BE] + st[S_BB] + st[S_BP]
        needed = 0.0
        for j in range(1, int(act[A_RESERVE] + 0.5) + 1):
            if t + j < tv.shape[0]:
                needed += tv[t + j, TV_NEED]
        safe_share = 0.0
        pc_held = pc_share if act[A_LOCATION] > 0.5 else 0.0  # private credit is only held with asset location
        if total > 0.0:
            safe_share = min(1.0, max(needed / total, pc_held))
            if act[A_REFILL] > 0.5 and ys[Y_EQRET] < 0.0:
                safe_now = (st[S_PB] + st[S_PP] + st[S_RB] + st[S_RP] + st[S_BB] + st[S_BP]) / total
                safe_share = min(safe_share, safe_now)
        stock_logged = 1.0 - safe_share
        if act[A_LOCATION] > 0.5:
            realized += _rebalance(st, 1.0 - safe_share, min(pc_share, safe_share), False)
        else:
            realized += _rebalance(st, 1.0 - safe_share, 0.0, True)
    elif act[A_LOCATION] > 0.5:
        realized += _rebalance(st, share * (1.0 - pc_share), pc_share, False)
    else:
        realized += _rebalance(st, share, 0.0, True)

    # 8. Taxes. `realized` is the net gain; `realized_st` is the short-term part of it, taxed as ordinary income.
    realized_st = ys[Y_REALIZED_ST] + st[S_STACC]
    st[S_STACC] = 0.0
    r = tax_core(wages_taxable, interest, dividends, dividends, realized, ret_dist, conv, ss, early_base, kids, deps, cf_in, aged, realized_st)
    total_tax = r.total_tax
    portfolio_tax = total_tax - wage_tax_t
    st[S_CF] = r.cap_loss_carryforward_out

    # 9. Pay the portfolio-caused tax from the brokerage account. Gains realized by selling
    # to pay it are taxed next year; a negative amount (tax saved) is added to the account.
    due = portfolio_tax
    conv_cash = 0.0
    if conv > 0.0 and due > 0.0 and free_cash > 0.0:
        # The part of the bill caused by the conversion comes out of this year's spare wages first.
        no_conversion = tax_core(wages_taxable, interest, dividends, dividends, realized, ret_dist, 0.0, ss, early_base, kids, deps, cf_in, aged, realized_st)
        conv_cash = min(max(0.0, total_tax - no_conversion.total_tax), free_cash, due)
        due -= conv_cash
    if due > 0.0:
        _pay_tax(st, due, conv, ne)
    elif due < 0.0:
        st[S_BB] -= due

    # 10. Advisory fee, charged pro rata to every account. Gains realized on the slice sold
    # from brokerage equity are taxed next year.
    total_assets = 0.0
    for i in range(N_BALANCES):
        if i != S_BBASIS:
            total_assets += st[i]
    fee = _advisory_fee(total_assets, row[SP_FEE_BREAKPOINTS], row[SP_FEE_FLAT])
    if act[A_HARVEST] > 1.5:
        fee += hhc[HC_DI_FEE_PREMIUM] * st[S_BE]  # zero unless a sensitivity run charges a direct-indexing premium
    if fee > 0.0 and total_assets > 0.0:
        f = min(1.0, fee / total_assets)
        if st[S_LOTS] > 0.5:
            st[S_DGAIN] += _lots_sell(st, f * st[S_BE], st[S_LOTS])  # the slice of stock sold for the fee comes out of the lots
            for i in range(N_BALANCES):
                if i != S_BE and i != S_BBASIS:
                    st[i] *= 1.0 - f
        else:
            st[S_DGAIN] += f * (st[S_BE] - st[S_BBASIS])
            for i in range(N_BALANCES):
                st[i] *= 1.0 - f

    # 11. Contributions: 401(k) to the pre-tax (or Roth) account, savings to the brokerage account.
    if k > 0.0:
        if roth_401k:
            ros = st[S_RE] + st[S_RB] + st[S_RP]
            if ros > 0.0:
                st[S_RE] += k * st[S_RE] / ros
                st[S_RB] += k * st[S_RB] / ros
                st[S_RP] += k * st[S_RP] / ros
            else:
                st[S_RE] += k
        else:
            pre = st[S_PE] + st[S_PB] + st[S_PP]
            if pre > 0.0:
                st[S_PE] += k * st[S_PE] / pre
                st[S_PB] += k * st[S_PB] / pre
                st[S_PP] += k * st[S_PP] / pre
            else:
                st[S_PE] += k
    repaid_saving = min(saved_net, st[S_LOAN])  # the loan is repaid from this year's savings first
    st[S_LOAN] -= repaid_saving
    saved_net -= repaid_saving
    if saved_net > 0.0:
        brk = st[S_BE] + st[S_BB] + st[S_BP]
        to_equity = min(saved_net, saved_net * st[S_BE] / brk) if brk > 0.0 else saved_net
        to_pc = saved_net * st[S_BP] / brk if brk > 0.0 else 0.0
        if st[S_LOTS] > 0.5:
            _lots_buy(st, to_equity)
        else:
            st[S_BE] += to_equity
            st[S_BBASIS] += to_equity
        st[S_BP] += to_pc
        st[S_BB] += saved_net - to_equity - to_pc
    if roth_gap > 0.0:
        _pay_tax(st, roth_gap, 0.0, ne)
    # The short-term part of the gains those sales realized is reported next year, like the rest of them (`S_DGAIN`).
    st[S_DGAIN_ST] += st[S_STACC]
    st[S_STACC] = 0.0

    # After-tax wealth at the end of the year.
    wealth = 0.0
    pretax = 0.0
    if want_wealth or do_log:
        pretax = st[S_PE] + st[S_PB] + st[S_PP]
        owed = pretax * pretax_withdrawal_rate(pretax, ss_annual, aged)
        unrealized = max(0.0, st[S_BE] - st[S_BBASIS])
        wealth = (
            st[S_BE]
            + st[S_BB]
            + st[S_BP]
            + st[S_GB]
            - _LTCG_RATE * unrealized
            + st[S_RE]
            + st[S_RB]
            + st[S_RP]
            + pretax
            - st[S_LOAN]
            - owed
            + _LTCG_RATE * st[S_CF]
            - _LTCG_RATE * max(0.0, st[S_DGAIN])
            - st[S_UNFUNDED]
        )

    if do_log:
        equity_total = st[S_PE] + st[S_RE] + st[S_BE]
        long_term = pretax + st[S_RE] + st[S_RB] + st[S_RP] + st[S_BE] + st[S_BB] + st[S_BP]
        log[t, L_AGE] = age
        log[t, L_WAGES] = w
        log[t, L_K401] = k
        log[t, L_SS] = ss
        log[t, L_NEED] = need
        log[t, L_GOAL] = goal
        log[t, L_INTEREST] = interest
        log[t, L_DIVIDENDS] = dividends
        log[t, L_HARVEST] = harvest
        log[t, L_RETDIST] = ret_dist
        log[t, L_CONV] = conv
        log[t, L_BUCKETFLOW] = bucket_flow
        log[t, L_BUCKET] = st[S_GB]
        log[t, L_STOCKTARGET] = stock_logged
        log[t, L_EQSHARE] = equity_total / long_term if long_term > 0.0 else 0.0
        log[t, L_NETGAIN] = realized
        log[t, L_EARLYBASE] = early_base
        log[t, L_CFIN] = cf_in
        log[t, L_CFOUT] = r.cap_loss_carryforward_out
        log[t, L_KIDS] = kids
        log[t, L_DEPS] = deps
        log[t, L_WAGESTAXABLE] = wages_taxable
        log[t, L_AGI] = r.agi
        log[t, L_TAXABLE] = r.taxable_income
        log[t, L_MARGINAL] = r.marginal_federal_rate
        log[t, L_FED] = r.federal_total
        log[t, L_IL] = r.illinois_tax
        log[t, L_TOTALTAX] = total_tax
        log[t, L_WAGETAX] = wage_tax_t
        log[t, L_PORTTAX] = portfolio_tax
        log[t, L_FEE] = fee
        log[t, L_PRETAX] = pretax
        log[t, L_ROTH] = st[S_RE] + st[S_RB] + st[S_RP]
        log[t, L_BROKERAGE] = st[S_BE] + st[S_BB] + st[S_BP]
        log[t, L_WEALTH] = wealth
        log[t, L_UNREALIZED] = st[S_BE] - st[S_BBASIS]
        log[t, L_AGED] = aged
        log[t, L_RMD] = rmd
        log[t, L_PC] = st[S_PP] + st[S_RP] + st[S_BP]
        log[t, L_FREECASH] = free_cash
        log[t, L_CONVCASH] = conv_cash
        log[t, L_K401ROTH] = k if roth_401k else 0.0
        log[t, L_ROTHTAX] = extra_tax
        log[t, L_SAVING] = saved_net
        log[t, L_ROTHGAP] = roth_gap
        log[t, L_LOAN] = st[S_LOAN]
        log[t, L_BORROWED] = borrowed
        log[t, L_LOANINT] = ys[Y_LOANINT]
        log[t, L_FORCED] = ys[Y_FORCED]
        log[t, L_REPAID_SAVING] = repaid_saving
        log[t, L_REPAID_GAIN] = repaid_gain
        log[t, L_GAINHARVEST] = gain_harvest
        log[t, L_STGAIN] = realized_st
    return wealth, total_tax


# How `_run_years` treats its first year (see there).
RUN_FULL, RUN_BEGIN, RUN_REST = 0, 1, 2


@jit
def _run_years(st, ys, act, tv, hhc, row, gates, rets, wages, k401, wt, t0, t1, mode, want_last, record, path_wealth, do_log, log):
    """Simulate years t0 .. t1-1 of one household on one future, mutating the state `st`.

    `mode` says how the first year goes (every later year always goes in full):
      RUN_FULL  the policy `row` chooses each year's action (written to `act`), then the year is run
      RUN_BEGIN year t0 only (t1 = t0 + 1) up to the decision point: returns and harvesting are applied
                and `act` holds what the policy would do; the caller may change it
      RUN_REST  year t0 from the decision point on, with the action already in `act`
    The fixed strategies use RUN_FULL over the whole horizon; the adaptive planner calls RUN_BEGIN,
    decides, then RUN_REST, and its rollouts call RUN_REST then RUN_FULL to the horizon. All of them
    go through this one function, so a forced action reproduces a fixed strategy exactly.

    `rets` is (years, 3); `wages`, `k401` are (years,); `wt` is (years, 2) (the tax on wages alone with
    a pre-tax and with a Roth 401(k)). Returns (after-tax wealth after the last year if `want_last`,
    income tax paid over the years run).
    """
    taxes_paid = 0.0
    wealth = 0.0
    for t in range(t0, t1):
        w = wages[t]
        if not (mode == RUN_REST and t == t0):
            _policy_action(row, gates[t], tv, t, w, act)
            _year_begin(st, ys, tv, t, hhc, act, rets[t, 0], rets[t, 1], rets[t, 2])
            if mode == RUN_BEGIN:
                return 0.0, 0.0
        want = record or do_log or (want_last and t == t1 - 1)
        res = _year_rest(st, ys, tv, t, hhc, row, act, w, k401[t], wt[t, 0], wt[t, 1], want, do_log, log)
        taxes_paid += res[1]
        if want:
            wealth = res[0]
        if record:
            path_wealth[t] = wealth
    return wealth, taxes_paid


@jit
def _simulate_path(s, p, strat, gates, tv, init, hhc, rets, wages, k401, wage_tax, path_wealth, record, log, do_log):
    n_years = tv.shape[0]
    st = init.copy()
    _lots_start(st, strat[s])
    ys = np.zeros(NY)
    act = np.zeros(NACT)
    wealth, taxes_paid = _run_years(
        st, ys, act, tv, hhc, strat[s], gates[s], rets[p], wages[p], k401[p], wage_tax[p], 0, n_years, RUN_FULL,
        True, record, path_wealth, do_log, log,
    )
    pretax = st[S_PE] + st[S_PB] + st[S_PP]
    owed = pretax * pretax_withdrawal_rate(pretax, hhc[HC_SS], tv[n_years - 1, TV_AGED])
    return wealth, taxes_paid, owed, st[S_UNFUNDED]


@jit(parallel=True, nogil=True)
def _simulate_batch(strat, gates, tv, init, hhc, rets, wages, k401, wage_tax, out, path_wealth, record, log, log_index):
    n_policies = strat.shape[0]
    n_paths = rets.shape[0]
    for i in prange(n_policies * n_paths):
        s = i // n_paths
        p = i - s * n_paths
        pw = path_wealth[s, p] if record else path_wealth[0, 0]
        res = _simulate_path(s, p, strat, gates, tv, init, hhc, rets, wages, k401, wage_tax, pw, record, log, i == log_index)
        out[s, p, R_WEALTH] = res[0]
        out[s, p, R_TAXES] = res[1]
        out[s, p, R_PRETAX_OWED] = res[2]
        out[s, p, R_UNFUNDED] = res[3]


@jit(parallel=True, nogil=True)
def _wage_tax_table(wages, k401, tv, out):
    n_paths = wages.shape[0]
    n_years = wages.shape[1]
    for p in prange(n_paths):
        for t in range(n_years):
            # [..., 0]: the 401(k) contribution is pre-tax (taxable wages are reduced by it);
            # [..., 1]: it is Roth (taxable wages are the full wages).
            pre = tax_core(wages[p, t] - k401[p, t], 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, tv[t, TV_KIDS], tv[t, TV_DEPS], 0.0, tv[t, TV_AGED])
            roth = tax_core(wages[p, t], 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, tv[t, TV_KIDS], tv[t, TV_DEPS], 0.0, tv[t, TV_AGED])
            out[p, t, 0] = pre.total_tax
            out[p, t, 1] = roth.total_tax


# --------------------------------------------------------------------------------------------
# Python layer
# --------------------------------------------------------------------------------------------

# numba's `workqueue` threading layer (the fallback when OpenMP/TBB are unavailable) aborts the whole
# process on concurrent parallel launches, so every parallel kernel call goes through this lock.
class _KernelLock:
    """A mutex with two priorities. Foreground work (`with _KERNEL_LOCK:`, a request waiting for its plan) takes the
    lock as soon as the kernel in flight finishes. Background work (`with _KERNEL_LOCK.background():`, the adaptive
    planner's chunks of paths) also waits while foreground work is queued and for a short grace after it, so a request
    that makes several kernel calls in a row is not interleaved with long background chunks."""

    GRACE_SECONDS = 0.05

    def __init__(self) -> None:
        self._cond = threading.Condition()
        self._busy = False
        self._waiting = 0  # foreground callers waiting
        self._last_foreground = -1e9

    def _acquire(self, background: bool) -> None:
        with self._cond:
            if background:
                while self._busy or self._waiting or time.monotonic() - self._last_foreground < self.GRACE_SECONDS:
                    self._cond.wait(self.GRACE_SECONDS)  # also re-checks when the grace period has run out
            else:
                self._waiting += 1
                while self._busy:
                    self._cond.wait()
                self._waiting -= 1
            self._busy = True

    def _release(self, background: bool) -> None:
        with self._cond:
            self._busy = False
            if not background:
                self._last_foreground = time.monotonic()
            self._cond.notify_all()

    def __enter__(self) -> None:
        self._acquire(False)

    def __exit__(self, *exc) -> None:
        self._release(False)

    def background(self) -> _BackgroundLock:
        return _BackgroundLock(self)


class _BackgroundLock:
    def __init__(self, lock: _KernelLock) -> None:
        self._lock = lock

    def __enter__(self) -> None:
        self._lock._acquire(True)

    def __exit__(self, *exc) -> None:
        self._lock._release(True)


_KERNEL_LOCK = _KernelLock()


@dataclass(frozen=True)
class Policy:
    """Everything a strategy decides. The RIA baseline and Donabach strategies are both Policies."""

    stock_share: float = 0.80  # stock share of long-term money at the start of the glide
    glide_start_age: float | None = 58.0  # None: start gliding today (age-based RIA glide path)
    glide_drop: float = 0.25  # points shed between glide_start_age and 70
    private_credit: float = 0.0  # share of long-term money, held in the pre-tax account
    direct_indexing: bool = False  # harvest by stock (else fund level)
    goal_bonds: bool = False  # fund each goal in bonds four years ahead
    donabach_location: bool = True  # private credit/bonds in pre-tax, stocks in the Roth
    conversion_top: float = 0.0  # 0 = no Roth conversions, else the bracket top to fill
    conversion_every_year: bool = False  # else low-income years and retirement only
    bracket_withdrawals: bool = True  # pre-tax up to the bracket target, then brokerage, then Roth
    withdrawal_top: float = P.TOP_OF_22
    breakpoint_fees: bool = False  # RIA breakpoint schedule instead of the flat fee
    flat_fee: float = DONABACH_FLAT_FEE
    k401: str = "pretax"  # 401(k) contributions: "pretax", "roth", or "roth_low" (Roth in low-income years only)
    goal_funding: str = "sell"  # "sell" assets for a goal, or "borrow" against the taxable account (box spread)
    tax_loss_harvesting: bool = True  # False: never harvest losses (the typical advisor)
    reserve_years: int = 0  # spending reserve: years of expenses held in bonds and private credit, the rest in stocks (0 = none)
    reserve_refill_after_gains: bool = True  # with a reserve: do not sell stocks to refill it in a year stocks fell
    lot_method: str = "average"  # which tax lots a sale of brokerage stock takes: "average" (no lots), "fifo" or "hifo"
    short_term_ordinary: bool = False  # with lots: gains on lots held a year or less are taxed as ordinary income

    def row(self, current_age: float) -> np.ndarray:
        r = np.zeros(NSP)
        r[SP_STOCK] = self.stock_share
        r[SP_GLIDE_START] = current_age if self.glide_start_age is None else self.glide_start_age
        r[SP_GLIDE_DROP] = self.glide_drop
        r[SP_PC] = self.private_credit
        r[SP_DI] = float(self.direct_indexing)
        r[SP_BUCKET] = float(self.goal_bonds)
        r[SP_LOCATION] = 0.0 if self.donabach_location else 1.0
        r[SP_CONV_TOP] = self.conversion_top
        r[SP_CONV_EVERY] = float(self.conversion_every_year)
        r[SP_WD_BRACKET] = float(self.bracket_withdrawals)
        r[SP_WD_TOP] = self.withdrawal_top
        r[SP_FEE_BREAKPOINTS] = float(self.breakpoint_fees)
        r[SP_FEE_FLAT] = self.flat_fee
        r[SP_K401] = {"pretax": K401_PRETAX, "roth": K401_ROTH, "roth_low": K401_ROTH_LOW}[self.k401]
        r[SP_BORROW] = {"sell": 0.0, "borrow": 1.0}[self.goal_funding]
        r[SP_TLH] = float(self.tax_loss_harvesting)
        r[SP_RESERVE] = float(self.reserve_years)
        r[SP_REFILL] = float(self.reserve_refill_after_gains)
        r[SP_LOTS] = {"average": LOTS_AVERAGE, "fifo": LOTS_FIFO, "hifo": LOTS_HIFO}[self.lot_method]
        r[SP_STCG] = float(self.short_term_ordinary and self.lot_method != "average")
        return r

    def replace(self, **changes) -> Policy:
        return replace(self, **changes)


@dataclass(frozen=True)
class ModelOptions:
    """Alternative assumptions for sensitivity runs (`app.study.sensitivity`). The defaults are exactly the
    specification, and the app never passes anything else."""

    harvest_model: str = "spec"  # "spec" or "evidence": the direct-indexing harvest rule
    di_fee_premium: float = 0.0  # extra yearly fee on direct-indexed equity
    market: markets.Assumptions | None = None


@dataclass
class SimInputs:
    """Everything the kernel needs for one household and one set of futures."""

    n_years: int
    n_paths: int
    tv: np.ndarray  # (years, NTV)
    init: np.ndarray  # (NSTATE,)
    hhc: np.ndarray  # (NHC,)
    rets: np.ndarray  # (paths, years, 3)
    wages: np.ndarray  # (paths, years) gross household wages
    k401: np.ndarray  # (paths, years)
    wage_tax: np.ndarray  # (paths, years, 2) tax on wages alone: [..., 0] pre-tax 401(k), [..., 1] Roth 401(k)
    # What the adaptive planner needs to imagine other futures from any year (see app.sim.adaptive):
    logperm: np.ndarray | None = None  # (paths, years, 2) each earner's log permanent wage component
    inc_base: np.ndarray | None = None  # (2,) each earner's wages in the first year
    inc_growth: np.ndarray | None = None  # (2, years) real wage growth by the earner's own age each year
    inc_working: np.ndarray | None = None  # (years,) 1.0 while the household still works
    n_earners: int = 1
    market: markets.Assumptions | None = None  # the return assumptions the futures were drawn from
    seed: int = 0  # the seed the futures were drawn with (rollouts use a stream disjoint from it)

    @property
    def ages(self) -> np.ndarray:
        return self.tv[:, TV_AGE]

    @property
    def current_age(self) -> float:
        return float(self.tv[0, TV_AGE])


def goal_schedule(household: Household, n_years: int) -> np.ndarray:
    """Real dollars due in each simulated year."""
    pay = np.zeros(n_years)
    g = household.goals
    if g.home_purchase_in_years is not None and g.home_purchase_in_years < n_years:
        pay[g.home_purchase_in_years] += g.home_down_payment
    if g.college_starts_in_years is not None:
        for t in range(g.college_starts_in_years, g.college_starts_in_years + g.college_years):
            if t < n_years:
                pay[t] += g.college_annual_cost
    return pay


def _time_table(household: Household, n_years: int, expected_wages: np.ndarray) -> np.ndarray:
    g = household.goals
    ss = household.social_security
    age0 = household.primary_age
    tv = np.zeros((n_years, NTV))
    goal = goal_schedule(household, n_years)
    for t in range(n_years):
        age = age0 + t
        retired = age >= g.retirement_age
        benefit = ss.annual_benefit if age >= ss.start_age else 0.0
        tv[t, TV_AGE] = age
        tv[t, TV_RETIRED] = float(retired)
        tv[t, TV_SS] = benefit
        tv[t, TV_NEED] = max(0.0, g.retirement_spending - benefit) if retired else 0.0
        tv[t, TV_GOAL] = goal[t]
        tv[t, TV_BUCKET] = goal[t + 1 : t + 1 + BUCKET_YEARS_AHEAD].sum()
        tv[t, TV_EXPWAGE] = expected_wages[t]
        tv[t, TV_KIDS] = sum(1 for c in household.children_ages if 0 <= c + t <= P.CTC_MAX_CHILD_AGE)
        tv[t, TV_DEPS] = sum(1 for c in household.children_ages if c + t < 23)
        tv[t, TV_NEARN] = 0.0 if retired else sum(1 for person in household.people if person.wages > 0)
        tv[t, TV_AGED] = sum(1 for person in household.people if person.age + t >= P.AGED_AGE)
        tv[t, TV_SPEND] = 0.0 if retired else g.retirement_spending
    return tv


def _initial_state(household: Household) -> np.ndarray:
    a = household.accounts
    st = np.zeros(NSTATE)
    st[S_PE] = a.pretax_balance * a.pretax_equity_share
    st[S_PB] = a.pretax_balance * (1.0 - a.pretax_equity_share)
    st[S_RE] = a.roth_balance * a.roth_equity_share
    st[S_RB] = a.roth_balance * (1.0 - a.roth_equity_share)
    st[S_BE] = a.brokerage_value
    st[S_BBASIS] = a.brokerage_basis
    st[S_BB] = a.cash  # cash is held with the brokerage bonds
    return st


def build_inputs(
    household: Household,
    n_paths: int = 400,
    seed: int = markets.DEFAULT_SEED,
    deterministic: bool = False,
    shock: MarketShock | None = None,
    options: ModelOptions | None = None,
) -> SimInputs:
    """Draw the futures (or build the one deterministic path) and precompute what is shared."""
    options = options or ModelOptions()
    n_years = household.horizon_years
    if n_years + 1 > MAX_LOTS:
        raise ValueError(f"a horizon of {n_years} years needs more than the {MAX_LOTS} tax lots the simulator keeps")
    base = [p.wages for p in household.people]
    ages = [p.age for p in household.people]
    retire = household.goals.retirement_age
    n_earners = len(household.people)

    expected, expected_lp = income.household_wage_state(base, ages, retire, income.no_shocks(n_years, n_earners))
    expected = expected[0]
    if deterministic:
        rets = markets.expected_returns(n_years, options.market)
        wages = expected[None, :].copy()
        logperm = expected_lp.copy()
    else:
        rets = markets.draw_returns(n_paths, n_years, seed, options.market)
        shocks = income.draw_income_shocks(n_paths, n_years, n_earners, seed)
        wages, logperm = income.household_wage_state(base, ages, retire, shocks)
    if shock is not None:
        rets = markets.with_equity_shock(rets, shock.year, shock.equity_return)

    tv = _time_table(household, n_years, expected)
    k401 = np.minimum(P.LIMIT_401K_EMPLOYEE * tv[:, TV_NEARN][None, :], KEEP_401K_SHARE_OF_WAGES * wages)
    wage_tax = np.zeros((*wages.shape, 2))
    with _KERNEL_LOCK:
        _wage_tax_table(np.ascontiguousarray(wages), np.ascontiguousarray(k401), tv, wage_tax)

    hhc = np.zeros(NHC)
    hhc[HC_SS] = household.social_security.annual_benefit
    hhc[HC_RMD_START] = P.rmd_start_age(P.TAX_YEAR - household.primary_age)
    hhc[HC_HARVEST_MODEL] = {"spec": 0.0, "evidence": 1.0}[options.harvest_model]
    hhc[HC_DI_FEE_PREMIUM] = options.di_fee_premium
    return SimInputs(
        n_years=n_years,
        n_paths=wages.shape[0],
        tv=tv,
        init=_initial_state(household),
        hhc=hhc,
        rets=np.ascontiguousarray(rets, dtype=np.float64),
        wages=np.ascontiguousarray(wages, dtype=np.float64),
        k401=np.ascontiguousarray(k401, dtype=np.float64),
        wage_tax=wage_tax,
        logperm=np.ascontiguousarray(logperm, dtype=np.float64),
        inc_base=np.array([*base, 0.0][:2], dtype=np.float64) if n_earners < 2 else np.array(base[:2], dtype=np.float64),
        inc_growth=np.array(
            [income.growth_table(a, n_years) for a in ages] + ([np.zeros(n_years)] if n_earners < 2 else []),
            dtype=np.float64,
        ),
        inc_working=income.working_flags(ages[0], retire, n_years),
        n_earners=n_earners,
        market=options.market,
        seed=seed,
    )


@dataclass
class BatchResult:
    wealth: np.ndarray  # (policies, paths) after-tax wealth at the horizon
    taxes_paid: np.ndarray  # (policies, paths) income taxes paid over the plan
    pretax_owed: np.ndarray  # (policies, paths) tax still owed on pre-tax balances at the horizon
    unfunded: np.ndarray  # (policies, paths) obligations that could not be funded
    path_wealth: np.ndarray | None = None  # (policies, paths, years) when recorded
    log: dict[str, np.ndarray] | None = None  # year log of the requested (policy, path)


def run_batch(
    inputs: SimInputs,
    policies: list[Policy],
    gates: np.ndarray | None = None,
    record_paths: bool = False,
    log_for: tuple[int, int] | None = None,
) -> BatchResult:
    """Simulate every policy on every path. `gates` has shape (policies, years, NGATE)."""
    s_count = len(policies)
    strat = np.ascontiguousarray([p.row(inputs.current_age) for p in policies], dtype=np.float64)
    if gates is None:
        gates = np.ones((s_count, inputs.n_years, NGATE))
    gates = np.ascontiguousarray(gates, dtype=np.float64)
    out = np.zeros((s_count, inputs.n_paths, NRESULT))
    if record_paths:
        path_wealth = np.zeros((s_count, inputs.n_paths, inputs.n_years))
    else:
        path_wealth = np.zeros((1, 1, 1))
    if log_for is None:
        log, log_index = np.zeros((1, 1)), -1
    else:
        log = np.zeros((inputs.n_years, NLOG))
        log_index = log_for[0] * inputs.n_paths + log_for[1]
    with _KERNEL_LOCK:
        _simulate_batch(
            strat, gates, inputs.tv, inputs.init, inputs.hhc, inputs.rets, inputs.wages,
            inputs.k401, inputs.wage_tax, out, path_wealth, record_paths, log, log_index,
        )
    return BatchResult(
        wealth=out[:, :, R_WEALTH],
        taxes_paid=out[:, :, R_TAXES],
        pretax_owed=out[:, :, R_PRETAX_OWED],
        unfunded=out[:, :, R_UNFUNDED],
        path_wealth=path_wealth if record_paths else None,
        log={name: log[:, i].copy() for i, name in enumerate(LOG_COLUMNS)} if log_for else None,
    )


def run_forced(
    inputs: SimInputs,
    policy: Policy,
    overrides: dict[int, dict[int, float]] | None = None,
    path: int = 0,
) -> BatchResult:
    """One path under `policy` with some years' actions overridden: `overrides[t] = {A_*: value}`.

    This is the adaptive planner's own mechanism (decide after the year's returns, then act) driven
    from Python, which is how the tests force actions. The result carries the year log.
    """
    overrides = overrides or {}
    n_years = inputs.n_years
    st = inputs.init.copy()
    ys = np.zeros(NY)
    act = np.zeros(NACT)
    gates = np.ones((n_years, NGATE))
    row = policy.row(inputs.current_age)
    _lots_start(st, row)
    log = np.zeros((n_years, NLOG))
    scratch = np.zeros(n_years)
    rets = np.ascontiguousarray(inputs.rets[path])
    wages = np.ascontiguousarray(inputs.wages[path])
    k401 = np.ascontiguousarray(inputs.k401[path])
    wt = np.ascontiguousarray(inputs.wage_tax[path])
    wealth = taxes = 0.0
    for t in range(n_years):
        common = (inputs.tv, inputs.hhc, row, gates, rets, wages, k401, wt)
        _run_years(st, ys, act, *common, t, t + 1, RUN_BEGIN, False, False, scratch, False, log)
        for dim, value in overrides.get(t, {}).items():
            act[dim] = value
        w, tax = _run_years(st, ys, act, *common, t, t + 1, RUN_REST, t == n_years - 1, False, scratch, True, log)
        taxes += tax
        wealth = w if t == n_years - 1 else wealth
    pretax = st[S_PE] + st[S_PB] + st[S_PP]
    owed = pretax * float(pretax_withdrawal_rate(pretax, float(inputs.hhc[HC_SS]), float(inputs.tv[-1, TV_AGED])))
    return BatchResult(
        wealth=np.array([[wealth]]),
        taxes_paid=np.array([[taxes]]),
        pretax_owed=np.array([[owed]]),
        unfunded=np.array([[st[S_UNFUNDED]]]),
        log={name: log[:, i].copy() for i, name in enumerate(LOG_COLUMNS)},
    )


def run_detail(inputs: SimInputs, policy: Policy, gate_row: np.ndarray | None = None) -> BatchResult:
    """The year-by-year log for one policy on the first path (use a deterministic `inputs`)."""
    gates = None if gate_row is None else gate_row[None, :, :]
    return run_batch(inputs, [policy], gates=gates, log_for=(0, 0))


def initial_after_tax_wealth(household: Household) -> float:
    """After-tax wealth today, by the same formula the simulator reports each year."""
    st = _initial_state(household)
    pretax = st[S_PE] + st[S_PB] + st[S_PP]
    aged = sum(1 for person in household.people if person.age >= P.AGED_AGE)
    owed = pretax * float(pretax_withdrawal_rate(pretax, household.social_security.annual_benefit, float(aged)))
    unrealized = max(0.0, st[S_BE] - st[S_BBASIS])
    return float(
        st[S_BE] + st[S_BB] - _LTCG_RATE * unrealized + st[S_RE] + st[S_RB] + pretax - owed
    )

