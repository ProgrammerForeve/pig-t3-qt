"""C7b: LMStudioModelsWorker + cache helpers."""

from __future__ import annotations

import time

import pytest

from PIG_T3.gui_qt.workers.lmstudio_models_worker import (
    LMStudioModelsWorker,
    cache_is_fresh,
    get_cached_models,
    save_models_to_cache,
)
from tests.helpers.threading import run_worker_and_wait

pytestmark = pytest.mark.threading


def test_worker_returns_models(qtbot, managed_thread, monkeypatch):
    monkeypatch.setattr(
        "PIG_T3.core.lmstudio_client.get_lmstudio_models",
        lambda *a, **kw: ["qwen2.5-coder", "phi3"],
    )
    w = LMStudioModelsWorker()
    t = managed_thread()
    w.moveToThread(t)
    args = run_worker_and_wait(qtbot, w, t, done_signal=w.done)
    assert args == [["qwen2.5-coder", "phi3"]]


def test_worker_error_signal(qtbot, managed_thread, monkeypatch):
    def _boom(*a, **kw):
        raise RuntimeError("connection refused")

    monkeypatch.setattr("PIG_T3.core.lmstudio_client.get_lmstudio_models", _boom)
    w = LMStudioModelsWorker()
    t = managed_thread()
    w.moveToThread(t)
    t.started.connect(w.run)
    errors: list[str] = []
    w.error.connect(errors.append)
    with qtbot.waitSignal(w.error, timeout=2000):
        t.start()
    assert errors
    assert "connection refused" in errors[0]


def test_cache_empty():
    assert get_cached_models({}) == []


def test_cache_bad_shape():
    assert get_cached_models({"lmstudio_models_cache": "junk"}) == []
    assert get_cached_models({"lmstudio_models_cache": {"models": "junk"}}) == []


def test_cache_roundtrip():
    settings = {}
    save_models_to_cache(settings, ["a", "b"])
    assert get_cached_models(settings) == ["a", "b"]


def test_cache_is_fresh_new():
    settings = {}
    save_models_to_cache(settings, ["x"])
    assert cache_is_fresh(settings) is True


def test_cache_is_stale():
    settings = {"lmstudio_models_cache": {"models": ["x"], "ts": time.time() - 120}}
    assert cache_is_fresh(settings) is False


def test_cache_is_fresh_missing():
    assert cache_is_fresh({}) is False
