"""Test doubles that satisfy the ML interfaces, used only to exercise the plumbing in tests.

These are not models and are never installed in `backend/models/`.
"""

from __future__ import annotations

from app.ml.interfaces import (
    ActionChoice,
    ActionProposal,
    ChoiceRecommendation,
    Factor,
    IncomeForecast,
    OptionProbability,
    ProposedAction,
    Recommendation,
    ValueEstimate,
)
from app.planner.strategies import CHOICE_OPTIONS, CHOICES


class StubRecommender:
    def __init__(self, picks: dict[str, str] | None = None, with_distribution: bool = False):
        self.picks = picks or {
            "stock_share": "90",
            "conversion": "none",
            "private_credit": "10",
            "direct_indexing": "on",
            "goal_bonds": "off",
            "k401": "pretax",
            "goal_funding": "sell",
            "reserve": "off",
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


class SevenChoiceRecommender:
    """A model written before the spending reserve was a choice: it names the first seven only."""

    def recommend(self, household):
        full = StubRecommender().recommend(household)
        return {"choices": [c.model_dump() for c in full.choices if c.choice != "reserve"], "top_factors": []}


class RaisingRecommender:
    def recommend(self, household):
        raise RuntimeError("model blew up")


class WrongLengthForecaster:
    def forecast(self, household, years):
        return StubForecaster().forecast(household, years + 1)


class NoMethod:
    pass


class StubPolicyModel:
    """Proposes the continuation action first, then the same action with one more year of private credit."""

    def propose(self, state, max_actions):
        base = state.continuation
        other = base.model_copy(update={"private_credit": 0.15 if base.private_credit < 0.15 else 0.0})
        actions = [ProposedAction(action=base, probability=0.7), ProposedAction(action=other, probability=0.2)]
        return ActionProposal(actions=actions[:max_actions], top_factors=[Factor(feature="total_wealth", direction="up", weight=0.4)])


class StubValueModel:
    """Values every action at the household's wealth, a little more for a higher stock share."""

    def value(self, state, actions):
        wealth = max(state.state["total_wealth"], 1.0)
        return ValueEstimate(values=[wealth * (1.0 + 0.1 * a.stock_share) for a in actions])


class DictPolicyModel:
    def propose(self, state, max_actions):
        action = state.continuation.model_dump()
        return {"actions": [{"action": action, "probability": 0.5}]}


class TooManyActionsPolicyModel:
    def propose(self, state, max_actions):
        actions = []
        for share in (0.5, 0.6, 0.7, 0.8):
            actions.append(ProposedAction(action=state.continuation.model_copy(update={"stock_share": share}), probability=0.2))
        return ActionProposal(actions=actions)


class WrongLengthValueModel:
    def value(self, state, actions):
        return ValueEstimate(values=[1.0] * (len(actions) + 1))


class NegativeValueModel:
    def value(self, state, actions):
        return {"values": [-5.0 for _ in actions]}


def sample_action(**overrides) -> ActionChoice:
    data = dict(stock_share=0.5, conversion_bracket=24, private_credit=0.15, k401="pretax", goal_funding="sell", realize_gains=False)
    data.update(overrides)
    return ActionChoice(**data)
