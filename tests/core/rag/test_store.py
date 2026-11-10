"""C3: VectorStore на sqlite-vec."""

from __future__ import annotations

import pytest

from PIG_T3.core.rag.chunker import Chunk
from PIG_T3.core.rag.store import DimensionMismatchError, VectorStore


def _chunk(path: str, content: str, start: int = 1) -> Chunk:
    return Chunk(
        path=path,
        content=content,
        kind="function",
        name=path,
        start_line=start,
        end_line=start + content.count("\n"),
    )


def _vec(value: float, dim: int = 4) -> list[float]:
    return [value] * dim


@pytest.fixture
def store(tmp_path):
    s = VectorStore(str(tmp_path / "rag.db"), dimension=4)
    yield s
    s.close()


# ---------- Basic ----------


def test_empty_store(store):
    assert store.count() == 0
    assert store.all_chunks() == []


def test_add_and_count(store):
    chunks = [_chunk("a.py", "def a(): pass"), _chunk("b.py", "def b(): pass")]
    n = store.add(chunks, [_vec(0.1), _vec(0.2)])
    assert n == 2
    assert store.count() == 2


def test_add_mismatch_raises(store):
    chunks = [_chunk("a.py", "x")]
    with pytest.raises(ValueError, match="mismatch"):
        store.add(chunks, [])


def test_add_empty(store):
    assert store.add([], []) == 0


def test_all_chunks_roundtrip(store):
    original = _chunk("sub/mod.py", "def f():\n    return 1", start=10)
    store.add([original], [_vec(0.5)])
    loaded = store.all_chunks()
    assert len(loaded) == 1
    assert loaded[0].path == "sub/mod.py"
    assert loaded[0].start_line == 10
    assert loaded[0].content == "def f():\n    return 1"


# ---------- Search ----------


def test_search_returns_nearest(store):
    store.add(
        [_chunk("near.py", "x"), _chunk("far.py", "y")],
        [_vec(0.1), _vec(0.9)],
    )
    results = store.search(_vec(0.1), k=2)
    assert len(results) == 2
    assert results[0][0].path == "near.py"
    assert results[0][1] < results[1][1]


def test_search_k_limited(store):
    store.add(
        [_chunk(f"f{i}.py", "x") for i in range(5)],
        [_vec(i * 0.1) for i in range(5)],
    )
    results = store.search(_vec(0.0), k=2)
    assert len(results) == 2


def test_search_zero_k(store):
    store.add([_chunk("a.py", "x")], [_vec(0.1)])
    assert store.search(_vec(0.1), k=0) == []


# ---------- Clear / reopen ----------


def test_clear(store):
    store.add([_chunk("a.py", "x")], [_vec(0.1)])
    store.clear()
    assert store.count() == 0
    assert store.all_chunks() == []


def test_reopen_persists(tmp_path):
    path = str(tmp_path / "rag.db")
    s1 = VectorStore(path, dimension=4)
    s1.add([_chunk("a.py", "x")], [_vec(0.1)])
    s1.close()

    s2 = VectorStore(path, dimension=4)
    assert s2.count() == 1
    s2.close()


def test_dimension_mismatch_raises(tmp_path):
    path = str(tmp_path / "rag.db")
    s1 = VectorStore(path, dimension=4)
    s1.add([_chunk("a.py", "x")], [_vec(0.1)])
    s1.close()

    with pytest.raises(DimensionMismatchError, match="dimension"):
        VectorStore(path, dimension=8)
