"""Contracts for the two machine-learning models that plug into Donabach.

The models are built separately. This module defines what they must accept and return, and
`household_features`, the exact feature vector the app builds for them, so the models are
trained on what the app will actually feed them.

Strategy recommender
    `recommend(household) -> Recommendation`
    For each of the eight strategy choices (`CHOICES`): the option it recommends, the
    probability it assigns that option (0 to 1), optionally the full distribution over options,
    plus `top_factors` for the explanation. Options must come from `CHOICE_OPTIONS`, and the
    recommended options together must be a strategy the engine can run (a spending reserve other
    than "off" needs `stock_share` "100" and `goal_bonds` "off").

Income forecaster
    `forecast(household, years) -> IncomeForecast`
    Per-year quantiles (p10, p25, p50, p75, p90) of household income in real 2026 dollars, for
    the next `years` years, plus `top_factors`.

Policy model (year-by-year planner)
    `propose(state, max_actions) -> ActionProposal`
    The year-by-year planner picks each year's action by simulating rollouts (spec part B). The policy
    model is trained on what that search chose and will propose the actions worth scoring, each with the
    probability that the search would pick it, so the search can score a handful instead of dozens.

Value model (year-by-year planner)
    `value(state, actions) -> ValueEstimate`
    Trained on the certainty-equivalent scores the rollouts gave every candidate action. It estimates
    those scores from the state so the search can skip candidates that are clearly worse.

Until a model file is dropped in (see `app.ml.adapters`) the app shows "Model not connected".
Nothing here, or anywhere else in the app, invents a prediction.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Literal, Protocol, runtime_checkable

from pydantic import BaseModel, Field, field_validator, model_validator

from app.planner.strategies import CHOICE_OPTIONS, CHOICES, PRIVATE_CREDIT_SHARES, STOCK_SHARES, Strategy
from app.schemas import Household
from app.tax.picture import children_under_17, current_tax_return

# --------------------------------------------------------------------------------------------
# Results
# --------------------------------------------------------------------------------------------


class Factor(BaseModel):
    """One input that moved a prediction.

    direction: "up" if a higher value of the feature raises the output (the probability of the
    recommended option, or forecast income); "down" if it lowers it.
    weight: relative importance, 0 to 1.
    """

    feature: str
    direction: Literal["up", "down"]
    weight: float = Field(ge=0.0, le=1.0)


class OptionProbability(BaseModel):
    option: str
    probability: float = Field(ge=0.0, le=1.0)


class ChoiceRecommendation(BaseModel):
    choice: str  # one of CHOICES
    option: str  # the recommended option, from CHOICE_OPTIONS[choice]
    probability: float = Field(ge=0.0, le=1.0)  # the model's confidence in that option
    distribution: list[OptionProbability] | None = None  # optional: every option's probability

    @model_validator(mode="after")
    def _valid_option(self) -> ChoiceRecommendation:
        options = CHOICE_OPTIONS.get(self.choice)
        if options is None:
            raise ValueError(f"unknown strategy choice {self.choice!r}; expected one of {CHOICES}")
        if self.option not in options:
            raise ValueError(f"{self.option!r} is not an option for {self.choice!r}; expected one of {options}")
        for entry in self.distribution or []:
            if entry.option not in options:
                raise ValueError(f"{entry.option!r} is not an option for {self.choice!r}")
        return self


class Recommendation(BaseModel):
    choices: list[ChoiceRecommendation]
    top_factors: list[Factor] = Field(default_factory=list)

    @field_validator("choices")
    @classmethod
    def _one_per_choice(cls, choices: list[ChoiceRecommendation]) -> list[ChoiceRecommendation]:
        if sorted(c.choice for c in choices) != sorted(CHOICES):
            raise ValueError(f"expected exactly one entry for each of {CHOICES}")
        return choices

    @model_validator(mode="after")
    def _a_strategy_the_engine_can_run(self) -> Recommendation:
        # The options are chosen one by one, but not every combination is a strategy: a spending reserve holds
        # everything outside it in stocks and already pays for goals, so it needs stock_share 100 and goal_bonds off.
        try:
            Strategy.from_choices({c.choice: c.option for c in self.choices})
        except ValueError as exc:
            raise ValueError(f"the recommended options are not a strategy the engine can run: {exc}") from exc
        return self

    def option(self, choice: str) -> str:
        return next(c.option for c in self.choices if c.choice == choice)


QUANTILES = ("p10", "p25", "p50", "p75", "p90")


class IncomeForecast(BaseModel):
    ages: list[int]  # primary earner's age in each forecast year
    p10: list[float]
    p25: list[float]
    p50: list[float]
    p75: list[float]
    p90: list[float]
    top_factors: list[Factor] = Field(default_factory=list)

    @model_validator(mode="after")
    def _aligned_and_ordered(self) -> IncomeForecast:
        n = len(self.ages)
        series = [getattr(self, q) for q in QUANTILES]
        if any(len(s) != n for s in series):
            raise ValueError("every quantile series must have one value per age")
        for values in zip(*series, strict=True):
            if any(a > b + 1e-9 for a, b in zip(values, values[1:], strict=False)):
                raise ValueError("quantiles must be non-decreasing: p10 <= p25 <= p50 <= p75 <= p90")
        return self


# --------------------------------------------------------------------------------------------
# What the teammates implement
# --------------------------------------------------------------------------------------------


@runtime_checkable
class StrategyRecommender(Protocol):
    def recommend(self, household: Household) -> Recommendation: ...


@runtime_checkable
class IncomeForecaster(Protocol):
    def forecast(self, household: Household, years: int) -> IncomeForecast: ...


# --------------------------------------------------------------------------------------------
# The year-by-year planner's helper models (spec B7)
# --------------------------------------------------------------------------------------------

CONVERSION_BRACKETS = (0, 12, 22, 24)  # 0: no Roth conversion; else fill that federal bracket this year

# What the planner knows at a decision, beyond the household as it started (`household_features`): the
# state of the plan after this year's returns, in real 2026 dollars. Built by `app.planner.decision_data`.
STATE_FEATURE_NAMES = (
    # when
    "age",
    "year_index",
    "years_remaining",
    "retired",
    "years_to_retirement",
    "aged_spouses",
    "rmds_required",
    # balances by account and asset class
    "pretax_equity",
    "pretax_bonds",
    "pretax_private_credit",
    "roth_equity",
    "roth_bonds",
    "roth_private_credit",
    "brokerage_equity",
    "brokerage_basis",
    "brokerage_bonds_and_cash",
    "brokerage_private_credit",
    "goal_bucket",
    # shape of the balance sheet
    "total_wealth",
    "pretax_share",
    "roth_share",
    "taxable_share",
    "equity_share",
    "private_credit_share",
    "brokerage_unrealized_gain_share",
    "loss_carryforward",
    "loan",
    "loan_to_brokerage",
    "unfunded_so_far",
    # income
    "wages_this_year",
    "wages_expected_this_year",
    "wages_vs_expected",
    "k401_contribution_room_used",
    "social_security_this_year",
    "spending_need_from_portfolio",
    # goals
    "goal_due_this_year",
    "goal_amount_this_year",
    "goal_amount_next_three_years",
    "years_to_next_goal",
    # recent markets
    "equity_return_this_year",
    "bond_return_this_year",
    "equity_growth_last_three_years",
    "equity_growth_since_start",
)


class ActionChoice(BaseModel):
    """One year's action: the six decisions the year-by-year planner makes (spec B3)."""

    stock_share: float  # one of STOCK_SHARES
    conversion_bracket: int  # one of CONVERSION_BRACKETS
    private_credit: float  # one of PRIVATE_CREDIT_SHARES
    k401: Literal["pretax", "roth"]  # type of this year's 401(k) contribution
    goal_funding: Literal["sell", "borrow"]  # how a goal due this year is paid (ignored when none is due)
    realize_gains: bool  # realize gains up to the top of the 0% capital-gains bracket

    @model_validator(mode="after")
    def _on_the_menu(self) -> ActionChoice:
        if not any(abs(self.stock_share - share) < 1e-9 for share in STOCK_SHARES):
            raise ValueError(f"stock share {self.stock_share!r} is not one of {STOCK_SHARES}")
        if self.conversion_bracket not in CONVERSION_BRACKETS:
            raise ValueError(f"conversion bracket {self.conversion_bracket!r} is not one of {CONVERSION_BRACKETS}")
        if not any(abs(self.private_credit - share) < 1e-9 for share in PRIVATE_CREDIT_SHARES):
            raise ValueError(f"private credit share {self.private_credit!r} is not one of {PRIVATE_CREDIT_SHARES}")
        return self

    def key(self) -> tuple:
        return (round(self.stock_share, 6), self.conversion_bracket, round(self.private_credit, 6), self.k401, self.goal_funding, self.realize_gains)


class DecisionState(BaseModel):
    """What a helper model is shown at one decision of one path."""

    household: dict[str, float]  # `household_features` of the household as the plan started (FEATURE_NAMES)
    state: dict[str, float]  # the plan's state at this decision (STATE_FEATURE_NAMES)
    continuation: ActionChoice  # what the best fixed strategy would do this year

    @model_validator(mode="after")
    def _complete_and_finite(self) -> DecisionState:
        for label, values, names in (("household", self.household, FEATURE_NAMES), ("state", self.state, STATE_FEATURE_NAMES)):
            if set(values) != set(names):
                missing, extra = sorted(set(names) - set(values)), sorted(set(values) - set(names))
                raise ValueError(f"{label} features must be exactly the documented names (missing {missing}, unexpected {extra})")
            bad = [name for name, value in values.items() if not math.isfinite(value)]
            if bad:
                raise ValueError(f"{label} features must be finite; got non-finite values for {bad}")
        return self


class ProposedAction(BaseModel):
    action: ActionChoice
    probability: float = Field(ge=0.0, le=1.0)  # how likely the model thinks the search is to take this action


class ActionProposal(BaseModel):
    """The actions the policy model thinks worth scoring, best first."""

    actions: list[ProposedAction] = Field(min_length=1)
    top_factors: list[Factor] = Field(default_factory=list)

    @model_validator(mode="after")
    def _ordered_and_distinct(self) -> ActionProposal:
        probabilities = [a.probability for a in self.actions]
        if any(a < b - 1e-9 for a, b in zip(probabilities, probabilities[1:], strict=False)):
            raise ValueError("actions must be ordered from most to least probable")
        if sum(probabilities) > 1.0 + 1e-6:
            raise ValueError("the probabilities of distinct actions cannot sum to more than 1")
        if len({a.action.key() for a in self.actions}) != len(self.actions):
            raise ValueError("an action may be proposed only once")
        return self


class ValueEstimate(BaseModel):
    """Estimated certainty-equivalent after-tax wealth at the horizon (real 2026 dollars) of each action asked about."""

    values: list[float]
    top_factors: list[Factor] = Field(default_factory=list)

    @field_validator("values")
    @classmethod
    def _positive_and_finite(cls, values: list[float]) -> list[float]:
        if not all(math.isfinite(v) and v > 0 for v in values):
            raise ValueError("estimated values must be finite and positive dollars")
        return values


@runtime_checkable
class PolicyModel(Protocol):
    def propose(self, state: DecisionState, max_actions: int) -> ActionProposal: ...


@runtime_checkable
class ValueModel(Protocol):
    def value(self, state: DecisionState, actions: Sequence[ActionChoice]) -> ValueEstimate: ...


# --------------------------------------------------------------------------------------------
# Features
# --------------------------------------------------------------------------------------------

FEATURE_NAMES = (
    # who
    "age",
    "spouse_age",
    "n_earners",
    "n_children",
    "youngest_child_age",
    # income
    "wages_total",
    "wages_primary",
    "wages_secondary_share",
    "pretax_deferrals",
    # balances
    "pretax_balance",
    "roth_balance",
    "brokerage_value",
    "brokerage_unrealized_gain_share",
    "cash",
    "liquid_wealth",
    "pretax_share",
    "roth_share",
    "taxable_share",
    "pretax_equity_share",
    # balances relative to income
    "liquid_wealth_to_wages",
    "pretax_to_wages",
    "brokerage_to_wages",
    # goals
    "retirement_age",
    "years_to_retirement",
    "retirement_spending",
    "retirement_spending_to_wages",
    "has_home_goal",
    "years_to_home",
    "home_down_payment_to_wages",
    "has_college_goal",
    "years_to_college",
    "college_annual_cost_to_wages",
    "social_security_annual",
    "years_to_social_security",
    "charitable_giving",
    "charitable_giving_to_wages",
    # this year's tax picture
    "agi_now",
    "marginal_federal_rate_now",
    "effective_total_rate_now",
)

_NO_GOAL_YEARS = 99.0  # sentinel for "no such goal"; always paired with a has_* flag


def household_features(household: Household) -> dict[str, float]:
    """The feature vector the models consume, in `FEATURE_NAMES` order. All values are finite."""
    people = household.people
    a, g, ss = household.accounts, household.goals, household.social_security
    wages = max(household.total_wages, 1.0)  # denominator for the "relative to income" features
    liquid = max(household.liquid_wealth, 1.0)
    tax = current_tax_return(household)
    primary = people[0]
    secondary = people[1].wages if len(people) > 1 else 0.0
    deferrals = sum(p.pretax_401k for p in people)
    unrealized = max(0.0, a.brokerage_value - a.brokerage_basis)

    features = {
        "age": float(primary.age),
        "spouse_age": float(people[1].age) if len(people) > 1 else 0.0,
        "n_earners": float(sum(1 for p in people if p.wages > 0)),
        "n_children": float(children_under_17(household)),
        "youngest_child_age": float(min(household.children_ages)) if household.children_ages else -1.0,
        "wages_total": household.total_wages,
        "wages_primary": primary.wages,
        "wages_secondary_share": secondary / wages,
        "pretax_deferrals": deferrals,
        "pretax_balance": a.pretax_balance,
        "roth_balance": a.roth_balance,
        "brokerage_value": a.brokerage_value,
        "brokerage_unrealized_gain_share": unrealized / a.brokerage_value if a.brokerage_value > 0 else 0.0,
        "cash": a.cash,
        "liquid_wealth": household.liquid_wealth,
        "pretax_share": a.pretax_balance / liquid,
        "roth_share": a.roth_balance / liquid,
        "taxable_share": (a.brokerage_value + a.cash) / liquid,
        "pretax_equity_share": a.pretax_equity_share,
        "liquid_wealth_to_wages": household.liquid_wealth / wages,
        "pretax_to_wages": a.pretax_balance / wages,
        "brokerage_to_wages": a.brokerage_value / wages,
        "retirement_age": float(g.retirement_age),
        "years_to_retirement": float(g.retirement_age - primary.age),
        "retirement_spending": g.retirement_spending,
        "retirement_spending_to_wages": g.retirement_spending / wages,
        "has_home_goal": float(g.home_purchase_in_years is not None),
        "years_to_home": float(g.home_purchase_in_years) if g.home_purchase_in_years is not None else _NO_GOAL_YEARS,
        "home_down_payment_to_wages": g.home_down_payment / wages if g.home_purchase_in_years is not None else 0.0,
        "has_college_goal": float(g.college_starts_in_years is not None and g.college_years > 0),
        "years_to_college": float(g.college_starts_in_years) if g.college_starts_in_years is not None else _NO_GOAL_YEARS,
        "college_annual_cost_to_wages": g.college_annual_cost / wages if g.college_starts_in_years is not None else 0.0,
        "social_security_annual": ss.annual_benefit,
        "years_to_social_security": float(max(0, ss.start_age - primary.age)),
        "charitable_giving": g.charitable_giving,
        "charitable_giving_to_wages": g.charitable_giving / wages,
        "agi_now": tax.agi,
        "marginal_federal_rate_now": tax.marginal_federal_rate,
        "effective_total_rate_now": tax.effective_total_rate,
    }
    assert tuple(features) == FEATURE_NAMES
    assert all(math.isfinite(v) for v in features.values())
    return features


def feature_vector(household: Household) -> list[float]:
    return list(household_features(household).values())


__all__ = [
    "CONVERSION_BRACKETS",
    "FEATURE_NAMES",
    "STATE_FEATURE_NAMES",
    "ActionChoice",
    "ActionProposal",
    "ChoiceRecommendation",
    "DecisionState",
    "Factor",
    "IncomeForecast",
    "IncomeForecaster",
    "OptionProbability",
    "PolicyModel",
    "ProposedAction",
    "Recommendation",
    "StrategyRecommender",
    "ValueEstimate",
    "ValueModel",
    "feature_vector",
    "household_features",
]
