# ADR-014: Flow Control в JSON-патче

## Status
Accepted (2026-11-14)

## Context
AI-ответ может содержать несколько действий (create/edit/run_command),
которые должны выполняться в определённом порядке с остановкой пайплайна
при критичной ошибке. Legacy-патчер выполнял всё подряд без учёта
зависимостей и без откатов.

## Decision
Ввести 4 опциональных поля на каждое действие:

- `id: str` — уникальный id действия (для ссылок из `depends_on`).
- `depends_on: list[str]` — действие выполняется только если все deps
  завершились `ok`. Skip транзитивный (A fail → B skipped → C skipped).
- `on_failure: "continue" | "abort" | "rollback"` — `abort` останавливает
  весь массив; `rollback` = abort + восстановление `before/` из бэкапа.
- `on_success: "continue" | "abort"` — `abort` останавливает массив
  после успешного действия.

Топологическая сортировка по `depends_on` — детектит цикл и возвращает
ошибку «Циклическая depends_on» до применения.

## Consequences
- `apply_llm_changes` получил `backup_dir` параметр для rollback.
- `ApplyWorker` передаёт `backup_dir = .pig/backups/<uuid>/` и
  сохраняет `_patch_ctx` с `failed_edits` для retry.
- Покрытие: `tests/core/test_patcher_flow_control.py` (9 тестов).
- Совместимость: действия без `id`/`depends_on` работают как раньше.
