# Задачи по ADR-014…017

Легенда: `[x]` выполнено · `[ ]` в работе · `[~]` частично · `[-]` отложено / YAGNI

---

## ADR-014 — Flow control (id / depends_on / on_failure / on_success / rollback)

### Базис (в коде)
- [x] `patcher.py::apply_llm_changes(backup_dir=...)` — параметр
- [x] `_toposort_actions()` — топосортировка по `depends_on`
- [x] `_rollback_patch()` — откат `before/` + удаление created (`after` без `before`)
- [x] Валидация дубликатов `id` до apply
- [x] Skip по `depends_on` (транзитивный, каскад fail-safe)
- [x] `on_failure: "abort"` и `"rollback"` для всех actions
- [x] `on_success: "abort"`
- [x] `PIPELINE ABORTED` в лог при `on_failure`

### P0 — закрыто (2026-11-14)
- [x] `analyzer._write_patching_instructions` — блок `FLOW CONTROL` + пример DAG (стр. 180-189 `analyzer.py`)
- [x] `tests/core/test_patcher_flow_control.py` — 11 тестов:
  - `test_depends_on_ok` / `test_depends_on_skip` / `test_depends_on_transitive_skip`
  - `test_deadlock` / `test_duplicate_ids`
  - `test_rollback_restore` / `test_rollback_deletes_created`
  - `test_on_failure_abort` / `test_on_success_abort`
  - `test_command_xor_commands` / `test_backward_compat_no_id`
- [x] `test_analyzer_prompt.py` — `assert "depends_on" in buf.getvalue()` (в `test_prompt_has_flow_control`)

### P1
- [ ] `on_failure: "retry_with_context"` для `create` (конфликт «файл существует») — отложено до реального кейса

### P2 / YAGNI
- [-] `on_skip: "continue"` — отклонено в ADR (YAGNI, вернуться при кейсе)

---

## ADR-015 — Git-like tree history

### Базис (в коде)
- [x] `core/history_tree.py` — `HistoryTreeManager`, `HistoryNode`
- [x] `apply` / `undo` / `redo` / `branch_from` / `path_to_root`
- [x] `.gitignore`: `.pig/history_tree.json`
- [x] `tests/core/test_history_tree.py` — 9 тестов (apply/undo/redo/branch/persist)

### P0 — 2–3 сессии
- [ ] `gui_qt/models/history_tree_model.py` — `QAbstractItemModel` с `quintptr internalId` (ADR-009), иконки 🟢 applied / 🔵 current / ⚪ rolled_back / 🔴 failed
- [ ] `gui_qt/tabs/history.py` — `HistoryTab`:
  - `QTreeView` + `HistoryTreeModel`
  - `QTextBrowser` справа с `compute_diffs` против родителя
  - Тулбар: ↩ Rollback to here / 🌿 Branch from here / ↪ Redo / 🗑 Delete node / ☑ Editor / ☑ Plan
  - Auto-scroll к current при открытии
- [ ] `main_window.py`: `_TAB_KEYS += ["history"]`, `_TAB_TITLES["history"] = "🕐 История"`, `set_path(root)` при смене проекта
- [ ] `editor.py`: заменить `history_stack`/`redo_stack` на `HistoryTreeManager`:
  - `_on_apply_done` → `mgr.apply(...)` + `mgr.save()`
  - `_on_undo` → `mgr.undo()` + `_restore_from_backup(id, "before")`
  - `_on_redo` → `mgr.redo()` + `_restore_from_backup(id, "after")`
  - `_load_history` — миграция `.pig/editor_history.json` → линейный tree
  - `HistoryTreeManager.max_nodes` + `HistoryNode.payload` — для совместимости с `test_history_cap_at_10` и `llm_text`
- [ ] `plan.py`: то же, `source="plan"`
- [ ] Тесты:
  - `tests/gui_qt/test_history_tab.py` — smoke
  - `tests/gui_qt/test_main_window_smoke.py` — обновить на 6 вкладок
  - `tests/gui_qt/test_editor_tab_extra.py::test_history_cap_at_10` — переписать под новый API

### P1
- [ ] Prune UI: badge «История > 200, рассмотрите очистку» + команда «🗑 Очистить всё кроме current»
- [ ] Фильтр по source в `HistoryTab`

### P2 / вне scope
- [-] Merge веток — вне scope ADR-015
- [-] Cross-project history — per-project tree
- [-] Selective rollback по файлам — полный snapshot

---

## ADR-016 — Retry с контекстом (multi-turn)

### Базис (в коде)
- [x] `core/patcher.py`: `FailedEdit` dataclass, `_find_near_match()` (difflib, threshold 0.6), `patch_context` out-param
- [x] `read_lines` action (защита пути, лимит 200 строк, `read_requests` в `patch_context`)
- [x] `on_failure: "retry_with_context"` — складывает `failed_edits` в `patch_context`
- [x] `core/multi_turn.py::build_retry_prompt()` + `_trim_original()`
- [x] `PlanStepWorker.run()` — multi-turn retry-loop с `patch_context`
- [x] `_default_apply` принимает `patch_context=`
- [x] `config.py`: `quality_edit_retry_max: 2`, `quality_edit_retry_context_lines: 20`

### P0 — закрыто (2026-11-14)
- [x] Editor retry с реальным LLM — `EditorTab._on_retry_with_context` вызывает `make_llm_client()` → `llm.ask(retry_prompt)` → `_on_apply()` при успехе
- [x] `tests/gui_qt/test_editor_retry_llm.py` — 3 теста (fake LLM, no-model → copy to clipboard, `needs_retry=False` → noop)
- [x] `tests/core/test_multi_turn.py` — 9 тестов `build_retry_prompt` + `_trim_original`

### P1
- [ ] Editor `read_lines` UI: показывать, какие строки LLM запросила; кнопка «📋 Скопировать с содержимым файлов»
- [ ] PlanTab: два уровня retry (retry_with_context → полный retry) с явным логом `🔧 retry 1/2` → `🔄 full retry`

### P2 / YAGNI
- [-] Retry с backoff — только для flaky `run_command`, не LLM-патчей
- [-] Cross-step retry — вне scope ADR-016 (в ADR-015)
- [-] `on_not_found` отдельный хук — отклонено (единый `retry_with_context`)

---

## ADR-017 — run_command batch

### Базис (в коде)
- [x] `patcher.py::apply_llm_changes`: `command` XOR `commands`, `report_mode` (`summary`/`full`)
- [x] `command_runner.py`: `summarize_output()` (fail-pattern regex + fallback last-20 + truncate 100)
- [x] `diff_preview.extract_commands` разворачивает `commands[]` в N × `CommandSpec` с `batch_index`/`batch_size`
- [x] `DiffDialog`: `[2/3] $ cmd` в списке + `[batch 2/3]` в панели деталей
- [x] `ApplyWorker`: прокидывает `command_allow_shell_operators`, обрабатывает `PIPELINE ABORTED`
- [x] `config.py`: `command_summary_max_lines: 100`, `command_summary_min_matches: 5`

### P0 — закрыто (2026-11-14)
- [x] Batch summary: `❌ RUN 2/3: [2] ruff (failed)` — индекс упавшей команды
- [x] `tests/core/test_patcher_run_command_batch.py` — 9 тестов, включая `test_batch_summary_includes_index_middle`

### P1
- [ ] timeout per-command для batch (отдельное поле `timeout_sec` на каждую команду) — отложено до реального кейса
- [ ] whitelist reject per-command: покрыто `test_batch_whitelist_per_command`, но нет теста на «whitelist ok + команда failed»

### P2
- [-] `run_batch` как отдельная сущность — отклонено (расширение `run_command`)
- [-] `on_failure: retry` для flaky — future work

---

## Общая инфраструктура

- [x] `pyproject.toml`: `pytest`, `pytest-qt`, `pytest-timeout` в `[project.optional-dependencies] dev` (2026-11-14)
- [x] `CHANGELOG.md`: секция `[Unreleased]` — ADR-014…017 + fixes (2026-11-14)
- [x] `pyproject.toml`: coverage floor 67% → 70% (2026-11-14)
- [ ] `docs/usage.md`: разделы «Flow control в патче», «Дерево истории», «Retry с контекстом», «Batch-команды» — примеры JSON
- [ ] `CONTEXT.md`: глоссарий — `HistoryTreeManager`, `FailedEdit`, `build_retry_prompt`, `CommandSpec.batch_index`
- [ ] `tests/gui_qt/test_misc_coverage3.py` — пустой файл, удалить или заселить под ADR-015 UI

---

## Рекомендуемый порядок следующей сессии

**Вариант B (пол-сессии): docs + cleanup**
1. `docs/usage.md` — примеры JSON для 4 ADR (reference для HistoryTab)
2. `CONTEXT.md` — глоссарий
3. Удалить пустой `test_misc_coverage3.py`

**Вариант A (2–3 сессии): ADR-015 UI**
1. `history_tree_model.py` + `history_tab.py` — только view, без миграции EditorTab (не ломает существующие тесты)
2. `HistoryTreeManager.max_nodes` + `HistoryNode.payload` + миграция `EditorTab`/`PlanTab`
3. `main_window` wiring (6-я вкладка) + тесты + обновить `test_main_window_smoke.py`
