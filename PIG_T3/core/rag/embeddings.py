"""Embeddings backends для RAG (C2).

Единый интерфейс:
    embed(texts: list[str]) -> list[list[float]]
    dimension -> int
    model_name -> str

Две реализации:
- OllamaEmbeddings: /api/embed через requests (Ollama уже в проекте)
- SentenceTransformersEmbeddings: lazy import, опциональный extra

Фабрика make_embeddings_backend(preferred):
- "auto" → Ollama если запущена, иначе ST, иначе RuntimeError с
  инструкцией как поднять один из них
- "ollama" / "sentence-transformers" → строго этот backend
"""
from __future__ import annotations

import logging
from typing import Protocol

import requests

log = logging.getLogger("pig_t3.rag.embeddings")


_OLLAMA_EMBED_URL = "http://localhost:11434/api/embed"
_OLLAMA_TAGS_URL = "http://localhost:11434/api/tags"
_DEFAULT_OLLAMA_MODEL = "nomic-embed-text"     # 768d, популярная
_DEFAULT_ST_MODEL = "all-MiniLM-L6-v2"         # 384d, быстрая
_OLLAMA_BATCH_SIZE = 32
_OLLAMA_TIMEOUT = 60


class EmbeddingsBackend(Protocol):
    @property
    def model_name(self) -> str: ...
    @property
    def dimension(self) -> int: ...
    def embed(self, texts: list[str]) -> list[list[float]]: ...


# ---------- Ollama ----------


class OllamaEmbeddings:
    """Embeddings через Ollama /api/embed (батчи по 32)."""

    def __init__(
        self,
        model: str = _DEFAULT_OLLAMA_MODEL,
        url: str = _OLLAMA_EMBED_URL,
        timeout: int = _OLLAMA_TIMEOUT,
    ):
        self._model = model
        self._url = url
        self._timeout = timeout
        self._dim: int | None = None

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def dimension(self) -> int:
        if self._dim is None:
            # probe: один короткий embed, чтобы узнать размерность
            self._dim = len(self.embed(["probe"])[0])
        return self._dim

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        out: list[list[float]] = []
        for i in range(0, len(texts), _OLLAMA_BATCH_SIZE):
            batch = texts[i : i + _OLLAMA_BATCH_SIZE]
            try:
                response = requests.post(
                    self._url,
                    json={"model": self._model, "input": batch},
                    timeout=self._timeout,
                )
                response.raise_for_status()
                data = response.json()
            except requests.RequestException as e:
                raise RuntimeError(
                    f"Ollama embed failed (model={self._model}): {e}. "
                    f"Проверьте 'ollama serve' и 'ollama pull {self._model}'"
                ) from e
            embeddings = data.get("embeddings", [])
            if not embeddings:
                raise RuntimeError(
                    f"Ollama returned no embeddings (model={self._model}): {data}"
                )
            out.extend(embeddings)
        if self._dim is None and out:
            self._dim = len(out[0])
        return out

    @staticmethod
    def is_available(
        tags_url: str = _OLLAMA_TAGS_URL, timeout: int = 2
    ) -> bool:
        try:
            r = requests.get(tags_url, timeout=timeout)
            return r.status_code == 200
        except requests.RequestException:
            return False


# ---------- sentence-transformers ----------


class SentenceTransformersEmbeddings:
    """Embeddings через sentence-transformers (опциональный extra)."""

    def __init__(self, model: str = _DEFAULT_ST_MODEL):
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as e:
            raise ImportError(
                "sentence-transformers не установлен. "
                "Вариант 1: uv sync --extra rag "
                "(тянет ~500 МБ torch). "
                "Вариант 2: используйте Ollama с моделью "
                "'nomic-embed-text'."
            ) from e
        self._model = model
        self._st = SentenceTransformer(model)
        self._dim = int(self._st.get_sentence_embedding_dimension())

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def dimension(self) -> int:
        return self._dim

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        vecs = self._st.encode(texts, show_progress_bar=False)
        return [v.tolist() for v in vecs]

    @staticmethod
    def is_available() -> bool:
        try:
            import sentence_transformers  # noqa: F401

            return True
        except ImportError:
            return False


# ---------- Factory ----------


def make_embeddings_backend(preferred: str = "auto") -> EmbeddingsBackend:
    """Создать backend по имени."""
    if preferred == "ollama":
        return OllamaEmbeddings()
    if preferred == "sentence-transformers":
        return SentenceTransformersEmbeddings()
    if preferred == "auto":
        if OllamaEmbeddings.is_available():
            log.debug("RAG embeddings: auto-picked Ollama")
            return OllamaEmbeddings()
        if SentenceTransformersEmbeddings.is_available():
            log.debug("RAG embeddings: auto-picked sentence-transformers")
            return SentenceTransformersEmbeddings()
        raise RuntimeError(
            "Нет доступных embeddings backend.\n"
            "Вариант 1: запустите Ollama ('ollama serve' + "
            "'ollama pull nomic-embed-text').\n"
            "Вариант 2: установите sentence-transformers "
            "('uv sync --extra rag')."
        )
    raise ValueError(f"Unknown embeddings backend: {preferred!r}")
