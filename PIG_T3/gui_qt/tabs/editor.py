"""Вкладка «✏️ Редактор (JSON Patcher)» (T-302..T-307).

Публичный интерфейс:
- ``set_path(folder)`` — синхронизация пути с вкладкой Генератора
- ``load_json(text)`` — вставить JSON (используется планом)
- ``_on_validate``, ``_on_apply``, ``_on_undo``, ``_on_redo``
"""

from __future__ import annotations

import contextlib
import json
import logging
import os

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ...core.patcher import clean_json_text
from ..dialogs.diff_dialog import DiffDialog
from ..workers.apply_worker import ApplyWorker, UndoRedoWorker
from ..workers.diff_preview import compute_diffs, extract_commands
from ..workers.lmstudio_models_worker import (
    LMStudioModelsWorker,
)
from ..workers.lmstudio_models_worker import (
    cache_is_fresh as lmstudio_cache_is_fresh,
)
from ..workers.lmstudio_models_worker import (
    get_cached_models as get_lmstudio_cached_models,
)
from ..workers.lmstudio_models_worker import (
    save_models_to_cache as save_lmstudio_models_to_cache,
)
from ..workers.ollama_models_worker import (
    OllamaModelsWorker,
    cache_is_fresh,
    get_cached_models,
    save_models_to_cache,
)

_HISTORY_LIMIT = 10

log = logging.getLogger("pig_t3.editor")


def _show_warning(parent, title: str, text: str) -> None:
    QMessageBox.warning(parent, title, text)


def _show_info(parent, title: str, text: str) -> None:
    QMessageBox.information(parent, title, text)


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


class EditorTab(QWidget):
    """Редактор JSON-патча + Undo/Redo + авто-фикс (заглушка T-307)."""

    undo_available_changed = Signal(bool)
    redo_available_changed = Signal(bool)

    def __init__(
        self,
        settings: dict,
        parent=None,
        pause_watcher_cb=None,
        resume_watcher_cb=None,
    ):
        super().__init__(parent)
        self.settings = dict(settings)
        self._pause_watcher_cb = pause_watcher_cb
        self._resume_watcher_cb = resume_watcher_cb
        self.history_stack: list[dict] = []
        self.redo_stack: list[dict] = []
        self._last_applied_content: str | None = None
        self._current_path: str = self.settings.get("root_folder", "")

        self._apply_thread: QThread | None = None
        self._apply_worker: ApplyWorker | None = None
        self._models_thread: QThread | None = None
        self._models_worker: OllamaModelsWorker | None = None
        self._lmstudio_models_thread: QThread | None = None
        self._lmstudio_models_worker: LMStudioModelsWorker | None = None
        self._undo_thread: QThread | None = None
        self._undo_worker: UndoRedoWorker | None = None

        self._setup_ui()
        self._populate()
        self._connect_signals()

    # ---------- UI ----------

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        top = QHBoxLayout()
        top.addWidget(QLabel("Целевая папка:"))
        self.path_edit = QLineEdit(self._current_path)
        self.path_edit.setReadOnly(True)
        top.addWidget(self.path_edit, 1)
        self.btn_redo = QPushButton("↪ Повторить")
        self.btn_undo = QPushButton("↩ Отменить")
        self.btn_redo.setEnabled(False)
        self.btn_undo.setEnabled(False)
        top.addWidget(self.btn_redo)
        top.addWidget(self.btn_undo)
        layout.addLayout(top)

        layout.addWidget(QLabel("Вставьте JSON-ответ от AI (можно с ```json):"))
        self.editor_text = QPlainTextEdit()
        self.editor_text.setPlaceholderText("[{...}, {...}]")
        layout.addWidget(self.editor_text, 1)

        # Ollama settings (упрощённо — модель + 3 ключевых параметра)
        ollama_group = QGroupBox("🛠️ Ollama Auto-Fix (Локальная LLM)")
        ollama_layout = QVBoxLayout(ollama_group)

        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Модель:"))
        self.model_combo = QComboBox()
        self._populate_models()
        row1.addWidget(self.model_combo, 1)
        ollama_layout.addLayout(row1)

        row2 = QHBoxLayout()
        self.ctx_edit = QLineEdit()
        self.pred_edit = QLineEdit()
        self.temp_edit = QLineEdit()
        for label, edit in (
            ("Ctx:", self.ctx_edit),
            ("Predict:", self.pred_edit),
            ("Temp:", self.temp_edit),
        ):
            row2.addWidget(QLabel(label))
            edit.setMaximumWidth(80)
            row2.addWidget(edit)
        row2.addStretch(1)
        ollama_layout.addLayout(row2)
        layout.addWidget(ollama_group)

        btn_row = QHBoxLayout()
        self.btn_paste = QPushButton("📋 Вставить")
        self.btn_validate = QPushButton("🔍 Проверить / Форматировать")
        self.btn_preview = QPushButton("👁 Просмотр изменений")
        self.btn_apply = QPushButton("ПРИМЕНИТЬ ИЗМЕНЕНИЯ")
        btn_row.addWidget(self.btn_paste)
        btn_row.addWidget(self.btn_validate)
        btn_row.addWidget(self.btn_preview)
        btn_row.addWidget(self.btn_apply, 1)
        layout.addLayout(btn_row)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #e5c07b;")
        layout.addWidget(self.status_label)

    def _populate_models(self) -> None:
        base = [
            "None",
            "BomjAPI",
            "Web: Gemini",
            "Web: DeepSeek",
            "Web: DeepSeek (DeepThink)",
            "Web: DeepSeek Expert",
            "Web: DeepSeek Expert (DeepThink)",
        ]
        cached = get_cached_models(self.settings)
        for m in cached:
            if m not in base:
                base.append(m)
        lmstudio_cached = get_lmstudio_cached_models(self.settings)
        for m in lmstudio_cached:
            name = f"LM Studio: {m}"
            if name not in base:
                base.append(name)
        self.model_combo.addItems(base)
        if not cache_is_fresh(self.settings):
            self._fetch_models_async()
        if not lmstudio_cache_is_fresh(self.settings):
            self._fetch_lmstudio_models_async()

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

    def _fetch_lmstudio_models_async(self) -> None:
        if self._lmstudio_models_thread is not None:
            return
        worker = LMStudioModelsWorker(
            base_url=self.settings.get("lmstudio_base_url", "http://localhost:1234/v1"),
            api_key=self.settings.get("lmstudio_api_key", "lm-studio"),
        )
        thread = QThread(self)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.done.connect(self._on_lmstudio_models_fetched)
        worker.error.connect(self._on_lmstudio_models_error)
        for sig in (worker.done, worker.error):
            sig.connect(lambda *_args, w=worker, t=thread: self._cleanup_lmstudio_thread(w, t))
        self._lmstudio_models_worker = worker
        self._lmstudio_models_thread = thread
        thread.start()

    def _on_lmstudio_models_fetched(self, models: list) -> None:
        save_lmstudio_models_to_cache(self.settings, models)
        current = self.model_combo.currentText()
        existing = {self.model_combo.itemText(i) for i in range(self.model_combo.count())}
        for m in models:
            name = f"LM Studio: {m}"
            if name not in existing:
                self.model_combo.addItem(name)
        idx = self.model_combo.findText(current)
        if idx >= 0:
            self.model_combo.setCurrentIndex(idx)

    def _on_lmstudio_models_error(self, _msg: str) -> None:
        pass

    def _cleanup_lmstudio_thread(self, worker, thread) -> None:
        if thread is not None:
            try:
                thread.quit()
                thread.wait(3000)
            except RuntimeError:
                pass
        if self._lmstudio_models_thread is thread:
            self._lmstudio_models_thread = None
            self._lmstudio_models_worker = None

    def _populate(self) -> None:
        opts = self.settings.get("ollama_options", {})
        self.ctx_edit.setText(str(opts.get("num_ctx", 24000)))
        self.pred_edit.setText(str(opts.get("num_predict", 12000)))
        self.temp_edit.setText(str(opts.get("temperature", 0.5)))
        current = self.settings.get("ollama_model", "None")
        idx = self.model_combo.findText(current)
        if idx >= 0:
            self.model_combo.setCurrentIndex(idx)
        self._load_history()

    def _connect_signals(self) -> None:
        self.btn_paste.clicked.connect(self._on_paste)
        self.btn_validate.clicked.connect(self._on_validate)
        self.btn_preview.clicked.connect(self._on_preview)
        self.btn_apply.clicked.connect(self._on_apply)
        self.btn_undo.clicked.connect(self._on_undo)
        self.btn_redo.clicked.connect(self._on_redo)

    # ---------- Public ----------

    def set_path(self, folder: str) -> None:
        self._current_path = folder or ""
        self.path_edit.setText(self._current_path)
        self._load_history()

    def load_json(self, text: str) -> None:
        self.editor_text.setPlainText(text)
        self._on_validate()

    # ---------- Handlers ----------
    def _on_preview(self) -> None:
        """Показать diff перед применением. Если пользователь нажал
        «Применить» в диалоге — запускаем _on_apply."""
        if not self._on_validate():
            return
        if not self._current_path or not os.path.isdir(self._current_path):
            _show_error(self, "Ошибка", "Папка проекта не существует.")
            return
        raw = self.editor_text.toPlainText().strip()
        try:
            diffs = compute_diffs(raw, self._current_path)
        except Exception as e:
            _show_error(self, "Ошибка предпросмотра", str(e))
            return
        commands = extract_commands(raw)
        if commands and not self.settings.get("allow_command_execution", False):
            _show_warning(
                self,
                "Команды заблокированы",
                f"В патче {len(commands)} run_command, но в настройках "
                "не включено «Разрешить выполнение команд». Команды "
                "будут пропущены при применении.",
            )
        if not diffs and not commands:
            _show_info(self, "Просмотр", "Изменений нет.")
            return
        if self._pause_watcher_cb is not None:
            with contextlib.suppress(Exception):
                self._pause_watcher_cb()
        try:
            dlg = DiffDialog(diffs, commands=commands, parent=self)
            accepted = dlg.exec() == DiffDialog.DialogCode.Accepted
        finally:
            if self._resume_watcher_cb is not None:
                with contextlib.suppress(Exception):
                    self._resume_watcher_cb()
        if accepted:
            self._on_apply()

    def _on_paste(self) -> None:
        from PySide6.QtWidgets import QApplication

        text = QApplication.clipboard().text()
        if not text:
            self.status_label.setText("⚠️ Буфер пуст")
            return
        self.editor_text.setPlainText(text)
        self.status_label.setText("📋 Вставлено из буфера")

    def _on_validate(self) -> bool:
        raw = self.editor_text.toPlainText().strip()
        if not raw:
            self.status_label.setText("Пустое поле.")
            return False
        cleaned = clean_json_text(raw)
        try:
            data = json.loads(cleaned)
            if not isinstance(data, list):
                raise ValueError("JSON должен быть списком.")
            pretty = json.dumps(data, indent=2, ensure_ascii=False)
            self.editor_text.setPlainText(pretty)
            self.status_label.setText(f"✅ Валидный JSON. Операций: {len(data)}")
            return True
        except Exception as e:
            self.status_label.setText(f"❌ Ошибка JSON: {e}")
            return False

    def _on_apply(self) -> None:
        if not self._on_validate():
            return
        if not self._current_path or not os.path.isdir(self._current_path):
            _show_error(self, "Ошибка", "Папка проекта не существует.")
            return
        raw = self.editor_text.toPlainText().strip()
        if self._last_applied_content == raw and not _show_yes_no(
            self,
            "Подтверждение",
            "Эти изменения уже применялись. Повторить?",
        ):
            return
        self._last_applied_content = raw

        self.btn_apply.setEnabled(False)
        self.btn_apply.setText("Применение...")

        if self._pause_watcher_cb is not None:
            with contextlib.suppress(Exception):
                self._pause_watcher_cb()
        self._apply_worker = ApplyWorker(raw, self._current_path, settings=self.settings)
        self._apply_thread = QThread(self)
        self._apply_worker.moveToThread(self._apply_thread)
        self._apply_thread.started.connect(self._apply_worker.run)
        self._apply_worker.done.connect(self._on_apply_done)
        self._apply_worker.error.connect(self._on_apply_error)
        for sig in (self._apply_worker.done, self._apply_worker.error):
            sig.connect(self._cleanup_apply_thread)
        self._apply_thread.start()

    def _on_apply_done(self, log: str, record: dict) -> None:
        self.history_stack.append(record)
        if len(self.history_stack) > _HISTORY_LIMIT:
            oldest = self.history_stack.pop(0)
            # Бэкап мог быть уже удалён вручную — не критично
            with contextlib.suppress(Exception):
                import shutil

                shutil.rmtree(
                    os.path.join(
                        self._current_path,
                        ".pig",
                        "backups",
                        oldest["id"],
                    ),
                    ignore_errors=True,
                )
        self.redo_stack.clear()
        self._update_undo_redo()
        self._show_result_dialog(log)

    def _on_apply_error(self, msg: str) -> None:
        _show_error(self, "Ошибка применения", msg)
        self.status_label.setText(f"❌ {msg}")

    def _show_result_dialog(self, log: str) -> None:
        """Окно результата патча: лог + полные .pig/cmd/*.log по кнопке."""
        import os
        import re as _re

        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices, QGuiApplication
        from PySide6.QtWidgets import (
            QDialog,
            QFileDialog,
            QHBoxLayout,
            QMessageBox,
            QPlainTextEdit,
            QPushButton,
            QVBoxLayout,
        )

        dlg = QDialog(self)
        dlg.setWindowTitle("Результат патча")
        dlg.resize(1100, 700)
        layout = QVBoxLayout(dlg)
        text = QPlainTextEdit()
        text.setReadOnly(True)
        text.setPlainText(log)
        layout.addWidget(text, 1)

        output_paths = _re.findall(r"📄 output:\s*(\S+\.log)", log)

        def _copy_visible() -> None:
            QGuiApplication.clipboard().setText(text.toPlainText())

        def _copy_all() -> None:
            parts = [log]
            base = self._current_path or ""
            for rel in output_paths:
                full = os.path.join(base, rel)
                try:
                    with open(full, encoding="utf-8", errors="replace") as f:
                        parts.append(f"\n\n=== {rel} ===\n{f.read()}")
                except Exception as exc:
                    parts.append(f"\n\n=== {rel} ===\n(не удалось прочитать: {exc})")
            QGuiApplication.clipboard().setText("\n".join(parts))

        def _open_last_log() -> None:
            if not output_paths:
                return
            full = os.path.join(self._current_path or "", output_paths[-1])
            QDesktopServices.openUrl(QUrl.fromLocalFile(full))

        def _save_to_file() -> None:
            path, _ = QFileDialog.getSaveFileName(
                dlg,
                "Сохранить лог",
                "patch_result.log",
                "Log files (*.log);;All files (*)",
            )
            if path:
                try:
                    with open(path, "w", encoding="utf-8") as fh:
                        fh.write(text.toPlainText())
                except OSError as exc:
                    QMessageBox.warning(dlg, "Ошибка", f"Не удалось сохранить: {exc}")

        btn_row = QHBoxLayout()
        btn_copy = QPushButton("📋 Копировать")
        btn_copy.setToolTip("Скопировать видимый лог в буфер обмена")
        btn_copy.clicked.connect(_copy_visible)
        btn_row.addWidget(btn_copy)

        if output_paths:
            btn_copy_all = QPushButton(f"📋 Копировать всё (+{len(output_paths)} лог.)")
            btn_copy_all.setToolTip("Скопировать лог + полные выводы .pig/cmd/*.log (для вставки в чат с AI)")
            btn_copy_all.clicked.connect(_copy_all)
            btn_row.addWidget(btn_copy_all)

            btn_open = QPushButton("📄 Открыть .log")
            btn_open.setToolTip(output_paths[-1])
            btn_open.clicked.connect(_open_last_log)
            btn_row.addWidget(btn_open)

        btn_save = QPushButton("💾 Сохранить в файл")
        btn_save.setToolTip("Сохранить видимый лог в .log-файл")
        btn_save.clicked.connect(_save_to_file)
        btn_row.addWidget(btn_save)

        btn_row.addStretch(1)
        btn_close = QPushButton("Закрыть")
        btn_close.setDefault(True)
        btn_close.clicked.connect(dlg.accept)
        btn_row.addWidget(btn_close)
        layout.addLayout(btn_row)

        dlg.exec()
        dlg.deleteLater()

    def _on_undo(self) -> None:
        if not self.history_stack:
            return
        record = self.history_stack.pop()
        self.redo_stack.append(record)
        self._update_undo_redo()
        self.status_label.setText("⏳ Отмена...")
        self._start_undo_redo(record, "undo")

    def _on_redo(self) -> None:
        if not self.redo_stack:
            return
        record = self.redo_stack.pop()
        self.history_stack.append(record)
        self._update_undo_redo()
        self.status_label.setText("⏳ Повтор...")
        self._start_undo_redo(record, "redo")

    def _start_undo_redo(self, record: dict, action: str) -> None:
        self.btn_apply.setEnabled(False)
        if self._pause_watcher_cb is not None:
            with contextlib.suppress(Exception):
                self._pause_watcher_cb()
        self._undo_worker = UndoRedoWorker(self._current_path, record, action)
        self._undo_thread = QThread(self)
        self._undo_worker.moveToThread(self._undo_thread)
        self._undo_thread.started.connect(self._undo_worker.run)
        self._undo_worker.done.connect(self._on_undo_redo_done)
        self._undo_worker.error.connect(self._on_undo_redo_error)
        for sig in (self._undo_worker.done, self._undo_worker.error):
            sig.connect(self._cleanup_undo_thread)
        self._undo_thread.start()

    def _on_undo_redo_done(self, msg: str) -> None:
        self.status_label.setText(f"✅ {msg}")
        record = self.history_stack[-1] if self.history_stack else (self.redo_stack[-1] if self.redo_stack else None)
        if record:
            self.editor_text.setPlainText(record["llm_text"])
            self._on_validate()

    def _on_undo_redo_error(self, msg: str) -> None:
        self.status_label.setText(f"❌ {msg}")
        _show_error(self, "Ошибка", msg)

    def _update_undo_redo(self) -> None:
        self.btn_undo.setEnabled(bool(self.history_stack))
        self.btn_redo.setEnabled(bool(self.redo_stack))
        self.undo_available_changed.emit(bool(self.history_stack))
        self.redo_available_changed.emit(bool(self.redo_stack))
        self._save_history()

    def _history_file(self) -> str:
        return os.path.join(self._current_path, ".pig", "editor_history.json")

    def _save_history(self) -> None:
        if not self._current_path or not os.path.isdir(self._current_path):
            return
        path = self._history_file()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "history": self.history_stack,
                        "redo": self.redo_stack,
                        "last": self._last_applied_content or "",
                    },
                    f,
                    ensure_ascii=False,
                    indent=2,
                )
        except OSError:
            pass

    def _load_history(self) -> None:
        self.history_stack = []
        self.redo_stack = []
        if not self._current_path or not os.path.isdir(self._current_path):
            return
        path = self._history_file()
        if not os.path.exists(path):
            return
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            return

        def _valid(rec) -> bool:
            return isinstance(rec, dict) and bool(rec.get("id"))

        self.history_stack = [r for r in data.get("history", []) if _valid(r)]
        self.redo_stack = [r for r in data.get("redo", []) if _valid(r)]
        self._last_applied_content = data.get("last") or None
        self.btn_undo.setEnabled(bool(self.history_stack))
        self.btn_redo.setEnabled(bool(self.redo_stack))

    # ---------- Cleanup ----------

    def _cleanup_apply_thread(self, *_args) -> None:
        thread = self._apply_thread
        self._apply_thread = None
        self._apply_worker = None
        if thread is not None:
            try:
                thread.quit()
                thread.wait(3000)
            except RuntimeError:
                pass
        self.btn_apply.setEnabled(True)
        self.btn_apply.setText("ПРИМЕНИТЬ ИЗМЕНЕНИЯ")
        if self._resume_watcher_cb is not None:
            with contextlib.suppress(Exception):
                self._resume_watcher_cb()

    def _cleanup_undo_thread(self, *_args) -> None:
        thread = self._undo_thread
        self._undo_thread = None
        self._undo_worker = None
        if thread is not None:
            try:
                thread.quit()
                thread.wait(3000)
            except RuntimeError:
                pass
        self.btn_apply.setEnabled(True)
        if self._resume_watcher_cb is not None:
            with contextlib.suppress(Exception):
                self._resume_watcher_cb()

    def stop_workers(self) -> None:
        """Остановка для MainWindow.closeEvent."""
        self._cleanup_models_thread()
        if self._lmstudio_models_thread is not None:
            self._cleanup_lmstudio_thread(self._lmstudio_models_worker, self._lmstudio_models_thread)
        for thread_attr in ("_apply_thread", "_undo_thread"):
            thread = getattr(self, thread_attr, None)
            if thread is not None:
                try:
                    thread.quit()
                    thread.wait(2000)
                except RuntimeError:
                    pass
                setattr(self, thread_attr, None)
