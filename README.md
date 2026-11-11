# 🐖 PIG-T3 — AI Context Generator & Patcher (форк)

Десктоп-приложение (**PySide6 + Qt-Material**) для работы с большими
кодовыми базами вместе с AI-ассистентами (ChatGPT, Claude, DeepSeek,
локальные модели Ollama).

Генерирует **отчёт-контекст** с полной структурой проекта и исходниками
для отправки в LLM. Применяет **JSON-патчи от AI** автоматически
(create / edit / move / delete) с undo/redo и бэкапами.

Дополнительно:
- 📝 **План проекта** — пошаговые планы из описания + автоматическое выполнение
- 🔍 **Анализ кода** — офлайн-аудит Python (Radon CC/MI, Pylint, Bandit)
- 🧠 **Оптимизация контекста** — отбор релевантных файлов через граф зависимостей + LLM-ранжирование
- 🧠 **RAG-оптимизация** (опционально) — семантический отбор через
  Ollama `nomic-embed-text` или `sentence-transformers`; индекс
  `.pig/rag.db`, BM25+vector+RRF. См. [ADR-011](docs/adr/011-rag.md).

**Это форк.** Оригинальный PIG-T3 — `pip install pig-t3`.
GUI переписан с Tkinter на PySide6 в v2.0.0. См. [docs/adr/](docs/adr/).

---

## ✨ Возможности

### 🏠 Генератор
- Сканирование папки, ignore-лист, фильтр по расширениям.
- Один `.txt` с XML-тегами `<file path="...">`.
- Опции: нумерация строк, инструкция для AI, пустые папки, авто-копирование.
- **Дерево с нативными чекбоксами** — клик по строке = toggle (папка каскадом).
  «🌐 Весь проект» — tristate select-all. Состояние сохраняется в `.pig/state.json`.
- **Оптимизация контекста** — задача, % сжатия, BFS-глубина, модель.

### ✏️ Редактор (JSON Patcher)
- Вставка JSON-ответа LLM, валидация, pretty-print.
- Действия: `create`, `edit`, `move`, `delete`.
- Undo/Redo с бэкапами в `.pig/backups/<uuid>/{before,after}/` (лимит 10).
- **Auto-Fix** — починка битого JSON через Ollama / Web / BomjAPI.

### 📝 План
- Генерация плана из концепции (`GeneratePlanWorker`).
- Выполнение шага (`PlanStepWorker`): контекст → LLM → JSON → apply.
- Retry (2 попытки), выполнение всего плана с прогрессом и остановкой.
- **Git** — auto-commit перед шагом, опционально push.

### 📊 Анализ кода
- Radon CC, Radon MI, Pylint Score, Bandit — в фоне, с отменой.
- `QTableView` с цветовой индикацией, панель деталей.
- Свёрнутый вид — только `path` + сортируемая метрика.

### ⚙️ Настройки
- Тема, шрифт, высота строк, вес оптимизатора, Git, LLM-таймауты,
  видимость вкладок. Применяются без перезапуска.

### 🤖 Бэкенды LLM

| Бэкенд | Где работает |
| :--- | :--- |
| Ollama | Локально (`qwen2.5-coder` и др.) |
| Web: DeepSeek | chat.deepseek.com через Playwright |
| Web: Gemini | AI Studio через Playwright |
| BomjAPI | Ручной ввод (промпт/ответ) для любого веб-чата |

---

## 📦 Установка (форк)

Требуется **Python 3.10+** и **uv** (или `pip`).

```bash
git clone https://github.com/ProgrammerForeve/pig-t3-qt pig-t3-fork
cd pig-t3-fork
uv sync --extra dev          # runtime + dev + PySide6 + qt-material
```

Для Web-бэкендов:

```bash
uv run playwright install chromium
```

**Не** ставится через `pip install pig-t3` — это оригинал, здесь другой код.

---

## 🚀 Быстрый старт

Точки входа:

```bash
uv run python -m PIG_T3      # как модуль
uv run python run.py         # из корня репо
uv run pig-t3                # console script (если ставили через pip install -e .)
./dist/PIG-T3                # после сборки PyInstaller
```

Флоу:

1. **Генератор** → выбрать папку → «ГЕНЕРИРОВАТЬ КОНТЕКСТ» → `project_context.txt`.
2. Отправить файл в чат с AI.
3. **Редактор** → вставить JSON-ответ → «Проверить» → «Применить».
4. Или **План** — описать цель, выполнить шаги.

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
  {"action": "mark_step_completed", "step_id": "step_1", "completed": true}
]
```

⚠️ Для существующих файлов — **только** `edit`, не `create`.
В `replace_lines` не включайте неизменные соседние строки — будут дубли.

Полная спецификация — во вкладке **Инфо**.

---

## ⚙️ Конфигурация

| Файл | Что хранит |
| :--- | :--- |
| `app_config.json` | тема, шрифт, веса оптимизатора, Git, таймауты, `tabs_visibility`, `recent_projects` |
| `.pig/state.json` | `ui_tree_expanded`, `ui_tree_unchecked`, `history_stack`, `redo_stack` (per-project) |
| `.pig/plan.json` | план проекта |
| `.pig/backups/<uuid>/{before,after}/` | снапшоты для undo/redo |

**Миграция тем:** `pink` / `eye_care` → `light`, `dark_pink` → `dark`
при первой загрузке. `ui_scale` удаляется.

Дерево: expand/uncheck восстанавливаются между запусками и **не сбрасываются**
при изменении extensions/ignore (если папка проекта не менялась).

---

## 🐙 Git

Включается в **Настройки → Функционал → Git**. Перед шагом плана:

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
```

**Lint-скоуп:** `PIG_T3/gui_qt`, `PIG_T3/config.py`, `tests/`.
Legacy `PIG_T3/core/*`, `PIG_T3/utils/*` исключены (ADR-005).

**Pre-commit** (при каждом `git commit`):
- EOF, trailing-whitespace, merge-conflict, large-files
- `ruff` + `ruff-format` (только in-scope)
- `pytest tests/ -q --timeout=30 -x` (~10 сек, стоп на первом падении)

Обход: `git commit --no-verify`.

**Тесты:**

```bash
uv run pytest tests/ -v
uv run pytest tests/gui_qt/test_generator.py
uv run pytest -k threading
```

Покрытие:
- unit — модели, воркеры, диалоги
- **QThread-контракт** — сигналы, отдельный поток, UI не блокируется, отмена, без утечек
- **smoke** — все 5 вкладок нужных классов, нет `tkinter` и legacy-импортов

---

## 📦 Сборка

```bash
uv run pyinstaller pig_t3.spec --noconfirm
```

- Linux: `dist/PIG-T3`
- Windows: `dist/PIG-T3.exe`
- macOS: `dist/PIG-T3` (unsigned, `xattr -dr com.apple.quarantine` после переноса)

Спек бандлит PySide6, qt-material, иконки, зависимости анализатора.

**CI** — `.github/workflows/build.yml` на каждый push в `master` и тег `v*`:

| OS | Шаги | Артефакт |
| :--- | :--- | :--- |
| Ubuntu | Qt libs → pytest → build | `PIG-T3-linux` |
| Windows | deps → build | `PIG-T3-windows` |

Скачивать: **Actions → Build → Artifacts**.

---

## 🏗️ Архитектура

- **[`CONTEXT.md`](CONTEXT.md)** — глоссарий (вкладки, воркеры, модели, LLM-обёртки, файлы состояния), публичные API вкладок, чек-лист «как добавить вкладку».
- **[`docs/adr/`](docs/adr/)** — 10 ADR (PySide6, Qt-Material, QThread, QAbstractItemModel, scope, config compat, hotkeys, dialog wrappers, quintptr internalId, os._exit).

```
PIG_T3/
├── config.py                  # ConfigManager
├── main.py                    # entry point
├── core/                      # Бизнес-логика (без изменений при миграции)
│   ├── analyzer.py
│   ├── context_optimizer.py
│   ├── patcher.py
│   ├── ollama_client.py
│   ├── dependency_graph.py
│   ├── plan_validator.py
│   └── quality/               # radon/pylint/bandit
├── utils/                     # clipboard, dep_installer, web APIs, BomjAPI
└── gui_qt/                    # PySide6 GUI
    ├── app.py
    ├── main_window.py
    ├── theme.py
    ├── config_compat.py
    ├── tabs/                  # generator, info, editor, plan, quality
    ├── workers/               # 7 QThread-воркеров + llm_wrappers
    ├── models/                # project_tree, quality_table
    ├── widgets/               # project_tree_view
    └── dialogs/               # optimize, settings, new_plan
```

**Добавить вкладку** — см. `CONTEXT.md`. Кратко:
`tabs/<name>.py` → экспорт в `tabs/__init__.py` → ключ в `_TAB_KEYS` /
`_TAB_TITLES` → ветка в `_setup_tabs` → `stop_workers()` в `closeEvent`.

---

## 🩺 Проблемы

**`free(): invalid size` при выходе** — историческая проблема (T-107),
исправлена на 5 уровнях (ADR-009, ADR-010). Если вернулась — запустить с
`PIG_NO_SPLASH=1`, посмотреть `/tmp/pig_crash.log` (Linux) или
`%TEMP%\pig_crash.log` (Windows).

**`Gtk-Message: Failed to load module "xapp-gtk3-module"`** — безвредное
предупреждение GTK (Mint / XApps). Игнорировать или
`sudo apt install libxapp-gtk3-module`.

**Ctrl+C / Ctrl+V не работают** — не должно быть (ADR-007, нативные
Qt-хэндлеры). Сообщите файл и виджет.

**Тема «сломалась» после обновления** — `pink`/`eye_care` → `light`,
`dark_pink` → `dark` (ADR-002). Сменить акцент: `_QT_MATERIAL` в
`gui_qt/theme.py` (`dark_teal.xml`, `dark_blue.xml`, `light_teal.xml`,
`light_blue.xml`).

**PyInstaller: `attempted relative import`** — собирайте **только**
через `pyinstaller pig_t3.spec`, не `PIG_T3/main.py` (T-703).

---

## Changelog

### v2.0.0 — миграция на PySide6 (2026-11)

**Breaking:**
- GUI: Tkinter → PySide6 + Qt-Material
- Темы `pink` / `eye_care` / `dark_pink` удалены (миграция в `light`/`dark`)
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

Контекст-генератор, JSON-патчер, план, анализ, оптимизатор — всё на
Tkinter. Заменено в v2.0.0.

---

## 📄 Лицензия

MIT — см. [LICENSE](LICENSE).

---

## 🙏 Благодарности

PySide6, Qt-Material, Radon, Pylint, Vulture, Bandit, NetworkX, Playwright,
Ollama.

---

> Форк. Оригинал: `pip install pig-t3`.
> Автор оригинального PIG-T3 — Loki (gosoftware2025@gmail.com).
