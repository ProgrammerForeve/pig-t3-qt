"""GeneratePlanWorker — генерация плана из концепции (T-405).

Контракт test_threading_contract: QObject, run(), сигналы
progress/done/error/cancelled.

LLM-клиент и построитель контекста — DI-параметры (None → factory /
default implementation) для тестируемости.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Callable

from PySide6.QtCore import QObject, QThread, Signal, Slot

from ...core.patcher import clean_json_text

_PLAN_PROMPT_TEMPLATE = """You are an expert AI architect. Break down the main task into a step-by-step implementation plan.

Main Task: {concept}

ARCHITECTURE REQUIREMENTS (CRITICAL):
- The project must have a clear, well-organized architecture with folders and subfolders.
- Avoid monolithic single-file design; split logic into modules and packages.
- The plan should consist primarily of Implementation (Impl) steps. Each Impl step must contain a detailed technical specification: exact file paths, classes, functions, and logic to implement.
- Include Verification (Verify) steps only where necessary to check correctness, but NOT as mandatory pairs for every stage.
- The first step may be 'setup_workspace' (id: setup_workspace) to configure file extensions and ignore list, but it's optional.

RULES:
1. Return ONLY a valid JSON array of objects. NO MARKDOWN TEXT OUTSIDE THE ARRAY.
2. Each object must have 'id', 'title' (string), and 'description' (string, detailed technical instructions).
3. Order steps logically to achieve the task.

[PROJECT CONTEXT]
{context}"""

log = logging.getLogger("pig_t3.gui_qt.app")


class GeneratePlanWorker(QObject):
    progress = Signal(int, str)
    done = Signal(list)
    error = Signal(str)
    cancelled = Signal()

    def __init__(
        self,
        root_folder: str,
        concept: str,
        model_name: str,
        settings: dict,
        limit_tokens: int = 12000,
        parent_widget=None,
        llm_client=None,
        context_builder: Callable[[str, str, int], str] | None = None,
        parent: QObject | None = None,
    ):
        super().__init__(parent)
        self._root = root_folder
        self._concept = concept
        self._model_name = model_name
        self._settings = dict(settings)
        self._limit_tokens = limit_tokens
        self._parent_widget = parent_widget
        self._llm = llm_client
        self._context_builder = context_builder

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
            return self._context_builder(self._root, self._concept, self._limit_tokens)
        return self._default_context_build()

    def _default_context_build(self) -> str:
        from ...core.context_optimizer import ContextOptimizer

        try:
            opt = ContextOptimizer(
                root_folder=self._root,
                task=self._concept,
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
                log.warning("context build: skip %s: %s", path, e)
        return "".join(parts)

    def _parse_plan(self, response: str) -> list[dict]:
        if not response:
            return []
        cleaned = clean_json_text(response)
        try:
            data = json.loads(cleaned)
        except Exception:
            return []
        if not isinstance(data, list):
            return []
        result: list[dict] = []
        for i, step in enumerate(data):
            if not isinstance(step, dict):
                continue
            step.setdefault("id", f"step_{i + 1}")
            step.setdefault("title", "")
            step.setdefault("description", "")
            step.setdefault("completed", False)
            step.setdefault("report", "")
            step.setdefault("status", "pending")
            result.append(step)
        return result

    @Slot()
    def run(self) -> None:
        try:
            if self._is_interrupted():
                self.cancelled.emit()
                return

            self.progress.emit(10, "Сбор контекста проекта...")
            context = self._build_context()
            if self._is_interrupted():
                self.cancelled.emit()
                return

            self.progress.emit(30, f"Запрос к {self._model_name}...")
            llm = self._get_llm()
            if llm is None:
                self.error.emit("Модель LLM не выбрана или недоступна")
                return

            prompt = _PLAN_PROMPT_TEMPLATE.format(concept=self._concept, context=context)
            response = llm.ask(prompt)
            if self._is_interrupted():
                self.cancelled.emit()
                return

            self.progress.emit(80, "Разбор плана...")
            plan = self._parse_plan(response)
            if not plan:
                self.error.emit(f"Не удалось распарсить план. Ответ начинался с: {response[:200]}")
                return

            self.progress.emit(100, f"Готово. Шагов: {len(plan)}")
            self.done.emit(plan)
        except Exception as e:
            self.error.emit(str(e))
