"""The API serves requests on a thread pool, so overlapping planning calls must not crash numba.

numba's `workqueue` threading layer (what you get when OpenMP and TBB are unavailable) aborts the
whole process on concurrent parallel launches. Every parallel kernel call goes through one lock; this
test forces the unsafe layer in a subprocess (so a regression cannot take pytest down with it) and
checks that overlapping plans all succeed with identical results.
"""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]

SCRIPT = textwrap.dedent(
    """
    from concurrent.futures import ThreadPoolExecutor
    from tests.conftest import make_demo_household
    from app.planner.plan import build_plan

    household = make_demo_household()
    build_plan(household, n_paths=50)

    def work(_):
        plan = build_plan(household, n_paths=150, demo_mode=True)
        return plan.stats.typical_outcome.median, plan.strategy.label

    with ThreadPoolExecutor(6) as pool:
        results = list(pool.map(work, range(18)))
    assert len(set(results)) == 1, results
    print("ok")
    """
)


@pytest.mark.parametrize("layer", ["workqueue", "default"])
def test_overlapping_plans_do_not_crash_the_kernel(layer):
    env = dict(os.environ, PYTHONPATH=str(BACKEND))
    if layer == "workqueue":
        env["NUMBA_THREADING_LAYER"] = "workqueue"
    result = subprocess.run(
        [sys.executable, "-c", SCRIPT], cwd=BACKEND, env=env, capture_output=True, text=True, timeout=240
    )
    assert result.returncode == 0, f"exit {result.returncode}\n{result.stderr[-2000:]}"
    assert result.stdout.strip().endswith("ok")
