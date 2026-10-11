"""HTTP request and response models (the API contract the frontend is typed against).

Domain models (Household and friends) live in `app.schemas`; this module adds the contracts
for each endpoint. Every dollar amount is a real 2026 dollar.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.docs.models import DocKind, ParsedDocument
from app.ml.interfaces import Factor, IncomeForecast, Recommendation
from app.planner.explain import AdvantageStep
from app.schemas import Household, MarketShock
from app.tax.engine import TaxLine, TaxReturn

# --------------------------------------------------------------------------------------------
# Documents
# --------------------------------------------------------------------------------------------


class DocumentInfo(BaseModel):
    id: str
    name: str
    size_bytes: int
    pages: int
    kind: DocKind | None = None  # known once the document has been parsed


class DocumentList(BaseModel):
    documents: list[DocumentInfo]


class ParseResponse(BaseModel):
    document: DocumentInfo
    parsed: ParsedDocument


# --------------------------------------------------------------------------------------------
# Household
# --------------------------------------------------------------------------------------------


class Answers(BaseModel):
    """What the app asks (goals) and what it estimates (Roth, cash, Social Security)."""

    home_purchase_in_years: int | None = Field(3, ge=0, le=30)
    home_down_payment: float = Field(120_000.0, ge=0)
    college_starts_in_years: int | None = Field(10, ge=0, le=30)
    college_annual_cost: float = Field(35_000.0, ge=0)
    college_years: int = Field(4, ge=0, le=8)
    retirement_age: int = Field(62, ge=50, le=70)
    retirement_spending: float = Field(110_000.0, ge=0)
    roth_balance: float = Field(30_000.0, ge=0)
    cash: float = Field(40_000.0, ge=0)
    social_security_annual: float = Field(50_000.0, ge=0)
    social_security_start_age: int = Field(67, ge=62, le=70)


class HouseholdRequest(BaseModel):
    document_ids: list[str] = Field(min_length=1)
    overrides: dict[str, float | str] = Field(
        default_factory=dict, description="Fields the user corrected, by field key"
    )
    answers: Answers = Field(default_factory=Answers)


class MissingField(BaseModel):
    key: str
    label: str


class AccountLine(BaseModel):
    label: str
    amount: float
    estimated: bool = False
    detail: str | None = None


class GoalLine(BaseModel):
    label: str
    detail: str
    estimated: bool = False


class HouseholdProfile(BaseModel):
    household: Household
    accounts: list[AccountLine]
    goals: list[GoalLine]
    tax_return: TaxReturn
    tax_lines: list[TaxLine]
    estimated: list[str]
    total_assets: float


# --------------------------------------------------------------------------------------------
# Models and forecast
# --------------------------------------------------------------------------------------------


class ModelStatus(BaseModel):
    model: Literal["recommender", "forecaster"]
    connected: bool
    reason: str | None = None
    expected_path: str | None = None


class ModelsStatus(BaseModel):
    recommender: ModelStatus
    forecaster: ModelStatus


class ForecastRequest(BaseModel):
    household: Household
    n_paths: int = Field(2_000, ge=200, le=20_000)
    demo_mode: bool = True
    seed: int | None = None


class ForecastResponse(BaseModel):
    connected: bool
    label: str  # "Placeholder forecast" or "Income forecast model"
    reason: str | None = None
    note: str
    forecast: IncomeForecast
    top_factors: list[Factor] = Field(default_factory=list)


# --------------------------------------------------------------------------------------------
# Plan
# --------------------------------------------------------------------------------------------


class PlanRequest(BaseModel):
    household: Household
    n_paths: int = Field(400, ge=50, le=5_000)
    demo_mode: bool = True
    seed: int | None = None
    shock: MarketShock | None = None


class OutcomeView(BaseModel):
    median: float
    p10: float
    p90: float
    score: float  # certainty-equivalent wealth


class StrategyView(BaseModel):
    choices: dict[str, str]
    label: str
    sentence: str
    outcome: OutcomeView


class RankedRow(BaseModel):
    rank: int
    choices: dict[str, str]
    label: str
    median: float
    p10: float
    p90: float
    score: float
    tied_with: int | None = None
    is_chosen: bool = False
    is_model_pick: bool = False


class PlanRow(BaseModel):
    """One year of the deterministic plan (expected returns, no shocks)."""

    year_index: int
    age: int
    income: float  # wages + Social Security + retirement withdrawals + interest + dividends
    wages: float
    roth_conversion: float
    losses_harvested: float
    goal_bonds_balance: float  # held in the goal bond bucket at year end
    goal_bonds_flow: float  # moved into (+) or released from (-) the bucket this year
    goal_paid: float
    stock_share: float  # target stock share of long-term money
    total_tax: float
    federal_tax: float
    illinois_tax: float
    wealth: float  # after-tax wealth at year end


class RecommenderPanel(BaseModel):
    status: ModelStatus
    recommendation: Recommendation | None = None
    model_strategy: StrategyView | None = None  # what the model recommended, scored by the engine
    verified_strategy: StrategyView | None = None  # best of the model's candidates by engine score
    agrees: bool | None = None
    candidates: list[RankedRow] = Field(default_factory=list)


class StatCards(BaseModel):
    typical_outcome: OutcomeView
    ria_typical_outcome: OutcomeView
    advantage_per_year: float  # typical outcome minus the RIA's typical outcome, over the plan years
    advantage_total: float
    lifetime_taxes: float  # income taxes paid plus tax still owed on pre-tax accounts (median)
    ria_lifetime_taxes: float
    years: int


class FanSeries(BaseModel):
    ages: list[int]
    p10: list[float]
    p25: list[float]
    p50: list[float]
    p75: list[float]
    p90: list[float]


class PlanSettings(BaseModel):
    n_paths: int
    seed: int
    demo_mode: bool
    elapsed_seconds: float
    current_age: int
    horizon_age: int
    strategies_searched: int
    market_shock: MarketShock | None = None


class PlanResponse(BaseModel):
    planner_label: str
    strategy: StrategyView
    reason: str
    recommender: RecommenderPanel
    ria: StrategyView
    rows: list[PlanRow]
    stats: StatCards
    fan: FanSeries
    ria_fan: FanSeries
    advantage: list[AdvantageStep]
    searched: list[RankedRow]
    settings: PlanSettings


class YearDetailRequest(BaseModel):
    household: Household
    choices: dict[str, str]
    year_index: int = Field(ge=0)
    shock: MarketShock | None = None


# --------------------------------------------------------------------------------------------
# What-if
# --------------------------------------------------------------------------------------------

Preset = Literal["home_next_year", "spouse_b_income_cut", "retire_57", "market_drop_30"]


class HouseholdEdits(BaseModel):
    """Editable what-if inputs. Only the fields the caller sets are applied."""

    retirement_age: int | None = Field(None, ge=50, le=70)
    retirement_spending: float | None = Field(None, ge=0)
    home_purchase_in_years: int | None = Field(None, ge=0, le=30)
    home_down_payment: float | None = Field(None, ge=0)
    college_starts_in_years: int | None = Field(None, ge=0, le=30)
    college_annual_cost: float | None = Field(None, ge=0)
    primary_wages: float | None = Field(None, ge=0)
    spouse_wages: float | None = Field(None, ge=0)
    social_security_annual: float | None = Field(None, ge=0)
    roth_balance: float | None = Field(None, ge=0)
    cash: float | None = Field(None, ge=0)
    remove_home_purchase: bool = False
    remove_college: bool = False


class WhatIfRequest(BaseModel):
    household: Household
    presets: list[Preset] = Field(default_factory=list)
    edits: HouseholdEdits = Field(default_factory=HouseholdEdits)
    n_paths: int = Field(400, ge=50, le=5_000)
    demo_mode: bool = True
    seed: int | None = None
    shock: MarketShock | None = None  # an existing shock to keep (from a previous what-if)


class Change(BaseModel):
    field: str
    label: str
    before: str
    after: str


class WhatIfResponse(BaseModel):
    changes: list[Change]
    household: Household
    shock: MarketShock | None
    plan: PlanResponse

