"""ProjectTreeModel: QAbstractItemModel для дерева проекта с чекбоксами (T-104).

Хранит иерархию узлов (файлы + папки) с tristate-состоянием:
- Checked — включён (по умолчанию)
- Unchecked — исключён
- PartiallyChecked — у папки есть смешанные потомки

Публичный интерфейс:
- ``ProjectTreeModel(root_path, files)`` — где ``files`` — список
  ``(absolute_path, extension)`` из ``ProjectAnalyzer.scan_directory()``
- ``checkStateChanged`` (Signal) — испускается при любом изменении чекбокса
- ``checked_files() -> list[str]`` — абсолютные пути включённых файлов
- ``unchecked_paths() -> list[str]`` — относительные пути исключённых узлов
  (совместимо с ``ui_tree_unchecked`` legacy-формата)
- ``set_unchecked_paths(paths)`` — восстановить состояние по списку путей
- ``find_index(rel_path) -> QModelIndex`` — найти индекс по относительному пути

Сортировка: папки раньше файлов, обе группы — по алфавиту
(case-insensitive).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from PySide6.QtCore import QAbstractItemModel, QModelIndex, Qt, Signal


@dataclass
class TreeNode:
    """Узел дерева (файл или папка)."""

    name: str
    path: str
    is_dir: bool
    parent: TreeNode | None = None
    children: list[TreeNode] = field(default_factory=list)
    check_state: Qt.CheckState = Qt.CheckState.Checked


class ProjectTreeModel(QAbstractItemModel):
    """Модель дерева проекта с чекбоксами (одна колонка)."""

    checkStateChanged = Signal()

    def __init__(
        self,
        root_path: str,
        files: list[tuple[str, str]],
        parent=None,
    ):
        super().__init__(parent)
        self.root_path = os.path.abspath(root_path)
        self._root = TreeNode(name="", path=self.root_path, is_dir=True)
        self._build_tree(files)
        self._recompute_all(self._root)

    # ---------- Building ----------

    def _build_tree(self, files: list[tuple[str, str]]) -> None:
        dirs_map: dict[str, TreeNode] = {"": self._root}

        for full_path, _ext in files:
            rel = os.path.relpath(full_path, self.root_path).replace("\\", "/")
            parts = rel.split("/")
            current_rel = ""
            parent_node = self._root
            for part in parts[:-1]:
                current_rel = f"{current_rel}/{part}" if current_rel else part
                if current_rel not in dirs_map:
                    node = TreeNode(
                        name=part,
                        path=os.path.join(self.root_path, current_rel),
                        is_dir=True,
                        parent=parent_node,
                    )
                    parent_node.children.append(node)
                    dirs_map[current_rel] = node
                parent_node = dirs_map[current_rel]

            fname = parts[-1]
            file_node = TreeNode(
                name=fname,
                path=full_path,
                is_dir=False,
                parent=parent_node,
            )
            parent_node.children.append(file_node)

        self._sort_recursive(self._root)

    def _sort_recursive(self, node: TreeNode) -> None:
        node.children.sort(key=lambda n: (0 if n.is_dir else 1, n.name.lower()))
        for child in node.children:
            self._sort_recursive(child)

    def _recompute_all(self, node: TreeNode) -> None:
        """Bottom-up: состояние папки = агрегат её детей."""
        for child in node.children:
            self._recompute_all(child)
        if node is self._root or not node.children:
            return
        states = {c.check_state for c in node.children}
        if states == {Qt.CheckState.Checked}:
            node.check_state = Qt.CheckState.Checked
        elif states == {Qt.CheckState.Unchecked}:
            node.check_state = Qt.CheckState.Unchecked
        else:
            node.check_state = Qt.CheckState.PartiallyChecked

    # ---------- Index mapping ----------

    def _node_to_index(self, node: TreeNode) -> QModelIndex:
        if node is self._root:
            return QModelIndex()
        parent = node.parent
        row = parent.children.index(node)
        return self.createIndex(row, 0, node)

    def _find_node(self, rel_path: str) -> TreeNode | None:
        if not rel_path:
            return self._root
        parts = rel_path.split("/")
        node = self._root
        for part in parts:
            found = None
            for child in node.children:
                if child.name == part:
                    found = child
                    break
            if found is None:
                return None
            node = found
        return node

    def _rel_path(self, node: TreeNode) -> str:
        return os.path.relpath(node.path, self.root_path).replace("\\", "/")

    # ---------- QAbstractItemModel API ----------

    def index(
        self,
        row: int,
        column: int,
        parent: QModelIndex = QModelIndex(),
    ) -> QModelIndex:
        if not self.hasIndex(row, column, parent):
            return QModelIndex()
        parent_node = parent.internalPointer() if parent.isValid() else self._root
        if row < 0 or row >= len(parent_node.children):
            return QModelIndex()
        return self.createIndex(row, column, parent_node.children[row])

    def parent(self, index: QModelIndex) -> QModelIndex:  # type: ignore[override]
        if not index.isValid():
            return QModelIndex()
        node = index.internalPointer()
        if node is None or node.parent is None or node.parent is self._root:
            return QModelIndex()
        return self._node_to_index(node.parent)

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # type: ignore[override]
        if parent.column() > 0:
            return 0
        node = parent.internalPointer() if parent.isValid() else self._root
        return len(node.children)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # type: ignore[override]
        return 1

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        node = index.internalPointer()
        if role == Qt.ItemDataRole.DisplayRole:
            return node.name
        if role == Qt.ItemDataRole.CheckStateRole:
            return node.check_state
        return None

    def setData(  # type: ignore[override]
        self,
        index: QModelIndex,
        value,
        role: int = Qt.ItemDataRole.EditRole,
    ) -> bool:
        if not index.isValid() or role != Qt.ItemDataRole.CheckStateRole:
            return False
        try:
            state = Qt.CheckState(value)
        except (ValueError, TypeError):
            return False

        node = index.internalPointer()
        if node.is_dir:
            self._set_subtree_state(node, state)
        else:
            node.check_state = state

        if node.parent is not None and node.parent is not self._root:
            self._recompute_ancestors(node.parent)

        self._notify_subtree_changed(node)
        self.checkStateChanged.emit()
        return True

    def flags(self, index: QModelIndex) -> Qt.ItemFlag:  # type: ignore[override]
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        return Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsUserCheckable

    # ---------- Helpers ----------

    def _set_subtree_state(self, node: TreeNode, state: Qt.CheckState) -> None:
        node.check_state = state
        for child in node.children:
            self._set_subtree_state(child, state)

    def _recompute_ancestors(self, node: TreeNode) -> None:
        while node is not self._root:
            states = {c.check_state for c in node.children}
            if states == {Qt.CheckState.Checked}:
                new_state = Qt.CheckState.Checked
            elif states == {Qt.CheckState.Unchecked}:
                new_state = Qt.CheckState.Unchecked
            else:
                new_state = Qt.CheckState.PartiallyChecked
            node.check_state = new_state
            idx = self._node_to_index(node)
            if idx.isValid():
                self.dataChanged.emit(idx, idx, [Qt.ItemDataRole.CheckStateRole])
            if node.parent is None or node.parent is self._root:
                break
            node = node.parent

    def _notify_subtree_changed(self, node: TreeNode) -> None:
        idx = self._node_to_index(node)
        if idx.isValid():
            self.dataChanged.emit(idx, idx, [Qt.ItemDataRole.CheckStateRole])
        for child in node.children:
            self._notify_subtree_changed(child)

    def _notify_all(self) -> None:
        for child in self._root.children:
            self._notify_subtree_changed(child)

    # ---------- Public helpers ----------

    def find_index(self, rel_path: str) -> QModelIndex:
        """Вернуть QModelIndex по относительному пути (или invalid, если нет)."""
        node = self._find_node(rel_path)
        if node is None:
            return QModelIndex()
        return self._node_to_index(node)

    def checked_files(self) -> list[str]:
        """Абсолютные пути включённых файлов (только листья)."""
        result: list[str] = []

        def walk(node: TreeNode) -> None:
            if not node.is_dir and node.check_state == Qt.CheckState.Checked:
                result.append(node.path)
            for child in node.children:
                walk(child)

        for child in self._root.children:
            walk(child)
        return result

    def unchecked_paths(self) -> list[str]:
        """Относительные пути исключённых узлов (файлов и полностью исключённых папок).

        Совместимо с legacy-форматом ``ui_tree_unchecked``:
        если папка исключена полностью — возвращается её путь (без потомков);
        если исключён один файл — его путь.
        """
        result: list[str] = []

        def walk(node: TreeNode) -> None:
            if node.check_state == Qt.CheckState.Unchecked:
                result.append(self._rel_path(node))
            else:
                for child in node.children:
                    walk(child)

        for child in self._root.children:
            walk(child)
        return result

    def set_unchecked_paths(self, paths) -> None:
        """Сбросить всё в Checked, пометить указанные пути Unchecked,
        пересчитать состояния папок. Совместим с legacy-форматом (допускает
        избыточные пути: папка + её потомки)."""
        self._set_subtree_state(self._root, Qt.CheckState.Checked)
        for path in paths:
            node = self._find_node(path)
            if node is None:
                continue
            if node.is_dir:
                self._set_subtree_state(node, Qt.CheckState.Unchecked)
            else:
                node.check_state = Qt.CheckState.Unchecked
        self._recompute_all(self._root)
        self._notify_all()
