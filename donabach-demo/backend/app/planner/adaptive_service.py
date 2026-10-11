"""Running the adaptive plan in the background and remembering it.

The fixed planner answers in about a second; the adaptive one takes several. `request` returns at once:
either the finished plan (it was precomputed, as for the demo household, or asked for before) or a job id
the client polls with `job`. One worker thread runs jobs in order; each runs in chunks of evaluation paths
and releases the kernel lock between them, so a fresh fixed-strategy plan is never stuck behind a long
adaptive run.
"""

from __future__ import annotations

import hashlib
import threading
import uuid
from collections import OrderedDict
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from app.api_models import AdaptiveJob, AdaptiveSection
from app.planner.adaptive_plan import compute_adaptive
from app.planner.strategies import Strategy
from app.schemas import Household, MarketShock
from app.sim.adaptive import AdaptiveSettings

CACHE_SIZE = 24
JOBS_KEPT = 64


def cache_key(
    household: Household,
    strategy: Strategy,
    seed: int,
    n_eval_paths: int,
    shock: MarketShock | None,
    settings: AdaptiveSettings,
) -> str:
    """Everything the adaptive result depends on."""
    parts = [
        household.model_dump_json(),
        strategy.key,
        str(seed),
        str(n_eval_paths),
        shock.model_dump_json() if shock else "none",
        repr(settings),
    ]
    return hashlib.sha256("|".join(parts).encode()).hexdigest()


@dataclass
class _Job:
    id: str
    key: str
    status: str = "running"
    progress: float = 0.0
    error: str | None = None
    result: AdaptiveSection | None = None
    lock: threading.Lock = field(default_factory=threading.Lock)


class AdaptiveService:
    def __init__(self) -> None:
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="adaptive")
        self._cache: OrderedDict[str, AdaptiveSection] = OrderedDict()
        self._jobs: OrderedDict[str, _Job] = OrderedDict()
        self._by_key: dict[str, str] = {}
        self._lock = threading.Lock()

    def clear(self) -> None:
        """Forget every cached plan and finished job (jobs still running keep running; tests and scripts use this)."""
        with self._lock:
            self._cache.clear()
            for job_id in [j for j, job in self._jobs.items() if job.status != "running"]:
                self._by_key.pop(self._jobs.pop(job_id).key, None)

    # -- cache ------------------------------------------------------------------------------

    def cached(self, key: str) -> AdaptiveSection | None:
        with self._lock:
            section = self._cache.get(key)
            if section is not None:
                self._cache.move_to_end(key)
                return section.model_copy(update={"from_cache": True})
        return None

    def store(self, key: str, section: AdaptiveSection) -> None:
        with self._lock:
            self._cache[key] = section
            self._cache.move_to_end(key)
            while len(self._cache) > CACHE_SIZE:
                self._cache.popitem(last=False)

    # -- jobs -------------------------------------------------------------------------------

    def request(
        self, key: str, work: Callable[[Callable[[float], None]], AdaptiveSection]
    ) -> tuple[AdaptiveSection | None, str | None]:
        """The finished plan if it is known, else the id of a job that is computing it."""
        hit = self.cached(key)
        if hit is not None:
            return hit, None
        with self._lock:
            existing = self._by_key.get(key)
            if existing is not None and existing in self._jobs and self._jobs[existing].status != "error":
                job = self._jobs[existing]
                if job.status == "done" and job.result is not None:  # finished, but no longer in the cache
                    self._cache[key] = job.result
                    self._cache.move_to_end(key)
                    return job.result.model_copy(update={"from_cache": True}), None
                return None, existing
            job = _Job(id=uuid.uuid4().hex[:12], key=key)
            self._jobs[job.id] = job
            self._by_key[key] = job.id
            while len(self._jobs) > JOBS_KEPT:
                old_id, old = self._jobs.popitem(last=False)
                self._by_key.pop(old.key, None)
        self._executor.submit(self._run, job, work)
        return None, job.id

    def _run(self, job: _Job, work: Callable[[Callable[[float], None]], AdaptiveSection]) -> None:
        def progress(value: float) -> None:
            job.progress = max(job.progress, min(1.0, value))

        try:
            section = work(progress)
        except Exception as exc:  # a failure is reported to the poller, never swallowed
            job.error = f"{type(exc).__name__}: {exc}"
            job.status = "error"
            return
        self.store(job.key, section)
        job.result = section
        job.progress = 1.0
        job.status = "done"

    def job(self, job_id: str) -> AdaptiveJob | None:
        with self._lock:
            job = self._jobs.get(job_id)
        if job is None:
            return None
        return AdaptiveJob(id=job.id, status=job.status, progress=job.progress, error=job.error, result=job.result)

    def wait(self, job_id: str, timeout: float = 120.0) -> AdaptiveJob:
        """Block until a job finishes (for tests and scripts)."""
        import time

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            current = self.job(job_id)
            if current is None or current.status != "running":
                assert current is not None
                return current
            time.sleep(0.05)
        raise TimeoutError(f"adaptive job {job_id} did not finish in {timeout}s")


service = AdaptiveService()


def request_plan(
    household: Household,
    strategy: Strategy,
    seed: int,
    n_eval_paths: int,
    shock: MarketShock | None,
    risk_aversion: float,
    k: int,
    z_min: float = 1.0,
) -> tuple[AdaptiveSection | None, str | None]:
    settings = AdaptiveSettings(k=k, z_min=z_min, risk_aversion=risk_aversion)
    key = cache_key(household, strategy, seed, n_eval_paths, shock, settings)

    def work(progress: Callable[[float], None]) -> AdaptiveSection:
        return compute_adaptive(household, strategy, seed, n_eval_paths, shock, on_progress=progress, settings=settings)

    return service.request(key, work)
