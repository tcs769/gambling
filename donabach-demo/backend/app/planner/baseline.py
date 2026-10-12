"""The two advisors Donabach is compared with.

**Good RIA**: what a competent traditional advisor would do for this household.

* Age-based glide path: 80% stocks today, falling linearly to 50% at 70, the same mix in every
  account (no asset location)
* Breakpoint fees: 1.0% on the first $1M, 0.8% to $3M, 0.6% to $5M, 0.5% above
* Loss harvesting only at fund level, only in years when equities fall more than 10%
* Goals paid from the brokerage account pro rata, with no dedicated bond bucket
* No Roth conversions
* Retirement withdrawals taken pro rata across accounts (the 10% early-withdrawal penalty is
  still avoided by tapping pre-tax money last before 59 1/2)
* Stock sold in the taxable account comes from the oldest tax lots first (first in, first out), and gains on
  lots held a year or less are taxed as ordinary income, as they are for every strategy

**Typical advisor** (spec A9): the same glide path and mechanics, but

* a fee of 1.15% on the first $500,000 falling to 0.6% above $5M (a surveyed schedule), instead of the good RIA's
* actively managed funds that charge their expense ratios (0.60% on stocks, 0.45% on bonds), and 3% of the portfolio in cash
* no tax-loss harvesting at all
* every account managed separately with the same mix
* no Roth conversions; withdrawals taken proportionally
* the same first-in-first-out tax lots
* actively managed funds in the taxable account, which distribute capital gains every year (see below)

The mechanics live in `app.sim.simulate`; this module only fixes the parameters.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.sim import markets
from app.sim.simulate import FEE_RATES, FEE_TOPS, Policy

GLIDE_START_SHARE = 0.80
GLIDE_END_SHARE = 0.50
TYPICAL_ADVISOR_FEE = 0.010
BASELINE_LOT_METHOD = "fifo"  # the advisors sell the oldest lots first

# The typical advisor puts the taxable account in actively managed US equity funds, which pass capital gains through to their
# holders every year whether or not the holder sold anything. Morningstar's median ten-year tax cost ratio (the return the
# top federal rate takes from distributions) for US stock funds is 1.79% (all funds, index funds and ETFs below 0.50%; large
# blend 1.26% over the last three years). The model's dividends (a yield of 1.8%, taxed at 23.8%) account for 0.43 points of it;
# the rest is capital gain distributions taxed at a blend of 23.8% (88%, long-term) and 40.8% (12%, short-term): they come to
# 5.3% of the funds' value a year, or 6.5% on 20% and 37% rates without the 3.8% surtax. 5.5% is used (4% to 7% in the
# sensitivity). The 12% short-term share is Lipper's, for all open-end funds in 2006 (cited by Johnson and Poterba, 2016).
# The short-term part is paid out as ordinary dividends. The good RIA holds tax-efficient index funds, whose distributions
# are close to nothing (tax cost ratios under 0.5%, nearly all of it the dividends), so it has none. Sources and what was
# read of them: reports/final_report.md, Update 4.
ACTIVE_FUND_DISTRIBUTION = 0.055
ACTIVE_FUND_SHORT_TERM_SHARE = 0.12

RIA_BASELINE = Policy(
    stock_share=GLIDE_START_SHARE,
    glide_start_age=None,  # start gliding today
    glide_drop=GLIDE_START_SHARE - GLIDE_END_SHARE,
    private_credit=0.0,
    direct_indexing=False,
    goal_bonds=False,
    donabach_location=False,
    conversion_top=0.0,
    bracket_withdrawals=False,
    breakpoint_fees=True,
    lot_method=BASELINE_LOT_METHOD,
    short_term_ordinary=True,
)

TYPICAL_ADVISOR = Policy(
    stock_share=GLIDE_START_SHARE,
    glide_start_age=None,
    glide_drop=GLIDE_START_SHARE - GLIDE_END_SHARE,
    private_credit=0.0,
    direct_indexing=False,
    tax_loss_harvesting=False,
    goal_bonds=False,
    donabach_location=False,
    conversion_top=0.0,
    bracket_withdrawals=False,
    breakpoint_fees=False,
    flat_fee=TYPICAL_ADVISOR_FEE,
    lot_method=BASELINE_LOT_METHOD,
    short_term_ordinary=True,
    fund_distribution=ACTIVE_FUND_DISTRIBUTION,
    fund_distribution_short_term=ACTIVE_FUND_SHORT_TERM_SHARE,
    typical_fee_schedule=True,
    fund_expense_equity=markets.ACTIVE_EXPENSE_EQUITY,
    fund_expense_bond=markets.ACTIVE_EXPENSE_BOND,
    cash_share=markets.TYPICAL_CASH_SHARE,
)

# A do-it-yourself investor (Update 4, 12.8): the same glide path, in index funds, with no advisory fee and no advice (no loss harvesting,
# no conversions, accounts managed separately, oldest lots sold first), and a behavior gap: Morningstar's "Mind the Gap" study finds
# that the average dollar invested in US stock funds earns about half a percentage point a year less than the funds themselves
# (the dollar-weighted return of the last ten years against their time-weighted return; the study's all-fund gap is 1.2 points, and
# 0.1 to 1.2 is the range of the figures read; reports/final_report.md, Update 4). The gap is the DIY investor's alone: it is not
# applied to the advisors or to Donabach, whose plans are rules. It is taken out of the stock return (index funds' 0.05% expense ratio
# too, ICI's average for index equity funds, and the same on the bond funds).
DIY_BEHAVIOR_GAP = 0.005
DIY_INDEX_EXPENSE = 0.0005

DIY_INVESTOR = Policy(
    stock_share=GLIDE_START_SHARE,
    glide_start_age=None,
    glide_drop=GLIDE_START_SHARE - GLIDE_END_SHARE,
    private_credit=0.0,
    direct_indexing=False,
    tax_loss_harvesting=False,
    goal_bonds=False,
    donabach_location=False,
    conversion_top=0.0,
    bracket_withdrawals=False,
    breakpoint_fees=False,
    flat_fee=0.0,
    lot_method=BASELINE_LOT_METHOD,
    short_term_ordinary=True,
    fund_expense_equity=DIY_INDEX_EXPENSE + DIY_BEHAVIOR_GAP,
    fund_expense_bond=DIY_INDEX_EXPENSE,
)

# (up to, fee rate) rows, for display next to results.
FEE_SCHEDULE = tuple(zip(FEE_TOPS.tolist(), FEE_RATES.tolist(), strict=True))

GOOD_RIA_SENTENCE = (
    "A good traditional advisor: an age-based glide path from 80% to 50% stocks, the same mix in every "
    "account, breakpoint fees of 1.0% falling to 0.5%, fund-level loss harvesting in years stocks fall more "
    "than 10%, goals paid from the brokerage account, no Roth conversions, pro rata withdrawals and the oldest "
    "tax lots sold first."
)
TYPICAL_ADVISOR_SENTENCE = (
    "A typical advisor: a fee of 1.15% on the first $500,000 falling to 0.6% above $5 million, funds that charge 0.60% (stocks) and 0.45% (bonds) a year, 3% in cash, no tax-loss harvesting, every account managed "
    "separately with the same mix, an age-based glide path from 80% to 50% stocks, no Roth conversions, "
    "withdrawals taken proportionally and the oldest tax lots sold first. Its taxable funds are actively managed, so they "
    "pay out capital gains every year."
)


@dataclass(frozen=True)
class Baseline:
    key: str
    label: str
    definition: str
    policy: Policy


DIY_SENTENCE = (
    "Doing it yourself: the same age-based glide path in index funds with no advisory fee, no loss harvesting, no conversions, withdrawals "
    "taken proportionally and the oldest tax lots sold first, and the behavior gap the average investor shows (about half a point a year "
    "less than the funds earn)."
)
GOOD_RIA = Baseline("good_ria", "Good RIA", GOOD_RIA_SENTENCE, RIA_BASELINE)
TYPICAL = Baseline("typical_advisor", "Typical advisor", TYPICAL_ADVISOR_SENTENCE, TYPICAL_ADVISOR)
BASELINES = (GOOD_RIA, TYPICAL)
DIY = Baseline("diy", "Do it yourself", DIY_SENTENCE, DIY_INVESTOR)
STUDY_BASELINES = (GOOD_RIA, TYPICAL, DIY)  # the studies compare with all three; the app shows the first two
