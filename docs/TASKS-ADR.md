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

### P0 — следующая сессия
- [ ] **`analyzer._write_patching_instructions`** — документировать `id`, `on_failure` (`continue|abort|rollback`), `on_success`, `depends_on` + пример DAG. ~15 строк в системный промпт.
- [ ] **`tests/core/test_patcher_flow_control.py`** — 8 тестов:
  - `test_depends_on_ok` — последовательное выполнение
  - `test_depends_on_skip` — failed dep → downstream skip
  - `test_depends_on_transitive_skip` — A fail → B skip → C skip
  - `test_deadlock` — циклические deps → ошибка до apply
  - `test_duplicate_ids` — ошибка парсинга до apply
  - `test_on_failure_rollback` — abort + restore `before/`
  - `test_on_success_abort` — успешный action останавливает пайплайн
  - `test_rollback_deletes_created` — created (after без before) удаляется
- [ ] **`test_analyzer_prompt.py`** — `assert "depends_on" in buf.getvalue()`

### P1
- [ ] `on_failure: "retry_with_context"` для `create` (конфликт «файл существует»)

### P2 / YAGNI
- [-] `on_skip: "continue"` — отклонено в ADR (YAGNI, вернуться при кейсе)

---

## ADR-015 — Git-like tree history

### Базис (в коде)
- [x] `core/history_tree.py` — `HistoryTreeManager`, `HistoryNode`
- [x] `apply` / `undo` / `redo` / `branch_from` / `path_to_root`
- [x] `.gitignore`: `.pig/history_tree.json`

### P0 — 2–3 сессии
- [ ] **`gui_qt/models/history_tree_model.py`** — `QAbstractItemModel` с `quintptr internalId` (ADR-009), иконки 🟢 applied / 🔵 current / ⚪ rolled_back / 🔴 failed
- [ ] **`gui_qt/tabs/history.py`** — `HistoryTab`:
  - `QTreeView` + `HistoryTreeModel`
  - `QTextBrowser` справа с `compute_diffs` против родителя
  - Тулбар: ↩ Rollback to here / 🌿 Branch from here / ↪ Redo / 🗑 Delete node / ☑ Editor / ☑ Plan
  - Auto-scroll к current при открытии
- [ ] **`main_window.py`**: `_TAB_KEYS += ["history"]`, `_TAB_TITLES["history"] = "🕐 История"`, `set_path(root)` при смене проекта
- [ ] **`editor.py`**: заменить `history_stack`/`redo_stack` на `HistoryTreeManager`;
  - `_on_apply_done` → `mgr.apply(...)` + `mgr.save()`
  - `_on_undo` → `mgr.undo()` + `_restore_from_backup(id, "before")`
  - `_on_redo` → `mgr.redo()` + `_restore_from_backup(id, "after")`
  - `_load_history` — миграция `.pig/editor_history.json` → линейный tree
- [ ] **`plan.py`**: то же, `source="plan"`
- [ ] **Тесты**:
  - `tests/core/test_history_tree.py` — apply/undo/redo/branch/prune/migrate
  - `tests/gui_qt/test_history_tab.py` — smoke
  - `tests/gui_qt/test_main_window_smoke.py` — обновить на 6 вкладок
- [ ] **`test_threading_contract.py`** — если добавятся новые воркеры

### P1
- [ ] **Prune UI**: badge «История > 200, рассмотрите очистку» + команда «🗑 Очистить всё кроме current»
- [ ] **Фильтр по source** в `HistoryTab`

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
- [x] `EditorTab._on_retry_with_context` — копирует prompt в буфер (заглушка)
- [x] `config.py`: `quality_edit_retry_max: 2`, `quality_edit_retry_context_lines: 20`

### P0 — 1 сессия
- [ ] **Editor retry с реальным LLM** (не только копирование):
  - `EditorTab._on_retry_with_context` → если модель выбрана (`ollama_model` / `LM Studio: *`), `make_llm_client()` → `llm.ask(retry_prompt)` → новый round через `ApplyWorker`
  - До `quality_edit_retry_max` раундов
  - При успехе — обновить `history_stack`
- [ ] **`tests/gui_qt/test_editor_retry.py`** — mock llm, 2 раунда, второй успешен
- [ ] **`tests/core/test_multi_turn.py`** — `build_retry_prompt` содержит все `failed_edits`, обрезает по budget

### P1
- [ ] **Editor `read_lines` UI**: показывать, какие строки LLM запросила; кнопка «📋 Скопировать с содержимым файлов»
- [ ] **PlanTab**: два уровня retry (retry_with_context → полный retry) с явным логом `🔧 retry 1/2` → `🔄 full retry`

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

### P0 — нет (закрыто)

### P1
- [ ] **Batch summary**: `❌ RUN 2/3: [2] ruff (failed)` вместо `❌ RUN 2/3: ruff (failed)` — индекс команды для точности
- [ ] **`tests/core/test_patcher_run_command_batch.py`** — расширить: whitelist reject per-command, `on_failure: abort` на любой failed, timeout per-command

### P2
- [-] `run_batch` как отдельная сущность — отклонено (расширение `run_command`)
- [-] `on_failure: retry` для flaky — future work

---

## Общая инфраструктура

- [ ] **`pyproject.toml`**: `pytest_timeout` в dev-deps (сейчас addopts ждёт плагин, но `ModuleNotFoundError` при чистой установке)
- [ ] **`docs/usage.md`**: разделы «Flow control в патче», «Дерево истории», «Retry с контекстом», «Batch-команды» — примеры JSON
- [ ] **`CHANGELOG.md`**: секция `[Unreleased]` — ADR-014…017
- [ ] **`CONTEXT.md`**: глоссарий — `HistoryTreeManager`, `FailedEdit`, `build_retry_prompt`, `CommandSpec.batch_index`
- [ ] **`pyproject.toml`**: coverage floor 67% → 70% после ADR-015 UI

---

## Рекомендуемый порядок следующей сессии

1. `tests/core/test_patcher_flow_control.py` (8 тестов) — фиксирует ADR-014
2. `analyzer._write_patching_instructions` + `test_analyzer_prompt.py`
3. Editor retry с LLM + `test_editor_retry.py`
4. ADR-015 UI — отдельная крупная ветка (2–3 сессии)
