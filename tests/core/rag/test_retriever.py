"""C3: HybridRetriever — BM25 + vector + RRF."""

from __future__ import annotations

import pytest

from PIG_T3.core.rag.chunker import Chunk
from PIG_T3.core.rag.retriever import HybridRetriever, tokenize
from PIG_T3.core.rag.store import VectorStore


class _FakeBackend:
    """Embeddings backend, который возвращает векторы по ключевым словам."""

    def __init__(self, dim: int = 4):
        self._dim = dim

    @property
    def model_name(self) -> str:
        return "fake"

    @property
    def dimension(self) -> int:
        return self._dim

    def embed(self, texts):
        # Тривиальный "embedding": длина текста в каждом слоте
        return [[len(t) / 100.0] * self._dim for t in texts]


def _chunk(path, content, start=1):
    return Chunk(
        path=path,
        content=content,
        kind="function",
        name=path,
        start_line=start,
        end_line=start + content.count("\n"),
    )


@pytest.fixture
def store(tmp_path):
    s = VectorStore(str(tmp_path / "rag.db"), dimension=4)
    yield s
    s.close()


# ---------- Tokenizer ----------


def test_tokenize_snake_case():
    assert "calculate_total" not in tokenize("calculate_total")
    assert "calculate" in tokenize("calculate_total")
    assert "total" in tokenize("calculate_total")


def test_tokenize_camel_case():
    tokens = tokenize("calculateTotal")
    assert "calculate" in tokens
    assert "total" in tokens


def test_tokenize_lowercases():
    assert "hello" in tokenize("HELLO World")


# ---------- Retrieval ----------


def test_retrieve_empty_store(store):
    r = HybridRetriever(store, _FakeBackend())
    assert r.retrieve("query") == []


def test_retrieve_empty_query(store):
    store.add([_chunk("a.py", "x")], [[0.1] * 4])
    r = HybridRetriever(store, _FakeBackend())
    assert r.retrieve("") == []


def test_retrieve_finds_by_content(store):
    store.add(
        [
            _chunk("billing.py", "def calculate_total(cart):\n    return sum(cart)"),
            _chunk("auth.py", "def login(user, password):\n    return True"),
        ],
        [[0.5] * 4, [0.3] * 4],
    )
    r = HybridRetriever(store, _FakeBackend())
    results = r.retrieve("calculate total", k=2)
    assert results
    assert results[0].path == "billing.py"


def test_retrieve_k_limits(store):
    store.add(
        [_chunk(f"f{i}.py", f"def f{i}(): pass") for i in range(5)],
        [[0.1 * i] * 4 for i in range(5)],
    )
    r = HybridRetriever(store, _FakeBackend())
    assert len(r.retrieve("function", k=2)) == 2


# ---------- RRF fusion ----------


def test_rrf_fuse_combines_rankings():
    a = _chunk("a.py", "a", start=1)
    b = _chunk("b.py", "b", start=1)
    c = _chunk("c.py", "c", start=1)

    # a, b, c в первом; b, c, a во втором
    result = HybridRetriever._rrf_fuse([[a, b, c], [b, c, a]])
    # b встречается 2-м и 1-м → выше всех
    assert result[0].path == "b.py"
    # все три присутствуют
    assert {r.path for r in result} == {"a.py", "b.py", "c.py"}


def test_rrf_fuse_dedupes():
    a = _chunk("a.py", "a", start=1)
    result = HybridRetriever._rrf_fuse([[a, a]])
    assert len(result) == 1


def test_rrf_fuse_empty():
    assert HybridRetriever._rrf_fuse([[], []]) == []


# ---------- Refresh ----------


def test_refresh_after_add(store):
    r = HybridRetriever(store, _FakeBackend())
    assert r.retrieve("anything") == []
    store.add([_chunk("new.py", "def novel_function(): pass")], [[0.1] * 4])
    r.refresh()
    results = r.retrieve("novel function")
    assert any(c.path == "new.py" for c in results)


# ---------- BM25 fallback ----------


def test_retrieve_works_without_vector(store):
    """Если vector search падает — BM25 всё равно даёт результат."""

    class _BrokenBackend(_FakeBackend):
        def embed(self, texts):
            raise RuntimeError("backend down")

    store.add(
        [_chunk("auth.py", "def login(user, password): pass")],
        [[0.5] * 4],
    )
    r = HybridRetriever(store, _BrokenBackend())
    results = r.retrieve("login password")
    assert any(c.path == "auth.py" for c in results)
