"""NewPlanDialog — ввод концепции для генерации плана (T-405)."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)


def _show_warning(parent, title: str, text: str) -> None:
    QMessageBox.warning(parent, title, text)


class NewPlanDialog(QDialog):
    def __init__(self, models: list[str], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Новый план")
        self.setMinimumSize(600, 480)
        self._setup_ui(models)

    def _setup_ui(self, models: list[str]) -> None:
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Введите концепцию (задачу) проекта:"))
        self.concept_edit = QPlainTextEdit()
        self.concept_edit.setPlaceholderText("Например: CLI-утилита для конвертации CSV в JSON с тестами")
        layout.addWidget(self.concept_edit, 1)

        layout.addWidget(QLabel("Модель LLM:"))
        self.model_combo = QComboBox()
        self.model_combo.addItems(models)
        layout.addWidget(self.model_combo)

        btns = QHBoxLayout()
        btns.addStretch(1)
        self.btn_cancel = QPushButton("Отмена")
        self.btn_create = QPushButton("Создать план")
        self.btn_create.setDefault(True)
        btns.addWidget(self.btn_cancel)
        btns.addWidget(self.btn_create)
        layout.addLayout(btns)

        self.btn_cancel.clicked.connect(self.reject)
        self.btn_create.clicked.connect(self._on_create)

    def _on_create(self) -> None:
        if not self.get_concept():
            _show_warning(self, "Внимание", "Введите концепцию!")
            return
        if self.get_model() in ("", "None"):
            _show_warning(self, "Внимание", "Выберите модель LLM!")
            return
        self.accept()

    def get_concept(self) -> str:
        return self.concept_edit.toPlainText().strip()

    def get_model(self) -> str:
        return self.model_combo.currentText()
