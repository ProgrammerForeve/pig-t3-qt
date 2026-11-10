"""TDD: ScanWorker (T-504)."""

from __future__ import annotations

import time

import pytest

from PIG_T3.core.quality import FileMetrics
from PIG_T3.gui_qt.workers.quality_worker import ScanWorker
from tests.helpers.threading import run_worker_and_wait

pytestmark = pytest.mark.threading


class _FakeScanner:
    def __init__(self, result, delay=0.0, fail=None):
        self.result = result
        self.delay = delay
        self.fail = fail

    def scan(self, progress_callback=None):
        if self.delay:
            for i in range(3):
                time.sleep(self.delay / 3)
                if progress_callback:
                    progress_callback((i + 1) * 30, f"step {i + 1}")
        if self.fail:
            raise self.fail
        return list(self.result)


def _worker(scanner):
    return ScanWorker("/fake", scanner=scanner, dep_check=lambda cb: True)


def test_successful_scan_emits_done(qtbot, managed_thread):
    metrics = [FileMetrics(path="a.py")]
    w = _worker(_FakeScanner(metrics))
    t = managed_thread()
    w.moveToThread(t)
    args = run_worker_and_wait(qtbot, w, t, done_signal=w.done)
    assert len(args[0]) == 1
    assert args[0][0].path == "a.py"


def test_progress_signals_delivered(qtbot, managed_thread):
    w = _worker(_FakeScanner([], delay=0.05))
    t = managed_thread()
    w.moveToThread(t)
    progress = []
    w.progress.connect(lambda p, m: progress.append((p, m)))
    run_worker_and_wait(qtbot, w, t, done_signal=w.done)
    assert progress


def test_error_on_exception(qtbot, managed_thread):
    w = _worker(_FakeScanner([], fail=RuntimeError("boom")))
    t = managed_thread()
    w.moveToThread(t)
    t.started.connect(w.run)
    errors = []
    w.error.connect(errors.append)
    with qtbot.waitSignal(w.error, timeout=2000):
        t.start()
    assert errors and "boom" in errors[0]


def test_dep_check_fails_emits_error(qtbot, managed_thread):
    w = ScanWorker(
        "/fake",
        scanner=_FakeScanner([]),
        dep_check=lambda cb: False,
    )
    t = managed_thread()
    w.moveToThread(t)
    t.started.connect(w.run)
    errors = []
    w.error.connect(errors.append)
    with qtbot.waitSignal(w.error, timeout=2000):
        t.start()
    assert errors


def test_cancel_interrupts(qtbot, managed_thread):
    w = _worker(_FakeScanner([], delay=0.5))
    t = managed_thread()
    w.moveToThread(t)
    t.started.connect(w.run)
    cancelled = []
    w.cancelled.connect(lambda: cancelled.append(True))
    with qtbot.waitSignal(w.cancelled, timeout=3000):
        t.start()
        time.sleep(0.1)
        t.requestInterruption()
    assert cancelled
