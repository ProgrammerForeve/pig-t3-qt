"""C2: embeddings backends (mocked — без реальных Ollama/ST)."""

from __future__ import annotations

import pytest

from PIG_T3.core.rag import embeddings as emb_module
from PIG_T3.core.rag.embeddings import (
    OllamaEmbeddings,
    SentenceTransformersEmbeddings,
    make_embeddings_backend,
)


@pytest.fixture(autouse=True)
def _mock_lmstudio_unavailable(monkeypatch):
    """По умолчанию LM Studio недоступен в тестах C2.

    C7a добавил LMStudioEmbeddings в цепочку auto: Ollama → LM Studio
    → ST. Старые тесты мокали только Ollama и ST. Без этого мока
    is_available() делает реальный HTTP к localhost:1234.
    Тесты в test_embeddings_lmstudio.py явно мокают LM Studio в
    каждом тесте — этот autouse их не касается (отдельный файл).
    """
    from PIG_T3.core.rag.embeddings import LMStudioEmbeddings

    monkeypatch.setattr(
        LMStudioEmbeddings,
        "is_available",
        staticmethod(lambda *a, **kw: False),
    )


class _FakeResponse:
    def __init__(self, json_data, status=200):
        self._json = json_data
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests

            raise requests.HTTPError(f"status {self.status_code}")

    def json(self):
        return self._json


# ---------- OllamaEmbeddings ----------


def test_ollama_empty_input(monkeypatch):
    called = []
    monkeypatch.setattr(
        emb_module.requests,
        "post",
        lambda *a, **kw: called.append(1) or _FakeResponse({"embeddings": []}),
    )
    out = OllamaEmbeddings().embed([])
    assert out == []
    assert not called


def test_ollama_single_batch(monkeypatch):
    captured = {}

    def fake_post(url, json, timeout):
        captured["url"] = url
        captured["model"] = json["model"]
        captured["input"] = json["input"]
        return _FakeResponse({"embeddings": [[0.1, 0.2], [0.3, 0.4]]})

    monkeypatch.setattr(emb_module.requests, "post", fake_post)
    out = OllamaEmbeddings(model="nomic-embed-text").embed(["a", "b"])
    assert out == [[0.1, 0.2], [0.3, 0.4]]
    assert captured["model"] == "nomic-embed-text"
    assert captured["input"] == ["a", "b"]
    assert "api/embed" in captured["url"]


def test_ollama_batching(monkeypatch):
    """70 texts → 3 calls (32 + 32 + 6)."""
    calls: list[list[str]] = []

    def fake_post(url, json, timeout):
        calls.append(list(json["input"]))
        return _FakeResponse({"embeddings": [[0.0]] * len(json["input"])})

    monkeypatch.setattr(emb_module.requests, "post", fake_post)
    OllamaEmbeddings().embed([f"t{i}" for i in range(70)])
    assert len(calls) == 3
    assert len(calls[0]) == 32
    assert len(calls[1]) == 32
    assert len(calls[2]) == 6


def test_ollama_http_error_raises(monkeypatch):
    monkeypatch.setattr(
        emb_module.requests,
        "post",
        lambda *a, **kw: _FakeResponse({}, status=500),
    )
    with pytest.raises(RuntimeError, match="Ollama embed failed"):
        OllamaEmbeddings().embed(["x"])


def test_ollama_no_embeddings_raises(monkeypatch):
    monkeypatch.setattr(
        emb_module.requests,
        "post",
        lambda *a, **kw: _FakeResponse({"embeddings": []}),
    )
    with pytest.raises(RuntimeError, match="no embeddings"):
        OllamaEmbeddings().embed(["x"])


def test_ollama_dim_from_response(monkeypatch):
    monkeypatch.setattr(
        emb_module.requests,
        "post",
        lambda *a, **kw: _FakeResponse({"embeddings": [[0.0] * 768]}),
    )
    backend = OllamaEmbeddings()
    assert backend.dimension == 768
    assert backend.model_name == "nomic-embed-text"


def test_ollama_is_available(monkeypatch):
    monkeypatch.setattr(
        emb_module.requests,
        "get",
        lambda *a, **kw: _FakeResponse({"models": []}, status=200),
    )
    assert OllamaEmbeddings.is_available() is True


def test_ollama_not_available(monkeypatch):
    def boom(*a, **kw):
        import requests

        raise requests.ConnectionError("refused")

    monkeypatch.setattr(emb_module.requests, "get", boom)
    assert OllamaEmbeddings.is_available() is False


# ---------- SentenceTransformersEmbeddings ----------


def test_st_raises_without_package(monkeypatch):
    """ImportError с понятным сообщением."""
    import builtins

    real_import = builtins.__import__

    def blocked(name, *a, **kw):
        if name.startswith("sentence_transformers"):
            raise ImportError("not installed")
        return real_import(name, *a, **kw)

    monkeypatch.setattr(builtins, "__import__", blocked)
    with pytest.raises(ImportError, match="sentence-transformers не установлен"):
        SentenceTransformersEmbeddings()


def test_st_wraps_encode(monkeypatch):
    class _FakeST:
        def __init__(self, model):
            self.model = model

        def get_sentence_embedding_dimension(self):
            return 384

        def encode(self, texts, show_progress_bar=False):
            class _V:
                def __init__(self, vals):
                    self._vals = vals

                def tolist(self):
                    return self._vals

            return [_V([0.1 * (i + 1)] * 3) for i, _ in enumerate(texts)]

    import sys

    fake_module = type(
        "sentence_transformers",
        (),
        {"SentenceTransformer": _FakeST},
    )
    monkeypatch.setitem(sys.modules, "sentence_transformers", fake_module)

    backend = SentenceTransformersEmbeddings(model="all-MiniLM-L6-v2")
    assert backend.dimension == 384
    assert backend.model_name == "all-MiniLM-L6-v2"
    out = backend.embed(["a", "b"])
    assert len(out) == 2
    assert len(out[0]) == 3


def test_st_empty_input(monkeypatch):
    class _FakeST:
        def __init__(self, model):
            pass

        def get_sentence_embedding_dimension(self):
            return 384

        def encode(self, texts, show_progress_bar=False):
            return []

    import sys

    fake_module = type(
        "sentence_transformers",
        (),
        {"SentenceTransformer": _FakeST},
    )
    monkeypatch.setitem(sys.modules, "sentence_transformers", fake_module)
    backend = SentenceTransformersEmbeddings()
    assert backend.embed([]) == []


def test_st_is_available_true(monkeypatch):
    import sys

    fake_module = type("sentence_transformers", (), {})
    monkeypatch.setitem(sys.modules, "sentence_transformers", fake_module)
    assert SentenceTransformersEmbeddings.is_available() is True


def test_st_is_available_false(monkeypatch):
    import builtins

    real_import = builtins.__import__

    def blocked(name, *a, **kw):
        if name.startswith("sentence_transformers"):
            raise ImportError
        return real_import(name, *a, **kw)

    monkeypatch.setattr(builtins, "__import__", blocked)
    assert SentenceTransformersEmbeddings.is_available() is False


# ---------- Factory ----------


def test_factory_ollama(monkeypatch):
    monkeypatch.setattr(OllamaEmbeddings, "is_available", staticmethod(lambda: True))
    backend = make_embeddings_backend("auto")
    assert isinstance(backend, OllamaEmbeddings)


def test_factory_st_when_no_ollama(monkeypatch):
    monkeypatch.setattr(OllamaEmbeddings, "is_available", staticmethod(lambda: False))
    monkeypatch.setattr(
        SentenceTransformersEmbeddings,
        "is_available",
        staticmethod(lambda: True),
    )

    class _FakeST:
        def __init__(self, model):
            pass

        def get_sentence_embedding_dimension(self):
            return 384

        def encode(self, texts, show_progress_bar=False):
            return []

    import sys

    fake_module = type(
        "sentence_transformers",
        (),
        {"SentenceTransformer": _FakeST},
    )
    monkeypatch.setitem(sys.modules, "sentence_transformers", fake_module)

    backend = make_embeddings_backend("auto")
    assert isinstance(backend, SentenceTransformersEmbeddings)


def test_factory_raises_when_none(monkeypatch):
    monkeypatch.setattr(OllamaEmbeddings, "is_available", staticmethod(lambda: False))
    monkeypatch.setattr(
        SentenceTransformersEmbeddings,
        "is_available",
        staticmethod(lambda: False),
    )
    with pytest.raises(RuntimeError, match="Нет доступных"):
        make_embeddings_backend("auto")


def test_factory_unknown_raises():
    with pytest.raises(ValueError, match="Unknown"):
        make_embeddings_backend("bogus")


def test_factory_explicit_ollama(monkeypatch):
    backend = make_embeddings_backend("ollama")
    assert isinstance(backend, OllamaEmbeddings)


def test_factory_explicit_st(monkeypatch):
    class _FakeST:
        def __init__(self, model):
            pass

        def get_sentence_embedding_dimension(self):
            return 384

        def encode(self, texts, show_progress_bar=False):
            return []

    import sys

    fake_module = type(
        "sentence_transformers",
        (),
        {"SentenceTransformer": _FakeST},
    )
    monkeypatch.setitem(sys.modules, "sentence_transformers", fake_module)
    backend = make_embeddings_backend("sentence-transformers")
    assert isinstance(backend, SentenceTransformersEmbeddings)
