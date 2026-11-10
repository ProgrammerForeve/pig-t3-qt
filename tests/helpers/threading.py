"""Помощники для тестирования QThread + сигналы.

Контракт воркера (см. test_threading_contract.py):
- QObject, перемещён в QThread через moveToThread
- Слот ``run()`` (или аналог) — вся работа внутри
- Сигналы: ``progress(cur, total)``, ``finished(*args)``, ``error(str)``
- НЕ обращается к UI напрямую — только emit
"""

from __future__ import annotations

from typing import Any, Callable

from PySide6.QtCore import QObject, QThread, QTimer, Signal, Slot


def run_worker_and_wait(
    qtbot,
    worker: QObject,
    thread: QThread,
    run_slot: str = "run",
    done_signal: Signal | None = None,
    timeout: int = 10_000,
) -> list[Any]:
    """Запускает воркер в QThread и ждёт ``done_signal``.

    Возвращает аргументы сигнала завершения.
    Побочно проверяет, что поток остановился после теста (см. ``managed_thread``).
    """
    if done_signal is None:
        done_signal = getattr(worker, "finished", None)
        if done_signal is None:
            raise ValueError("worker не имеет сигнала 'finished'; передайте done_signal явно")

    thread.started.connect(getattr(worker, run_slot))

    with qtbot.waitSignal(done_signal, timeout=timeout) as blocker:
        thread.start()

    # Detach worker from the thread BEFORE managed_thread stops it.
    # Without this, worker keeps affinity to a dead QThread; when
    # Python GC later calls its C++ destructor from the main thread,
    # QObject::thread() returns a dangling pointer -> UB (SIGABRT on
    # some Qt builds, notably CI with offscreen).
    import contextlib

    with contextlib.suppress(RuntimeError):
        worker.moveToThread(QThread.currentThread())

    return list(blocker.args)


def collect_signals(
    signal: Signal,
    sink: list,
) -> Callable:
    """Возвращает колбэк, накапливающий аргументы ``signal`` в ``sink``."""

    def _collector(*args):
        sink.append(args if len(args) != 1 else args[0])

    signal.connect(_collector)
    return _collector


@Slot()
def _noop() -> None:
    pass


def assert_main_thread_not_blocked(
    qtbot,
    worker: QObject,
    thread: QThread,
    run_slot: str = "run",
    tick_ms: int = 10,
    min_ticks: int = 3,
    timeout: int = 10_000,
) -> None:
    """Проверяет, что main-thread продолжает обрабатывать события,
    пока воркер работает в фоне.

    Работает так: запускает QTimer в main-thread, который «тикает» каждые
    ``tick_ms``. Если UI блокирован — тиков будет 0 или мало. Ожидаем
    минимум ``min_ticks`` тиков за время работы воркера.
    """
    ticks: list[int] = []

    timer = QTimer()
    timer.setInterval(tick_ms)
    timer.timeout.connect(lambda: ticks.append(1))
    timer.start()

    try:
        run_worker_and_wait(qtbot, worker, thread, run_slot=run_slot, timeout=timeout)
    finally:
        timer.stop()

    assert len(ticks) >= min_ticks, (
        f"Main thread, похоже, был блокирован: получено {len(ticks)} тиков, ожидалось ≥{min_ticks}"
    )
