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

class LMStudioEmbeddings:
    """Embeddings через OpenAI-совместимый /v1/embeddings.

    LM Studio: {base_url}/embeddings, формат OpenAI:
    {"data": [{"embedding": [...], "index": 0}, ...]}.
    """

    def __init__(
        self,
        model: str,
        base_url: str = "http://localhost:1234/v1",
        api_key: str = "lm-studio",
        timeout: int = 60,
    ):
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout
        self._dim: int | None = None

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def dimension(self) -> int:
        if self._dim is None:
            self._dim = len(self.embed(["probe"])[0])
        return self._dim

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        out: list[list[float]] = []
        for i in range(0, len(texts), _OLLAMA_BATCH_SIZE):
            batch = texts[i : i + _OLLAMA_BATCH_SIZE]
            try:
                r = requests.post(
                    f"{self._base_url}/embeddings",
                    json={"model": self._model, "input": batch},
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {self._api_key}",
                    },
                    timeout=self._timeout,
                )
                r.raise_for_status()
                data = r.json()
            except requests.RequestException as e:
                raise RuntimeError(
                    f"LM Studio embed failed (model={self._model}): {e}. "
                    "Проверьте: LM Studio сервер запущен, модель "
                    f"'{self._model}' загружена, /v1/embeddings доступен."
                ) from e
            items = data.get("data", [])
            if not items:
                raise RuntimeError(
                    f"LM Studio returned no embeddings "
                    f"(model={self._model}): {str(data)[:200]}"
                )
            # OpenAI формат: data может быть не отсортирован по index
            items = sorted(items, key=lambda x: x.get("index", 0))
            out.extend(item.get("embedding", []) for item in items)
        if self._dim is None and out:
            self._dim = len(out[0])
        return out

    @staticmethod
    def is_available(
        base_url: str = "http://localhost:1234/v1",
        api_key: str = "lm-studio",
        timeout: int = 2,
    ) -> bool:
        try:
            r = requests.get(
                f"{base_url.rstrip('/')}/models",
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=timeout,
            )
            return r.status_code == 200
        except requests.RequestException:
            return False



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


def make_embeddings_backend(
    preferred: str = "auto",
    *,
    lmstudio_model: str | None = None,
    lmstudio_base_url: str = "http://localhost:1234/v1",
    lmstudio_api_key: str = "lm-studio",
) -> EmbeddingsBackend:
    """Создать backend по имени.

    preferred:
    - "auto": Ollama → LM Studio → sentence-transformers (первый
      доступный)
    - "ollama" / "lmstudio" / "sentence-transformers": строгий выбор

    lmstudio_model: имя модели для LM Studio (обязательно для
    preferred="lmstudio"; для auto — если не задано, берётся первая
    из /v1/models).
    """
    if preferred == "ollama":
        return OllamaEmbeddings()
    if preferred == "sentence-transformers":
        return SentenceTransformersEmbeddings()
    if preferred == "lmstudio":
        if not lmstudio_model:
            raise ValueError(
                "lmstudio_model обязателен для preferred='lmstudio'"
            )
        return LMStudioEmbeddings(
            lmstudio_model, lmstudio_base_url, lmstudio_api_key
        )
    if preferred == "auto":
        if OllamaEmbeddings.is_available():
            log.debug("RAG embeddings: auto-picked Ollama")
            return OllamaEmbeddings()
        if LMStudioEmbeddings.is_available(
            lmstudio_base_url, lmstudio_api_key
        ):
            model = lmstudio_model
            if not model:
                from ...core.lmstudio_client import get_lmstudio_models

                models = get_lmstudio_models(
                    lmstudio_base_url, lmstudio_api_key
                )
                model = models[0] if models else None
            if model:
                log.debug(
                    "RAG embeddings: auto-picked LM Studio (%s)", model
                )
                return LMStudioEmbeddings(
                    model, lmstudio_base_url, lmstudio_api_key
                )
        if SentenceTransformersEmbeddings.is_available():
            log.debug("RAG embeddings: auto-picked sentence-transformers")
            return SentenceTransformersEmbeddings()
        raise RuntimeError(
            "Нет доступных embeddings backend.\n"
            "Вариант 1: запустите Ollama ('ollama serve' + "
            "'ollama pull nomic-embed-text').\n"
            "Вариант 2: запустите LM Studio с embeddings-моделью "
            "(например nomic-embed-text-v1.5) и включите server на "
            "localhost:1234.\n"
            "Вариант 3: установите sentence-transformers "
            "('uv sync --extra rag')."
        )
    raise ValueError(f"Unknown embeddings backend: {preferred!r}")
