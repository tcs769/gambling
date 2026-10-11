"""Using the strategy recommender: turn its answer into candidates for the engine to verify.

When the recommender is connected the planner scores the model's top recommendation plus its
five nearest alternatives with the search engine, instead of searching the whole menu. The
alternatives are the five strategies of the planning style's menu closest to the recommendation
(fewest and smallest option changes); ties are broken by the model's own joint probability, then
menu order.
"""

from __future__ import annotations

from app.ml.interfaces import Recommendation
from app.planner.strategies import CHOICE_OPTIONS, CHOICES, Strategy, menu

N_ALTERNATIVES = 5


def strategy_from_recommendation(rec: Recommendation) -> Strategy:
    return Strategy.from_choices({choice: rec.option(choice) for choice in CHOICES})


def distance(a: Strategy, b: Strategy) -> int:
    """Sum over the eight choices of how many options apart the two strategies are."""
    ca, cb = a.choices(), b.choices()
    return sum(
        abs(CHOICE_OPTIONS[c].index(ca[c]) - CHOICE_OPTIONS[c].index(cb[c])) for c in CHOICES
    )


def joint_probability(rec: Recommendation, strategy: Strategy) -> float:
    """Product of the model's per-choice probabilities for `strategy` (0 where it gave none)."""
    chosen = strategy.choices()
    total = 1.0
    for entry in rec.choices:
        if entry.distribution:
            p = next((d.probability for d in entry.distribution if d.option == chosen[entry.choice]), 0.0)
        else:
            p = entry.probability if entry.option == chosen[entry.choice] else 0.0
        total *= p
    return total


def candidates(rec: Recommendation, k: int = N_ALTERNATIVES, style: str = "balanced") -> tuple[Strategy, list[Strategy]]:
    """The model's top strategy and its `k` nearest alternatives from the planning style's menu."""
    top = strategy_from_recommendation(rec)
    others = [s for s in menu(style=style) if s != top]
    order = {s: i for i, s in enumerate(others)}
    others.sort(key=lambda s: (distance(top, s), -joint_probability(rec, s), order[s]))
    return top, others[:k]
