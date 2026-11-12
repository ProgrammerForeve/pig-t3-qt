"""ProjectTreeView — QTreeView с кликом по строке как toggle (T-105).

Поведение:
- клик по ветке-индикатору (треугольник раскрытия) — стандартное
  поведение Qt (expand/collapse)
- клик в любом другом месте строки — переключение чекбокса
- клик вне строк — стандартное поведение
"""

from __future__ import annotations

from PySide6.QtCore import QModelIndex, QPoint, Qt
from PySide6.QtWidgets import (
    QHeaderView,
    QStyledItemDelegate,
    QTreeView,
)

_DEFAULT_ROW_HEIGHT = 22


class _RowHeightDelegate(QStyledItemDelegate):
    """Делегат с фиксированной высотой строки."""

    _DEFAULT_HEIGHT = 20

    def __init__(self, row_height: int, parent=None):
        super().__init__(parent)
        self._row_height = max(12, int(row_height))

    def set_row_height(self, h: int) -> None:
        self._row_height = max(12, int(h))

    def sizeHint(self, option, index):
        from PySide6.QtCore import QSize

        # При teardown C++ delegate может быть уже удалён, но Qt ещё
        # вызывает sizeHint. Явный QStyledItemDelegate.sizeHint(self, ...)
        # вместо super() — если self мёртв, RuntimeError ловится здесь,
        # а не на этапе super()-lookup.
        try:
            size = QStyledItemDelegate.sizeHint(self, option, index)
        except (RuntimeError, AttributeError):
            return QSize(0, self._DEFAULT_HEIGHT)
        try:
            size.setHeight(self._row_height)
        except (RuntimeError, AttributeError):
            return QSize(0, self._DEFAULT_HEIGHT)
        return size


class ProjectTreeView(QTreeView):
    def __init__(self, parent=None):
        super().__init__(parent)
        # Issue 4 (P2): вторая колонка — размеры. Заголовки видны.
        self.setHeaderHidden(False)
        self.setUniformRowHeights(True)
        self.setSelectionMode(QTreeView.SelectionMode.SingleSelection)
        self.setEditTriggers(QTreeView.EditTrigger.NoEditTriggers)

        # Ширина колонок — в _apply_column_widths(), вызов после setModel.

        self._row_height = _DEFAULT_ROW_HEIGHT
        self._row_delegate = _RowHeightDelegate(self._row_height, self)
        self.setItemDelegate(self._row_delegate)

    def setup_size_column(self) -> None:
        """Настроить колонку размеров: stretch для 0, fixed 90px для 1.

        Вызывать ПОСЛЕ setModel() — до присоединения модели Qt
        игнорирует setColumnWidth. Не override'им setModel (SIGSEGV
        при teardown на test_capture_tree_state_returns_dict).
        """
        try:
            from shiboken6 import isValid

            if not isValid(self):
                return
            header = self.header()
            if header is not None and isValid(header):
                header.setStretchLastSection(False)
                header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
                header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
            self.setColumnWidth(1, 90)
        except Exception:
            return

    def apply_row_height(self, height: int) -> None:
        """Установить высоту строки (px). Игнорирует невалидные значения.

        Использует viewport().update() вместо reset() — reset()
        создаёт persistent indices, которые при teardown view
        пытаются разрезолвиться через уже-удалённый delegate.
        """
        if height is None or int(height) <= 0:
            return
        self._row_height = int(height)
        self._row_delegate.set_row_height(self._row_height)
        self.viewport().update()

    def row_height(self) -> int:
        return self._row_height

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
        if index.column() != 0:
            # Issue 4 (P2): в колонке размеров чекбокса нет.
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
            if index.isValid():
                # Issue 4 (P2): клик в колонке размеров — обычное выделение,
                # не toggle (иначе клик по '12.3 KB' снимал бы чекбокс).
                if index.column() != 0:
                    super().mousePressEvent(event)
                    return
                if not self._is_on_branch_indicator(pos, index) and self.toggle_check_for_index(index):
                    event.accept()
                    return
        super().mousePressEvent(event)
