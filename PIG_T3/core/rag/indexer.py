"""ProjectIndexer — построение .pig/rag.db (C4a).

Сканирует файлы проекта, chunk'ит через chunker, эмбеддит батчами
по 32 и складывает в VectorStore. Переиспользует файл .pig/rag.db
между запусками (persist в store.py).
"""
from __future__ import annotations

import logging
import os
from typing import Callable

from .chunker import chunk_files
from .embeddings import EmbeddingsBackend
from .store import VectorStore

log = logging.getLogger("pig_t3.rag.indexer")


_EMBED_BATCH = 32


class ProjectIndexer:
    def __init__(
        self,
        root_folder: str,
        backend: EmbeddingsBackend,
        db_path: str | None = None,
    ):
        self._root = os.path.abspath(root_folder)
        self._backend = backend
        self._db_path = db_path or os.path.join(
            self._root, ".pig", "rag.db"
        )

    @property
    def db_path(self) -> str:
        return self._db_path

    def index_exists(self) -> bool:
        return os.path.exists(self._db_path)

    def open_store(self) -> VectorStore:
        return VectorStore(self._db_path, dimension=self._backend.dimension)

    def build(
        self,
        rel_paths: list[str],
        progress_callback: Callable[[int, int], None] | None = None,
        cancel_callback: Callable[[], bool] | None = None,
    ) -> int:
        """Проиндексировать файлы. Возвращает количество чанков.

        Содержимое существующего .pig/rag.db заменяется целиком
        (clear + rebuild). Инкрементальная индексация — future work.
        """
        if progress_callback:
            progress_callback(0, 1)  # type: ignore[arg-type]
        chunks = chunk_files(self._root, rel_paths)
        if not chunks:
            log.info("indexer: no chunks from %d files", len(rel_paths))
            return 0

        log.info(
            "indexer: %d chunks from %d files", len(chunks), len(rel_paths)
        )
        total = len(chunks)
        embedded = 0

        with self.open_store() as store:
            store.clear()
            for start in range(0, total, _EMBED_BATCH):
                if cancel_callback and cancel_callback():
                    log.info("indexer: cancelled at %d/%d", start, total)
                    return start
                batch = chunks[start : start + _EMBED_BATCH]
                texts = [f"{c.to_header()}\n\n{c.content}" for c in batch]
                vectors = self._backend.embed(texts)
                store.add(batch, vectors)
                embedded = min(start + _EMBED_BATCH, total)
                if progress_callback:
                    progress_callback(embedded, total)

        return embedded
