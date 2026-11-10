"""Глобальные фикстуры pytest."""

from __future__ import annotations

import gc

import pytest


@pytest.fixture(autouse=True)
def _gc_after_test():
    """Форсируем GC после каждого теста.

    TreeNode в ProjectTreeModel имеет циклические ссылки
    (parent <-> children). Без явного gc.collect() они могут не
    собраться до interpreter shutdown, а shiboken в этот момент
    освобождает QModelIndex → heap corruption.
    """
    yield
    gc.collect()


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
            # Без terminate(): Qt-документация прямо предупреждает,
            # что terminate() оставляет мьютексы и C++ объекты в
            # неопределённом состоянии → heap corruption при
            # interpreter shutdown.
            if not t.wait(5000):
                raise AssertionError(f"QThread не завершился за 5с: {t}")
        assert not t.isRunning()
    # Дать Qt протолкнуть deferred deletes перед teardown
    gc.collect()


def pytest_sessionfinish(session, exitstatus):
    """Не даём Python финальному GC трогать Qt-объекты при shutdown.

    При интерпретатор-shutdown gc.collect() обходит shiboken-wrapper'ы
    (QApplication из pytest-qt, QThread-обёртки, QObject'ы), shiboken
    дёргает C++-деструкторы, а те в произвольном порядке дёргают
    освобождённую память → glibc heap corruption (free(): invalid
    size).

    gc.freeze() переводит все живые объекты в «permanent generation»;
    shutdown-сборка их не трогает, ОС освободит память при завершении
    процесса.
    """
    import gc

    gc.freeze()


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
