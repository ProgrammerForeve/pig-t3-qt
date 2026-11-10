"""TDD: OptimizeWorker (T-110) — контракт из test_threading_contract."""

from __future__ import annotations

import time

import pytest

from PIG_T3.gui_qt.workers.optimize_worker import OptimizeWorker
from tests.helpers.threading import run_worker_and_wait

pytestmark = pytest.mark.threading


class _FakeOptimizer:
    def __init__(self, result, delay=0.0, fail=None):
        self.result = result
        self.delay = delay
        self.fail = fail
        self.calls = 0
        self.cancelled_at = None

    def optimize(self, progress_callback=None, fallback_callback=None):
        self.calls += 1
        for i in range(5):
            if self.delay:
                time.sleep(self.delay / 5)
            if progress_callback:
                progress_callback((i + 1) * 20, f"step {i + 1}")
        if self.fail:
            raise self.fail
        return list(self.result)


def _worker(optimizer):
    return OptimizeWorker(root_folder="/fake", task="t", limit_tokens=1000, optimizer=optimizer)


def test_successful_run_emits_done(qtbot, managed_thread):
    w = _worker(_FakeOptimizer(["/p/a.py", "/p/b.py"]))
    t = managed_thread()
    w.moveToThread(t)
    args = run_worker_and_wait(qtbot, w, t, done_signal=w.done)
    assert args == [["/p/a.py", "/p/b.py"]]


def test_progress_signals_delivered(qtbot, managed_thread):
    w = _worker(_FakeOptimizer(["/p/a.py"], delay=0.05))
    t = managed_thread()
    w.moveToThread(t)
    progress: list = []
    w.progress.connect(lambda p, m: progress.append((p, m)))
    run_worker_and_wait(qtbot, w, t, done_signal=w.done)
    assert progress
    for p, m in progress:
        assert 0 <= p <= 100
        assert isinstance(m, str)


def test_error_signal_on_exception(qtbot, managed_thread):
    w = _worker(_FakeOptimizer([], fail=RuntimeError("boom")))
    t = managed_thread()
    w.moveToThread(t)
    t.started.connect(w.run)
    errors: list[str] = []
    w.error.connect(errors.append)
    with qtbot.waitSignal(w.error, timeout=2000):
        t.start()
    assert errors and "boom" in errors[0]


def test_cancel_interrupts(qtbot, managed_thread):
    fake = _FakeOptimizer(["/p/a.py"], delay=0.5)
    w = _worker(fake)
    t = managed_thread()
    w.moveToThread(t)
    t.started.connect(w.run)
    cancelled: list[bool] = []
    w.cancelled.connect(lambda: cancelled.append(True))
    with qtbot.waitSignal(w.cancelled, timeout=3000):
        t.start()
        time.sleep(0.1)
        t.requestInterruption()
    assert cancelled
    assert fake.calls == 1


def test_run_in_separate_thread(qtbot, managed_thread):
    import threading

    class _Spy:
        thread_id = None

        def optimize(self, progress_callback=None, fallback_callback=None):
            _Spy.thread_id = threading.get_ident()
            return []

    w = _worker(_Spy())
    t = managed_thread()
    w.moveToThread(t)
    run_worker_and_wait(qtbot, w, t, done_signal=w.done)
    assert _Spy.thread_id is not None
    assert _Spy.thread_id != threading.get_ident()
