"""Глобальные фикстуры pytest."""

from __future__ import annotations

import pytest


@pytest.fixture(scope="session")
def qapp_session():
    """QApplication на всю сессию (нужен для QWidget/QObject)."""
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def managed_thread(qapp_session):
    """Фабрика QThread с гарантированной остановкой после теста.

    Использование:
        def test_foo(managed_thread):
            thread = managed_thread()
            worker.moveToThread(thread)
            ...
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
            if not t.wait(2000):
                t.terminate()
                t.wait(1000)
        assert not t.isRunning(), f"QThread не завершился после teardown: {t}"
