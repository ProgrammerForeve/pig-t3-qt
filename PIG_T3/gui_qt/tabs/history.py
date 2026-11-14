"""HistoryTab — просмотр git-like дерева истории (ADR-015).

Источник данных — HistoryTreeManager (.pig/history_tree.json).
Слева QTreeView с HistoryTreeModel, справа QTextBrowser с unified diff
before/after из .pig/backups/<node.id>/.

Кнопки:
- Rollback: undo() + restore before/ (1 шаг от current)
- Redo: redo() + restore after/ (1 шаг вперёд)
- Branch: branch_from(selected) — следующий apply пойдёт от выбранной
- Delete: delete_node(selected, cascade=True)
"""

from __future__ import annotations

import difflib
import html
import logging
import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTextBrowser,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from ...core.history_tree import HistoryNode, HistoryTreeManager
from ..models.history_tree_model import HistoryTreeModel

log = logging.getLogger("pig_t3.gui_qt.tabs.history")

_HISTORY_PRUNE_THRESHOLD = 200


def _read_text(path: str) -> str:
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return ""


class HistoryTab(QWidget):
    """Дерево истории + rollback/redo/branch/delete."""

    def __init__(self, settings: dict, parent=None):
        super().__init__(parent)
        self.settings = dict(settings)
        self._current_path = self.settings.get("root_folder", "")
        self._manager: HistoryTreeManager | None = None
        self._setup_ui()
        self._connect_signals()
        if self._current_path and os.path.isdir(self._current_path):
            self.reload()

    # ---------- UI ----------

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        path_row = QHBoxLayout()
        path_row.addWidget(QLabel("Целевая папка:"))
        self.path_edit = QLineEdit(self._current_path)
        self.path_edit.setReadOnly(True)
        self.path_edit.setPlaceholderText("Папка из вкладки Генератор")
        path_row.addWidget(self.path_edit, 1)
        layout.addLayout(path_row)

        toolbar = QHBoxLayout()
        self.btn_refresh = QPushButton("🔄 Обновить")
        self.btn_rollback = QPushButton("↩ Отменить")
        self.btn_rollback.setToolTip("Откатить последний шаг (restore before/)")
        self.btn_redo = QPushButton("↪ Повторить")
        self.btn_redo.setToolTip("Повторить откат (restore after/)")
        self.btn_branch = QPushButton("🌿 Ветвить")
        self.btn_branch.setToolTip("Сделать выбранную ноду current; следующий apply пойдёт от неё")
        self.btn_delete = QPushButton("🗑 Удалить")
        self.btn_delete.setToolTip("Удалить выбранную ноду и её детей")
        self.btn_prune = QPushButton("🧹 Prune")
        self.btn_prune.setToolTip("Удалить все rolled_back ноды вне пути к current")
        self.badge = QLabel("")
        self.badge.setStyleSheet("color: #e5c07b; font-weight: bold;")
        for btn in (
            self.btn_rollback,
            self.btn_redo,
            self.btn_branch,
            self.btn_delete,
            self.btn_prune,
        ):
            btn.setEnabled(False)
        self.status_label = QLabel("Выберите папку проекта во вкладке Генератор")
        toolbar.addWidget(self.btn_refresh)
        toolbar.addWidget(self.btn_rollback)
        toolbar.addWidget(self.btn_redo)
        toolbar.addWidget(self.btn_branch)
        toolbar.addWidget(self.btn_delete)
        toolbar.addWidget(self.btn_prune)
        toolbar.addStretch(1)
        toolbar.addWidget(self.badge)
        toolbar.addWidget(self.status_label, 1)
        layout.addLayout(toolbar)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(splitter, 1)

        self.tree_view = QTreeView()
        self.tree_view.setHeaderHidden(False)
        self.tree_view.setSelectionMode(QTreeView.SelectionMode.SingleSelection)
        self.tree_view.setEditTriggers(QTreeView.EditTrigger.NoEditTriggers)
        self.model = HistoryTreeModel(None)
        self.tree_view.setModel(self.model)
        splitter.addWidget(self.tree_view)

        self.details = QTextBrowser()
        self.details.setOpenExternalLinks(True)
        splitter.addWidget(self.details)

        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        splitter.setSizes([360, 720])

    def _connect_signals(self) -> None:
        self.btn_refresh.clicked.connect(self.reload)
        self.btn_rollback.clicked.connect(self._on_rollback_clicked)
        self.btn_redo.clicked.connect(self._on_redo_clicked)
        self.btn_branch.clicked.connect(self._on_branch_clicked)
        self.btn_delete.clicked.connect(self._on_delete_clicked)
        self.btn_prune.clicked.connect(self._on_prune_clicked)
        self.tree_view.selectionModel().currentRowChanged.connect(self._on_selection_changed)

    # ---------- Public ----------

    def set_path(self, folder: str) -> None:
        self._current_path = folder or ""
        self.path_edit.setText(self._current_path)
        self.reload()

    def reload(self) -> None:
        if not self._current_path or not os.path.isdir(self._current_path):
            self._manager = None
            self.model.set_manager(None)
            self.details.setHtml("")
            self.status_label.setText("Выберите папку проекта во вкладке Генератор")
            self._update_button_states()
            return
        try:
            self._manager = HistoryTreeManager(self._current_path)
        except Exception as e:
            log.warning("history tree load failed: %s", e)
            self._manager = None
            self.model.set_manager(None)
            self.details.setHtml("")
            self.status_label.setText(f"⚠️ Ошибка загрузки: {e}")
            self._update_button_states()
            return
        self.model.set_manager(self._manager)
        if not self._manager.nodes:
            self.details.setHtml(
                "<p><i>История пуста. Примените патч через вкладку «Редактор» — запись появится здесь.</i></p>"
            )
            self.status_label.setText("История пуста (примените патч через Редактор)")
            self._update_button_states()
            return
        self.status_label.setText(f"Нод: {len(self._manager.nodes)} · current: {self._manager.current or '—'}")
        current_idx = self.model.find_index(self._manager.current or "")
        if current_idx.isValid():
            self.tree_view.setCurrentIndex(current_idx)
            self.tree_view.scrollTo(current_idx)
            self.tree_view.expand(current_idx.parent())
        self._update_button_states()

    # ---------- Button states ----------

    def _update_button_states(self) -> None:
        mgr = self._manager
        if mgr is None:
            for btn in (
                self.btn_rollback,
                self.btn_redo,
                self.btn_branch,
                self.btn_delete,
            ):
                btn.setEnabled(False)
            return
        cur = mgr.nodes.get(mgr.current) if mgr.current else None
        has_parent = cur is not None and cur.parent is not None
        has_redo = False
        if cur is not None:
            has_redo = any(c in mgr.nodes and mgr.nodes[c].status == "rolled_back" for c in cur.children)
        has_selection = self.tree_view.currentIndex().isValid()
        self.btn_rollback.setEnabled(has_parent)
        self.btn_redo.setEnabled(has_redo)
        self.btn_branch.setEnabled(has_selection)
        self.btn_delete.setEnabled(has_selection)
        has_rolled_back = any(n.status == "rolled_back" for n in mgr.nodes.values())
        self.btn_prune.setEnabled(has_rolled_back)
        if len(mgr.nodes) > _HISTORY_PRUNE_THRESHOLD:
            self.badge.setText(f"⚠️ История > {_HISTORY_PRUNE_THRESHOLD}")
        else:
            self.badge.setText("")

    # ---------- Handlers ----------

    def _on_rollback_clicked(self) -> None:
        mgr = self._manager
        if mgr is None or not mgr.current:
            return
        node = mgr.nodes.get(mgr.current)
        if node is None or node.parent is None:
            return
        record = {"id": node.id, "paths": list(node.files)}
        mgr.undo()
        self._restore_backup(record, "before")
        self.reload()

    def _on_redo_clicked(self) -> None:
        mgr = self._manager
        if mgr is None or not mgr.current:
            return
        cur = mgr.nodes.get(mgr.current)
        if cur is None:
            return
        candidates = [mgr.nodes[c] for c in cur.children if c in mgr.nodes and mgr.nodes[c].status == "rolled_back"]
        if not candidates:
            return
        candidates.sort(key=lambda n: n.applied_at)
        target = candidates[-1]
        record = {"id": target.id, "paths": list(target.files)}
        mgr.redo()
        self._restore_backup(record, "after")
        self.reload()

    def _on_branch_clicked(self) -> None:
        mgr = self._manager
        if mgr is None:
            return
        nid = self.model.node_id_at(self.tree_view.currentIndex())
        if not nid:
            return
        mgr.branch_from(nid)
        self.reload()

    def _on_delete_clicked(self) -> None:
        mgr = self._manager
        if mgr is None:
            return
        nid = self.model.node_id_at(self.tree_view.currentIndex())
        if not nid:
            return
        ok = QMessageBox.question(
            self,
            "Удалить",
            f"Удалить ноду {nid[:8]}…? (дети тоже будут удалены)",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if ok != QMessageBox.StandardButton.Yes:
            return
        try:
            mgr.delete_node(nid, cascade=True)
        except Exception as e:
            QMessageBox.warning(self, "Ошибка", str(e))
            return
        self.reload()

    def _on_prune_clicked(self) -> None:
        mgr = self._manager
        if mgr is None:
            return
        count = mgr.clear_rolled_back()
        if count:
            self.status_label.setText(f"🧹 Удалено {count} rolled_back нод")
        self.reload()

    def _restore_backup(self, record: dict, which: str) -> None:
        if not self._current_path:
            return
        from ..workers.apply_worker import _restore_snapshot

        backup_dir = os.path.join(
            self._current_path,
            ".pig",
            "backups",
            record["id"],
            which,
        )
        try:
            _restore_snapshot(self._current_path, backup_dir, record.get("paths", []))
        except Exception as e:
            log.warning("restore backup failed: %s", e)

    def _on_selection_changed(self, current, _previous) -> None:
        self._update_button_states()
        node = self.model.data(current, Qt.ItemDataRole.UserRole)
        if node is None:
            self.details.setHtml("")
            return
        self.details.setHtml(self._build_details_html(node))

    def _build_details_html(self, node: HistoryNode) -> str:
        is_current = self._manager is not None and self._manager.current == node.id
        header = (
            f"<h3>{html.escape(node.action_summary or '(без описания)')}</h3>"
            f"<p>"
            f"<b>id:</b> <code>{html.escape(node.id)}</code><br>"
            f"<b>source:</b> {html.escape(node.source)}<br>"
            f"<b>status:</b> {html.escape(node.status)}"
            f"{' 🔵 current' if is_current else ''}<br>"
            f"<b>applied_at:</b> {html.escape(node.applied_at or '—')}<br>"
            f"<b>files:</b> {html.escape(', '.join(node.files) or '—')}"
            f"</p>"
        )
        return header + self._build_diff_html(node)

    def _build_diff_html(self, node: HistoryNode) -> str:
        if not self._current_path:
            return ""
        backup_dir = os.path.join(self._current_path, ".pig", "backups", node.id)
        before_dir = os.path.join(backup_dir, "before")
        after_dir = os.path.join(backup_dir, "after")
        if not os.path.isdir(before_dir) and not os.path.isdir(after_dir):
            return "<p><i>Бэкап не найден (возможно, удалён prune'ом или записан не через ApplyWorker).</i></p>"
        parts: list[str] = []
        for rel in node.files:
            old = _read_text(os.path.join(before_dir, rel))
            new = _read_text(os.path.join(after_dir, rel))
            if old == new:
                continue
            diff_lines = list(
                difflib.unified_diff(
                    old.splitlines(keepends=True),
                    new.splitlines(keepends=True),
                    fromfile=f"before/{rel}",
                    tofile=f"after/{rel}",
                )
            )
            if not diff_lines:
                continue
            parts.append(f"<h4>{html.escape(rel)}</h4><pre>{html.escape(''.join(diff_lines))}</pre>")
        if not parts:
            return "<p><i>Нет изменений в файлах</i></p>"
        return "".join(parts)
