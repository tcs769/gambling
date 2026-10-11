"""Tax-year 2026 parameters: married filing jointly, Illinois residents.

Every constant lives here, with its source. Federal values are from IRS Rev. Proc. 2025-32
unless noted otherwise. The simulator runs in real (inflation-adjusted) terms, so these
2026 dollar amounts are held constant for the whole projection.

Simplifications (also stated in the UI footer): income tax only (no payroll taxes), standard
deduction only (no itemizing), no AMT, no state tax credits.
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
# Illinois base income starts at federal AGI and subtracts federally taxed retirement income:
# IRA/401(k) distributions, Roth conversions and taxable Social Security (35 ILCS 5/203).

# --- Retirement-balance valuation ---------------------------------------------------------
# After-tax wealth values a pre-tax balance as if it were withdrawn evenly over this many
# years alongside Social Security. Project convention (see the simulator spec).
PRETAX_WITHDRAWAL_YEARS = 20
# Tax on unrealized gains and on unused loss carryforward in the after-tax wealth formula.
UNREALIZED_GAIN_TAX_RATE = 0.15

SIMPLIFICATIONS = (
    "Income tax only (no payroll taxes)",
    "Standard deduction only (no itemizing)",
    "No AMT",
    "No state tax credits",
)
