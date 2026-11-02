"""The customer portal's contract: what the Invest and Compare screens show, and what changed after a change of answers.

Every number is computed once, in `app.portal.engine_view`, and reused everywhere it appears (so the screens agree). Where a figure is
finer-grained than the engine (fund names, sector and region weights, positions) the field says so with `illustrative` and the mapping
lives in `app.portal.illustrative`.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.schemas import Household

MoveStatus = Literal["done", "ongoing", "scheduled", "needs_ok", "your_step"]


class Summary(BaseModel):
    horizon_age: int
    age: int
    projected_wealth: float  # median after-tax wealth at the horizon with Waramoug
    invested_today: float  # total savings
    fee_dollars: float  # a year: fee rate x managed balances
    fee_rate: float  # a fraction
    tax_saved: float  # estimated, this year


class ProjectionPoint(BaseModel):
    age: int
    wealth: float


class GoalMarker(BaseModel):
    key: Literal["college", "retirement", "social_security", "home"]
    label: str
    start_age: int
    end_age: int | None = None  # a shaded band when set, else a line


class AssetRow(BaseModel):
    key: Literal["us_stocks", "intl_stocks", "bonds", "private_credit", "cash"]
    label: str
    amount: float
    share: float
    expected_return: float  # real, a year, the engine's assumption


class Mix(BaseModel):
    rows: list[AssetRow]
    total: float
    illustrative_split: bool = True  # the US / international split of stocks is a fixed illustrative mapping


class LocationRow(BaseModel):
    key: str
    label: str
    brokerage: float
    pretax: float
    roth: float
    total: float


class Location(BaseModel):
    rows: list[LocationRow]
    total: LocationRow


class Move(BaseModel):
    key: str
    title: str
    amount: float | None = None
    timing: str  # "This year", "Next year (age 51)"
    age: int | None = None  # the age of the year it happens in
    status: MoveStatus
    detail: str | None = None  # labels only: "Tax $14,057"


class Overview(BaseModel):
    projection: list[ProjectionPoint]
    markers: list[GoalMarker]
    mix: Mix
    location: Location
    moves: list[Move]


class HoldingRow(BaseModel):
    name: str
    positions: int
    value: float
    gain: float | None = None  # unrealized gain in dollars (taxable stocks)
    yield_rate: float | None = None  # a yearly yield (bonds, private credit, stocks in retirement accounts)
    share: float  # of the account


class AccountHoldings(BaseModel):
    key: Literal["brokerage", "pretax", "roth"]
    label: str
    balance: float
    taxation: str
    cost_basis: float | None = None
    unrealized_gain: float | None = None
    holdings: list[HoldingRow]


class StockRow(BaseModel):
    name: str
    value: float
    gain: float


class BarRow(BaseModel):
    label: str
    share: float
    amount: float


class HoldingsTab(BaseModel):
    accounts: list[AccountHoldings]
    largest_stocks: list[StockRow] | None = None  # only a direct-indexed holding has individual stocks
    sectors: list[BarRow]
    regions: list[BarRow]
    illustrative: bool = True  # sector and region weights (and the largest stocks) are a fixed illustrative mapping, not engine output


class TaxesThisYear(BaseModel):
    roth_conversion: float
    conversion_tax: float
    losses_harvested: float
    gains_offset: float
    deducted_from_income: float
    carried_forward: float
    interest_kept_out: float
    tax_saved: float


class BracketStep(BaseModel):
    rate: float
    floor: float
    ceiling: float | None
    filled: bool


class BracketView(BaseModel):
    brackets: list[BracketStep]
    taxable_before: float  # ordinary taxable income before the conversion
    conversion: float
    fills_to: float  # taxable_before + conversion
    marginal_rate: float  # the bracket the conversion fills
    illinois_tax_on_conversion: float


class Opportunity(BaseModel):
    name: str
    value: float
    cost: float
    loss: float
    replacement: str


class ConversionRow(BaseModel):
    year: int
    age: int
    amount: float
    tax: float
    bracket_rate: float


class TaxesTab(BaseModel):
    this_year: TaxesThisYear
    bracket: BracketView
    opportunities: list[Opportunity]  # empty: no position is below cost
    opportunities_illustrative: bool = True
    conversions: list[ConversionRow]


class IncomeRow(BaseModel):
    age: int
    year: int
    social_security: float
    from_pretax: float
    from_taxable: float
    from_roth: float
    total_sources: float
    spending: float
    tax: float
    total_uses: float


class RequiredWithdrawals(BaseModel):
    start_age: int
    first_amount: float
    covered: bool
    note: str


class RetirementTab(BaseModel):
    rows: list[IncomeRow]
    withdrawal_order: list[str]
    required: RequiredWithdrawals


class GoalCard(BaseModel):
    key: Literal["college", "retirement", "home"]
    label: str
    target: float
    target_label: str  # "$178,158 in total", "$90,015 a year"
    timing: str
    progress: float  # 0..1
    status: Literal["On track", "Close", "Behind"]


class GoalsTab(BaseModel):
    cards: list[GoalCard]


class Portfolio(BaseModel):
    summary: Summary
    overview: Overview
    holdings: HoldingsTab
    taxes: TaxesTab
    retirement: RetirementTab
    goals: GoalsTab


class MixShare(BaseModel):
    key: str
    label: str
    share: float


class AdvisorCard(BaseModel):
    title: str
    wealth_80: float
    bar: float  # scaled to the larger of the two cards
    mix: list[MixShare]
    accounts: list[str]
    harvesting: str
    harvested_so_far: float | None = None
    roth_conversion: float
    fee_dollars: float
    fee_rate: float  # of managed accounts, effective


class Comparison(BaseModel):
    dollars_more: float
    rate_per_year: float
    advisor: AdvisorCard
    waramoug: AdvisorCard


class MixChange(BaseModel):
    key: str
    label: str
    before: float
    after: float
    moved: bool


class MoveChange(BaseModel):
    kind: Literal["added", "removed", "changed"]
    title: str
    before: str | None = None
    after: str | None = None


class WhatChanged(BaseModel):
    changed: str  # "Income: job loss next year"
    mix: list[MixChange]
    wealth_before: float
    wealth_after: float
    moves: list[MoveChange]
    conversion_age: int
    conversion_before: float
    conversion_after: float


class Plan(BaseModel):
    plan_id: str
    household: Household
    portfolio: Portfolio
    comparison: Comparison
    what_changed: WhatChanged | None = None
    event: Literal["none", "job_loss", "raise"] = "none"


class InvestRequest(BaseModel):
    household: Household
    event: Literal["none", "job_loss", "raise"] = "none"
    previous_plan_id: str | None = Field(None, description="The plan the customer saw before this change (what changed is shown against it)")
    change_label: str | None = Field(None, description="Words for the value that was changed, e.g. 'Income: job loss next year'")
