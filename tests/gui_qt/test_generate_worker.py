"""TDD: GenerateWorker (T-107) — контракт из test_threading_contract."""

from __future__ import annotations

import time

import pytest

from PIG_T3.gui_qt.workers.generate_worker import GenerateWorker
from tests.helpers.threading import run_worker_and_wait

pytestmark = pytest.mark.threading


class _FakeAnalyzer:
    """Дублирует сигнатуру ProjectAnalyzer.process."""

    def __init__(self, result, delay=0.0, fail=None):
        self.result = result
        self.delay = delay
        self.fail = fail
        self.cancel_seen = False
        self.calls = 0

    def process(self, settings, progress_callback=None, cancel_callback=None):
        self.calls += 1
        if self.delay:
            for i in range(5):
                time.sleep(self.delay / 5)
                if cancel_callback and cancel_callback():
                    self.cancel_seen = True
                    return None
                if progress_callback:
                    progress_callback(i + 1, 5)
        if self.fail:
            raise self.fail
        if cancel_callback and cancel_callback():
            self.cancel_seen = True
            return None
        return self.result


def test_successful_run_emits_finished(qtbot, managed_thread):
    worker = GenerateWorker(
        {"output_name": "ctx"},
        analyzer=_FakeAnalyzer(("out.txt", 3, 120, 4567)),
    )
    thread = managed_thread()
    worker.moveToThread(thread)
    args = run_worker_and_wait(qtbot, worker, thread)
    assert args == ["out.txt", 3, 120, 4567]


def test_progress_signals_delivered(qtbot, managed_thread):
    worker = GenerateWorker(
        {"output_name": "ctx"},
        analyzer=_FakeAnalyzer(("out.txt", 3, 120, 4567), delay=0.05),
    )
    thread = managed_thread()
    worker.moveToThread(thread)
    progress: list[tuple[int, int]] = []
    worker.progress.connect(lambda c, t: progress.append((c, t)))

    run_worker_and_wait(qtbot, worker, thread)
    assert progress
    for c, t in progress:
        assert 0 < c <= t


def test_error_signal_on_exception(qtbot, managed_thread):
    worker = GenerateWorker(
        {"output_name": "ctx"},
        analyzer=_FakeAnalyzer(None, fail=RuntimeError("boom")),
    )
    thread = managed_thread()
    worker.moveToThread(thread)
    # ЯВНО подключаем run — иначе thread.start() просто крутит
    # пустой event loop и никаких сигналов не будет.
    thread.started.connect(worker.run)

    errors: list[str] = []
    worker.error.connect(errors.append)

    with qtbot.waitSignal(worker.error, timeout=2000):
        thread.start()

    assert len(errors) == 1
    assert "boom" in errors[0]


def test_cancel_interrupts(qtbot, managed_thread):
    fake = _FakeAnalyzer(("out.txt", 1, 1, 1), delay=0.5)
    worker = GenerateWorker({"output_name": "ctx"}, analyzer=fake)
    thread = managed_thread()
    worker.moveToThread(thread)
    thread.started.connect(worker.run)

    cancelled: list[bool] = []
    worker.cancelled.connect(lambda: cancelled.append(True))

    with qtbot.waitSignal(worker.cancelled, timeout=3000):
        thread.start()
        # Дать воркеру стартовать, затем отменить
        time.sleep(0.1)
        thread.requestInterruption()

    assert fake.cancel_seen


def test_run_in_separate_thread(qtbot, managed_thread):
    """Контракт: run() исполняется не в main-thread.

    См. комментарий в test_threading_contract.py: храним
    threading.get_ident() (int), а не QThread.currentThread()
    (wrapper). QThread.currentThreadId() в PySide6 отсутствует.
    """
    import threading

    class _SpyAnalyzer:
        run_thread_id = None

        def process(self, settings, progress_callback=None, cancel_callback=None):
            _SpyAnalyzer.run_thread_id = threading.get_ident()
            return ("out.txt", 0, 0, 0)

    worker = GenerateWorker({"output_name": "ctx"}, analyzer=_SpyAnalyzer())
    thread = managed_thread()
    worker.moveToThread(thread)
    run_worker_and_wait(qtbot, worker, thread)

    assert _SpyAnalyzer.run_thread_id is not None
    assert _SpyAnalyzer.run_thread_id != threading.get_ident()


def test_excluded_paths_passed_to_analyzer(qtbot, managed_thread):
    captured = {}

    class _Capture:
        def process(self, settings, progress_callback=None, cancel_callback=None):
            captured.update(settings)
            return ("out.txt", 0, 0, 0)

    worker = GenerateWorker(
        {"output_name": "ctx", "excluded_paths": ["/a", "/b"]},
        analyzer=_Capture(),
    )
    thread = managed_thread()
    worker.moveToThread(thread)
    run_worker_and_wait(qtbot, worker, thread)

    assert captured["excluded_paths"] == ["/a", "/b"]
