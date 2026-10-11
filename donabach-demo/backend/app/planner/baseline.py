"""The "good RIA" baseline: what a competent traditional advisor would do for this household.

* Age-based glide path: 80% stocks today, falling linearly to 50% at 70, the same mix in every
  account (no asset location)
* Breakpoint fees: 1.0% on the first $1M, 0.8% to $3M, 0.6% to $5M, 0.5% above
* Loss harvesting only at fund level, only in years when equities fall more than 10%
* Goals paid from the brokerage account pro rata, with no dedicated bond bucket
* No Roth conversions
* Retirement withdrawals taken pro rata across accounts (the 10% early-withdrawal penalty is
  still avoided by tapping pre-tax money last before 59 1/2)

The mechanics live in `app.sim.simulate`; this module only fixes the parameters.
"""

from __future__ import annotations

from app.sim.simulate import FEE_RATES, FEE_TOPS, Policy

GLIDE_START_SHARE = 0.80
GLIDE_END_SHARE = 0.50

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
)

# (up to, fee rate) rows, for display next to results.
FEE_SCHEDULE = tuple(zip(FEE_TOPS.tolist(), FEE_RATES.tolist(), strict=True))
