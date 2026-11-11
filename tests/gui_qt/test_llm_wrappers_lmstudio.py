"""C7a: LMStudioWrapper + make_llm_client с префиксом."""

from __future__ import annotations

from typing import ClassVar

from PIG_T3.gui_qt.workers.llm_wrappers import (
    LMStudioWrapper,
    make_llm_client,
)


class _FakeClient:
    calls: ClassVar[list[str]] = []

    def __init__(self, model, base_url="", api_key="", timeout=0):
        self.model = model
        self.base_url = base_url
        self.api_key = api_key
        self.timeout = timeout

    def chat(self, prompt):
        _FakeClient.calls.append(prompt)
        if "FILES:" in prompt:
            return '{"a.py": 90, "b.py": 30}'
        return "answer text"


def test_lmstudio_wrapper_ask(monkeypatch):
    _FakeClient.calls = []
    monkeypatch.setattr("PIG_T3.core.lmstudio_client.LMStudioClient", _FakeClient)
    w = LMStudioWrapper("qwen2.5-coder")
    assert w.ask("hello") == "answer text"


def test_lmstudio_wrapper_optimize_context(monkeypatch):
    _FakeClient.calls = []
    monkeypatch.setattr("PIG_T3.core.lmstudio_client.LMStudioClient", _FakeClient)
    w = LMStudioWrapper("qwen2.5-coder")
    scores = w.optimize_context("task", [{"path": "a.py", "lines": 10}])
    assert scores == {"a.py": 90, "b.py": 30}


def test_make_llm_client_lmstudio_prefix(monkeypatch):
    _FakeClient.calls = []
    monkeypatch.setattr("PIG_T3.core.lmstudio_client.LMStudioClient", _FakeClient)
    client = make_llm_client(
        "LM Studio: qwen2.5-coder",
        parent_widget=None,
        settings={
            "lmstudio_base_url": "http://custom:8080/v1",
            "lmstudio_api_key": "mykey",
            "lmstudio_timeout": 300,
        },
    )
    assert isinstance(client, LMStudioWrapper)
    # Проверка, что настройки проброшены в LMStudioClient
    assert client._client.base_url == "http://custom:8080/v1"
    assert client._client.api_key == "mykey"
    assert client._client.timeout == 300


def test_make_llm_client_lmstudio_defaults(monkeypatch):
    _FakeClient.calls = []
    monkeypatch.setattr("PIG_T3.core.lmstudio_client.LMStudioClient", _FakeClient)
    client = make_llm_client("LM Studio: phi3", parent_widget=None, settings={})
    assert client._client.base_url == "http://localhost:1234/v1"
    assert client._client.api_key == "lm-studio"
    assert client._client.timeout == 600


def test_make_llm_client_default_ollama(monkeypatch):
    """Без префикса — Ollama (регрессия)."""
    client = make_llm_client("qwen2.5-coder", parent_widget=None, settings={})
    from PIG_T3.gui_qt.workers.llm_wrappers import OllamaWrapper

    assert isinstance(client, OllamaWrapper)
