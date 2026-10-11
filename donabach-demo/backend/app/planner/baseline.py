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

* a flat 1.0% fee at every balance (no breakpoints)
* no tax-loss harvesting at all
* every account managed separately with the same mix
* no Roth conversions; withdrawals taken proportionally
* the same first-in-first-out tax lots

The mechanics live in `app.sim.simulate`; this module only fixes the parameters.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.sim.simulate import FEE_RATES, FEE_TOPS, Policy

GLIDE_START_SHARE = 0.80
GLIDE_END_SHARE = 0.50
TYPICAL_ADVISOR_FEE = 0.010
BASELINE_LOT_METHOD = "fifo"  # the advisors sell the oldest lots first

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
    "A typical advisor: a flat 1.0% fee at every balance, no tax-loss harvesting, every account managed "
    "separately with the same mix, an age-based glide path from 80% to 50% stocks, no Roth conversions, "
    "withdrawals taken proportionally and the oldest tax lots sold first."
)


@dataclass(frozen=True)
class Baseline:
    key: str
    label: str
    definition: str
    policy: Policy


GOOD_RIA = Baseline("good_ria", "Good RIA", GOOD_RIA_SENTENCE, RIA_BASELINE)
TYPICAL = Baseline("typical_advisor", "Typical advisor", TYPICAL_ADVISOR_SENTENCE, TYPICAL_ADVISOR)
BASELINES = (GOOD_RIA, TYPICAL)
