"""BomjAPI — ручной ввод ответа LLM (Qt-версия, T-111a).

Публичный API совместим с legacy Tkinter-версией:
- ``BomjAPI(validators=...).send(payload, parent=None) -> str``
- ``get_data()``, ``save(path)``, ``load(path)``

Внутри — QDialog, блокирующий (exec()). Из worker-потоков
использовать через ``gui_qt.workers.llm_wrappers.BomjWrapper``:
он поднимает диалог в main-thread через bridge и разблокирует
worker по threading.Event.
"""
from __future__ import annotations

import os
import pickle

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QVBoxLayout,
)


class BomjAPI:
    """Ручной ввод ответа LLM через модальный диалог."""

    def __init__(self, validators=None):
        self.validators = validators
        self.data: dict[str, str] = {}
        self.last_response = ""

    # ---------- Payload parsing ----------

    def _parse_payload(self, payload) -> str:
        if isinstance(payload, str):
            return payload
        if "messages" in payload:
            parts = []
            for msg in payload["messages"]:
                role = msg.get("role", "Unknown")
                content = msg.get("content", "")
                parts.append(f"{role}:\n{content}")
            return "\n\n".join(parts)
        if "promt" in payload:
            return payload["promt"]
        if "prompt" in payload:
            return payload["prompt"]
        return "Empty prompt"

    def _get_validator(self, model_name: str):
        if callable(self.validators):
            return self.validators
        if isinstance(self.validators, dict):
            return self.validators.get(model_name)
        return None

    # ---------- Dialog ----------

    def _build_dialog(self, parent, model: str, prompt_text: str, validator):
        dlg = QDialog(parent)
        dlg.setWindowTitle(f"Request to {model}")
        dlg.resize(900, 560)

        layout = QVBoxLayout(dlg)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(splitter, 1)

        # --- Левая половина: промпт (read-only) ---
        left = QLabel("PROMPT TEXT (ТУТ ТЕКСТ ПРОМПТА)")
        left_widget = QDialog()
        left_widget_layout = QVBoxLayout(left_widget)
        left_widget_layout.setContentsMargins(0, 0, 0, 0)
        left_widget_layout.addWidget(left)

        prompt_edit = QPlainTextEdit()
        prompt_edit.setPlainText(prompt_text)
        prompt_edit.setReadOnly(True)
        left_widget_layout.addWidget(prompt_edit, 1)

        btn_copy_prompt = QPushButton("COPY (СКОПИРОВАТЬ)")

        def _copy_prompt():
            QApplication.clipboard().setText(prompt_text)
            QMessageBox.information(dlg, "Copied", "Prompt copied to clipboard!")

        btn_copy_prompt.clicked.connect(_copy_prompt)
        left_widget_layout.addWidget(btn_copy_prompt)
        splitter.addWidget(left_widget)

        # --- Правая половина: ответ ---
        right_widget = QDialog()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.addWidget(QLabel("RESPONSE TEXT (ТУТ ТЕКСТ ОТВЕТА)"))

        response_edit = QPlainTextEdit()
        right_layout.addWidget(response_edit, 1)
        response_edit.setFocus()

        btn_row = QHBoxLayout()
        btn_paste = QPushButton("PASTE (ВСТАВИТЬ)")

        def _paste():
            text = QApplication.clipboard().text()
            if text:
                response_edit.insertPlainText(text)

        btn_paste.clicked.connect(_paste)
        btn_row.addWidget(btn_paste)

        btn_check = None
        if validator is not None:
            btn_check = QPushButton("CHECK (ПРОВЕРИТЬ)")

            def _check():
                current = response_edit.toPlainText().strip()
                if validator(current):
                    btn_check.setStyleSheet("background: lightgreen")
                else:
                    btn_check.setStyleSheet("background: salmon")
                    QMessageBox.warning(
                        dlg, "Validation Failed", "The response did not pass validation!"
                    )

            btn_check.clicked.connect(_check)
            btn_row.addWidget(btn_check)

        btn_accept = QPushButton("▶ ACCEPT (ПРИНЯТЬ)")

        def _accept():
            current = response_edit.toPlainText().strip()
            if current == self.last_response and current != "":
                if not self._ask_yes_no(
                    dlg,
                    "Duplicate Match",
                    "This response is exactly the same as the previous one.\n"
                    "Are you sure you want to proceed?",
                ):
                    return
            if validator is not None and not validator(current):
                if not self._ask_yes_no(
                    dlg,
                    "Warning",
                    "The response does not meet the criteria (validation failed).\n"
                    "Proceed anyway?",
                ):
                    return
                if not self._ask_yes_no(
                    dlg,
                    "Are you sure?",
                    "Are you absolutely sure you want to submit an invalid response?",
                ):
                    return
            dlg._result = current
            dlg.accept()

        btn_accept.clicked.connect(_accept)
        btn_row.addStretch(1)
        btn_row.addWidget(btn_accept)
        right_layout.addLayout(btn_row)
        splitter.addWidget(right_widget)

        dlg._result = None
        return dlg

    @staticmethod
    def _ask_yes_no(parent, title: str, text: str) -> bool:
        from PySide6.QtWidgets import QMessageBox as _MB

        result = _MB.question(
            parent,
            title,
            text,
            _MB.StandardButton.Yes | _MB.StandardButton.No,
            _MB.StandardButton.No,
        )
        return result == _MB.StandardButton.Yes

    # ---------- Public ----------

    def send(self, payload, parent=None) -> str:
        if isinstance(payload, str):
            payload = {"model": "Standard", "promt": payload}

        model = payload.get("model", "Unknown_Model")
        prompt_text = self._parse_payload(payload)
        validator = self._get_validator(model)

        dlg = self._build_dialog(parent, model, prompt_text, validator)
        try:
            code = dlg.exec()
        finally:
            dlg.deleteLater()

        if code != QDialog.DialogCode.Accepted:
            return ""
        result = dlg._result or ""
        self.last_response = result
        self.data[prompt_text] = result
        return result

    def get_data(self) -> dict[str, str]:
        return self.data

    def save(self, filepath: str = "bomj_data.pkl") -> None:
        with open(filepath, "wb") as f:
            pickle.dump(self.data, f)

    def load(self, filepath: str = "bomj_data.pkl") -> None:
        if os.path.exists(filepath):
            with open(filepath, "rb") as f:
                self.data = pickle.load(f)  # noqa: S301 — доверенный локальный файл
