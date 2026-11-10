"""HybridRetriever — BM25 + vector + RRF (C3).

RRF (Reciprocal Rank Fusion, Cormack 2009):
    score(doc) = Σ 1 / (k + rank_i)
для каждой ranked-выдачи. Стабильно сливает несовместимые
скоры (BM25 — произвольные числа, vector — косинусные
расстояния) без нормализации.
"""
from __future__ import annotations

import logging
import re
from collections import defaultdict
from rank_bm25 import BM25Okapi

from .chunker import Chunk
from .embeddings import EmbeddingsBackend
from .store import VectorStore

log = logging.getLogger("pig_t3.rag.retriever")


_RRF_K = 60
_BM25_CANDIDATES_MULT = 3


def tokenize(text: str) -> list[str]:
    """Токенайзер для кода и прозы.

    - camelCase / PascalCase → отдельные токены
    - snake_case / dotted.path / kebab-case → отдельные токены
    - lowercase, минимальная длина токена 2 (иначе BM25 зашумлен
      однобуквенными совпадениями из индексов циклов)
    """
    # camelCase → camel Case
    s = re.sub(r"([a-z])([A-Z])", r"\1 \2", text)
    # snake_case / dotted.path / kebab-case → пробелы
    s = re.sub(r"[._\-/]+", " ", s)
    tokens = re.findall(r"\w+", s.lower())
    return [t for t in tokens if len(t) >= 2]

class RobustBM25(BM25Okapi):
    """BM25Okapi с ограниченным снизу IDF для малых корпусов.

    BM25Okapi: idf = log((N - df + 0.5) / (df + 0.5)).
    При N=2, df=1 → idf = log(1) = 0; при N=1 → idf отрицательный.
    Ранжирование разваливается на крошечных корпусах (тесты,
    проекты из 1–2 файлов).

    BM25Plus с delta=1 не подходит: даёт ненулевой score несовпавшим
    документам, в RRF это даёт одинаковые веса при равных рангах.

    Клампим idf к [0.1, ∞). Для реальных корпусов (N > 10) idf > 0.1
    естественно, поведение не меняется. Несовпавшие документы
    остаются с score=0 — фильтр scores[i] > 0 работает корректно.
    """

    _MIN_IDF = 0.1

    def _calc_idf(self, nd):
        super()._calc_idf(nd)
        for word in self.idf:
            self.idf[word] = max(self._MIN_IDF, self.idf[word])



class HybridRetriever:
    def __init__(self, store: VectorStore, backend: EmbeddingsBackend):
        self._store = store
        self._backend = backend
        self._bm25 = None
        self._bm25_chunks: list[Chunk] = []
        self._rebuild_bm25()

    def _rebuild_bm25(self) -> None:
        chunks = self._store.all_chunks()
        self._bm25_chunks = chunks
        if not chunks:
            self._bm25 = None
            return
        tokenized = [tokenize(c.content + " " + c.name) for c in chunks]
        # RobustBM25: BM25Okapi с idf-клэмпом на [0.1, ∞). Гарантирует
        # положительный idf даже на 1-2 документах; несовпавшие
        # остаются с score=0 (фильтр scores[i] > 0 работает).
        self._bm25 = RobustBM25(tokenized)
        log.debug("BM25 rebuilt: %d chunks", len(chunks))

    def refresh(self) -> None:
        """Перестроить BM25 после add/clear."""
        self._rebuild_bm25()

    def retrieve(self, query: str, k: int = 10) -> list[Chunk]:
        if k <= 0 or not query.strip():
            return []
        if self._store.count() == 0:
            return []

        candidates = k * _BM25_CANDIDATES_MULT

        # Vector ranking
        try:
            q_vec = self._backend.embed([query])[0]
            vec_hits = self._store.search(q_vec, k=candidates)
            vec_ranking = [c for c, _ in vec_hits]
        except Exception as e:
            log.warning("vector search failed, BM25-only: %s", e)
            vec_ranking = []

        # BM25 ranking
        if self._bm25 is not None:
            scores = self._bm25.get_scores(tokenize(query))
            order = sorted(
                range(len(scores)), key=lambda i: -scores[i]
            )[:candidates]
            bm25_ranking = [self._bm25_chunks[i] for i in order if scores[i] > 0]
        else:
            bm25_ranking = []

        fused = self._rrf_fuse([vec_ranking, bm25_ranking])
        return fused[:k]

    @staticmethod
    def _rrf_fuse(rankings: list[list[Chunk]], k: int = _RRF_K) -> list[Chunk]:
        scores: dict[tuple[str, int, int], float] = defaultdict(float)
        chunk_map: dict[tuple[str, int, int], Chunk] = {}
        for ranking in rankings:
            for rank, chunk in enumerate(ranking, 1):
                key = (chunk.path, chunk.start_line, chunk.end_line)
                scores[key] += 1.0 / (k + rank)
                chunk_map.setdefault(key, chunk)
        ordered = sorted(scores.items(), key=lambda kv: -kv[1])
        return [chunk_map[key] for key, _ in ordered]
