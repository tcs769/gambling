"""Search over the strategy menu.

Every strategy is evaluated on the same N futures (common random numbers). The score is the
certainty-equivalent after-tax wealth at 70 under CRRA utility with risk aversion 3 and a
$50,000 floor: the guaranteed amount that would be exactly as good as the risky distribution.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import numpy as np

from app.planner.strategies import Strategy, menu
from app.sim.simulate import BatchResult, Policy, SimInputs, run_batch

RISK_AVERSION = 3.0
WEALTH_FLOOR = 50_000.0


def certainty_equivalent(
    wealth: np.ndarray, risk_aversion: float = RISK_AVERSION, floor: float = WEALTH_FLOOR
) -> np.ndarray:
    """CRRA certainty equivalent over the last axis (paths). Wealth below the floor counts as the floor."""
    w = np.maximum(wealth, floor)
    if risk_aversion == 1.0:
        return np.exp(np.mean(np.log(w), axis=-1))
    exponent = 1.0 - risk_aversion
    return np.mean(w**exponent, axis=-1) ** (1.0 / exponent)


@dataclass(frozen=True)
class Outcome:
    """Summary of one strategy's after-tax wealth at 70 across the futures."""

    median: float
    p10: float
    p90: float
    score: float  # certainty-equivalent wealth

    @classmethod
    def of(cls, wealth: np.ndarray) -> Outcome:
        p10, median, p90 = np.percentile(wealth, [10, 50, 90])
        return cls(float(median), float(p10), float(p90), float(certainty_equivalent(wealth)))


@dataclass(frozen=True)
class RankedStrategy:
    rank: int
    strategy: Strategy
    outcome: Outcome
    tied_with: int | None  # rank of the first strategy with an identical result, if any


@dataclass
class SearchResult:
    ranked: list[RankedStrategy]
    batch: BatchResult
    strategies: list[Strategy]
    n_paths: int
    elapsed_seconds: float

    @property
    def best(self) -> RankedStrategy:
        return self.ranked[0]

    def index_of(self, strategy: Strategy) -> int:
        return self.strategies.index(strategy)

    def outcome_of(self, strategy: Strategy) -> Outcome:
        return Outcome.of(self.batch.wealth[self.index_of(strategy)])


def rank_strategies(strategies: list[Strategy], wealth: np.ndarray) -> list[RankedStrategy]:
    """Order strategies by certainty-equivalent wealth, best first (ties keep menu order)."""
    scores = certainty_equivalent(wealth)
    order = np.argsort(-scores, kind="stable")
    seen: dict[bytes, int] = {}
    ranked: list[RankedStrategy] = []
    for position, i in enumerate(order, start=1):
        fingerprint = np.round(wealth[i], 2).tobytes()
        tied = seen.get(fingerprint)
        seen.setdefault(fingerprint, position)
        ranked.append(RankedStrategy(position, strategies[i], Outcome.of(wealth[i]), tied))
    return ranked


def search(
    inputs: SimInputs,
    strategies: list[Strategy] | None = None,
    extra_policies: list[Policy] | None = None,
    record_paths: bool = False,
) -> SearchResult:
    """Evaluate `strategies` (default: the full menu) on the futures in `inputs`."""
    strategies = strategies if strategies is not None else menu()
    started = time.perf_counter()
    policies = [s.policy() for s in strategies] + list(extra_policies or [])
    batch = run_batch(inputs, policies, record_paths=record_paths)
    n = len(strategies)
    ranked = rank_strategies(strategies, batch.wealth[:n])
    return SearchResult(
        ranked=ranked,
        batch=batch,
        strategies=strategies,
        n_paths=inputs.n_paths,
        elapsed_seconds=time.perf_counter() - started,
    )
