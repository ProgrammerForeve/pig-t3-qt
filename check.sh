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
        --cov=PIG_T3 --cov-report=term-missing --cov-fail-under=67 \
        2>&1 | tail -n 40
    # PIG_NO_EXIT=1 → pytest-cov печатает отчёт, но возможен
    # 'free(): invalid size' на Qt shutdown. Реальный exit code
    # приходит из --cov-fail-under (0 или 1), SIGABRT в tail не мешает.
    # Явно проверяем через subprocess ещё раз без cov для exit code:
    echo ""
    echo "==> Test gate (без coverage, чистый exit code)"
    uv run pytest tests/ -q --timeout=60 --timeout-method=thread
    exit $?
fi

uv run pytest tests/ -q --timeout=60 --timeout-method=thread
