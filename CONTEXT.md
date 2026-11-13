# Глоссарий PIG-T3

Термины из ADR-014…017. См. `docs/adr/` и `docs/usage.md`.

## Патч и действия

**JSON-патч** — ответ LLM: корневой JSON-массив объектов-действий
(`create` / `edit` / `delete` / `move` / `run_command` /
`mark_step_completed` / `read_lines` / `update_settings`). Парсится в
`core/patcher.py::apply_llm_changes`.

**`FailedEdit`** (dataclass, `core/patcher.py`) — описание упавшего
`edit` для retry: `path`, `find`, `replace`, `error`, `best_match_line`,
`best_match_ratio`, `context_lines`, `total_lines`. Заполняется в
`patch_context["failed_edits"]` при `on_failure: "retry_with_context"`.

**`patch_context`** (`dict`, out-param `apply_llm_changes`) — слот
обратной связи для caller'а:
- `failed_edits: list[FailedEdit]` — что упало (для retry)
- `read_requests: list[dict]` — что LLM попросила через `read_lines`
- `needs_retry: bool` — `bool(failed_edits or read_requests)`
- `applied_count: int` — сколько действий применилось

**`Read_lines`** (action) — `{path, start, end}` (≤ 200 строк). Чистое
чтение, не требует `allow_command_execution`. Результат идёт в
`patch_context["read_requests"]`.

## Retry (ADR-016)

**`build_retry_prompt(failed_edits, read_requests, original_response)`**
(`core/multi_turn.py`) — собирает компактный промпт для LLM: «исправь
упавшие действия, предпочитай `replace_lines`, если не хватает
контекста — верни `read_lines`». Обрезает по `max_chars=8000`.

**`_trim_original(raw)`** — вытаскивает `[...]` из `original_response`
(LLM часто оборачивает JSON в markdown), обрезает до 4000 символов.

**`_find_near_match(full_text, find_str, threshold=0.6)`**
(`core/patcher.py`) — fuzzy-поиск через `difflib.SequenceMatcher`.
Возвращает `(line_1based, ratio, context_lines)` или `None`.

## Flow control (ADR-014)

**`depends_on`** — `list[str]` id'шников. Действие выполняется только
если все deps = `ok`. Skip транзитивный (A fail → B skip → C skip).

**`on_failure`** — `continue` (default) | `abort` | `rollback`.
`rollback` = abort + restore `before/` для всех затронутых путей.

**`on_success`** — `continue` (default) | `abort`. `abort` останавливает
массив после успешного действия (редкий кейс: «первое действие
валидирует — если прошло, не продолжать»).

**`_toposort_actions(actions)`** (`core/patcher.py`) — топосортировка
по `depends_on`. Цикл → возвращает строку-ошибку вместо массива.

**`_rollback_patch(root, backup_dir, log)`** — откат:
1. Удалить created (есть в `after/`, нет в `before/`)
2. Restore из `before/` для всего остального

## run_command batch (ADR-017)

**`CommandSpec`** (dataclass, `gui_qt/workers/diff_preview.py`) —
описание одной команды для `DiffDialog`:
- `command: str`
- `output_path: str | None`
- `timeout_sec: int`
- `on_failure: str`
- `batch_index: int | None` — 0-based, `None` если одиночная
- `batch_size: int` — сколько команд в batch

**`summarize_output(text, max_lines=100, min_matches=5)`**
(`core/command_runner.py`) — фильтрует stdout/stderr по failure-паттернам
(pytest/ruff/mypy/pylint/bandit/traceback). Если `< min_matches` —
fallback на последние 20 строк. Обрезает до `max_lines`.

**`report_mode`** — `summary` (одна строка + failure summary) или
`full` (полный stdout/stderr). Default: `summary` для batch, `full`
для одиночной.

## History tree (ADR-015)

**`HistoryTreeManager(root_folder)`** (`core/history_tree.py`) — data-layer
для git-like дерева истории.
- `apply(summary, files, source, backup_id) -> str` — записать ноду
- `undo() -> HistoryNode | None` — current → parent
- `redo() -> HistoryNode | None` — current → newest rolled_back child
- `branch_from(node_id)` — следующий apply пойдёт от node_id

**`HistoryNode`** (dataclass):
- `id: str` — UUID, совпадает с `backup_id` из `ApplyWorker`
- `parent: str | None` — родительская нода
- `children: list[str]` — дочерние ноды
- `action_summary: str` — человекочитаемое описание
- `source: str` — `"editor"` | `"plan"`
- `status: str` — `"applied"` | `"rolled_back"`
- `files: list[str]` — затронутые пути
- `applied_at: str` — ISO timestamp

Persist: `.pig/history_tree.json` — `{current, nodes}`.

## Настройки

**`allow_command_execution`** (bool, default `false`) — разрешить
`run_command` из патча. Без него — `⛔ RUN заблокирован`.

**`command_whitelist`** (str, default `""`) — `"pytest,ruff,git"`.
Пустой = все разрешены. Непустой = блокировать составные команды
(`;`, `&&`, `|`, `$()`) если `command_allow_shell_operators=false`.

**`command_allow_shell_operators`** (bool, default `false`) — при
непустом whitelist разрешать `pytest && ...`, `pytest | tail`.

**`quality_edit_retry_max`** (int, default 2) — сколько раундов
`retry_with_context` пробовать в `PlanStepWorker`.
