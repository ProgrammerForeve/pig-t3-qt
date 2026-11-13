# ADR-016: Retry упавших `edit` с контекстом (multi-turn feedback loop)

## Статус
Принято (2026-11-13, ожидает реализации)

## Контекст

Когда `edit` упал с `фрагмент не найден` — сейчас два варианта (ADR-014):
- `on_failure: "continue"` — лог `❌ Text Patch a.py: фрагмент не найден`, пайплайн идёт дальше (файл не изменён)
- `on_failure: "abort"` — `PIPELINE ABORTED`, пользователь видит diff и решает вручную

**Проблема**: LLM обычно **знает** где фрагмент — по номерам строк в контексте `project_context.txt` (`  15 | def foo():`). Но написала `find` с неправильными отступами / табами / соседними строками. Патч не применяется, хотя исправление — 1 строка.

`PlanStepWorker.retry` (сейчас) делает **полный** новый запрос:
- Собирает весь контекст заново (~10000 токенов на 50 файлов)
- Отправляет концепцию + план + контекст
- LLM отвечает с нуля

Это:
- **Дорого** (10000 токенов × N retry)
- **Медленно** (30-60 сек)
- **Неэффективно** — LLM заново генерирует весь патч из 5-10 actions, хотя упал 1

## Решение

Новый режим `on_failure: "retry_with_context"` (только `edit`).

### Сигнатура `apply_llm_changes`

```python
def apply_llm_changes(
    llm_response: str,
    root_folder: str,
    *,
    allow_command_execution: bool = False,
    command_whitelist: str | list[str] = "",
    command_default_timeout: int = 120,
    command_allow_shell_operators: bool = False,
    runner=None,
    patch_context: dict | None = None,  # NEW: out-param (backward compat)
) -> str:
    ...
    if patch_context is not None:
        patch_context["needs_retry"] = bool(failed_edits)
        patch_context["failed_edits"] = failed_edits  # list[FailedEdit]
        patch_context["applied_count"] = success_count
    return log_string
```

`patch_context` — opt-in. Без него — работает как раньше (`str` return, ничего не меняется). Существующие тесты не падают.

### `FailedEdit` dataclass

```python
@dataclass
class FailedEdit:
    path: str
    find: str                     # исходный find из JSON
    replace: str                  # исходный replace
    error: str                    # "not found (exact + flexible)"
    best_match_line: int | None   # L15 — где "почти" нашлось (fuzzy)
    best_match_ratio: float       # 0.85 — насколько похоже
    context_lines: list[str]      # ±20 строк вокруг best_match_line
    total_lines: int              # 42 — размер файла
```

### Fuzzy match в `_apply_replace_text`

При провале exact + flexible:
1. `difflib.SequenceMatcher` по `find.splitlines()` против скользящего окна `full_text`
2. Ratio > 0.6 → best_match_line = начало окна, best_match_ratio
3. Если ratio < 0.6 — `best_match_line = None` (нет смысла retry, LLM явно ошиблась)

Стоимость: `difflib` на 42 строках — < 1ms. На 2000 строках — ~50ms (только для failed edit, не для всех).

### Caller (PlanStepWorker / EditorTab)

```python
patch_context = {}
result = apply_llm_changes(
    response, root,
    on_failure="retry_with_context",
    patch_context=patch_context,
)
if patch_context.get("needs_retry"):
    retry_prompt = build_retry_prompt(
        original_response=response,
        failed_edits=patch_context["failed_edits"],
    )
    response2 = llm.ask(retry_prompt)  # ~500 токенов
    apply_llm_changes(response2, root, ...)  # до max_retries
```

### Retry prompt (что видит LLM)

```
Твой предыдущий JSON-патч применился частично.
Упавшие действия (нужно исправить):

1. edit `a.py`
   - find (первые 80 символов): `def foo():\n\treturn 1`
   - ошибка: фрагмент не найден (exact + flexible)
   - Похожий фрагмент около L15 (ratio 0.85):
     L14 |
     L15 | def foo():
     L16 |     return 1
     L17 |
   - Файл: 42 строки

Верни JSON-массив ТОЛЬКО для исправления упавших действий.
Предпочти `replace_lines` с точными номерами строк (start/end из L-меток).
```

**~500 токенов** вместо 10000 — в 20 раз дешевле.

### Ограничения

- **Max retries**: `quality_edit_retry_max` (default 2) в `config.py`
- **Только `edit`**: `create` не имеет find, `move`/`delete` идемпотентны, `run_command` retry = flaky (отдельный механизм)
- **`best_match_ratio < 0.6`** → `needs_retry = False`, сразу fail (не тратим токены на безнадёжный retry)
- **Timeout**: каждый retry — новый LLM-запрос. Для Ollama/LM Studio ~10-30 сек. Для Web — 60-120 сек

## Что НЕ в этом ADR (сознательно)

### `read_lines` как действие

```json
[{"action": "read_lines", "path": "a.py", "start": 10, "end": 25}]
```

**Решение: включить в v1** (2026-11-13).

Обоснование:
- Хотя `run_command: "sed -n '10,25p' a.py"` даёт то же — это **обходит whitelist** (`sed` редко в whitelist) и требует `allow_command_execution=true`
- `read_lines` — pure read, не требует whitelist, не считается «опасной командой»
- LLM **упреждающе** запрашивает строки: «хочу edit a.py, но не уверена в отступах → сначала read_lines 10-25, потом точный replace_lines»
- Работает в обоих случаях: (a) до apply (проактивно, multi-turn до), (b) в retry_with_context (реактивно, если ±N контекста недостаточно)

**Протокол:**

```python
def apply_llm_changes(
    llm_response, root, *, patch_context=None, ...
) -> str:
    read_requests: list[ReadRequest] = []
    for action in actions:
        if action["action"] == "read_lines":
            read_requests.append(ReadRequest(path, start, end))
            continue  # не применяем, не считаем за success/fail
        # ... обычная логика

    if patch_context is not None:
        patch_context["read_requests"] = read_requests
        patch_context["needs_retry"] = bool(read_requests) or bool(failed_edits)
        patch_context["failed_edits"] = failed_edits
        # read_lines результаты caller получит сам (читает файл)
    return log
```

**Caller (PlanStepWorker):**

```python
max_rounds = 3
for round in range(max_rounds):
    patch_context = {}
    result = apply_llm_changes(response, root, patch_context=patch_context)

    read_requests = patch_context.get("read_requests", [])
    if read_requests:
        # LLM хочет данные — читаем, отправляем обратно
        response = llm.ask(build_read_result_prompt(response, read_requests, root))
        continue  # следующий round

    if patch_context.get("failed_edits"):
        response = llm.ask(build_retry_prompt(response, patch_context["failed_edits"]))
        continue  # retry

    break  # успех
```

**`read_lines` в retry_with_context:**

Если `context_lines` из auto-fuzzy (Q4: 2-3× find.length) недостаточно — LLM в **следующем** JSON может добавить `read_lines` на весь файл или больше строк:

```json
[{"action": "read_lines", "path": "a.py", "start": 1, "end": 200}]
```

→ caller читает, отправляет 200 строк → LLM генерирует правильный `replace_lines`.

**Ограничения `read_lines`:**
- `end - start <= 200` (защита от «прочитай весь файл» — 200 строк ≈ 1000 токенов, норм)
- `path` через `_safe_path` (не выйти за root, ADR-012)
- Не считается `success`/`fail` — пропускается в счётчиках
- Max rounds (2-3) для защиты от бесконечного «read → wrong → read → wrong»
- Если файл > 200 строк и LLM просит `end-start > 200` → clamp до 200 + warning в лог

**Стоимость:**
- `read_lines` → 200 строк ≈ 1000 токенов
- Обычно 1 read_lines хватает → 1 round
- Итого 1 retry ≈ 500-1500 токенов (vs 10000 на полный re-request)

### Бесконечный retry

Не зацикливаемся. Если LLM после N retry не справилась — fail, пользователь смотрит diff, правит вручную или в Editor.

### Cross-step retry

Если шаг плана №3 упал с `retry_with_context`, а шаг №1 уже откатился (undo) — retry не имеет смысла. Cross-step — в ADR-015 (tree history), не здесь.

## Обоснование

**Почему `patch_context` а не `ApplyResult`:**
- `apply_llm_changes` возвращает `str` — 30+ тестов проверяют `assert "CREATE: a.py" in log`
- Сменить на dataclass → сломать все
- `patch_context` — out-param, opt-in, backward compat 100%

**Почему fuzzy 0.6 а не exact retry:**
- `replace_text` уже делает exact + flexible (ADR-006). Не нашли — значит отступы/символы расходятся **сильно**
- LLM часто пишет `return 1` с 4 пробелами вместо таба, или путает `def foo(self):` → `def foo():`
- fuzzy с 0.6 = «есть похожее, но не точное» — стоит retry
- ratio < 0.6 = «LLM вообще не про этот файл» — retry бесполезен

**Почему ±N строк контекста, где N = 2-3 × find.length:**
- LLM ищет фрагмент из K строк — контекст должен быть ≥ 2K, чтобы увидеть границы
- `find = 2 строки` → ±6 строк контекста (~50 токенов)
- `find = 10 строк` → ±30 строк контекста (~150 токенов)
- `find = 50 строк` → ±150 строк контекста (~500 токенов) — но для таких больших find обычно `replace_text` не используется
- **LLM может явно запросить больше** через `read_lines` (см. ниже) — если ±N недостаточно
- Default: `N = max(20, 2 * len(find.splitlines()))`, max 50 (защита от гигантских файлов)

**Почему только `edit`:**
- `create` — если файл уже существует, это не «not found», это «conflict». Retry не поможет, нужно `delete` + `create` или `edit`
- `move` — если target существует, retry = overwrite или rename. Не fuzzy-проблема
- `delete` — идемпотентно, нет «почти нашлось»
- `run_command` — retry = flaky тест (другой механизм, `timeout` + backoff)

## Последствия

**Код:**
- `core/patcher.py`: `FailedEdit` dataclass, `_find_near_match()`, `patch_context` параметр, `on_failure: "retry_with_context"` в парсере
- `core/analyzer.py::_write_patching_instructions`: документировать `retry_with_context` в списке `on_failure` значений (+3 строки)
- `gui_qt/workers/plan_step_worker.py`: `patch_context` + `build_retry_prompt()` + цикл retry с `max_retries`
- `gui_qt/tabs/editor.py`: кнопка «🔧 Retry with context» после failed diff (opt-in)
- `config.py`: `quality_edit_retry_max: 2`
- Тесты: `test_patcher_retry.py` (new, ~10), `test_plan_step_worker_retry.py` (new, ~5)

**Backward compat:**
- Без `patch_context` — работает как раньше
- `on_failure: "continue"` (default) — не триггерит retry
- `on_failure: "abort"` — не триггерит retry (пользователь контролирует)
- Только явный `on_failure: "retry_with_context"` → `patch_context["needs_retry"] = True`

**Стоимость:**
- Обычный патч: 0 retry, 0 overhead
- Failed edit + retry: ~500 токенов + ~10-30 сек (Ollama) или 60-120 сек (Web)
- Если ratio < 0.6 — 0 retry (безнадёжно)

**Token savings:**
- Сейчас: 10000 × N retry
- С retry_with_context: 500 × N retry
- Для 1 failed edit из 5: 10000 → 500 (−95%)

## Принятые решения

1. **PlanTab retry** → **два уровня**. Первый: `retry_with_context` (быстро, ~500-1500 токенов, только упавшие edits). Если не помог (max 2 retry) — второй: существующий полный retry (`_on_retry_clicked`, ~10000 токенов). Кнопка «🔄 Повторить шаг» использует **оба** последовательно: сначала `retry_with_context` (прозрачно для пользователя), потом полный retry (если первый не помог). Пользователь видит в логе: `🔧 retry_with_context: 1/2` → `🔄 full retry`.

2. **`on_failure: "retry_with_context"` + `depends_on`** → **retry прошёл = succeeded для downstream**. Если edit в итоге применился (после N retry) — `_applied[id] = True`, downstream `depends_on` видит success. Это логично: цель `retry_with_context` — сделать edit succeeded, не «сделать вид что failed».

3. **Fuzzy match threshold** → **0.6** (как в ADR). `SequenceMatcher.ratio() >= 0.6` → best_match найден, стоит retry. `< 0.6` → `needs_retry = False`, сразу fail (не тратим токены). A/B на реальных патчах покажет, надо ли 0.5 или 0.7 — но 0.6 разумный дефолт.

4. **`context_lines` > 20** → **N = max(20, 2-3 × find.length)**, max 50. LLM может запросить больше через `read_lines` (см. ниже). Не нужно отдельного config-ключа `quality_edit_retry_context_lines` — эвристика достаточна. Для функции 100 строк `find.length` = 2-5 строк (сама сигнатура + пара строк) → N = 20-30, достаточно. Если `find` = 50 строк (редко) → N = 50 (max).

5. **`read_lines` future work** → **включено в v1** (2026-11-13). См. секцию «`read_lines` как действие» выше. Отвечает на «нужно, хотя это повторяет обычный grep/find» — да, но `read_lines` не требует `allow_command_execution=true` и whitelist (pure read). Плюс в retry-цикле LLM **сама** может запросить больше контекста, если auto-fuzzy недостаточно.

6. **Multi-turn vs single-turn** → **обрезать original patch до 2000 токенов**. В retry prompt включаем:
   - `failed_edits` (полностью, с context_lines)
   - **surrounding actions** (±2 действия вокруг failed, чтобы LLM понимала контекст пайплайна)
   - **не** весь original patch (может быть 20 actions × 500 токенов = 10000, обрезка)
   - Маркер `... (N действий до/после опущены)`
