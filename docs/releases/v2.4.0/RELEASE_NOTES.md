# PIG-T3 2.4.0

**Дата:** 2026-11-14

## Что нового

### Flow control в JSON-патче (ADR-014)
- `id`, `depends_on`, `on_failure`, `on_success`.
- Rollback через `.pig/backups/<id>/before/`.

### Git-like дерево истории (ADR-015)
- Новая вкладка «🕐 История»: дерево apply/undo/redo, rollback/redo,
  branch, delete, prune, фильтр по source (Editor/Plan).
- Авто-наполнение из EditorTab и PlanTab.

### Retry с контекстом (ADR-016)
- `retry_with_context` для edit — fuzzy-поиск через difflib.
- `read_lines` — запрос контекста у LLM.
- 2-level retry в PlanTab, UI для read_lines в EditorTab.

### run_command batch (ADR-017)
- `commands[]` XOR `command`, `report_mode`, индекс упавшей команды.

## Установка

```bash
pip install pig-t3==2.4.0
```

Или из исходников:

```bash
git checkout v2.4.0
pip install -e .
```
