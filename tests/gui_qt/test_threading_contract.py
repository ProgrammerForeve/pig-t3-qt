"""Контракт многопоточного воркера (шаблон для T-107+).

Все будущие воркеры (GenerateWorker, OptimizeWorker, ApplyWorker,
PlanStepWorker, ScanWorker) обязаны проходить эти тесты.
"""

from __future__ import annotations

import time

import pytest
from PySide6.QtCore import QObject, Signal, Slot

from tests.helpers.threading import (
    assert_main_thread_not_blocked,
    collect_signals,
    run_worker_and_wait,
)

pytestmark = pytest.mark.threading


# ---------- Эталонный воркер (шаблон для T-107) ----------


class _EchoWorker(QObject):
    """Минимальный воркер, удовлетворяющий контракту."""

    progress = Signal(int, int)
    finished = Signal(str)
    error = Signal(str)

    @Slot()
    def run(self) -> None:
        for i in range(10):
            self.progress.emit(i + 1, 10)
        self.finished.emit("ok")


class _SlowWorker(QObject):
    """Воркер, имитирующий долгую работу (200 мс)."""

    finished = Signal(str)

    @Slot()
    def run(self) -> None:
        time.sleep(0.2)
        self.finished.emit("done")


class _FailingWorker(QObject):
    error = Signal(str)
    finished = Signal(str)

    @Slot()
    def run(self) -> None:
        try:
            raise ValueError("boom")
        except ValueError as e:
            self.error.emit(str(e))
        finally:
            self.finished.emit("failed")


# ---------- Тесты контракта ----------


def test_worker_emits_progress_and_finished(qtbot, managed_thread):
    """Все сигналы доходят из фонового потока в main-thread."""
    thread = managed_thread()
    worker = _EchoWorker()
    worker.moveToThread(thread)

    progress: list[tuple[int, int]] = []
    collect_signals(worker.progress, progress)

    args = run_worker_and_wait(qtbot, worker, thread)

    assert args == ["ok"]
    assert progress == [(i, 10) for i in range(1, 11)]


def test_worker_thread_actually_separate(qtbot, managed_thread):
    """Слот run() выполняется НЕ в main-thread.

    Храним threading.get_ident() (int), а не QThread.currentThread()
    (wrapper): wrapper, сохранённый на module-level классе, живёт до
    shutdown pytest-сессии. При финальном GC shiboken уничтожает
    C++ QThread раньше, чем держащий его wrapper → heap corruption
    (free(): invalid size).

    QThread.currentThreadId() в PySide6 не экспортирован, поэтому
    используем стандартный Python API — threading.get_ident().
    """
    import threading

    class _ThreadAwareWorker(QObject):
        finished = Signal(str)
        run_thread_id = None

        @Slot()
        def run(self):
            _ThreadAwareWorker.run_thread_id = threading.get_ident()
            self.finished.emit("ok")

    thread = managed_thread()
    worker = _ThreadAwareWorker()
    worker.moveToThread(thread)

    run_worker_and_wait(qtbot, worker, thread)

    assert _ThreadAwareWorker.run_thread_id is not None, "run() не выполнился"
    assert _ThreadAwareWorker.run_thread_id != threading.get_ident(), (
        "run() выполнился в main-thread — потеряли многопоточность"
    )


def test_main_thread_not_blocked_while_worker_runs(qtbot, managed_thread):
    """UI-поток продолжает обрабатывать события, пока воркер занят."""
    thread = managed_thread()
    worker = _SlowWorker()
    worker.moveToThread(thread)

    assert_main_thread_not_blocked(qtbot, worker, thread, min_ticks=3)


def test_worker_error_signal_delivered(qtbot, managed_thread):
    """Сигнал error доходит до main-thread, затем finished."""
    thread = managed_thread()
    worker = _FailingWorker()
    worker.moveToThread(thread)

    errors: list[str] = []
    collect_signals(worker.error, errors)

    args = run_worker_and_wait(qtbot, worker, thread)

    assert args == ["failed"]
    assert errors == ["boom"]


def test_worker_does_not_leak_thread(managed_thread):
    """managed_thread обязан остановить поток после теста (проверка teardown)."""
    thread = managed_thread()
    assert not thread.isRunning()
    # Реальная проверка — в фикстуре на teardown; здесь smoke.
