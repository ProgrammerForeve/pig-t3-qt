"""C4b: OptimizeWorker выбирает RagOptimizer vs ContextOptimizer."""

from __future__ import annotations

from PIG_T3.core.context_optimizer import ContextOptimizer
from PIG_T3.core.rag.optimizer import RagOptimizer
from PIG_T3.gui_qt.workers.optimize_worker import OptimizeWorker


class _FakeBackend:
    def __init__(self, dim=4):
        self._dim = dim

    @property
    def model_name(self):
        return "fake"

    @property
    def dimension(self):
        return self._dim

    def embed(self, texts):
        return [[float(len(t))] * self._dim for t in texts]


def test_worker_default_uses_context_optimizer(tmp_path):
    w = OptimizeWorker(
        root_folder=str(tmp_path),
        task="x",
        limit_tokens=1000,
        use_rag=False,
    )
    assert isinstance(w._optimizer, ContextOptimizer)


def test_worker_use_rag_creates_rag_optimizer(tmp_path, monkeypatch):
    """RagOptimizer создаётся, если backend доступен (мокаем)."""
    from PIG_T3.core.rag import optimizer as rag_opt_module

    original = rag_opt_module.RagOptimizer.__init__

    def _patched(self, *args, **kwargs):
        kwargs["backend"] = _FakeBackend()
        original(self, *args, **kwargs)

    monkeypatch.setattr(rag_opt_module.RagOptimizer, "__init__", _patched)

    w = OptimizeWorker(
        root_folder=str(tmp_path),
        task="x",
        limit_tokens=1000,
        use_rag=True,
        scan_config={"extensions": ".py", "ignore_list": ""},
    )
    assert isinstance(w._optimizer, RagOptimizer)


def test_worker_fallback_when_no_backend(tmp_path, monkeypatch):
    """RagOptimizer.__init__ бросает RuntimeError → ContextOptimizer."""
    from PIG_T3.core.rag import optimizer as rag_opt_module

    def _raise(*args, **kwargs):
        raise RuntimeError("no backend")

    monkeypatch.setattr(rag_opt_module.RagOptimizer, "__init__", _raise)
    w = OptimizeWorker(
        root_folder=str(tmp_path),
        task="x",
        limit_tokens=1000,
        use_rag=True,
    )
    assert isinstance(w._optimizer, ContextOptimizer)


def test_worker_passes_scan_config(tmp_path, monkeypatch):
    """scan_config передаётся в RagOptimizer."""
    from PIG_T3.core.rag import optimizer as rag_opt_module

    captured = {}
    original = rag_opt_module.RagOptimizer.__init__

    def _patched(self, *args, **kwargs):
        captured.update(kwargs)
        kwargs["backend"] = _FakeBackend()
        original(self, *args, **kwargs)

    monkeypatch.setattr(rag_opt_module.RagOptimizer, "__init__", _patched)
    cfg = {"extensions": ".py, .md", "ignore_list": "venv"}
    OptimizeWorker(
        root_folder=str(tmp_path),
        task="x",
        limit_tokens=1000,
        use_rag=True,
        scan_config=cfg,
    )
    assert captured["scan_config"] == cfg


def test_worker_on_fallback_emits_progress(tmp_path, qtbot):
    """_on_fallback эмитит progress сигнал."""
    w = OptimizeWorker(
        root_folder=str(tmp_path),
        task="x",
        limit_tokens=1000,
    )
    events: list[int] = []
    w.progress.connect(lambda p, _m: events.append(p))
    w._on_fallback("vector down")
    assert events == [50]
