"""LLM-обёртки для OptimizeWorker (T-111b).

Единый интерфейс:
    ``.optimize_context(task: str, meta_list: list[dict]) -> dict[str, int]``

Возвращают ``{relative_path: score_0_100}``. Ключи — те же, что
приходят в ``meta_list[*]["path"]`` (относительно root_folder).

Реализации:
- ``OllamaWrapper`` — sync requests к Ollama (worker-поток)
- ``WebWrapper`` — Playwright через MajorchicAPIAdapter (worker-поток)
- ``BomjWrapper`` — BomjAPI через bridge в main-thread (worker
  блокируется на threading.Event, main-thread показывает QDialog)
"""

from __future__ import annotations

import contextlib
import json
import re
import threading
from typing import Any

from PySide6.QtCore import QObject, Qt, Signal

_PROMPT_TEMPLATE = """You are a Senior Software Architect. Evaluate the importance of each file for the specific TASK.
TASK:
{task}

RULES:
1. Assign an integer score from 0 to 100 for each file.
2. SCORING CRITERIA:
   - 100: file explicitly mentioned in the task by exact name
   - 98-99: clearly intended / crucial to modify
   - 50-97: highly important for understanding logic
   - 30-49: useful context
   - 0-29: unrelated
3. Output ONLY a valid JSON object where keys are file paths and
   values are integer scores.
Example: {{"path/to/file1.py": 100, "path/to/file2.py": 30}}

FILES:
{context}"""


def _build_prompt(task: str, meta_list: list[dict]) -> str:
    parts = []
    for meta in meta_list:
        parts.append(
            f"File: {meta.get('path', '')}\n"
            f"Lines: {meta.get('lines', 0)}\n"
            f"Classes: {', '.join(meta.get('classes', []))}\n"
            f"Functions: {', '.join(meta.get('functions', []))}\n"
        )
    return _PROMPT_TEMPLATE.format(task=task, context="\n".join(parts))


def _parse_scores(response_text: str) -> dict[str, int]:
    """Вытащить {path: score} из ответа LLM. Пусто → {}."""
    if not response_text:
        return {}
    match = re.search(r"\{.*\}", response_text, re.DOTALL)
    if not match:
        return {}
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(k): int(v) for k, v in data.items() if isinstance(v, (int, float))}


# ---------- Ollama ----------


class OllamaWrapper:
    """OllamaClient.optimize_context — sync, безопасен в worker-потоке."""

    def __init__(self, model: str, options: dict | None = None):
        from ...core.ollama_client import OllamaClient

        self._client = OllamaClient(model, options or {})

    def optimize_context(self, task: str, meta_list: list[dict]) -> dict[str, int]:
        return self._client.optimize_context(task, meta_list)


# ---------- Web (DeepSeek / Gemini) ----------


class WebWrapper:
    """MajorchicAPIAdapter — Playwright, sync, безопасен в worker-потоке."""

    def __init__(
        self,
        model_name: str,
        timeout: int = 600,
        stable_count: int = 7,
    ):
        self._backend = "gemini" if "Gemini" in model_name else "deepseek"
        self._expert = "Expert" in model_name
        self._deep_think = "DeepThink" in model_name
        self._timeout = timeout
        self._stable_count = stable_count

    def optimize_context(self, task: str, meta_list: list[dict]) -> dict[str, int]:
        from ...utils.majorchic_api import MajorchicAPIAdapter

        prompt = _build_prompt(task, meta_list)
        adapter = None
        try:
            adapter = MajorchicAPIAdapter(
                backend=self._backend,
                headless=False,
                profile_name="default",
                expert_mode=self._expert,
                deep_think=self._deep_think,
                timeout=self._timeout,
                stable_count=self._stable_count,
            )
            response = adapter.send(prompt)
        finally:
            if adapter is not None:
                with contextlib.suppress(Exception):
                    adapter.close()
        return _parse_scores(response or "")


# ---------- BomjAPI bridge ----------


class _BomjBridge(QObject):
    """Живёт в main-thread. Принимает запросы из worker-потоков.

    Сигнал ``_request(dict)`` эмитится из worker-потока; Qt доставляет
    его слоту ``_on_request`` через queued connection → слот выполняется
    в main-thread, где можно создавать QDialog.
    """

    _request = Signal(dict)

    def __init__(self, parent_widget):
        super().__init__()
        self._parent_widget = parent_widget
        self._event: threading.Event | None = None
        self._result: str = ""
        self._request.connect(self._on_request, Qt.ConnectionType.QueuedConnection)

    def _on_request(self, payload: dict) -> None:
        from ...utils.BomjAPI import BomjAPI

        api = BomjAPI()
        try:
            self._result = api.send(payload, parent=self._parent_widget) or ""
        except Exception as e:
            print(f"BomjAPI error: {e}")
            self._result = ""
        finally:
            if self._event is not None:
                self._event.set()

    def ask(self, payload: dict, timeout: float | None = None) -> str:
        """Вызывается из worker-потока. Блокируется до ответа."""
        event = threading.Event()
        self._event = event
        self._result = ""
        self._request.emit(payload)
        event.wait(timeout=timeout)
        self._event = None
        return self._result


class BomjWrapper:
    """BomjAPI через _BomjBridge. Создаётся в main-thread."""

    def __init__(self, parent_widget):
        self._bridge = _BomjBridge(parent_widget)

    def optimize_context(self, task: str, meta_list: list[dict]) -> dict[str, int]:
        prompt = _build_prompt(task, meta_list)
        response = self._bridge.ask({"model": "BomjAPI", "prompt": prompt})
        return _parse_scores(response)


# ---------- Factory ----------


def make_llm_client(
    model_name: str,
    parent_widget: Any,
    settings: dict,
) -> Any | None:
    """Создать LLM-клиент по имени модели.

    None → None (offline optimize)
    BomjAPI → BomjWrapper(parent_widget)
    Web: * → WebWrapper
    иначе → OllamaWrapper
    """
    if not model_name or model_name == "None":
        return None
    if model_name == "BomjAPI":
        return BomjWrapper(parent_widget)
    if model_name.startswith("Web: "):
        return WebWrapper(
            model_name,
            timeout=int(settings.get("web_api_timeout", 600)),
            stable_count=int(settings.get("web_api_stable_count", 7)),
        )
    return OllamaWrapper(model_name, settings.get("ollama_options", {}))
