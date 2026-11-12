# 🐖 PIG-T3 — AI Context Generator & Patcher (форк)

Десктоп-приложение (**PySide6 + Qt-Material**) для работы с большими
кодовыми базами вместе с AI-ассистентами (ChatGPT, Claude, DeepSeek,
локальные модели Ollama / LM Studio).

Генерирует **отчёт-контекст** с полной структурой проекта и исходниками
для отправки в LLM. Применяет **JSON-патчи от AI** автоматически
(create / edit / move / delete / run_command) с undo/redo и бэкапами.

**Это форк.** Оригинальный PIG-T3 — `pip install pig-t3`.
GUI переписан с Tkinter на PySide6 в v2.0.0. См. [docs/adr/](docs/adr/).

---

## 📥 Скачать готовый бинарник

Последний релиз: **[v2.2.0](https://github.com/ProgrammerForeve/pig-t3-qt/releases/tag/v2.2.0)**

| OS | Скачать | Размер |
| :--- | :--- | :--- |
| **Windows** | [PIG-T3-windows.zip](https://github.com/ProgrammerForeve/pig-t3-qt/releases/download/v2.2.0/PIG-T3-windows.zip) | ~108 MB |
| **Linux** | [PIG-T3-linux.zip](https://github.com/ProgrammerForeve/pig-t3-qt/releases/download/v2.2.0/PIG-T3-linux.zip) | ~144 MB |

- **Windows:** распаковать, запустить `PIG-T3.exe`
  (SmartScreen → **More info → Run anyway** — бинарник не подписан)
- **Linux:** распаковать, `chmod +x PIG-T3 && ./PIG-T3`

Если хотите собрать из исходников — см. раздел [Установка (форк)](#-установка-форк).

---

## ✨ Возможности

### 🏠 Генератор
- Сканирование папки, ignore-лист, фильтр по расширениям.
- Один `.txt` с XML-тегами `<file path="...">`.
- Опции: нумерация строк, инструкция для AI, пустые папки, авто-копирование.
- **Дерево с нативными чекбоксами** — клик по строке = toggle (папка каскадом).
  «🌐 Весь проект» — tristate select-all. Состояние сохраняется в `.pig/state.json`.
- **📁 Recent projects** — меню недавних, 1 клик для смены проекта.
- **🔄 File watcher** — дерево само обновляется через ~1.5 сек после внешних
  изменений (IDE, git pull, LLM patch). Отключается в настройках.
- **✨ Оптимизация контекста** — задача, % сжатия, BFS-глубина, модель,
  опционально **RAG** (semantic search).

### ✏️ Редактор (JSON Patcher)
- Вставка JSON-ответа LLM, валидация, pretty-print.
- **👁 Diff preview** — unified diff (файлы + `$ команды`) **до** применения.
- Действия: `create`, `edit`, `move`, `delete`, `run_command`.
- Undo/Redo с бэкапами в `.pig/backups/<uuid>/{before,after}/` (лимит 10).
- **Auto-Fix** — починка битого JSON через Ollama / LM Studio / Web / BomjAPI.
- **Whitespace-flexible edit** — `replace_text` игнорирует tabs/spaces/indent.

### 📝 План
- Генерация плана из концепции (`GeneratePlanWorker`).
- Выполнение шага (`PlanStepWorker`): контекст → LLM → JSON → apply.
- Retry (2 попытки), выполнение всего плана с прогрессом и остановкой.
- **Diff preview** перед apply (если «Авто-применение» выключено).
- **↩ / ↪ Undo/Redo** для delete / reorder / exec.
- **Git** — auto-commit перед шагом, опционально push.

### 📊 Анализ кода
- Radon CC, Radon MI, Pylint Score, Bandit — в фоне, с отменой.
- `QTableView` с цветовой индикацией, панель деталей.
- Свёрнутый вид — только `path` + сортируемая метрика.

### ⚙️ Настройки
- Тема, шрифт, высота строк, вес оптимизатора, Git, LLM-таймауты,
  видимость вкладок, **выполнение команд**, **LM Studio**.
  Применяются без перезапуска.

### 🛠️ run_command — self-validating workflow (opt-in)

AI может выполнить shell-команду и сохранить вывод в файл:

```json
{"action": "run_command",
 "command": "pytest tests/ -v",
 "output_path": ".pig/cmd/pytest.log",
 "timeout_sec": 120,
 "on_failure": "abort"}
```

- **Opt-in:** `allow_command_execution: false` в настройках (default).
- **Confirm** в DiffDialog (Editor) — команды видны перед apply.
- **Whitelist** по первой команде (`pytest,ruff,git`).
- **`PIPELINE ABORTED`** при не-нулевом exit code и `on_failure: abort` —
  шаг плана → failed, retry доступен.
- См. [ADR-012](docs/adr/012-run-command.md).

### 🧠 RAG — semantic search (опционально)

- **AST-aware chunker** для Python (функции/классы как отдельные чанки).
- **Embeddings:** Ollama (`nomic-embed-text`), LM Studio, sentence-transformers.
- **Vector store:** `sqlite-vec` в `.pig/rag.db`.
- **Hybrid retriever:** BM25 + vector + RRF fusion (k=60).
- **UI:** чекбокс «Использовать RAG» в `OptimizeDialog`.
- **Auto-выбор backend:** Ollama → LM Studio → sentence-transformers.
- **Fallback:** без embeddings — BFS+PageRank (старая эвристика).
- См. [ADR-011](docs/adr/011-rag.md).

### 🎯 Прочее
- **Hotkeys:** `Ctrl+1..5` (вкладки), `Ctrl+,` (настройки), `F5` (refresh).
  Нативные Ctrl+C/V/X/A/Z (ADR-007).
- **`--version` / `-V`** — печатает версию без запуска GUI.
- **`--verbose` / `-v`** — DEBUG-логи в stderr.
- **Streaming analyzer** — O(1) peak memory (читает по одному файлу).

---

## 🤖 Бэкенды LLM

| Бэкенд | Где работает |
| :--- | :--- |
| **Ollama** | Локально (`localhost:11434`), `/api/chat` |
| **LM Studio** | Локально (`localhost:1234/v1`), OpenAI-совместимый |
| **Web: DeepSeek** | chat.deepseek.com через Playwright |
| **Web: Gemini** | AI Studio через Playwright |
| **BomjAPI** | Ручной ввод (промпт/ответ) для любого веб-чата |

LM Studio модели в списке с префиксом **`LM Studio: <model>`**.
См. [ADR-013](docs/adr/013-lmstudio.md).

---

## 📦 Установка (форк)

Требуется **Python 3.10+** и **uv**.

```bash
git clone https://github.com/ProgrammerForeve/pig-t3-qt pig-t3-fork
cd pig-t3-fork
uv sync --extra dev          # runtime + dev + PySide6 + qt-material
```

**Опционально:**

```bash
uv run playwright install chromium   # для Web-бэкендов (DeepSeek/Gemini)
uv sync --extra rag                  # sentence-transformers (~500 MB)
```

**Не** ставится через `pip install pig-t3` — это оригинал, здесь другой код.

---

## 🚀 Быстрый старт

Точки входа:

```bash
uv run python -m PIG_T3        # как модуль
uv run python run.py           # из корня репо
uv run pig-t3                  # console script (pip install -e .)
uv run python -m PIG_T3 --version
./dist/PIG-T3                  # после PyInstaller
```

Флоу:

1. **Генератор** → выбрать папку → «ГЕНЕРИРОВАТЬ КОНТЕКСТ» → `project_context.txt`.
2. Отправить файл в чат с AI.
3. **Редактор** → вставить JSON-ответ → «Проверить» → «👁 Просмотр» → «Применить».
4. Или **План** — описать цель, выполнить шаги (с diff preview на каждом).

---

## 🧩 JSON-формат

Ответ LLM — JSON **массив**:

```json
[
  {"action": "update_settings", "extensions": ".py, .json", "ignore_list": "venv, .git"},
  {"action": "create", "path": "utils/h.py", "content": "def f():\n    return True\n"},
  {"action": "delete", "path": "old.py"},
  {"action": "move", "source": "old/f.py", "destination": "new/f.py"},
  {
    "action": "edit",
    "path": "main.py",
    "operations": [
      {"type": "replace_lines", "start": 10, "end": 12, "content": "    new_code()\n"},
      {"type": "insert_after_line", "line": 15, "content": "    print('x')\n"}
    ]
  },
  {"action": "run_command", "command": "pytest tests/", "output_path": ".pig/cmd/x.log", "on_failure": "abort"},
  {"action": "mark_step_completed", "step_id": "step_1", "completed": true}
]
```

⚠️ Для существующих файлов — **только** `edit`, не `create`.
В `replace_lines` не включайте неизменные соседние строки — будут дубли.
`replace_text` теперь терпим к tabs/spaces/indent (ADR-014 future).

Полная спецификация — во вкладке **Инфо**.

---

## ⚙️ Конфигурация

| Файл | Что хранит |
| :--- | :--- |
| `app_config.json` | тема, шрифт, веса оптимизатора, Git, LLM-таймауты, `tabs_visibility`, `recent_projects`, `allow_command_execution`, `lmstudio_*`, `ollama_models_cache`, `lmstudio_models_cache` |
| `.pig/state.json` | `ui_tree_expanded`, `ui_tree_unchecked`, `history_stack`, `redo_stack` (per-project) |
| `.pig/plan.json` | план проекта |
| `.pig/backups/<uuid>/{before,after}/` | снапшоты для undo/redo |
| `.pig/rag.db` | RAG index (`sqlite-vec`) |
| `.pig/cmd/` | output от `run_command` |

**Миграция тем:** `pink` / `eye_care` → `light`, `dark_pink` → `dark`
при первой загрузке (ADR-002). `ui_scale` удалён.

Дерево: expand/uncheck восстанавливаются между запусками и **не сбрасываются**
при изменении extensions/ignore (если папка проекта не менялась).

---

## 🐙 Git

**Настройки → Функционал → Git.** Перед шагом плана:

```bash
git add -A
git checkout -b pig_plan_<ts>    # если git_branch_mode == "new"
git commit -m "PIG-T3: auto-save before plan execution (<ts>)"
git push origin HEAD              # если git_auto_push == true
```

Если `git` нет или папка вне репо — интеграция молча пропускается.

---

## 🧪 Разработка

```bash
uv run pre-commit install     # хуки в .git/hooks/
./check.sh                    # ruff + pytest (быстро)
./check.sh --fix              # ruff --fix + format + pytest
./check.sh --cov              # + coverage (PIG_NO_EXIT=1, floor 67%)
```

**Lint-скоуп:** `PIG_T3/gui_qt`, `PIG_T3/config.py`, `tests/`.
Legacy `PIG_T3/core/*`, `PIG_T3/utils/*` — вне ruff style-скоупа
(ADR-005), но `T20` (print) запрещён везде в `PIG_T3/`.

**Pre-commit** (при `git commit`):
- EOF, trailing-whitespace, merge-conflict, large-files
- `ruff` + `ruff-format` (in-scope)
- `pytest tests/ -q --timeout=30 --timeout-method=thread -x`
  (~10 сек, стоп на первом падении)

Обход: `git commit --no-verify`.

**Тесты:**

```bash
uv run pytest tests/ -v
uv run pytest tests/gui_qt/test_generator.py
uv run pytest -k threading
```

Покрытие (**~780 тестов**, coverage 67%):
- unit — модели, воркеры, диалоги
- **QThread-контракт** — сигналы, отдельный поток, UI не блокируется,
  отмена, без утечек
- **smoke** — все 5 вкладок нужных классов, нет `tkinter` и legacy-импортов

---

## 📦 Сборка

```bash
uv run pyinstaller pig_t3.spec --noconfirm
```

- Linux: `dist/PIG-T3` (~144 MB)
- Windows: `dist/PIG-T3.exe` (~108 MB)
- macOS: `dist/PIG-T3` (unsigned, `xattr -dr com.apple.quarantine`)

Спек бандлит PySide6, qt-material, иконки, зависимости анализатора,
исключает `_pytest`/`PIL`/`rich`/`IPython`/Qt WebEngine/Quick/Multimedia
(D4).

**CI** — `.github/workflows/build.yml` на push в `master` и тег `v*`:

| OS | Runner | Шаги | Артефакт |
| :--- | :--- | :--- | :--- |
| Ubuntu | `ubuntu-24.04` | Qt libs → pytest → build | `PIG-T3-linux` |
| Windows | `windows-2022` | deps → build | `PIG-T3-windows` |

- Скачивать из **Releases** (см. верх README) — публичные URL, без логина.
- Или **Actions → Build → Artifacts** (требует логин).

---

## 🏗️ Архитектура

- **[`CONTEXT.md`](CONTEXT.md)** — глоссарий (вкладки, воркеры, модели,
  LLM-обёртки, файлы состояния), публичные API вкладок, чек-лист
  «как добавить вкладку».
- **[`docs/adr/`](docs/adr/)** — **13 ADR**:
  001 PySide6, 002 Qt-Material, 003 QThread, 004 QAbstractItemModel,
  005 scope, 006 config compat, 007 hotkeys, 008 dialog wrappers,
  009 quintptr internalId, 010 os._exit, 011 RAG, 012 run_command,
  013 LM Studio.
- **[`docs/usage.md`](docs/usage.md)** — гайд по 5 сценариям, настройка LLM,
  troubleshooting.
- **[`CHANGELOG.md`](CHANGELOG.md)** — сводка по версиям.

```
PIG_T3/
├── config.py                  # ConfigManager
├── logging_config.py          # structured logging (D3)
├── main.py                    # entry point (--version / --verbose)
├── core/                      # бизнес-логика
│   ├── analyzer.py            # streaming generator (C-)
│   ├── context_optimizer.py   # BFS + PageRank
│   ├── patcher.py             # apply_llm_changes (+ run_command, + whitespace-flex)
│   ├── command_runner.py      # subprocess + whitelist + output (C6)
│   ├── plan_validator.py
│   ├── ollama_client.py
│   ├── lmstudio_client.py     # OpenAI-совместимый (C7)
│   ├── dependency_graph.py
│   ├── rag/                   # C1-C5
│   │   ├── chunker.py         # AST-aware
│   │   ├── embeddings.py      # Ollama / LM Studio / ST
│   │   ├── store.py           # sqlite-vec
│   │   ├── retriever.py       # BM25 + vector + RRF
│   │   ├── indexer.py
│   │   └── optimizer.py       # RagOptimizer
│   └── quality/               # radon / pylint / bandit
├── utils/                     # clipboard, dep_installer, majorchic_api, BomjAPI
└── gui_qt/                    # PySide6 GUI
    ├── app.py
    ├── main_window.py
    ├── theme.py
    ├── config_compat.py
    ├── tabs/                  # generator, info, editor, plan, quality
    ├── workers/               # 10+ QThread-воркеров + 4 LLM-обёртки
    ├── models/                # project_tree, quality_table
    ├── widgets/               # project_tree_view, recent_menu, file_watcher
    └── dialogs/               # optimize, settings, new_plan, diff
```

**Добавить вкладку** — см. `CONTEXT.md`. Кратко:
`tabs/<name>.py` → экспорт в `tabs/__init__.py` → ключ в `_TAB_KEYS` /
`_TAB_TITLES` → ветка в `_setup_tabs` → `stop_workers()` в `closeEvent`.

---

## 🩺 Проблемы

**`free(): invalid size` при выходе** — историческая (T-107, ADR-009/010),
исправлена на 5 уровнях. Если вернулась — `PIG_NO_SPLASH=1 ./run.sh`,
посмотреть `/tmp/pig_crash.log` (Linux) / `%TEMP%\pig_crash.log` (Windows).

**`Gtk-Message: Failed to load module "xapp-gtk3-module"`** — безвредное
предупреждение GTK (Mint / XApps). Игнорировать или
`sudo apt install libxapp-gtk3-module`.

**Ctrl+C / Ctrl+V не работают** — не должно быть (ADR-007, нативные
Qt-хэндлеры). Сообщите файл и виджет.

**Тема «сломалась» после обновления** — `pink`/`eye_care` → `light`,
`dark_pink` → `dark` (ADR-002). Сменить акцент: `_QT_MATERIAL` в
`gui_qt/theme.py`.

**RAG не работает** — нужен embeddings-backend (Ollama / LM Studio / ST).
Проверьте **Настройки → Функционал → LM Studio** для LM Studio,
или `ollama serve` + `ollama pull nomic-embed-text`.

**LM Studio модели не появляются** — сервер запущен? **Local Server →
Start** в LM Studio, порт `1234` по умолчанию. Список кэшируется на 60 сек.

**`run_command` не выполняется** — включите **Настройки → Функционал →
«Разрешить выполнение команд»**. Default: off (safety).

**PyInstaller: `attempted relative import`** — собирайте **только**
через `pyinstaller pig_t3.spec`, не `PIG_T3/main.py` (T-703).

---

## 📜 Changelog

### v2.2.0 — LM Studio, RAG, run_command (2026-11-12)

**42 коммита** с v2.0.0. Тестов: 275 → ~780. Coverage: 55% → 67%.

**Added — LLM backends:**
- **LM Studio** (OpenAI-совместимый `/v1/*`), префикс `LM Studio: `
  в UI, embeddings для RAG. ADR-013.

**Added — RAG** (опционально, ADR-011):
- AST-aware chunker, `sqlite-vec` store, BM25+vector+RRF,
  `RagOptimizer` drop-in для `ContextOptimizer`, UI checkbox.

**Added — run_command** (opt-in, ADR-012):
- AI может выполнить shell-команду, сохранить вывод, остановить
  пайплайн при ошибке. Opt-in + confirm в Editor + whitelist + timeout.

**Added — UX:**
- Diff preview (Editor + Plan step) перед apply
- Recent projects menu, Plan undo/redo, File watcher (1.5 сек)
- Global status bar (активная вкладка)
- Hotkeys (Ctrl+1..5, Ctrl+,, F5)

**Added — инфраструктура:**
- Structured logging (`--verbose`), `--version` флаг
- Async models cache (Ollama / LM Studio), 60s TTL
- `_no_async_workers` autouse fixture для стабильности CI

**Changed:**
- Streaming analyzer — O(1) peak memory (было O(N × avg_size))
- `.exe` trim — 136 MB → ~108 MB (Windows), 144 MB (Linux)
- Coverage floor 55% → 67%
- CI: Ubuntu 24.04 + Windows 2022, `--timeout-method=thread`,
  apt-install retry

**Fixed:**
- Path traversal в `apply_llm_changes` (`../../etc/passwd`)
- `update_settings` без `path` (LLM не мог обновить настройки)
- `ignore_list=""` — все файлы отбрасывались
- QThread leak в `OptimizeDialog` при явном `models=`
- Tokenizer BM25 — `calculate_total` не находился по `calculate`
- Windows: diff preview отвергал все пути (`\` vs `/`)
- Windows: edit терял изменения при tabs/spaces/indent
- Windows: `_RowHeightDelegate` teardown race

См. полный [CHANGELOG.md](CHANGELOG.md).

### v2.0.0 — миграция на PySide6 (2026-11-10)

**Breaking:**
- GUI: Tkinter → PySide6 + Qt-Material
- Темы `pink` / `eye_care` / `dark_pink` удалены (миграция → `light`/`dark`)
- Ключ `ui_scale` удалён

**New:**
- 5 рабочих вкладок (Генератор / Инфо / Редактор / План / Анализ)
- 7 QThread-воркеров с контрактом
- 2 `QAbstractItemModel` (дерево tristate, таблица с proxy-сортировкой)
- 3 LLM-обёртки (Ollama / Web / BomjAPI)
- PyInstaller (Linux + Windows, CI-матрица)
- Pre-commit (ruff + pytest + hygiene)
- 10 ADR + `CONTEXT.md`
- 275+ тестов

**Cleanup:**
- `PIG_T3/gui/` удалён (ADR-005 / T-008)
- `PKG-INFO` untracked

### v1.x — Tkinter GUI (предыдущая версия)

Контекст-генератор, JSON-патчер, план, анализ, оптимизатор — на Tkinter.
Заменено в v2.0.0.

---

## 📄 Лицензия

MIT — см. [LICENSE](LICENSE).

---

## 🙏 Благодарности

PySide6, Qt-Material, Radon, Pylint, Vulture, Bandit, NetworkX,
Playwright, Ollama, LM Studio, sqlite-vec, rank-bm25, watchdog.

---

> Форк. Оригинал: `pip install pig-t3`.
> Автор оригинального PIG-T3 — Loki (gosoftware2025@gmail.com).
