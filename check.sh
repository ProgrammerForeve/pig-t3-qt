#!/usr/bin/env bash
set -uo pipefail

TARGETS="PIG_T3/gui_qt PIG_T3/config.py tests"

uv run ruff check $TARGETS --fix --unsafe-fixes
uv run ruff format $TARGETS

if [ "${1:-}" = "--cov" ]; then
    echo ""
    echo "==> pytest + coverage"
    PIG_NO_EXIT=1 uv run pytest tests/ -q \
        --timeout=60 --timeout-method=thread \
        --cov=PIG_T3 --cov-report=term-missing --cov-fail-under=67
    COV_RC=$?
    if [ "$COV_RC" -ne 0 ]; then
        echo ""
        echo "⚠️ Coverage below threshold or tests failed (exit $COV_RC)"
    fi
    exit $COV_RC
fi

uv run pytest tests/ -q --timeout=60 --timeout-method=thread
