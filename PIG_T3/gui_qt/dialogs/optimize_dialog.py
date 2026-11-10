"""OptimizeDialog — параметры оптимизации контекста (T-109).

Форма: описание задачи, процент сжатия (слайдер 1–100), BFS-глубина,
выбор LLM-модели. При OK сохраняет `opt_default_model` и
`opt_compression_pct` в переданный settings-dict.

Не запускает оптимизацию — это делает OptimizeWorker (T-110).

Публичный интерфейс:
- ``OptimizeDialog(settings, total_tokens, parent=None, models=None)``
- ``get_task() -> str`` — описание задачи (stripped)
- ``get_limit_tokens() -> int`` — total_tokens * pct / 100
- ``get_depth() -> int`` — BFS-глубина
- ``get_model() -> str`` — выбранная модель
- ``get_updated_settings() -> dict`` — settings с обновлёнными opt_*

Модели по умолчанию — из ``get_installed_models()`` (Ollama) +
фиксированный список Web/BomjAPI. В тестах передаётся ``models`` явно,
чтобы не дёргать Ollama.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QThread
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSlider,
    QSpinBox,
    QVBoxLayout,
)

from ..workers.ollama_models_worker import (
    OllamaModelsWorker,
    cache_is_fresh,
    get_cached_models,
    save_models_to_cache,
)


def _show_warning_dialog(parent, title: str, text: str) -> None:
    """Обёртка над QMessageBox.warning (см. ADR-008 обёрток)."""
    QMessageBox.warning(parent, title, text)


def _default_models() -> list[str]:
    """None + BomjAPI + Web-модели. Ollama — отдельно, асинхронно."""
    return [
        "None",
        "BomjAPI",
        "Web: Gemini",
        "Web: DeepSeek",
        "Web: DeepSeek (DeepThink)",
        "Web: DeepSeek Expert",
        "Web: DeepSeek Expert (DeepThink)",
    ]


class OptimizeDialog(QDialog):
    """Диалог «✨ Оптимизация контекста»."""

    def __init__(
        self,
        settings: dict,
        total_tokens: int,
        parent=None,
        models: list[str] | None = None,
        auto_fetch_models: bool = True,
    ):
        super().__init__(parent)
        self.settings = dict(settings)
        self.total_tokens = max(1, int(total_tokens))
        explicit_models = models is not None
        if explicit_models:
            self._models = list(models)
        else:
            base = _default_models()
            cached = get_cached_models(self.settings)
            for m in cached:
                if m not in base:
                    base.append(m)
            self._models = base

        self._models_thread: QThread | None = None
        self._models_worker: OllamaModelsWorker | None = None

        self._setup_ui()
        self._populate()
        self._connect_signals()
        self._update_estimate()

        # Если models переданы явно — caller контролирует список,
        # воркер не нужен (важно для тестов: не дёргаем Ollama в фоне).
        if not explicit_models and auto_fetch_models and not cache_is_fresh(self.settings):
            self._fetch_models_async()

    # ---------- UI ----------

    def _setup_ui(self) -> None:
        self.setWindowTitle("Оптимизация контекста")
        self.setMinimumSize(520, 540)

        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("Описание задачи (на русском или английском):"))
        self.task_edit = QPlainTextEdit()
        self.task_edit.setMinimumHeight(100)
        self.task_edit.setPlaceholderText("Например: добавить экспорт в CSV и покрыть тестами")
        layout.addWidget(self.task_edit)

        layout.addWidget(QLabel("Процент сжатия (оставить % объёма):"))
        pct_row = QHBoxLayout()
        self.pct_slider = QSlider(Qt.Orientation.Horizontal)
        self.pct_slider.setRange(1, 100)
        self.pct_value_label = QLabel("")
        self.pct_value_label.setMinimumWidth(48)
        self.pct_value_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        pct_row.addWidget(self.pct_slider, 1)
        pct_row.addWidget(self.pct_value_label)
        layout.addLayout(pct_row)

        self.estimate_label = QLabel("")
        layout.addWidget(self.estimate_label)

        layout.addWidget(QLabel("Глубина BFS обхода графа зависимостей:"))
        self.depth_spin = QSpinBox()
        self.depth_spin.setRange(1, 5)
        layout.addWidget(self.depth_spin)

        layout.addWidget(QLabel("Модель LLM:"))
        self.model_combo = QComboBox()
        self.model_combo.addItems(self._models)
        layout.addWidget(self.model_combo)

        layout.addStretch(1)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        self.btn_cancel = QPushButton("Отмена")
        self.btn_start = QPushButton("🚀 НАЧАТЬ ОПТИМИЗАЦИЮ")
        self.btn_start.setDefault(True)
        self.btn_start.setMinimumHeight(32)
        btn_row.addWidget(self.btn_cancel)
        btn_row.addWidget(self.btn_start)
        layout.addLayout(btn_row)

    def _populate(self) -> None:
        self.pct_slider.setValue(int(self.settings.get("opt_compression_pct", 50)))
        self.depth_spin.setValue(int(self.settings.get("opt_bfs_depth", 2)))

        current_model = self.settings.get("opt_default_model", "BomjAPI")
        idx = self.model_combo.findText(current_model)
        if idx >= 0:
            self.model_combo.setCurrentIndex(idx)
        elif self._models:
            self.model_combo.setCurrentIndex(0)

    def _connect_signals(self) -> None:
        self.pct_slider.valueChanged.connect(self._update_estimate)
        self.btn_start.clicked.connect(self._on_start)
        self.btn_cancel.clicked.connect(self.reject)

    def _update_estimate(self) -> None:
        pct = self.pct_slider.value()
        self.pct_value_label.setText(f"{pct}%")
        tokens = max(1, int(self.total_tokens * (pct / 100.0)))
        self.estimate_label.setText(f"Ожидаемо токенов: ~{tokens} (из ~{self.total_tokens})")

    def _fetch_models_async(self) -> None:
        if self._models_thread is not None:
            return
        self._models_worker = OllamaModelsWorker()
        self._models_thread = QThread(self)
        self._models_worker.moveToThread(self._models_thread)
        self._models_thread.started.connect(self._models_worker.run)
        self._models_worker.done.connect(self._on_models_fetched)
        self._models_worker.error.connect(self._on_models_error)
        for sig in (self._models_worker.done, self._models_worker.error):
            sig.connect(self._cleanup_models_thread)
        self._models_thread.start()

    def _on_models_fetched(self, models: list) -> None:
        save_models_to_cache(self.settings, models)
        current = self.model_combo.currentText()
        existing = {self.model_combo.itemText(i) for i in range(self.model_combo.count())}
        for m in models:
            if m not in existing:
                self.model_combo.addItem(m)
        idx = self.model_combo.findText(current)
        if idx >= 0:
            self.model_combo.setCurrentIndex(idx)

    def _on_models_error(self, _msg: str) -> None:
        # Ollama не запущена — молча, у пользователя остаются base-модели
        pass

    def _cleanup_models_thread(self, *_args) -> None:
        thread = self._models_thread
        self._models_thread = None
        self._models_worker = None
        if thread is not None:
            try:
                thread.quit()
                thread.wait(3000)
            except RuntimeError:
                pass

    def closeEvent(self, event) -> None:
        self._cleanup_models_thread()
        super().closeEvent(event)

    def _on_start(self) -> None:
        task = self.task_edit.toPlainText().strip()
        if not task:
            _show_warning_dialog(self, "Внимание", "Опишите задачу!")
            return
        self.settings["opt_default_model"] = self.model_combo.currentText()
        self.settings["opt_compression_pct"] = self.pct_slider.value()
        self.settings["opt_bfs_depth"] = self.depth_spin.value()
        self.accept()

    # ---------- Public ----------

    def get_task(self) -> str:
        return self.task_edit.toPlainText().strip()

    def get_limit_tokens(self) -> int:
        pct = self.pct_slider.value()
        return max(1, int(self.total_tokens * (pct / 100.0)))

    def get_depth(self) -> int:
        return self.depth_spin.value()

    def get_model(self) -> str:
        return self.model_combo.currentText()

    def get_updated_settings(self) -> dict:
        return dict(self.settings)
