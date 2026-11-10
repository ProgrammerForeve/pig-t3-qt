"""VectorStore на sqlite-vec (C3).

SQLite с расширением vec0: KNN-поиск по embedding'ам в одной
таблице с метаданными. Файл `.pig/rag.db`, ~10 MB на 10k чанков.

Dimension фиксируется при первом создании (meta.dimension).
Если backend меняется (ST 384d → Ollama 768d), store требует
переиндексации — скажет понятной ошибкой.
"""
from __future__ import annotations

import contextlib
import json
import logging
import sqlite3
from pathlib import Path
from typing import Iterable

from .chunker import Chunk

log = logging.getLogger("pig_t3.rag.store")


_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS chunks (
    rowid INTEGER PRIMARY KEY,
    path TEXT NOT NULL,
    kind TEXT NOT NULL,
    name TEXT NOT NULL DEFAULT '',
    start_line INTEGER NOT NULL,
    end_line INTEGER NOT NULL,
    content TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_chunks_path ON chunks(path);
"""


class DimensionMismatchError(RuntimeError):
    """Backend dimension не совпадает с тем, что в индексе."""


class VectorStore:
    """SQLite + sqlite-vec vector store."""

    def __init__(self, path: str, dimension: int):
        self._path = path
        self._dim = dimension
        self._conn = self._open(path)
        self._init_schema()

    @property
    def dimension(self) -> int:
        return self._dim

    @property
    def path(self) -> str:
        return self._path

    def _open(self, path: str) -> sqlite3.Connection:
        try:
            import sqlite_vec
        except ImportError as e:
            raise ImportError(
                "sqlite-vec не установлен. `uv sync` или `pip install sqlite-vec`"
            ) from e

        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)

        conn = sqlite3.connect(path, check_same_thread=False)
        try:
            conn.enable_load_extension(True)
            sqlite_vec.load(conn)
            conn.enable_load_extension(False)
        except Exception as e:
            conn.close()
            raise RuntimeError(
                f"sqlite-vec extension failed to load: {e}. "
                "Убедитесь, что wheel совместим с платформой."
            ) from e
        return conn

    def _init_schema(self) -> None:
        cur = self._conn.cursor()
        for stmt in _SCHEMA.strip().split(";"):
            if stmt.strip():
                cur.execute(stmt)

        # dimension из meta или создаём
        cur.execute("SELECT value FROM meta WHERE key='dimension'")
        row = cur.fetchone()
        if row is None:
            cur.execute(
                "INSERT INTO meta(key, value) VALUES ('dimension', ?)",
                (str(self._dim),),
            )
            cur.execute(
                f"CREATE VIRTUAL TABLE vec_chunks USING vec0("
                f"embedding float[{self._dim}])"
            )
        else:
            stored = int(row[0])
            if stored != self._dim:
                raise DimensionMismatchError(
                    f"Индекс построен с dimension={stored}, "
                    f"backend выдаёт {self._dim}. Удалите {self._path} "
                    "или переиндексируйте проект."
                )
            cur.execute(
                f"CREATE VIRTUAL TABLE IF NOT EXISTS vec_chunks "
                f"USING vec0(embedding float[{self._dim}])"
            )
        self._conn.commit()

    # ---------- Write ----------

    def add(self, chunks: Iterable[Chunk], embeddings: list[list[float]]) -> int:
        chunks = list(chunks)
        if len(chunks) != len(embeddings):
            raise ValueError(
                f"chunks/embeddings mismatch: {len(chunks)} != {len(embeddings)}"
            )
        if not chunks:
            return 0
        cur = self._conn.cursor()
        cur.execute("BEGIN")
        try:
            for chunk, vec in zip(chunks, embeddings):
                cur.execute(
                    "INSERT INTO chunks(path, kind, name, start_line, "
                    "end_line, content) VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        chunk.path, chunk.kind, chunk.name,
                        chunk.start_line, chunk.end_line, chunk.content,
                    ),
                )
                rowid = cur.lastrowid
                cur.execute(
                    "INSERT INTO vec_chunks(rowid, embedding) VALUES (?, ?)",
                    (rowid, json.dumps(vec)),
                )
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise
        return len(chunks)

    def clear(self) -> None:
        cur = self._conn.cursor()
        cur.execute("DELETE FROM chunks")
        cur.execute("DELETE FROM vec_chunks")
        self._conn.commit()

    # ---------- Read ----------

    def count(self) -> int:
        cur = self._conn.cursor()
        cur.execute("SELECT COUNT(*) FROM chunks")
        return int(cur.fetchone()[0])

    def all_chunks(self) -> list[Chunk]:
        cur = self._conn.cursor()
        cur.execute(
            "SELECT path, kind, name, start_line, end_line, content "
            "FROM chunks ORDER BY rowid"
        )
        return [
            Chunk(
                path=row[0], kind=row[1], name=row[2],
                start_line=row[3], end_line=row[4], content=row[5],
            )
            for row in cur.fetchall()
        ]

    def search(
        self, query_vector: list[float], k: int = 10
    ) -> list[tuple[Chunk, float]]:
        """KNN-поиск. Возвращает [(Chunk, distance), ...]."""
        if k <= 0:
            return []
        cur = self._conn.cursor()
        cur.execute(
            "SELECT c.path, c.kind, c.name, c.start_line, c.end_line, "
            "       c.content, v.distance "
            "FROM vec_chunks v JOIN chunks c ON c.rowid = v.rowid "
            "WHERE v.embedding MATCH ? AND k = ? "
            "ORDER BY v.distance",
            (json.dumps(query_vector), k),
        )
        rows = cur.fetchall()
        return [
            (
                Chunk(
                    path=r[0], kind=r[1], name=r[2],
                    start_line=r[3], end_line=r[4], content=r[5],
                ),
                float(r[6]),
            )
            for r in rows
        ]

    def close(self) -> None:
        with contextlib.suppress(Exception):
            self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
