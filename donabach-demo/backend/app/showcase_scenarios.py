"""The showcase household after an event: a job lost next year, or a stock market that falls 30% next year.

Each event is applied to every simulated future, the plan is searched again knowing about it (the showcase's own style and
limits, the same seed), and the new plan and the good advisor are measured on 2,000 other shocked futures. Beside the wealth
lines the year-by-year decisions of the plan before and after the event are set side by side on the expected path, and the
years in which they differ are marked, so a viewer sees what changed and not only the totals. Everything is worked out once,
at start-up when the demo is precomputed, and kept.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass

import numpy as np

from app import showcase
from app.api_models import (
    ScenarioChange,
    ScenarioInfo,
    ScenarioReplan,
    ScenarioYear,
    ShowcaseScenario,
)
from app.planner import plan as planner
from app.planner.plan import plan_rows
from app.planner.search import search_matched
from app.planner.strategies import menu
from app.schemas import JobLoss, MarketShock
from app.sim.simulate import build_inputs, run_batch, run_detail

CHANGE_DOLLARS = 1_000.0  # a year's conversion, harvest or wages must differ by this much to count as changed
CHANGE_SHARE = 0.02  # and the stock share by two points
MAX_SUMMARY = 4


@dataclass(frozen=True)
class Scenario:
    key: str
    label: str
    event: str
    shock: MarketShock | None = None
    job_loss: JobLoss | None = None


SCENARIOS: dict[str, Scenario] = {
    "job_loss": Scenario(
        key="job_loss",
        label="Job loss next year",
        event=(
            "The earner has no wages for a year, starting next year, and is back at the usual pay afterwards. Spending carries on; "
            "no unemployment insurance or severance is modeled."
        ),
        job_loss=JobLoss(year=1, years=1, keep=0.0),
    ),
    "market_drop": Scenario(
        key="market_drop",
        label="Market drops 30% next year",
        event="Stocks fall 30% next year in every simulated future; every other year is drawn as before.",
        shock=MarketShock(year=1, equity_return=-0.30),
    ),
}

# (key in the row, label, is it money)
FIELDS = [
    ("wages", "Wages", True),
    ("roth_conversion", "Roth conversion", True),
    ("losses_harvested", "Losses harvested", True),
    ("gains_harvested_tax_free", "Gains realized tax-free", True),
    ("stock_share", "Stock share", False),
]

ROW_FIELD = {"gains_harvested_tax_free": "gains_realized_tax_free"}  # the plan row's name for it

_lock = threading.RLock()
_scenarios: dict[str, ShowcaseScenario] = {}
_base_rows: dict[str, list] = {}


def infos() -> list[ScenarioInfo]:
    return [ScenarioInfo(key=s.key, label=s.label, event=s.event) for s in SCENARIOS.values()]


def _money(x: float) -> str:
    return f"${x:,.0f}"


def _sentence(age: int, key: str, before: float, after: float) -> str:
    if key == "wages":
        return f"At {age} wages are {_money(after)} instead of {_money(before)}."
    if key == "roth_conversion":
        if after < 0.5:
            return f"At {age} nothing is converted to Roth (before: {_money(before)})."
        return f"At {age} {_money(after)} is converted to Roth (before: {_money(before)})."
    if key == "losses_harvested":
        if after < 0.5:
            return f"At {age} no losses are harvested (before: {_money(before)})."
        return f"At {age} {_money(after)} of losses are harvested (before: {_money(before)})."
    if key == "gains_harvested_tax_free":
        if after < 0.5:
            return f"At {age} no gains are realized tax-free (before: {_money(before)})."
        return f"At {age} {_money(after)} of gains are realized tax-free (before: {_money(before)})."
    return f"At {age} the plan holds {after:.0%} stocks (before: {before:.0%})."


def _rows(household, strategy, scenario: Scenario | None):
    det = build_inputs(
        household, deterministic=True,
        shock=scenario.shock if scenario else None, job_loss=scenario.job_loss if scenario else None,
    )
    return plan_rows(run_detail(det, strategy.policy()).log, household)


def _base(prepared: showcase.Prepared) -> list:
    with _lock:
        rows = _base_rows.get(prepared.fixture.id)
        if rows is None:
            rows = _rows(prepared.fixture.household, prepared.strategy, None)
            _base_rows[prepared.fixture.id] = rows
        return rows


def _differs(key: str, before: float, after: float) -> bool:
    return abs(after - before) >= (CHANGE_SHARE if key == "stock_share" else CHANGE_DOLLARS)


def compare_rows(before: list, after: list) -> tuple[list[ScenarioYear], list[ScenarioChange]]:
    """The two plans' years side by side, with the years that differ marked, and every difference as a change."""
    years: list[ScenarioYear] = []
    changes: list[ScenarioChange] = []
    for b, a in zip(before, after, strict=True):
        changed: list[str] = []
        for key, label, _ in FIELDS:
            attr = ROW_FIELD.get(key, key)
            was, now = float(getattr(b, attr)), float(getattr(a, attr))
            if _differs(key, was, now):
                changed.append(key)
                changes.append(ScenarioChange(age=a.age, key=key, label=label, before=was, after=now, text=_sentence(a.age, key, was, now)))
        years.append(
            ScenarioYear(
                year_index=a.year_index, age=a.age,
                wages=a.wages, base_wages=b.wages,
                roth_conversion=a.roth_conversion, base_roth_conversion=b.roth_conversion,
                losses_harvested=a.losses_harvested, base_losses_harvested=b.losses_harvested,
                gains_harvested_tax_free=a.gains_realized_tax_free, base_gains_harvested_tax_free=b.gains_realized_tax_free,
                stock_share=a.stock_share, base_stock_share=b.stock_share,
                total_tax=a.total_tax, base_total_tax=b.total_tax,
                wealth=a.wealth, base_wealth=b.wealth,
                changed=changed,
            )
        )
    return years, changes


def summarize(changes: list[ScenarioChange]) -> list[str]:
    """The biggest difference of each kind that is not the event itself (wages), as the sentence the change carries."""
    out: list[tuple[float, str]] = []
    for key, _, money in FIELDS:
        if key == "wages":
            continue
        mine = [c for c in changes if c.key == key]
        if not mine:
            continue
        scale = 1.0 if money else 10_000.0  # a stock share moves by fractions: weigh a point as $100
        top = max(mine, key=lambda c: abs(c.after - c.before))
        out.append((abs(top.after - top.before) * scale, top.text))
    out.sort(key=lambda item: -item[0])
    return [text for _, text in out[:MAX_SUMMARY]]


def prepare(key: str) -> showcase.Prepared:
    """Search the plan again for the household after the event, and draw the futures it is measured on."""
    scenario = SCENARIOS[key]
    base = showcase.prepare()
    household = base.fixture.household
    fixture = base.fixture.model_copy(update={"id": f"{base.fixture.id}:{key}"})
    with _lock:
        cached = showcase._prepared.get(fixture.id)
        if cached is not None:
            return cached
        kwargs = {"shock": scenario.shock, "job_loss": scenario.job_loss}
        futures = build_inputs(household, n_paths=showcase.SEARCH_PATHS, seed=showcase.SEED, **kwargs)
        validation = build_inputs(household, n_paths=planner.VALIDATION_PATHS, seed=showcase.SEED + planner.VALIDATION_SEED_OFFSET, **kwargs)
        strategy = search_matched(futures, validation, menu(style=showcase.SHOWCASE_STYLE))[1].strategy
        inputs = build_inputs(household, n_paths=showcase.EVAL_PATHS, seed=showcase.SEED + planner.EVAL_SEED_OFFSET, **kwargs)
        prepared = showcase.Prepared(fixture, strategy, inputs)
        showcase._prepared[fixture.id] = prepared
        return prepared


def scenario(key: str) -> ShowcaseScenario:
    """The scenario's answer, worked out once and kept. Raises KeyError for a key that is not a scenario."""
    spec = SCENARIOS[key]
    with _lock:
        cached = _scenarios.get(key)
        if cached is not None:
            return cached
        base = showcase.prepare()
        prepared = prepare(key)
        household = base.fixture.household
        _, wealth = showcase.whole_plan(prepared)
        years_n = prepared.inputs.n_years

        # the plan chosen before the event against the one chosen knowing about it, on the same shocked futures
        batch = run_batch(prepared.inputs, [base.strategy.policy(), prepared.strategy.policy()])
        original, replanned = float(np.median(batch.wealth[0])), float(np.median(batch.wealth[1]))
        rate = (replanned / original) ** (1.0 / years_n) - 1.0 if original > 0 and replanned > 0 else 0.0

        years, changes = compare_rows(_base(base), _rows(household, prepared.strategy, spec))
        result = ShowcaseScenario(
            key=key, label=spec.label, event=spec.event,
            plan_label=prepared.strategy.short_label(), plan_sentence=prepared.strategy.describe(),
            original_plan_label=base.strategy.short_label(), plan_changed=prepared.strategy != base.strategy,
            wealth=wealth,
            replan=ScenarioReplan(
                original_plan_median_at_horizon=original, replanned_median_at_horizon=replanned,
                median_rate=rate, median_dollars=replanned - original,
            ),
            years=years, changes=changes, summary=summarize(changes),
        )
        _scenarios[key] = result
        return result


def precompute() -> None:
    """Work out every scenario now, so that none waits on a simulation when the demo is on camera."""
    for key in SCENARIOS:
        scenario(key)


def reset() -> None:
    with _lock:
        _scenarios.clear()
        _base_rows.clear()
        for key in [k for k in showcase._prepared if ":" in k]:
            showcase._prepared.pop(key, None)
