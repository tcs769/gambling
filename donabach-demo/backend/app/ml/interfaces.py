"""Contracts for the two machine-learning models that plug into Donabach.

The models are built separately. This module defines what they must accept and return, and
`household_features`, the exact feature vector the app builds for them, so the models are
trained on what the app will actually feed them.

Strategy recommender
    `recommend(household) -> Recommendation`
    For each of the five strategy choices (`CHOICES`): the option it recommends, the
    probability it assigns that option (0 to 1), optionally the full distribution over options,
    plus `top_factors` for the explanation. Options must come from `CHOICE_OPTIONS`.

Income forecaster
    `forecast(household, years) -> IncomeForecast`
    Per-year quantiles (p10, p25, p50, p75, p90) of household income in real 2026 dollars, for
    the next `years` years, plus `top_factors`.

Until a model file is dropped in (see `app.ml.adapters`) the app shows "Model not connected".
Nothing here, or anywhere else in the app, invents a prediction.
"""

from __future__ import annotations

import math
from typing import Literal, Protocol, runtime_checkable

from pydantic import BaseModel, Field, field_validator, model_validator

from app.planner.strategies import CHOICE_OPTIONS, CHOICES
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
    "FEATURE_NAMES",
    "ChoiceRecommendation",
    "Factor",
    "IncomeForecast",
    "IncomeForecaster",
    "OptionProbability",
    "Recommendation",
    "StrategyRecommender",
    "feature_vector",
    "household_features",
]
