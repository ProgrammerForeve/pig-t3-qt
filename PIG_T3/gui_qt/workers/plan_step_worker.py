"""PlanStepWorker — выполнение одного шага плана (T-406).

Контракт test_threading_contract: QObject, run(), сигналы
progress/done/error/cancelled.

DI-параметры (для тестов):
- llm_client: объект с .ask(prompt) -> str
- context_builder: callable(root, step_desc, limit) -> str
- apply_func: callable(llm_text, root_folder) -> str
"""

from __future__ import annotations

import json
import os
import time
from typing import Callable

from PySide6.QtCore import QObject, QThread, Signal, Slot

from ...core.patcher import apply_llm_changes, clean_json_text

_EXEC_PROMPT = """You are a coding assistant executing a specific step of a project plan.

FULL PROJECT PLAN:
{plan_json}

YOUR TASK: Execute ONLY the step described below.
Step ID: {step_id}
Step Title: {title}
Step Description:
{description}

CRITICAL INSTRUCTIONS:
1. The project context INCLUDES LINE NUMBERS. Use 'replace_lines' with 'start' and 'end' for all edits.
2. NEVER use 'replace_text' unless line numbers are absent.
3. When creating a new file, provide its FULL content in the 'create' action.
4. Execute this step COMPLETELY. All code described in the step must be written.
5. FORMAT: Your entire response must be a SINGLE valid JSON array. No markdown, no extra text. Start with '[' and end with ']'.
6. To update the plan status, include a 'mark_step_completed' action when done.
7. ANTI-DESTRUCTION: Use 'edit' for existing files, never 'create' to overwrite.
8. Do NOT execute other steps from the plan.

[PROJECT CONTEXT]
{context}"""


class PlanStepWorker(QObject):
    progress = Signal(int, str)
    done = Signal(dict, str)  # (updated step, apply log)
    error = Signal(dict, str)  # (step, error message)
    cancelled = Signal()

    def __init__(
        self,
        step: dict,
        plan_data: list[dict],
        root_folder: str,
        model_name: str,
        settings: dict,
        limit_tokens: int = 15000,
        parent_widget=None,
        llm_client=None,
        context_builder: Callable[[str, str, int], str] | None = None,
        apply_func: Callable[[str, str], str] | None = None,
        max_retries: int = 2,
        parent: QObject | None = None,
    ):
        super().__init__(parent)
        self._step = dict(step)
        self._plan_data = [dict(s) for s in plan_data]
        self._root = root_folder
        self._model_name = model_name
        self._settings = dict(settings)
        self._limit_tokens = limit_tokens
        self._parent_widget = parent_widget
        self._llm = llm_client
        self._context_builder = context_builder
        self._apply_func = apply_func or apply_llm_changes
        self._max_retries = max(0, max_retries)

    # ---------- Internals ----------

    def _is_interrupted(self) -> bool:
        thread = QThread.currentThread()
        return thread is not None and thread.isInterruptionRequested()

    def _get_llm(self):
        if self._llm is not None:
            return self._llm
        from .llm_wrappers import make_llm_client

        return make_llm_client(self._model_name, self._parent_widget, self._settings)

    def _build_context(self) -> str:
        if self._context_builder is not None:
            return self._context_builder(
                self._root,
                self._step.get("description", ""),
                self._limit_tokens,
            )
        return self._default_context_build()

    def _default_context_build(self) -> str:
        from ...core.context_optimizer import ContextOptimizer

        try:
            opt = ContextOptimizer(
                root_folder=self._root,
                task=self._step.get("description", ""),
                limit_tokens=self._limit_tokens,
                llm_client=None,
                bfs_depth=int(self._settings.get("opt_bfs_depth", 2)),
                token_bytes_per_token=int(self._settings.get("opt_token_bytes_per_token", 4)),
                ignore_list=self._settings.get("ignore_list", ""),
            )
            selected = opt.optimize()
        except Exception:
            selected = []
        parts: list[str] = []
        for path in selected:
            try:
                with open(path, encoding="utf-8", errors="replace") as f:
                    content = f.read()
                rel = os.path.relpath(path, self._root).replace("\\", "/")
                parts.append(f'<file path="{rel}">\n{content}\n</file>\n\n')
            except Exception as e:
                print(f"context build: skip {path}: {e}")
        return "".join(parts)

    def _build_prompt(self, context: str) -> str:
        plan_json = json.dumps(self._plan_data, indent=2, ensure_ascii=False)
        return _EXEC_PROMPT.format(
            plan_json=plan_json,
            step_id=self._step.get("id", ""),
            title=self._step.get("title", ""),
            description=self._step.get("description", ""),
            context=context,
        )

    def _apply_mark_to_step(self, llm_response: str) -> bool:
        try:
            cleaned = clean_json_text(llm_response)
            actions = json.loads(cleaned)
        except Exception:
            return False
        if not isinstance(actions, list):
            return False
        found = False
        for action in actions:
            if not isinstance(action, dict):
                continue
            if action.get("action") != "mark_step_completed":
                continue
            if "completed" in action:
                self._step["completed"] = bool(action["completed"])
            else:
                self._step["completed"] = True
            if action.get("explanation"):
                self._step["report"] = str(action["explanation"])
            if "append_description" in action:
                append = str(action["append_description"])
                if append:
                    existing = self._step.get("description", "")
                    self._step["description"] = (existing + "\n" + append) if existing else append
            found = True
        return found

    def _sleep_cancellable(self, seconds: float) -> bool:
        """Спать секунды, но проверять interruption каждые 100мс."""
        steps = max(1, int(seconds * 10))
        for _ in range(steps):
            if self._is_interrupted():
                return False
            time.sleep(seconds / steps)
        return True

    # ---------- Run ----------

    @Slot()
    def run(self) -> None:
        last_error = ""
        for attempt in range(self._max_retries + 1):
            if self._is_interrupted():
                self.cancelled.emit()
                return
            try:
                self.progress.emit(
                    10,
                    f"Сбор контекста (попытка {attempt + 1}/{self._max_retries + 1})...",
                )
                context = self._build_context()
                if self._is_interrupted():
                    self.cancelled.emit()
                    return

                self.progress.emit(30, f"Запрос к {self._model_name}...")
                llm = self._get_llm()
                if llm is None:
                    self.error.emit(self._step, "Модель LLM не выбрана или недоступна")
                    return

                prompt = self._build_prompt(context)
                llm_response = llm.ask(prompt) or ""
                if self._is_interrupted():
                    self.cancelled.emit()
                    return
                if not llm_response:
                    raise ValueError("LLM вернул пустой ответ")

                self.progress.emit(60, "Валидация JSON...")
                cleaned = clean_json_text(llm_response)
                parsed = json.loads(cleaned)
                if not isinstance(parsed, list):
                    raise ValueError("JSON должен быть списком операций")

                self.progress.emit(80, "Применение изменений...")
                apply_log = self._apply_func(llm_response, self._root)
                has_mark = self._apply_mark_to_step(llm_response)
                self._step["status"] = "completed" if has_mark else "pending"
                if not self._step.get("report"):
                    self._step["report"] = apply_log

                self.progress.emit(100, "Готово")
                self.done.emit(self._step, apply_log)
                return
            except Exception as e:
                last_error = str(e)
                if attempt < self._max_retries and not self._sleep_cancellable(1.0):
                    self.cancelled.emit()
                    return

        self.error.emit(self._step, last_error or "Неизвестная ошибка")
