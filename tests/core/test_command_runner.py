"""C6a: command_runner — run_command, whitelist, timeout, output_path."""

from __future__ import annotations

import sys

import pytest

from PIG_T3.core.command_runner import (
    CommandWhitelistError,
    _is_whitelisted,
    _safe_output_path,
    parse_whitelist,
    run_command,
)

_SHELL_ECHO = "echo hello"
_SHELL_EXIT = "exit 1" if sys.platform != "win32" else "cmd /c exit 1"
_SHELL_SLEEP = "sleep 10" if sys.platform != "win32" else "timeout /t 10 /nobreak"


def test_run_echo_ok(tmp_path):
    r = run_command(_SHELL_ECHO, cwd=str(tmp_path), timeout=5)
    assert r.ok
    assert r.returncode == 0
    assert "hello" in r.stdout


def test_run_exit_nonzero(tmp_path):
    r = run_command(_SHELL_EXIT, cwd=str(tmp_path), timeout=5)
    assert not r.ok
    assert r.returncode != 0


def test_run_empty_command(tmp_path):
    r = run_command("", cwd=str(tmp_path))
    assert r.returncode == -1
    assert "empty" in r.stderr.lower()


def test_run_timeout(tmp_path):
    r = run_command(_SHELL_SLEEP, cwd=str(tmp_path), timeout=1)
    assert r.timed_out
    assert r.returncode == -1
    assert "timed out" in r.stderr.lower()


def test_run_bad_cwd_returns_error(tmp_path):
    r = run_command(_SHELL_ECHO, cwd=str(tmp_path / "nope"))
    assert r.returncode == -1


# ---------- whitelist ----------


def test_parse_whitelist_str():
    assert parse_whitelist("pytest, ruff , git") == ["pytest", "ruff", "git"]


def test_parse_whitelist_list():
    assert parse_whitelist(["pytest", " ", "ruff"]) == ["pytest", "ruff"]


def test_parse_whitelist_empty():
    assert parse_whitelist(None) == []
    assert parse_whitelist("") == []


def test_is_whitelisted_empty_allows():
    assert _is_whitelisted("rm -rf /", [])


def test_is_whitelisted_hit():
    assert _is_whitelisted("pytest tests/", ["pytest", "ruff"])


def test_is_whitelisted_miss():
    assert not _is_whitelisted("rm -rf /", ["pytest"])


def test_run_whitelist_rejects(tmp_path):
    with pytest.raises(CommandWhitelistError):
        run_command("rm -rf .", cwd=str(tmp_path), whitelist=["pytest"])


# ---------- output_path ----------


def test_safe_output_path_inside(tmp_path):
    p = _safe_output_path(".pig/cmd/x.log", str(tmp_path))
    assert p is not None
    assert str(p).startswith(str(tmp_path.resolve()))


def test_safe_output_path_outside(tmp_path):
    assert _safe_output_path("../escape.log", str(tmp_path)) is None


def test_safe_output_path_root_itself(tmp_path):
    assert _safe_output_path("", str(tmp_path)) is None


def test_run_writes_output(tmp_path):
    r = run_command(
        _SHELL_ECHO,
        cwd=str(tmp_path),
        timeout=5,
        output_path=".pig/cmd/test.log",
    )
    assert r.output_path is not None
    out_file = tmp_path / ".pig" / "cmd" / "test.log"
    assert out_file.exists()
    content = out_file.read_text(encoding="utf-8")
    assert "hello" in content
    assert "exit_code: 0" in content


def test_run_output_outside_rejected(tmp_path):
    r = run_command(
        _SHELL_ECHO,
        cwd=str(tmp_path),
        timeout=5,
        output_path="../escape.log",
    )
    assert r.output_path is None
    assert "вне проекта" in r.stderr
    assert not (tmp_path.parent / "escape.log").exists()


def test_run_output_truncated_if_huge(tmp_path):
    # генератор большого вывода
    cmd = "python -c \"print('x' * 2000000)\""
    r = run_command(cmd, cwd=str(tmp_path), timeout=10)
    # Не проверяем точное количество — просто факт truncate
    # (на Windows команда может по-другому)
    if r.ok:
        assert len(r.stdout.encode("utf-8")) <= 1_100_000
