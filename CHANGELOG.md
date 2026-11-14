# Changelog

Все значимые изменения проекта PIG-T3. Формат вдохновлён
[Keep a Changelog](https://keepachangelog.com/).

## [2.4.0] — 2026-11-14

### Added

- **ADR-014 (flow control)**: `id`, `depends_on`, `on_failure`
  (`continue|abort|rollback`), `on_success` в JSON-патче. Топосортировка,
  транзитивный skip, deadlock detection, rollback через `before/`.
- **ADR-015 (history tree)**: `HistoryTreeManager` + `HistoryTab` —
  git-like дерево истории с rollback/redo/branch/delete, prune UI,
  фильтр по source, авто-наполнение из EditorTab и PlanTab.
- **ADR-016 (multi-turn retry)**: `on_failure: "retry_with_context"`,
  `read_lines` action, `build_retry_prompt`, 2-level retry в PlanTab
  (🔧 retry_with_context → 🔄 full retry), read_lines UI в EditorTab.
- **ADR-017 (run_command batch)**: `commands[]` XOR `command`,
  `report_mode` (`summary`/`full`), `summarize_output`,
  индекс упавшей команды в summary.

### Fixed

- `EditorTab._show_result_dialog`: F821 `record` undefined.
- `plan_step_worker.py`: `log = ...` внутри triple-quoted промпта.
- `rag/optimizer.py`: двойной `make_embeddings_backend`.
- `context_optimizer.py`: дублированные поля.
- `quality.py`: dead code после return.

### Infrastructure

- `docs/usage.md`, `CONTEXT.md` (глоссарий), `docs/TASKS-ADR.md`.
- `pyproject.toml`: pytest/pytest-qt/pytest-timeout в dev-deps.
- coverage floor 67% → 70%.

---

## [Unreleased]

### Added

- **ADR-014 (flow control)**: `id`, `depends_on`, `on_failure`
  (`continue|abort|rollback`), `on_success` в JSON-патче. Rollback через
  `before/`-снапшот в `.pig/backups/<uuid>/`. Топосортировка по `depends_on`,
  транзитивный skip, deadlock detection до apply.
- **ADR-015 (history tree)**: `HistoryTreeManager` / `HistoryNode` в
  `core/history_tree.py` — data-layer для git-like дерева истории.
  `apply` / `undo` / `redo` / `branch_from`, persist в `.pig/history_tree.json`.
  UI wiring (HistoryTab) — TODO.
- **ADR-016 (multi-turn retry)**: `on_failure: "retry_with_context"` для
  `edit`-действий — fuzzy-поиск через `difflib` при несовпадении `find`,
  `FailedEdit` с `best_match_line` / `best_match_ratio` / `context_lines`.
  Новое действие `read_lines` (≤ 200 строк). `build_retry_prompt` для
  компактного retry-промпта.
- **ADR-017 (run_command batch)**: `commands[]` XOR `command`,
  `report_mode` (`summary` / `full`), `summarize_output` для failure-summary,
  combined `output_path` для batch.
- Документация ADR-014…017 в `docs/adr/`.
- `docs/TASKS-ADR.md` — чек-лист по ADR-014…017.
- `tests/core/test_history_tree.py` — 9 тестов data-layer'а.
- `tests/core/test_multi_turn.py` — 9 тестов `build_retry_prompt` +
  `_trim_original`.

### Fixed

- `EditorTab._show_result_dialog`: F821 — `record` undefined (ломало
  ADR-016 retry button). Init `self._last_patch_record`, захват в локальную
  переменную перед `lambda`.
- `plan_step_worker.py`: `log = ...` оказался внутри triple-quoted
  `_EXEC_PROMPT` — попадал в каждый LLM-промпт. Плюс чужой logger name.
- `rag/optimizer.py`: `make_embeddings_backend(backend_pref)` вызывался
  дважды — второй backend создавался даже когда `backend` передан.
- `context_optimizer.py`: дублированные `self.all_files` / `self.file_metadata`
  и повторный `mod = ...` (merge-артефакт).
- `quality.py`: dead code после `return` в `_read_context`.
- `test_generator.py`: `test_btn_optimize_opens_dialog` содержал `...` вместо
  тела — заменён на реальную проверку.

### Infrastructure

- `pyproject.toml`: `pytest`, `pytest-qt`, `pytest-timeout` добавлены в
  `[project.optional-dependencies] dev`. Без этого `pip install -e .[dev]`
  ставил зависимости без `--timeout`-плагина, а `addopts` в
  `pyproject.toml` требует `--timeout=60` — чистая установка падала.
- `check.sh`: coverage floor 67% → 70% (текущее покрытие 70.62%).
