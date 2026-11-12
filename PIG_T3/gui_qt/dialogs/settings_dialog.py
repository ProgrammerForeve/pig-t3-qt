"""SettingsDialog — настройки приложения (T-601..T-603).

Две вкладки:
- Внешний вид: тема, размер шрифта, высота строк, размер чекбоксов,
  лимит чанка оптимизации.
- Функционал: BFS-глубина, веса greedy, байт на токен, видимость
  вкладок, Git-интеграция, параметры LLM.

При сохранении модифицирует переданный settings-dict in-place и
возвращает через ``get_updated_settings()``. Применение без
перезапуска — задача MainWindow (apply_theme + apply_row_height +
apply_tab_visibility).
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

_VALID_THEMES = ["dark", "light"]


class SettingsDialog(QDialog):
    def __init__(self, settings: dict, parent=None):
        super().__init__(parent)
        self._settings = dict(settings)
        self._setup_ui()
        self._populate()
        self._connect_signals()

    # ---------- UI ----------

    def _setup_ui(self) -> None:
        self.setWindowTitle("Настройки")
        self.setMinimumSize(560, 640)

        layout = QVBoxLayout(self)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_appearance_tab(), "🎨 Внешний вид")
        self.tabs.addTab(self._build_functional_tab(), "⚙️ Функционал")
        layout.addWidget(self.tabs, 1)

        btns = QHBoxLayout()
        btns.addStretch(1)
        self.btn_cancel = QPushButton("Отмена")
        self.btn_save = QPushButton("Сохранить")
        self.btn_save.setDefault(True)
        btns.addWidget(self.btn_cancel)
        btns.addWidget(self.btn_save)
        layout.addLayout(btns)

    def _build_appearance_tab(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)

        self.theme_combo = QComboBox()
        self.theme_combo.addItems(_VALID_THEMES)
        form.addRow("Тема оформления:", self.theme_combo)

        self.font_size_spin = QSpinBox()
        self.font_size_spin.setRange(8, 24)
        form.addRow("Размер шрифта (UI):", self.font_size_spin)

        self.row_height_spin = QSpinBox()
        self.row_height_spin.setRange(12, 60)
        form.addRow("Интервал строк (px):", self.row_height_spin)

        self.checkbox_size_spin = QSpinBox()
        self.checkbox_size_spin.setRange(10, 40)
        form.addRow("Размер галочек (px):", self.checkbox_size_spin)

        chunk_row = QWidget()
        chunk_layout = QHBoxLayout(chunk_row)
        chunk_layout.setContentsMargins(0, 0, 0, 0)
        self.opt_chunk_spin = QSpinBox()
        self.opt_chunk_spin.setRange(100, 100_000)
        self.opt_unit_combo = QComboBox()
        self.opt_unit_combo.addItems(["chars", "tokens", "lines"])
        chunk_layout.addWidget(self.opt_chunk_spin, 1)
        chunk_layout.addWidget(self.opt_unit_combo)
        form.addRow("Лимит чанка оптимизации:", chunk_row)

        return w

    def _build_functional_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)

        opt_group = QGroupBox("Параметры контекстного оптимизатора")
        opt_form = QFormLayout(opt_group)

        self.bfs_depth_spin = QSpinBox()
        self.bfs_depth_spin.setRange(1, 10)
        opt_form.addRow("Глубина BFS:", self.bfs_depth_spin)

        weights_row = QWidget()
        weights_layout = QHBoxLayout(weights_row)
        weights_layout.setContentsMargins(0, 0, 0, 0)
        self.llm_weight_spin = QDoubleSpinBox()
        self.llm_weight_spin.setRange(0.0, 1.0)
        self.llm_weight_spin.setSingleStep(0.05)
        self.pr_weight_spin = QDoubleSpinBox()
        self.pr_weight_spin.setRange(0.0, 1.0)
        self.pr_weight_spin.setSingleStep(0.05)
        self.cc_weight_spin = QDoubleSpinBox()
        self.cc_weight_spin.setRange(0.0, 1.0)
        self.cc_weight_spin.setSingleStep(0.05)
        for label, spin in (
            ("LLM", self.llm_weight_spin),
            ("PageRank", self.pr_weight_spin),
            ("CC", self.cc_weight_spin),
        ):
            weights_layout.addWidget(QLabel_like(label))
            weights_layout.addWidget(spin)
        opt_form.addRow("Веса отбора:", weights_row)

        self.bytes_per_token_spin = QSpinBox()
        self.bytes_per_token_spin.setRange(1, 10)
        opt_form.addRow("Байт на токен:", self.bytes_per_token_spin)
        layout.addWidget(opt_group)

        behavior_group = QGroupBox("Поведение")
        behavior_layout = QVBoxLayout(behavior_group)
        self.auto_refresh_cb = QCheckBox("Авто-обновление дерева при изменении файлов")
        behavior_layout.addWidget(self.auto_refresh_cb)
        layout.addWidget(behavior_group)

        cmd_group = QGroupBox("Выполнение команд (AI может запускать)")
        cmd_layout = QVBoxLayout(cmd_group)
        self.allow_cmd_cb = QCheckBox("Разрешить выполнение команд из JSON-патча")
        self.allow_cmd_cb.setToolTip(
            "AI сможет выполнять shell-команды (pytest, ruff, git) "
            "и складывать вывод в файлы. ВНИМАНИЕ: эквивалентно "
            "выполнению произвольного кода из ответа LLM."
        )
        cmd_layout.addWidget(self.allow_cmd_cb)
        self.confirm_cmd_cb = QCheckBox("Подтверждать команды в редакторе")
        self.confirm_cmd_cb.setToolTip("Показывать список команд в диалоге diff перед применением.")
        cmd_layout.addWidget(self.confirm_cmd_cb)

        lmstudio_group = QGroupBox("LM Studio (OpenAI-совместимый)")
        lmstudio_form = QFormLayout(lmstudio_group)
        self.lmstudio_url_edit = QLineEdit()
        self.lmstudio_url_edit.setPlaceholderText("http://localhost:1234/v1")
        lmstudio_form.addRow("Base URL:", self.lmstudio_url_edit)
        self.lmstudio_key_edit = QLineEdit()
        self.lmstudio_key_edit.setPlaceholderText("lm-studio")
        lmstudio_form.addRow("API key:", self.lmstudio_key_edit)
        self.lmstudio_timeout_spin = QSpinBox()
        self.lmstudio_timeout_spin.setRange(1, 3600)
        self.lmstudio_timeout_spin.setSuffix(" сек")
        lmstudio_form.addRow("Таймаут:", self.lmstudio_timeout_spin)
        self.lmstudio_embeddings_edit = QLineEdit()
        self.lmstudio_embeddings_edit.setPlaceholderText("например nomic-embed-text-v1.5 (пусто = авто)")
        lmstudio_form.addRow("Embeddings модель:", self.lmstudio_embeddings_edit)
        layout.addWidget(lmstudio_group)

        cmd_row = QFormLayout()
        self.cmd_timeout_spin = QSpinBox()
        self.cmd_timeout_spin.setRange(1, 3600)
        self.cmd_timeout_spin.setSuffix(" сек")
        cmd_row.addRow("Таймаут по умолчанию:", self.cmd_timeout_spin)
        self.cmd_whitelist_edit = QLineEdit()
        self.cmd_whitelist_edit.setPlaceholderText("pytest,ruff,mypy (пусто = все разрешены)")
        cmd_row.addRow("Whitelist:", self.cmd_whitelist_edit)
        cmd_layout.addLayout(cmd_row)
        layout.addWidget(cmd_group)

        cmd_row = QFormLayout()
        self.cmd_timeout_spin = QSpinBox()
        self.cmd_timeout_spin.setRange(1, 3600)
        self.cmd_timeout_spin.setSuffix(" сек")
        cmd_row.addRow("Таймаут по умолчанию:", self.cmd_timeout_spin)
        self.cmd_whitelist_edit = QLineEdit()
        self.cmd_whitelist_edit.setPlaceholderText("pytest,ruff,mypy (пусто = все разрешены)")
        cmd_row.addRow("Whitelist:", self.cmd_whitelist_edit)
        cmd_layout.addLayout(cmd_row)
        layout.addWidget(cmd_group)

        vis_group = QGroupBox("Отображение вкладок")
        vis_layout = QVBoxLayout(vis_group)
        self.vis_checks: dict[str, QCheckBox] = {
            "generator": QCheckBox("🏠 Генератор"),
            "info": QCheckBox("🎓 Инфо / JSON Specs"),
            "editor": QCheckBox("✏️ Редактор (JSON Patcher)"),
            "plan": QCheckBox("📝 План проекта"),
            "quality": QCheckBox("📊 Анализ кода"),
        }
        for cb in self.vis_checks.values():
            vis_layout.addWidget(cb)
        layout.addWidget(vis_group)

        git_group = QGroupBox("🐙 Git интеграция")
        git_form = QFormLayout(git_group)
        self.git_enabled_cb = QCheckBox("Включить авто-коммиты")
        git_form.addRow(self.git_enabled_cb)
        self.git_branch_combo = QComboBox()
        self.git_branch_combo.addItems(["new", "current"])
        git_form.addRow("Режим веток:", self.git_branch_combo)
        self.git_push_cb = QCheckBox("Push после каждого шага")
        git_form.addRow(self.git_push_cb)
        layout.addWidget(git_group)

        llm_group = QGroupBox("⚙️ Параметры LLM")
        llm_form = QFormLayout(llm_group)
        self.llm_timeout_spin = QSpinBox()
        self.llm_timeout_spin.setRange(30, 3600)
        llm_form.addRow("Таймаут Web API (сек):", self.llm_timeout_spin)
        self.llm_stable_spin = QSpinBox()
        self.llm_stable_spin.setRange(1, 30)
        llm_form.addRow("Стабильность ответа (сек):", self.llm_stable_spin)
        self.plan_step_tokens_spin = QSpinBox()
        self.plan_step_tokens_spin.setRange(1000, 200_000)
        llm_form.addRow("Лимит токенов для шага:", self.plan_step_tokens_spin)
        self.plan_gen_tokens_spin = QSpinBox()
        self.plan_gen_tokens_spin.setRange(1000, 200_000)
        llm_form.addRow("Лимит токенов для плана:", self.plan_gen_tokens_spin)
        self.quality_chunk_spin = QSpinBox()
        self.quality_chunk_spin.setRange(10, 500)
        llm_form.addRow("Размер чанка анализа:", self.quality_chunk_spin)
        layout.addWidget(llm_group)

        return w

    def _populate(self) -> None:
        s = self._settings

        theme = s.get("theme", "dark")
        if theme not in _VALID_THEMES:
            theme = "dark"
        self.theme_combo.setCurrentText(theme)

        self.font_size_spin.setValue(int(s.get("font_size", 10)))
        self.row_height_spin.setValue(int(s.get("tree_row_height", 28)))
        self.checkbox_size_spin.setValue(int(s.get("checkbox_size", 14)))
        self.opt_chunk_spin.setValue(int(s.get("opt_chunk_size", 7000)))
        unit = s.get("opt_chunk_unit", "tokens")
        if unit in ("chars", "tokens", "lines"):
            self.opt_unit_combo.setCurrentText(unit)

        self.bfs_depth_spin.setValue(int(s.get("opt_bfs_depth", 2)))
        self.llm_weight_spin.setValue(float(s.get("opt_greedy_llm_weight", 0.6)))
        self.pr_weight_spin.setValue(float(s.get("opt_greedy_pr_weight", 0.3)))
        self.cc_weight_spin.setValue(float(s.get("opt_greedy_cc_weight", 0.1)))
        self.bytes_per_token_spin.setValue(int(s.get("opt_token_bytes_per_token", 4)))
        self.auto_refresh_cb.setChecked(bool(s.get("auto_refresh_tree", True)))
        self.allow_cmd_cb.setChecked(bool(s.get("allow_command_execution", False)))
        self.confirm_cmd_cb.setChecked(bool(s.get("command_confirm_in_editor", True)))
        self.cmd_timeout_spin.setValue(int(s.get("command_default_timeout", 120)))
        self.cmd_whitelist_edit.setText(s.get("command_whitelist", ""))
        self.lmstudio_url_edit.setText(s.get("lmstudio_base_url", "http://localhost:1234/v1"))
        self.lmstudio_key_edit.setText(s.get("lmstudio_api_key", "lm-studio"))
        self.lmstudio_timeout_spin.setValue(int(s.get("lmstudio_timeout", 600)))
        self.lmstudio_embeddings_edit.setText(s.get("lmstudio_embeddings_model", ""))

        vis = s.get("tabs_visibility", {})
        for key, cb in self.vis_checks.items():
            cb.setChecked(vis.get(key, True))

        self.git_enabled_cb.setChecked(bool(s.get("git_enabled", False)))
        mode = s.get("git_branch_mode", "new")
        if mode in ("new", "current"):
            self.git_branch_combo.setCurrentText(mode)
        self.git_push_cb.setChecked(bool(s.get("git_auto_push", False)))

        self.llm_timeout_spin.setValue(int(s.get("web_api_timeout", 600)))
        self.llm_stable_spin.setValue(int(s.get("web_api_stable_count", 7)))
        self.plan_step_tokens_spin.setValue(int(s.get("plan_step_limit_tokens", 15000)))
        self.plan_gen_tokens_spin.setValue(int(s.get("plan_generation_limit_tokens", 12000)))
        self.quality_chunk_spin.setValue(int(s.get("quality_scan_chunk_size", 50)))

    def _connect_signals(self) -> None:
        self.btn_save.clicked.connect(self._on_save)
        self.btn_cancel.clicked.connect(self.reject)

    def _on_save(self) -> None:
        s = self._settings
        s["theme"] = self.theme_combo.currentText()
        s["font_size"] = self.font_size_spin.value()
        s["tree_row_height"] = self.row_height_spin.value()
        s["checkbox_size"] = self.checkbox_size_spin.value()
        s["opt_chunk_size"] = self.opt_chunk_spin.value()
        s["opt_chunk_unit"] = self.opt_unit_combo.currentText()

        s["opt_bfs_depth"] = self.bfs_depth_spin.value()
        s["opt_greedy_llm_weight"] = self.llm_weight_spin.value()
        s["opt_greedy_pr_weight"] = self.pr_weight_spin.value()
        s["opt_greedy_cc_weight"] = self.cc_weight_spin.value()
        s["opt_token_bytes_per_token"] = self.bytes_per_token_spin.value()
        s["auto_refresh_tree"] = self.auto_refresh_cb.isChecked()
        s["allow_command_execution"] = self.allow_cmd_cb.isChecked()
        s["command_confirm_in_editor"] = self.confirm_cmd_cb.isChecked()
        s["command_default_timeout"] = self.cmd_timeout_spin.value()
        s["command_whitelist"] = self.cmd_whitelist_edit.text().strip()
        s["lmstudio_base_url"] = self.lmstudio_url_edit.text().strip() or "http://localhost:1234/v1"
        s["lmstudio_api_key"] = self.lmstudio_key_edit.text().strip() or "lm-studio"
        s["lmstudio_timeout"] = self.lmstudio_timeout_spin.value()
        s["lmstudio_embeddings_model"] = self.lmstudio_embeddings_edit.text().strip()

        s["tabs_visibility"] = {key: cb.isChecked() for key, cb in self.vis_checks.items()}

        s["git_enabled"] = self.git_enabled_cb.isChecked()
        s["git_branch_mode"] = self.git_branch_combo.currentText()
        s["git_auto_push"] = self.git_push_cb.isChecked()

        s["web_api_timeout"] = self.llm_timeout_spin.value()
        s["web_api_stable_count"] = self.llm_stable_spin.value()
        s["plan_step_limit_tokens"] = self.plan_step_tokens_spin.value()
        s["plan_generation_limit_tokens"] = self.plan_gen_tokens_spin.value()
        s["quality_scan_chunk_size"] = self.quality_chunk_spin.value()

        self.accept()

    # ---------- Public ----------

    def get_updated_settings(self) -> dict:
        return dict(self._settings)


def QLabel_like(text: str) -> QWidget:
    """Мини-хелпер: QLabel без отдельного импорта в блоке."""
    from PySide6.QtWidgets import QLabel as _QL

    return _QL(text)
