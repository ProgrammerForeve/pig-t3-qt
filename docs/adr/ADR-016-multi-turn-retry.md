# ADR-016: Multi-turn Retry

## Status
Accepted (2026-11-14)

## Context
`edit` с `replace_text` может не найти фрагмент (indent,
whitespace, опечатка). Legacy просто писал «фрагмент не найден» —
LLM не получал шанса исправить.

## Decision
Два opt-in механизма в патче:

1. **`on_failure: "retry_with_context"`** на `edit`-действии. Если
   `replace_text` не нашёл, `_find_near_match` через `difflib.SequenceMatcher`
   ищет окно с ratio ≥ 0.6. При нахождении заполняет `FailedEdit`
   (path, find, replace, best_match_line, best_match_ratio, context_lines).
2. **`read_lines`** — новое действие: `{path, start, end}` (≤ 200 строк).
   Возвращает `read_requests` в `patch_context`, чтобы caller мог
   добавить контекст в следующий промпт.

`multi_turn.build_retry_prompt(failed_edits, read_requests, original)`
собирает компактный промпт для LLM: «исправь эти упавшие действия,
предпочитай `replace_lines`».

## Consequences
- `apply_llm_changes` получил `patch_context` param; caller заполняет
  `failed_edits`, `read_requests`, `needs_retry`, `applied_count`.
- `PlanStepWorker` умеет retry в цикле (max_retries=2 по умолчанию),
  `EditorTab._on_retry_with_context` — ручной retry через LLM.
- Покрытие: `tests/core/test_patcher_retry.py` (8 тестов).
