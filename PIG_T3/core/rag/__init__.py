"""RAG для PIG-T3 — semantic search по коду проекта."""
from .chunker import Chunk, chunk_file, chunk_files
from .embeddings import (
    EmbeddingsBackend,
    OllamaEmbeddings,
    SentenceTransformersEmbeddings,
    make_embeddings_backend,
)
from .retriever import HybridRetriever, tokenize
from .store import DimensionMismatchError, VectorStore

__all__ = [
    "Chunk",
    "DimensionMismatchError",
    "EmbeddingsBackend",
    "HybridRetriever",
    "OllamaEmbeddings",
    "SentenceTransformersEmbeddings",
    "VectorStore",
    "chunk_file",
    "chunk_files",
    "make_embeddings_backend",
    "tokenize",
]
