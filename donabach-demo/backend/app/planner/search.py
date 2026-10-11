"""Search over the strategy menu.

Every strategy is evaluated on the same N futures (common random numbers). The score is the
certainty-equivalent after-tax wealth at the horizon (age 80) under CRRA utility with risk aversion 3 and a
$50,000 floor: the guaranteed amount that would be exactly as good as the risky distribution.

With thousands of strategies the search is staged: every strategy is first scored on a quarter of the
futures, and only the best few go on to the full set (`SCREEN_KEEP`). Scoring all of them on every
future takes seconds; this takes about one. `search(..., exhaustive=True)` scores everything on
everything, and `tests/test_planner.py` checks that the two agree on the winner.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, replace

import numpy as np

from app.planner.strategies import Strategy, menu
from app.sim.simulate import BatchResult, Policy, SimInputs, run_batch

RISK_AVERSION = 3.0
WEALTH_FLOOR = 50_000.0

SCREEN_PATHS = 100  # futures used to screen the whole menu
SCREEN_KEEP = 150  # strategies that go on to be scored on every future
SCREEN_MIN_STRATEGIES = 400  # smaller menus are scored exhaustively


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
    """Summary of one strategy's after-tax wealth at the horizon across the futures."""

    median: float
    p10: float
    p90: float
    score: float  # certainty-equivalent wealth

    @classmethod
    def of(cls, wealth: np.ndarray, risk_aversion: float = RISK_AVERSION) -> Outcome:
        p10, median, p90 = np.percentile(wealth, [10, 50, 90])
        return cls(float(median), float(p10), float(p90), float(certainty_equivalent(wealth, risk_aversion)))


@dataclass(frozen=True)
class RankedStrategy:
    rank: int
    strategy: Strategy
    outcome: Outcome
    tied_with: int | None  # rank of the first strategy with an identical result, if any


@dataclass
class SearchResult:
    ranked: list[RankedStrategy]  # strategies scored on every future, best first
    batch: BatchResult  # their results (and any extra policies') on every future
    strategies: list[Strategy]  # the strategies in `batch`, in the order of its rows
    n_paths: int
    elapsed_seconds: float
    n_considered: int = 0  # the whole menu, of which `strategies` survived the screen

    @property
    def best(self) -> RankedStrategy:
        return self.ranked[0]

    def index_of(self, strategy: Strategy) -> int:
        return self.strategies.index(strategy)

    def outcome_of(self, strategy: Strategy, risk_aversion: float = RISK_AVERSION) -> Outcome:
        return Outcome.of(self.batch.wealth[self.index_of(strategy)], risk_aversion)


def rank_strategies(
    strategies: list[Strategy], wealth: np.ndarray, risk_aversion: float = RISK_AVERSION
) -> list[RankedStrategy]:
    """Order strategies by certainty-equivalent wealth, best first (ties keep menu order)."""
    scores = certainty_equivalent(wealth, risk_aversion)
    order = np.argsort(-scores, kind="stable")
    seen: dict[bytes, int] = {}
    ranked: list[RankedStrategy] = []
    for position, i in enumerate(order, start=1):
        fingerprint = np.round(wealth[i], 2).tobytes()
        tied = seen.get(fingerprint)
        seen.setdefault(fingerprint, position)
        ranked.append(RankedStrategy(position, strategies[i], Outcome.of(wealth[i], risk_aversion), tied))
    return ranked


def subset_inputs(inputs: SimInputs, n_paths: int) -> SimInputs:
    """The first `n_paths` futures of `inputs` (the same futures, so scores stay comparable)."""
    return replace(
        inputs,
        n_paths=n_paths,
        rets=inputs.rets[:n_paths],
        wages=inputs.wages[:n_paths],
        k401=inputs.k401[:n_paths],
        wage_tax=inputs.wage_tax[:n_paths],
        logperm=None if inputs.logperm is None else inputs.logperm[:n_paths],
    )


def search(
    inputs: SimInputs,
    strategies: list[Strategy] | None = None,
    extra_policies: list[Policy] | None = None,
    record_paths: bool = False,
    exhaustive: bool = False,
    risk_aversion: float = RISK_AVERSION,
) -> SearchResult:
    """Evaluate `strategies` (default: the full menu) on the futures in `inputs`."""
    strategies = strategies if strategies is not None else menu()
    started = time.perf_counter()
    considered = len(strategies)
    if not exhaustive and considered > SCREEN_MIN_STRATEGIES and inputs.n_paths > 2 * SCREEN_PATHS:
        screen = run_batch(subset_inputs(inputs, SCREEN_PATHS), [s.policy() for s in strategies]).wealth
        scores = certainty_equivalent(screen, risk_aversion)
        keep = sorted(np.argsort(-scores, kind="stable")[:SCREEN_KEEP].tolist())  # menu order breaks ties
        strategies = [strategies[i] for i in keep]
    policies = [s.policy() for s in strategies] + list(extra_policies or [])
    batch = run_batch(inputs, policies, record_paths=record_paths)
    n = len(strategies)
    ranked = rank_strategies(strategies, batch.wealth[:n], risk_aversion)
    return SearchResult(
        ranked=ranked,
        batch=batch,
        strategies=strategies,
        n_paths=inputs.n_paths,
        elapsed_seconds=time.perf_counter() - started,
        n_considered=considered,
    )
