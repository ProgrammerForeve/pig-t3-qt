"""FileWatcher — рекурсивный watcher проекта с debounce (B3).

Обёртка над watchdog.Observer. События из watchdog-треда
маршалятся в main-thread через Qt-сигнал (AutoConnection →
QueuedConnection), debounce 1.5с, эмитит changes_detected().

Зачем не QFileSystemWatcher: он нерекурсивный на Linux — пришлось
бы вручную добавлять/удалять каждую подпапку при изменении
структуры. watchdog делает это из коробки.

Если watchdog не установлен — start() возвращает False,
GeneratorTab просто работает без автообновления.
"""

from __future__ import annotations

import contextlib
import os

from PySide6.QtCore import QObject, QTimer, Signal

_IGNORED_PARTS = {
    ".pig",
    ".git",
    "__pycache__",
    "venv",
    ".venv",
    "node_modules",
    "build",
    "dist",
    ".idea",
    ".vscode",
    ".mypy_cache",
    ".ruff_cache",
    ".pytest_cache",
}


class _WatchdogHandler:
    """Мост watchdog → callback (эмитит Qt-сигнал)."""

    def __init__(self, on_event):
        self._on_event = on_event

    def dispatch(self, event) -> None:
        path = getattr(event, "src_path", "") or getattr(event, "dest_path", "")
        if path:
            parts = set(path.replace("\\", "/").split("/"))
            if parts & _IGNORED_PARTS:
                return
        self._on_event()


class FileWatcher(QObject):
    changes_detected = Signal()
    _fs_event = Signal()

    def __init__(self, debounce_ms: int = 1500, parent=None):
        super().__init__(parent)
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(debounce_ms)
        self._debounce.timeout.connect(self.changes_detected)
        self._fs_event.connect(self._schedule_debounce)

        self._observer = None
        self._handler = None
        self._path: str | None = None
        self._enabled: bool = True

    def start(self, path: str) -> bool:
        self.stop()
        self._enabled = True
        if not path or not os.path.isdir(path):
            return False
        try:
            from watchdog.observers import Observer
        except ImportError:
            return False
        try:
            self._path = path
            self._handler = _WatchdogHandler(self._on_fs_event)
            self._observer = Observer()
            self._observer.schedule(self._handler, path, recursive=True)
            self._observer.start()
            return True
        except Exception:
            self.stop()
            return False

    def stop(self) -> None:
        self._enabled = False
        if self._observer is not None:
            with contextlib.suppress(Exception):
                self._observer.stop()
                self._observer.join(timeout=2)
            self._observer = None
        self._handler = None
        self._path = None
        self._debounce.stop()

    def is_running(self) -> bool:
        return self._observer is not None

    def current_path(self) -> str | None:
        return self._path

    def _schedule_debounce(self) -> None:
        # Вызывается в main-thread (queued от _fs_event).
        # Guard: _fs_event мог быть queued до уничтожения FileWatcher.
        from shiboken6 import isValid

        if not isValid(self):
            return
        if getattr(self, "_debounce", None) is None:
            return
        if not isValid(self._debounce):
            return
        self._debounce.start()

    def _on_fs_event(self) -> None:
        # Вызывается из watchdog-треда. QTimer.start() тут небезопасен;
        # эмитим сигнал — Qt доставит его через queued connection.
        # CRITICAL: если watchdog уже остановлен (pause_file_watcher),
        # НЕ emit'им. Иначе fork() в subprocess.run копирует Qt-lock
        # в child в inconsistent state → parent abort (см. свежий
        # /tmp/pig_crash.log: apply_worker + _on_fs_event).
        if not getattr(self, "_enabled", True):
            return
        from shiboken6 import isValid

        if not isValid(self):
            return
        if not isValid(self._fs_event):
            return
        self._fs_event.emit()
