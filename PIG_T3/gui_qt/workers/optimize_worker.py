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
        optimizer: ContextOptimizer | None = None,
        parent: QObject | None = None,
    ):
        super().__init__(parent)
        if optimizer is not None:
            self._optimizer = optimizer
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
            )

    def _is_interrupted(self) -> bool:
        thread = QThread.currentThread()
        return thread is not None and thread.isInterruptionRequested()

    def _on_progress(self, percent: int, msg: str) -> None:
        if self._is_interrupted():
            raise _WorkerCancelled()
        self.progress.emit(percent, msg)

    @Slot()
    def run(self) -> None:
        try:
            selected = self._optimizer.optimize(progress_callback=self._on_progress)
        except _WorkerCancelled:
            self.cancelled.emit()
            return
        except Exception as e:
            self.error.emit(str(e))
            return
        self.done.emit(list(selected))
