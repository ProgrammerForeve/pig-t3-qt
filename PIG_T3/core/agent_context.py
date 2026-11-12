"""Сбор метаданных окружения для промпта агента (C8).

Возвращает dict / текстовый блок с:
- OS (linux/windows/darwin)
- Shell (cmd.exe / bash / zsh)
- Project root (абсолютный путь)
- Path separator (\\ или /)
- Python version
- Git available + branch

Используется в системных промптах:
- analyzer._write_patching_instructions (файл-контекст)
- plan_step_worker._build_prompt (выполнение шага)
- generate_plan_worker._PLAN_PROMPT_TEMPLATE (генерация плана)

Метаданные позволяют LLM:
- не предлагать bash-синтаксис на Windows (и наоборот)
- знать cwd для run_command (root_folder)
- учитывать наличие git
"""
from __future__ import annotations

import os
import platform
import subprocess
import sys
from pathlib import Path


def _detect_shell() -> str:
    """Shell, который использует subprocess.run(shell=True).

    - Windows: cmd.exe (shell=True = %COMSPEC%, обычно cmd.exe)
    - POSIX: basename $SHELL или "sh"
    """
    if os.name == "nt":
        return "cmd.exe"
    shell = os.environ.get("SHELL", "/bin/sh")
    return Path(shell).name or "sh"


def _detect_git(root_folder: str) -> dict:
    """Проверить git и текущую ветку. Никогда не бросает."""
    result = {"available": False, "branch": None}
    try:
        r = subprocess.run(
            ["git", "-C", root_folder, "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=3,
        )
        if r.returncode != 0:
            return result
        result["available"] = True
        b = subprocess.run(
            ["git", "-C", root_folder, "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            timeout=3,
        )
        if b.returncode == 0 and b.stdout.strip():
            result["branch"] = b.stdout.strip()
    except (OSError, subprocess.SubprocessError, FileNotFoundError):
        pass
    return result


def collect_environment(root_folder: str) -> dict:
    """Собрать метаданные. Возвращает dict с фиксированными ключами."""
    root = os.path.abspath(root_folder)
    git = _detect_git(root)
    if os.name == "nt":
        os_name = "windows"
    elif sys.platform == "darwin":
        os_name = "darwin"
    else:
        os_name = "linux"
    return {
        "os": os_name,
        "shell": _detect_shell(),
        "root_folder": root,
        "path_separator": "\\" if os.name == "nt" else "/",
        "python_version": platform.python_version(),
        "git_available": git["available"],
        "git_branch": git["branch"],
    }


def format_environment_block(env: dict) -> str:
    """Форматирует env в текстовый блок для промпта."""
    os_name = env.get("os", "linux")
    shell = env.get("shell", "sh")
    sep = env.get("path_separator", "/")
    root = env.get("root_folder", "")
    py = env.get("python_version", "?")

    if env.get("git_available"):
        git_line = (
            f"- Git: available (branch: {env.get('git_branch') or '?'})"
        )
    else:
        git_line = "- Git: not available in this folder"

    if os_name == "windows":
        shell_rules = (
            "- Use Windows-compatible commands (cmd.exe syntax).\n"
            "- Do NOT use bash-only syntax: $VAR, ~, /tmp, chmod, sudo,\n"
            "  apt, ./script.sh, single-quoted paths with spaces.\n"
            "- Multi-step: use 'cmd /c \"...\"' or chain with '&&'\n"
            "  (works in cmd.exe).\n"
            "- Quote paths with spaces: \"C:\\\\path with space\\\\file.py\".\n"
            "- Prefer 'python -m pytest ...', 'python -m ruff check ...'\n"
            "  instead of bare 'pytest' / 'ruff' (PATH may not have them).\n"
            "- Line endings: CRLF. Shell is case-insensitive."
        )
    else:
        shell_rules = (
            "- POSIX shell (bash/zsh) syntax is available.\n"
            "- '&&', '|', '$VAR', '~', '$(...)' are fine.\n"
            "- Quote paths with spaces: \"path with spaces/file.py\".\n"
            "- 'python -m pytest ...' is fine; direct 'pytest' works if\n"
            "  it's on PATH.\n"
            "- Line endings: LF. Shell is case-sensitive."
        )

    return (
        "[EXECUTION ENVIRONMENT]\n"
        f"- OS: {os_name}\n"
        f"- Shell (used for run_command): {shell}\n"
        f"- Project root: {root}\n"
        "- run_command executes with cwd = project root\n"
        f"- Path separator: '{sep}'\n"
        f"- Python: {py}\n"
        f"{git_line}\n"
        "\n"
        "RULES FOR run_command:\n"
        f"{shell_rules}\n"
        "- Commands are executed as subprocess.run(shell=True, "
        "cwd=<project root>).\n"
        "- Output: stdout + stderr captured, truncated to 1 MB.\n"
        "- timeout_sec: 1..3600, default 120.\n"
        "- output_path (optional): relative to project root, no '..'.\n"
        "  Example: .pig/cmd/test.log\n"
        "- on_failure: 'continue' (default) or 'abort' (stops the whole\n"
        "  action array on non-zero exit code).\n"
        "- Use run_command ONLY for validation / inspection: pytest,\n"
        "  ruff, mypy, pylint, bandit, git status, git diff, smoke runs.\n"
        "- Do NOT use run_command for destructive operations (rm -rf,\n"
        "  git reset --hard, git push --force, DROP TABLE, chmod 777)\n"
        "  unless the user explicitly asked in the task description.\n"
        "- For file changes use 'create' / 'edit' / 'move' / 'delete'.\n"
        "  run_command is not a substitute for those.\n"
        "- Split long scripts into multiple run_command actions; each\n"
        "  one should be short and focused.\n"
    )