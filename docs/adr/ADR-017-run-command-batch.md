# ADR-017: run_command Batch

## Status
Accepted (2026-11-14)

## Context
Валидация после правок — это обычно несколько команд: `pytest tests/ -q`,
`ruff check PIG_T3/`, `git diff --stat`. Legacy `run_command` принимал
одну строку — LLM генерировал N отдельных действий, каждое писал свой
output_path, дублировал `output_path` и шумел в чате.

## Decision
1. **XOR `command` / `commands`** в `run_command`: либо одна строка
   (legacy), либо `list[str]` (batch). Проверяется в начале
   `apply_llm_changes` и в цикле run_command.
2. **`report_mode: "summary" | "full"`** — default `summary` для batch,
   `full` для одиночной. В summary пишется одна строка `✅ RUN 2/2` или
   `❌ RUN 1/2: pytest failed` + failure summary от
   `command_runner.summarize_output` (pytest/ruff/mypy-паттерны).
3. **Combined output_path** для batch: все команды + их stdout/stderr
   пишутся в один `.pig/cmd/verify.log` (а не N файлов).
4. **`on_failure: "abort"`** для batch — останавливает массив после
   первой non-zero exit code.

## Consequences
- `diff_preview.extract_commands` возвращает `CommandSpec` per-команду
  с `batch_index` / `batch_size` для UI.
- `DiffDialog` рисует `[1/2] $ pytest`, `[2/2] $ ruff`.
- Покрытие: `tests/core/test_patcher_run_command_batch.py` (9 тестов).
- Legacy `command: "..."` работает без изменений.
