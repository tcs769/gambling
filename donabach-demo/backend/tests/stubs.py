"""Test doubles that satisfy the ML interfaces, used only to exercise the plumbing in tests.

These are not models and are never installed in `backend/models/`.
"""

from __future__ import annotations

from app.ml.interfaces import (
    ChoiceRecommendation,
    Factor,
    IncomeForecast,
    OptionProbability,
    Recommendation,
)
from app.planner.strategies import CHOICE_OPTIONS, CHOICES


class StubRecommender:
    def __init__(self, picks: dict[str, str] | None = None, with_distribution: bool = False):
        self.picks = picks or {
            "stock_share": "90",
            "conversion": "none",
            "private_credit": "on",
            "direct_indexing": "on",
            "goal_bonds": "off",
        }
        self.with_distribution = with_distribution

    def recommend(self, household):
        entries = []
        for choice in CHOICES:
            options = CHOICE_OPTIONS[choice]
            pick = self.picks[choice]
            distribution = None
            if self.with_distribution:
                rest = [o for o in options if o != pick]
                distribution = [OptionProbability(option=pick, probability=0.6)] + [
                    OptionProbability(option=o, probability=0.4 / len(rest)) for o in rest
                ]
            entries.append(ChoiceRecommendation(choice=choice, option=pick, probability=0.6, distribution=distribution))
        return Recommendation(choices=entries, top_factors=[Factor(feature="age", direction="up", weight=0.5)])


class StubForecaster:
    def forecast(self, household, years):
        wages = household.total_wages
        ages = [household.primary_age + t for t in range(years)]
        return IncomeForecast(
            ages=ages,
            p10=[0.8 * wages] * years,
            p25=[0.9 * wages] * years,
            p50=[wages] * years,
            p75=[1.1 * wages] * years,
            p90=[1.25 * wages] * years,
            top_factors=[Factor(feature="wages_total", direction="up", weight=0.9)],
        )


class BadOptionRecommender:
    def recommend(self, household):
        return {"choices": [{"choice": c, "option": "banana", "probability": 0.5} for c in CHOICES], "top_factors": []}


class DictRecommender:
    """Returns a plain dict, which the adapter validates into a Recommendation."""

    def recommend(self, household):
        return {
            "choices": [{"choice": c, "option": CHOICE_OPTIONS[c][0], "probability": 0.7} for c in CHOICES],
            "top_factors": [{"feature": "age", "direction": "down", "weight": 0.2}],
        }


class RaisingRecommender:
    def recommend(self, household):
        raise RuntimeError("model blew up")


class WrongLengthForecaster:
    def forecast(self, household, years):
        return StubForecaster().forecast(household, years + 1)


class NoMethod:
    pass
