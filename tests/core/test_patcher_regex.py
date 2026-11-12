"""Tests for regex in _apply_replace_text + command_allow_shell_operators."""

from __future__ import annotations

import json
import re

from PIG_T3.core.patcher import (
    _apply_replace_text,
    _parse_regex_find,
    apply_llm_changes,
)

# ---------- _parse_regex_find ----------


def test_parse_regex_basic():
    parsed = _parse_regex_find("/hello/")
    assert parsed is not None
    pattern, flags = parsed
    assert pattern == "hello"
    assert flags == 0


def test_parse_regex_flags():
    parsed = _parse_regex_find("/hello/im")
    assert parsed is not None
    pattern, flags = parsed
    assert pattern == "hello"
    assert flags & re.IGNORECASE
    assert flags & re.MULTILINE


def test_parse_regex_literal_returns_none():
    assert _parse_regex_find("hello world") is None
    assert _parse_regex_find("") is None
    assert _parse_regex_find("no-slashes") is None


def test_parse_regex_bad_flag_returns_none():
    assert _parse_regex_find("/hello/Z") is None


def test_parse_regex_unclosed_returns_none():
    assert _parse_regex_find("/hello") is None


# ---------- _apply_replace_text with regex ----------


def test_regex_replace_basic():
    text = "hello world"
    new, changed, status = _apply_replace_text(text, "/hello/", "bye")
    assert changed is True
    assert new == "bye world"
    assert "regex" in status


def test_regex_replace_case_insensitive():
    text = "Hello World"
    new, changed, _status = _apply_replace_text(text, "/hello/i", "bye")
    assert changed is True
    assert new == "bye World"


def test_regex_zero_matches():
    text = "nothing here"
    new, changed, status = _apply_replace_text(text, "/xyz/", "bye")
    assert changed is False
    assert new == text
    assert "0 matches" in status


def test_regex_invalid_pattern():
    text = "hello"
    new, changed, status = _apply_replace_text(text, "/[unclosed/", "bye")
    assert changed is False
    assert new == text
    assert "invalid regex" in status


def test_regex_rn_normalization_in_flexible():
    # literal find с \r\n должен всё равно найтись на файле с \r\n
    text = "def foo():\r\n    return 1\r\n"
    new, changed, _ = _apply_replace_text(
        text,
        "def foo():\r\n    return 1",
        "def foo():\r\n    return 2",
    )
    assert changed is True
    assert "return 2" in new


# ---------- command_allow_shell_operators через apply_llm_changes ----------


def _cmd_pipe():
    return json.dumps([{"action": "run_command", "command": "echo hi | head -1"}])


def test_pipe_rejected_by_default(tmp_path):
    # Без runner= → реальный run_command, whitelist применяется.
    # _is_whitelisted видит `|` → False → CommandWhitelistError →
    # patcher ловит и пишет `❌ run_command: ...` в лог.
    log = apply_llm_changes(
        _cmd_pipe(),
        str(tmp_path),
        allow_command_execution=True,
        command_whitelist="echo",
    )
    assert "❌ run_command" in log
    assert "✅ RUN" not in log


def test_pipe_allowed_with_shell_ops_optin(tmp_path):
    # allow_shell_operators=True → pipe разрешён → реально выполняется
    log = apply_llm_changes(
        _cmd_pipe(),
        str(tmp_path),
        allow_command_execution=True,
        command_whitelist="echo",
        command_allow_shell_operators=True,
    )
    assert "✅ RUN" in log
