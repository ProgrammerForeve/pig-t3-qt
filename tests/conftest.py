"""Глобальные фикстуры pytest."""

from __future__ import annotations

import os as _os

# Linux CI / headless: force offscreen QPA.
# Without this, QApplication([]) in pytest-qt's `qapp` fixture tries
# to init the xcb plugin (no DISPLAY), fails, falls back to offscreen
# with a half-loaded GL stack, and SIGABRTs mid-suite — before
# pytest_sessionfinish. Local dev with DISPLAY keeps xcb.
if not _os.environ.get("DISPLAY") and not _os.environ.get("QT_QPA_PLATFORM"):
    _os.environ["QT_QPA_PLATFORM"] = "offscreen"

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


@pytest.hookimpl(tryfirst=True)
def pytest_sessionfinish(session, exitstatus):
    import contextlib
    import os
    import sys

    with contextlib.suppress(Exception):
        sys.stdout.flush()
        sys.stderr.flush()

    # PIG_NO_EXIT=1 — диагностический режим: даём pytest нормально
    # завершиться, чтобы pytest-cov успел напечатать отчёт. В обычном
    # режиме os._exit() обходит Qt/shiboken shutdown (ADR-010).
    if os.environ.get("PIG_NO_EXIT"):
        return

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


@pytest.fixture(autouse=True)
def _no_async_workers(monkeypatch, request):
    """Отключает фоновые треды в UI-тестах.

    test_main_window_smoke.py создаёт MainWindow на каждый тест.
    Каждый MainWindow → EditorTab → 2 QThread воркера (Ollama +
    LM Studio) + FileWatcher → watchdog.Observer (real OS thread).
    9 тестов × 3+ треда = 27+ живых потоков перед test_misc_coverage.py.
    В offscreen CI teardown не успевает их остановить → SIGABRT
    (C++ QObject destroyed пока worker ещё emit'ит).

    Реальные файлы (test_file_watcher, test_ollama_models_worker,
    test_lmstudio_models_worker, test_optimize_dialog_async)
    исключены по nodeid — они тестируют поведение воркеров явно.

    В продакшене поведение не меняется — фикстура только в pytest.
    """
    nodeid = request.node.nodeid

    # FileWatcher: отключить реальный watchdog.Observer везде,
    # кроме тестов самого FileWatcher
    if "test_file_watcher" not in nodeid:
        from PIG_T3.gui_qt.widgets.file_watcher import FileWatcher

        monkeypatch.setattr(FileWatcher, "start", lambda self, path: False)

    # Async model workers в EditorTab/OptimizeDialog: отключить HTTP
    # только для UI-тестов, не тестирующих сами воркеры
    worker_test_files = (
        "test_ollama_models_worker",
        "test_lmstudio_models_worker",
        "test_optimize_dialog_async",
        "test_optimize_dialog_rag",
    )
    if not any(t in nodeid for t in worker_test_files):
        from PIG_T3.gui_qt.dialogs import optimize_dialog as od_module
        from PIG_T3.gui_qt.tabs import editor as editor_module

        def _safe_populate_models(self):
            base = [
                "None",
                "BomjAPI",
                "Web: Gemini",
                "Web: DeepSeek",
                "Web: DeepSeek (DeepThink)",
                "Web: DeepSeek Expert",
                "Web: DeepSeek Expert (DeepThink)",
            ]
            self.model_combo.addItems(base)

        monkeypatch.setattr(
            editor_module.EditorTab,
            "_populate_models",
            _safe_populate_models,
        )
        monkeypatch.setattr(
            od_module.OptimizeDialog,
            "_fetch_models_async",
            lambda self: None,
        )
        monkeypatch.setattr(
            od_module.OptimizeDialog,
            "_fetch_lmstudio_models_async",
            lambda self: None,
        )
