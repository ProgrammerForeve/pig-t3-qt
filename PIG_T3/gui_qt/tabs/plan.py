"""Вкладка «📝 План проекта» — каркас, load/save, редактирование, DnD.

Задачи T-401..T-404. Генерация плана (T-405) и выполнение (T-406..T-409)
реализуются в последующих коммитах.

Публичный интерфейс:
- ``PlanTab(settings)``
- ``set_path(folder)`` — синхронизация из GeneratorTab
- ``plan_data`` (list[dict]) — текущий план
- ``load_plan()`` / ``save_plan_silently()``
- ``stop_workers()`` — для MainWindow.closeEvent
"""

from __future__ import annotations

import contextlib
import json
import os

from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from ...core.plan_validator import validate_plan
from ..dialogs.new_plan_dialog import NewPlanDialog
from ..workers.generate_plan_worker import GeneratePlanWorker
from ..workers.plan_step_worker import PlanStepWorker

_SAVE_DEBOUNCE_MS = 500


def _show_warning(parent, title: str, text: str) -> None:
    QMessageBox.warning(parent, title, text)


def _show_error(parent, title: str, text: str) -> None:
    QMessageBox.critical(parent, title, text)


def _show_yes_no(parent, title: str, text: str) -> bool:
    r = QMessageBox.question(
        parent,
        title,
        text,
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No,
    )
    return r == QMessageBox.StandardButton.Yes


class PlanTab(QWidget):
    """Каркас вкладки «План проекта»."""

    plan_changed = Signal()

    def __init__(self, settings: dict, parent=None):
        super().__init__(parent)
        self.settings = dict(settings)
        self._current_path: str = self.settings.get("root_folder", "")
        self.plan_data: list[dict] = []
        self._current_index: int = -1
        self._gen_plan_thread: QThread | None = None
        self._gen_plan_worker: GeneratePlanWorker | None = None
        self._exec_thread: QThread | None = None
        self._exec_worker: PlanStepWorker | None = None
        self._full_plan_running: bool = False
        self._full_plan_cancel: bool = False
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(_SAVE_DEBOUNCE_MS)
        self._save_timer.timeout.connect(self._on_save_timer)

        self._setup_ui()
        self._connect_signals()

    # ---------- UI ----------

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(splitter, 1)

        # --- Левая панель: список шагов ---
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)

        top_btns = QHBoxLayout()
        self.btn_refresh = QPushButton("🔄 Обновить")
        self.btn_new_plan = QPushButton("✨ Новый План")
        top_btns.addWidget(self.btn_refresh)
        top_btns.addWidget(self.btn_new_plan)
        left_layout.addLayout(top_btns)

        self.plan_list = QListWidget()
        self.plan_list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.plan_list.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.plan_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        left_layout.addWidget(self.plan_list, 1)
        splitter.addWidget(left)

        # --- Правая панель: редактор шага ---
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)

        status_row = QHBoxLayout()
        self.cb_completed = QCheckBox("✅ Шаг выполнен")
        status_row.addWidget(self.cb_completed)
        status_row.addStretch(1)
        self.btn_delete_step = QPushButton("🗑️ Удалить шаг")
        status_row.addWidget(self.btn_delete_step)
        right_layout.addLayout(status_row)

        right_layout.addWidget(QLabel("Название:"))
        self.title_edit = QLineEdit()
        right_layout.addWidget(self.title_edit)

        right_layout.addWidget(QLabel("Описание (задача для ИИ):"))
        self.desc_edit = QPlainTextEdit()
        right_layout.addWidget(self.desc_edit, 1)

        right_layout.addWidget(QLabel("Отчёт ИИ о выполнении:"))
        self.report_edit = QPlainTextEdit()
        self.report_edit.setMaximumHeight(120)
        right_layout.addWidget(self.report_edit)

        splitter.addWidget(right)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        splitter.setSizes([320, 700])

        # --- Нижняя панель: выполнение ---
        exec_group = QGroupBox("🤖 Выполнение")
        exec_layout = QHBoxLayout(exec_group)

        exec_layout.addWidget(QLabel("Модель:"))
        self.model_combo = QComboBox()
        self.model_combo.addItems(["None", "BomjAPI", "Web: Gemini", "Web: DeepSeek"])
        exec_layout.addWidget(self.model_combo)

        self.cb_auto_apply = QCheckBox("Авто-применение")
        exec_layout.addWidget(self.cb_auto_apply)

        self.btn_exec_selected = QPushButton("🚀 ВЫПОЛНИТЬ ВЫБРАННЫЙ ШАГ")
        self.btn_exec_full = QPushButton("▶️ ВЫПОЛНИТЬ ВЕСЬ ПЛАН")
        self.btn_retry = QPushButton("🔄 Повторить шаг с ошибкой")
        self.btn_retry.setEnabled(False)

        exec_layout.addStretch(1)
        exec_layout.addWidget(self.btn_retry)
        exec_layout.addWidget(self.btn_exec_selected)
        exec_layout.addWidget(self.btn_exec_full)
        layout.addWidget(exec_group)

        progress_row = QHBoxLayout()
        self.progress_bar = QProgressBar()
        self.progress_bar.setMaximumWidth(300)
        self.progress_bar.setVisible(False)
        self.progress_global = QProgressBar()
        self.progress_global.setMaximumWidth(200)
        self.progress_global.setFormat("%v / %m шагов")
        self.progress_global.setVisible(False)
        self.status_label = QLabel("Готов")
        progress_row.addWidget(self.progress_bar)
        progress_row.addWidget(self.progress_global)
        progress_row.addWidget(self.status_label, 1)
        layout.addLayout(progress_row)

        self._update_editor_enabled(False)

    def _connect_signals(self) -> None:
        self.btn_refresh.clicked.connect(self.load_plan)
        self.btn_new_plan.clicked.connect(self._on_new_plan_clicked)
        self.btn_delete_step.clicked.connect(self._on_delete_step)
        self.plan_list.currentRowChanged.connect(self._on_step_selected)
        self.plan_list.model().rowsMoved.connect(self._on_rows_moved)

        self.title_edit.textChanged.connect(self._schedule_save)
        self.desc_edit.textChanged.connect(self._schedule_save)
        self.report_edit.textChanged.connect(self._schedule_save)
        self.cb_completed.toggled.connect(self._on_completed_toggled)

        # T-405..T-409 — заглушки на этом этапе
        self.btn_exec_selected.clicked.connect(self._on_exec_selected_clicked)
        self.btn_exec_full.clicked.connect(self._on_exec_full_clicked)
        self.btn_retry.clicked.connect(self._on_retry_clicked)

    # ---------- Public ----------

    def set_path(self, folder: str) -> None:
        self._current_path = folder or ""
        self.load_plan()

    def load_plan(self) -> None:
        if not self._current_path or not os.path.isdir(self._current_path):
            self.plan_data = []
            self._refresh_list()
            return
        path = os.path.join(self._current_path, ".pig", "plan.json")
        if not os.path.exists(path):
            self.plan_data = []
            self._refresh_list()
            return
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, list):
                data = []
        except Exception as e:
            print(f"load_plan error: {e}")
            data = []
        self.plan_data = data
        issues = validate_plan(self.plan_data)
        if issues:
            _show_warning(
                self,
                "Проблемы плана",
                "Обнаружены проблемы:\n\n" + "\n".join(issues),
            )
        self._refresh_list()

    def save_plan_silently(self) -> None:
        if not self._current_path or not os.path.isdir(self._current_path):
            return
        plan_path = os.path.join(self._current_path, ".pig", "plan.json")
        os.makedirs(os.path.dirname(plan_path), exist_ok=True)
        try:
            with open(plan_path, "w", encoding="utf-8") as f:
                json.dump(self.plan_data, f, indent=4, ensure_ascii=False)
            self.plan_changed.emit()
        except Exception as e:
            print(f"save_plan error: {e}")

    def stop_workers(self) -> None:
        self._save_timer.stop()
        for attr in ("_gen_plan_thread", "_exec_thread"):
            thread = getattr(self, attr, None)
            setattr(self, attr, None)
            if thread is not None:
                with contextlib.suppress(RuntimeError):
                    thread.requestInterruption()
                    thread.quit()
                    thread.wait(3000)
        self._gen_plan_worker = None
        self._exec_worker = None
        self._full_plan_running = False
        self._full_plan_cancel = False

    # ---------- List rendering ----------

    def _refresh_list(self) -> None:
        self.plan_list.clear()
        for step in self.plan_data:
            mark = "✅" if step.get("completed") else "⬜"
            status = step.get("status", "pending")
            if status == "in_progress":
                mark = "🔵"
            elif status == "failed":
                mark = "🔴"
            title = step.get("title", "Без названия")
            self.plan_list.addItem(QListWidgetItem(f"{mark} {title}"))
        if self.plan_data:
            self.plan_list.setCurrentRow(0)
        else:
            self._current_index = -1
            self._clear_editor()
            self._update_editor_enabled(False)

    # ---------- Editor sync ----------

    def _on_step_selected(self, row: int) -> None:
        if row < 0 or row >= len(self.plan_data):
            self._current_index = -1
            self._clear_editor()
            self._update_editor_enabled(False)
            return
        self._current_index = row
        step = self.plan_data[row]
        self._block_save_signals(True)
        try:
            self.title_edit.setText(step.get("title", ""))
            self.desc_edit.setPlainText(step.get("description", ""))
            self.report_edit.setPlainText(step.get("report", ""))
            self.cb_completed.setChecked(bool(step.get("completed", False)))
        finally:
            self._block_save_signals(False)
        self._update_editor_enabled(True)
        self.btn_retry.setEnabled(step.get("status") == "failed")

    def _clear_editor(self) -> None:
        self._block_save_signals(True)
        try:
            self.title_edit.clear()
            self.desc_edit.clear()
            self.report_edit.clear()
            self.cb_completed.setChecked(False)
        finally:
            self._block_save_signals(False)

    def _block_save_signals(self, block: bool) -> None:
        for w in (
            self.title_edit,
            self.desc_edit,
            self.report_edit,
            self.cb_completed,
        ):
            w.blockSignals(block)

    def _update_editor_enabled(self, enabled: bool) -> None:
        for w in (
            self.title_edit,
            self.desc_edit,
            self.report_edit,
            self.cb_completed,
            self.btn_delete_step,
        ):
            w.setEnabled(enabled)

    def _schedule_save(self) -> None:
        if self._current_index < 0:
            return
        self._save_timer.start()

    def _on_save_timer(self) -> None:
        """Debounce сработал: скопировать поля в plan_data и записать файл."""
        self._save_current_step()
        self.save_plan_silently()

    def _on_completed_toggled(self, checked: bool) -> None:
        if self._current_index < 0:
            return
        step = self.plan_data[self._current_index]
        step["completed"] = checked
        if checked and step.get("status") in ("in_progress", "failed"):
            step["status"] = "completed"
        self._save_timer.start()

    def _save_current_step(self) -> None:
        if self._current_index < 0 or self._current_index >= len(self.plan_data):
            return
        step = self.plan_data[self._current_index]
        step["title"] = self.title_edit.text()
        step["description"] = self.desc_edit.toPlainText().strip()
        step["report"] = self.report_edit.toPlainText().strip()
        step["completed"] = self.cb_completed.isChecked()

    # ---------- DnD ----------

    def _on_rows_moved(self, *_args) -> None:
        # Перестроить plan_data по текущему порядку в QListWidget
        new_order: list[dict] = []
        for i in range(self.plan_list.count()):
            item = self.plan_list.item(i)
            text = item.text() if item else ""
            # найдём по совпадению title (порядок гарантирован)
            for step in self.plan_data:
                if not step.get("_moved"):
                    display = f"{self._get_mark(step)} {step.get('title', '')}"
                    if display == text:
                        step["_moved"] = True
                        new_order.append(step)
                        break
        # fallback — если что-то не совпало, оставить старый порядок
        if len(new_order) == len(self.plan_data):
            for step in new_order:
                step.pop("_moved", None)
            self.plan_data = new_order
            self.save_plan_silently()
        else:
            for step in self.plan_data:
                step.pop("_moved", None)

    @staticmethod
    def _get_mark(step: dict) -> str:
        if step.get("status") == "in_progress":
            return "🔵"
        if step.get("status") == "failed":
            return "🔴"
        return "✅" if step.get("completed") else "⬜"

    # ---------- Handlers ----------

    def _on_new_plan_clicked(self) -> None:
        if not self._current_path or not os.path.isdir(self._current_path):
            _show_warning(
                self,
                "Ошибка",
                "Сначала выберите папку проекта во вкладке Генератор.",
            )
            return

        models = ["None", "BomjAPI", "Web: Gemini", "Web: DeepSeek"]
        with contextlib.suppress(Exception):
            from ...core.ollama_client import get_installed_models

            models.extend(get_installed_models())

        dlg = NewPlanDialog(models, parent=self)
        if dlg.exec() != NewPlanDialog.DialogCode.Accepted:
            return

        concept = dlg.get_concept()
        model = dlg.get_model()
        self._start_generate_plan(concept, model)

    def _start_generate_plan(self, concept: str, model_name: str) -> None:
        if self._gen_plan_thread is not None:
            return
        self.btn_new_plan.setEnabled(False)
        self.btn_exec_selected.setEnabled(False)
        self.btn_exec_full.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.status_label.setText("Генерация плана: подготовка...")

        limit = int(self.settings.get("plan_generation_limit_tokens", 12000))
        self._gen_plan_worker = GeneratePlanWorker(
            root_folder=self._current_path,
            concept=concept,
            model_name=model_name,
            settings=self.settings,
            limit_tokens=limit,
            parent_widget=self,
        )
        self._gen_plan_thread = QThread(self)
        self._gen_plan_worker.moveToThread(self._gen_plan_thread)
        self._gen_plan_thread.started.connect(self._gen_plan_worker.run)
        self._gen_plan_worker.progress.connect(self._on_gen_plan_progress)
        self._gen_plan_worker.done.connect(self._on_gen_plan_done)
        self._gen_plan_worker.error.connect(self._on_gen_plan_error)
        self._gen_plan_worker.cancelled.connect(self._on_gen_plan_cancelled)
        for sig in (
            self._gen_plan_worker.done,
            self._gen_plan_worker.error,
            self._gen_plan_worker.cancelled,
        ):
            sig.connect(self._cleanup_gen_plan_thread)
        self._gen_plan_thread.start()

    def _on_gen_plan_progress(self, percent: int, msg: str) -> None:
        self.progress_bar.setValue(percent)
        self.status_label.setText(f"{msg} ({percent}%)")

    def _on_gen_plan_done(self, plan: list) -> None:
        self.plan_data = plan
        self.save_plan_silently()
        self._refresh_list()
        self.status_label.setText(f"✅ План сгенерирован. Шагов: {len(plan)}")

    def _on_gen_plan_error(self, msg: str) -> None:
        self.status_label.setText(f"❌ Ошибка генерации: {msg}")
        _show_error(self, "Ошибка генерации", msg)

    def _on_gen_plan_cancelled(self) -> None:
        self.status_label.setText("⏹ Генерация плана отменена")

    def _cleanup_gen_plan_thread(self, *_args) -> None:
        thread = self._gen_plan_thread
        self._gen_plan_thread = None
        self._gen_plan_worker = None
        if thread is not None:
            with contextlib.suppress(RuntimeError):
                thread.quit()
                thread.wait(3000)
        self.btn_new_plan.setEnabled(True)
        self.btn_exec_selected.setEnabled(True)
        self.btn_exec_full.setEnabled(True)
        self.progress_bar.setVisible(False)

    def _on_delete_step(self) -> None:
        if self._current_index < 0:
            return
        if not _show_yes_no(self, "Удалить", "Точно удалить этот шаг?"):
            return
        self.plan_data.pop(self._current_index)
        self._current_index = -1
        self.save_plan_silently()
        self._refresh_list()

    def _on_exec_selected_clicked(self) -> None:
        if self._exec_thread is not None:
            return
        if self._current_index < 0 or self._current_index >= len(self.plan_data):
            _show_warning(self, "Внимание", "Выберите шаг для выполнения.")
            return
        step = self.plan_data[self._current_index]
        if step.get("completed") and not _show_yes_no(
            self,
            "Подтверждение",
            "Этот шаг уже выполнен. Выполнить повторно?",
        ):
            return
        model = self.model_combo.currentText()
        if model in ("", "None"):
            _show_warning(self, "Внимание", "Выберите модель LLM.")
            return
        if not self._current_path or not os.path.isdir(self._current_path):
            _show_warning(self, "Ошибка", "Папка проекта не существует.")
            return
        self._start_exec_step(step, model)

    def _on_retry_clicked(self) -> None:
        self._on_exec_selected_clicked()

    def _start_exec_step(self, step: dict, model_name: str) -> None:
        self.btn_exec_selected.setEnabled(False)
        self.btn_exec_full.setEnabled(False)
        self.btn_retry.setEnabled(False)
        self.btn_new_plan.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.status_label.setText(f"Выполнение шага: {step.get('title', '')}")

        limit = int(self.settings.get("plan_step_limit_tokens", 15000))
        self._exec_worker = PlanStepWorker(
            step=step,
            plan_data=self.plan_data,
            root_folder=self._current_path,
            model_name=model_name,
            settings=self.settings,
            limit_tokens=limit,
            parent_widget=self,
        )
        self._exec_thread = QThread(self)
        self._exec_worker.moveToThread(self._exec_thread)
        self._exec_thread.started.connect(self._exec_worker.run)
        self._exec_worker.progress.connect(self._on_exec_progress)
        self._exec_worker.done.connect(self._on_exec_done)
        self._exec_worker.error.connect(self._on_exec_error)
        self._exec_worker.cancelled.connect(self._on_exec_cancelled)
        for sig in (
            self._exec_worker.done,
            self._exec_worker.error,
            self._exec_worker.cancelled,
        ):
            sig.connect(self._cleanup_exec_thread)
        self._exec_thread.start()

    def _on_exec_progress(self, percent: int, msg: str) -> None:
        self.progress_bar.setValue(percent)
        self.status_label.setText(f"{msg} ({percent}%)")

    def _on_exec_done(self, step: dict, log: str) -> None:
        idx = -1
        for i, s in enumerate(self.plan_data):
            if s.get("id") == step.get("id"):
                idx = i
                break
        if idx >= 0:
            self.plan_data[idx] = step
            self.save_plan_silently()
            self._refresh_list()
            self.plan_list.setCurrentRow(idx)
        self.status_label.setText(f"✅ Шаг выполнен: {step.get('title', '')}")
        if self._full_plan_running:
            if self._full_plan_cancel:
                self._finish_full_plan("отменён")
            else:
                QTimer.singleShot(0, self._run_next_full_plan_step)

    def _on_exec_error(self, step: dict, msg: str) -> None:
        idx = -1
        for i, s in enumerate(self.plan_data):
            if s.get("id") == step.get("id"):
                idx = i
                break
        if idx >= 0:
            self.plan_data[idx]["status"] = "failed"
            self.plan_data[idx]["report"] = f"Ошибка: {msg}"
            self.save_plan_silently()
            self._refresh_list()
        self.status_label.setText(f"❌ Ошибка: {msg}")
        if self._full_plan_running:
            # Останавливаем весь пайплайн — legacy тоже так делал
            self._finish_full_plan("остановлен из-за ошибки")
        _show_error(self, "Ошибка выполнения", msg)

    def _on_exec_cancelled(self) -> None:
        self.status_label.setText("⏹ Выполнение отменено")

    def _cleanup_exec_thread(self, *_args) -> None:
        thread = self._exec_thread
        worker = self._exec_worker
        self._exec_thread = None
        self._exec_worker = None
        if thread is not None:
            with contextlib.suppress(RuntimeError):
                thread.quit()
                thread.wait(3000)
        self._detach_worker_from_thread(worker)
        self.btn_exec_selected.setEnabled(True)
        self.btn_exec_full.setEnabled(True)
        self.btn_new_plan.setEnabled(True)
        if 0 <= self._current_index < len(self.plan_data):
            step = self.plan_data[self._current_index]
            self.btn_retry.setEnabled(step.get("status") == "failed")
        self.progress_bar.setVisible(False)

    @staticmethod
    def _detach_worker_from_thread(worker) -> None:
        """Отвязать worker от мёртвого QThread перед GC (см. T-107)."""
        if worker is None:
            return
        with contextlib.suppress(RuntimeError, AttributeError):
            worker.moveToThread(QThread.currentThread())

    def _on_exec_full_clicked(self) -> None:
        if self._full_plan_running:
            # Кнопка уже нажата повторно — отменяем
            self._full_plan_cancel = True
            self.btn_exec_full.setEnabled(False)
            self.btn_exec_full.setText("⏹ ОСТАНОВКА...")
            thread = self._exec_thread
            if thread is not None:
                with contextlib.suppress(RuntimeError):
                    thread.requestInterruption()
            return

        if not self.plan_data:
            _show_warning(self, "Внимание", "План пуст.")
            return
        if all(s.get("completed") for s in self.plan_data):
            _show_warning(self, "Внимание", "Все шаги уже выполнены.")
            return
        if self.model_combo.currentText() in ("", "None"):
            _show_warning(self, "Внимание", "Выберите модель LLM.")
            return
        if not self._current_path or not os.path.isdir(self._current_path):
            _show_warning(self, "Ошибка", "Папка проекта не существует.")
            return

        self._full_plan_running = True
        self._full_plan_cancel = False
        self.btn_exec_full.setText("⏹ ОСТАНОВИТЬ ПОЛНЫЙ ПЛАН")
        self.progress_global.setVisible(True)
        self.progress_global.setRange(0, len(self.plan_data))
        self.progress_global.setValue(0)
        self._run_next_full_plan_step()

    def _run_next_full_plan_step(self) -> None:
        if not self._full_plan_running:
            return
        if self._full_plan_cancel:
            self._finish_full_plan("отменён")
            return
        next_idx = -1
        for i, s in enumerate(self.plan_data):
            if not s.get("completed"):
                next_idx = i
                break
        if next_idx < 0:
            self.progress_global.setValue(len(self.plan_data))
            self._finish_full_plan("завершён")
            return

        step = self.plan_data[next_idx]
        self.plan_list.setCurrentRow(next_idx)
        self.progress_global.setValue(next_idx)
        self.status_label.setText(f"Выполнение шага {next_idx + 1}/{len(self.plan_data)}: {step.get('title', '')}")
        model = self.model_combo.currentText()
        self._start_exec_step(step, model)

    def _finish_full_plan(self, status: str) -> None:
        self._full_plan_running = False
        self._full_plan_cancel = False
        self.btn_exec_full.setText("▶️ ВЫПОЛНИТЬ ВЕСЬ ПЛАН")
        self.btn_exec_full.setEnabled(True)
        self.btn_exec_selected.setEnabled(True)
        self.btn_new_plan.setEnabled(True)
        self.progress_global.setVisible(False)
        self.status_label.setText(f"Полный план {status}.")
        self._refresh_list()

    @staticmethod
    def _show_warning_stub(title: str, text: str) -> None:
        # Отдельный метод — тесты подменяют его
        QMessageBox.information(None, title, text)
