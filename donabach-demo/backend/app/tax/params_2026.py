"""Tax-year 2026 parameters: married filing jointly, Illinois residents.

Every constant lives here, with its source. Federal values are from IRS Rev. Proc. 2025-32
unless noted otherwise. The simulator runs in real (inflation-adjusted) terms, so these
2026 dollar amounts are held constant for the whole projection.

Simplifications (also stated in the UI footer): income tax only (no payroll taxes), the standard
deduction (itemizing only for charitable gifts), no AMT, no state tax credits.
"""

from __future__ import annotations

import math

import numpy as np

TAX_YEAR = 2026
FILING_STATUS = "married_filing_jointly"
STATE = "IL"

# --- Federal ordinary income brackets, MFJ ------------------------------------------------
# Source: IRS Rev. Proc. 2025-32 (tax year 2026 rate table, married filing jointly).
# Each row: (taxable income up to, marginal rate). The last bracket is open-ended.
FED_BRACKETS_MFJ: tuple[tuple[float, float], ...] = (
    (24_800.0, 0.10),
    (100_800.0, 0.12),
    (211_400.0, 0.22),
    (403_550.0, 0.24),
    (512_450.0, 0.32),
    (768_700.0, 0.35),
    (math.inf, 0.37),
)
BRACKET_TOPS = np.array([top for top, _ in FED_BRACKETS_MFJ])
BRACKET_RATES = np.array([rate for _, rate in FED_BRACKETS_MFJ])

# Top of the 12%, 22% and 24% brackets: the targets of the "fill the bracket" Roth strategies.
TOP_OF_12 = 100_800.0
TOP_OF_22 = 211_400.0
TOP_OF_24 = 403_550.0

# --- Standard deduction -------------------------------------------------------------------
# Source: IRS Rev. Proc. 2025-32 (standard deduction, married filing jointly).
STANDARD_DEDUCTION_MFJ = 32_200.0
# Additional standard deduction for each spouse aged 65 or older (IRC section 63(f)), married
# filing jointly, 2026. Source: IRS Rev. Proc. 2025-32 (additional standard deduction for the
# aged or blind, married: $1,650 per person). The separate $6,000 "senior deduction" of the One
# Big Beautiful Bill Act (IRC section 151(d)(5)) is deliberately NOT modelled: it expires after
# tax year 2028, long before this household reaches 65.
STANDARD_DEDUCTION_AGED_PER_SPOUSE = 1_650.0
AGED_AGE = 65

# --- Long-term capital gains and qualified dividends --------------------------------------
# Source: IRS Rev. Proc. 2025-32 (maximum zero and 15% rate amounts). MFJ thresholds: 0% up to
# CG_ZERO_TOP, 15% up to CG_FIFTEEN_TOP, 20% above. The preferential income stacks on top of
# ordinary taxable income, so the thresholds apply to total taxable income.
CG_ZERO_TOP = 98_900.0
CG_FIFTEEN_TOP = 613_700.0
CG_RATE_ZERO = 0.0
CG_RATE_FIFTEEN = 0.15
CG_RATE_TWENTY = 0.20

# --- Net investment income tax ------------------------------------------------------------
# Source: IRC section 1411. 3.8% of the lesser of net investment income or MAGI above the
# threshold. The $250,000 MFJ threshold is statutory and not indexed.
NIIT_RATE = 0.038
NIIT_THRESHOLD_MFJ = 250_000.0

# --- Child tax credit ---------------------------------------------------------------------
# Source: IRC section 24 as amended by the One Big Beautiful Bill Act (2025): $2,200 per child
# under 17 in 2026. Reduced by $50 per $1,000 (or fraction thereof) of MAGI above $400,000
# (MFJ). Treated as nonrefundable for simplicity (limited to income tax before credits).
CTC_PER_CHILD = 2_200.0
CTC_PHASEOUT_START_MFJ = 400_000.0
CTC_PHASEOUT_STEP = 1_000.0
CTC_PHASEOUT_REDUCTION = 50.0
CTC_MAX_CHILD_AGE = 16  # a child is "under 17" through age 16

# --- Capital losses -----------------------------------------------------------------------
# Source: IRC section 1211(b). Net capital losses offset up to $3,000 of ordinary income per
# year (MFJ); the remainder carries forward indefinitely.
CAP_LOSS_LIMIT = 3_000.0

# --- Early-withdrawal penalty -------------------------------------------------------------
# Source: IRC section 72(t). 10% additional tax on pre-tax withdrawals before age 59 1/2.
EARLY_WITHDRAWAL_PENALTY_RATE = 0.10
EARLY_WITHDRAWAL_AGE = 59.5

# --- Social Security ----------------------------------------------------------------------
# Simplification: 85% of benefits are treated as federally taxable (the statutory maximum
# inclusion, IRC section 86). Illinois does not tax Social Security benefits.
SS_TAXABLE_SHARE = 0.85

# --- Charitable gifts ---------------------------------------------------------------------
# Rules for tax year 2026 as the One Big Beautiful Bill Act (Pub. L. 119-21, sections 70424-70425) left them, read from IRS
# Publications 505 and 526 (2026) and IRS Topic 506 (see reports/final_report.md, "Update 4", for what was and was not read):
# * A household that does not itemize deducts up to $2,000 (married filing jointly) of cash gifts on top of the standard
#   deduction. Gifts of stock do not count.
# * One that itemizes deducts gifts only above 0.5% of its adjusted gross income. Cash gifts to public charities are limited
#   to 60% of AGI and gifts of long-term stock to 30%; both together to 60%. The excess carries forward five years, which the
#   model does not follow (it is lost): gifts that large are outside what it is for.
# * Long-term stock is deducted at its market value and no gain is recognized on giving it (IRC 170(e)); stock held a year or
#   less is deducted at its cost, which is why the simulator only ever gives lots held longer than a year.
# * The 35% cap on the benefit of itemized deductions for the 37% bracket (IRC 68, as rewritten) is not modelled, nor are
#   other itemized deductions: a household is treated as itemizing only if its gifts alone beat the standard deduction.
CHARITY_CASH_LIMIT = 0.60
CHARITY_STOCK_LIMIT = 0.30
CHARITY_ITEMIZER_FLOOR = 0.005
CHARITY_NON_ITEMIZER_MFJ = 2_000.0

# --- Retirement plan limits ---------------------------------------------------------------
# Source: IRS Notice 2025-67. Employee elective deferral limit under IRC section 402(g), 2026.
LIMIT_401K_EMPLOYEE = 24_500.0

# --- Illinois -----------------------------------------------------------------------------
# Source: 35 ILCS 5/201 (Illinois Income Tax Act): flat 4.95% individual income tax rate.
IL_RATE = 0.0495
# Source: Illinois exemption allowance (35 ILCS 5/204) at the 2026 amount specified for this
# project: $2,925 per taxpayer, spouse and dependent. Not allowed when federal AGI exceeds
# $500,000 (MFJ).
IL_EXEMPTION_PER_PERSON = 2_925.0
IL_EXEMPTION_AGI_LIMIT_MFJ = 500_000.0
# Source: 35 ILCS 5/204(d): an additional $1,000 exemption for each taxpayer and spouse aged 65 or
# older (subject to the same $500,000 AGI limit).
IL_EXEMPTION_AGED_PER_PERSON = 1_000.0
# Illinois base income starts at federal AGI and subtracts federally taxed retirement income:
# IRA/401(k) distributions, Roth conversions and taxable Social Security (35 ILCS 5/203).

# --- Required minimum distributions -------------------------------------------------------
# Start age under current law (SECURE 2.0 Act of 2022, section 107; IRC section 401(a)(9)(C)):
# 73 for anyone born 1951 through 1959, 75 for anyone born in 1960 or later. The first RMD is for
# the calendar year in which the owner reaches that age.
RMD_START_AGE_1951_1959 = 73
RMD_START_AGE_1960_ON = 75


def rmd_start_age(birth_year: int) -> int:
    """Age at which required minimum distributions begin for someone born in `birth_year`."""
    if birth_year >= 1960:
        return RMD_START_AGE_1960_ON
    if birth_year >= 1951:
        return RMD_START_AGE_1951_1959
    return 72  # born 1950 or earlier (SECURE Act); outside the range of households this app models


# Uniform Lifetime Table: the distribution period by the age the owner reaches in the year.
# Source: IRS Publication 590-B (2025), Appendix B, Table III (Uniform Lifetime), the table in
# effect since 2022 (Treas. Reg. section 1.401(a)(9)-9(c)). The RMD for a year is the prior
# December 31 balance divided by the period for the age reached that year. Ages 72 to 120+.
ULT_FIRST_AGE = 72
ULT_PERIODS = np.array(
    [
        27.4, 26.5, 25.5, 24.6, 23.7, 22.9, 22.0, 21.1, 20.2, 19.4,  # 72-81
        18.5, 17.7, 16.8, 16.0, 15.2, 14.4, 13.7, 12.9, 12.2, 11.5,  # 82-91
        10.8, 10.1, 9.5, 8.9, 8.4, 7.8, 7.3, 6.8, 6.4, 6.0,  # 92-101
        5.6, 5.2, 4.9, 4.6, 4.3, 4.1, 3.9, 3.7, 3.5, 3.4,  # 102-111
        3.3, 3.1, 3.0, 2.9, 2.8, 2.7, 2.5, 2.3, 2.0,  # 112-120+
    ]
)
ULT_LAST_AGE = ULT_FIRST_AGE + len(ULT_PERIODS) - 1  # 120, which stands for "120 and over"

# --- Portfolio borrowing (box-spread loans) -----------------------------------------------
# A box spread is four index options that together make a zero-coupon loan against a taxable
# portfolio. Its rate tracks Treasury yields plus a small premium: measured box-over-Treasury
# spreads run about 10 to 50 basis points (New York Fed and Cboe studies; Cboe's SPX box data
# averaged about 26 bp over 3-month Treasuries in 2025), so the project uses the 30 bp the spec asks for.
#
# The simulator works in real dollars, so the borrowing cost is a REAL rate:
#   real rate = short-term Treasury yield + 0.30% - inflation
SHORT_TERM_TREASURY_NOMINAL = 0.0452  # 1-year constant-maturity yield, week ending 2026-10-02 (FRED/ALFRED WGS1YR)
BOX_SPREAD_PREMIUM = 0.0030
# The inflation the model's market assumptions imply: bonds pay 3.5% taxable interest and earn 1.5%
# real, so 2.0% of the interest is inflation. Private credit's taxable yield uses the same figure.
ASSUMED_INFLATION = 0.02
BORROWING_RATE_REAL = SHORT_TERM_TREASURY_NOMINAL + BOX_SPREAD_PREMIUM - ASSUMED_INFLATION  # 2.82%
# Interest is treated as a capital loss each year. Real box spreads fall under IRC section 1256 (60%
# long-term, 40% short-term, marked to market); treating all of it as a long-term loss is a simplification.
#
# Guardrails (spec A6): borrowing never exceeds 30% of the taxable account's value (stocks, bonds and
# private credit; the goal-bond bucket is earmarked and not counted). If a market drop pushes the loan
# above 40% of it, assets are sold to bring it back to 30%.
BORROWING_LIMIT = 0.30
BORROWING_FORCED_SALE_TRIGGER = 0.40

# --- Retirement-balance valuation ---------------------------------------------------------
# After-tax wealth values a pre-tax balance as if it were withdrawn evenly over this many
# years alongside Social Security. Project convention (see the simulator spec).
PRETAX_WITHDRAWAL_YEARS = 20
# Tax on unrealized gains and on unused loss carryforward in the after-tax wealth formula.
UNREALIZED_GAIN_TAX_RATE = 0.15

SIMPLIFICATIONS = (
    "Income tax only (no payroll taxes)",
    "Standard deduction (itemized only for charitable gifts)",
    "No AMT",
    "No state tax credits",
)
