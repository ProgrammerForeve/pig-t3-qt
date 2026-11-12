"""OptimizeWorker — фоновое сжатие контекста (T-110).

Офлайн-режим (BFS + PageRank + greedy), LLM-клиент = None.
LLM-интеграция — задача T-111.

Контракт (test_threading_contract):
- QObject, moveToThread
- Слот ``run()`` — вся работа внутри
- Сигналы: progress(int, str), done(list), error(str), cancelled()
- Отмена через ``QThread.currentThread().isInterruptionRequested()``
  проверяется в progress_callback (работает в офлайн-режиме, т.к.
  ContextOptimizer часто зовёт callback)
"""

from __future__ import annotations

from PySide6.QtCore import QObject, QThread, Signal, Slot

from ...core.context_optimizer import ContextOptimizer


class _WorkerCancelled(Exception):
    """Внутренний сигнал отмены — прокидывается из progress_callback."""


class OptimizeWorker(QObject):
    progress = Signal(int, str)
    done = Signal(list)  # list[str] — абсолютные пути выбранных файлов
    error = Signal(str)
    cancelled = Signal()

    def __init__(
        self,
        root_folder: str,
        task: str,
        limit_tokens: int,
        bfs_depth: int = 2,
        greedy_llm_weight: float = 0.6,
        greedy_pr_weight: float = 0.3,
        greedy_cc_weight: float = 0.1,
        token_bytes_per_token: int = 4,
        ignore_list: str = "",
        scan_config: dict | None = None,
        use_rag: bool = False,
        settings: dict | None = None,
        optimizer: ContextOptimizer | None = None,
        parent: QObject | None = None,
    ):
        super().__init__(parent)
        self._settings = dict(settings or {})
        self._fallback_callback = None

        if optimizer is not None:
            self._optimizer = optimizer
        elif use_rag:
            self._optimizer = self._make_rag_optimizer(
                root_folder=root_folder,
                task=task,
                limit_tokens=limit_tokens,
                scan_config=scan_config,
                token_bytes_per_token=token_bytes_per_token,
            )
        else:
            self._optimizer = ContextOptimizer(
                root_folder=root_folder,
                task=task,
                limit_tokens=limit_tokens,
                llm_client=None,
                bfs_depth=bfs_depth,
                greedy_llm_weight=greedy_llm_weight,
                greedy_pr_weight=greedy_pr_weight,
                greedy_cc_weight=greedy_cc_weight,
                token_bytes_per_token=token_bytes_per_token,
                ignore_list=ignore_list,
            )

    def _make_rag_optimizer(
        self,
        root_folder: str,
        task: str,
        limit_tokens: int,
        scan_config: dict | None,
        token_bytes_per_token: int,
    ):
        """Создать RagOptimizer с graceful fallback на ContextOptimizer.

        Backend embeddings собирается здесь явно через
        make_embeddings_backend('auto', lmstudio_*) — auto-цепочка
        Ollama → LM Studio → sentence-transformers. LM Studio-настройки
        (base_url, api_key, model) берутся из self._settings, чтобы
        прокинуть их в фабрику C7a.

        Если ничего не доступно (RuntimeError) — fallback на
        ContextOptimizer (BFS+PageRank без LLM).
        """
        try:
            from ...core.rag.embeddings import make_embeddings_backend
            from ...core.rag.optimizer import RagOptimizer

            backend = make_embeddings_backend(
                "auto",
                lmstudio_model=(self._settings.get("lmstudio_embeddings_model") or None),
                lmstudio_base_url=self._settings.get("lmstudio_base_url", "http://localhost:1234/v1"),
                lmstudio_api_key=self._settings.get("lmstudio_api_key", "lm-studio"),
            )
            return RagOptimizer(
                root_folder=root_folder,
                task=task,
                limit_tokens=limit_tokens,
                scan_config=scan_config,
                backend=backend,
                force_reindex=False,
                bytes_per_token=token_bytes_per_token,
            )
        except RuntimeError as e:
            import logging

            logging.getLogger("pig_t3.optimize_worker").warning("RAG недоступен, fallback на ContextOptimizer: %s", e)
            return ContextOptimizer(
                root_folder=root_folder,
                task=task,
                limit_tokens=limit_tokens,
                llm_client=None,
                token_bytes_per_token=token_bytes_per_token,
            )

    def _is_interrupted(self) -> bool:
        thread = QThread.currentThread()
        return thread is not None and thread.isInterruptionRequested()

    def _on_progress(self, percent: int, msg: str) -> None:
        if self._is_interrupted():
            raise _WorkerCancelled()
        self.progress.emit(percent, msg)

    def _on_fallback(self, msg: str) -> None:
        """RAG или vector упали — оптимизатор сам выберет fallback."""
        self.progress.emit(50, f"⚠️ {msg}")

    @Slot()
    def run(self) -> None:
        try:
            selected = self._optimizer.optimize(
                progress_callback=self._on_progress,
                fallback_callback=self._on_fallback,
            )
        except _WorkerCancelled:
            self.cancelled.emit()
            return
        except Exception as e:
            self.error.emit(str(e))
            return
        self.done.emit(list(selected))
