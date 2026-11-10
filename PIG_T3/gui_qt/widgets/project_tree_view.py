"""ProjectTreeView — QTreeView с кликом по строке как toggle (T-105).

Поведение:
- клик по ветке-индикатору (треугольник раскрытия) — стандартное
  поведение Qt (expand/collapse)
- клик в любом другом месте строки — переключение чекбокса
- клик вне строк — стандартное поведение
"""

from __future__ import annotations

from PySide6.QtCore import QModelIndex, QPoint, Qt
from PySide6.QtWidgets import QTreeView


class ProjectTreeView(QTreeView):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setHeaderHidden(True)
        self.setUniformRowHeights(True)
        self.setSelectionMode(QTreeView.SelectionMode.SingleSelection)
        self.setEditTriggers(QTreeView.EditTrigger.NoEditTriggers)

    def _is_on_branch_indicator(self, pos: QPoint, index: QModelIndex) -> bool:
        """True, если позиция попадает в треугольник раскрытия этого узла.

        Треугольник рисуется только для узлов с детьми (у листьев его нет).
        Позиция считается в координатах viewport.
        """
        model = self.model()
        if model is None or not model.hasChildren(index):
            return False
        depth = 0
        parent = index.parent()
        while parent.isValid():
            depth += 1
            parent = parent.parent()
        indent = self.indentation()
        left = depth * indent
        right = left + indent
        return left <= pos.x() < right

    def toggle_check_for_index(self, index: QModelIndex) -> bool:
        """Программно переключить чекбокс. Возвращает True, если удалось."""
        if not index.isValid():
            return False
        model = self.model()
        if model is None:
            return False
        current = model.data(index, Qt.ItemDataRole.CheckStateRole)
        if current is None:
            return False
        new_state = Qt.CheckState.Unchecked if current == Qt.CheckState.Checked else Qt.CheckState.Checked
        return model.setData(index, new_state.value, Qt.ItemDataRole.CheckStateRole)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            pos = event.position().toPoint()
            index = self.indexAt(pos)
            if index.isValid() and not self._is_on_branch_indicator(pos, index) and self.toggle_check_for_index(index):
                event.accept()
                return
        super().mousePressEvent(event)
