"""C5: end-to-end RAG — chunker → embed → store → retrieve → optimizer."""

from __future__ import annotations

from typing import ClassVar

from PIG_T3.core.rag.chunker import chunk_files
from PIG_T3.core.rag.optimizer import RagOptimizer
from PIG_T3.core.rag.retriever import HybridRetriever
from PIG_T3.core.rag.store import VectorStore


class _KeywordBackend:
    """Embeddings, кодирующие наличие ключевых слов в тексте.

    Размерность 8. Каждое измерение соответствует ключевому слову;
    это даёт детерминированное поведение для интеграционного теста
    без реальной Ollama / ST.
    """

    KEYWORDS: ClassVar[list[str]] = [
        "calculate",
        "total",
        "cart",
        "export",
        "csv",
        "login",
        "user",
        "auth",
    ]

    @property
    def model_name(self) -> str:
        return "keyword-fake"

    @property
    def dimension(self) -> int:
        return len(self.KEYWORDS)

    def embed(self, texts):
        out = []
        for t in texts:
            low = t.lower()
            vec = [float(low.count(k)) for k in self.KEYWORDS]
            # нормировка, чтобы косинус был устойчивым
            norm = sum(v * v for v in vec) ** 0.5 or 1.0
            out.append([v / norm for v in vec])
        return out


def _make_project(tmp_path):
    (tmp_path / "billing.py").write_text("def calculate_total(cart):\n    return sum(cart)\n")
    (tmp_path / "export_utils.py").write_text(
        "def export_csv(rows, path):\n"
        "    with open(path, 'w') as f:\n"
        "        for row in rows:\n"
        "            f.write(','.join(row) + '\\n')\n"
    )
    (tmp_path / "auth.py").write_text("def login(user, password):\n    return user == 'admin' and password == 'x'\n")
    return tmp_path


def test_end_to_end_retrieval_by_semantics(tmp_path):
    """Запрос про calculate/cart должен найти billing.py."""
    root = _make_project(tmp_path)
    backend = _KeywordBackend()
    chunks = chunk_files(
        str(root),
        ["billing.py", "export_utils.py", "auth.py"],
    )
    with VectorStore(str(tmp_path / "rag.db"), dimension=backend.dimension) as store:
        vectors = backend.embed([c.content for c in chunks])
        store.add(chunks, vectors)
        retriever = HybridRetriever(store, backend)
        results = retriever.retrieve("calculate total cart", k=2)
        assert results
        assert any(c.path == "billing.py" for c in results)


def test_end_to_end_export_query(tmp_path):
    """Запрос про export/csv находит export_utils.py — то, что BFS
    не нашёл бы, если бы export_utils не был в графе импортов."""
    root = _make_project(tmp_path)
    backend = _KeywordBackend()
    chunks = chunk_files(
        str(root),
        ["billing.py", "export_utils.py", "auth.py"],
    )
    with VectorStore(str(tmp_path / "rag.db"), dimension=backend.dimension) as store:
        store.add(chunks, backend.embed([c.content for c in chunks]))
        retriever = HybridRetriever(store, backend)
        results = retriever.retrieve("export csv rows", k=2)
        assert any(c.path == "export_utils.py" for c in results)


def test_optimizer_builds_index_and_returns_files(tmp_path):
    """RagOptimizer: полный цикл — build index + retrieve + return abs paths."""
    root = _make_project(tmp_path)
    opt = RagOptimizer(
        root_folder=str(root),
        task="export csv rows",
        limit_tokens=5000,
        scan_config={
            "extensions": ".py",
            "ignore_list": "",
            "strict_mode": False,
        },
        backend=_KeywordBackend(),
        force_reindex=True,
    )
    result = opt.optimize()
    assert result
    # export_utils должен быть в результате
    assert any("export_utils.py" in p for p in result)
    # индекс создан
    assert (root / ".pig" / "rag.db").exists()


def test_optimizer_reuses_index(tmp_path):
    """Второй optimize() без force_reindex не переиндексирует."""
    root = _make_project(tmp_path)
    opt1 = RagOptimizer(
        root_folder=str(root),
        task="calculate total",
        limit_tokens=5000,
        scan_config={
            "extensions": ".py",
            "ignore_list": "",
            "strict_mode": False,
        },
        backend=_KeywordBackend(),
        force_reindex=True,
    )
    opt1.optimize()
    db_mtime_1 = (root / ".pig" / "rag.db").stat().st_mtime

    opt2 = RagOptimizer(
        root_folder=str(root),
        task="calculate total",
        limit_tokens=5000,
        scan_config={
            "extensions": ".py",
            "ignore_list": "",
            "strict_mode": False,
        },
        backend=_KeywordBackend(),
        force_reindex=False,
    )
    opt2.optimize()
    db_mtime_2 = (root / ".pig" / "rag.db").stat().st_mtime
    # mtime не изменился → индекс переиспользован
    assert db_mtime_1 == db_mtime_2
