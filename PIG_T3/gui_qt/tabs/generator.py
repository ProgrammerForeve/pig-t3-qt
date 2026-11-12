"""Вкладка «Генератор» — каркас (T-101..T-103) + дерево (T-105..T-106).

Публичный интерфейс:
- ``GeneratorTab(settings: dict)``
- ``collect_settings() -> dict``
- ``commit_recent_projects()`` — recent_projects + completer refresh
- ``refresh_tree()`` — сканировать и пересобрать дерево (state сохраняется
  между вызовами, если root не изменился)
- ``set_tree_data(files)`` — пересобрать дерево из явного списка (тесты)
- ``capture_tree_state() -> dict``
- ``settings_changed`` (Signal)
"""

from __future__ import annotations

import contextlib
import logging
import os
import sys

from PySide6.QtCore import (
    QModelIndex,
    QStringListModel,
    Qt,
    QThread,
    QTimer,
    Signal,
)
from PySide6.QtWidgets import (
    QCheckBox,
    QCompleter,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ...core.analyzer import ProjectAnalyzer
from ...utils.clipboard import copy_file_to_clipboard_windows
from ..dialogs.optimize_dialog import OptimizeDialog
from ..models.project_tree import ProjectTreeModel
from ..widgets.file_watcher import FileWatcher
from ..widgets.project_tree_view import ProjectTreeView
from ..widgets.recent_menu import RecentProjectsMenu
from ..workers.generate_worker import GenerateWorker
from ..workers.llm_wrappers import make_llm_client
from ..workers.optimize_worker import OptimizeWorker

_RECENT_PROJECTS_LIMIT = 10
_TREE_REFRESH_DELAY_MS = 600

log = logging.getLogger("pig_t3.generator")


def _show_info_dialog(parent, title: str, text: str) -> None:
    """Обёртка над QMessageBox.information.

    Вынесена на уровень модуля, чтобы тесты могли подменить её через
    monkeypatch.setattr(generator_module, '_show_info_dialog', ...) без
    патчинга shiboken-статик-метода QMessageBox (это ломает внутренние
    кэши PySide6 и приводит к heap corruption).
    """
    QMessageBox.information(parent, title, text)


def _show_critical_dialog(parent, title: str, text: str) -> None:
    """Обёртка над QMessageBox.critical (см. _show_info_dialog)."""
    QMessageBox.critical(parent, title, text)


class GeneratorTab(QWidget):
    """Каркас вкладки «Генератор»."""

    settings_changed = Signal()
    generation_finished = Signal(str, int, int, int)
    generation_cancelled = Signal()
    generation_error = Signal(str)

    def __init__(self, settings: dict):
        super().__init__()
        self.settings = settings
        self.analyzer = ProjectAnalyzer()
        self._last_root = None
        self._gen_thread: QThread | None = None
        self._gen_worker: GenerateWorker | None = None
        self._watcher = FileWatcher(debounce_ms=1500, parent=self)
        self._watcher.changes_detected.connect(self._on_files_changed)
        # FIX crash: счётчик для idempotent pause/resume (Editor зовёт
        # pause из _on_preview и _on_apply, resume — из cleanup'ов).
        self._watcher_pause_count: int = 0
        # FIX segfault: пауза watcher вокруг Editor apply/undo/redo
        # и защита от refresh во время модальных диалогов.
        self._watcher_paused: bool = False
        self._opt_thread: QThread | None = None
        self._opt_worker: OptimizeWorker | None = None

        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.setInterval(_TREE_REFRESH_DELAY_MS)
        self._refresh_timer.timeout.connect(self.refresh_tree)

        # Deferred-таймер для восстановления раскрытых папок.
        # QTimer.singleShot(0, lambda: ...) держит self через лямбду,
        # которая может выстрелить уже после уничтожения C++ QTreeView
        # (например, при teardown в pytest-qt). Атрибутный QTimer(self)
        # уничтожается вместе с self — timeout не сработает на мёртвом
        # C++ объекте.
        self._pending_expanded_restore: list[str] = []
        self._restore_expanded_timer = QTimer(self)
        self._restore_expanded_timer.setSingleShot(True)
        self._restore_expanded_timer.setInterval(0)
        self._restore_expanded_timer.timeout.connect(self._on_restore_expanded_timer)

        self._setup_ui()
        self._populate(settings)
        self._connect_signals()
        self.refresh_tree()
        self._refresh_recent_menu()
        if self.cb_sort_by_size.isChecked():
            self.tree_model.set_sort_mode("size")

        # Restore unchecked synchronously — set_unchecked_paths only
        # emits dataChanged, no persistent indices, safe right after
        # reset_data.
        unchecked = self.settings.get("ui_tree_unchecked", [])
        if unchecked:
            self.tree_model.set_unchecked_paths(unchecked)

        # Restore expanded DEFERRED — setExpanded creates persistent
        # indices in QTreeView. Calling it synchronously right after
        # endResetModel can corrupt view internals on some Qt versions.
        expanded = self.settings.get("ui_tree_expanded", [])
        if expanded:
            self._schedule_expanded_restore(expanded)

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
        self.btn_recent = QToolButton()
        self.btn_recent.setText("📁")
        self.btn_recent.setToolTip("Недавние проекты")
        self.btn_recent.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.recent_menu = RecentProjectsMenu(self)
        self.btn_recent.setMenu(self.recent_menu)
        self.btn_browse = QPushButton("Обзор…")
        self.btn_auto = QPushButton("Авто")
        path_layout.addWidget(self.path_edit, 0, 0)
        path_layout.addWidget(self.btn_recent, 0, 1)
        path_layout.addWidget(self.btn_browse, 0, 2)
        path_layout.addWidget(self.btn_auto, 0, 3)
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
        self.btn_all_ext = QPushButton("Все")
        self.btn_all_ext.setToolTip("Собрать все уникальные расширения из проекта и подставить в поле")
        self.btn_all_ext.setMaximumWidth(60)
        ext_row = QHBoxLayout()
        ext_row.setContentsMargins(0, 0, 0, 0)
        ext_row.addWidget(self.ext_edit, 1)
        ext_row.addWidget(self.btn_all_ext)
        fields_layout.addLayout(ext_row, 1, 0)
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
        options_grid = QGridLayout(self.options_widget)
        options_grid.setContentsMargins(20, 0, 0, 0)
        options_grid.setHorizontalSpacing(20)
        options_grid.setVerticalSpacing(2)
        self.cb_include_empty = QCheckBox("Включить в отчёт пустые папки")
        self.cb_add_edit_prompt = QCheckBox("Добавить инструкцию для AI (JSON Format)")
        self.cb_include_plan = QCheckBox("Добавить текущий план к отчёту")
        self.cb_line_numbers = QCheckBox("Нумеровать строки (для точного редактирования)")
        self.cb_auto_copy = QCheckBox("Авто-копировать ФАЙЛ в буфер (для вставки в чат)")
        self.cb_sort_by_size = QCheckBox("🔽 Сортировать по размеру (большие сверху)")
        self.cb_sort_by_size.setToolTip(
            "Перестроить дерево по размеру файлов/папок и показать размеры. "
            "Влияет на визуализацию; содержимое отчёта не меняется."
        )

        _all_cbs = [*list(self._checkboxes()), self.cb_sort_by_size]
        for _i, _cb in enumerate(_all_cbs):
            _cb.setFixedHeight(24)
            options_grid.addWidget(_cb, _i // 3, _i % 3)

        self.options_widget.setFixedHeight(80)
        self.options_widget.setStyleSheet("QCheckBox { font-size: 9pt; }")
        layout.addWidget(self.options_widget)

        # --- Дерево проекта (T-105) ---
        tree_header = QHBoxLayout()
        tree_header.addWidget(QLabel("Структура проекта:"))
        tree_header.addStretch(1)
        self.btn_optimize = QPushButton("✨ Оптимизация контекста")
        tree_header.addWidget(self.btn_optimize)
        self.btn_refresh_tree = QPushButton("🔄 Обновить")
        tree_header.addWidget(self.btn_refresh_tree)
        layout.addLayout(tree_header)

        # Компактная высота строки из конфига (T-110 UI)
        row_h = int(self.settings.get("tree_row_height") or 0)
        if row_h > 0:
            self.tree_view = ProjectTreeView()
            self.tree_view.apply_row_height(row_h)
        else:
            self.tree_view = ProjectTreeView()

        # Чекбокс «Весь проект» (T-110 UI)
        select_row = QHBoxLayout()
        self.cb_select_all = QCheckBox("🌐 Весь проект")
        self.cb_select_all.setTristate(False)
        self.cb_select_all.setCheckState(Qt.CheckState.Checked)
        select_row.addWidget(self.cb_select_all)
        select_row.addStretch(1)
        layout.addLayout(select_row)

        self.tree_model = ProjectTreeModel("", [])
        self.tree_view.setModel(self.tree_model)
        # Issue 4 (P2): колонка размеров — setup после setModel.
        self.tree_view.setup_size_column()
        layout.addWidget(self.tree_view, 1)

        # --- Панель генерации (T-107) ---
        self.btn_generate = QPushButton("🚀 ГЕНЕРИРОВАТЬ КОНТЕКСТ")
        self.btn_generate.setMinimumHeight(36)
        self.btn_generate.clicked.connect(self._on_generate_clicked)
        layout.addWidget(self.btn_generate)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        self.status_label = QLabel("Готов к работе")
        layout.addWidget(self.status_label)

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
        self.cb_sort_by_size.setChecked(settings.get("sort_by_size", False))

    def _connect_signals(self) -> None:
        self.btn_browse.clicked.connect(self.browse_folder)
        self.btn_all_ext.clicked.connect(self._on_all_ext_clicked)
        self.recent_menu.project_selected.connect(self._on_recent_selected)
        self.recent_menu.recent_cleared.connect(self._on_recent_cleared)
        self.btn_auto.clicked.connect(self.auto_set_folder)
        self.btn_refresh_tree.clicked.connect(self.refresh_tree)
        self.btn_optimize.clicked.connect(self.open_optimization_dialog)
        self.cb_select_all.clicked.connect(self._on_select_all_clicked)
        self.cb_sort_by_size.toggled.connect(self._on_sort_by_size_toggled)
        self.tree_model.checkStateChanged.connect(self._sync_select_all_state)

        for edit in (self.path_edit, self.ext_edit, self.ignore_edit, self.output_edit):
            edit.textChanged.connect(self._on_field_changed)

        for cb in self._checkboxes():
            cb.toggled.connect(self._on_checkbox_toggled)

    def _on_field_changed(self, _text: str) -> None:
        self.settings_changed.emit()
        self._refresh_timer.start()

    def _on_checkbox_toggled(self, _checked: bool) -> None:
        self.settings_changed.emit()

    def _on_sort_by_size_toggled(self, checked: bool) -> None:
        self.tree_model.set_sort_mode("size" if checked else "name")
        self.settings_changed.emit()

    def _on_options_toggled(self, checked: bool) -> None:
        self.options_widget.setVisible(checked)
        self.options_toggle.setArrowType(Qt.ArrowType.DownArrow if checked else Qt.ArrowType.RightArrow)

    def open_optimization_dialog(self) -> None:
        """Открыть диалог оптимизации контекста и запустить воркер."""
        total_tokens = self._estimate_total_tokens()
        dlg = OptimizeDialog(self.settings, total_tokens, parent=self)
        if dlg.exec() == OptimizeDialog.DialogCode.Accepted:
            self.settings.update(dlg.get_updated_settings())
            self.settings_changed.emit()
            self._start_optimization(
                dlg.get_task(),
                dlg.get_limit_tokens(),
                dlg.get_depth(),
                dlg.get_model(),
            )

    def _estimate_total_tokens(self) -> int:
        """Issue 4: (размер дерева + системный промт) / token_bytes.

        Считаем размер ВСЕХ файлов дерева (не только .py, как legacy) —
        точнее для смешанных проектов. Системный промт добавляется,
        только если включён add_edit_prompt. Пустое дерево → 1000.
        """
        token_bytes = int(self.settings.get("opt_token_bytes_per_token", 4) or 4)
        if token_bytes <= 0:
            token_bytes = 4
        total_bytes = 0
        tree_bytes = self.tree_model.checked_size_bytes()
        if tree_bytes:
            total_bytes += tree_bytes
        if self.cb_add_edit_prompt.isChecked():
            total_bytes += self._system_prompt_bytes()
        if total_bytes == 0:
            return 1000
        return max(1, total_bytes // token_bytes)

    def _system_prompt_bytes(self) -> int:
        """Issue 4: размер системного промта (add_edit_prompt) в байтах."""
        import io

        try:
            from ...core.agent_context import (
                collect_environment,
                format_environment_block,
            )

            env_block = format_environment_block(collect_environment(self.path_edit.text().strip() or "."))
        except Exception:
            env_block = ""
        buf = io.StringIO()
        try:
            self.analyzer._write_patching_instructions(
                buf,
                line_numbers=self.cb_line_numbers.isChecked(),
                use_sharp_indent=self.settings.get("use_sharp_indent", False),
                env_block=env_block,
                custom_system_prompt=self.settings.get("custom_system_prompt", "") or "",
            )
        except Exception as e:
            log.warning("_system_prompt_bytes failed: %s", e)
            return 0
        return len(buf.getvalue().encode("utf-8"))

    # ---------- Optimization worker (T-110) ----------

    def _start_optimization(self, task: str, limit_tokens: int, depth: int, model: str) -> None:
        if self._opt_thread is not None or self._gen_thread is not None:
            return
        root = self.path_edit.text().strip()
        if not root or not os.path.isdir(root):
            self.status_label.setText("❌ Папка проекта не существует")
            return

        llm_client = make_llm_client(model, self, self.settings)
        use_rag = bool(self.settings.get("opt_use_rag", False))
        scan_config = {
            "extensions": self.ext_edit.text(),
            "ignore_list": self.ignore_edit.text(),
            "strict_mode": self.settings.get("strict_mode", False),
        }
        self._opt_worker = OptimizeWorker(
            root_folder=root,
            task=task,
            limit_tokens=limit_tokens,
            bfs_depth=depth,
            greedy_llm_weight=float(self.settings.get("opt_greedy_llm_weight", 0.6)),
            greedy_pr_weight=float(self.settings.get("opt_greedy_pr_weight", 0.3)),
            greedy_cc_weight=float(self.settings.get("opt_greedy_cc_weight", 0.1)),
            token_bytes_per_token=int(self.settings.get("opt_token_bytes_per_token", 4)),
            ignore_list=self.ignore_edit.text(),
            scan_config=scan_config,
            use_rag=use_rag,
            settings=self.settings,
            llm_client=llm_client,
        )
        # model используется воркером с llm_client=None — offline.
        # LLM-обёртка — T-111.

        self._opt_thread = QThread(self)
        self._opt_worker.moveToThread(self._opt_thread)
        self._opt_thread.started.connect(self._opt_worker.run)
        self._opt_worker.progress.connect(self._on_optimization_progress)
        self._opt_worker.done.connect(self._on_optimization_done)
        self._opt_worker.error.connect(self._on_optimization_error)
        self._opt_worker.cancelled.connect(self._on_optimization_cancelled)
        for sig in (
            self._opt_worker.done,
            self._opt_worker.error,
            self._opt_worker.cancelled,
        ):
            sig.connect(self._cleanup_optimization_thread)

        self.btn_optimize.setEnabled(False)
        self.btn_generate.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.status_label.setText("Оптимизация: запуск...")
        self._opt_thread.start()

    def _on_optimization_progress(self, percent: int, msg: str) -> None:
        self.progress_bar.setValue(percent)
        self.status_label.setText(f"Оптимизация: {msg} ({percent}%)")

    def _on_optimization_done(self, selected_abs_paths: list) -> None:
        try:
            root = self.tree_model.root_path
            if not root:
                self.status_label.setText("⚠️ Оптимизация: дерево не загружено")
                return
            selected_rel = {os.path.relpath(p, root).replace("\\", "/") for p in selected_abs_paths}
            all_files = self._all_file_paths()
            unchecked_rel = [
                os.path.relpath(f, root).replace("\\", "/")
                for f in all_files
                if os.path.relpath(f, root).replace("\\", "/") not in selected_rel
            ]
            self.tree_model.set_unchecked_paths(unchecked_rel)
            self.status_label.setText(f"✅ Оптимизация завершена. Выбрано файлов: {len(selected_rel)}")
        except Exception as e:
            log.warning("Error applying optimization: %s", e)
            self.status_label.setText(f"⚠️ Ошибка применения: {e}")

    def _on_optimization_error(self, msg: str) -> None:
        self.status_label.setText(f"❌ Ошибка оптимизации: {msg}")

    def _on_optimization_cancelled(self) -> None:
        self.status_label.setText("⏹ Оптимизация отменена")

    def _cleanup_optimization_thread(self, *_args) -> None:
        thread = self._opt_thread
        worker = self._opt_worker
        self._opt_thread = None
        self._opt_worker = None
        if thread is not None:
            try:
                thread.quit()
                if not thread.wait(3000):
                    thread.terminate()
                    thread.wait(1000)
            except RuntimeError as e:
                log.warning("opt thread cleanup: %s", e)
        self._detach_worker_from_thread(worker)
        self.progress_bar.setVisible(False)
        self.btn_optimize.setEnabled(True)
        self.btn_generate.setEnabled(True)

    def stop_optimization(self) -> None:
        """Остановить воркер оптимизации (для MainWindow.closeEvent)."""
        thread = self._opt_thread
        worker = self._opt_worker
        self._opt_thread = None
        self._opt_worker = None
        if thread is not None:
            try:
                thread.requestInterruption()
                thread.quit()
                if not thread.wait(3000):
                    thread.terminate()
                    thread.wait(1000)
            except RuntimeError:
                pass
        self._detach_worker_from_thread(worker)

    def _on_select_all_clicked(self, checked: bool) -> None:
        self.tree_model.set_all_checked(checked)
        self._sync_select_all_state()

    def _sync_select_all_state(self) -> None:
        all_files = self._all_file_paths()
        if not all_files:
            self.cb_select_all.setCheckState(Qt.CheckState.Checked)
            return
        checked_count = len(self.tree_model.checked_files())
        if checked_count == len(all_files):
            self.cb_select_all.setCheckState(Qt.CheckState.Checked)
        elif checked_count == 0:
            self.cb_select_all.setCheckState(Qt.CheckState.Unchecked)
        else:
            self.cb_select_all.setCheckState(Qt.CheckState.PartiallyChecked)

    @staticmethod
    def _detach_worker_from_thread(worker) -> None:
        """Вернуть worker в main-thread перед удалением.

        QObject с affinity на уже остановленный QThread нельзя удалять
        из main-thread — shiboken вызовет C++ деструктор из чужого
        потока, QObject::thread() вернёт мёртвый указатель → UB
        (SIGSEGV). moveToThread(current) сначала перемещает affinity
        обратно, потом GC безопасно собирает объект в main-thread.
        """
        if worker is None:
            return
        # C++ объект мог быть уже уничтожен — тогда moveToThread
        # бросит RuntimeError/AttributeError; это ожидаемо.
        with contextlib.suppress(RuntimeError, AttributeError):
            worker.moveToThread(QThread.currentThread())

    def _all_file_paths(self) -> list[str]:
        result: list[str] = []
        root = self.tree_model.root_path

        def walk(index: QModelIndex) -> None:
            if not index.isValid():
                return
            if self.tree_model.is_dir(index):
                for i in range(self.tree_model.rowCount(index)):
                    walk(self.tree_model.index(i, 0, index))
            else:
                rel = self.tree_model.relative_path(index)
                result.append(os.path.join(root, rel))

        for i in range(self.tree_model.rowCount(QModelIndex())):
            walk(self.tree_model.index(i, 0, QModelIndex()))
        return result

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
            "sort_by_size": self.cb_sort_by_size.isChecked(),
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
        self._refresh_recent_menu()

    def capture_tree_state(self) -> dict:
        """Снимок ui_tree_expanded / ui_tree_unchecked для сохранения."""
        try:
            return {
                "ui_tree_expanded": self._capture_expanded_paths(),
                "ui_tree_unchecked": self.tree_model.unchecked_paths(),
            }
        except Exception as e:
            log.warning("Error capturing tree state: %s", e)
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
                log.warning("Error capturing state before refresh: %s", e)
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
            log.warning("Tree scan error: %s", e)
            files = []
        self.tree_model.reset_data(files, root)

        if saved_unchecked:
            self.tree_model.set_unchecked_paths(saved_unchecked)
        if saved_expanded:
            self._schedule_expanded_restore(saved_expanded)
        self._update_watcher()

    def _update_watcher(self) -> None:
        """Запустить watcher на текущем root_folder, если auto_refresh on."""
        if not self.settings.get("auto_refresh_tree", True):
            if self._watcher.is_running():
                self._watcher.stop()
            return
        target = self.tree_model.root_path
        if not target:
            return
        if self._watcher.current_path() == target:
            return  # уже следим за этой папкой
        self._watcher.start(target)

    def _on_files_changed(self) -> None:
        """Debounced event от watcher — пересобрать дерево, если не заняты.

        Защита от segfault (см. /tmp/pig_crash.log, project_tree.py:275):
        если открыт модальный диалог (DiffDialog/SettingsDialog/и т.п.),
        event loop обрабатывает paint-события параллельно с dataChanged.
        emit на только что уничтоженных C++ QTreeView-узлах даёт SIGSEGV.
        Поэтому: pause_file_watcher() во время apply/undo/redo И
        activeModalWidget() guard для любых модальных диалогов.
        """
        if not self.settings.get("auto_refresh_tree", True):
            return
        if self._gen_thread is not None or self._opt_thread is not None:
            return  # не мешаем активной операции
        if getattr(self, "_watcher_paused", False):
            return  # явно приостановлен (Editor apply/undo/redo)
        try:
            from PySide6.QtWidgets import QApplication

            if QApplication.activeModalWidget() is not None:
                return  # модальный диалог открыт — пропускаем refresh
        except Exception as e:
            log.debug("activeModalWidget check failed: %s", e)
        self.refresh_tree()

    def pause_file_watcher(self) -> None:
        """FIX segfault: приостановить refresh по FileWatcher."""
        try:
            from shiboken6 import isValid

            if not isValid(self):
                return
            if getattr(self, "_watcher", None) is None or not isValid(self._watcher):
                return
        except Exception:
            return
        self._watcher_paused = True
        self._watcher_pause_count = getattr(self, "_watcher_pause_count", 0) + 1
        if self._watcher_pause_count == 1 and self._watcher.is_running():
            try:
                self._watcher.stop()
            except Exception as e:
                log.warning("pause_file_watcher stop: %s", e)

    def resume_file_watcher(self) -> None:
        """FIX segfault: возобновить + один refresh, если были изменения."""
        try:
            from shiboken6 import isValid

            if not isValid(self):
                return
            if getattr(self, "_watcher", None) is None or not isValid(self._watcher):
                return
        except Exception:
            return
        count = getattr(self, "_watcher_pause_count", 0)
        if count <= 0:
            return  # not paused — no-op (защита от двойного resume)
        new_count = count - 1
        self._watcher_pause_count = new_count
        if new_count > 0:
            return
        self._watcher_paused = False
        target = self.tree_model.root_path
        if target and self.settings.get("auto_refresh_tree", True):
            try:
                self._watcher.start(target)
            except Exception as e:
                log.warning("resume_file_watcher start: %s", e)
        self.refresh_tree()

    def set_tree_data(self, files: list[tuple[str, str]]) -> None:
        """Пересобрать дерево из явного списка (для тестов/внешних вызовов)."""
        self.tree_model.reset_data(files, self.path_edit.text())

    # ---------- Tree state helpers ----------

    def _capture_expanded_paths(self) -> list[str]:
        """Относительные пути всех раскрытых папок."""
        result: list[str] = []

        def walk(index: QModelIndex) -> None:
            if not index.isValid():
                return
            try:
                if self.tree_model.is_dir(index) and self.tree_view.isExpanded(index):
                    result.append(self.tree_model.relative_path(index))
                for i in range(self.tree_model.rowCount(index)):
                    walk(self.tree_model.index(i, 0, index))
            except Exception as e:
                log.warning("walk error at expanded capture: %s", e)

        try:
            for i in range(self.tree_model.rowCount(QModelIndex())):
                walk(self.tree_model.index(i, 0, QModelIndex()))
        except Exception as e:
            log.warning("Error capturing expanded paths: %s", e)
        return result

    def _schedule_expanded_restore(self, paths: list[str]) -> None:
        """Отложить восстановление expanded на один тик event loop."""
        self._pending_expanded_restore = list(paths)
        self._restore_expanded_timer.start()

    def _on_restore_expanded_timer(self) -> None:
        paths = self._pending_expanded_restore
        self._pending_expanded_restore = []
        self._restore_expanded_paths(paths)

    def _restore_expanded_paths(self, paths: list[str]) -> None:
        from shiboken6 import isValid

        # Защита от гонки: таймер мог выстрелить после уничтожения
        # C++ QTreeView/QAbstractItemModel (например, между тестами
        # в pytest-qt). Без проверки createIndex/setExpanded на мёртвом
        # C++ объекте даёт heap corruption.
        try:
            if not isValid(self) or not isValid(self.tree_view) or not isValid(self.tree_model):
                return
        except Exception:
            return

        for rel in paths:
            try:
                idx = self.tree_model.find_index(rel)
                if idx.isValid():
                    self.tree_view.setExpanded(idx, True)
            except RuntimeError:
                return

    # ---------- Generation (T-107) ----------
    def stop_generation(self) -> None:
        """Принудительно остановить фоновую генерацию (вызывается из
        MainWindow.closeEvent перед удалением виджета).

        Безопасен при повторном вызове и когда воркер не запущен.
        """
        thread = self._gen_thread
        worker = self._gen_worker
        self._gen_thread = None
        self._gen_worker = None
        if thread is not None:
            try:
                thread.requestInterruption()
                thread.quit()
                if not thread.wait(3000):
                    thread.terminate()
                    thread.wait(1000)
            except RuntimeError:
                pass
        self._detach_worker_from_thread(worker)

    def _on_generate_clicked(self) -> None:
        if self._gen_thread is not None:
            self._request_generation_cancel()
        else:
            self._start_generation()

    def _start_generation(self) -> None:
        root = self.path_edit.text().strip()
        if not root or not os.path.isdir(root):
            self.status_label.setText("❌ Папка проекта не существует")
            return

        settings = self.settings.copy()
        settings.update(self.collect_settings())
        settings.setdefault("strict_mode", self.settings.get("strict_mode", False))
        settings.setdefault("ignore_self", True)

        # Blacklist: только явно снятые галочки
        excluded = {os.path.normcase(os.path.abspath(p)) for p in self._excluded_file_paths()}
        settings["excluded_paths"] = list(excluded)

        self._gen_worker = GenerateWorker(settings, analyzer=self.analyzer)
        self._gen_thread = QThread(self)
        self._gen_worker.moveToThread(self._gen_thread)

        self._gen_thread.started.connect(self._gen_worker.run)
        self._gen_worker.progress.connect(self._on_generation_progress)
        self._gen_worker.finished.connect(self._on_generation_finished)
        self._gen_worker.error.connect(self._on_generation_error)
        self._gen_worker.cancelled.connect(self._on_generation_cancelled)
        # Cleanup в главном потоке после отработки любого исхода
        for sig in (
            self._gen_worker.finished,
            self._gen_worker.error,
            self._gen_worker.cancelled,
        ):
            sig.connect(self._cleanup_generation_thread)

        self.btn_generate.setText("❌ ОТМЕНИТЬ ГЕНЕРАЦИЮ")
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)  # indeterminate until first progress
        self.progress_bar.setValue(0)
        self.status_label.setText("Поиск файлов…")

        self._gen_thread.start()

    def _request_generation_cancel(self) -> None:
        if self._gen_thread is not None:
            self._gen_thread.requestInterruption()
            self.btn_generate.setText("ОТМЕНА…")
            self.btn_generate.setEnabled(False)

    def _excluded_file_paths(self) -> list[str]:
        """Абсолютные пути явно снятых файлов (blacklist для generator)."""
        result: list[str] = []
        model = self.tree_model
        root = model.root_path
        if not root:
            return result
        for rel in model.unchecked_paths():
            full = os.path.join(root, rel)
            if os.path.isfile(full):
                result.append(full)
        return result

    def _on_generation_progress(self, current: int, total: int) -> None:
        if total > 0:
            self.progress_bar.setRange(0, total)
            self.progress_bar.setValue(current)
            percent = int(current / total * 100)
            self.status_label.setText(f"Обработка: {current}/{total} ({percent}%)")
        else:
            self.status_label.setText(f"Обработка: {current}")

    def _on_generation_finished(self, path, count, lines, chars) -> None:
        lines_s = self._format_number(lines)
        chars_s = self._format_number(chars)
        self.status_label.setText(f"✅ Готово! Файлов: {count} | Строк: {lines_s} | Символов: {chars_s}")
        self._show_success_dialog(path, count, lines, chars)
        self.generation_finished.emit(path, count, lines, chars)
        self._reset_generate_button()

    def _on_generation_error(self, msg: str) -> None:
        self.status_label.setText(f"❌ Ошибка: {msg}")
        self._show_error_dialog(msg)
        self.generation_error.emit(msg)
        self._reset_generate_button()

    def _on_generation_cancelled(self) -> None:
        self.status_label.setText("⏹ Генерация отменена")
        self.generation_cancelled.emit()
        self._reset_generate_button()

    @staticmethod
    def _format_number(n: int) -> str:
        """1.2K / 45.68K / 3.4M — как в legacy GUI."""
        if n >= 1_000_000:
            return f"{n / 1_000_000:.2f}".rstrip("0").rstrip(".") + "M"
        if n >= 1_000:
            return f"{n / 1_000:.2f}".rstrip("0").rstrip(".") + "K"
        return str(n)

    def _show_success_dialog(self, path: str, count: int, lines: int, chars: int) -> None:
        lines_s = self._format_number(lines)
        chars_s = self._format_number(chars)
        msg = f"Отчет создан:\n{path}\n\nФайлов: {count}\nСтрок кода: {lines_s}\nСимволов: {chars_s}"
        if self.cb_auto_copy.isChecked():
            if copy_file_to_clipboard_windows(path):
                msg += "\n\n📋 ФАЙЛ СКОПИРОВАН В БУФЕР!"
            else:
                msg += "\n\n⚠️ Не удалось скопировать файл в буфер."
        _show_info_dialog(self, "Успех", msg)

    def _show_error_dialog(self, msg: str) -> None:
        _show_critical_dialog(self, "Ошибка", f"Что-то пошло не так:\n{msg}")

    def _reset_generate_button(self) -> None:
        self.btn_generate.setText("🚀 ГЕНЕРИРОВАТЬ КОНТЕКСТ")
        self.btn_generate.setEnabled(True)
        self.progress_bar.setVisible(False)

    def _cleanup_generation_thread(self, *_args) -> None:
        thread = self._gen_thread
        worker = self._gen_worker
        self._gen_thread = None
        self._gen_worker = None
        if thread is not None:
            try:
                thread.quit()
                if not thread.wait(3000):
                    thread.terminate()
                    thread.wait(1000)
            except RuntimeError as e:
                log.warning("thread cleanup: %s", e)
        # Вернуть worker в main-thread до того, как Python GC его
        # соберёт. moveToThread(dead_thread) делает affinity
        # невалидной; QObject::~QObject из main-thread на объекте с
        # мёртвой affinity — UB (SIGSEGV).
        self._detach_worker_from_thread(worker)

    # ---------- Handlers ----------

    def _refresh_recent_menu(self) -> None:
        paths = self.settings.get("recent_projects", [])
        self.recent_menu.update_projects(paths)

    def _on_recent_selected(self, path: str) -> None:
        self.path_edit.setText(path)

    def _on_recent_cleared(self) -> None:
        self.settings["recent_projects"] = []
        self._completer_model.setStringList([])
        self._refresh_recent_menu()
        self.settings_changed.emit()

    def browse_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Выберите папку проекта", self.path_edit.text())
        if folder:
            self.path_edit.setText(folder)

    def _on_all_ext_clicked(self) -> None:
        """Собрать все уникальные расширения файлов в проекте
        (с учётом ignore_list) и записать в ext_edit."""
        root = self.path_edit.text().strip()
        if not root or not os.path.isdir(root):
            self.status_label.setText("❌ Папка проекта не существует")
            return
        raw_ignore = self.ignore_edit.text().strip()
        ignored = {x.strip() for x in raw_ignore.split(",") if x.strip()}
        exts: set[str] = set()
        try:
            for _dirpath, dirnames, filenames in os.walk(root):
                dirnames[:] = [d for d in dirnames if d not in ignored and not any(ign in d for ign in ignored)]
                for f in filenames:
                    ext = os.path.splitext(f)[1]
                    if ext:
                        exts.add(ext.lower())
        except OSError as e:
            log.warning("all_ext walk failed: %s", e)
            self.status_label.setText(f"⚠️ Ошибка обхода: {e}")
            return
        if not exts:
            self.status_label.setText("⚠️ Расширения не найдены")
            return
        self.ext_edit.setText(", ".join(sorted(exts)))
        self.status_label.setText(f"🔍 Найдено расширений: {len(exts)}")

    def auto_set_folder(self) -> None:
        if getattr(sys, "frozen", False):
            parent_dir = os.path.dirname(sys.executable)
        else:
            parent_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
        self.path_edit.setText(parent_dir)

    def closeEvent(self, event) -> None:
        self._watcher.stop()
        super().closeEvent(event)
