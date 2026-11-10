"""C4a: ProjectIndexer — build/clear, mock embeddings."""

from __future__ import annotations

from PIG_T3.core.rag.indexer import ProjectIndexer


class _FakeBackend:
    def __init__(self, dim: int = 4):
        self._dim = dim
        self.calls: list[list[str]] = []

    @property
    def model_name(self) -> str:
        return "fake"

    @property
    def dimension(self) -> int:
        return self._dim

    def embed(self, texts):
        self.calls.append(list(texts))
        return [[float(len(t) % 10)] * self._dim for t in texts]


def _make_project(tmp_path):
    (tmp_path / "a.py").write_text("def f():\n    return 1\n")
    (tmp_path / "b.py").write_text("class C:\n    def m(self):\n        pass\n")
    (tmp_path / "doc.md").write_text("# hi\n")
    return tmp_path


def test_build_creates_index(tmp_path):
    _make_project(tmp_path)
    backend = _FakeBackend()
    indexer = ProjectIndexer(str(tmp_path), backend)
    assert not indexer.index_exists()
    n = indexer.build(["a.py", "b.py", "doc.md"])
    assert n >= 3
    assert indexer.index_exists()


def test_build_empty_list(tmp_path):
    backend = _FakeBackend()
    indexer = ProjectIndexer(str(tmp_path), backend)
    n = indexer.build([])
    assert n == 0


def test_build_progress_callback(tmp_path):
    _make_project(tmp_path)
    backend = _FakeBackend()
    indexer = ProjectIndexer(str(tmp_path), backend)
    events: list[tuple[int, int]] = []
    indexer.build(
        ["a.py", "b.py"],
        progress_callback=lambda c, t: events.append((c, t)),
    )
    assert events
    assert events[-1][0] == events[-1][1]


def test_build_cancel(tmp_path):
    _make_project(tmp_path)
    backend = _FakeBackend()
    indexer = ProjectIndexer(str(tmp_path), backend)
    n = indexer.build(
        ["a.py", "b.py", "doc.md"],
        cancel_callback=lambda: True,
    )
    assert n == 0


def test_build_replaces_previous(tmp_path):
    _make_project(tmp_path)
    backend = _FakeBackend()
    indexer = ProjectIndexer(str(tmp_path), backend)
    indexer.build(["a.py"])
    indexer.build(["b.py"])
    # индекс заменён — второй build не накапливает
    with indexer.open_store() as store:
        paths = {c.path for c in store.all_chunks()}
    assert paths == {"b.py"}


def test_build_missing_file_skipped(tmp_path):
    backend = _FakeBackend()
    indexer = ProjectIndexer(str(tmp_path), backend)
    n = indexer.build(["missing.py"])
    assert n == 0
