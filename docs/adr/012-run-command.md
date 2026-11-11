# ADR-012: `run_command` — выполнение shell-команд из JSON-патча

## Статус
Принято (2026-11)

## Контекст
AI-агенты (особенно code-focused, как Qwen-Coder, Claude, GPT)
при написании кода часто хотят проверить результат: `pytest`,
`ruff check`, `mypy`, `git status`. В PIG-T3 патч применялся
«слепо» — AI писал код, пользователь видел результат, но не мог
попросить агента тут же протестировать.

## Решение
Добавить действие `run_command` в JSON-патч:

```json
[
  {"action": "create", "path": "tests/test_x.py", "content": "..."},
  {
    "action": "run_command",
    "command": "pytest tests/test_x.py -v",
    "output_path": ".pig/cmd/pytest_x.log",
    "timeout_sec": 120,
    "on_failure": "abort",
    "explanation": "Verify the new test passes"
  }
]
```

## Модель безопасности

| Риск | Митигация |
| :--- | :--- |
| RCE через вредоносный AI | Opt-in (`allow_command_execution: false` в default) |
| Случайное выполнение | Confirm в `DiffDialog` — команды показываются как `$ pytest …` до apply |
| Бесконечный цикл | Timeout 1..3600 сек, default 120 |
| Порча файлов вне проекта | `output_path` через `Path.relative_to` (не выйти за root) |
| Огромный вывод | Truncate stdout/stderr до 1 MB |
| Шумные команды | Опциональный `command_whitelist` (первая команда: `pytest,ruff,…`) |
| Секреты в логах | `.pig/cmd/` в `.gitignore` |

**Явное ограничение:** `shell=True`, `cwd=root_folder`. AI может
написать `bash -c "cd /; rm ..."`. Opt-in это **допускает** —
пользователь принимает риск. Не включайте `allow_command_execution`
на недоверенных проектах.

## Поведение

### Editor (ручной apply)
- `_on_preview` → `extract_commands` → `DiffDialog(diffs, commands)`
- Команды показываются как `$ …`, с `timeout`, `output_path`
- «Применить» → выполняются в порядке JSON. `on_failure: abort`
  при не-нулевом exit code останавливает пайплайн
- Уже созданные файлы остаются, undo доступен

### Plan step (авто)
- Confirm не показывается (opt-in — это и есть подтверждение)
- `on_failure: abort` → `step.status = "failed"`, `report` содержит
  exit code и вывод
- Retry через стандартную кнопку

### Full plan
- Abort на шаге N → весь пайплайн остановлен, шаг N в `failed`

## Обоснование

**Почему opt-in, а не default:** shell-команда из ответа LLM
эквивалентна выполнению произвольного кода. Для большинства
пользователей патч без `run_command` — норма. Opt-in позволяет
включить self-validating workflow осознанно.

**Почему confirm в Editor:** `run_command` — самый опасный тип
действия в патче. Editor — ручной режим, показать команду перед
запуском дёшево и резко снижает риск.

**Почему нет confirm в Plan:** plan — автоматический режим,
подтверждать каждую команду убивает смысл. Opt-in в Settings —
единая точка.

**Почему shell=True, а не shlex:** пользователи AI пишут
`pytest tests/ -v && ruff check`; shell=True это поддерживает.
`shlex` требует массивов, что усложняет формулировку в JSON.
Риск компенсирован opt-in + whitelist.

**Почему не Docker-песочница:** для соло-разработчика требование
Docker слишком тяжёлое. `run_command` с `cwd=root` — практичный
баланс. Docker-режим — future work (ADR-TBD).

## Последствия

- `.pig/cmd/` в `.gitignore`
- +200 KB к `.exe` (`command_runner.py` + тесты не пакуются)
- Frozen `.exe`: `shell=True` работает на Windows (cmd.exe) и Linux
  (bash/sh)
- `PIPELINE ABORTED` — текстовый маркер в логе, который видят
  `ApplyWorker` и `PlanStepWorker` для перехода в `failed`