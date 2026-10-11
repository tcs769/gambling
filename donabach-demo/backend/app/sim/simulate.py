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

# State vector. Indices 0..8 are balances that scale together when a fee is charged.
(S_PE, S_PB, S_PP, S_RE, S_RB, S_BE, S_BBASIS, S_BB, S_GB) = range(9)
S_CF, S_DGAIN, S_DDIST, S_UNFUNDED = 9, 10, 11, 12
NSTATE = 13
N_BALANCES = 9

# Time-varying inputs, one row per simulated year.
(TV_AGE, TV_RETIRED, TV_SS, TV_NEED, TV_GOAL, TV_BUCKET, TV_EXPWAGE, TV_KIDS, TV_DEPS, TV_NEARN, TV_AGED) = range(11)
NTV = 11

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
) = range(13)
NSP = 13

# Per-(policy, year) switches. 1.0 = the decision is taken, 0.0 = removed for that year.
G_CONV, G_HARVEST, G_BUCKET, G_LOCATION, G_WITHDRAW = range(5)
NGATE = 5
GATE_NAMES = ("conversion", "harvest", "bucket", "location", "withdraw")

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
) = range(10)
NACT = 10

# Scratch carried from the start of a year to its end (what the household saw, then did).
(Y_REALIZED, Y_RETDIST, Y_EARLYBASE, Y_CFIN, Y_DIVIDENDS, Y_INTEREST, Y_HARVEST, Y_PRETAX_OPEN) = range(8)
NY = 8

# Household constants.
HC_SS = 0
HC_RMD_START = 1  # age at which required minimum distributions begin
NHC = 2

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
def _sell_brokerage(st, amount):
    """Sell `amount` pro rata across brokerage equity and bonds. Returns (sold, realized gain)."""
    be = st[S_BE]
    total = be + st[S_BB]
    if amount <= 0.0 or total <= 0.0:
        return 0.0, 0.0
    f = min(1.0, amount / total)
    gain = f * (be - st[S_BBASIS])
    st[S_BBASIS] *= 1.0 - f
    st[S_BE] = be * (1.0 - f)
    st[S_BB] *= 1.0 - f
    return f * total, gain


@jit
def _sell_roth(st, amount):
    total = st[S_RE] + st[S_RB]
    if amount <= 0.0 or total <= 0.0:
        return 0.0
    f = min(1.0, amount / total)
    st[S_RE] *= 1.0 - f
    st[S_RB] *= 1.0 - f
    return f * total


@jit
def _sell_pretax(st, amount):
    total = st[S_PE] + st[S_PB] + st[S_PP]
    if amount <= 0.0 or total <= 0.0:
        return 0.0
    f = min(1.0, amount / total)
    st[S_PE] *= 1.0 - f
    st[S_PB] *= 1.0 - f
    st[S_PP] *= 1.0 - f
    return f * total


@jit
def _ordinary_income(wages_taxable, interest, taxable_ss, ret_dist, conv, realized, cf):
    """Ordinary income so far: wages, interest, SS, withdrawals, conversions, and any capital
    loss deduction (net losses offset up to $3,000 of ordinary income)."""
    net = realized - cf
    loss_deduction = 0.0
    if net < 0.0:
        loss_deduction = min(P.CAP_LOSS_LIMIT, -net)
    return wages_taxable + interest + taxable_ss + ret_dist + conv - loss_deduction


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

    uniform: the same mix in every account (the RIA approach).
    Otherwise Donabach asset location: private credit, then bonds, fill the pre-tax account
    first; the Roth holds stocks; brokerage takes the remainder.
    """
    pe, pb, pp = st[S_PE], st[S_PB], st[S_PP]
    re, rb = st[S_RE], st[S_RB]
    be, bb = st[S_BE], st[S_BB]
    pre = pe + pb + pp
    ros = re + rb
    brk = be + bb
    total = pre + ros + brk
    if total <= 0.0:
        return 0.0

    if uniform:
        pe_n, pb_n, pp_n = pre * equity, pre * (1.0 - equity), 0.0
        re_n, rb_n = ros * equity, ros * (1.0 - equity)
        be_n = brk * equity
    else:
        equity_target = equity * total
        pp_n = min(private_credit * total, pre)
        bonds_target = total - equity_target - pp_n
        pb_n = min(bonds_target, pre - pp_n)
        pe_n = pre - pp_n - pb_n
        re_n = min(ros, max(equity_target - pe_n, 0.0))
        rb_n = ros - re_n
        be_n = equity_target - pe_n - re_n
    be_n = min(max(be_n, 0.0), brk)  # guard against floating-point drift
    bb_n = brk - be_n

    gain = 0.0
    if be_n < be:
        gain = (be - be_n) * (be - st[S_BBASIS]) / be
        st[S_BBASIS] *= be_n / be
    elif be_n > be:
        st[S_BBASIS] += be_n - be
    st[S_PE], st[S_PB], st[S_PP] = pe_n, pb_n, pp_n
    st[S_RE], st[S_RB] = re_n, rb_n
    st[S_BE], st[S_BB] = be_n, bb_n
    return gain


# --------------------------------------------------------------------------------------------
# One household, one future: the year, in two halves
# --------------------------------------------------------------------------------------------
#
# A year is simulated by `_year_begin` (returns and loss harvesting: what the household sees
# before it decides anything) and `_year_rest` (everything it then does, given an action). A fixed
# policy turns its row into the year's action with `_policy_action`; the adaptive planner chooses
# the action itself after `_year_begin`, from what has happened so far. Both go through the same
# two functions, so a forced action reproduces a fixed policy exactly.


@jit
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
    act[A_K401_ROTH] = 0.0
    act[A_BORROW] = 0.0
    act[A_REALIZE] = 0.0
    harvest = 0.0
    if gates_row[G_HARVEST] > 0.5:
        harvest = 2.0 if row[SP_DI] > 0.5 else 1.0
    act[A_HARVEST] = harvest
    act[A_BUCKET] = 1.0 if (row[SP_BUCKET] > 0.5 and gates_row[G_BUCKET] > 0.5) else 0.0
    act[A_LOCATION] = 1.0 if (row[SP_LOCATION] < 0.5 and gates_row[G_LOCATION] > 0.5) else 0.0
    act[A_WDBRACKET] = 1.0 if (row[SP_WD_BRACKET] > 0.5 and gates_row[G_WITHDRAW] > 0.5) else 0.0


@jit
def _year_begin(st, ys, tv, t, act, r_e, r_b, r_c):
    """Steps 1-2: apply this year's returns, then harvest losses. Fills the year scratch `ys`."""
    age = tv[t, TV_AGE]
    early = age < _EARLY_AGE

    # Gains and withdrawals deferred from paying last year's tax and fees land in this year.
    realized = st[S_DGAIN]
    ret_dist = st[S_DDIST]
    st[S_DGAIN] = 0.0
    st[S_DDIST] = 0.0
    ys[Y_EARLYBASE] = ret_dist if early else 0.0
    ys[Y_CFIN] = st[S_CF]
    ys[Y_PRETAX_OPEN] = st[S_PE] + st[S_PB] + st[S_PP]  # last December 31 balance: the RMD base

    # Opening balances drive this year's dividends and interest.
    dividends = markets.DIVIDEND_YIELD * st[S_BE]
    interest = markets.BOND_INTEREST_YIELD * (st[S_BB] + st[S_GB])

    # 1. Returns.
    st[S_PE] *= 1.0 + r_e
    st[S_PB] *= 1.0 + r_b
    st[S_PP] *= 1.0 + r_c
    st[S_RE] *= 1.0 + r_e
    st[S_RB] *= 1.0 + r_b
    st[S_BE] *= 1.0 + r_e
    st[S_BBASIS] += dividends  # reinvested dividends are bought at cost
    st[S_BB] *= 1.0 + r_b
    st[S_GB] *= 1.0 + r_b

    # 2. Harvest losses (0 = none, 1 = fund level, 2 = stock by stock).
    harvest = 0.0
    be = st[S_BE]
    basis = st[S_BBASIS]
    mode = act[A_HARVEST]
    if mode > 0.5 and be > 0.0:
        if mode > 1.5:
            decline = max(0.0, -r_e) * be / (1.0 + r_e)
            dispersion = HARVEST_DISPERSION * be * min(1.0, basis / be)
            harvest = min(HARVEST_DECLINE_SHARE * decline + dispersion, HARVEST_CAP_OF_VALUE * be, basis)
        elif r_e < FUND_HARVEST_TRIGGER:
            harvest = max(0.0, basis - be)
        harvest = max(0.0, harvest)
        realized -= harvest
        st[S_BBASIS] = basis - harvest

    ys[Y_REALIZED] = realized
    ys[Y_RETDIST] = ret_dist
    ys[Y_DIVIDENDS] = dividends
    ys[Y_INTEREST] = interest
    ys[Y_HARVEST] = harvest


@jit
def _year_rest(st, ys, tv, t, hhc, row, act, w, k, wage_tax_t, want_wealth, do_log, log):
    """Steps 3-11 for the action `act`. Returns (after-tax wealth if `want_wealth`, total income tax)."""
    age = tv[t, TV_AGE]
    ss = tv[t, TV_SS]
    taxable_ss = P.SS_TAXABLE_SHARE * ss
    kids = tv[t, TV_KIDS]
    deps = tv[t, TV_DEPS]
    wages_taxable = w - k
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
        rmd = _sell_pretax(st, ys[Y_PRETAX_OPEN] / _ult_period(age))
        ret_dist += rmd
    rmd_cash = rmd

    # 3b. Pay goals that are due: RMD cash, bucket, then brokerage pro rata, then Roth, then pre-tax.
    goal = tv[t, TV_GOAL]
    if goal > 0.0:
        due = goal
        from_rmd = min(rmd_cash, due)
        rmd_cash -= from_rmd
        due -= from_rmd
        from_bucket = min(st[S_GB], due)
        st[S_GB] -= from_bucket
        due -= from_bucket
        if due > 0.0:
            sold, gain = _sell_brokerage(st, due)
            realized += gain
            due -= sold
        if due > 0.0:
            due -= _sell_roth(st, due)
        if due > 0.0:
            taken = _sell_pretax(st, due)
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
            sold, gain = _sell_brokerage(st, remaining)
            realized += gain
            remaining -= sold
            if remaining > 0.0:
                remaining -= _sell_roth(st, remaining)
            if remaining > 0.0:
                taken = _sell_pretax(st, remaining)
                ret_dist += taken
                early_base += taken
                remaining -= taken
        elif wd_bracket:
            # Pre-tax up to the bracket target, then brokerage, then Roth.
            ordinary = _ordinary_income(wages_taxable, interest, taxable_ss, ret_dist, 0.0, realized, cf_in)
            room = max(0.0, wd_top + std - ordinary)
            taken = _sell_pretax(st, min(remaining, room))
            ret_dist += taken
            remaining -= taken
            if remaining > 0.0:
                sold, gain = _sell_brokerage(st, remaining)
                realized += gain
                remaining -= sold
            if remaining > 0.0:
                remaining -= _sell_roth(st, remaining)
            if remaining > 0.0:
                taken = _sell_pretax(st, remaining)
                ret_dist += taken
                remaining -= taken
        else:
            # Pro rata across pre-tax, brokerage and Roth.
            pre = st[S_PE] + st[S_PB] + st[S_PP]
            brk = st[S_BE] + st[S_BB]
            ros = st[S_RE] + st[S_RB]
            total = pre + brk + ros
            if total > 0.0:
                f = min(1.0, remaining / total)
                taken = _sell_pretax(st, f * pre)
                ret_dist += taken
                sold, gain = _sell_brokerage(st, f * brk)
                realized += gain
                got = _sell_roth(st, f * ros)
                remaining -= taken + sold + got
        st[S_UNFUNDED] += _shortfall(remaining)
    if rmd_cash > 0.0:
        st[S_BB] += rmd_cash  # an RMD that exceeds spending is reinvested in the taxable account

    # 5. Roth conversion: fill the chosen bracket, if the action asks for it.
    conv = 0.0
    if conv_top > 0.0:
        ordinary = _ordinary_income(wages_taxable, interest, taxable_ss, ret_dist, 0.0, realized, cf_in)
        room = max(0.0, conv_top + std - ordinary)
        pre = st[S_PE] + st[S_PB] + st[S_PP]
        # The tax is paid from the taxable account, never out of the converted dollars.
        affordable = (st[S_BE] + st[S_BB]) / marginal_rate(conv_top - 1.0)
        conv = min(room, pre, affordable)
        if conv > 0.0:
            f = conv / pre
            st[S_RE] += f * st[S_PE]
            st[S_RB] += f * (st[S_PB] + st[S_PP])
            st[S_PE] *= 1.0 - f
            st[S_PB] *= 1.0 - f
            st[S_PP] *= 1.0 - f

    # 6. Fund or release the goal bucket (bonds held in the taxable account).
    bucket_flow = 0.0
    if act[A_BUCKET] > 0.5:
        target = tv[t, TV_BUCKET]
        held = st[S_GB]
        if held < target:
            sold, gain = _sell_brokerage(st, target - held)
            realized += gain
            st[S_GB] += sold
            bucket_flow = sold
        elif held > target:
            st[S_GB] = target
            st[S_BB] += held - target
            bucket_flow = target - held

    # 7. Rebalance to the target allocation and asset location.
    share = act[A_STOCK]
    pc_share = act[A_PC]
    if act[A_LOCATION] > 0.5:
        realized += _rebalance(st, share * (1.0 - pc_share), pc_share, False)
    else:
        realized += _rebalance(st, share, 0.0, True)

    # 8. Taxes.
    r = tax_core(wages_taxable, interest, dividends, dividends, realized, ret_dist, conv, ss, early_base, kids, deps, cf_in, aged)
    total_tax = r.total_tax
    portfolio_tax = total_tax - wage_tax_t
    st[S_CF] = r.cap_loss_carryforward_out

    # 9. Pay the portfolio-caused tax from the brokerage account. Gains realized by selling
    # to pay it are taxed next year; a negative amount (tax saved) is added to the account.
    due = portfolio_tax
    if due > 0.0:
        sold, gain = _sell_brokerage(st, due)
        st[S_DGAIN] += gain
        due -= sold
        if due > 0.0:
            due -= _sell_roth(st, due)
        if due > 0.0:
            taken = _sell_pretax(st, due)
            st[S_DDIST] += taken
            due -= taken
        st[S_UNFUNDED] += _shortfall(due)
    elif due < 0.0:
        st[S_BB] -= due

    # 10. Advisory fee, charged pro rata to every account. Gains realized on the slice sold
    # from brokerage equity are taxed next year.
    total_assets = 0.0
    for i in range(N_BALANCES):
        if i != S_BBASIS:
            total_assets += st[i]
    fee = _advisory_fee(total_assets, row[SP_FEE_BREAKPOINTS], row[SP_FEE_FLAT])
    if fee > 0.0 and total_assets > 0.0:
        f = min(1.0, fee / total_assets)
        st[S_DGAIN] += f * (st[S_BE] - st[S_BBASIS])
        for i in range(N_BALANCES):
            st[i] *= 1.0 - f

    # 11. Contributions: 401(k) to the pre-tax account, savings to the brokerage account.
    if k > 0.0:
        pre = st[S_PE] + st[S_PB] + st[S_PP]
        if pre > 0.0:
            st[S_PE] += k * st[S_PE] / pre
            st[S_PB] += k * st[S_PB] / pre
            st[S_PP] += k * st[S_PP] / pre
        else:
            st[S_PE] += k
    saved = BROKERAGE_SAVINGS_SHARE * w
    if saved > 0.0:
        brk = st[S_BE] + st[S_BB]
        to_equity = min(saved, saved * st[S_BE] / brk) if brk > 0.0 else saved
        st[S_BE] += to_equity
        st[S_BBASIS] += to_equity
        st[S_BB] += saved - to_equity

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
            + st[S_GB]
            - _LTCG_RATE * unrealized
            + st[S_RE]
            + st[S_RB]
            + pretax
            - owed
            + _LTCG_RATE * st[S_CF]
            - _LTCG_RATE * max(0.0, st[S_DGAIN])
            - st[S_UNFUNDED]
        )

    if do_log:
        equity_total = st[S_PE] + st[S_RE] + st[S_BE]
        long_term = pretax + st[S_RE] + st[S_RB] + st[S_BE] + st[S_BB]
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
        log[t, L_STOCKTARGET] = share
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
        log[t, L_ROTH] = st[S_RE] + st[S_RB]
        log[t, L_BROKERAGE] = st[S_BE] + st[S_BB]
        log[t, L_WEALTH] = wealth
        log[t, L_UNREALIZED] = st[S_BE] - st[S_BBASIS]
        log[t, L_AGED] = aged
        log[t, L_RMD] = rmd
    return wealth, total_tax


@jit
def _simulate_path(s, p, strat, gates, tv, init, hhc, rets, wages, k401, wage_tax, path_wealth, record, log, do_log):
    n_years = tv.shape[0]
    st = init.copy()
    ys = np.zeros(NY)
    act = np.zeros(NACT)
    row = strat[s]
    taxes_paid = 0.0
    wealth = 0.0
    for t in range(n_years):
        w = wages[p, t]
        _policy_action(row, gates[s, t], tv, t, w, act)
        _year_begin(st, ys, tv, t, act, rets[p, t, 0], rets[p, t, 1], rets[p, t, 2])
        want = record or do_log or t == n_years - 1
        res = _year_rest(st, ys, tv, t, hhc, row, act, w, k401[p, t], wage_tax[p, t], want, do_log, log)
        taxes_paid += res[1]
        if want:
            wealth = res[0]
        if record:
            path_wealth[t] = wealth

    pretax = st[S_PE] + st[S_PB] + st[S_PP]
    owed = pretax * pretax_withdrawal_rate(pretax, hhc[HC_SS], tv[n_years - 1, TV_AGED])
    return wealth, taxes_paid, owed, st[S_UNFUNDED]


@jit(parallel=True)
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


@jit(parallel=True)
def _wage_tax_table(wages, k401, tv, out):
    n_paths = wages.shape[0]
    n_years = wages.shape[1]
    for p in prange(n_paths):
        for t in range(n_years):
            r = tax_core(wages[p, t] - k401[p, t], 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, tv[t, TV_KIDS], tv[t, TV_DEPS], 0.0, tv[t, TV_AGED])
            out[p, t] = r.total_tax


# --------------------------------------------------------------------------------------------
# Python layer
# --------------------------------------------------------------------------------------------

# numba's `workqueue` threading layer (the fallback when OpenMP/TBB are unavailable) aborts the whole
# process on concurrent parallel launches, so every parallel kernel call goes through this lock.
_KERNEL_LOCK = threading.Lock()


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
        return r

    def replace(self, **changes) -> Policy:
        return replace(self, **changes)


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
    wage_tax: np.ndarray  # (paths, years) tax on wages alone

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
) -> SimInputs:
    """Draw the futures (or build the one deterministic path) and precompute what is shared."""
    n_years = household.horizon_years
    base = [p.wages for p in household.people]
    ages = [p.age for p in household.people]
    retire = household.goals.retirement_age
    n_earners = len(household.people)

    expected = income.household_wages(base, ages, retire, income.no_shocks(n_years, n_earners))[0]
    if deterministic:
        rets = markets.expected_returns(n_years)
        wages = expected[None, :].copy()
    else:
        rets = markets.draw_returns(n_paths, n_years, seed)
        shocks = income.draw_income_shocks(n_paths, n_years, n_earners, seed)
        wages = income.household_wages(base, ages, retire, shocks)
    if shock is not None:
        rets = markets.with_equity_shock(rets, shock.year, shock.equity_return)

    tv = _time_table(household, n_years, expected)
    k401 = np.minimum(P.LIMIT_401K_EMPLOYEE * tv[:, TV_NEARN][None, :], KEEP_401K_SHARE_OF_WAGES * wages)
    wage_tax = np.zeros_like(wages)
    with _KERNEL_LOCK:
        _wage_tax_table(np.ascontiguousarray(wages), np.ascontiguousarray(k401), tv, wage_tax)

    hhc = np.zeros(NHC)
    hhc[HC_SS] = household.social_security.annual_benefit
    hhc[HC_RMD_START] = P.rmd_start_age(P.TAX_YEAR - household.primary_age)
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

