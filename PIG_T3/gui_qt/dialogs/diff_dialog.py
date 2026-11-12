"""DiffDialog — предпросмотр изменений JSON-патча (B1)."""

from __future__ import annotations

from html import escape

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
)

from ..workers.diff_preview import CommandSpec, FileDiff

_STATUS_ICON = {
    "created": "➕",
    "modified": "✏️",
    "deleted": "🗑️",
    "failed": "⚠️",
}


def _diff_to_html(text: str) -> str:
    parts: list[str] = []
    for line in text.splitlines():
        escaped = escape(line)
        if line.startswith("+++") or line.startswith("---"):
            parts.append(f'<span style="color:#61afef;font-weight:bold;">{escaped}</span>')
        elif line.startswith("@@"):
            parts.append(f'<span style="color:#c678dd;">{escaped}</span>')
        elif line.startswith("+"):
            parts.append(f'<span style="color:#98c379;">{escaped}</span>')
        elif line.startswith("-"):
            parts.append(f'<span style="color:#e06c75;">{escaped}</span>')
        else:
            parts.append(escaped)
    return "<pre style='font-family:monospace;'>" + "<br>".join(parts) + "</pre>"


class DiffDialog(QDialog):
    def __init__(
        self,
        diffs: list[FileDiff],
        commands: list[CommandSpec] | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self._diffs = list(diffs)
        self._commands = list(commands or [])
        self.setWindowTitle("Просмотр изменений")
        self.resize(1000, 640)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        if not self._diffs and not self._commands:
            layout.addWidget(QLabel("Нет изменений для отображения."))
        else:
            parts = []
            if self._diffs:
                parts.append(f"файлов: {len(self._diffs)}")
            if self._commands:
                parts.append(f"команд: {len(self._commands)}")
            summary = QLabel("Затронуто: " + ", ".join(parts))
            layout.addWidget(summary)

            splitter = QSplitter(Qt.Orientation.Horizontal)
            layout.addWidget(splitter, 1)

            self.file_list = QListWidget()
            for d in self._diffs:
                icon = _STATUS_ICON.get(d.status, "•")
                QListWidgetItem(f"{icon}  {d.path}", self.file_list)
            for c in self._commands:
                tag = "⏹" if c.on_failure == "abort" else "▶"
                QListWidgetItem(f"{tag}  $ {c.command}", self.file_list)
            self.file_list.currentRowChanged.connect(self._on_file_selected)
            splitter.addWidget(self.file_list)

            self.diff_view = QTextEdit()
            self.diff_view.setReadOnly(True)
            splitter.addWidget(self.diff_view)

            splitter.setStretchFactor(0, 1)
            splitter.setStretchFactor(1, 3)
            splitter.setSizes([280, 720])

            if self._diffs or self._commands:
                self.file_list.setCurrentRow(0)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        self.btn_cancel = QPushButton("Отмена")
        self.btn_apply = QPushButton("Применить")
        self.btn_apply.setDefault(True)
        btn_row.addWidget(self.btn_cancel)
        btn_row.addWidget(self.btn_apply)
        layout.addLayout(btn_row)

        self.btn_cancel.clicked.connect(self.reject)
        self.btn_apply.clicked.connect(self.accept)

        # P2 (issue 6): если все diffs — failed и команд нет, применять
        # нечего. Disable Apply, чтобы пользователь не нажал вхолостую.
        if self._diffs and not self._commands and all(d.status == "failed" for d in self._diffs):
            self.btn_apply.setEnabled(False)
            self.btn_apply.setToolTip(
                "Все изменения помечены как failed — применять нечего. См. подробности в правой панели."
            )

    def _on_file_selected(self, row: int) -> None:
        if row < 0:
            self.diff_view.clear()
            return
        if row < len(self._diffs):
            d = self._diffs[row]
            if not d.unified_diff:
                self.diff_view.setPlainText("(пустой diff)")
                return
            self.diff_view.setHtml(_diff_to_html(d.unified_diff))
            return
        cmd_idx = row - len(self._diffs)
        if cmd_idx < 0 or cmd_idx >= len(self._commands):
            self.diff_view.clear()
            return
        c = self._commands[cmd_idx]
        lines = [
            f"$ {c.command}",
            "",
            f"timeout: {c.timeout_sec}s",
            f"on_failure: {c.on_failure}",
        ]
        if c.output_path:
            lines.append(f"output_path: {c.output_path}")
        else:
            lines.append("output_path: (не сохраняется)")
        self.diff_view.setPlainText("\n".join(lines))
