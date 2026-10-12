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
from collections.abc import Callable
from dataclasses import dataclass, replace

import numpy as np

from app.planner.baseline import RIA_BASELINE
from app.planner.strategies import Strategy, menu
from app.sim.simulate import BatchResult, Policy, SimInputs, run_batch

RISK_AVERSION = 3.0
WEALTH_FLOOR = 50_000.0

SCREEN_PATHS = 100  # futures used to screen the whole menu (at 64 or 80 the staged search missed the exhaustive winner on the demo household)
SCREEN_KEEP = 110  # strategies that go on to be scored on every future
SCREEN_MIN_STRATEGIES = 400  # smaller menus are scored exhaustively
REFINE_DIRECT_INDEXING = 8  # direct-indexing strategies scored on every future with the stock-level book
DI_PER_GROUP_POOL = 6  # with groups: direct-indexing strategies of each group the screen passes on, ranked on every future with the aggregate rule
DI_PER_GROUP = 2  # and the best of them that go on to be scored with the stock-level book
DI_SCREEN_PATHS = 100  # futures the direct-indexing strategies are screened on
DI_POOL = 30  # direct-indexing strategies the screen passes on, to be ranked on every future with the aggregate rule


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


def median_wealth(wealth: np.ndarray) -> np.ndarray:
    """The median over the last axis (paths): the criterion of the maximum-gap study, which asks for the biggest median advantage."""
    return np.median(wealth, axis=-1)


def rank_strategies(
    strategies: list[Strategy], wealth: np.ndarray, risk_aversion: float = RISK_AVERSION, criterion: Callable[[np.ndarray], np.ndarray] | None = None
) -> list[RankedStrategy]:
    """Order strategies by certainty-equivalent wealth (or by `criterion`), best first (ties keep menu order)."""
    scores = certainty_equivalent(wealth, risk_aversion) if criterion is None else criterion(wealth)
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
    group_of: Callable[[Strategy], int] | None = None,
    criterion: Callable[[np.ndarray], np.ndarray] | None = None,
    screen_mask: Callable[[BatchResult], np.ndarray] | None = None,
) -> SearchResult:
    """Evaluate `strategies` (default: the full menu) on the futures in `inputs`. In a staged search at most `refine` of
    the strategies that direct-index survive the screen (see the module's note). `valuation` is the wealth the score is of:
    "liquidated" (everything sold at the horizon, the app's) or "heirs" (passed to heirs: a step-up, the heirs' tax rate). With
    `group_of` (a strategy's group, such as its reserve length) a staged search keeps the best of every group, so that a group the
    screen ranks low as a whole (a long reserve) is still scored on every future when a constraint rules the others out.
    `criterion` replaces the certainty equivalent as the score (rows are strategies, columns futures), and `screen_mask`, given the screen's
    results, says which strategies may pass the screen (a constraint checked on the screen's futures)."""
    if valuation not in ("liquidated", "heirs"):
        raise ValueError(f"unknown valuation {valuation!r}; expected 'liquidated' or 'heirs'")

    def wealth_of(batch: BatchResult) -> np.ndarray:
        return batch.wealth if valuation == "liquidated" else batch.wealth_heirs

    def score_of(wealth: np.ndarray) -> np.ndarray:
        return certainty_equivalent(wealth, risk_aversion) if criterion is None else criterion(wealth)

    strategies = strategies if strategies is not None else menu()
    started = time.perf_counter()
    considered = len(strategies)
    if not exhaustive and considered > SCREEN_MIN_STRATEGIES and inputs.n_paths > 2 * SCREEN_PATHS:
        # The strategies that direct-index are screened on fewer futures: the screen only picks a pool of them (`DI_POOL`) that is then
        # ranked on every future, and their selection is separate from the others' in any case.
        by_stock = np.array([_by_stock(s) for s in strategies])
        screen_scores = np.empty(len(strategies))
        for members, paths in ((~by_stock, SCREEN_PATHS), (by_stock, DI_SCREEN_PATHS)):
            idx = np.flatnonzero(members)
            if idx.size == 0:
                continue
            part = run_batch(subset_inputs(inputs, paths), [_aggregate(strategies[i].policy()) for i in idx])
            scores = score_of(wealth_of(part))
            if screen_mask is not None:
                scores = np.where(screen_mask(part), scores, -np.inf)
            screen_scores[idx] = scores
        order = np.argsort(-screen_scores, kind="stable").tolist()
        if group_of is None:
            pool = [i for i in order if _by_stock(strategies[i])][: max(DI_POOL, refine)]
            if len(pool) > refine:
                # the screen's 100 futures are too few to tell near-identical strategies apart: rank the pool on every future (still with
                # the aggregate rule, which costs what a fund does) and take the best of it
                on_all = wealth_of(run_batch(inputs, [_aggregate(strategies[i].policy()) for i in pool]))
                pool = [pool[j] for j in np.argsort(-score_of(on_all), kind="stable")[:refine]]
            rest = [i for i in order if not _by_stock(strategies[i])][: SCREEN_KEEP - len(pool)]
        else:
            groups = sorted({group_of(s) for s in strategies})
            by_group = {g: [i for i in order if group_of(strategies[i]) == g] for g in groups}
            wide = [i for g in groups for i in [j for j in by_group[g] if _by_stock(strategies[j])][:DI_PER_GROUP_POOL]]
            on_all = score_of(wealth_of(run_batch(inputs, [_aggregate(strategies[i].policy()) for i in wide])))
            pool = []
            for g in groups:
                members = sorted((j for j, i in enumerate(wide) if group_of(strategies[i]) == g), key=lambda j: -on_all[j])
                pool += [wide[j] for j in members[:DI_PER_GROUP]]
            quota = max(1, (SCREEN_KEEP - len(pool)) // len(groups))
            rest = [i for g in groups for i in [j for j in by_group[g] if not _by_stock(strategies[j])][:quota]]
        strategies = [strategies[i] for i in sorted(pool + rest)]  # menu order breaks ties
    policies = [s.policy() for s in strategies] + list(extra_policies or [])
    batch = run_batch(inputs, policies, record_paths=record_paths)
    n = len(strategies)
    ranked = rank_strategies(strategies, wealth_of(batch)[:n], risk_aversion, criterion)
    return SearchResult(
        ranked=ranked,
        batch=batch,
        strategies=strategies,
        n_paths=inputs.n_paths,
        elapsed_seconds=time.perf_counter() - started,
        n_considered=considered,
    )


FORCED_SALE_LIMIT = 0.02  # the liability-matched plan sells stocks in a falling year to pay for goals or spending in at most this share of futures


@dataclass(frozen=True)
class MatchedChoice:
    """What the liability-matched search found: the strategy it picked and how it stands against its two limits."""

    strategy: Strategy
    forced_sale_chance: float
    ruin_chance: float
    advisor_ruin_chance: float
    feasible: bool  # False: nothing in the menu met both limits, and this is the one that came closest


def feasibility_mask(inputs: SimInputs, limit: float = FORCED_SALE_LIMIT, forced_slack: float = 0.06, ruin_slack: float = 0.03):
    """A `screen_mask` for the liability-matched search: a strategy may pass the screen when, on the screen's own futures, its chance of a
    forced sale is within `forced_slack` of the limit and its chance of ruin within `ruin_slack` of the good advisor's (a screen of a
    hundred futures cannot tell 2% from 4%, so it is only asked to keep the clearly infeasible out of the finalists)."""

    def mask(batch: BatchResult) -> np.ndarray:
        advisor = run_batch(subset_inputs(inputs, batch.wealth.shape[1]), [RIA_BASELINE])
        ruin_limit = float(np.mean(advisor.unfunded[0] > 0)) + ruin_slack
        return (np.mean(batch.forced_years > 0, axis=1) <= limit + forced_slack) & (np.mean(batch.unfunded > 0, axis=1) <= ruin_limit)

    return mask


def matched_choice(result: SearchResult, advisor_unfunded: np.ndarray, limit: float = FORCED_SALE_LIMIT, validation: BatchResult | None = None) -> MatchedChoice:
    """Among the strategies scored on every future, the best (by median wealth, which is the gap over the advisor and so, within the
    limits, the most in stocks) whose chance of a forced sale in a falling year is at most `limit` and whose chance of running out of
    money is no higher than the advisor's (`advisor_unfunded`, one value per future). With none feasible, the strategy with the least
    excess over the two limits.

    `validation` is the same strategies (and then the advisor) run on more futures, which the search never saw: the chances and the median
    are then those of both sets together. A limit checked on the futures the best of many strategies was picked on is optimistic (the one
    that happens to have few forced sales there wins), and the extra futures are what makes the limit mean something."""
    n = len(result.strategies)
    wealth = result.batch.wealth[:n]
    forced_paths = result.batch.forced_years[:n] > 0
    ruin_paths = result.batch.unfunded[:n] > 0
    advisor_paths = advisor_unfunded > 0
    if validation is not None:
        wealth = np.concatenate([wealth, validation.wealth[:n]], axis=1)
        forced_paths = np.concatenate([forced_paths, validation.forced_years[:n] > 0], axis=1)
        ruin_paths = np.concatenate([ruin_paths, validation.unfunded[:n] > 0], axis=1)
        advisor_paths = np.concatenate([advisor_paths, validation.unfunded[n] > 0])
    forced = np.mean(forced_paths, axis=1)
    ruin = np.mean(ruin_paths, axis=1)
    advisor = float(np.mean(advisor_paths))
    median = np.median(wealth, axis=1)
    ok = (forced <= limit + 1e-12) & (ruin <= advisor + 1e-12)
    feasible = [i for i in np.argsort(-median, kind="stable") if ok[i]]
    if feasible:
        i = int(feasible[0])
        return MatchedChoice(result.strategies[i], float(forced[i]), float(ruin[i]), advisor, True)
    excess = np.maximum(0.0, forced - limit) + np.maximum(0.0, ruin - advisor)
    i = int(np.argmin(excess))
    return MatchedChoice(result.strategies[i], float(forced[i]), float(ruin[i]), advisor, False)


def search_matched(
    inputs: SimInputs, validation_inputs: SimInputs, strategies: list[Strategy] | None = None, limit: float = FORCED_SALE_LIMIT
) -> tuple[SearchResult, MatchedChoice]:
    """The liability-matched planner: the staged search of the strategies by median wealth, kept to those that look feasible on the
    screen's futures and with the best of every reserve length going on to be scored on every future; then the finalists are run on
    `validation_inputs` too and the best that meets both limits on all the futures together is chosen (`matched_choice`)."""
    strategies = strategies if strategies is not None else menu(style="liability_matched")
    result = search(
        inputs, strategies=strategies, extra_policies=[RIA_BASELINE], group_of=lambda s: s.reserve_years,
        screen_mask=feasibility_mask(inputs), criterion=median_wealth,
    )
    n = len(result.strategies)
    validation = run_batch(validation_inputs, [s.policy() for s in result.strategies] + [RIA_BASELINE])
    return result, matched_choice(result, result.batch.unfunded[n], limit, validation)
