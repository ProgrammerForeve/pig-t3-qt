"""QualityTableModel — QAbstractTableModel для FileMetrics (T-501).

6 колонок: path / sloc / cc / mi / score / sec.
Цвет фона ячейки — по FileMetrics.get_status_for_column(col).
Сортировка — через QSortFilterProxyModel (T-502).
"""

from __future__ import annotations

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtGui import QBrush, QColor

from ...core.quality import FileMetrics

_COLUMNS = ["path", "sloc", "cc", "mi", "score", "sec"]
_HEADERS = {
    "path": "📄 Файл (Путь)",
    "sloc": "📝 Строк",
    "cc": "🌀 Сложность",
    "mi": "🛠️ Поддерж.",
    "score": "⭐ Score",
    "sec": "🛡️ Безоп.",
}
_STATUS_COLOR = {
    "green": "#98c379",
    "yellow": "#e5c07b",
    "red": "#e06c75",
}


class QualityTableModel(QAbstractTableModel):
    def __init__(self, metrics: list[FileMetrics] | None = None, parent=None):
        super().__init__(parent)
        self._metrics: list[FileMetrics] = list(metrics or [])

    # ---------- QAbstractTableModel ----------

    def rowCount(self, parent=QModelIndex()) -> int:  # type: ignore[override]
        return 0 if parent.isValid() else len(self._metrics)

    def columnCount(self, parent=QModelIndex()) -> int:  # type: ignore[override]
        return 0 if parent.isValid() else len(_COLUMNS)

    def headerData(  # type: ignore[override]
        self, section, orientation, role=Qt.ItemDataRole.DisplayRole
    ):
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal:
            return _HEADERS[_COLUMNS[section]]
        return section + 1

    def data(self, index: QModelIndex, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not (0 <= index.row() < len(self._metrics)):
            return None
        metric = self._metrics[index.row()]
        col = _COLUMNS[index.column()]

        if role == Qt.ItemDataRole.DisplayRole:
            return self._format_value(metric, col)

        if role == Qt.ItemDataRole.ForegroundRole:
            status = metric.get_status_for_column(col)
            color = _STATUS_COLOR.get(status, "#cccccc")
            return QBrush(QColor(color))

        if role == Qt.ItemDataRole.UserRole:
            return metric

        return None

    def sort(self, column: int, order=Qt.SortOrder.AscendingOrder) -> None:  # type: ignore[override]
        if not (0 <= column < len(_COLUMNS)):
            return
        self.layoutAboutToBeChanged.emit()
        col = _COLUMNS[column]
        reverse = order == Qt.SortOrder.DescendingOrder
        self._metrics.sort(key=lambda m: self._sort_key(m, col), reverse=reverse)
        self.layoutChanged.emit()

    # ---------- Helpers ----------

    def _sort_key(self, metric: FileMetrics, col: str):
        if col == "path":
            return metric.path
        if col == "sloc":
            return metric.sloc
        if col == "cc":
            return metric.complexity
        if col == "mi":
            return metric.maintainability
        if col == "score":
            return metric.pylint_score
        if col == "sec":
            return metric.security_issues
        return 0

    def _format_value(self, metric: FileMetrics, col: str) -> str:
        if col == "path":
            return metric.path
        if col == "sloc":
            return str(metric.sloc)
        if col == "cc":
            return f"{metric.complexity:.1f}"
        if col == "mi":
            return f"{metric.maintainability:.1f}"
        if col == "score":
            return f"{metric.pylint_score:.1f}"
        if col == "sec":
            return str(metric.security_issues)
        return ""

    # ---------- Public ----------

    def set_metrics(self, metrics: list[FileMetrics]) -> None:
        self.beginResetModel()
        self._metrics = list(metrics)
        self.endResetModel()

    def metrics_at(self, row: int) -> FileMetrics | None:
        if 0 <= row < len(self._metrics):
            return self._metrics[row]
        return None

    def all_metrics(self) -> list[FileMetrics]:
        return list(self._metrics)
