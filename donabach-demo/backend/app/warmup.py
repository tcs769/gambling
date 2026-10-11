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
