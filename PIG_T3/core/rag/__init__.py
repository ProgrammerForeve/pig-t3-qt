"""RAG для PIG-T3 — semantic search по коду проекта."""
from .chunker import Chunk, chunk_file, chunk_files
from .embeddings import (
    EmbeddingsBackend,
    OllamaEmbeddings,
    SentenceTransformersEmbeddings,
    make_embeddings_backend,
)

__all__ = [
    "Chunk",
    "EmbeddingsBackend",
    "OllamaEmbeddings",
    "SentenceTransformersEmbeddings",
    "chunk_file",
    "chunk_files",
    "make_embeddings_backend",
]
