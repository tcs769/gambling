"""HTTP request and response models (the API contract the frontend is typed against).

Domain models (Household and friends) live in `app.schemas`; this module adds the contracts
for each endpoint. Every dollar amount is a real 2026 dollar.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.docs.models import DocKind, ParsedDocument
from app.ml.interfaces import Factor, IncomeForecast, Recommendation
from app.planner.explain import AdvantageStep, YearDetail
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
    charitable_giving: float = Field(0.0, ge=0, description="Gifts to charity a year")
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
    tax_estimated: bool = False  # True when no tax form was read and the picture is an estimate
    total_assets: float


# --------------------------------------------------------------------------------------------
# Models and forecast
# --------------------------------------------------------------------------------------------


class ModelStatus(BaseModel):
    model: Literal["recommender", "forecaster", "policy", "value"]
    connected: bool
    reason: str | None = None
    expected_path: str | None = None


class ModelsStatus(BaseModel):
    recommender: ModelStatus
    forecaster: ModelStatus
    policy: ModelStatus  # proposes candidate actions for the year-by-year planner's search
    value: ModelStatus  # estimates candidate scores for the year-by-year planner's search


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
    n_paths: int = Field(400, ge=50, le=5_000, description="Futures the strategy search runs on")
    n_eval_paths: int = Field(
        200, ge=50, le=5_000, description="Fresh futures (never seen by the search) every result is measured on"
    )
    demo_mode: bool = True
    seed: int | None = None
    shock: MarketShock | None = None
    risk_aversion: float = Field(3.0, ge=0.5, le=10.0, description="CRRA coefficient behind the score")
    planning_style: Literal["balanced", "equity_first", "liability_matched"] = Field(
        "equity_first",
        description="equity_first: a spending reserve of bonds and private credit, everything else in stocks; balanced: a stock share with a glide path",
    )
    adaptive: bool = Field(True, description="Also compute the year-by-year adaptive plan (in the background)")
    adaptive_rollouts: int = Field(32, ge=4, le=128, description="Rollouts (fresh futures) scored per candidate action")


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
    goal_label: str | None = None  # which goal(s) the payment is for, e.g. "Home purchase"
    stock_share: float  # target stock share of long-term money
    total_tax: float
    federal_tax: float
    illinois_tax: float
    wealth: float  # after-tax wealth at year end
    required_distribution: float = 0.0  # RMD taken this year
    private_credit_balance: float = 0.0  # held across all three accounts at year end
    roth_401k_contribution: float = 0.0  # this year's 401(k) contribution that went to the Roth side
    borrowed: float = 0.0  # new box-spread borrowing for a goal this year
    loan_balance: float = 0.0  # box-spread loan outstanding at year end
    gains_realized_tax_free: float = 0.0  # gains realized up to the 0% bracket (adaptive plans only)


class RecommenderPanel(BaseModel):
    status: ModelStatus
    recommendation: Recommendation | None = None
    model_strategy: StrategyView | None = None  # what the model recommended, scored by the engine
    verified_strategy: StrategyView | None = None  # best of the model's candidates by engine score
    agrees: bool | None = None
    candidates: list[RankedRow] = Field(default_factory=list)


class FanSeries(BaseModel):
    ages: list[int]
    p10: list[float]
    p25: list[float]
    p50: list[float]
    p75: list[float]
    p90: list[float]


class AdvantageView(BaseModel):
    """The plan's advantage over one baseline, measured two ways (spec A7), both annualized.

    Each is the yearly growth-rate difference `(plan / baseline)^(1/years) - 1` that would open the
    observed gap over the horizon: median uses median after-tax wealth, risk-adjusted uses
    certainty-equivalent wealth (the planner's own objective). The `*_low` / `*_high` pair is the
    5th to 95th percentile when the evaluation futures are resampled.
    """

    median: float
    risk_adjusted: float
    median_dollars: float  # plan median minus baseline median at the horizon
    risk_adjusted_dollars: float  # plan certainty equivalent minus baseline's
    median_low: float
    median_high: float
    risk_adjusted_low: float
    risk_adjusted_high: float


class BaselineView(BaseModel):
    """One advisor the plan is compared with, measured on the same evaluation futures."""

    key: Literal["good_ria", "typical_advisor"]
    label: str
    definition: str
    outcome: OutcomeView  # liquidated at the horizon
    outcome_heirs: OutcomeView  # the same futures with the estate passed to heirs at the horizon
    lifetime_taxes: float  # median income tax paid plus tax still owed on pre-tax accounts
    shortfall_chance: float  # share of futures in which spending or a goal could not be funded
    advantage: AdvantageView  # the plan's advantage over this baseline, liquidated at the horizon
    advantage_heirs: AdvantageView  # ... and with the estate passed to heirs
    fan: FanSeries


class LiabilityView(BaseModel):
    """The liability-matched plan against its two limits, measured on the futures it was chosen on (`chosen_on`) and on fresh ones."""

    reserve_years: int
    forced_sale_limit: float  # the most futures in which stocks may be sold in a falling year to pay for goals or spending
    forced_sale_chance: float  # on fresh futures
    advisor_forced_sale_chance: float
    ruin_chance: float
    advisor_ruin_chance: float
    chosen_on_forced_sale_chance: float
    chosen_on_ruin_chance: float
    chosen_on_advisor_ruin_chance: float
    feasible: bool  # False: nothing in the menu met both limits and this plan came closest
    stock_share_by_age: list[tuple[int, float]]  # share of long-term money in stocks, year by year (the expected path)


class StatCards(BaseModel):
    typical_outcome: OutcomeView
    ria_typical_outcome: OutcomeView
    typical_outcome_heirs: OutcomeView
    ria_typical_outcome_heirs: OutcomeView
    advantage_per_year: float  # typical outcome minus the RIA's typical outcome, over the plan years
    advantage_total: float
    lifetime_taxes: float  # income taxes paid plus tax still owed on pre-tax accounts (median)
    ria_lifetime_taxes: float
    years: int
    shortfall_chance: float  # share of futures in which the plan could not fund spending or a goal
    advantage: AdvantageView  # over the good RIA, liquidated at the horizon
    advantage_heirs: AdvantageView  # over the good RIA, with the estate passed to heirs
    forced_sale_chance: float = 0.0  # share of futures in which the plan sold stocks in a falling year to pay for goals or spending
    ria_forced_sale_chance: float = 0.0


class PlanSettings(BaseModel):
    n_paths: int  # futures the strategy search ran on
    n_eval_paths: int  # fresh futures every outcome, fan chart and advantage is measured on
    seed: int
    eval_seed: int
    demo_mode: bool
    elapsed_seconds: float
    current_age: int
    horizon_age: int
    strategies_searched: int
    risk_aversion: float  # CRRA coefficient behind the score
    wealth_floor: float  # wealth below this counts as this much when scoring
    market_shock: MarketShock | None = None
    planning_style: Literal["balanced", "equity_first", "liability_matched"] = "equity_first"  # which family of strategies was searched
    heirs_rate: float = 0.24  # the flat tax rate on pre-tax accounts in the "passed to heirs" valuation
    liquidated_label: str = "Liquidated at 80"
    heirs_label: str = "Passed to heirs at 80"
    heirs_note: str = ""  # what the "passed to heirs" valuation assumes and why


# --- The adaptive planner (spec part B) ---------------------------------------------------------


class ActionView(BaseModel):
    """One year's decisions."""

    stock_share: float
    conversion_bracket: int | None  # fill the 12%, 22% or 24% bracket, or None
    private_credit: float
    k401: Literal["pretax", "roth"]
    goal_funding: Literal["sell", "borrow"] | None  # None in a year with no goal due
    realize_gains: bool
    label: str


class AlternativeView(BaseModel):
    action: ActionView
    ce: float  # certainty-equivalent after-tax wealth at the horizon, from the rollouts
    ce_gap: float  # the chosen action's CE minus this one's (negative: scored higher but not convincingly)
    differs_in: list[str]  # which decisions differ from the chosen action


class YearDecisionView(BaseModel):
    """Why this year: what the adaptive planner chose along the plan path, and what it weighed."""

    year_index: int
    age: int
    chosen: ActionView
    fixed: ActionView  # what the fixed (continuation) strategy does this year
    departs: bool
    departures: list[str]  # the decisions that differ from the fixed strategy
    alternatives: list[AlternativeView]  # the next best alternatives to the chosen action
    ce_chosen: float  # certainty-equivalent wealth at the horizon of the chosen action, from the search's rollouts
    ce_fixed: float  # ... and of the fixed strategy's action
    candidates_scored: int
    changes_proposed: int  # changes the search proposed this year
    changes_kept: int  # ... that held up when re-tested on fresh futures
    ce_chosen_fresh: float  # the chosen action's certainty equivalent on the fresh re-test futures (= ce_chosen if none)
    ce_fixed_fresh: float  # ... the fixed strategy's action on the same fresh futures
    why: str  # a few computed sentences
    facts: dict[str, float]  # the numbers behind the sentences


class AdaptivePlanRow(PlanRow):
    departs: bool = False
    departures: list[str] = Field(default_factory=list)


class StrategyOutcome(BaseModel):
    """One of the four strategies, measured on the same evaluation futures."""

    key: Literal["typical_advisor", "good_ria", "best_fixed", "adaptive"]
    label: str
    definition: str
    outcome: OutcomeView
    lifetime_taxes: float
    shortfall_chance: float
    fan: FanSeries
    advantage_vs_typical: AdvantageView | None = None  # its advantage over each baseline
    advantage_vs_ria: AdvantageView | None = None


class AdaptiveSection(BaseModel):
    k: int  # rollouts per candidate on the evaluation futures
    n_eval_paths: int
    z_min: float
    confirm_k: int  # fresh futures a proposed change is re-tested on (0: no re-test)
    confirm_z: float  # standard errors a change must win by on them
    tilt: float  # how far (SDs a year) the importance-sampled half of the rollouts shifts equity returns down
    plan_path_k: int  # rollouts per candidate along the plan path (the table and "Why this year"): more, since it is one path
    plan_path_confirm_k: int
    risk_aversion: float
    elapsed_seconds: float  # for the whole adaptive computation
    seconds_per_path: float
    search: str  # how candidates are chosen, in words
    rows: list[AdaptivePlanRow]  # the adaptive plan along the plan path (expected returns plus any shock)
    year_details: list[YearDetail]  # what was done each year of that path, with its full tax return (decisions are not valued)
    decisions: list[YearDecisionView]
    strategies: list[StrategyOutcome]  # typical advisor, good RIA, best fixed, adaptive
    value_of_judgment: AdvantageView  # adaptive over the best fixed strategy, on the same futures
    departure_share: float  # share of decision-years (over every evaluation path) the planner leaves the fixed strategy
    departure_by_decision: dict[str, float]
    departure_by_year: list[float]  # for each year, the share of evaluation futures in which the planner changes anything
    departure_by_year_and_decision: dict[str, list[float]]  # ... and for each decision separately
    from_cache: bool = False


class AdaptiveJob(BaseModel):
    id: str
    status: Literal["running", "done", "error", "cancelled"]
    progress: float  # 0 to 1
    error: str | None = None
    result: AdaptiveSection | None = None


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
    baselines: list[BaselineView]  # good RIA, then typical advisor
    liability: LiabilityView | None = None  # the liability-matched style's limits and how the plan stands against them
    advantage: list[AdvantageStep]
    searched: list[RankedRow]
    settings: PlanSettings
    adaptive: AdaptiveSection | None = None  # present at once when it was precomputed (demo mode), else see adaptive_job
    adaptive_job: str | None = None  # poll GET /plan/adaptive/{id} for the year-by-year plan


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
    charitable_giving: float | None = Field(None, ge=0)
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
    n_eval_paths: int = Field(200, ge=50, le=5_000)
    demo_mode: bool = True
    seed: int | None = None
    risk_aversion: float = Field(3.0, ge=0.5, le=10.0)
    planning_style: Literal["balanced", "equity_first", "liability_matched"] = "equity_first"
    adaptive: bool = True
    adaptive_rollouts: int = Field(32, ge=4, le=128)
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



# --------------------------------------------------------------------------------------------
# The showcase household: summary card, strategy waterfall, wealth over time
# --------------------------------------------------------------------------------------------


class CardPerson(BaseModel):
    label: str
    age: int
    wages: float


class CardAccount(BaseModel):
    key: Literal["taxable", "pretax", "roth", "cash"]
    label: str
    value: float
    share: float  # of everything the household has saved
    basis: float | None = None  # the taxable account only
    unrealized_gain: float | None = None


class CardGoal(BaseModel):
    key: Literal["home", "college", "retirement", "social_security"]
    label: str
    detail: str
    years_from_now: int | None = None
    amount: float | None = None


class HouseholdCard(BaseModel):
    """Everything the summary card shows, computed from the household."""

    people: list[CardPerson]
    children_ages: list[int]
    annual_income: float
    total_savings: float
    accounts: list[CardAccount]
    goals: list[CardGoal]
    notes: list[str]  # what stands out about this household, each computed from its numbers


class ShowcaseBar(BaseModel):
    """One strategy of the waterfall."""

    key: str
    label: str
    detail: str
    enabled: bool
    delta_rate: float  # change in the annual advantage over the advisor (a fraction: 0.004 is 0.4% a year)
    delta_dollars: float  # change in median after-tax wealth at the horizon
    cumulative_rate: float
    cumulative_dollars: float


class WealthLines(BaseModel):
    ages: list[int]  # today's age first
    plan_median: list[float]
    plan_p10: list[float]
    advisor_median: list[float]
    advisor_p10: list[float]


class ShowcaseMedian(BaseModel):
    """The waterfall's headline: the median advantage and nothing else."""

    median_rate: float  # annual growth-rate advantage of median after-tax wealth at the horizon (a fraction)
    median_dollars: float
    median_low: float  # the 5th to 95th percentile over resamples of the futures
    median_high: float
    plan_median_at_horizon: float
    advisor_median_at_horizon: float


class ShowcaseWaterfall(BaseModel):
    """The strategies switched on in sequence on the same futures: one bar each, and what they add up to (median only)."""

    enabled: list[str]
    bars: list[ShowcaseBar]
    advantage: ShowcaseMedian
    n_paths: int
    years: int
    horizon_age: int
    advisor_label: str


class ShowcaseAdvantage(BaseModel):
    median_rate: float  # annual growth-rate advantage of median after-tax wealth at the horizon (a fraction)
    median_dollars: float
    median_low: float  # the 5th to 95th percentile over resamples of the futures
    median_high: float
    risk_adjusted_rate: float
    risk_adjusted_dollars: float
    plan_median_at_horizon: float
    advisor_median_at_horizon: float
    plan_p10_at_horizon: float
    advisor_p10_at_horizon: float
    plan_shortfall: float  # share of futures in which the plan runs out of money
    advisor_shortfall: float


class ShowcaseHeirs(BaseModel):
    """The same plan and advisor with the estate passed to heirs at the horizon (step-up on the taxable account, the pre-tax
    accounts taxed at the heirs' rate), on the same futures. The median only: the risk-adjusted advantage is shown once."""

    label: str
    note: str  # what it assumes and why, with the rate
    rate: float  # the heirs' flat tax rate on pre-tax accounts
    median_rate: float
    median_dollars: float
    plan_median_at_horizon: float
    advisor_median_at_horizon: float


class ShowcaseWealth(BaseModel):
    """The whole plan (every strategy on) against the advisor: wealth over time and both measures of the advantage.

    Worked out once. Switching strategies off on the waterfall does not change it."""

    liquidated_label: str  # the valuation of `advantage` and the wealth lines: everything sold at 80
    advantage: ShowcaseAdvantage
    heirs: ShowcaseHeirs
    wealth: WealthLines
    risk_adjusted_label: str
    risk_adjusted_explanation: str  # one line
    n_paths: int
    years: int
    horizon_age: int
    risk_aversion: float
    advisor_label: str


class ShowcaseRequest(BaseModel):
    enabled: list[str] | None = None  # strategy keys left on, None for all of them


class ShowcaseResponse(BaseModel):
    id: str
    name: str
    type_label: str
    tagline: str
    household: Household
    card: HouseholdCard
    plan_label: str  # the recommendation in one line
    plan_sentence: str  # the recommendation in plain language
    waterfall: ShowcaseWaterfall  # every strategy on
    wealth: ShowcaseWealth  # the whole plan
    typical_rate: float | None  # the typical household's median advantage a year (a fraction), from the 300-household study
    footer_note: str  # what the showcase footer adds: these results are for this household, and what a typical one sees
