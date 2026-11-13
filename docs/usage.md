# Usage — JSON-патчи и API

Примеры для фич из ADR-014…017. Все действия — элементы корневого
JSON-массива (см. `core/analyzer.py::_write_patching_instructions`).

---

## ADR-014 — Flow control

Поля на каждом действии:
- `id: str` — уникальный id (для ссылок из `depends_on`)
- `depends_on: list[str]` — выполнять только если все deps = `ok`
- `on_failure: "continue" | "abort" | "rollback"` — `abort` останавливает
  массив; `rollback` = abort + restore `before/` из `.pig/backups/<id>/`
- `on_success: "continue" | "abort"` — `abort` останавливает массив
  после успешного действия

### Пример: DAG с проверкой

```json
[
  {
    "id": "e1",
    "action": "edit",
    "path": "src/a.py",
    "operations": [
      {"type": "replace_lines", "start": 10, "end": 12, "content": "    new_code()"}
    ]
  },
  {
    "id": "e2",
    "action": "edit",
    "path": "src/b.py",
    "operations": [
      {"type": "insert_after_line", "line": 5, "content": "    return True"}
    ],
    "depends_on": ["e1"]
  },
  {
    "id": "t",
    "action": "run_command",
    "command": "pytest tests/ -q",
    "depends_on": ["e1", "e2"],
    "on_failure": "rollback"
  }
]
```

Если `e1` упадёт → `e2` и `t` skipped (транзитивно). Если `t` упадёт
(non-zero exit) → restore `before/` для всех затронутых путей.

### Пример: `on_success: abort` (стоп после успеха)

```json
[
  {
    "id": "first",
    "action": "create",
    "path": "marker.txt",
    "content": "done\n",
    "on_success": "abort"
  },
  {"action": "create", "path": "never.txt", "content": "x\n"}
]
```

`never.txt` не будет создан.

---

## ADR-016 — Retry с контекстом

### `retry_with_context` (на `edit`)

Если `replace_text` не находит фрагмент, патчер запускает fuzzy-поиск
(`difflib`, threshold 0.6) и складывает `FailedEdit` в `patch_context`.
Caller (EditorTab / PlanStepWorker) может отправить retry-промпт в LLM.

```json
{
  "action": "edit",
  "path": "src/a.py",
  "on_failure": "retry_with_context",
  "operations": [
    {"type": "replace_text", "find": "def foo(a, c):", "replace": "def foo(a, b):"}
  ]
}
```

### `read_lines` — запросить контекст у LLM

```json
{"action": "read_lines", "path": "src/a.py", "start": 10, "end": 30}
```

`end - start ≤ 200`. Результат попадает в `patch_context["read_requests"]`
и добавляется в следующий промпт. Чистое чтение — не требует
`allow_command_execution`.

### Retry-промпт (внутренний API)

```python
from PIG_T3.core.multi_turn import build_retry_prompt

prompt = build_retry_prompt(
    failed_edits=ctx["failed_edits"],      # list[FailedEdit]
    read_requests=ctx["read_requests"],    # list[dict]
    original_response=llm_text,            # исходный JSON-патч
)
# prompt — компактный текст с ошибками + best_match + контекстом
```

---

## ADR-017 — run_command batch

### Одиночная команда (legacy)

```json
{"action": "run_command", "command": "pytest tests/ -q"}
```

### Batch — несколько команд в одном действии

```json
{
  "action": "run_command",
  "commands": ["pytest tests/ -q", "ruff check PIG_T3/"],
  "report_mode": "summary",
  "on_failure": "abort",
  "output_path": ".pig/cmd/verify.log"
}
```

- `command` XOR `commands` — оба сразу → ошибка парсинга
- `report_mode: "summary"` — одна строка `✅ RUN 2/2` или
  `❌ RUN 1/2: [2] ruff (failed)` (с индексом упавшей команды)
- `report_mode: "full"` — полный stdout/stderr каждой команды (default
  для одиночной)
- `output_path` — combined лог всех команд в один файл
- `on_failure: "abort"` — остановить после первой non-zero

### Whitelist

```json
{
  "action": "run_command",
  "commands": ["pytest tests/", "ruff check PIG_T3/"],
  "on_failure": "abort"
}
```

При непустом `command_whitelist` в настройках (например
`"pytest,ruff"`) команда должна начинаться с разрешённого токена.
По умолчанию (`command_allow_shell_operators: false`) составные
команды (`;`, `&&`, `|`, `$()`) блокируются.

---

## ADR-015 — History tree (API, UI pending)

Data-layer для git-like истории. UI (`HistoryTab`) — TODO.

```python
from PIG_T3.core.history_tree import HistoryTreeManager

mgr = HistoryTreeManager(root_folder)

# Записать применение патча
nid = mgr.apply(
    action_summary="created a.py",
    files=["a.py"],
    source="editor",       # "editor" | "plan"
    backup_id="uuid-...",  # = patch_id из ApplyWorker
)

# Откатить (current → parent)
node = mgr.undo()
# node.status == "rolled_back", node.files — какие файлы трогались

# Повторить (current → newest rolled_back child)
node = mgr.redo()

# Ветвление: следующий apply пойдёт от node_id
mgr.branch_from(node_id)
```

Persist: `.pig/history_tree.json` — `{current, nodes: {id: HistoryNode}}`.
`backup_id` линкует ноду к `.pig/backups/<id>/before|after/` (undo/redo
восстанавливает файлы из бэкапа).
