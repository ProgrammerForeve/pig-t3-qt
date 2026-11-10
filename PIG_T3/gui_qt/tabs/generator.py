"""Вкладка «Генератор» — каркас (T-101).

Содержит поля ввода пути проекта, расширений, ignore-листа и имени отчёта.
Не выполняет генерацию — это делает воркер (T-107).

Публичный интерфейс:
- ``GeneratorTab(settings: dict)`` — конструктор, читает значения из ``settings``
- ``collect_settings() -> dict`` — собрать текущие значения в формате конфига
- ``settings_changed`` (Signal) — испускается при любом изменении поля
"""

from __future__ import annotations

import os
import sys

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QGridLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class GeneratorTab(QWidget):
    """Каркас вкладки «Генератор»."""

    settings_changed = Signal()

    def __init__(self, settings: dict):
        super().__init__()
        self.settings = settings
        self._setup_ui()
        self._populate(settings)
        self._connect_signals()

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

        layout.addStretch(1)

    def _populate(self, settings: dict) -> None:
        self.path_edit.setText(settings.get("root_folder", ""))
        self.ext_edit.setText(settings.get("extensions", ""))
        self.ignore_edit.setText(settings.get("ignore_list", ""))
        self.output_edit.setText(settings.get("output_name", ""))

    def _connect_signals(self) -> None:
        self.btn_browse.clicked.connect(self.browse_folder)
        self.btn_auto.clicked.connect(self.auto_set_folder)

        for edit in (self.path_edit, self.ext_edit, self.ignore_edit, self.output_edit):
            edit.textChanged.connect(self.settings_changed)

    # ---------- Public ----------

    def collect_settings(self) -> dict:
        """Возвращает текущие значения полей в формате конфига."""
        return {
            "root_folder": self.path_edit.text(),
            "extensions": self.ext_edit.text(),
            "ignore_list": self.ignore_edit.text(),
            "output_name": self.output_edit.text(),
        }

    # ---------- Handlers ----------

    def browse_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Выберите папку проекта", self.path_edit.text())
        if folder:
            self.path_edit.setText(folder)

    def auto_set_folder(self) -> None:
        """Устанавливает путь по эвристике: frozen → рядом с .exe, иначе → корень репо."""
        if getattr(sys, "frozen", False):
            parent_dir = os.path.dirname(sys.executable)
        else:
            # PIG_T3/gui_qt/tabs/generator.py → ../../.. = корень репозитория
            parent_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
        self.path_edit.setText(parent_dir)
