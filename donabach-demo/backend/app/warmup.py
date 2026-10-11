"""Compile (or load from the on-disk cache) the simulation kernels before the first request."""

from __future__ import annotations

import time

from app.schemas import Accounts, Goals, Household, Person
from app.sim.markets import DEFAULT_SEED
from app.tax.picture import current_tax_return


def warm(n_paths: int = 50) -> float:
    """Run a tiny plan end to end; returns the seconds it took."""
    from app.planner.plan import build_plan

    started = time.perf_counter()
    household = Household(
        people=[Person(age=40, wages=150_000), Person(age=39, wages=90_000)],
        children_ages=[6],
        accounts=Accounts(brokerage_value=100_000, brokerage_basis=80_000, pretax_balance=300_000, roth_balance=20_000, cash=30_000),
        goals=Goals(),
    )
    build_plan(household, n_paths=n_paths, demo_mode=True, seed=DEFAULT_SEED)
    current_tax_return(household)  # the tax engine's Python-facing entry point compiles separately
    return time.perf_counter() - started


def precompute_demo() -> None:
    """Start the demo household's adaptive plan computing in the background (demo mode shows it at once).

    This is the household the app builds from the three sample documents with the default answers, planned
    with the app's default settings, so the first `/plan` request for it finds the finished adaptive plan (or
    the job already running). Set DONABACH_NO_PRECOMPUTE=1 to skip it.
    """
    import os

    if os.environ.get("DONABACH_NO_PRECOMPUTE"):
        return
    from app import builder
    from app.api_models import Answers
    from app.planner import adaptive_service, plan
    from app.planner.strategies import Strategy
    from app.store import store

    documents = [store.parsed(doc.id) for doc in store.add_samples()]
    household = builder.build_household(documents, {}, Answers())
    response = plan.build_plan(household, 400, True, None, None, 200, 3.0, plan.DEFAULT_STYLE)
    adaptive_service.request_plan(
        household, Strategy.from_choices(response.strategy.choices), response.settings.seed, 200, None, 3.0, 32
    )
