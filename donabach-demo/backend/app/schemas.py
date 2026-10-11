"""Pydantic models shared across the backend: the household, and (later) the API contracts.

All dollar amounts are real 2026 dollars. Ages are whole years today.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

HORIZON_AGE = 80  # the simulation runs until the primary earner reaches this age


class Person(BaseModel):
    name: str = ""
    age: int = Field(ge=18, le=69)
    wages: float = Field(ge=0, description="Gross annual wages before pre-tax deferrals")
    pretax_401k: float = Field(0.0, ge=0, description="This year's pre-tax 401(k) deferrals")


class Accounts(BaseModel):
    brokerage_value: float = Field(ge=0)
    brokerage_basis: float = Field(ge=0, description="Cost basis of the brokerage equity")
    pretax_balance: float = Field(ge=0, description="401(k)/IRA balances combined")
    pretax_equity_share: float = Field(0.75, ge=0, le=1, description="Stock share of the 401(k)/IRA")
    roth_balance: float = Field(0.0, ge=0)
    roth_equity_share: float = Field(1.0, ge=0, le=1)
    cash: float = Field(0.0, ge=0, description="Cash savings; invested with brokerage bonds")


class Goals(BaseModel):
    home_purchase_in_years: int | None = Field(3, ge=0, description="Years until the purchase")
    home_down_payment: float = Field(120_000.0, ge=0)
    college_starts_in_years: int | None = Field(10, ge=0)
    college_annual_cost: float = Field(35_000.0, ge=0)
    college_years: int = Field(4, ge=0, le=8)
    retirement_age: int = Field(62, ge=50, le=70)
    retirement_spending: float = Field(110_000.0, ge=0, description="Spending a year, before tax")


class SocialSecurity(BaseModel):
    annual_benefit: float = Field(50_000.0, ge=0, description="Household benefit a year")
    start_age: int = Field(67, ge=62, le=70)


class IncomeSnapshot(BaseModel):
    """This year's income as reported on the tax form (feeds the profile's tax picture)."""

    wages_after_401k: float = 0.0
    interest: float = 0.0
    qualified_dividends: float = 0.0
    ordinary_dividends: float = 0.0
    net_capital_gain: float = 0.0


class Household(BaseModel):
    people: list[Person] = Field(min_length=1, max_length=2)
    children_ages: list[int] = Field(default_factory=list, max_length=4)
    accounts: Accounts
    goals: Goals = Field(default_factory=Goals)
    social_security: SocialSecurity = Field(default_factory=SocialSecurity)
    snapshot: IncomeSnapshot | None = None
    estimated: list[str] = Field(
        default_factory=list, description="Inputs that are estimates, not read from documents"
    )

    @model_validator(mode="after")
    def _check(self) -> Household:
        if self.goals.retirement_age <= self.primary_age:
            raise ValueError("retirement age must be after the primary earner's current age")
        return self

    @property
    def primary_age(self) -> int:
        return self.people[0].age

    @property
    def horizon_years(self) -> int:
        return HORIZON_AGE - self.primary_age

    @property
    def total_wages(self) -> float:
        return sum(p.wages for p in self.people)

    @property
    def liquid_wealth(self) -> float:
        a = self.accounts
        return a.brokerage_value + a.pretax_balance + a.roth_balance + a.cash


class MarketShock(BaseModel):
    """A one-off equity shock applied to every simulated future (a what-if)."""

    year: int = Field(1, ge=0, description="Years from now (1 = next year)")
    equity_return: float = Field(-0.30, gt=-1.0)
