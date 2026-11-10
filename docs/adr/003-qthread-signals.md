# ADR-003: QThread + сигналы/слоты

## Статус
Принято (2026-11)

## Контекст
Legacy использовал `threading.Thread` + `queue.Queue` + `self.after()`
для обновления UI из фонового потока (метод `safe_after`). Это ручная
реализация того, что Qt предоставляет нативно.

## Решение
Все длительные операции (`analyzer.process`, `scanner.scan`,
`ContextOptimizer.optimize`, LLM-вызовы, применение патча) выполняются
в `QThread` с воркерами. Обновление UI — только через сигналы,
подключённые к слотам в главном потоке (queued connection).

## Контракт воркера
`tests/gui_qt/test_threading_contract.py`:
- `QObject`, перемещён в `QThread` через `moveToThread`
- Слот `run()` — вся работа внутри
- Сигналы `progress` / `done` (или `finished`) / `error` / `cancelled`
- НЕ обращается к UI напрямую — только `emit`
- Отмена — через `QThread.currentThread().isInterruptionRequested()`,
  проверяется в `cancel_callback` или в `_sleep_cancellable`

## Последствия
- Все воркеры (`GenerateWorker`, `OptimizeWorker`, `PlanStepWorker`,
  `ApplyWorker`, `ScanWorker`) обязаны проходить контракт
- Cleanup на teardown: `thread.quit() + wait(3000)`, затем
  `worker.moveToThread(QThread.currentThread())` — detach от мёртвого
  потока перед GC (иначе SIGSEGV, см. T-107/T-406)
