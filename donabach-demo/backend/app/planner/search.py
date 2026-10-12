"""Search over the strategy menu.

Every strategy is evaluated on the same N futures (common random numbers). The score is the
certainty-equivalent after-tax wealth at the horizon (age 80) under CRRA utility with risk aversion 3 and a
$50,000 floor: the guaranteed amount that would be exactly as good as the risky distribution.

With thousands of strategies the search is staged: every strategy is first scored on a quarter of the
futures, and only the best few go on to the full set (`SCREEN_KEEP`). Scoring all of them on every
future takes seconds; this takes about one. `search(..., exhaustive=True)` scores everything on
everything, and `tests/test_planner.py` checks that the two agree on the winner.

Direct indexing is simulated stock by stock (`app.sim.stocks`), which takes about thirty times as long as a fund on every
path. The search therefore ranks the strategies that direct-index with the aggregate harvest rule (the rule calibrated on the
stock-level book) in two steps, `DI_POOL` of them by the screen's scores and then the `REFINE_DIRECT_INDEXING` best of those on every
future; only those go on to every future with the stock-level book, beside the best of the strategies that do not direct-index
(those are the same either way). Every score in the ranking is therefore the engine's own, and a direct-indexing strategy is never
ranked on the rule it was screened with. (Against scoring every strategy at stock level on eight households of the equity-first menu,
the winner's score was the best one's every time; ranking the candidates on the screen's 100 futures alone missed it by up to 0.08%.)
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
REFINE_DIRECT_INDEXING = 8  # direct-indexing strategies scored on every future with the stock-level book
DI_POOL = 36  # direct-indexing strategies the screen passes on, to be ranked on every future with the aggregate rule


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
        stock_g=None if inputs.stock_g is None else inputs.stock_g[:n_paths],
    )


def _aggregate(policy: Policy) -> Policy:
    """The same policy with direct indexing on the account's totals (fast), when it direct-indexes stock by stock."""
    return policy.replace(di_model="aggregate") if policy.direct_indexing and policy.di_model == "stock" else policy


def _by_stock(strategy: Strategy) -> bool:
    return strategy.direct_indexing and strategy.policy().di_model == "stock"


def search(
    inputs: SimInputs,
    strategies: list[Strategy] | None = None,
    extra_policies: list[Policy] | None = None,
    record_paths: bool = False,
    exhaustive: bool = False,
    risk_aversion: float = RISK_AVERSION,
    refine: int = REFINE_DIRECT_INDEXING,
    valuation: str = "liquidated",
) -> SearchResult:
    """Evaluate `strategies` (default: the full menu) on the futures in `inputs`. In a staged search at most `refine` of
    the strategies that direct-index survive the screen (see the module's note). `valuation` is the wealth the score is of:
    "liquidated" (everything sold at the horizon, the app's) or "heirs" (passed to heirs: a step-up, the heirs' tax rate)."""
    if valuation not in ("liquidated", "heirs"):
        raise ValueError(f"unknown valuation {valuation!r}; expected 'liquidated' or 'heirs'")

    def wealth_of(batch: BatchResult) -> np.ndarray:
        return batch.wealth if valuation == "liquidated" else batch.wealth_heirs

    strategies = strategies if strategies is not None else menu()
    started = time.perf_counter()
    considered = len(strategies)
    if not exhaustive and considered > SCREEN_MIN_STRATEGIES and inputs.n_paths > 2 * SCREEN_PATHS:
        screen = wealth_of(run_batch(subset_inputs(inputs, SCREEN_PATHS), [_aggregate(s.policy()) for s in strategies]))
        order = np.argsort(-certainty_equivalent(screen, risk_aversion), kind="stable").tolist()
        pool = [i for i in order if _by_stock(strategies[i])][: max(DI_POOL, refine)]
        if len(pool) > refine:
            # the screen's 100 futures are too few to tell near-identical strategies apart: rank the pool on every future (still with
            # the aggregate rule, which costs what a fund does) and take the best of it
            on_all = wealth_of(run_batch(inputs, [_aggregate(strategies[i].policy()) for i in pool]))
            pool = [pool[j] for j in np.argsort(-certainty_equivalent(on_all, risk_aversion), kind="stable")[:refine]]
        rest = [i for i in order if not _by_stock(strategies[i])][: SCREEN_KEEP - len(pool)]
        strategies = [strategies[i] for i in sorted(pool + rest)]  # menu order breaks ties
    policies = [s.policy() for s in strategies] + list(extra_policies or [])
    batch = run_batch(inputs, policies, record_paths=record_paths)
    n = len(strategies)
    ranked = rank_strategies(strategies, wealth_of(batch)[:n], risk_aversion)
    return SearchResult(
        ranked=ranked,
        batch=batch,
        strategies=strategies,
        n_paths=inputs.n_paths,
        elapsed_seconds=time.perf_counter() - started,
        n_considered=considered,
    )
