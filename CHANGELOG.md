# Changelog

Все значимые изменения проекта PIG-T3 (форк).
Формат: [Keep a Changelog](https://keepachangelog.com/ru/1.1.0/),
версионирование — [Semantic Versioning](https://semver.org/lang/ru/).

## [Unreleased]

## [2.1.0] - 2026-11-12

42 коммита с v2.0.0. Добавлены четыре LLM-backend (было 3), RAG,
self-validating workflow через run_command, пять UX-фич, серьёзный
tech-debt спринт. Тестов: 275 → 780 (+505). Покрытие: 55% → 67%.

### Added — LLM backends

- **LM Studio** (OpenAI-совместимый `/v1/chat/completions`,
  `/v1/embeddings`, `/v1/models`). Модели с префиксом `LM Studio: `
  в списках Editor/Optimize/Plan. Отдельный embeddings-backend для
  RAG. См. [ADR-013](docs/adr/013-lmstudio.md).
  (`ce96129`, `1e0ae4d`, `012be5b`)

### Added — RAG (Retrieval-Augmented Generation)

- **AST-aware chunker** — Python функции/классы как отдельные чанки,
  не разрываем тела посередине. (`6642a7b`, ADR-011)
- **Embeddings backends** — Ollama (`nomic-embed-text`) и
  sentence-transformers (`all-MiniLM-L6-v2`, extra `[rag]`).
  (`0a50f7b`)
- **Vector store** на `sqlite-vec` в `.pig/rag.db` (KNN через
  `vec0` virtual table). (`01ae493`)
- **Hybrid retriever** — BM25 + vector + RRF fusion (k=60).
  `RobustBM25` с idf-клэмпом для малых корпусов. (`01ae493`)
- **ProjectIndexer + RagOptimizer** — drop-in замена
  `ContextOptimizer`, с fallback на BFS+PageRank при недоступном
  embeddings backend. (`698cb9d`)
- **UI:** чекбокс «Использовать RAG» в OptimizeDialog, автоматический
  выбор backend (Ollama → LM Studio → ST). (`22d5755`)

### Added — run_command (self-validating workflow)

- **Новое JSON-действие** `{"action": "run_command", "command":
  "pytest tests/ -v", "output_path": ".pig/cmd/x.log",
  "on_failure": "abort"}`. AI может выполнить команду, сохранить
  вывод в файл, при падении — остановить пайплайн.
- Opt-in: `allow_command_execution` в настройках (default off).
- Confirm в DiffDialog (Editor) — команды показываются как
  `▶ $ pytest …` перед применением.
- Whitelist по первой команде (`pytest,ruff,mypy,git`).
- Таймаут 1..3600s (default 120), stdout/stderr truncate до 1 MB,
  output_path через `Path.relative_to` (не выйти за root).
- `PIPELINE ABORTED` → step failed, retry кнопка в Plan.
- См. [ADR-012](docs/adr/012-run-command.md).
  (`af19516`, `452e6bf`, `fbc4414`)

### Added — UX

- **Diff preview перед apply** (Editor, Plan step) — unified diff
  до применения патча, file list + `▶ $ cmd` для run_command.
  (`4179b14`, `cb9813a`)
- **Recent projects menu** — 📁 рядом с путём, 1 клик вместо
  4 для смены проекта. (`e1dfa9d`)
- **Undo/Redo в Plan tab** — ↩ / ↪ для delete/reorder/exec. (`6c5dded`)
- **File watcher** — дерево проекта само обновляется через 1.5 сек
  после внешних изменений (IDE, git pull, LLM patch). Отключается в
  настройках. (`2771823`)
- **Глобальный статус-бар** — показывает статус активной вкладки
  в `QStatusBar` главного окна. (`34c9c2e`)

### Added — Инфраструктура

- **Structured logging** — `logging_config.py`, `--verbose` флаг,
  root logger `pig_t3`, 60+ `print()` заменены на `log.debug/warning`.
  Ruff T20 запрещает новые `print()`. (`7006b43`)
- **`--version` / `-V` флаг** — `PIG-T3 2.1.0` без запуска GUI.
  (`f6d38cd`)
- **Hotkeys** — `Ctrl+1..5` (вкладки), `Ctrl+,` (настройки), `F5`
  (refresh). Только нативные Qt-хэндлеры для Ctrl+C/V/X/A/Z. (`34c9c2e`)
- **Авто-кэш моделей** Ollama / LM Studio — асинхронная загрузка,
  60-сек TTL, stale-while-revalidate. UI не блокируется, если
  сервер не запущен. (`48fc97f`, `1e0ae4d`)

### Changed

- **Streaming analyzer** — `ProjectAnalyzer.process()` читает по
  одному файлу, O(1) peak memory вместо O(N × avg_size). На проекте
  500 MB — 500 MB RSS вместо OOM. (`c4255dc`)
- **`.exe` trim** — PyInstaller excludes `_pytest`, `PIL`, `rich`,
  `IPython`, `setuptools._vendor`, Qt WebEngine/Quick/Multimedia.
  136 MB → ~120 MB. (`a2c299e`)
- **`RagOptimizer.__init__`** — опциональный `backend=` для инъекции
  готового объекта (используется OptimizeWorker для LM Studio). (`1e0ae4d`)
- **`OptimizeWorker.__init__`** — новый `settings=` для чтения
  `lmstudio_*` из конфига. (`1e0ae4d`)
- **Coverage floor** — 55% → 67% (поэтапно: 55 → 60 → 61 → 62 → 67).
- **CI** — Ubuntu 24.04 + Windows 2022 (LTS), `actions/*@v5`,
  `workflow_dispatch`, `QT_QPA_PLATFORM=offscreen`, apt-install
  с 5×60s retry на flaky DNS. (`d957e7e`, `4a39adc`, `19fc9e4`,
  `327626d`)

### Fixed

- **Path traversal** в `apply_llm_changes` — `../../etc/passwd`
  больше не проходит. `_safe_path()` через `Path.relative_to`
  в каждом action. (`34c9c2e`)
- **`update_settings` action** — требовал `path`, что невозможно.
  LLM не мог обновить настройки проекта. (`78404a9`)
- **`ignore_list=""`** — все файлы отбрасывались из-за
  `"" in <any>` матча. Пустые элементы после `split(',')`
  отбрасываются. Sentinel `\x00` в GeneratorTab. (`c4255dc`)
- **QThread leak** в `OptimizeDialog` — при явном `models=`
  реальный воркер стартовал и падал на teardown. Явные модели
  отключают auto-fetch. (`48fc97f`)
- **Tokenizer BM25** — `calculate_total` не находился по `calculate`.
  Добавлен `[._\-/]+ → ' '` + `ClassVar` для class attributes. (`01ae493`)
- **Windows: diff preview** — `_filter_safe` сравнивал
  `startswith(str(root) + "/")`, на Windows `\` vs `/` → все пути
  отвергались, «Нет изменений». `Path.relative_to()`. (`09e837e`)
- **Windows: edit с tabs/spaces** — `replace_text` терял изменения
  при несовпадении whitespace. `_apply_replace_text` с двухуровневым
  fallback (exact → regex `\s+`), `_shift_indent` для сохранения
  вложенности, anti-dup через `.strip()`. (`f05f381`)
- **Windows: `_RowHeightDelegate`** — teardown race, `RuntimeError:
  already deleted` в pytest-qt. `QStyledItemDelegate.sizeHint(self,
  ...)` в try/except + `viewport().update()` вместо `reset()`.
  (`1e0ae4d`)
- **`free(): invalid size`** в тестах — `QAbstractItemModel
  internalPointer` → `quintptr internalId`, `QThread` detach перед
  GC, `os._exit` в `pytest_sessionfinish` (ADR-009, ADR-010).
  (наследие v2.0.0, исправлено полностью)

### Infrastructure / DevEx

- **`check.sh`** — single pytest run, `-q` точки, `--timeout-method=thread`
  на обоих путях (cov и не-cov). (`bba871b`, `83f66d1`, `ba3604d`)
- **Pre-commit** — `thread` timeout вместо `signal` (SIGALRM вызывал
  SIGABRT в shiboken). (`ba3604d`)
- **Coverage** — `pytest-cov` с `PIG_NO_EXIT` для отчёта, floor в
  `pyproject.toml`. (`2353d2a`, `ebd52f2`, `f2d4ac8`, `3aac337`,
  `78404a9`)
- **Qt-Material** — тема `dark`/`light` только, миграция legacy
  (`pink`/`eye_care`/`dark_pink`). (наследие v2.0.0, ADR-002)
- **LICENSE** — MIT с двойным copyright (оригинал + форк). (`34c9c2e`)

### Documentation

- **ADR-011** — RAG архитектура. (`8fcad14`)
- **ADR-012** — `run_command` safety model. (`fbc4414`)
- **ADR-013** — LM Studio backend. (`012be5b`)
- **`docs/usage.md`** — пользовательский гайд: 5 сценариев,
  настройка LLM (Ollama/LM Studio/Web/BomjAPI), troubleshooting. (`b23e357`, `fbc4414`, `012be5b`)
- **`docs/releases/v2.1.0/QA.md`** — QA-чек-лист 10 блоков. (`30ff3a7`)
- **`CONTEXT.md`** — глоссарий, API вкладок, воркеры, RAG, LM Studio. (`8fcad14`, `012be5b`)
- **README** — русский, форк-ориентированный. (`37f625a`)

### Tests

- **275 → 780 passed** (+505), 1 skipped.
- Покрытие: **55% → 67%**.
- Новые области: core/analyzer, core/patcher, core/command_runner,
  core/rag (chunker/embeddings/store/retriever/indexer/optimizer),
  workers (apply/generate/plan_step/optimize/scan/ollama/lmstudio),
  utils, settings_dialog, optimize_dialog, diff_dialog, main_window,
  shortcuts.
- `test_threading_contract.py` — обязательный контракт для любого
  QThread-воркера (progress/finished/error/cancelled, run в отдельном
  потоке, main-thread не блокируется, cancel через
  `isInterruptionRequested`, no thread leak).

## [2.0.0] — 2026-11-10

Первая версия форка. Миграция GUI с Tkinter на PySide6 + Qt-Material.
5 вкладок, 3 LLM-backend (Ollama / Web / BomjAPI), 275 тестов,
10 ADR, PyInstaller single-file build, pre-commit hooks.

Подробнее — `git log v2.0.0` и `docs/adr/001..010`.
