# ADR-017: `run_command` с batch (`commands[]`) + `report_mode`

## Статус
Принято (2026-11-13, ожидает реализации)

## Контекст

ADR-012 ввёл `run_command` (single). ADR-014 — `on_failure`/`on_success`/`depends_on`. ADR-016 — `read_lines` для multi-turn.

Задача: **автоматизировать цикл «применил → проверил → отчёт»**. AI хочет в одном патче: сделать 5 правок + запустить pytest + ruff, и получить **короткий** отчёт (успех/провал + traceback), а не полный 100KB stdout.

Сейчас: каждая команда — отдельный `run_command`. 5 команд = 5 actions + 5 output_path. Полный stdout в каждом. Нет агрегированного отчёта.

## Решение

**Расширить `run_command`, не создавать `run_batch`.**

```json
{
  "action": "run_command",
  "command": "pytest tests/ -q",
  "commands": ["pytest tests/ -q", "ruff check PIG_T3/", "mypy PIG_T3/"],
  "report_mode": "summary",
  "output_path": ".pig/cmd/verify.log",
  "on_failure": "abort",
  "timeout_sec": 120
}
```

### Правила

- **`command` XOR `commands`** — оба → ошибка парсинга до apply
- **`report_mode`**: `"summary"` (default для `commands`), `"full"` (default для `command`)
- **Whitelist** — каждая команда из `commands` проверяется **отдельно** (не только первая)
- **`on_failure: "abort"`** — abort всего пайплайна при провале **любой** команды
- **`timeout_sec`** — per-command (не общий на batch)
- **`output_path`** — full log **всех** команд в один файл с маркерами `=== cmd N: ... ===`

### `report_mode: "summary"` — что показывает

**Успех** (все exit=0):
```
✅ RUN 3/3: pytest, ruff, mypy (exit=0)
```

**Провал** (хоть одна exit≠0):
```
❌ RUN 2/3: mypy (exit=1)
─── mypy ───
path/to/file.py:42: error: Argument 1 has incompatible type
path/to/file.py:88: error: Missing return statement
─── pytest ───
965 passed in 45s
```

**Фильтрация для failure:**
1. Regex: `^(FAILED|ERROR|error:|E\s{2,}|File "|assert|Traceback)` — pytest/ruff/mypy/pylint/bandit
2. Fallback: последние 20 строк (если паттернов < 5) — для нестандартного вывода
3. Truncate: 100 строк на команду

### Публичный API (backward compat)

`run_command` в `core/command_runner.py` — сигнатура не меняется. Batch реализуется в `patcher.py::apply_llm_changes`:

```python
if "commands" in action and action["commands"]:
    for i, cmd in enumerate(action["commands"], 1):
        result = run_command(cmd, ...)  # существующая
        # aggregate
else:
    result = run_command(action["command"], ...)  # как сейчас
```

### Автоматизация «применил → проверил»

AI генерирует:
```json
[
  {"action": "edit", "path": "a.py", "operations": [...]},
  {"action": "run_command",
   "commands": ["pytest tests/ -q", "ruff check PIG_T3/"],
   "report_mode": "summary", "on_failure": "abort",
   "output_path": ".pig/cmd/verify.log"}
]
```

После apply — одна строка (успех) или отфильтрованный traceback (провал). Если нужен полный stdout — `read_lines` (ADR-016) на `.pig/cmd/verify.log`.

## Обоснование

**Почему не `run_batch`:**
- Ломает системпромт (AI уже знает `run_command`), ломает whitelist логику (дублировать), ломает `output_path` (тот же формат), ломает тесты.
- `command`/`commands` — ортогонально, `commands` = цикл по `command`.

**Почему summary по умолчанию для batch:**
- 3-5 команд × 50-100KB stdout = 300KB в диалоге. Бесполезно для AI.
- Summary даёт «что упало + почему» — 90% кейсов.
- Full — если AI явно хочет разобраться в деталях (`report_mode: "full"` или `read_lines`).

**Почему whitelist по каждой:**
- `["pytest", "rm -rf /"]` — если проверять только первую (`pytest`), `rm` пройдёт. Безопасность.

**Почему fallback «последние 20 строк»:**
- Не всё матчится паттернами (custom scripts, obscure tools).
- Последние 20 строк — обычно где ошибка (exit code, stack trace tail).
- Если паттернов уже 5+ — 20 строк могут быть шумом, не добавляем.

## Последствия

**Код:**
- `core/patcher.py::apply_llm_changes` — парсинг `commands`, цикл, агрегация, `report_mode`
- `core/command_runner.py` — без изменений (batch в patcher, `run_command` = single)
- `core/analyzer.py::_write_patching_instructions` — документировать `commands` + `report_mode` (+5 строк)
- `config.py`: `command_summary_max_lines: 100` (truncate), `command_summary_min_matches: 5` (fallback threshold)
- Тесты: `test_patcher_run_command_batch.py` (~8): summary success, summary fail, full mode, whitelist reject, timeout per-command, on_failure abort

**Backward compat:**
- `command` (single) — работает как сейчас, `report_mode: "full"` default
- `commands` — новый, не ломает
- Старые патчи (без `commands`) — не затронуты

**Token savings:**
- 3 команды × 50KB stdout = 150KB → summary: 200-500 байт (−99.7%)
- С `read_lines` для деталей — 500-2000 байт (−98%)

## Принятые решения

1. **`run_batch` vs `run_command` + `commands`** → `run_command` (без новой сущности).
2. **Whitelist** → каждая команда отдельно.
3. **Timeout** → per-command.
4. **`on_failure`** → abort всего пайплайна при любой failed команде.
5. **`report_mode` default** → `summary` для batch, `full` для single.
6. **Фильтрация** → regex-паттерны + fallback last-20-lines + truncate 100.
