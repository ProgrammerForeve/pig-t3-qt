"""C8: agent_context — environment block для промпта."""

from __future__ import annotations

import os
import sys

from PIG_T3.core import agent_context as ac

# ---------- collect_environment ----------


def test_collect_returns_required_keys(tmp_path):
    env = ac.collect_environment(str(tmp_path))
    for key in (
        "os",
        "shell",
        "root_folder",
        "path_separator",
        "python_version",
        "git_available",
        "git_branch",
    ):
        assert key in env


def test_collect_root_folder_is_absolute(tmp_path):
    env = ac.collect_environment(str(tmp_path))
    assert os.path.isabs(env["root_folder"])


def test_collect_os_matches_current(tmp_path):
    env = ac.collect_environment(str(tmp_path))
    expected = "windows" if os.name == "nt" else "darwin" if sys.platform == "darwin" else "linux"
    assert env["os"] == expected


def test_collect_separator(tmp_path):
    env = ac.collect_environment(str(tmp_path))
    assert env["path_separator"] in ("\\", "/")


def test_collect_python_version_nonempty(tmp_path):
    env = ac.collect_environment(str(tmp_path))
    assert env["python_version"]
    assert "." in env["python_version"]


def test_collect_no_git_in_empty_tmp(tmp_path, monkeypatch):
    """Если git не видит .git — available=False, branch=None."""
    monkeypatch.setattr(
        ac.subprocess,
        "run",
        lambda *a, **kw: type("R", (), {"returncode": 1, "stdout": ""})(),
    )
    env = ac.collect_environment(str(tmp_path))
    assert env["git_available"] is False
    assert env["git_branch"] is None


def test_collect_git_available(monkeypatch, tmp_path):
    class _Ok:
        def __init__(self, out):
            self.returncode = 0
            self.stdout = out

    calls = {"n": 0}

    def _fake_run(cmd, **kw):
        calls["n"] += 1
        if calls["n"] == 1:
            return _Ok(str(tmp_path))
        return _Ok("main")

    monkeypatch.setattr(ac.subprocess, "run", _fake_run)
    env = ac.collect_environment(str(tmp_path))
    assert env["git_available"] is True
    assert env["git_branch"] == "main"


# ---------- format_environment_block ----------


def test_format_contains_header():
    block = ac.format_environment_block(ac.collect_environment("."))
    assert "[EXECUTION ENVIRONMENT]" in block


def test_format_contains_os():
    block = ac.format_environment_block(ac.collect_environment("."))
    assert "OS:" in block


def test_format_contains_run_command_rules():
    block = ac.format_environment_block(ac.collect_environment("."))
    assert "RULES FOR run_command:" in block
    assert "subprocess.run" in block


def test_format_windows_shell_rules():
    env = {
        "os": "windows",
        "shell": "cmd.exe",
        "root_folder": "C:\\p",
        "path_separator": "\\",
        "python_version": "3.10.0",
        "git_available": False,
        "git_branch": None,
    }
    block = ac.format_environment_block(env)
    assert "cmd.exe syntax" in block
    assert "Do NOT use bash-only" in block


def test_format_linux_shell_rules():
    env = {
        "os": "linux",
        "shell": "bash",
        "root_folder": "/p",
        "path_separator": "/",
        "python_version": "3.10.0",
        "git_available": False,
        "git_branch": None,
    }
    block = ac.format_environment_block(env)
    assert "POSIX shell" in block


def test_format_git_available():
    env = {
        "os": "linux",
        "shell": "bash",
        "root_folder": "/p",
        "path_separator": "/",
        "python_version": "3.10.0",
        "git_available": True,
        "git_branch": "main",
    }
    block = ac.format_environment_block(env)
    assert "branch: main" in block


def test_format_git_not_available():
    env = {
        "os": "linux",
        "shell": "bash",
        "root_folder": "/p",
        "path_separator": "/",
        "python_version": "3.10.0",
        "git_available": False,
        "git_branch": None,
    }
    block = ac.format_environment_block(env)
    assert "not available" in block
