"""HistoryTreeModel — QAbstractItemModel для HistoryTreeManager (ADR-015).

Источник истины — HistoryTreeManager.nodes (dict[id, HistoryNode]).
Дерево строится по parent/children. Внутренний int-id для QModelIndex
через _id_to_int (как ProjectTreeModel — не internalPointer, ADR-009).

Иконки статуса: 🟢 applied · 🔵 current · ⚪ rolled_back.
"""

from __future__ import annotations

from PySide6.QtCore import QAbstractItemModel, QModelIndex, Qt

from ...core.history_tree import HistoryNode, HistoryTreeManager

_ICON = {
    "applied": "🟢",
    "rolled_back": "⚪",
    "failed": "🔴",
}


class HistoryTreeModel(QAbstractItemModel):
    """Модель дерева истории. Одна колонка."""

    def __init__(self, manager: HistoryTreeManager | None = None, parent=None):
        super().__init__(parent)
        self._manager = manager
        self._root_children: list[str] = []
        self._id_to_int: dict[str, int] = {}
        self._int_to_id: dict[int, str] = {}
        self._next_int = 1
        self._rebuild()

    # ---------- Registry ----------

    def _get_int(self, node_id: str) -> int:
        if node_id not in self._id_to_int:
            self._id_to_int[node_id] = self._next_int
            self._int_to_id[self._next_int] = node_id
            self._next_int += 1
        return self._id_to_int[node_id]

    def _node_from_index(self, index: QModelIndex) -> HistoryNode | None:
        if not index.isValid() or self._manager is None:
            return None
        nid = self._int_to_id.get(int(index.internalId()))
        if nid is None:
            return None
        return self._manager.nodes.get(nid)

    def _rebuild(self) -> None:
        self._id_to_int.clear()
        self._int_to_id.clear()
        self._next_int = 1
        self._root_children = []
        if self._manager is None:
            return
        for nid, node in self._manager.nodes.items():
            if node.parent is None:
                self._root_children.append(nid)
        # Стабильный порядок — по applied_at (fallback — id).
        self._root_children.sort(
            key=lambda nid: (
                self._manager.nodes[nid].applied_at or "",
                nid,
            )
        )

    # ---------- Public ----------

    def set_manager(self, manager: HistoryTreeManager | None) -> None:
        self.beginResetModel()
        self._manager = manager
        self._rebuild()
        self.endResetModel()

    def node_id_at(self, index: QModelIndex) -> str:
        node = self._node_from_index(index)
        return "" if node is None else node.id

    def find_index(self, node_id: str) -> QModelIndex:
        if self._manager is None or node_id not in self._manager.nodes:
            return QModelIndex()
        node = self._manager.nodes[node_id]
        if node.parent is None:
            try:
                row = self._root_children.index(node_id)
            except ValueError:
                return QModelIndex()
        else:
            parent = self._manager.nodes.get(node.parent)
            if parent is None:
                return QModelIndex()
            try:
                row = list(parent.children).index(node_id)
            except ValueError:
                return QModelIndex()
        return self.createIndex(row, 0, self._get_int(node_id))

    # ---------- QAbstractItemModel ----------

    def index(self, row, column, parent=QModelIndex()):
        if not self.hasIndex(row, column, parent):
            return QModelIndex()
        if parent.isValid():
            parent_node = self._node_from_index(parent)
            if parent_node is None:
                return QModelIndex()
            children = list(parent_node.children)
        else:
            children = self._root_children
        if row < 0 or row >= len(children):
            return QModelIndex()
        return self.createIndex(row, column, self._get_int(children[row]))

    def parent(self, index):  # type: ignore[override]
        if not index.isValid() or self._manager is None:
            return QModelIndex()
        node = self._node_from_index(index)
        if node is None or node.parent is None:
            return QModelIndex()
        parent_node = self._manager.nodes.get(node.parent)
        if parent_node is None:
            return QModelIndex()
        if parent_node.parent is None:
            gp_children = self._root_children
        else:
            gp = self._manager.nodes.get(parent_node.parent)
            gp_children = list(gp.children) if gp is not None else []
        try:
            row = gp_children.index(parent_node.id)
        except ValueError:
            return QModelIndex()
        return self.createIndex(row, 0, self._get_int(parent_node.id))

    def rowCount(self, parent=QModelIndex()):  # type: ignore[override]
        if parent.column() > 0:
            return 0
        if not parent.isValid():
            return len(self._root_children)
        node = self._node_from_index(parent)
        return 0 if node is None else len(node.children)

    def columnCount(self, parent=QModelIndex()):  # type: ignore[override]
        return 1

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        node = self._node_from_index(index)
        if node is None:
            return None
        is_current = self._manager is not None and self._manager.current == node.id
        if role == Qt.ItemDataRole.DisplayRole:
            icon = _ICON.get(node.status, "•")
            mark = " 🔵" if is_current else ""
            return f"{icon} {node.action_summary}{mark}"
        if role == Qt.ItemDataRole.ToolTipRole:
            return (
                f"id: {node.id}\n"
                f"source: {node.source}\n"
                f"status: {node.status}"
                f"{' (current)' if is_current else ''}\n"
                f"files: {', '.join(node.files) or '—'}\n"
                f"applied_at: {node.applied_at}"
            )
        if role == Qt.ItemDataRole.UserRole:
            return node
        return None

    def headerData(  # type: ignore[override]
        self, section, orientation, role=Qt.ItemDataRole.DisplayRole
    ):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return "История"
        return super().headerData(section, orientation, role)
