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

RULES (CRITICAL — follow exactly):
1. Return a JSON ARRAY [ ... ] — NOT an object {{ ... }}.
2. Start with '[' and end with ']'. NO markdown, NO prose, NO ```json wrapper.
3. DO NOT return keys like 'tools', 'answers', or 'reasoning' — that is the WRONG format.
4. Each element MUST be an object with exactly these keys: 'id' (string), 'title' (string, short), 'description' (string, detailed).
5. Example: [{{"id": "step_1", "title": "Setup", "description": "Create folders and files for..."}}, {{"id": "step_2", ...}}]
6. Order steps logically to achieve the task.

{env_block}

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
            log.warning("_parse_plan: empty response")
            return []
        cleaned = clean_json_text(response)
        try:
            data = json.loads(cleaned)
        except Exception as e:
            log.warning(
                "_parse_plan: json.loads failed: %s; raw=%r",
                e,
                response[:500],
            )
            return []
        if not isinstance(data, list):
            log.warning(
                "_parse_plan: expected list, got %s; keys=%r; raw=%r",
                type(data).__name__,
                sorted(data.keys())[:10] if isinstance(data, dict) else None,
                response[:500],
            )
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

            from ...core.agent_context import (
                collect_environment,
                format_environment_block,
            )

            env_block = format_environment_block(collect_environment(self._root))
            prompt = _PLAN_PROMPT_TEMPLATE.format(
                concept=self._concept,
                context=context,
                env_block=env_block,
            )
            response = llm.ask(prompt)
            if self._is_interrupted():
                self.cancelled.emit()
                return

            self.progress.emit(80, "Разбор плана...")
            plan = self._parse_plan(response)
            if not plan:
                hint = ""
                try:
                    _parsed = json.loads(clean_json_text(response))
                    if isinstance(_parsed, dict):
                        _keys = set(_parsed.keys())
                        if "tools" in _keys or "answers" in _keys:
                            hint = (
                                " Модель вернула {tools, answers} — это "
                                "tool-call формат, а не план. Используйте "
                                "более крупную модель (Qwen2.5-Coder-7B+) "
                                "или BomjAPI."
                            )
                        else:
                            hint = f" Модель вернула object (ключи: {sorted(_keys)[:5]}), ожидался массив."
                except Exception as e:
                    log.debug("_parse_plan hint detection failed: %s", e)
                _preview = response[:300].replace("\n", " ⏎ ")
                self.error.emit(f"Не удалось распарсить план.{hint} Ответ начинался с: {_preview}")
                return
            self.progress.emit(100, f"Готово. Шагов: {len(plan)}")
            self.done.emit(plan)
        except Exception as e:
            self.error.emit(str(e))
