#!/usr/bin/env bash
set -uo pipefail

TARGETS="PIG_T3/gui_qt PIG_T3/config.py tests"

uv run ruff check $TARGETS --fix --unsafe-fixes
uv run ruff format $TARGETS
uv run pytest tests/ -v --timeout=60 --timeout-method=thread

# Coverage — отдельно, без задержки хуков
if [ "${1:-}" = "--cov" ]; then
    echo ""
    echo "==> Coverage report"
    PIG_NO_EXIT=1 uv run pytest tests/ -q --timeout=60 \
        --cov=PIG_T3 --cov-report=term-missing --cov-fail-under=60
    COV_RC=$?
    if [ "$COV_RC" -ne 0 ]; then
        echo ""
        echo "⚠️ Coverage below threshold or tests failed (exit $COV_RC)"
    fi
fi
