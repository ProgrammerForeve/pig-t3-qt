"""RecentProjectsMenu — QMenu с недавними проектами (B4).

Показывает до 10 путей из settings['recent_projects'].
Клик → сигнал project_selected(str), MainWindow/GeneratorTab подхватывает.
"""

from __future__ import annotations

import os

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QMenu, QWidget

_MAX_ITEMS = 10


class RecentProjectsMenu(QMenu):
    project_selected = Signal(str)
    recent_cleared = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__("📁 Недавние", parent)
        self._rebuild([])

    def update_projects(self, paths: list[str]) -> None:
        """Обновить список путей."""
        self._rebuild(paths)

    def _rebuild(self, paths: list[str]) -> None:
        self.clear()

        existing = [p for p in paths if isinstance(p, str) and p and os.path.isdir(p)][:_MAX_ITEMS]

        if not existing:
            empty = self.addAction("(пусто)")
            empty.setEnabled(False)
            return

        for path in existing:
            action = self.addAction(path)
            action.setToolTip(path)
            action.triggered.connect(lambda _checked=False, p=path: self.project_selected.emit(p))

        self.addSeparator()
        clear_action = self.addAction("🗑 Очистить список")
        clear_action.triggered.connect(self._on_clear)

    def _on_clear(self) -> None:
        self.recent_cleared.emit()
