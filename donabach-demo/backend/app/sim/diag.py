"""The layout of a path's diagnostic accumulators (`app.study.diagnostics` reads them).

When the simulator is asked for diagnostics (`run_batch(..., diagnostics=True)`) every (policy, path) fills one row of
`DG_SIZE` numbers over its life: the stock sold from the brokerage account and the gains realized by it, by purpose (harvested losses
are a purpose with no sale: a negative gain and the tax it saved); the tax on those gains; the whole of the income tax broken up by the kind of income it was charged on; the pre-tax withdrawals
and their penalty; where the spending reserve was held; the position at the horizon; and the tape of the equity bought and
sold each year, which `app.sim.replay` replays under other lot rules. All dollars are real 2026 dollars, summed over the years.

Purposes. A sale of brokerage stock is for one of: the goals (home, college), retirement spending, the year's charitable gift
(the cash part), the income tax (and the tax on a Roth 401(k) contribution), rebalancing to the target mix, refilling the
spending reserve (with the goal bond bucket, which the reserve includes), the advisory fee, or something else (a forced sale
to keep a loan within its limit, repaying it, and the loan's interest). Fund distributions are gains with no sale.

Income types. The year's income tax is split by stacking the income in the order the tax is computed: wages and Social Security
first, then interest, then pre-tax withdrawals (the penalty with them), required distributions, Roth conversions, short-term
gains (ordinary income), dividends, long-term gains; each type's share is what it added to the tax. The charitable
deduction's saving comes last, as a negative amount. The shares add up to the year's tax exactly.
"""

from __future__ import annotations

from app.sim.state import MAX_LOTS

# --- purposes -----------------------------------------------------------------------------------------------------
(P_GOALS, P_SPENDING, P_GIFTS, P_TAXES, P_REBALANCING, P_RESERVE, P_FEES, P_OTHER, P_DISTRIBUTIONS, P_HARVEST, P_GAIN_HARVEST) = range(11)
N_PURPOSES = 11
PURPOSES = (
    "goals",
    "retirement spending",
    "charitable gifts (cash part)",
    "income taxes",
    "rebalancing",
    "refilling the reserve",
    "advisory fees",
    "other (loan)",
    "fund distributions",
    "loss harvesting",
    "gain harvesting (sold and bought back)",
)

# --- income types of the tax --------------------------------------------------------------------------------------
(T_OTHER, T_INTEREST, T_WITHDRAWALS, T_REQUIRED, T_CONVERSIONS, T_SHORT_TERM, T_DIVIDENDS, T_LONG_TERM, T_CHARITY) = range(9)
N_TYPES = 9
TAX_TYPES = (
    "wages and Social Security",
    "interest",
    "pre-tax withdrawals (and the early-withdrawal penalty)",
    "required minimum distributions",
    "Roth conversions",
    "short-term gains",
    "dividends",
    "long-term gains",
    "charitable deduction",
)

# --- pre-tax withdrawals by purpose -------------------------------------------------------------------------------
(W_GOALS, W_SPENDING, W_GIFTS, W_TAXES, W_REQUIRED) = range(5)
N_WITHDRAWALS = 5

# --- the layout of one row ----------------------------------------------------------------------------------------
D_SOLD = 0  # N_PURPOSES: equity sold, by purpose
D_GAIN = D_SOLD + N_PURPOSES  # N_PURPOSES: gains realized by those sales (negative: a loss), by purpose
D_TAX = D_GAIN + N_PURPOSES  # N_PURPOSES: the tax on capital gains, shared out by purpose in proportion to the gains
D_TYPE = D_TAX + N_PURPOSES  # N_TYPES: the income tax by kind of income
D_PTW = D_TYPE + N_TYPES  # N_WITHDRAWALS: pre-tax withdrawals by purpose
D_PENALTY = D_PTW + N_WITHDRAWALS  # early-withdrawal penalty paid
D_EARLY = D_PENALTY + 1  # pre-tax dollars withdrawn before 59 1/2
D_WAGETAX = D_EARLY + 1  # the tax on wages alone (what the household would pay with no portfolio)
D_DONATED = D_WAGETAX + 1  # value of stock given in kind
D_DONATED_GAIN = D_DONATED + 1  # the gain on it (never taxed)
D_CASHGIFT = D_DONATED_GAIN + 1  # gifts paid in cash
D_FUNDDIST = D_CASHGIFT + 1  # fund capital gain distributions
D_FUNDDIST_ST = D_FUNDDIST + 1  # the short-term part of them
D_CARRY_TAX = D_FUNDDIST_ST + 1  # gains realized selling for the tax, reported next year (carried between years)
D_CARRY_FEE = D_CARRY_TAX + 1  # the same for the fee
D_RES_PRETAX = D_CARRY_FEE + 1  # the spending reserve (bonds and private credit, the goal bucket with the brokerage's): summed year-end
D_RES_ROTH = D_RES_PRETAX + 1  # balances over the retired years, by account
D_RES_BROKERAGE = D_RES_ROTH + 1
D_RES_YEARS = D_RES_BROKERAGE + 1  # the number of retired years
D_RES0_PRETAX = D_RES_YEARS + 1  # the same at the end of the first retired year
D_RES0_ROTH = D_RES0_PRETAX + 1
D_RES0_BROKERAGE = D_RES0_ROTH + 1
D_RES0_SET = D_RES0_BROKERAGE + 1
D_END_BE = D_RES0_SET + 1  # brokerage equity at the horizon
D_END_BASIS = D_END_BE + 1  # its cost basis
D_YG = D_END_BASIS + 1  # N_PURPOSES: the gains of the year's tax return by purpose (this year's, scratch for sharing out the tax)
D_SIZE_SCALARS = D_YG + N_PURPOSES

# The tape: per year, the change in brokerage equity at each step (negative a sale, positive a purchase). TAPE_REALIZE is the exception:
# it holds the gain the year's gain harvesting realized (stock sold and bought back at once, so the equity does not change).
(
    TAPE_FORCED,
    TAPE_GOALS,
    TAPE_DONATE,
    TAPE_SPENDING,
    TAPE_REALIZE,
    TAPE_BUCKET,
    TAPE_LOAN,
    TAPE_REBALANCE,
    TAPE_TAXES,
    TAPE_FEES,
    TAPE_SAVING,
    TAPE_TAXGAP,
) = range(12)
NK = 12
D_TAPE = D_SIZE_SCALARS
DG_SIZE = D_TAPE + MAX_LOTS * NK
