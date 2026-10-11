"""The kernel lock: one parallel launch at a time, foreground work ahead of background work."""

from __future__ import annotations

import threading
import time

from app.sim.simulate import _KernelLock


def test_it_is_a_mutex_for_foreground_and_background_work_alike():
    lock = _KernelLock()
    inside = []
    overlaps = []

    def work(background: bool):
        for _ in range(20):
            with lock.background() if background else lock:
                inside.append(1)
                if len(inside) > 1:
                    overlaps.append(1)
                time.sleep(0.001)
                inside.pop()

    threads = [threading.Thread(target=work, args=(i % 2 == 0,)) for i in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not overlaps


def test_a_waiting_foreground_caller_goes_before_a_background_caller_that_arrived_first():
    lock = _KernelLock()
    order: list[str] = []
    release = threading.Event()

    def holder():
        with lock:
            release.wait(2.0)

    def background():
        with lock.background():
            order.append("background")

    def foreground():
        with lock:
            order.append("foreground")

    h = threading.Thread(target=holder)
    h.start()
    time.sleep(0.05)
    b = threading.Thread(target=background)
    b.start()
    time.sleep(0.05)  # the background caller is already waiting...
    f = threading.Thread(target=foreground)
    f.start()
    time.sleep(0.05)  # ...when the foreground one arrives
    release.set()
    for t in (h, b, f):
        t.join(5.0)
    assert order == ["foreground", "background"]


def test_background_work_waits_a_short_grace_after_foreground_work_so_a_request_is_not_interleaved():
    lock = _KernelLock()
    with lock:
        pass
    started = time.monotonic()
    with lock.background():
        waited = time.monotonic() - started
    assert waited >= _KernelLock.GRACE_SECONDS * 0.8
    # with no foreground work for a while it is granted at once
    time.sleep(_KernelLock.GRACE_SECONDS * 1.5)
    started = time.monotonic()
    with lock.background():
        assert time.monotonic() - started < _KernelLock.GRACE_SECONDS * 0.5


def test_a_background_holder_is_not_interrupted_but_is_released_for_the_next_caller():
    lock = _KernelLock()
    log: list[str] = []

    def background():
        with lock.background():
            log.append("bg start")
            time.sleep(0.1)
            log.append("bg end")

    t = threading.Thread(target=background)
    t.start()
    time.sleep(0.03)
    with lock:  # the foreground caller waits for the chunk in flight, then proceeds
        log.append("fg")
    t.join()
    assert log == ["bg start", "bg end", "fg"]
