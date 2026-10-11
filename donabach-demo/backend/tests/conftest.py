from __future__ import annotations

import pytest

from app.schemas import Accounts, Goals, Household, IncomeSnapshot, Person, SocialSecurity


def make_demo_household(**overrides) -> Household:
    """The fictional demo household from the spec (fixtures/demo_household.json)."""
    data = dict(
        people=[
            Person(name="Alex Sample", age=38, wages=140_000, pretax_401k=24_500),
            Person(name="Jordan Sample", age=37, wages=110_000, pretax_401k=24_500),
        ],
        children_ages=[8],
        accounts=Accounts(
            brokerage_value=150_000,
            brokerage_basis=110_000,
            pretax_balance=400_000,
            pretax_equity_share=0.75,
            roth_balance=30_000,
            cash=40_000,
        ),
        goals=Goals(
            home_purchase_in_years=3,
            home_down_payment=120_000,
            college_starts_in_years=10,
            college_annual_cost=35_000,
            college_years=4,
            retirement_age=62,
            retirement_spending=110_000,
        ),
        social_security=SocialSecurity(annual_benefit=50_000, start_age=67),
        snapshot=IncomeSnapshot(
            wages_after_401k=201_000,
            interest=800,
            qualified_dividends=2_700,
            ordinary_dividends=3_000,
            net_capital_gain=1_500,
        ),
    )
    data.update(overrides)
    return Household(**data)


@pytest.fixture
def demo_household() -> Household:
    return make_demo_household()
