"""Глобальные фикстуры pytest."""

from __future__ import annotations

import pytest


@pytest.fixture
def managed_thread(qapp):
    """Фабрика QThread с гарантированной остановкой после теста.

    Использует pytest-qt's qapp (единственный QApplication),
    без дублирования через session-scoped фикстуру.
    """
    from PySide6.QtCore import QThread

    threads = []

    def factory() -> QThread:
        t = QThread()
        threads.append(t)
        return t

    yield factory

    for t in threads:
        if t.isRunning():
            t.quit()
            if not t.wait(5000):
                raise AssertionError(f"QThread не завершился за 5с: {t}")
        assert not t.isRunning()
    # gc.collect() здесь НЕ вызываем: во время teardown pytest-qt
    # часть C++-объектов уже уничтожена, а shiboken-обёртки ещё живы.
    # Сборка мусора дёргает их деструкторы → heap corruption
    # (free(): invalid size) прямо в teardown последнего теста,
    # до pytest_sessionfinish с os._exit(). Финальный GC и так
    # обходится через os._exit() в pytest_sessionfinish.


def pytest_sessionfinish(session, exitstatus):
    """Форсированный чистый выход в обход Python shutdown.

    gc.freeze() недостаточно: даже в permanent generation Python
    делает Py_DECREF при очистке module-globals в момент shutdown.
    Один DECREF на shiboken-wrapper (QApplication из pytest-qt,
    QThread, QObject) вызывает C++-деструктор; порядок деструкторов
    не согласован с Qt → heap corruption (free(): invalid size).

    os._exit() завершает процесс сразу после тестов, минуя atexit,
    финальный GC и shiboken cleanup. ОС освобождает память целиком.
    Минусы: не срабатывают atexit-хуки, coverage-репортинг,
    pytest-xdist может ругаться — приемлемо для CI.
    """
    import contextlib
    import os
    import sys

    with contextlib.suppress(Exception):
        sys.stdout.flush()
        sys.stderr.flush()
    os._exit(int(exitstatus))


@pytest.fixture(autouse=True)
def _silence_dialogs(monkeypatch):
    """Не даём модальным диалогам блокировать прогон тестов.

    Патчим module-level обёртки в PIG_T3.gui_qt.tabs.generator, а НЕ
    QMessageBox.information / .critical напрямую: monkeypatch на
    статических методах shiboken-классов рассинхронизирует внутренние
    кэши PySide6 и приводит к heap corruption (free(): invalid size).
    """
    from PIG_T3.gui_qt.tabs import generator as gen_module

    monkeypatch.setattr(gen_module, "_show_info_dialog", lambda *a, **kw: None)
    monkeypatch.setattr(gen_module, "_show_critical_dialog", lambda *a, **kw: None)
