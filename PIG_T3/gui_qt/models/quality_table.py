"""QualityTableModel — QAbstractTableModel для FileMetrics (T-501).

7 колонок: check / path / sloc / cc / mi / score / sec.
- Колонка 0 «check» — исключение файла из «📋 В задачу»
- Эмодзи в DisplayRole: 🟢/🟡/🔴 по статусу
- UserRole + 1 — numeric sort key (QSortFilterProxyModel.sortRole)
- UserRole — FileMetrics объект (для details)
"""

from __future__ import annotations

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtGui import QBrush, QColor

from ...core.quality import FileMetrics

_COLUMNS = ["check", "path", "sloc", "cc", "mi", "score", "sec"]
_HEADERS = {
    "check": "✓",
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
_STATUS_EMOJI = {
    "green": "🟢",
    "yellow": "🟡",
    "red": "🔴",
}


class QualityTableModel(QAbstractTableModel):
    def __init__(self, metrics: list[FileMetrics] | None = None, parent=None):
        super().__init__(parent)
        self._metrics: list[FileMetrics] = list(metrics or [])
        self._checked: list[bool] = [True] * len(self._metrics)

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

        if role == Qt.ItemDataRole.CheckStateRole and col == "check":
            return Qt.CheckState.Checked if self._checked[index.row()] else Qt.CheckState.Unchecked

        if role == Qt.ItemDataRole.DisplayRole:
            if col == "check":
                return None
            return self._format_value(metric, col)

        if role == Qt.ItemDataRole.ForegroundRole:
            if col == "check":
                return None
            status = metric.get_status_for_column(col)
            color = _STATUS_COLOR.get(status, "#cccccc")
            return QBrush(QColor(color))

        if role == Qt.ItemDataRole.TextAlignmentRole and col == "sloc":
            return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        if role == Qt.ItemDataRole.UserRole:
            return metric

        if role == Qt.ItemDataRole.UserRole + 1:
            return self._sort_key(metric, col)

        if role == Qt.ItemDataRole.ToolTipRole and col == "path":
            return metric.path

        return None

    def setData(  # type: ignore[override]
        self, index, value, role=Qt.ItemDataRole.EditRole
    ) -> bool:
        if role != Qt.ItemDataRole.CheckStateRole:
            return False
        if not index.isValid() or index.column() != 0:
            return False
        row = index.row()
        if not (0 <= row < len(self._checked)):
            return False
        try:
            new = Qt.CheckState(value) == Qt.CheckState.Checked
        except (ValueError, TypeError):
            return False
        self._checked[row] = new
        self.dataChanged.emit(index, index, [Qt.ItemDataRole.CheckStateRole])
        return True

    def flags(self, index: QModelIndex):  # type: ignore[override]
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        base = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        if index.column() == 0:
            base |= Qt.ItemFlag.ItemIsUserCheckable
        return base

    def sort(  # type: ignore[override]
        self, column: int, order=Qt.SortOrder.AscendingOrder
    ) -> None:
        if not (0 <= column < len(_COLUMNS)):
            return
        paired = list(zip(self._metrics, self._checked))
        col = _COLUMNS[column]
        reverse = order == Qt.SortOrder.DescendingOrder
        paired.sort(key=lambda mc: self._sort_key(mc[0], col), reverse=reverse)
        self.layoutAboutToBeChanged.emit()
        self._metrics = [m for m, _ in paired]
        self._checked = [c for _, c in paired]
        self.layoutChanged.emit()

    # ---------- Helpers ----------

    def _sort_key(self, metric: FileMetrics, col: str):
        if col == "check":
            return 0
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
            return f"{_STATUS_EMOJI[metric.status_cc]} {metric.complexity:.1f}"
        if col == "mi":
            return f"{_STATUS_EMOJI[metric.status_mi]} {metric.maintainability:.1f}"
        if col == "score":
            return f"{_STATUS_EMOJI[metric.status_pylint]} {metric.pylint_score:.1f}"
        if col == "sec":
            return f"{_STATUS_EMOJI[metric.status_security]} {metric.security_issues}"
        return ""

    # ---------- Public ----------

    def set_metrics(self, metrics: list[FileMetrics]) -> None:
        self.beginResetModel()
        self._metrics = list(metrics)
        self._checked = [True] * len(self._metrics)
        self.endResetModel()

    def metrics_at(self, row: int) -> FileMetrics | None:
        if 0 <= row < len(self._metrics):
            return self._metrics[row]
        return None

    def all_metrics(self) -> list[FileMetrics]:
        return list(self._metrics)

    def checked_metrics(self) -> list[FileMetrics]:
        return [m for m, c in zip(self._metrics, self._checked) if c]

    def set_all_checked(self, checked: bool) -> None:
        self._checked = [checked] * len(self._metrics)
        if self._metrics:
            tl = self.index(0, 0)
            br = self.index(len(self._metrics) - 1, 0)
            self.dataChanged.emit(tl, br, [Qt.ItemDataRole.CheckStateRole])

    def checked_count(self) -> int:
        return sum(1 for c in self._checked if c)
