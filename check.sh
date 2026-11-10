#!/usr/bin/env bash
set -uo pipefail

# Линтим только новый код. Legacy (PIG_T3/gui, PIG_T3/core,
# PIG_T3/utils/*, PIG_T3/main.py) — вне scope миграции (см. ADR-005).
TARGETS="PIG_T3/gui_qt PIG_T3/config.py tests"

uv run ruff check $TARGETS --fix --unsafe-fixes
uv run ruff format $TARGETS
uv run pytest tests/ -v --timeout=60 --timeout-method=thread