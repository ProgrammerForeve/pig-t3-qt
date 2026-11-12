"""RagOptimizer — семантический отбор файлов для контекста (C4a).

Совместим с ContextOptimizer.optimize():
    optimize(progress_callback=None, fallback_callback=None) -> list[str]
возвращает абсолютные пути выбранных файлов.

При первом запуске (или при force_reindex) строит .pig/rag.db.
Дальше использует существующий индекс.
"""
from __future__ import annotations

import logging
import os
from typing import Callable

from .embeddings import EmbeddingsBackend, make_embeddings_backend
from .indexer import ProjectIndexer
from .retriever import HybridRetriever

log = logging.getLogger("pig_t3.rag.optimizer")


_DEFAULT_CHUNK_TOKENS = 500
_DEFAULT_BYTES_PER_TOKEN = 4
_MIN_K = 20
_MAX_K = 200
_DEFAULT_EXTENSIONS = ".py, .md, .txt, .json, .yml, .yaml, .toml, .cfg"


class RagOptimizer:
    def __init__(
        self,
        root_folder: str,
        task: str,
        limit_tokens: int,
        scan_config: dict | None = None,
        backend: EmbeddingsBackend | None = None,
        backend_pref: str = "auto",
        force_reindex: bool = False,
        db_path: str | None = None,
        bytes_per_token: int = _DEFAULT_BYTES_PER_TOKEN,
    ):
        self._root = os.path.abspath(root_folder)
        self._task = task
        self._limit = max(1, int(limit_tokens))
        self._scan_config = dict(scan_config or {})
        self._backend = backend or make_embeddings_backend(backend_pref)
        self._force_reindex = force_reindex
        self._bytes_per_token = max(1, int(bytes_per_token))
        self._indexer = ProjectIndexer(
            self._root, self._backend, db_path=db_path
        )
        self._backend = backend or make_embeddings_backend(backend_pref)
        ...
    def optimize(
        self,
        progress_callback: Callable[[int, str], None] | None = None,
        fallback_callback: Callable[[str], None] | None = None,
    ) -> list[str]:
        need_build = self._force_reindex or not self._indexer.index_exists()

        if not need_build:
            try:
                with self._indexer.open_store() as store:
                    if store.count() == 0:
                        need_build = True
                    else:
                        log.info("RAG index ready: %d chunks", store.count())
            except Exception as e:
                log.warning("index open failed, will rebuild: %s", e)
                need_build = True

        if need_build:
            self._build_index(progress_callback)

        if progress_callback:
            progress_callback(90, "Семантический поиск...")

        try:
            with self._indexer.open_store() as store:
                retriever = HybridRetriever(store, self._backend)
                k = max(
                    _MIN_K,
                    min(_MAX_K, self._limit // _DEFAULT_CHUNK_TOKENS),
                )
                chunks = retriever.retrieve(self._task, k=k)
        except Exception as e:
            log.error("RAG retrieval failed: %s", e)
            if fallback_callback:
                fallback_callback(f"RAG поиск упал: {e}")
            return []

        result = self._dedupe_and_cap(chunks)
        if progress_callback:
            total_tokens = sum(
                self._estimate_tokens(p) for p in result
            )
            progress_callback(
                100,
                f"RAG: {len(result)} файлов (~{total_tokens} токенов)",
            )
        return result

    def _build_index(
        self, progress_callback: Callable[[int, str], None] | None
    ) -> None:
        if progress_callback:
            progress_callback(5, "Сканирование проекта...")
        from ..analyzer import ProjectAnalyzer

        analyzer = ProjectAnalyzer()
        cfg = {
            "root_folder": self._root,
            "extensions": self._scan_config.get(
                "extensions", _DEFAULT_EXTENSIONS
            ),
            "ignore_list": self._scan_config.get("ignore_list", ""),
            "strict_mode": self._scan_config.get("strict_mode", False),
            "ignore_self": True,
        }
        try:
            files, _ = analyzer.scan_directory(cfg)
        except Exception as e:
            log.error("scan failed: %s", e)
            return

        rel_paths = [
            os.path.relpath(f, self._root).replace("\\", "/")
            for f, _ in files
        ]
        if not rel_paths:
            if progress_callback:
                progress_callback(85, "Нет файлов для индексации")
            return

        if progress_callback:
            progress_callback(
                10, f"Индексация ({len(rel_paths)} файлов)..."
            )

        def _on_progress(cur: int, total: int) -> None:
            if progress_callback:
                pct = 10 + int(70 * cur / max(1, total))
                progress_callback(pct, f"Индексация: {cur}/{total} чанков")

        indexed = self._indexer.build(rel_paths, progress_callback=_on_progress)
        log.info("RAG index built: %d chunks", indexed)
        if progress_callback:
            progress_callback(85, f"Индекс готов ({indexed} чанков)")

    def _estimate_tokens(self, full_path: str) -> int:
        try:
            return max(1, os.path.getsize(full_path) // self._bytes_per_token)
        except OSError:
            return 1

    def _dedupe_and_cap(self, chunks: list) -> list[str]:
        seen: list[str] = []
        total_tokens = 0
        for chunk in chunks:
            if chunk.path in seen:
                continue
            full = os.path.join(self._root, chunk.path)
            tokens = self._estimate_tokens(full)
            if seen and total_tokens + tokens > self._limit:
                continue
            seen.append(chunk.path)
            total_tokens += tokens
        return [os.path.join(self._root, p) for p in seen]
