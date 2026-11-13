# ADR-015: Git-like Tree History

## Status
Proposed (data layer implemented, UI wiring — TODO)

## Context
EditorTab использует плоский `history_stack: list[dict]` с cap=10 и
`redo_stack: list[dict]`. Это работает для линейного undo/redo, но не
позволяет:
- ветвить историю (применить патч, откатить, применить другой);
- видеть дерево изменений в UI;
- persist-ить историю в `.pig/`.

## Decision
`HistoryTreeManager` (в `core/history_tree.py`):
- `apply(summary, files, source, backup_id)` → создаёт `HistoryNode`,
  линкует к `current`, эмитит в JSON `.pig/history_tree.json`.
- `undo()` → `current = node.parent`, `node.status = "rolled_back"`.
- `redo()` → выбирает из `node.children` тот, что rolled_back, по
  `applied_at`; ставит `status = "applied"`.
- `branch_from(node_id)` → `current = node_id` (следующий apply будет
  ветвью от этой ноды).

`backup_id` = `patch_id` из `ApplyWorker`, чтобы история ссылалась на
бэкап `.pig/backups/<id>/`.

## Consequences
- Data layer готов и покрыт `tests/core/test_history_tree.py`.
- UI-wiring (EditorTab → HistoryTreeManager) НЕ сделан — текущий
  `history_stack` в EditorTab не мигрирован; это отдельная задача
  (требует замены `.history_stack` / `.redo_stack` и переписать
  `_on_apply_done`, `_on_undo`, `_on_redo`).
- `test_editor_tab_extra.py::test_history_cap_at_10` пока опирается на
  старый плоский стек.
