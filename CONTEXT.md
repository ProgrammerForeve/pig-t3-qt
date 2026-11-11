# PIG-T3 · Контекст проекта

Документ фиксирует термины и архитектурные решения, принятые при миграции
GUI с Tkinter на PySide6 + Qt-Material. Ссылки на ADR — в `docs/adr/`.

## Термины

### Вкладки (tabs)
Верхнеуровневые разделы главного окна. Ключи: `generator`, `info`, `editor`,
`plan`, `quality`. Каждая реализована как `QWidget` в `PIG_T3/gui_qt/tabs/`.

| Вкладка | Класс | Файл |
| :--- | :--- | :--- |
| 🏠 Генератор | `GeneratorTab` | `tabs/generator.py` |
| 🎓 Инфо | `InfoTab` | `tabs/info.py` |
| ✏️ Редактор | `EditorTab` | `tabs/editor.py` |
| 📝 План | `PlanTab` | `tabs/plan.py` |
| 📊 Анализ кода | `QualityTab` | `tabs/quality.py` |

### Воркеры (workers)
`QObject`-классы, перемещённые в `QThread` через `moveToThread`. Живут в
`PIG_T3/gui_qt/workers/`. Контракт — `tests/gui_qt/test_threading_contract.py`.

| Воркер | Назначение | Сигналы |
| :--- | :--- | :--- |
| `GenerateWorker` | Сканирование проекта → отчёт | `progress`, `finished`, `error`, `cancelled` |
| `OptimizeWorker` | Сжатие контекста (BFS + LLM) | `progress(int, str)`, `done(list)`, `error`, `cancelled` |
| `GeneratePlanWorker` | Концепция → JSON-план | `progress`, `done(list)`, `error`, `cancelled` |
| `PlanStepWorker` | Выполнение шага плана | `progress`, `done(step, log)`, `error(step, msg)`, `cancelled` |
| `ApplyWorker` | Применение JSON-патча | `done(log, record)`, `error` |
| `UndoRedoWorker` | Откат/повтор snapshot | `done(msg)`, `error` |
| `ScanWorker` | Аудит кода (radon/pylint/bandit) | `progress(int, str)`, `done(list[FileMetrics])`, `error`, `cancelled` |

### Модели (models)
`QAbstractItemModel` / `QAbstractTableModel` в `PIG_T3/gui_qt/models/`.

- `ProjectTreeModel` — дерево проекта с tristate чекбоксами. Использует
  **quintptr `internalId`** вместо Python `internalPointer` (ADR-009).
- `QualityTableModel` — 6 колонок `path/sloc/cc/mi/score/sec` для
  `FileMetrics`. Цвет — по `FileMetrics.get_status_for_column()`.

### LLM-обёртки (llm_wrappers)
Единый интерфейс `.optimize_context(task, meta_list)` + `.ask(prompt)`:
- `OllamaWrapper` — локальная Ollama
- `WebWrapper` — DeepSeek/Gemini через Playwright
- `BomjWrapper` — ручной ввод через `_BomjBridge` + `QDialog`

Фабрика `make_llm_client(model_name, parent, settings)`.

### Состояние (state)
- `app_config.json` — глобальные настройки (`ConfigManager`)
- `.pig/state.json` — per-project: `ui_tree_expanded`, `ui_tree_unchecked`, `history_stack`, `redo_stack`
- `.pig/plan.json` — план проекта
- `.pig/backups/<uuid>/{before,after}/` — снапшоты для undo/redo

### Горячие клавиши
**Только нативные Qt** обработчики — никаких `QShortcut` для
Ctrl+C/V/X/A/Z (ADR-007). QA-чек-лист: все поля ввода, все диалоги
(после открытия, фокус на первом поле).

## Публичные API вкладок

### `GeneratorTab(settings)`
- `collect_settings() -> dict`
- `refresh_tree()`, `set_tree_data(files)`
- `capture_tree_state() -> dict`
- `commit_recent_projects()`
- `stop_generation()`, `stop_optimization()`
- Сигналы: `settings_changed`, `generation_finished`, `generation_cancelled`, `generation_error`

### `EditorTab(settings)`
- `set_path(folder)`, `load_json(text)`
- `stop_workers()`
- Сигналы: `undo_available_changed(bool)`, `redo_available_changed(bool)`

### `PlanTab(settings)`
- `set_path(folder)`
- `load_plan()`, `save_plan_silently()`
- `stop_workers()`
- Сигнал: `plan_changed`

### `QualityTab()`
- `set_path(folder)`
- `set_metrics(list[FileMetrics])`
- `stop_scan()`

## RAG (Retrieval-Augmented Generation)

Опциональный слой семантического отбора файлов. Включается
чекбоксом «Использовать RAG» в `OptimizeDialog`. Выключен по
умолчанию — требует Ollama (`nomic-embed-text`) или
`sentence-transformers`.

### Компоненты (`PIG_T3/core/rag/`)

| Модуль | Назначение |
| :--- | :--- |
| `chunker.py` | AST-aware разбиение (функции/классы как чанки) |
| `embeddings.py` | Ollama / sentence-transformers за одним Protocol |
| `store.py` | `sqlite-vec` в `.pig/rag.db`, KNN через `vec0` |
| `retriever.py` | BM25 + vector + RRF fusion (k=60) |
| `indexer.py` | `ProjectIndexer.build(rel_paths)` → chunk + embed + store |
| `optimizer.py` | `RagOptimizer.optimize()` — drop-in для `ContextOptimizer` |

### Индекс

- Файл: `<project>/.pig/rag.db` (в `.gitignore`)
- Размер: ~10 MB на 10k чанков
- Dimension фиксируется при создании; смена backend →
  `DimensionMismatchError` (удалить файл и переиндексировать)
- Полная пересборка при каждом `build()`. Инкрементальная —
  future work (mtime + add/delete по файлам)

### Fallback

Если embeddings backend недоступен:
- `OptimizeWorker._make_rag_optimizer` ловит `RuntimeError`,
  логирует warning, возвращает `ContextOptimizer` (BFS+PageRank)
- Пользователь видит «⚠️ RAG недоступен…» в статус-баре
- Задача выполняется через старую эвристику

### Как включить

```bash
# вариант 1 — Ollama (лёгкий)
ollama serve
ollama pull nomic-embed-text

# вариант 2 — sentence-transformers (тяжёлый)
uv sync --extra rag
```

Затем: **Генератор → ✨ Оптимизация контекста → ✅ Использовать RAG**.

## Как добавить новую вкладку

1. Создать `PIG_T3/gui_qt/tabs/<name>.py` с классом `<Name>Tab(QWidget)`.
2. Экспортировать в `tabs/__init__.py`.
3. Добавить ключ в `_TAB_KEYS` и `_TAB_TITLES` в `main_window.py`.
4. В `_setup_tabs` добавить `elif key == "<name>": widget = <Name>Tab(...)`.
5. В `closeEvent` — `if hasattr(widget, "stop_workers"): widget.stop_workers()` (если есть воркеры).
6. Тесты: `<name>_tab` в `tests/gui_qt/`, smoke — добавить в `test_main_window_smoke.py`.
