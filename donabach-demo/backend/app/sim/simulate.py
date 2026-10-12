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
from app.schemas import HORIZON_AGE, Household, MarketShock
from app.sim import income, markets, mortality
from app.sim.diag import (
    D_CARRY_FEE,
    D_CARRY_TAX,
    D_CASHGIFT,
    D_DONATED,
    D_DONATED_GAIN,
    D_EARLY,
    D_END_BASIS,
    D_END_BE,
    D_FUNDDIST,
    D_FUNDDIST_ST,
    D_GAIN,
    D_PENALTY,
    D_PTW,
    D_RES0_BROKERAGE,
    D_RES0_PRETAX,
    D_RES0_ROTH,
    D_RES0_SET,
    D_RES_BROKERAGE,
    D_RES_PRETAX,
    D_RES_ROTH,
    D_RES_YEARS,
    D_SOLD,
    D_TAPE,
    D_TAX,
    D_TYPE,
    D_WAGETAX,
    D_YG,
    DG_SIZE,
    N_PURPOSES,
    NK,
    P_DISTRIBUTIONS,
    P_FEES,
    P_GIFTS,
    P_GOALS,
    P_HARVEST,
    P_OTHER,
    P_REBALANCING,
    P_RESERVE,
    P_SPENDING,
    P_TAXES,
    T_CHARITY,
    T_CONVERSIONS,
    T_DIVIDENDS,
    T_LONG_TERM,
    T_OTHER,
    T_REQUIRED,
    T_SHORT_TERM,
    T_WITHDRAWALS,
    TAPE_BUCKET,
    TAPE_DONATE,
    TAPE_FEES,
    TAPE_FORCED,
    TAPE_GOALS,
    TAPE_LOAN,
    TAPE_REBALANCE,
    TAPE_SAVING,
    TAPE_SPENDING,
    TAPE_TAXES,
    TAPE_TAXGAP,
    W_GIFTS,
    W_GOALS,
    W_REQUIRED,
    W_SPENDING,
    W_TAXES,
)

# --------------------------------------------------------------------------------------------
# Layout constants shared by the kernel and the Python wrappers
# --------------------------------------------------------------------------------------------
# State vector and tax-lot layout: see app/sim/state.py (names are re-exported here for the modules that import them
# from the simulator).
from app.sim.state import (  # noqa: E402, F401
    D_LOTC,
    D_LOTU,
    D_MAXC,
    D_PRICE,
    D_UNITS,
    DI_BUCKETS,
    DI_GMIN,
    LOTS_AVERAGE,
    LOTS_FIFO,
    LOTS_HIFO,
    LOTS_STOCK,
    MAX_LOTS,
    N_BALANCES,
    N_SCALARS,
    N_STOCKS,
    NSTATE,
    NSTATE_DI,
    S_BB,
    S_BBASIS,
    S_BE,
    S_BEST,
    S_BP,
    S_CF,
    S_DDIST,
    S_DGAIN,
    S_DGAIN_ST,
    S_FSALE,
    S_GB,
    S_LOAN,
    S_LOTC,
    S_LOTS,
    S_LOTU,
    S_PB,
    S_PE,
    S_PP,
    S_PRICE,
    S_RB,
    S_RE,
    S_RP,
    S_SINGLE,
    S_STACC,
    S_STCG,
    S_UNFUNDED,
    S_UNITS,
    S_W80,
    S_YEAR,
)
from app.sim.stocks import di_buy, di_donate, di_realize, di_sell, di_start, di_year_begin
from app.sim.stocks import lot_short_share as _lot_short_share
from app.tax import params_2026 as P
from app.tax.engine import bracket_top, liquidation_taxes, marginal_rate, pretax_withdrawal_rate, standard_deduction, tax_core

# Time-varying inputs, one row per simulated year.
(TV_AGE, TV_RETIRED, TV_SS, TV_NEED, TV_GOAL, TV_BUCKET, TV_EXPWAGE, TV_KIDS, TV_DEPS, TV_NEARN, TV_AGED, TV_SPEND, TV_GIFT) = range(13)
NTV = 13

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
    SP_DIMODEL,
    SP_DONATE,
    SP_DIST,
    SP_DISTST,
    SP_ER_E,
    SP_ER_B,
    SP_CASH,
    SP_REALIZE,
) = range(28)
NSP = 28

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
    A_DIST,  # capital gains the funds in the brokerage account distribute each year, as a share of its equity
    A_DISTST,  # the short-term share of those distributions
    A_ER_E,  # expense ratio of the equity funds held (taken from their return)
    A_ER_B,  # expense ratio of the bond funds held
    A_CASH,  # share of the portfolio held in cash (taken from the bonds)
) = range(17)
NACT = 17

# Scratch carried from the start of a year to its end (what the household saw, then did).
(
    Y_REALIZED,
    Y_RETDIST,
    Y_EARLYBASE,
    Y_CFIN,
    Y_DIVIDENDS,
    Y_INTEREST,
    Y_HARVEST,
    Y_PRETAX_OPEN,
    Y_LOANINT,
    Y_FORCED,
    Y_EQRET,
    Y_REALIZED_ST,
    Y_DIST,
    Y_DISTST,
    Y_FORCEDEQ,
    Y_FORCEDGAIN,
    Y_HARVESTST,
) = range(17)
NY = 17

# Household constants.
HC_SS = 0
HC_RMD_START = 1  # age at which required minimum distributions begin
HC_HARVEST_MODEL = 2  # the aggregate direct-indexing harvest rule: 0 the specification's, 1 the evidence-based alternative, 2 calibrated
HC_DI_FEE_PREMIUM = 3  # extra yearly fee on direct-indexed equity (0 in the specification)
HC_HARVEST_THRESHOLD = 4  # stock by stock: a lot is harvested when its cost is this far above the price (a fraction)
HC_HEIRS_RATE = 5  # the flat tax rate the heirs pay on the pre-tax balance they inherit (the "passed to heirs" valuation)
HC_REPORT_AGE = 7  # the age at which a path that runs on past it also reports its wealth (80)
HC_VALUATION = 6  # 0 the tax engine values what is owed on liquidation (`liquidation_taxes`), 1 the flat rates used before Update 4
NHC = 8

# Kernel result columns.
R_WEALTH, R_TAXES, R_PRETAX_OWED, R_UNFUNDED, R_WEALTH_HEIRS, R_FORCED, R_WEALTH80 = range(7)
NRESULT = 7

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
    "fund_distribution",
    "fund_distribution_short_term",
    "gift_cash",
    "gift_stock",
    "charitable_deduction",
    "deduction",
    "itemized",
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
    L_FUNDDIST,
    L_FUNDDIST_ST,
    L_GIFTCASH,
    L_GIFTSTOCK,
    L_CHARITY,
    L_DEDUCTION,
    L_ITEMIZED,
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
# The aggregate rule with the dispersion measured on the stock-level book instead of assumed (HC_HARVEST_MODEL 2):
# decline share, dispersion share of value a year, and the power of the basis ratio it is scaled by.
HARVEST_CAL_DECLINE = 0.85
HARVEST_CAL_DISPERSION = 0.03
HARVEST_CAL_POWER = 1.0
HARVEST_THRESHOLD = 0.01  # the stock-level book harvests a lot whose cost is more than 1% above its stock's price
HEIRS_TAX_RATE = 0.24  # see `heirs_wealth`
# The survivor phase (12.2). After the first spouse dies the survivor files as a single taxpayer, spends this share of what the couple
# did and draws this share of the household's Social Security benefit (the larger of the two benefits, taken to be 60% of their sum).
# Both are assumptions: the documents give neither (see reports/final_report.md, Update 4, for the sensitivity).
SURVIVOR_SPENDING_SHARE = 0.75
SURVIVOR_SS_SHARE = 0.60
FUND_HARVEST_TRIGGER = -0.10  # fund-level harvesting only when equities fall more than 10%
GLIDE_END_AGE = 70.0  # glide paths end here, as before the horizon moved from 70 to 80

# Breakpoint advisory fee schedule used by the RIA baseline: (upper bound, marginal fee rate).
FEE_TOPS = np.array([1_000_000.0, 3_000_000.0, 5_000_000.0, np.inf])
FEE_RATES = np.array([0.010, 0.008, 0.006, 0.005])
# The typical advisor's schedule, marginal rates by balance (SP_FEE_BREAKPOINTS 2). Veres' survey through Kitces (2023) has median
# advisory fees of almost 1.25% under $250,000, 1.00% to $1M and 0.75% over $2M, and Kitces Research (2024) a typical schedule of
# 1.00% to $1M, 0.90% at $2M and 0.75% at $5M. Envestnet's 2026 survey has an average of 0.96%. Averages under $500,000 run
# 1.1% to 1.25%: 1.15% is used for the first $500,000 (reports/final_report.md, Update 4, for what was read).
TYPICAL_FEE_TOPS = np.array([500_000.0, 1_000_000.0, 2_000_000.0, 5_000_000.0, np.inf])
TYPICAL_FEE_RATES = np.array([0.0115, 0.010, 0.009, 0.0075, 0.006])
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


@jit(inline="always")
def wants_book(row):
    """Does this policy's brokerage equity live in the direct-indexing book (100 stocks with lots)? Direct indexing, with
    the stock-level model, and tax lots (a policy on average cost keeps no lots, so its direct indexing is the aggregate rule)."""
    return row[SP_DI] > 0.5 and row[SP_DIMODEL] > 0.5 and row[SP_LOTS] > 0.5


@jit
def _lots_start(st, row):
    """Start a path: the policy's lot method and short-term switch go into the state, and with lots the whole opening
    brokerage stock position is lot 0 (long-term), at a price of 1 a unit. A path that has the direct-indexing book (its
    state vector is `NSTATE_DI` long, see `wants_book`) spreads the position over the book's stocks instead."""
    st[S_LOTS] = row[SP_LOTS]
    st[S_STCG] = row[SP_STCG]
    if wants_book(row):
        di_start(st)
    elif row[SP_LOTS] > 0.5:
        be = st[S_BE]
        st[S_PRICE] = 1.0
        st[S_UNITS] = be
        st[S_LOTU] = be
        st[S_LOTC] = st[S_BBASIS] / be if be > 0.0 else 1.0
        st[S_BEST] = 0.0 if be > 0.0 else -1.0


@jit(inline="always")
def _lots_sell(st, amount, order):
    """Sell `amount` of brokerage stock from its lots, `order` LOTS_FIFO (oldest lot first) or LOTS_HIFO (the lot bought at
    the highest price first, which is the one with the highest cost per dollar of value). Returns the realized gain; its
    short-term part, when short-term gains are taxed as ordinary income, is added to `st[S_STACC]`."""
    if order > 2.5:
        return di_sell(st, amount)
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
    if st[S_LOTS] > 2.5:
        di_buy(st, amount)
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
    if st[S_LOTS] > 2.5:
        return di_realize(st, room)
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


@jit(inline="always")
def _lots_donate(st, amount):
    """Give away `amount` of brokerage stock held more than a year, the lots with the most gain per dollar first (the lowest
    cost per unit): nothing is sold, so no gain is realized, and the lot's cost leaves with it. Only lots with a gain are given
    (a lot with a loss is worth more sold). Returns the value given, which is less than `amount` when there is not enough."""
    if amount <= 0.0 or st[S_BE] <= 0.0:
        return 0.0
    if st[S_LOTS] > 2.5:
        return di_donate(st, amount)
    if st[S_LOTS] < 0.5:
        # no lots: the account is one position at its average cost, so a gift is pro rata
        if st[S_BE] <= st[S_BBASIS]:
            return 0.0
        h = min(1.0, amount / st[S_BE])
        given = h * st[S_BE]
        st[S_BBASIS] *= 1.0 - h
        st[S_BE] -= given
        return given
    year = int(st[S_YEAR])
    n = min(year + 2, MAX_LOTS)
    price = st[S_PRICE]
    given = 0.0
    units_given = 0.0
    basis_given = 0.0
    while given < amount - 1e-9:
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
        take = min(best_u, (amount - given) / price)
        st[S_LOTU + best] = best_u - take
        given += take * price
        units_given += take
        basis_given += take * best_c
    if units_given > 0.0:
        units = st[S_UNITS] - units_given
        if units <= 1e-9:
            units = 0.0
            st[S_BBASIS] = 0.0
        else:
            st[S_BBASIS] -= basis_given
        st[S_UNITS] = units
        st[S_BE] = price * units
        st[S_BEST] = -1.0
    return given


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
def _sell_safe(st, amount, account):
    """Sell only the bonds and private credit of one account (0 pre-tax, 1 brokerage, 2 Roth), pro rata. Returns the amount sold."""
    if account < 0.5:
        b, p = S_PB, S_PP
    elif account < 1.5:
        b, p = S_BB, S_BP
    else:
        b, p = S_RB, S_RP
    safe = st[b] + st[p]
    if amount <= 0.0 or safe <= 0.0:
        return 0.0
    sold = min(amount, safe)
    g = sold / safe
    st[b] *= 1.0 - g
    st[p] *= 1.0 - g
    return sold


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
def _zero_gain_room(wages_taxable, interest, dividends, taxable_ss, ret_dist, conv, realized, realized_st, cf, std, single):
    """Dollars of further long-term gain that would still be taxed at 0% this year (income so far
    stacked under them: ordinary income, qualified dividends, gains already realized)."""
    ordinary = _ordinary_income(wages_taxable, interest, taxable_ss, ret_dist, conv, realized, realized_st, cf)
    taxable = max(0.0, ordinary + max(0.0, realized - cf) - _short_in_net(realized, realized_st, cf) + dividends - std)
    return max(0.0, (P.CG_ZERO_TOP_SINGLE if single > 0.5 else P.CG_ZERO_TOP) - taxable)


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
    if breakpoints > 1.5:
        fee = 0.0
        lower = 0.0
        for i in range(TYPICAL_FEE_TOPS.shape[0]):
            top = TYPICAL_FEE_TOPS[i]
            if total > lower:
                fee += (min(total, top) - lower) * TYPICAL_FEE_RATES[i]
            lower = top
        return fee
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
    act[A_REALIZE] = row[SP_REALIZE]
    harvest = 0.0
    if gates_row[G_HARVEST] > 0.5 and row[SP_TLH] > 0.5:
        harvest = 2.0 if row[SP_DI] > 0.5 else 1.0
    act[A_HARVEST] = harvest
    act[A_BUCKET] = 1.0 if ((row[SP_BUCKET] > 0.5 or row[SP_RESERVE] > 0.5) and gates_row[G_BUCKET] > 0.5) else 0.0
    act[A_LOCATION] = 1.0 if (row[SP_LOCATION] < 0.5 and gates_row[G_LOCATION] > 0.5) else 0.0
    act[A_WDBRACKET] = 1.0 if (row[SP_WD_BRACKET] > 0.5 and gates_row[G_WITHDRAW] > 0.5) else 0.0
    act[A_RESERVE] = row[SP_RESERVE]
    act[A_REFILL] = row[SP_REFILL]
    act[A_DIST] = row[SP_DIST]
    act[A_DISTST] = row[SP_DISTST]
    act[A_ER_E] = row[SP_ER_E]
    act[A_ER_B] = row[SP_ER_B]
    act[A_CASH] = row[SP_CASH]


@jit(inline="always")
def _year_begin(st, ys, tv, t, hhc, act, r_e, r_b, r_c, g):
    """Steps 1-2: apply this year's returns, then harvest losses. Fills the year scratch `ys`. `g` is the year's movement of
    each stock of the direct-indexing book (used only by a path that has one)."""
    age = tv[t, TV_AGE]
    early = age < _EARLY_AGE
    equity_open = st[S_BE]
    basis_open = st[S_BBASIS]
    st[S_YEAR] = t
    # Fund costs and cash (the typical advisor): equity funds lose their expense ratio, and the bond sleeve is partly cash, which
    # earns the cash return and yield and loses the bond funds' expense ratio.
    cash_of_bonds = min(1.0, act[A_CASH] / max(1e-9, 1.0 - act[A_STOCK] - act[A_PC]))
    r_e = r_e - act[A_ER_E]
    r_b = r_b - act[A_ER_B] - cash_of_bonds * (r_b - markets.CASH_REAL_RETURN)
    bond_yield = markets.BOND_INTEREST_YIELD - cash_of_bonds * (markets.BOND_INTEREST_YIELD - markets.CASH_INTEREST_YIELD)

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
    interest = bond_yield * (st[S_BB] + st[S_GB]) + markets.PRIVATE_CREDIT_INCOME_YIELD * st[S_BP]

    # 1. Returns.
    st[S_PE] *= 1.0 + r_e
    st[S_PB] *= 1.0 + r_b
    st[S_PP] *= 1.0 + r_c
    st[S_RE] *= 1.0 + r_e
    st[S_RB] *= 1.0 + r_b
    st[S_RP] *= 1.0 + r_c
    book = st[S_LOTS] > 2.5
    book_loss = 0.0
    book_loss_short = 0.0
    if book:
        # The sleeve's stocks move with the market and with their own movements, which net to nothing across the sleeve;
        # every stock pays the dividend, bought back at the new price; losses are harvested lot by lot.
        book_loss, book_loss_short = di_year_begin(
            st, t, 1.0 + r_e - markets.DIVIDEND_YIELD, g, markets.DIVIDEND_YIELD, hhc[HC_HARVEST_THRESHOLD], act[A_HARVEST] > 1.5
        )
        st[S_BBASIS] += dividends
    elif st[S_LOTS] > 0.5:
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

    # 1b. Capital gain distributions by the funds the account holds: `act[A_DIST]` of its value a year, a share `act[A_DISTST]`
    # of it short-term (paid as ordinary dividends). The household is taxed on them though it sold nothing, and the distribution
    # is reinvested, so every lot's cost rises by its share of it. (The direct-indexing book holds stocks, which distribute none.)
    dist = 0.0
    dist_st = 0.0
    if act[A_DIST] > 0.0 and not book and st[S_BE] > 0.0:
        dist = act[A_DIST] * st[S_BE]
        dist_st = act[A_DISTST] * dist
        if st[S_LOTS] > 0.5:
            bump = act[A_DIST] * st[S_PRICE]
            for i in range(min(t + 2, MAX_LOTS)):
                if st[S_LOTU + i] > 1e-9:
                    st[S_LOTC + i] += bump
        st[S_BBASIS] += dist
        realized += dist - dist_st

    # 2. Harvest losses (0 = none, 1 = fund level, 2 = stock by stock).
    harvest = 0.0
    be = st[S_BE]
    basis = st[S_BBASIS]
    mode = act[A_HARVEST]
    if book:
        # Already harvested, lot by lot, as the prices moved; the short-term part of the loss joins this year's short-term gains.
        harvest = book_loss
        realized -= harvest
        st[S_STACC] -= book_loss_short
    elif mode > 0.5 and be > 0.0:
        if mode > 1.5:
            decline = max(0.0, -r_e) * be / (1.0 + r_e)
            model = hhc[HC_HARVEST_MODEL]
            if model > 1.5:
                # The aggregate rule with the dispersion measured on the stock-level book (see app.study.harvest_calibration).
                b_now = min(1.0, basis / be)
                wanted = HARVEST_CAL_DECLINE * decline + HARVEST_CAL_DISPERSION * be * b_now**HARVEST_CAL_POWER
            elif model > 0.5:
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
    be_before_forced = st[S_BE]
    loan_interest, forced, forced_gain = _accrue_and_deleverage(st)
    ys[Y_FORCEDEQ] = be_before_forced - st[S_BE]
    ys[Y_FORCEDGAIN] = forced_gain
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
    ys[Y_DIST] = dist
    ys[Y_DISTST] = dist_st
    ys[Y_HARVESTST] = book_loss_short


@jit(inline="always")
def _need_of(tv, t, single):
    """Retirement spending net of Social Security in year t: the couple's (`TV_NEED`), or the survivor's, who spends
    `SURVIVOR_SPENDING_SHARE` of what the couple did and draws `SURVIVOR_SS_SHARE` of the household's benefit."""
    need = tv[t, TV_NEED]
    if single > 0.5 and need > 0.0:
        ss = tv[t, TV_SS]
        return max(0.0, SURVIVOR_SPENDING_SHARE * (need + ss) - SURVIVOR_SS_SHARE * ss)
    return need


@jit(inline="always")
def valuation_taxes(st, hhc, interest, dividends, aged, kids, deps):
    """What liquidating everything would cost in tax, as (tax on the pre-tax balance, tax on the gains): the tax engine's own
    figure over the years it takes (`liquidation_taxes`), or with `HC_VALUATION` 1 the flat rates used before Update 4."""
    pretax = st[S_PE] + st[S_PB] + st[S_PP]
    unrealized = max(0.0, st[S_BE] - st[S_BBASIS])
    ss = hhc[HC_SS] * (SURVIVOR_SS_SHARE if st[S_SINGLE] > 0.5 else 1.0)
    if hhc[HC_VALUATION] > 0.5:
        rate = pretax_withdrawal_rate(pretax, ss, aged)
        return pretax * rate, _LTCG_RATE * (unrealized + max(0.0, st[S_DGAIN]) - st[S_CF])
    return liquidation_taxes(
        unrealized, st[S_DGAIN], st[S_DGAIN_ST], st[S_DDIST], pretax, st[S_CF], ss, interest, dividends, aged, kids, deps, st[S_SINGLE]
    )


@jit
def _diag_tax_year(diag, wages_taxable, interest, dividends, dist_st, realized, realized_st, ret_dist, rmd, conv, ss, early_base, kids, deps, cf_in, aged, harvest, harvest_st, total_tax, single):
    """Split the year's income tax by the kind of income (`app.sim.diag`): the income is stacked in the order the tax is worked
    out and each kind's share is what it added. Then share the tax on capital gains out among the purposes of the year's sales in
    proportion to their gains (loss harvesting, a negative gain, gets the tax its losses saved)."""
    none = 0.0
    optional = ret_dist - rmd
    c0 = tax_core(wages_taxable, interest, none, none, none, none, none, ss, none, kids, deps, none, aged, none, none, none, single).total_tax
    c1 = tax_core(wages_taxable, interest, none, none, none, optional, none, ss, early_base, kids, deps, none, aged, none, none, none, single).total_tax
    c2 = tax_core(wages_taxable, interest, none, none, none, ret_dist, none, ss, early_base, kids, deps, none, aged, none, none, none, single).total_tax
    c3 = tax_core(wages_taxable, interest, none, none, none, ret_dist, conv, ss, early_base, kids, deps, none, aged, none, none, none, single).total_tax
    short = _short_in_net(realized, realized_st, cf_in)
    c4 = tax_core(wages_taxable, interest, none, none, short, ret_dist, conv, ss, early_base, kids, deps, none, aged, short, none, none, single).total_tax
    c5 = tax_core(wages_taxable, interest, dividends, dividends + dist_st, short, ret_dist, conv, ss, early_base, kids, deps, none, aged, short, none, none, single).total_tax
    c6 = tax_core(wages_taxable, interest, dividends, dividends + dist_st, realized, ret_dist, conv, ss, early_base, kids, deps, cf_in, aged, realized_st, none, none, single).total_tax
    diag[D_TYPE + T_OTHER] += c0
    diag[D_TYPE + T_WITHDRAWALS] += c1 - c0
    diag[D_TYPE + T_REQUIRED] += c2 - c1
    diag[D_TYPE + T_CONVERSIONS] += c3 - c2
    diag[D_TYPE + T_SHORT_TERM] += c4 - c3
    diag[D_TYPE + T_DIVIDENDS] += c5 - c4
    diag[D_TYPE + T_LONG_TERM] += c6 - c5
    diag[D_TYPE + T_CHARITY] += total_tax - c6
    # what the year's harvested losses saved: the tax with them minus the tax without them
    without = tax_core(wages_taxable, interest, dividends, dividends + dist_st, realized + harvest, ret_dist, conv, ss, early_base, kids, deps, cf_in, aged, realized_st + harvest_st, none, none, single).total_tax
    saved = c6 - without
    diag[D_TAX + P_HARVEST] += saved
    # The rest of the tax on gains is the tax on the year's sales and distributions as they stand: shared out in proportion to
    # their gains when it is a tax, and (a net loss, so a tax saved) in proportion to their losses.
    rest = (c4 - c3) + (c6 - c5) - saved
    positive = 0.0
    negative = 0.0
    for q in range(N_PURPOSES):
        if q != P_HARVEST:
            positive += max(0.0, diag[D_YG + q])
            negative += max(0.0, -diag[D_YG + q])
    if rest >= 0.0:
        if positive > 0.0:
            for q in range(N_PURPOSES):
                if q != P_HARVEST and diag[D_YG + q] > 0.0:
                    diag[D_TAX + q] += rest * diag[D_YG + q] / positive
        else:
            diag[D_TAX + P_OTHER] += rest
    else:
        if negative > 0.0:
            for q in range(N_PURPOSES):
                if q != P_HARVEST and diag[D_YG + q] < 0.0:
                    diag[D_TAX + q] += rest * (-diag[D_YG + q]) / negative
        else:
            diag[D_TAX + P_HARVEST] += rest


@jit(inline="always")
def _diag_step(diag, t, purpose, tape_slot, sold, gain, change):
    """Book one step's sale of brokerage stock: `sold` and `gain` under `purpose`, and the signed `change` in equity on the tape."""
    diag[D_SOLD + purpose] += sold
    diag[D_GAIN + purpose] += gain
    diag[D_YG + purpose] += gain
    diag[D_TAPE + t * NK + tape_slot] += change


@jit(inline="always")
def _year_rest(st, ys, tv, t, hhc, row, act, w, k, wt_pre, wt_roth, single, want_wealth, do_log, log, diag, do_diag):
    """Steps 3-11 for the action `act`. Returns (after-tax wealth if `want_wealth`, total income tax). With `do_diag` the
    step also fills the path's diagnostic row `diag` (see `app.sim.diag`; without it `diag` is never touched)."""
    age = tv[t, TV_AGE]
    # A surviving spouse (single = 1) files as a single taxpayer, spends less and draws the larger of the two benefits (the constants above).
    st[S_SINGLE] = single
    ss = tv[t, TV_SS] * (SURVIVOR_SS_SHARE if single > 0.5 else 1.0)
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
    gift = tv[t, TV_GIFT]
    gift_wages = min(gift, spare)  # a charitable gift is paid out of spare wages first (step 3c)
    spare -= gift_wages
    free_cash = max(0.0, spare - uncovered)
    roth_gap = max(0.0, uncovered - spare)  # extra tax even spare wages cannot cover: paid from the portfolio
    early = age < _EARLY_AGE
    aged = tv[t, TV_AGED]
    std = standard_deduction(aged, single)

    realized = ys[Y_REALIZED]
    ret_dist = ys[Y_RETDIST]
    early_base = ys[Y_EARLYBASE]
    cf_in = ys[Y_CFIN]
    dividends = ys[Y_DIVIDENDS]
    interest = ys[Y_INTEREST]
    harvest = ys[Y_HARVEST]
    wd_bracket = act[A_WDBRACKET] > 0.5
    wd_top = bracket_top(row[SP_WD_TOP], single)
    conv_top = bracket_top(act[A_CONV_TOP], single)
    dist_st = ys[Y_DISTST]  # the short-term part of fund distributions is paid as ordinary dividends
    interest_o = interest + dist_st  # ordinary income other than wages, for the bracket rooms below

    track = do_diag
    be_mark = st[S_BE]
    realized_mark = realized
    carry_tax = 0.0
    carry_fee = 0.0
    if track:
        carry_tax = diag[D_CARRY_TAX]  # gains realized selling for last year's tax and fee are reported this year
        carry_fee = diag[D_CARRY_FEE]
        diag[D_CARRY_TAX] = 0.0
        diag[D_CARRY_FEE] = 0.0
        for q in range(N_PURPOSES):
            diag[D_YG + q] = 0.0
        diag[D_YG + P_TAXES] = carry_tax
        diag[D_YG + P_FEES] = carry_fee
        distributed = ys[Y_DIST] - dist_st
        other_gain = ys[Y_FORCEDGAIN] - ys[Y_LOANINT]
        diag[D_YG + P_DISTRIBUTIONS] = distributed
        diag[D_GAIN + P_DISTRIBUTIONS] += distributed
        diag[D_YG + P_OTHER] = other_gain
        diag[D_GAIN + P_OTHER] += other_gain
        diag[D_SOLD + P_OTHER] += ys[Y_FORCEDEQ]
        diag[D_GAIN + P_HARVEST] -= harvest
        diag[D_FUNDDIST] += ys[Y_DIST]
        diag[D_FUNDDIST_ST] += dist_st
        diag[D_TAPE + t * NK + TAPE_FORCED] -= ys[Y_FORCEDEQ]
        diag[D_WAGETAX] += wage_tax_t

    # 3a. Required minimum distribution: the prior year-end pre-tax balance over the Uniform
    # Lifetime Table period, withdrawn from pre-tax (taxable income) and spent first on goals
    # and spending; whatever is not needed goes to the brokerage account.
    rmd = 0.0
    if age >= hhc[HC_RMD_START]:
        rmd = _sell_pretax(st, ys[Y_PRETAX_OPEN] / _ult_period(age), ne)
        ret_dist += rmd
    rmd_cash = rmd
    if track:
        diag[D_PTW + W_REQUIRED] += rmd
    pt_mark = ret_dist

    equity_before = st[S_PE] + st[S_RE] + st[S_BE]  # for the forced-sale count below (what goals and spending sell)

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
        if due > 0.0 and ne > 0.5 and ys[Y_EQRET] < 0.0:
            # the reserve is spent first when stocks have fallen, in whichever account it sits (see step 4)
            due -= _sell_safe(st, due, 1.0)
            due -= _sell_safe(st, due, 2.0)
            if not early:
                taken = _sell_safe(st, due, 0.0)
                ret_dist += taken
                due -= taken
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
    if track:
        _diag_step(diag, t, P_GOALS, TAPE_GOALS, max(0.0, be_mark - st[S_BE]), realized - realized_mark, st[S_BE] - be_mark)
        diag[D_PTW + W_GOALS] += ret_dist - pt_mark
        be_mark = st[S_BE]
        realized_mark = realized
        pt_mark = ret_dist

    # 3c. Charitable gifts. Spare wages paid what they could (above); the rest is paid out of the portfolio with the retirement
    # spending (step 4). A policy that gives lots gives stock held over a year with the most gain per dollar instead of cash:
    # nothing is sold, so no gain is realized, and the cash it would have given out of wages is saved (step 11) so that the
    # household's spending is the same either way.
    gift_stock = 0.0
    unrealized_mark = st[S_BE] - st[S_BBASIS]
    if gift > 0.0 and row[SP_DONATE] > 0.5:
        gift_stock = _lots_donate(st, gift)
    gift_cash = gift - gift_stock
    from_wages = min(gift_cash, gift_wages)
    gift_portfolio = gift_cash - from_wages
    reinvest = gift_wages - from_wages
    if track:
        diag[D_DONATED] += gift_stock
        diag[D_DONATED_GAIN] += unrealized_mark - (st[S_BE] - st[S_BBASIS])
        diag[D_CASHGIFT] += gift_cash
        diag[D_TAPE + t * NK + TAPE_DONATE] += st[S_BE] - be_mark
        be_mark = st[S_BE]

    # 4. Withdraw retirement spending (net of Social Security) and the part of the gift that spare wages did not pay.
    need_spend = _need_of(tv, t, single)
    need = need_spend + gift_portfolio
    spend_share = need_spend / need if need > 0.0 else 1.0
    if need > 0.0:
        from_rmd = min(rmd_cash, need)
        rmd_cash -= from_rmd
        remaining = need - from_rmd
        if remaining > 0.0 and ne > 0.5 and ys[Y_EQRET] < 0.0:
            # A spending reserve is there to be spent when stocks have fallen, wherever the account holding it is: the bonds and
            # private credit of every account go first (pre-tax within the bracket target, unless before 59 1/2, then the taxable
            # account, then the Roth), and stocks are sold only for what they cannot cover.
            if not early:
                ordinary = _ordinary_income(wages_taxable, interest_o, taxable_ss, ret_dist, 0.0, realized, ys[Y_REALIZED_ST] + st[S_STACC], cf_in)
                taken = _sell_safe(st, min(remaining, max(0.0, wd_top + std - ordinary)), 0.0)
                ret_dist += taken
                remaining -= taken
            remaining -= _sell_safe(st, remaining, 1.0)
            remaining -= _sell_safe(st, remaining, 2.0)
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
            ordinary = _ordinary_income(wages_taxable, interest_o, taxable_ss, ret_dist, 0.0, realized, ys[Y_REALIZED_ST] + st[S_STACC], cf_in)
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
    if ys[Y_EQRET] < 0.0 and equity_before - (st[S_PE] + st[S_RE] + st[S_BE]) > 1.0:
        st[S_FSALE] += 1.0  # stocks were sold to pay for goals or spending in a year they fell
    if track:
        dg_sold = max(0.0, be_mark - st[S_BE])
        dg_gain = realized - realized_mark
        dg_pt = ret_dist - pt_mark
        _diag_step(diag, t, P_SPENDING, TAPE_SPENDING, dg_sold * spend_share, dg_gain * spend_share, st[S_BE] - be_mark)
        _diag_step(diag, t, P_GIFTS, TAPE_SPENDING, dg_sold * (1.0 - spend_share), dg_gain * (1.0 - spend_share), 0.0)
        diag[D_PTW + W_SPENDING] += dg_pt * spend_share
        diag[D_PTW + W_GIFTS] += dg_pt * (1.0 - spend_share)
        be_mark = st[S_BE]
        realized_mark = realized

    # 5. Roth conversion: fill the chosen bracket, if the action asks for it. The tax on it can be
    # paid from the taxable account (cash included) and from this year's wages once taxes, 401(k),
    # brokerage savings and normal spending are covered, but never out of the converted dollars.
    # Before retirement normal spending is taken to be what the household plans to spend in
    # retirement; the documents do not say what it spends today.
    conv = 0.0
    if conv_top > 0.0:
        ordinary = _ordinary_income(wages_taxable, interest_o, taxable_ss, ret_dist, 0.0, realized, ys[Y_REALIZED_ST] + st[S_STACC], cf_in)
        room = max(0.0, conv_top + std - ordinary)
        pre = st[S_PE] + st[S_PB] + st[S_PP]
        funds = st[S_BE] + st[S_BB] + st[S_BP] + free_cash
        affordable = funds / marginal_rate(conv_top - 1.0, single)
        conv = min(room, pre, affordable)
        if conv > 0.0:
            _convert_to_roth(st, conv / pre)

    # 5b. Realize gains up to the top of the 0% capital-gain bracket (an action only the adaptive planner
    # takes): sell and immediately rebuy the equity, so nothing moves but the basis, which steps up.
    gain_harvest = 0.0
    if act[A_REALIZE] > 0.5:
        unrealized = st[S_BE] - st[S_BBASIS]
        if unrealized > 0.0:
            room = _zero_gain_room(wages_taxable, interest_o, dividends, taxable_ss, ret_dist, conv, realized, ys[Y_REALIZED_ST] + st[S_STACC], cf_in, std, single)
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
    if track:
        _diag_step(diag, t, P_RESERVE, TAPE_BUCKET, max(0.0, be_mark - st[S_BE]), realized - realized_mark, st[S_BE] - be_mark)
        be_mark = st[S_BE]
        realized_mark = realized

    # 6b. Repay the loan in a low-tax year by selling appreciated holdings: realize gains only up to
    # the top of the 0% capital-gain bracket (nothing to realize means the sale is tax-free anyway).
    repaid_gain = 0.0
    if st[S_LOAN] > 0.0 and borrowed <= 0.0:  # not in the year it was borrowed
        room = _zero_gain_room(wages_taxable, interest_o, dividends, taxable_ss, ret_dist, conv, realized, ys[Y_REALIZED_ST] + st[S_STACC], cf_in, std, single)
        if room > 0.0:
            value = st[S_BE] + st[S_BB] + st[S_BP]
            embedded = (st[S_BE] - st[S_BBASIS]) / value if value > 0.0 else 0.0
            amount = st[S_LOAN] if embedded <= 0.0 else min(st[S_LOAN], room / embedded)
            repaid_gain, gain = _sell_brokerage(st, amount, 0.0)
            realized += gain
            st[S_LOAN] -= repaid_gain
    if track:
        _diag_step(diag, t, P_OTHER, TAPE_LOAN, max(0.0, be_mark - st[S_BE]), realized - realized_mark, st[S_BE] - be_mark)
        be_mark = st[S_BE]
        realized_mark = realized

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
                needed += _need_of(tv, t + j, single)
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
    if track:
        # (in the reserve policy the rebalance is what refills the reserve)
        _diag_step(
            diag, t, P_RESERVE if act[A_RESERVE] > 0.5 else P_REBALANCING, TAPE_REBALANCE,
            max(0.0, be_mark - st[S_BE]), realized - realized_mark, st[S_BE] - be_mark,
        )
        be_mark = st[S_BE]
        realized_mark = realized

    # 8. Taxes. `realized` is the net gain; `realized_st` is the short-term part of it, taxed as ordinary income. The short-term
    # part of fund distributions is ordinary dividends, and a gift is a deduction (`tax_core`).
    realized_st = ys[Y_REALIZED_ST] + st[S_STACC]
    st[S_STACC] = 0.0
    r = tax_core(wages_taxable, interest, dividends, dividends + dist_st, realized, ret_dist, conv, ss, early_base, kids, deps, cf_in, aged, realized_st, gift_cash, gift_stock, single)
    total_tax = r.total_tax
    if track:
        diag[D_PENALTY] += r.early_withdrawal_penalty
        diag[D_EARLY] += early_base
        _diag_tax_year(
            diag, wages_taxable, interest, dividends, dist_st, realized, realized_st, ret_dist, rmd, conv, ss, early_base, kids,
            deps, cf_in, aged, ys[Y_HARVEST], ys[Y_HARVESTST], total_tax, single,
        )
    portfolio_tax = total_tax - wage_tax_t
    st[S_CF] = r.cap_loss_carryforward_out

    # 9. Pay the portfolio-caused tax from the brokerage account. Gains realized by selling
    # to pay it are taxed next year; a negative amount (tax saved) is added to the account.
    due = portfolio_tax
    conv_cash = 0.0
    if conv > 0.0 and due > 0.0 and free_cash > 0.0:
        # The part of the bill caused by the conversion comes out of this year's spare wages first.
        no_conversion = tax_core(wages_taxable, interest, dividends, dividends + dist_st, realized, ret_dist, 0.0, ss, early_base, kids, deps, cf_in, aged, realized_st, gift_cash, gift_stock, single)
        conv_cash = min(max(0.0, total_tax - no_conversion.total_tax), free_cash, due)
        due -= conv_cash
    dgain_mark = st[S_DGAIN]
    ddist_mark = st[S_DDIST]
    if due > 0.0:
        _pay_tax(st, due, conv, ne)
    elif due < 0.0:
        st[S_BB] -= due
    if track:
        paid_gain = st[S_DGAIN] - dgain_mark
        diag[D_SOLD + P_TAXES] += max(0.0, be_mark - st[S_BE])
        diag[D_GAIN + P_TAXES] += paid_gain
        diag[D_CARRY_TAX] += paid_gain
        diag[D_PTW + W_TAXES] += st[S_DDIST] - ddist_mark
        diag[D_TAPE + t * NK + TAPE_TAXES] += st[S_BE] - be_mark
        be_mark = st[S_BE]

    # 10. Advisory fee, charged pro rata to every account. Gains realized on the slice sold
    # from brokerage equity are taxed next year.
    total_assets = 0.0
    for i in range(N_BALANCES):
        if i != S_BBASIS:
            total_assets += st[i]
    fee = _advisory_fee(total_assets, row[SP_FEE_BREAKPOINTS], row[SP_FEE_FLAT])
    if act[A_HARVEST] > 1.5:
        fee += hhc[HC_DI_FEE_PREMIUM] * st[S_BE]  # zero unless a sensitivity run charges a direct-indexing premium
    dgain_mark = st[S_DGAIN]
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
    if track:
        fee_gain = st[S_DGAIN] - dgain_mark
        diag[D_SOLD + P_FEES] += max(0.0, be_mark - st[S_BE])
        diag[D_GAIN + P_FEES] += fee_gain
        diag[D_CARRY_FEE] += fee_gain
        diag[D_TAPE + t * NK + TAPE_FEES] += st[S_BE] - be_mark
        be_mark = st[S_BE]

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
    saved_net += reinvest  # the cash a gift of stock saved the household (step 3c)
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
    if track:
        diag[D_TAPE + t * NK + TAPE_SAVING] += st[S_BE] - be_mark
        be_mark = st[S_BE]
    dgain_mark = st[S_DGAIN]
    if roth_gap > 0.0:
        _pay_tax(st, roth_gap, 0.0, ne)
    if track:
        gap_gain = st[S_DGAIN] - dgain_mark
        diag[D_SOLD + P_TAXES] += max(0.0, be_mark - st[S_BE])
        diag[D_GAIN + P_TAXES] += gap_gain
        diag[D_CARRY_TAX] += gap_gain
        diag[D_TAPE + t * NK + TAPE_TAXGAP] += st[S_BE] - be_mark
    # The short-term part of the gains those sales realized is reported next year, like the rest of them (`S_DGAIN`).
    st[S_DGAIN_ST] += st[S_STACC]
    st[S_STACC] = 0.0

    if track and tv[t, TV_RETIRED] > 0.5:
        # where the spending reserve (the safe assets) sits at the end of a retired year
        held_pretax = st[S_PB] + st[S_PP]
        held_roth = st[S_RB] + st[S_RP]
        held_brokerage = st[S_BB] + st[S_BP] + st[S_GB]
        diag[D_RES_PRETAX] += held_pretax
        diag[D_RES_ROTH] += held_roth
        diag[D_RES_BROKERAGE] += held_brokerage
        diag[D_RES_YEARS] += 1.0
        if diag[D_RES0_SET] < 0.5:
            diag[D_RES0_PRETAX] = held_pretax
            diag[D_RES0_ROTH] = held_roth
            diag[D_RES0_BROKERAGE] = held_brokerage
            diag[D_RES0_SET] = 1.0

    # After-tax wealth at the end of the year.
    wealth = 0.0
    pretax = 0.0
    report = age + 1.0 == hhc[HC_REPORT_AGE]  # the year in which the reporting age's birthday comes at its end
    if want_wealth or do_log or report:
        pretax = st[S_PE] + st[S_PB] + st[S_PP]
        val_pretax, val_gains = valuation_taxes(st, hhc, interest, dividends, aged, kids, deps)
        owed = val_pretax
        wealth = (
            st[S_BE]
            + st[S_BB]
            + st[S_BP]
            + st[S_GB]
            + st[S_RE]
            + st[S_RB]
            + st[S_RP]
            + pretax
            - st[S_LOAN]
            - owed
            - val_gains
            - st[S_UNFUNDED]
        )
        if report:
            st[S_W80] = wealth

    if do_log:
        equity_total = st[S_PE] + st[S_RE] + st[S_BE]
        long_term = pretax + st[S_RE] + st[S_RB] + st[S_RP] + st[S_BE] + st[S_BB] + st[S_BP]
        log[t, L_AGE] = age
        log[t, L_WAGES] = w
        log[t, L_K401] = k
        log[t, L_SS] = ss
        log[t, L_NEED] = need_spend
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
        log[t, L_FUNDDIST] = ys[Y_DIST]
        log[t, L_FUNDDIST_ST] = dist_st
        log[t, L_GIFTCASH] = gift_cash
        log[t, L_GIFTSTOCK] = gift_stock
        log[t, L_CHARITY] = r.charitable_deduction
        log[t, L_DEDUCTION] = r.deduction
        log[t, L_ITEMIZED] = r.itemized
    return wealth, total_tax


# How `_run_years` treats its first year (see there).
RUN_FULL, RUN_BEGIN, RUN_REST = 0, 1, 2


@jit
def _run_years(st, ys, act, tv, hhc, row, gates, rets, wages, k401, wt, zg, t0, t1, mode, want_last, record, path_wealth, do_log, log, diag, do_diag):
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
    a pre-tax and with a Roth 401(k)); `zg` is (years, N_STOCKS), each stock's own movement of the direct-indexing book (any
    array with a row to spare when the path has no book). `diag` is the path's diagnostic row, written only with `do_diag`
    (`app.sim.diag`). Returns (after-tax wealth after the last year if `want_last`, income tax paid over the years run).
    """
    taxes_paid = 0.0
    wealth = 0.0
    for t in range(t0, t1):
        w = wages[t]
        if not (mode == RUN_REST and t == t0):
            _policy_action(row, gates[t], tv, t, w, act)
            _year_begin(st, ys, tv, t, hhc, act, rets[t, 0], rets[t, 1], rets[t, 2], zg[t if t < zg.shape[0] else 0])
            if mode == RUN_BEGIN:
                return 0.0, 0.0
        want = record or do_log or (want_last and t == t1 - 1)
        res = _year_rest(st, ys, tv, t, hhc, row, act, w, k401[t], wt[t, 0], wt[t, 1], wt[t, 2], want, do_log, log, diag, do_diag)
        taxes_paid += res[1]
        if want:
            wealth = res[0]
        if record:
            path_wealth[t] = wealth
    return wealth, taxes_paid


@jit(inline="always")
def heirs_wealth(st, hhc, interest, dividends, aged, kids, deps):
    """After-tax wealth if the household dies with what it has and its heirs inherit it (the second valuation at the horizon;
    `_year_rest` has the first, liquidating everything). Taxable assets pass with a step-up in basis (IRC 1014), so the
    unrealized gain is never taxed; the Roth is theirs untaxed; the pre-tax accounts are taxed at the heirs' flat rate
    `hhc[HC_HEIRS_RATE]` (`HEIRS_TAX_RATE`: they must be emptied within ten years, and the heirs are at their prime earning
    years). A loan is still owed, gains already realized to pay tax or fees are still taxed on the owner's last return
    (the engine's tax on them alone, or the old flat rate), and an unused capital-loss carryforward is worth nothing to them
    (it ends with the owner's last return)."""
    pretax = st[S_PE] + st[S_PB] + st[S_PP]
    if hhc[HC_VALUATION] > 0.5:
        last_return = _LTCG_RATE * max(0.0, st[S_DGAIN])
    else:
        ss = hhc[HC_SS] * (SURVIVOR_SS_SHARE if st[S_SINGLE] > 0.5 else 1.0)
        paid = liquidation_taxes(
            0.0, st[S_DGAIN], st[S_DGAIN_ST], st[S_DDIST], 0.0, 0.0, ss, interest, dividends, aged, kids, deps, st[S_SINGLE]
        )
        last_return = paid[0] + paid[1]
    return (
        st[S_BE]
        + st[S_BB]
        + st[S_BP]
        + st[S_GB]
        + st[S_RE]
        + st[S_RB]
        + st[S_RP]
        + pretax * (1.0 - hhc[HC_HEIRS_RATE])
        - st[S_LOAN]
        - last_return
        - st[S_UNFUNDED]
    )


@jit(inline="always")
def terminal_values(st, ys, hhc, tv, n_years):
    """(pre-tax tax owed on liquidation, wealth passed to heirs) after the last year, from the state and the last year's scratch."""
    aged = tv[n_years - 1, TV_AGED]
    kids = tv[n_years - 1, TV_KIDS]
    deps = tv[n_years - 1, TV_DEPS]
    owed = valuation_taxes(st, hhc, ys[Y_INTEREST], ys[Y_DIVIDENDS], aged, kids, deps)[0]
    return owed, heirs_wealth(st, hhc, ys[Y_INTEREST], ys[Y_DIVIDENDS], aged, kids, deps)


@jit
def _simulate_path(s, p, strat, gates, tv, init, hhc, rets, wages, k401, wage_tax, zs, path_wealth, record, log, do_log, diag, do_diag):
    n_years = tv.shape[0]
    if wants_book(strat[s]):
        st = np.zeros(NSTATE_DI)  # the direct-indexing book follows the base state
        st[:NSTATE] = init[:NSTATE]
    else:
        st = init.copy()
    _lots_start(st, strat[s])
    ys = np.zeros(NY)
    act = np.zeros(NACT)
    wealth, taxes_paid = _run_years(
        st, ys, act, tv, hhc, strat[s], gates[s], rets[p], wages[p], k401[p], wage_tax[p], zs[p], 0, n_years, RUN_FULL,
        True, record, path_wealth, do_log, log, diag, do_diag,
    )
    owed, heirs = terminal_values(st, ys, hhc, tv, n_years)
    if do_diag:
        diag[D_END_BE] = st[S_BE]
        diag[D_END_BASIS] = st[S_BBASIS]
    return wealth, taxes_paid, owed, st[S_UNFUNDED], heirs, st[S_FSALE], st[S_W80]


@jit(parallel=True, nogil=True)
def _simulate_batch(strat, gates, tv, init, hhc, rets, wages, k401, wage_tax, zs, out, path_wealth, record, log, log_index, diag, want_diag):
    n_policies = strat.shape[0]
    n_paths = rets.shape[0]
    # Path-major: a stretch of consecutive iterations visits every policy, so a thread's share has its direct-indexing
    # policies (about thirty times the work of the others) in proportion, wherever they sit in the list.
    for i in prange(n_policies * n_paths):
        p = i // n_policies
        s = i - p * n_policies
        pw = path_wealth[s, p] if record else path_wealth[0, 0]
        dg = diag[s, p] if want_diag else diag[0, 0]
        res = _simulate_path(s, p, strat, gates, tv, init, hhc, rets, wages, k401, wage_tax, zs, pw, record, log, i == log_index, dg, want_diag)
        out[s, p, R_WEALTH] = res[0]
        out[s, p, R_TAXES] = res[1]
        out[s, p, R_PRETAX_OWED] = res[2]
        out[s, p, R_UNFUNDED] = res[3]
        out[s, p, R_WEALTH_HEIRS] = res[4]
        out[s, p, R_FORCED] = res[5]
        out[s, p, R_WEALTH80] = res[6]


@jit(parallel=True, nogil=True)
def _wage_tax_table(wages, k401, tv, single, out):
    n_paths = wages.shape[0]
    n_years = wages.shape[1]
    for p in prange(n_paths):
        for t in range(n_years):
            sg = single[p, t]
            # [..., 0]: the 401(k) contribution is pre-tax (taxable wages are reduced by it);
            # [..., 1]: it is Roth (taxable wages are the full wages); [..., 2]: the household files as a single taxpayer this year.
            pre = tax_core(wages[p, t] - k401[p, t], 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, tv[t, TV_KIDS], tv[t, TV_DEPS], 0.0, tv[t, TV_AGED], 0.0, 0.0, 0.0, sg)
            roth = tax_core(wages[p, t], 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, tv[t, TV_KIDS], tv[t, TV_DEPS], 0.0, tv[t, TV_AGED], 0.0, 0.0, 0.0, sg)
            out[p, t, 0] = pre.total_tax
            out[p, t, 1] = roth.total_tax
            out[p, t, 2] = sg


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
    di_model: str = "stock"  # with direct indexing: "stock" (100 stocks with their own lots) or "aggregate" (the rule on the account's totals)
    donate_lots: bool = False  # charitable gifts: give the lots with the most gain per dollar (held over a year) instead of cash
    fund_distribution: float = 0.0  # capital gains the funds in the brokerage account distribute each year, as a share of their value
    fund_distribution_short_term: float = 0.0  # the share of those distributions that is short-term (paid as ordinary dividends)
    typical_fee_schedule: bool = False  # the typical advisor's marginal fee schedule (higher under $500,000) instead of `breakpoint_fees`
    fund_expense_equity: float = 0.0  # expense ratio of the equity funds, taken from their return
    fund_expense_bond: float = 0.0  # expense ratio of the bond funds
    cash_share: float = 0.0  # share of the portfolio held in cash instead of bonds
    gain_harvesting: bool = False  # each year realize gains up to the top of the 0% capital-gain bracket (sell and rebuy: only the basis steps up)

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
        r[SP_FEE_BREAKPOINTS] = 2.0 if self.typical_fee_schedule else float(self.breakpoint_fees)
        r[SP_FEE_FLAT] = self.flat_fee
        r[SP_K401] = {"pretax": K401_PRETAX, "roth": K401_ROTH, "roth_low": K401_ROTH_LOW}[self.k401]
        r[SP_BORROW] = {"sell": 0.0, "borrow": 1.0}[self.goal_funding]
        r[SP_TLH] = float(self.tax_loss_harvesting)
        r[SP_RESERVE] = float(self.reserve_years)
        r[SP_REFILL] = float(self.reserve_refill_after_gains)
        r[SP_LOTS] = {"average": LOTS_AVERAGE, "fifo": LOTS_FIFO, "hifo": LOTS_HIFO}[self.lot_method]
        r[SP_STCG] = float(self.short_term_ordinary and self.lot_method != "average")
        r[SP_DIMODEL] = {"aggregate": 0.0, "stock": 1.0}[self.di_model]
        r[SP_DONATE] = float(self.donate_lots)
        r[SP_DIST] = self.fund_distribution
        r[SP_DISTST] = self.fund_distribution_short_term
        r[SP_ER_E] = self.fund_expense_equity
        r[SP_ER_B] = self.fund_expense_bond
        r[SP_CASH] = self.cash_share
        r[SP_REALIZE] = float(self.gain_harvesting)
        return r

    def replace(self, **changes) -> Policy:
        return replace(self, **changes)


@dataclass(frozen=True)
class ModelOptions:
    """Alternative assumptions for sensitivity runs (`app.study.sensitivity`). The defaults are exactly the
    specification, and the app never passes anything else."""

    harvest_model: str = "calibrated"  # the aggregate direct-indexing harvest rule: "spec" (3% dispersion), "evidence" or "calibrated"
    di_fee_premium: float = 0.0  # extra yearly fee on direct-indexed equity
    market: markets.Assumptions | None = None
    idio_vol: float = markets.STOCK_IDIO_VOL  # a stock's own volatility a year, beside the market's (the direct-indexing book)
    harvest_threshold: float = HARVEST_THRESHOLD  # the direct-indexing book harvests a lot whose cost is this far above its price
    heirs_rate: float = HEIRS_TAX_RATE  # the flat rate heirs pay on the pre-tax balance (the "passed to heirs" valuation)
    valuation: str = "engine"  # how "liquidated at 80" taxes unrealized gains and pre-tax balances: "engine" or the old "flat" 15%
    survivor: bool = False  # the first spouse's death comes at the age the SSA table says; the survivor files single (see `SURVIVOR_*`)
    horizon_age: int | None = None  # simulate to this age instead of 80 (the batch then also reports its wealth at 80)


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
    stock_g: np.ndarray = None  # (paths, years, N_STOCKS) float32: each stock's own yearly movement (mean 1), for the direct-indexing book

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
        tv[t, TV_GIFT] = g.charitable_giving
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


def survivor_flags(household: Household, n_draws: int, n_years: int, seed: int) -> np.ndarray:
    """(draws, years): 1.0 in the years the household files as a single taxpayer. The two spouses' lifetimes are drawn from the SSA
    table (`app.sim.mortality`); the first death makes the other a survivor from the following year. A death before the primary earner
    retires is moved to the retirement year (the model does not follow a household whose earner dies while working), and the survivor
    is taken to live to the end of the horizon, so the results are those of a survivor who lives that long."""
    rng = np.random.default_rng(np.random.SeedSequence(seed).spawn(5)[4])
    deaths = mortality.death_years([p.age for p in household.people], n_years, rng.random((n_draws, 2)))
    retire_year = max(0, household.goals.retirement_age - household.primary_age)
    first = np.maximum(deaths.min(axis=1), retire_year)
    years = np.arange(n_years)[None, :]
    return (years > first[:, None]).astype(np.float64)


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
    n_years = household.horizon_years if options.horizon_age is None else options.horizon_age - household.primary_age
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
    single = np.zeros(wages.shape)
    if options.survivor and not deterministic and len(household.people) == 2:
        single = survivor_flags(household, wages.shape[0], n_years, seed)
    wage_tax = np.zeros((*wages.shape, 3))
    with _KERNEL_LOCK:
        _wage_tax_table(np.ascontiguousarray(wages), np.ascontiguousarray(k401), tv, np.ascontiguousarray(single), wage_tax)

    hhc = np.zeros(NHC)
    hhc[HC_SS] = household.social_security.annual_benefit
    hhc[HC_RMD_START] = P.rmd_start_age(P.TAX_YEAR - household.primary_age)
    hhc[HC_HARVEST_MODEL] = {"spec": 0.0, "evidence": 1.0, "calibrated": 2.0}[options.harvest_model]
    hhc[HC_DI_FEE_PREMIUM] = options.di_fee_premium
    hhc[HC_HARVEST_THRESHOLD] = options.harvest_threshold
    hhc[HC_HEIRS_RATE] = options.heirs_rate
    hhc[HC_VALUATION] = {"engine": 0.0, "flat": 1.0}[options.valuation]
    hhc[HC_REPORT_AGE] = float(HORIZON_AGE)
    n_draw = wages.shape[0]
    stock_z = np.random.default_rng(np.random.SeedSequence(seed).spawn(4)[3]).standard_normal(
        (n_draw, n_years, N_STOCKS), dtype=np.float32
    )
    stock_g = np.exp(np.float32(options.idio_vol) * stock_z - np.float32(0.5 * options.idio_vol**2))  # lognormal with mean 1
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
        stock_g=np.ascontiguousarray(stock_g, dtype=np.float32),
    )


@dataclass
class BatchResult:
    wealth: np.ndarray  # (policies, paths) after-tax wealth at the horizon
    taxes_paid: np.ndarray  # (policies, paths) income taxes paid over the plan
    pretax_owed: np.ndarray  # (policies, paths) tax still owed on pre-tax balances at the horizon
    unfunded: np.ndarray  # (policies, paths) obligations that could not be funded
    path_wealth: np.ndarray | None = None  # (policies, paths, years) when recorded
    log: dict[str, np.ndarray] | None = None  # year log of the requested (policy, path)
    wealth_heirs: np.ndarray | None = None  # (policies, paths) the second valuation at the horizon: passed to heirs (`heirs_wealth`)
    diag: np.ndarray | None = None  # (policies, paths, DG_SIZE) diagnostics, when asked for (`app.sim.diag`)
    wealth_at_80: np.ndarray | None = None  # (policies, paths) after-tax wealth at age 80 (the same as `wealth` when the horizon is 80)
    forced_years: np.ndarray | None = None  # (policies, paths) years the household sold stock for goals or spending in a year stocks fell


def run_batch(
    inputs: SimInputs,
    policies: list[Policy],
    gates: np.ndarray | None = None,
    record_paths: bool = False,
    log_for: tuple[int, int] | None = None,
    diagnostics: bool = False,
) -> BatchResult:
    """Simulate every policy on every path. `gates` has shape (policies, years, NGATE). `diagnostics` also fills
    `BatchResult.diag`, what each path sold, realized and paid in tax (`app.sim.diag`)."""
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
        log_index = log_for[1] * s_count + log_for[0]
    diag = np.zeros((s_count, inputs.n_paths, DG_SIZE)) if diagnostics else np.zeros((1, 1, 1))
    with _KERNEL_LOCK:
        _simulate_batch(
            strat, gates, inputs.tv, inputs.init, inputs.hhc, inputs.rets, inputs.wages,
            inputs.k401, inputs.wage_tax, inputs.stock_g, out, path_wealth, record_paths, log, log_index, diag, diagnostics,
        )
    return BatchResult(
        wealth=out[:, :, R_WEALTH],
        taxes_paid=out[:, :, R_TAXES],
        pretax_owed=out[:, :, R_PRETAX_OWED],
        unfunded=out[:, :, R_UNFUNDED],
        path_wealth=path_wealth if record_paths else None,
        log={name: log[:, i].copy() for i, name in enumerate(LOG_COLUMNS)} if log_for else None,
        wealth_heirs=out[:, :, R_WEALTH_HEIRS],
        forced_years=out[:, :, R_FORCED],
        wealth_at_80=out[:, :, R_WEALTH80],
        diag=diag if diagnostics else None,
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
    row = policy.row(inputs.current_age)
    if wants_book(row):
        st = np.zeros(NSTATE_DI)
        st[:NSTATE] = inputs.init[:NSTATE]
    else:
        st = inputs.init.copy()
    ys = np.zeros(NY)
    act = np.zeros(NACT)
    gates = np.ones((n_years, NGATE))
    _lots_start(st, row)
    log = np.zeros((n_years, NLOG))
    scratch = np.zeros(n_years)
    rets = np.ascontiguousarray(inputs.rets[path])
    wages = np.ascontiguousarray(inputs.wages[path])
    k401 = np.ascontiguousarray(inputs.k401[path])
    wt = np.ascontiguousarray(inputs.wage_tax[path])
    zg = np.ascontiguousarray(inputs.stock_g[path])
    no_diag = np.zeros(1)
    wealth = taxes = 0.0
    for t in range(n_years):
        common = (inputs.tv, inputs.hhc, row, gates, rets, wages, k401, wt, zg)
        _run_years(st, ys, act, *common, t, t + 1, RUN_BEGIN, False, False, scratch, False, log, no_diag, False)
        for dim, value in overrides.get(t, {}).items():
            act[dim] = value
        w, tax = _run_years(st, ys, act, *common, t, t + 1, RUN_REST, t == n_years - 1, False, scratch, True, log, no_diag, False)
        taxes += tax
        wealth = w if t == n_years - 1 else wealth
    owed, heirs = terminal_values(st, ys, inputs.hhc, inputs.tv, n_years)
    return BatchResult(
        wealth=np.array([[wealth]]),
        taxes_paid=np.array([[taxes]]),
        pretax_owed=np.array([[owed]]),
        unfunded=np.array([[st[S_UNFUNDED]]]),
        log={name: log[:, i].copy() for i, name in enumerate(LOG_COLUMNS)},
        wealth_heirs=np.array([[float(heirs)]]),
    )


def run_detail(inputs: SimInputs, policy: Policy, gate_row: np.ndarray | None = None) -> BatchResult:
    """The year-by-year log for one policy on the first path (use a deterministic `inputs`)."""
    gates = None if gate_row is None else gate_row[None, :, :]
    return run_batch(inputs, [policy], gates=gates, log_for=(0, 0))


def initial_after_tax_wealth(household: Household, options: ModelOptions | None = None) -> float:
    """After-tax wealth today, by the same formula the simulator reports each year (the tax engine's cost of liquidating)."""
    st = _initial_state(household)
    pretax = st[S_PE] + st[S_PB] + st[S_PP]
    aged = float(sum(1 for person in household.people if person.age >= P.AGED_AGE))
    kids = float(sum(1 for age in household.children_ages if age <= P.CTC_MAX_CHILD_AGE))
    hhc = np.zeros(NHC)
    hhc[HC_SS] = household.social_security.annual_benefit
    hhc[HC_VALUATION] = {"engine": 0.0, "flat": 1.0}[(options or ModelOptions()).valuation]
    interest = markets.BOND_INTEREST_YIELD * (st[S_BB] + st[S_GB]) + markets.PRIVATE_CREDIT_INCOME_YIELD * st[S_BP]
    dividends = markets.DIVIDEND_YIELD * st[S_BE]
    owed, gains = valuation_taxes(st, hhc, interest, dividends, aged, kids, kids)
    return float(st[S_BE] + st[S_BB] + st[S_RE] + st[S_RB] + pretax - owed - gains)
