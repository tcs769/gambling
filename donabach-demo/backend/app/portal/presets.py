"""The changes the demo precomputes (each is a household edit or an event, run through the real planner), and the precompute itself."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

from app import showcase
from app.portal import engine_view as E
from app.schemas import Household


@dataclass(frozen=True)
class Preset:
    key: str
    label: str  # words for the value that was changed
    event: str
    edit: Callable[[Household], Household]


def _goals(**changes) -> Callable[[Household], Household]:
    def edit(h: Household) -> Household:
        data = h.model_dump()
        data["goals"].update(changes)
        return Household.model_validate(data)

    return edit


def _wages(factor: float) -> Callable[[Household], Household]:
    def edit(h: Household) -> Household:
        data = h.model_dump()
        for person in data["people"]:
            person["wages"] = round(person["wages"] * factor, 2)
        return Household.model_validate(data)

    return edit


PRESETS: tuple[Preset, ...] = (
    Preset("job_loss", "Income: job loss next year", "job_loss", lambda h: h),
    Preset("raise", "Income: a raise", "raise", lambda h: h),
    Preset("retire_65", "Retirement age: 65", "none", _goals(retirement_age=65)),
    Preset("home_1y", "Home purchase: $150,000 next year", "none", _goals(home_purchase_in_years=1, home_down_payment=150_000.0)),
    Preset("spending_120k", "Retirement spending: $120,000", "none", _goals(retirement_spending=120_000.0)),
    Preset("wages_minus_20", "Income: wages 20% lower", "none", _wages(0.8)),
)


def base_household() -> Household:
    return E.normalize(showcase.load_fixture().household)


def precompute() -> dict[str, str]:
    """The base plan, then every preset against it. Returns the plan ids by key (and prints nothing)."""
    ids: dict[str, str] = {}
    base = E.get_plan(base_household())
    ids["base"] = base.plan_id
    for preset in PRESETS:
        started = time.perf_counter()
        plan = E.get_plan(preset.edit(base_household()), preset.event, base.plan_id, preset.label)
        ids[preset.key] = plan.plan_id
        E._computed_seconds.setdefault(plan.plan_id, time.perf_counter() - started)
    return ids
