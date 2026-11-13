"""ScanWorker — фоновое сканирование качества (T-504).

Контракт test_threading_contract: QObject, run(), сигналы
progress/done/error/cancelled.
"""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QObject, QThread, Signal, Slot

from ...core.quality import ProjectScanner


class ScanWorker(QObject):
    progress = Signal(int, str)  # (percent 0-100, message)
    done = Signal(list)  # list[FileMetrics]
    error = Signal(str)
    cancelled = Signal()

    def __init__(
        self,
        root_path: str,
        chunk_size: int = 50,
        scanner: ProjectScanner | None = None,
        dep_check: Callable[[Callable[[str], None]], bool] | None = None,
        parent: QObject | None = None,
        settings: dict | None = None,
    ):
        super().__init__(parent)
        s = settings or {}
        if scanner is not None:
            self._scanner = scanner
        else:
            self._scanner = ProjectScanner(
                root_path,
                chunk_size=chunk_size,
                pylint_disable=str(s.get("quality_pylint_disable", "")),
                pylint_max_line_length=int(s.get("quality_pylint_max_line_length", 120)),
                vulture_min_confidence=int(s.get("quality_vulture_min_confidence", 60)),
                bandit_severity=str(s.get("quality_bandit_severity", "medium")),
                tool_timeout=int(s.get("quality_tool_timeout", 120)),
            )
        self._dep_check = dep_check

    def _is_interrupted(self) -> bool:
        thread = QThread.currentThread()
        return thread is not None and thread.isInterruptionRequested()

    def _check_deps(self) -> bool:
        if self._dep_check is None:
            from ...utils.dep_installer import DependencyInstaller

            return DependencyInstaller.check_and_install(callback=lambda text: self.progress.emit(2, text))
        return self._dep_check(lambda text: self.progress.emit(2, text))

    @Slot()
    def run(self) -> None:
        try:
            if not self._check_deps():
                self.error.emit("Не удалось установить анализаторы")
                return
            if self._is_interrupted():
                self.cancelled.emit()
                return

            def _cb(percent: int, msg: str) -> None:
                if self._is_interrupted():
                    return
                self.progress.emit(percent, msg)

            metrics = self._scanner.scan(progress_callback=_cb)
        except Exception as e:
            self.error.emit(str(e))
            return
        if self._is_interrupted():
            self.cancelled.emit()
            return
        self.done.emit(list(metrics))
