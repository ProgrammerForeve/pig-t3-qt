"""C7b: OptimizeWorker прокидывает lmstudio_* в make_embeddings_backend."""

from __future__ import annotations

from PIG_T3.core.context_optimizer import ContextOptimizer
from PIG_T3.gui_qt.workers.optimize_worker import OptimizeWorker


class _FakeBackend:
    def __init__(self, *a, **kw):
        self.model_name = "fake"
        self.dimension = 4

    def embed(self, texts):
        return [[0.0] * 4 for _ in texts]


def test_make_rag_optimizer_passes_lmstudio_settings(tmp_path, monkeypatch):
    """make_embeddings_backend получает lmstudio_* из settings."""
    from PIG_T3.core.rag import embeddings as emb_module

    captured = {}

    def _patched(preferred="auto", **kw):
        captured["preferred"] = preferred
        captured.update(kw)
        return _FakeBackend()

    monkeypatch.setattr(emb_module, "make_embeddings_backend", _patched)

    w = OptimizeWorker(
        root_folder=str(tmp_path),
        task="x",
        limit_tokens=1000,
        use_rag=True,
        settings={
            "lmstudio_base_url": "http://custom:8080/v1",
            "lmstudio_api_key": "mykey",
            "lmstudio_embeddings_model": "custom-embed",
        },
    )
    w._make_rag_optimizer(
        root_folder=str(tmp_path),
        task="x",
        limit_tokens=1000,
        scan_config={},
        token_bytes_per_token=4,
    )
    assert captured["preferred"] == "auto"
    assert captured["lmstudio_base_url"] == "http://custom:8080/v1"
    assert captured["lmstudio_api_key"] == "mykey"
    assert captured["lmstudio_model"] == "custom-embed"


def test_make_rag_optimizer_fallback_on_no_backend(tmp_path, monkeypatch):
    """RuntimeError из make_embeddings_backend → ContextOptimizer."""
    from PIG_T3.core.rag import embeddings as emb_module

    def _raise(*a, **kw):
        raise RuntimeError("no backend")

    monkeypatch.setattr(emb_module, "make_embeddings_backend", _raise)

    w = OptimizeWorker(
        root_folder=str(tmp_path),
        task="x",
        limit_tokens=1000,
        use_rag=True,
        settings={},
    )
    opt = w._make_rag_optimizer(
        root_folder=str(tmp_path),
        task="x",
        limit_tokens=1000,
        scan_config={},
        token_bytes_per_token=4,
    )
    assert isinstance(opt, ContextOptimizer)


def test_make_rag_optimizer_empty_embeddings_model_passes_none(tmp_path, monkeypatch):
    """Пустая lmstudio_embeddings_model → lmstudio_model=None."""
    from PIG_T3.core.rag import embeddings as emb_module

    captured = {}

    def _patched(preferred="auto", **kw):
        captured.update(kw)
        return _FakeBackend()

    monkeypatch.setattr(emb_module, "make_embeddings_backend", _patched)

    w = OptimizeWorker(
        root_folder=str(tmp_path),
        task="x",
        limit_tokens=1000,
        use_rag=True,
        settings={"lmstudio_embeddings_model": ""},
    )
    w._make_rag_optimizer(
        root_folder=str(tmp_path),
        task="x",
        limit_tokens=1000,
        scan_config={},
        token_bytes_per_token=4,
    )
    assert captured["lmstudio_model"] is None
