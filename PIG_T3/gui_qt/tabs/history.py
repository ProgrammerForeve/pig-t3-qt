"""HistoryTab — просмотр git-like дерева истории (ADR-015, view only).

Источник данных — HistoryTreeManager (.pig/history_tree.json).
Слева QTreeView с HistoryTreeModel, справа QTextBrowser с unified diff
before/after из .pig/backups/<node.id>/.

Кнопки Rollback / Branch / Redo / Delete — disabled заглушки до
миграции EditorTab на HistoryTreeManager (ADR-015 P0 step 4).
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


_STUB_TOOLTIP = "Требуется миграция EditorTab на HistoryTreeManager (ADR-015 P0 step 4)"


def _read_text(path: str) -> str:
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return ""


class HistoryTab(QWidget):
    """Просмотр дерева истории (read-only на этом этапе)."""

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
        self.btn_rollback = QPushButton("↩ Rollback to here")
        self.btn_branch = QPushButton("🌿 Branch from here")
        self.btn_redo = QPushButton("↪ Redo")
        self.btn_delete = QPushButton("🗑 Delete node")
        for btn in (self.btn_rollback, self.btn_branch, self.btn_redo, self.btn_delete):
            btn.setEnabled(False)
            btn.setToolTip(_STUB_TOOLTIP)
        self.status_label = QLabel("Выберите папку проекта во вкладке Генератор")
        toolbar.addWidget(self.btn_refresh)
        toolbar.addWidget(self.btn_rollback)
        toolbar.addWidget(self.btn_branch)
        toolbar.addWidget(self.btn_redo)
        toolbar.addWidget(self.btn_delete)
        toolbar.addStretch(1)
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
            return
        try:
            self._manager = HistoryTreeManager(self._current_path)
        except Exception as e:
            log.warning("history tree load failed: %s", e)
            self._manager = None
            self.model.set_manager(None)
            self.details.setHtml("")
            self.status_label.setText(f"⚠️ Ошибка загрузки: {e}")
            return
        self.model.set_manager(self._manager)
        if not self._manager.nodes:
            self.details.setHtml(
                "<p><i>История пуста. Примените патч через вкладку «Редактор» — запись появится здесь.</i></p>"
            )
            self.status_label.setText("История пуста (примените патч через Редактор)")
            return
        self.status_label.setText(f"Нод: {len(self._manager.nodes)} · current: {self._manager.current or '—'}")
        current_idx = self.model.find_index(self._manager.current or "")
        if current_idx.isValid():
            self.tree_view.setCurrentIndex(current_idx)
            self.tree_view.scrollTo(current_idx)
            self.tree_view.expand(current_idx.parent())

    # ---------- Handlers ----------

    def _on_selection_changed(self, current, _previous) -> None:
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
