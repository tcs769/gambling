"""The background job service behind the year-by-year plan: one job per plan, cached, never stuck, never silent."""

from __future__ import annotations

import threading
import time

import pytest

from app.api_models import AdaptiveSection
from app.planner import adaptive_service
from app.planner.adaptive_service import AdaptiveService


def section(tag: int = 0) -> AdaptiveSection:
    return AdaptiveSection.model_construct(k=tag, from_cache=False)


@pytest.fixture
def service():
    s = AdaptiveService()
    yield s
    s._executor.shutdown(wait=True)


def test_a_job_runs_in_the_background_reports_progress_and_is_then_cached(service):
    gate = threading.Event()

    def work(progress):
        progress(0.3)
        gate.wait(5.0)
        progress(0.9)
        return section(7)

    hit, job_id = service.request("key", work)
    assert hit is None and job_id
    time.sleep(0.1)
    running = service.job(job_id)
    assert running.status == "running" and running.progress == pytest.approx(0.3) and running.result is None
    gate.set()
    done = service.wait(job_id, timeout=5.0)
    assert done.status == "done" and done.progress == 1.0 and done.result.k == 7
    hit, job = service.request("key", work)
    assert job is None and hit.k == 7 and hit.from_cache is True


def test_asking_again_while_a_job_runs_joins_it_instead_of_starting_another(service):
    gate = threading.Event()
    calls = []

    def work(progress):
        calls.append(1)
        gate.wait(5.0)
        return section()

    _, first = service.request("same", work)
    _, second = service.request("same", work)
    _, other = service.request("different", work)
    assert first == second != other
    gate.set()
    service.wait(first, timeout=5.0)
    service.wait(other, timeout=5.0)
    assert len(calls) == 2  # one run per distinct plan


def test_progress_never_goes_backwards_or_past_one(service):
    seen = []

    def work(progress):
        for value in (0.5, 0.2, 1.7):
            progress(value)
            seen.append(service.job(job_id).progress)
        return section()

    gate = threading.Event()
    _, job_id = service.request("p", lambda progress: (gate.wait(5.0), work(progress))[1])
    gate.set()
    service.wait(job_id, timeout=5.0)
    assert seen == [0.5, 0.5, 1.0]


def test_a_failed_job_says_why_and_the_next_request_tries_again(service):
    def broken(progress):
        raise RuntimeError("kernel exploded")

    _, job_id = service.request("k", broken)
    failed = service.wait(job_id, timeout=5.0)
    assert failed.status == "error" and "RuntimeError: kernel exploded" in failed.error and failed.result is None
    hit, retry = service.request("k", lambda progress: section(3))
    assert hit is None and retry != job_id
    assert service.wait(retry, timeout=5.0).result.k == 3


def test_a_finished_job_is_served_again_even_after_the_cache_forgot_it(service):
    _, job_id = service.request("k", lambda progress: section(5))
    service.wait(job_id, timeout=5.0)
    service._cache.clear()  # evicted
    hit, job = service.request("k", lambda progress: section(99))
    assert job is None and hit.k == 5 and hit.from_cache is True  # the finished result, not a new run, and not a bare job id
    assert service.cached("k").k == 5  # and it is back in the cache


def test_the_cache_keeps_the_most_recently_used_plans(service, monkeypatch):
    monkeypatch.setattr(adaptive_service, "CACHE_SIZE", 2)
    for key, tag in (("a", 1), ("b", 2)):
        service.store(key, section(tag))
    assert service.cached("a").k == 1  # touching a makes b the oldest
    service.store("c", section(3))
    assert service.cached("b") is None and service.cached("a").k == 1 and service.cached("c").k == 3


def test_clear_forgets_finished_work_but_not_a_running_job(service):
    gate = threading.Event()
    _, finished = service.request("finished", lambda progress: section(2))
    service.wait(finished, timeout=5.0)
    _, running = service.request("running", lambda progress: (gate.wait(5.0), section())[1])  # one worker: after the first
    service.clear()
    assert service.cached("finished") is None and service.job(finished) is None
    assert service.job(running).status == "running"
    gate.set()
    assert service.wait(running, timeout=5.0).status == "done"


def test_an_unknown_job_is_none_and_waiting_for_it_returns_none_immediately(service):
    assert service.job("nope") is None


def test_the_cache_key_changes_with_anything_the_result_depends_on():
    from tests.conftest import make_demo_household

    from app.planner.strategies import Strategy
    from app.schemas import MarketShock
    from app.sim.adaptive import AdaptiveSettings

    household = make_demo_household()
    strategy = Strategy.from_choices({"stock_share": "50", "conversion": "none", "private_credit": "0", "direct_indexing": "off", "goal_bonds": "off", "k401": "pretax", "goal_funding": "sell"})
    base = adaptive_service.cache_key(household, strategy, 1, 200, None, AdaptiveSettings())
    assert base == adaptive_service.cache_key(household, strategy, 1, 200, None, AdaptiveSettings())
    variants = [
        adaptive_service.cache_key(make_demo_household(children_ages=[]), strategy, 1, 200, None, AdaptiveSettings()),
        adaptive_service.cache_key(household, strategy.__class__.from_choices({**strategy.choices(), "stock_share": "60"}), 1, 200, None, AdaptiveSettings()),
        adaptive_service.cache_key(household, strategy, 2, 200, None, AdaptiveSettings()),
        adaptive_service.cache_key(household, strategy, 1, 300, None, AdaptiveSettings()),
        adaptive_service.cache_key(household, strategy, 1, 200, MarketShock(year=1, equity_return=-0.3), AdaptiveSettings()),
        adaptive_service.cache_key(household, strategy, 1, 200, None, AdaptiveSettings(k=64)),
        adaptive_service.cache_key(household, strategy, 1, 200, None, AdaptiveSettings(risk_aversion=5.0)),
        adaptive_service.cache_key(household, strategy, 1, 200, None, AdaptiveSettings(confirm_z=2.0)),
    ]
    assert len({base, *variants}) == 1 + len(variants)
