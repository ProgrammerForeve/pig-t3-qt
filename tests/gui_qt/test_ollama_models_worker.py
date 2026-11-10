"""Day 8: OllamaModelsWorker + cache helpers."""

from __future__ import annotations

import time

import pytest

from PIG_T3.gui_qt.workers.ollama_models_worker import (
    OllamaModelsWorker,
    cache_is_fresh,
    get_cached_models,
    save_models_to_cache,
)
from tests.helpers.threading import run_worker_and_wait

pytestmark = pytest.mark.threading


def test_worker_returns_models(qtbot, managed_thread, monkeypatch):
    monkeypatch.setattr(
        "PIG_T3.core.ollama_client.get_installed_models",
        lambda: ["qwen2.5-coder", "llama3"],
    )
    w = OllamaModelsWorker()
    t = managed_thread()
    w.moveToThread(t)
    args = run_worker_and_wait(qtbot, w, t, done_signal=w.done)
    assert args == [["qwen2.5-coder", "llama3"]]


def test_worker_error_when_ollama_raises(qtbot, managed_thread, monkeypatch):
    def _boom():
        raise RuntimeError("connection refused")

    monkeypatch.setattr("PIG_T3.core.ollama_client.get_installed_models", _boom)
    w = OllamaModelsWorker()
    t = managed_thread()
    w.moveToThread(t)
    t.started.connect(w.run)
    errors: list[str] = []
    w.error.connect(errors.append)
    with qtbot.waitSignal(w.error, timeout=2000):
        t.start()
    assert errors
    assert "connection refused" in errors[0]


def test_worker_empty_list(qtbot, managed_thread, monkeypatch):
    monkeypatch.setattr("PIG_T3.core.ollama_client.get_installed_models", lambda: [])
    w = OllamaModelsWorker()
    t = managed_thread()
    w.moveToThread(t)
    args = run_worker_and_wait(qtbot, w, t, done_signal=w.done)
    assert args == [[]]


# ---------- cache helpers ----------


def test_get_cached_empty():
    assert get_cached_models({}) == []


def test_get_cached_bad_shape():
    assert get_cached_models({"ollama_models_cache": "junk"}) == []
    assert get_cached_models({"ollama_models_cache": {"models": "junk"}}) == []


def test_save_then_get():
    settings = {}
    save_models_to_cache(settings, ["a", "b"])
    assert get_cached_models(settings) == ["a", "b"]


def test_save_coerces_to_str():
    settings = {}
    save_models_to_cache(settings, [1, 2])  # type: ignore[list-item]
    assert get_cached_models(settings) == ["1", "2"]


def test_cache_is_fresh_new():
    settings = {}
    save_models_to_cache(settings, ["x"])
    assert cache_is_fresh(settings) is True


def test_cache_is_stale():
    settings = {"ollama_models_cache": {"models": ["x"], "ts": time.time() - 120}}
    assert cache_is_fresh(settings) is False


def test_cache_is_fresh_missing():
    assert cache_is_fresh({}) is False


def test_cache_is_fresh_bad_ts():
    settings = {"ollama_models_cache": {"models": [], "ts": "junk"}}
    assert cache_is_fresh(settings) is False
