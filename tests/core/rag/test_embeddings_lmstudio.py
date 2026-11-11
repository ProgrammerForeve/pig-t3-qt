"""C7a: LMStudioEmbeddings + factory с LM Studio."""

from __future__ import annotations

import pytest

from PIG_T3.core.rag import embeddings as emb_module
from PIG_T3.core.rag.embeddings import (
    LMStudioEmbeddings,
    make_embeddings_backend,
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


# ---------- embed ----------


def test_embed_single_batch(monkeypatch):
    captured = {}

    def fake_post(url, json, headers, timeout):
        captured["url"] = url
        captured["model"] = json["model"]
        captured["input"] = json["input"]
        captured["auth"] = headers.get("Authorization")
        return _FakeResponse(
            {
                "data": [
                    {"embedding": [0.1, 0.2], "index": 0},
                    {"embedding": [0.3, 0.4], "index": 1},
                ]
            }
        )

    monkeypatch.setattr(emb_module.requests, "post", fake_post)
    e = LMStudioEmbeddings("nomic-embed-text-v1.5", "http://x:1234/v1", "key")
    out = e.embed(["a", "b"])
    assert out == [[0.1, 0.2], [0.3, 0.4]]
    assert captured["url"] == "http://x:1234/v1/embeddings"
    assert captured["model"] == "nomic-embed-text-v1.5"
    assert captured["auth"] == "Bearer key"


def test_embed_respects_index_order(monkeypatch):
    """OpenAI возвращает data в произвольном порядке — сортируем по index."""

    def fake_post(url, json, headers, timeout):
        return _FakeResponse(
            {
                "data": [
                    {"embedding": [9.0], "index": 1},
                    {"embedding": [1.0], "index": 0},
                ]
            }
        )

    monkeypatch.setattr(emb_module.requests, "post", fake_post)
    e = LMStudioEmbeddings("m")
    out = e.embed(["a", "b"])
    assert out == [[1.0], [9.0]]


def test_embed_batching(monkeypatch):
    calls: list[list[str]] = []

    def fake_post(url, json, headers, timeout):
        calls.append(list(json["input"]))
        return _FakeResponse({"data": [{"embedding": [0.0], "index": i} for i in range(len(json["input"]))]})

    monkeypatch.setattr(emb_module.requests, "post", fake_post)
    LMStudioEmbeddings("m").embed([f"t{i}" for i in range(70)])
    assert len(calls) == 3
    assert len(calls[0]) == 32
    assert len(calls[1]) == 32
    assert len(calls[2]) == 6


def test_embed_empty(monkeypatch):
    called = []
    monkeypatch.setattr(
        emb_module.requests,
        "post",
        lambda *a, **kw: called.append(1) or _FakeResponse({}),
    )
    assert LMStudioEmbeddings("m").embed([]) == []
    assert not called


def test_embed_http_error_raises(monkeypatch):
    monkeypatch.setattr(
        emb_module.requests,
        "post",
        lambda *a, **kw: _FakeResponse({}, status=500),
    )
    with pytest.raises(RuntimeError, match="LM Studio embed failed"):
        LMStudioEmbeddings("m").embed(["x"])


def test_embed_no_data_raises(monkeypatch):
    monkeypatch.setattr(
        emb_module.requests,
        "post",
        lambda *a, **kw: _FakeResponse({"data": []}),
    )
    with pytest.raises(RuntimeError, match="no embeddings"):
        LMStudioEmbeddings("m").embed(["x"])


def test_dimension_probes(monkeypatch):
    monkeypatch.setattr(
        emb_module.requests,
        "post",
        lambda *a, **kw: _FakeResponse({"data": [{"embedding": [0.0] * 768, "index": 0}]}),
    )
    e = LMStudioEmbeddings("m")
    assert e.dimension == 768
    assert e.model_name == "m"


def test_is_available_true(monkeypatch):
    monkeypatch.setattr(
        emb_module.requests,
        "get",
        lambda *a, **kw: _FakeResponse({"data": []}, status=200),
    )
    assert LMStudioEmbeddings.is_available() is True


def test_is_available_false(monkeypatch):
    def boom(*a, **kw):
        import requests

        raise requests.ConnectionError("refused")

    monkeypatch.setattr(emb_module.requests, "get", boom)
    assert LMStudioEmbeddings.is_available() is False


# ---------- Factory ----------


def test_factory_explicit_lmstudio_requires_model():
    with pytest.raises(ValueError, match="lmstudio_model"):
        make_embeddings_backend("lmstudio")


def test_factory_explicit_lmstudio(monkeypatch):
    e = make_embeddings_backend(
        "lmstudio",
        lmstudio_model="nomic-embed-text-v1.5",
        lmstudio_base_url="http://custom:8080/v1",
    )
    assert isinstance(e, LMStudioEmbeddings)
    assert e._model == "nomic-embed-text-v1.5"
    assert e._base_url == "http://custom:8080/v1"


def test_factory_auto_picks_ollama_first(monkeypatch):
    monkeypatch.setattr(
        emb_module.OllamaEmbeddings,
        "is_available",
        staticmethod(lambda: True),
    )
    monkeypatch.setattr(
        emb_module.LMStudioEmbeddings,
        "is_available",
        staticmethod(lambda *a, **kw: True),
    )
    e = make_embeddings_backend("auto")
    assert isinstance(e, emb_module.OllamaEmbeddings)


def test_factory_auto_picks_lmstudio_when_no_ollama(monkeypatch):
    monkeypatch.setattr(
        emb_module.OllamaEmbeddings,
        "is_available",
        staticmethod(lambda: False),
    )
    monkeypatch.setattr(
        emb_module.LMStudioEmbeddings,
        "is_available",
        staticmethod(lambda *a, **kw: True),
    )
    # get_lmstudio_models возвращает ["nomic-embed-text-v1.5"]
    monkeypatch.setattr(
        "PIG_T3.core.lmstudio_client.get_lmstudio_models",
        lambda *a, **kw: ["nomic-embed-text-v1.5"],
    )
    e = make_embeddings_backend("auto")
    assert isinstance(e, LMStudioEmbeddings)
    assert e._model == "nomic-embed-text-v1.5"


def test_factory_auto_uses_explicit_lmstudio_model(monkeypatch):
    monkeypatch.setattr(
        emb_module.OllamaEmbeddings,
        "is_available",
        staticmethod(lambda: False),
    )
    monkeypatch.setattr(
        emb_module.LMStudioEmbeddings,
        "is_available",
        staticmethod(lambda *a, **kw: True),
    )
    e = make_embeddings_backend("auto", lmstudio_model="custom-model")
    assert isinstance(e, LMStudioEmbeddings)
    assert e._model == "custom-model"


def test_factory_auto_falls_back_to_st(monkeypatch):
    monkeypatch.setattr(
        emb_module.OllamaEmbeddings,
        "is_available",
        staticmethod(lambda: False),
    )
    monkeypatch.setattr(
        emb_module.LMStudioEmbeddings,
        "is_available",
        staticmethod(lambda *a, **kw: False),
    )
    monkeypatch.setattr(
        emb_module.SentenceTransformersEmbeddings,
        "is_available",
        staticmethod(lambda: True),
    )

    # Заглушка ST, чтобы не грузить torch
    class _FakeST:
        def __init__(self, model):
            pass

        def get_sentence_embedding_dimension(self):
            return 384

        def encode(self, texts, show_progress_bar=False):
            return []

    import sys

    fake = type("sentence_transformers", (), {"SentenceTransformer": _FakeST})
    monkeypatch.setitem(sys.modules, "sentence_transformers", fake)

    e = make_embeddings_backend("auto")
    assert isinstance(e, emb_module.SentenceTransformersEmbeddings)


def test_factory_auto_raises_when_none(monkeypatch):
    monkeypatch.setattr(
        emb_module.OllamaEmbeddings,
        "is_available",
        staticmethod(lambda: False),
    )
    monkeypatch.setattr(
        emb_module.LMStudioEmbeddings,
        "is_available",
        staticmethod(lambda *a, **kw: False),
    )
    monkeypatch.setattr(
        emb_module.SentenceTransformersEmbeddings,
        "is_available",
        staticmethod(lambda: False),
    )
    with pytest.raises(RuntimeError, match="Нет доступных"):
        make_embeddings_backend("auto")
