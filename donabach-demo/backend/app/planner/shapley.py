"""Shapley attribution of the advantage over the advisor, beside the sequential waterfall.

The waterfall (`app.planner.waterfall`) switches the plan's strategies on in a fixed order, so a strategy that works best with another
gets less or more credit depending on where it stands in the order. The Shapley value does not depend on an order: a strategy's share is its
added advantage averaged over every order the strategies could have been switched on in (equivalently, over every subset of the others it
could have joined). Every subset of the plan's strategies is run on the same futures (`2^k` policies, at most a thousand), the value of a
subset is the annualized growth-rate advantage of its median after-tax wealth over the advisor's, and the shares add up to the whole.

The strategies of the plan are field-disjoint changes to the advisor's policy (the fee, the asset location, the lots, ...), so a subset is
applied in the waterfall's order and the result does not depend on it.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from math import factorial

import numpy as np

from app.planner.baseline import RIA_BASELINE
from app.planner.strategies import Strategy
from app.planner.waterfall import waterfall_strategies
from app.sim.simulate import Policy, SimInputs, run_batch
from app.study import metrics


@dataclass(frozen=True)
class Share:
    key: str
    label: str
    sequential_rate: float  # the waterfall's bar, with every strategy on and in the waterfall's order
    shapley_rate: float  # the order-free share
    sequential_dollars: float
    shapley_dollars: float


def shapley_shares(inputs: SimInputs, strategy: Strategy, baseline: Policy = RIA_BASELINE) -> list[Share]:
    steps = waterfall_strategies(strategy, baseline)
    k = len(steps)
    subsets = [frozenset(c) for r in range(k + 1) for c in combinations(range(k), r)]

    def policy_of(subset: frozenset[int]) -> Policy:
        policy = baseline
        for i, step in enumerate(steps):
            if i in subset:
                policy = step.change(policy)
        return policy

    policies = [policy_of(s) for s in subsets]
    distinct = list(dict.fromkeys(policies))
    batch = run_batch(inputs, distinct)
    median_of = {p: float(np.median(batch.wealth[i])) for i, p in enumerate(distinct)}
    base = median_of[baseline]
    years = inputs.n_years
    value = {s: metrics.annualized(median_of[policy_of(s)], base, years) for s in subsets}
    dollars = {s: median_of[policy_of(s)] - base for s in subsets}

    def phi(i: int, table: dict[frozenset[int], float]) -> float:
        total = 0.0
        others = [j for j in range(k) if j != i]
        for r in range(k):
            weight = factorial(r) * factorial(k - r - 1) / factorial(k)
            for c in combinations(others, r):
                s = frozenset(c)
                total += weight * (table[s | {i}] - table[s])
        return total

    out = []
    sequence = frozenset()
    for i, step in enumerate(steps):
        before, after = sequence, sequence | {i}
        out.append(
            Share(
                key=step.key,
                label=step.label,
                sequential_rate=value[after] - value[before],
                shapley_rate=phi(i, value),
                sequential_dollars=dollars[after] - dollars[before],
                shapley_dollars=phi(i, dollars),
            )
        )
        sequence = after
    return out
