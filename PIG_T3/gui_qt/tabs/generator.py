"""Вкладка «Генератор» — каркас (T-101..T-103) + дерево (T-105..T-106).

Публичный интерфейс:
- ``GeneratorTab(settings: dict)``
- ``collect_settings() -> dict``
- ``commit_recent_projects()`` — recent_projects + completer refresh
- ``refresh_tree()`` — сканировать и пересобрать дерево
- ``set_tree_data(files)`` — пересобрать дерево из явного списка (тесты)
- ``capture_tree_state() -> dict``
- ``restore_tree_state_from_settings()``
- ``settings_changed`` (Signal)
"""

from __future__ import annotations

import os
import sys

from PySide6.QtCore import QModelIndex, QStringListModel, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QCompleter,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ...core.analyzer import ProjectAnalyzer
from ..models.project_tree import ProjectTreeModel
from ..widgets.project_tree_view import ProjectTreeView

_RECENT_PROJECTS_LIMIT = 10
_TREE_REFRESH_DELAY_MS = 600


class GeneratorTab(QWidget):
    """Каркас вкладки «Генератор»."""

    settings_changed = Signal()

    def __init__(self, settings: dict):
        super().__init__()
        self.settings = settings
        self.analyzer = ProjectAnalyzer()
        self._last_root = None

        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.setInterval(_TREE_REFRESH_DELAY_MS)
        self._refresh_timer.timeout.connect(self.refresh_tree)

        self._setup_ui()
        self._populate(settings)
        self._connect_signals()
        self.refresh_tree()

        # Restore unchecked synchronously — set_unchecked_paths only
        # emits dataChanged, no persistent indices, safe right after
        # reset_data.
        unchecked = self.settings.get("ui_tree_unchecked", [])
        if unchecked:
            self.tree_model.set_unchecked_paths(unchecked)

        # Restore expanded DEFERRED — setExpanded creates persistent
        # indices in QTreeView. Calling it synchronously right after
        # endResetModel can corrupt view internals on some Qt versions
        # (free(): invalid size). One event-loop tick is enough.
        expanded = self.settings.get("ui_tree_expanded", [])
        if expanded:
            QTimer.singleShot(0, lambda e=list(expanded): self._restore_expanded_paths(e))

    # ---------- UI ----------

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        # --- Строка «Папка проекта» ---
        layout.addWidget(QLabel("Папка проекта:"))

        path_row = QWidget()
        path_layout = QGridLayout(path_row)
        path_layout.setContentsMargins(0, 0, 0, 0)

        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText("Путь к проекту…")
        self._setup_completer()
        self.btn_browse = QPushButton("Обзор…")
        self.btn_auto = QPushButton("Авто")
        path_layout.addWidget(self.path_edit, 0, 0)
        path_layout.addWidget(self.btn_browse, 0, 1)
        path_layout.addWidget(self.btn_auto, 0, 2)
        path_layout.setColumnStretch(0, 1)
        layout.addWidget(path_row)

        # --- Расширения / Имя отчёта ---
        fields_row = QWidget()
        fields_layout = QGridLayout(fields_row)
        fields_layout.setContentsMargins(0, 0, 0, 0)

        fields_layout.addWidget(QLabel("Расширения:"), 0, 0)
        fields_layout.addWidget(QLabel("Имя отчёта:"), 0, 1)

        self.ext_edit = QLineEdit()
        self.output_edit = QLineEdit()
        fields_layout.addWidget(self.ext_edit, 1, 0)
        fields_layout.addWidget(self.output_edit, 1, 1)
        fields_layout.setColumnStretch(0, 1)
        fields_layout.setColumnStretch(1, 1)
        layout.addWidget(fields_row)

        # --- Ignore-лист ---
        layout.addWidget(QLabel("Исключить (Ignore):"))
        self.ignore_edit = QLineEdit()
        layout.addWidget(self.ignore_edit)

        # --- Опции генерации (сворачиваемые, T-106b) ---
        self.options_toggle = QToolButton()
        self.options_toggle.setText("Опции генерации")
        self.options_toggle.setCheckable(True)
        self.options_toggle.setChecked(True)
        self.options_toggle.setArrowType(Qt.ArrowType.DownArrow)
        self.options_toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.options_toggle.toggled.connect(self._on_options_toggled)
        layout.addWidget(self.options_toggle)

        self.options_widget = QWidget()
        options_layout = QVBoxLayout(self.options_widget)
        options_layout.setContentsMargins(20, 0, 0, 0)

        self.cb_include_empty = QCheckBox("Включить в отчёт пустые папки")
        self.cb_add_edit_prompt = QCheckBox("Добавить инструкцию для AI (JSON Format)")
        self.cb_include_plan = QCheckBox("Добавить текущий план к отчёту")
        self.cb_line_numbers = QCheckBox("Нумеровать строки (для точного редактирования)")
        self.cb_auto_copy = QCheckBox("Авто-копировать ФАЙЛ в буфер (для вставки в чат)")

        for cb in self._checkboxes():
            options_layout.addWidget(cb)
        layout.addWidget(self.options_widget)

        # --- Дерево проекта (T-105) ---
        tree_header = QHBoxLayout()
        tree_header.addWidget(QLabel("Структура проекта:"))
        tree_header.addStretch(1)
        self.btn_refresh_tree = QPushButton("🔄 Обновить")
        tree_header.addWidget(self.btn_refresh_tree)
        layout.addLayout(tree_header)

        self.tree_model = ProjectTreeModel("", [])
        self.tree_view = ProjectTreeView()
        self.tree_view.setModel(self.tree_model)
        layout.addWidget(self.tree_view, 1)

    def _setup_completer(self) -> None:
        recent = list(self.settings.get("recent_projects", []))
        self._completer_model = QStringListModel(recent)
        completer = QCompleter(self._completer_model, self)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self.path_edit.setCompleter(completer)

    def _checkboxes(self) -> tuple[QCheckBox, ...]:
        return (
            self.cb_include_empty,
            self.cb_add_edit_prompt,
            self.cb_include_plan,
            self.cb_line_numbers,
            self.cb_auto_copy,
        )

    def _populate(self, settings: dict) -> None:
        self.path_edit.setText(settings.get("root_folder", ""))
        self.ext_edit.setText(settings.get("extensions", ""))
        self.ignore_edit.setText(settings.get("ignore_list", ""))
        self.output_edit.setText(settings.get("output_name", ""))

        self.cb_include_empty.setChecked(settings.get("include_empty_folders", False))
        self.cb_add_edit_prompt.setChecked(settings.get("add_edit_prompt", False))
        self.cb_include_plan.setChecked(settings.get("include_plan", False))
        self.cb_line_numbers.setChecked(settings.get("line_numbers", False))
        self.cb_auto_copy.setChecked(settings.get("auto_copy_file", False))

    def _connect_signals(self) -> None:
        self.btn_browse.clicked.connect(self.browse_folder)
        self.btn_auto.clicked.connect(self.auto_set_folder)
        self.btn_refresh_tree.clicked.connect(self.refresh_tree)

        for edit in (self.path_edit, self.ext_edit, self.ignore_edit, self.output_edit):
            edit.textChanged.connect(self._on_field_changed)

        for cb in self._checkboxes():
            cb.toggled.connect(self._on_checkbox_toggled)

    def _on_field_changed(self, _text: str) -> None:
        self.settings_changed.emit()
        self._refresh_timer.start()

    def _on_checkbox_toggled(self, _checked: bool) -> None:
        self.settings_changed.emit()

    def _on_options_toggled(self, checked: bool) -> None:
        self.options_widget.setVisible(checked)
        self.options_toggle.setArrowType(Qt.ArrowType.DownArrow if checked else Qt.ArrowType.RightArrow)

    # ---------- Public ----------

    def collect_settings(self) -> dict:
        """Возвращает текущие значения полей в формате конфига."""
        return {
            "root_folder": self.path_edit.text(),
            "extensions": self.ext_edit.text(),
            "ignore_list": self.ignore_edit.text(),
            "output_name": self.output_edit.text(),
            "include_empty_folders": self.cb_include_empty.isChecked(),
            "add_edit_prompt": self.cb_add_edit_prompt.isChecked(),
            "include_plan": self.cb_include_plan.isChecked(),
            "line_numbers": self.cb_line_numbers.isChecked(),
            "auto_copy_file": self.cb_auto_copy.isChecked(),
        }

    def commit_recent_projects(self) -> None:
        current = self.path_edit.text().strip()
        if not current:
            return
        recent = [p for p in self.settings.get("recent_projects", []) if p != current]
        recent.insert(0, current)
        recent = recent[:_RECENT_PROJECTS_LIMIT]
        self.settings["recent_projects"] = recent
        self._completer_model.setStringList(recent)

    def capture_tree_state(self) -> dict:
        """Снимок ui_tree_expanded / ui_tree_unchecked для сохранения."""
        try:
            return {
                "ui_tree_expanded": self._capture_expanded_paths(),
                "ui_tree_unchecked": self.tree_model.unchecked_paths(),
            }
        except Exception as e:
            print(f"Error capturing tree state: {e}")
            return {"ui_tree_expanded": [], "ui_tree_unchecked": []}

    def refresh_tree(self) -> None:
        """Сканирует текущий root_folder и пересобирает дерево.

        Если root не изменился — сохраняет состояние чекбоксов и
        раскрытых папок. Если изменился — сбрасывает (новый проект).
        """
        root = self.path_edit.text().strip()
        root_changed = root != self._last_root
        self._last_root = root

        if not root or not os.path.isdir(root):
            self.tree_model.reset_data([], root or os.getcwd())
            return

        if not root_changed and self.tree_model.root_path:
            try:
                saved_unchecked = self.tree_model.unchecked_paths()
                saved_expanded = self._capture_expanded_paths()
            except Exception as e:
                print(f"Error capturing state before refresh: {e}")
                saved_unchecked = []
                saved_expanded = []
        else:
            saved_unchecked = []
            saved_expanded = []

        extensions_clean = ", ".join(x.strip() for x in self.ext_edit.text().split(",") if x.strip())
        ignore_clean = ", ".join(x.strip() for x in self.ignore_edit.text().split(",") if x.strip())
        # Sentinel: пустой ignore_list станет [''] после split в
        # analyzer, а '' in <any path> истинно → отфильтрует всё.
        if not ignore_clean:
            ignore_clean = "\x00"

        cfg = self.settings.copy()
        cfg.update(
            {
                "root_folder": root,
                "extensions": extensions_clean,
                "ignore_list": ignore_clean,
                "strict_mode": self.settings.get("strict_mode", False),
            }
        )
        try:
            files, _empty = self.analyzer.scan_directory(cfg)
        except Exception as e:
            print(f"Tree scan error: {e}")
            files = []
        self.tree_model.reset_data(files, root)

        if saved_unchecked:
            self.tree_model.set_unchecked_paths(saved_unchecked)
        if saved_expanded:
            # Defer setExpanded — same reason as in _deferred_restore.
            QTimer.singleShot(0, lambda e=list(saved_expanded): self._restore_expanded_paths(e))

    def set_tree_data(self, files: list[tuple[str, str]]) -> None:
        """Пересобрать дерево из явного списка (для тестов/внешних вызовов)."""
        self.tree_model.reset_data(files, self.path_edit.text())

    # ---------- Tree state helpers ----------

    def _capture_expanded_paths(self) -> list[str]:
        """Относительные пути всех раскрытых папок.

        Обёрнуто в try/except: на некоторых Qt-сборках внутренние
        persistent indices могут быть временно невалидны (особенно
        сразу после reset_data). Безопаснее вернуть частичный
        результат, чем уронить приложение.
        """
        result: list[str] = []

        def walk(index: QModelIndex) -> None:
            if not index.isValid():
                return
            try:
                node = index.internalPointer()
                if node is not None and node.is_dir and self.tree_view.isExpanded(index):
                    result.append(self.tree_model.relative_path(index))
                for i in range(self.tree_model.rowCount(index)):
                    walk(self.tree_model.index(i, 0, index))
            except Exception as e:
                print(f"walk error at expanded capture: {e}")

        try:
            for i in range(self.tree_model.rowCount(QModelIndex())):
                walk(self.tree_model.index(i, 0, QModelIndex()))
        except Exception as e:
            print(f"Error capturing expanded paths: {e}")
        return result

    def _restore_expanded_paths(self, paths: list[str]) -> None:
        for rel in paths:
            idx = self.tree_model.find_index(rel)
            if idx.isValid():
                self.tree_view.setExpanded(idx, True)

    # ---------- Handlers ----------

    def browse_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Выберите папку проекта", self.path_edit.text())
        if folder:
            self.path_edit.setText(folder)

    def auto_set_folder(self) -> None:
        if getattr(sys, "frozen", False):
            parent_dir = os.path.dirname(sys.executable)
        else:
            parent_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
        self.path_edit.setText(parent_dir)
