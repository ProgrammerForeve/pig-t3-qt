# ADR-014: Hooks (on_failure/on_success) и flow control в JSON-патче

## Статус
Предложено (2026-11-13)

## Контекст

Текущий JSON-патч (см. ADR-012):
- `run_command` имеет `on_failure: "continue" | "abort"`
- Остальные действия (`create`/`edit`/`move`/`delete`) при ошибке просто пишут в лог и продолжают
- Нет способа выразить: «запусти тесты ТОЛЬКО если все патчи применились успешно»
- Нет способа выразить: «откати все изменения если хоть один шаг упал»
- Нет способа выразить: «после успешных тестов — обнови документацию и закоммить»

Типичный workflow для AI-агента (PIG-T3 как «self-validating»):
1. Применить N файловых правок
2. Запустить тесты (pytest/ruff/mypy)
3. Если тесты зелёные — обновить docs + git commit
4. Если тесты упали — откатить все правки, не оставляя мусора

Сейчас это выразить нельзя: `run_command` с `on_failure: "abort"` остановит пайплайн, но `create`/`edit` перед ним уже применились и не откатятся автоматически.

## Решение

Расширить JSON-патч опциональными полями flow control. Все поля snake_case — консистентно с существующими (`on_failure`, `output_path`, `timeout_sec`, `step_id`).

### 1. `id` (new, все действия)

Строковый идентификатор действия. Нужен для `depends_on`. Дубликаты в одном патче → ошибка парсинга до apply.

### 2. `on_failure` (extend, все действия)

Расширить на **все** действия (сейчас только `run_command`):
- `"continue"` (default) — лог, продолжить
- `"abort"` — остановить пайплайн, `PIPELINE ABORTED`
- `"rollback"` — остановить + откатить все применённые действия в этом патче (через `.pig/backups/<uuid>/{before,after}/`)
- `"retry_with_context"` (только `edit`) — см. ADR-016 (future work)

### 3. `on_success` (new, все действия)

- `"continue"` (default)
- `"abort"` — если действие **успешно** — остановить пайплайн

Редкий кейс (симметрия). Например `edit` как «проба» — если неожиданно нашёлся, это ошибка.

### 4. `depends_on` (new, все действия)

Список `id`. Действие выполняется **только если** все зависимости успешно завершились. Если хоть одна упала → действие **пропускается** (skip в логе, не fail).

```json
[
  {"id": "edit_a", "action": "edit", "path": "a.py", "operations": [...], "on_failure": "abort"},
  {"id": "edit_b", "action": "edit", "path": "b.py", "operations": [...], "on_failure": "abort"},
  {"id": "test", "action": "run_command", "command": "pytest tests/ -q",
   "depends_on": ["edit_a", "edit_b"], "on_failure": "abort"},
  {"id": "docs", "action": "edit", "path": "README.md", "operations": [...],
   "depends_on": ["test"]},
  {"id": "commit", "action": "run_command",
   "command": "git add -A && git commit -m 'AI: ...'",
   "depends_on": ["test", "docs"], "on_failure": "abort"}
]
```

### Что НЕ в v1 (сознательно)

- **`phase`** (явные фазы apply/validate/finalize) — reject. `depends_on` покрывает все кейсы, гибче, стандарт (DAG).
- **`on_not_found`** (отдельный хук для `edit`) — reject. `on_failure: "retry_with_context"` проще, и в будущем единый механизм.
- **Multi-turn feedback loop** — отдельный ADR-016 (меняет сигнатуру `apply_llm_changes`: dict, не строка лога).
- **Retry с backoff** — future work, для flaky `run_command` (не для LLM-патчей).

## Обоснование

**Почему `on_failure: "rollback"` а не автоматический rollback при `abort`:**
- Rollback — дорогая операция (чтение snapshot, запись). Для большинства случаев `abort` + пользователь смотрит diff — достаточно.
- Явный `rollback` заставляет AI-агента думать о транзакционности.

**Почему `depends_on` а не `phase`:**
- `phase: "apply"` — жёсткая таксономия, AI-агент должен угадывать границы.
- `depends_on` — явно, любой DAG, работает для «test after edit_a (только)».

**Почему snake_case, не camelCase:**
- Уже есть `on_failure`, `output_path`, `timeout_sec`, `step_id`.
- Многие AI-tools используют camelCase (`onFailure`), но консистентность **внутри проекта** важнее.
- Не переименовываем существующий `on_failure`.

**Почему `retry_with_context` — отдельный ADR:**
- Требует: структурированный failure из `apply_llm_changes`, цикл запроса-ответа с LLM, интеграция с PlanTab retry. Смешивать в ADR-014 — расплывание scope.

## Последствия

**Код:**
- `core/patcher.py`: парсинг `id`, `on_failure` (все actions), `on_success`, `depends_on`; `_applied: dict[str, bool]` для tracking; `_rollback_applied()` через `.pig/backups/`
- `core/analyzer.py::_write_patching_instructions` — документировать 4 поля + пример с `depends_on`. Системпромт +~10 строк.
- Тесты: `test_patcher_extra.py` (+8), `test_patcher_run_command.py` (adapt)

**Backward compat:**
- Все поля опциональны
- Без `depends_on` — линейная семантика как сейчас
- Без `rollback` — просто abort, файлы остаются применёнными

**Future work (ADR-016 TBD):**
- `on_failure: "retry_with_context"` для `edit`
- Multi-turn feedback loop (LLM видит контекст строк, переписывает JSON)
- Интеграция с PlanTab retry (сейчас retry перезапускает step полностью)

**Ограничение:**
- `depends_on` работает в пределах одного патча. Между шагами плана — своя логика.


## Принятые решения

1. **Rollback имплементация** → переиспользовать `.pig/backups/<uuid>/`. Snapshot уже создаётся `ApplyWorker` для undo/redo — тот же механизм. Для rollback: пройти по `_applied` в обратном порядке, для каждого применить `before/` из его backup. Никакого нового transaction log.

2. **`on_success` use case** → оставить для симметрии. Реального кейса сейчас нет (кроме «пробы edit»), но: (a) дёшево в реализации (~5 строк в парсере), (b) AI-агенты иногда генерируют симметричные структуры, (c) добавить обратно после релиза — breaking change в схеме. YAGNI-risk принят.

3. **Дубликаты `id`** → ошибка парсинга **до apply**. `clean_json_text` + `json.loads` → валидация: `len(ids) != len(set(ids))` → `return "❌ Дублирующиеся id в патче: ..."`. Не применяем ничего. Проще отладить, чем «последний побеждает».

4. **Per-action `rollback: true`** → **reject**. Оверхэд: backup перед каждым `create`/`move`/`delete` (уже делается в ApplyWorker для undo, но семантика «откатить если следующий abort» требует transaction log + reverse-операции для move). `on_failure: "rollback"` + существующие backups покрывают 95% кейсов.

5. **`depends_on` на skipped** → **каскад fail-safe**. Skipped считается «не succeeded» → зависимые тоже skip. Пример: A fail → B (dep: A) skip → C (dep: B) skip. Причина: если B не выполнился, файл в старом состоянии, C применится к неполному состоянию → скорее всего тоже упадёт или создаст невалидный код. Аналогия: Makefile не линкует `program` если `b.o` не собрался.
   - **`on_skip: "continue"`** — **не вводим** (YAGNI). Если появится реальный кейс «выполнить C даже если B skipped» — добавим как третий хук явно.
   - Пример в логе: `⏭ Skip C: B skipped (transitive: A failed)`.
