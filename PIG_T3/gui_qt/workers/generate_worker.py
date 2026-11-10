"""GenerateWorker — фоновое сканирование проекта (T-107).

Соответствует контракту из test_threading_contract.py:
- QObject, перемещается в QThread через moveToThread
- Слот ``run()`` — вся работа внутри
- Сигналы: progress(current, total), finished(path, count, lines, chars),
  error(str), cancelled()
- НЕ обращается к UI напрямую — только emit
- Отмена через ``thread.requestInterruption()``; воркер проверяет
  ``QThread.currentThread().isInterruptionRequested()`` через
  cancel_callback, который передаётся в analyzer.process
"""

from __future__ import annotations

from PySide6.QtCore import QObject, QThread, Signal, Slot

from ...core.analyzer import ProjectAnalyzer


class GenerateWorker(QObject):
    progress = Signal(int, int)
    finished = Signal(str, int, int, int)  # path, count, lines, chars
    error = Signal(str)
    cancelled = Signal()

    def __init__(
        self,
        settings: dict,
        analyzer: ProjectAnalyzer | None = None,
        parent: QObject | None = None,
    ):
        super().__init__(parent)
        self.settings = dict(settings)
        self.analyzer = analyzer if analyzer is not None else ProjectAnalyzer()

    def _cancel_requested(self) -> bool:
        thread = QThread.currentThread()
        return thread is not None and thread.isInterruptionRequested()

    @Slot()
    def run(self) -> None:
        try:
            result = self.analyzer.process(
                self.settings,
                progress_callback=self._on_progress,
                cancel_callback=self._cancel_requested,
            )
        except Exception as e:
            self.error.emit(str(e))
            return

        if result is None:
            self.cancelled.emit()
            return

        path, count, lines, chars = result
        self.finished.emit(path, count, lines, chars)

    def _on_progress(self, current: int, total: int) -> None:
        self.progress.emit(current, total)
