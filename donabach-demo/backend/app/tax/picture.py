"""This year's tax picture for a household: the engine run on the income reported on the 1040."""

from __future__ import annotations

from app.schemas import Household
from app.sim import markets
from app.tax import params_2026 as P
from app.tax.engine import TaxInputs, TaxReturn, compute_return

CHILD_DEPENDENT_UNTIL_AGE = 22  # a child is a dependent (Illinois exemption) through age 22


def children_under_17(household: Household) -> int:
    return sum(1 for age in household.children_ages if 0 <= age <= P.CTC_MAX_CHILD_AGE)


def dependents(household: Household) -> int:
    return sum(1 for age in household.children_ages if age <= CHILD_DEPENDENT_UNTIL_AGE)


def current_tax_return(household: Household) -> TaxReturn:
    """Tax for this year from the reported income, or from the market model if none was reported."""
    snap = household.snapshot
    if snap is not None:
        wages = snap.wages_after_401k
        interest = snap.interest
        qualified = snap.qualified_dividends
        ordinary = snap.ordinary_dividends
        gain = snap.net_capital_gain
    else:
        deferrals = min(
            sum(p.pretax_401k for p in household.people) or P.LIMIT_401K_EMPLOYEE * len(household.people),
            0.20 * household.total_wages,
        )
        wages = household.total_wages - deferrals
        interest = markets.BOND_INTEREST_YIELD * household.accounts.cash
        qualified = ordinary = markets.DIVIDEND_YIELD * household.accounts.brokerage_value
        gain = 0.0
    return compute_return(
        TaxInputs(
            wages=wages,
            interest=interest,
            qualified_dividends=qualified,
            ordinary_dividends=ordinary,
            net_capital_gain=gain,
            children_under_17=children_under_17(household),
            dependents=dependents(household),
        )
    )
