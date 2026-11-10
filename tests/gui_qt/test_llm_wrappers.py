"""TDD: LLM-обёртки (T-111b)."""

from __future__ import annotations

from PIG_T3.gui_qt.workers import llm_wrappers as lw

# ---------- _build_prompt / _parse_scores ----------


def test_build_prompt_includes_task_and_files():
    p = lw._build_prompt("add CSV", [{"path": "a.py", "lines": 10}])
    assert "add CSV" in p
    assert "a.py" in p
    assert "Lines: 10" in p


def test_parse_scores_valid_json():
    txt = 'Some prose before {"a.py": 90, "b.py": 30} trailing'
    assert lw._parse_scores(txt) == {"a.py": 90, "b.py": 30}


def test_parse_scores_empty():
    assert lw._parse_scores("") == {}
    assert lw._parse_scores("no json here") == {}
    assert lw._parse_scores("{broken") == {}


def test_parse_scores_drops_non_numeric():
    assert lw._parse_scores('{"a.py": 90, "b.py": "bad"}') == {"a.py": 90}


# ---------- OllamaWrapper ----------


def test_ollama_wrapper_delegates(monkeypatch):
    calls = {}

    class _FakeClient:
        def __init__(self, model, options):
            calls["model"] = model
            calls["options"] = options

        def optimize_context(self, task, meta):
            return {"a.py": 42}

    monkeypatch.setattr("PIG_T3.core.ollama_client.OllamaClient", _FakeClient)
    w = lw.OllamaWrapper("qwen2.5", {"num_ctx": 1024})
    assert w.optimize_context("t", [{"path": "a.py"}]) == {"a.py": 42}
    assert calls["model"] == "qwen2.5"


# ---------- WebWrapper ----------


def test_web_wrapper_parses_response(monkeypatch):
    class _FakeAdapter:
        def __init__(self, **kw):
            self.kw = kw

        def send(self, prompt):
            return '{"a.py": 88}'

        def close(self):
            pass

    monkeypatch.setattr("PIG_T3.utils.majorchic_api.MajorchicAPIAdapter", _FakeAdapter)
    w = lw.WebWrapper("Web: DeepSeek", timeout=100, stable_count=3)
    assert w.optimize_context("t", [{"path": "a.py"}]) == {"a.py": 88}


def test_web_wrapper_gemini_backend(monkeypatch):
    captured = {}

    class _FakeAdapter:
        def __init__(self, backend, **kw):
            captured["backend"] = backend

        def send(self, prompt):
            return "{}"

        def close(self):
            pass

    monkeypatch.setattr("PIG_T3.utils.majorchic_api.MajorchicAPIAdapter", _FakeAdapter)
    lw.WebWrapper("Web: Gemini").optimize_context("t", [])
    assert captured["backend"] == "gemini"


# ---------- BomjWrapper ----------


def test_bomj_wrapper_uses_bridge(monkeypatch, qapp):
    class _FakeBridge:
        def __init__(self, parent):
            pass

        def ask(self, payload, timeout=None):
            assert payload["model"] == "BomjAPI"
            return '{"x.py": 77}'

    monkeypatch.setattr(lw, "_BomjBridge", _FakeBridge)
    w = lw.BomjWrapper(None)
    assert w.optimize_context("t", [{"path": "x.py"}]) == {"x.py": 77}


# ---------- make_llm_client ----------


def test_make_llm_client_none():
    assert lw.make_llm_client("None", None, {}) is None
    assert lw.make_llm_client("", None, {}) is None


def test_make_llm_client_bomj(monkeypatch, qapp):
    monkeypatch.setattr(lw, "_BomjBridge", lambda p: None)
    client = lw.make_llm_client("BomjAPI", None, {})
    assert isinstance(client, lw.BomjWrapper)


def test_make_llm_client_web():
    client = lw.make_llm_client("Web: DeepSeek", None, {})
    assert isinstance(client, lw.WebWrapper)


def test_make_llm_client_ollama():
    client = lw.make_llm_client("qwen2.5-coder", None, {})
    assert isinstance(client, lw.OllamaWrapper)
