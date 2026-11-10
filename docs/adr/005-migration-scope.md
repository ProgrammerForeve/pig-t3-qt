# ADR-005: Scope миграции (только GUI)

## Статус
Принято (2026-11)

## Контекст
PIG-T3 включает GUI, core-логику (analyzer, patcher, context_optimizer,
quality, plan_validator, ollama_client) и utils (BomjAPI, clipboard,
dep_installer, majorchic_api). Полная миграция core/utils — огромный
объём, риск регрессий в работающих алгоритмах.

## Решение
Мигрируется **только GUI**: `PIG_T3/gui_qt/`.
`PIG_T3/core/*`, `PIG_T3/utils/*` (кроме `BomjAPI.py`, переписанного
на PySide6 в T-111a) и `PIG_T3/config.py` остаются как есть.

## Обоснование
- Бизнес-логика работает — переписывать ради переписывания нет смысла
- GUI и core связаны через тонкий контракт (dict → результат, callable
  → callback) — легко адаптировать
- Меньше риск регрессий

## Последствия
- `ruff check` таргетирует только `PIG_T3/gui_qt PIG_T3/config.py tests`
  (см. `check.sh`), legacy-файлы не проверяются
- Legacy Tkinter `PIG_T3/gui/` удалён в T-008
- `BomjAPI.py` — единственный `utils/*`, переписанный на PySide6
