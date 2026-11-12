"""run_command — выполнение shell-команд из JSON-патча (C6a).

Позволяет AI запросить запуск команды и сохранение вывода в файл:

    {"action": "run_command", "command": "pytest tests/ -v",
     "output_path": ".pig/cmd/pytest.log",
     "timeout_sec": 120, "on_failure": "abort"}

Безопасность:
- opt-in через app_config (allow_command_execution, default false)
- обязательный timeout (1..3600 сек, default 120)
- output_path через Path.relative_to — не выйти за корень проекта
- truncate stdout/stderr до 1 MB
- опциональный whitelist по первой команде ('pytest,ruff,git')

Ограничение (документируется в ADR-012): shell=True, cwd=root_folder.
AI может написать 'bash -c "cd /; rm ..."' — opt-in это допускает.
Не запускайте с allow_command_execution=true на недоверенных проектах.
"""
from __future__ import annotations

import logging
import os
import re
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger("pig_t3.command_runner")


_MAX_OUTPUT_BYTES = 1_000_000
_DEFAULT_TIMEOUT = 120
_MAX_TIMEOUT = 3600


@dataclass
class CommandResult:
    command: str
    returncode: int
    stdout: str
    stderr: str
    output_path: str | None = None
    timed_out: bool = False
    truncated: bool = False

    @property
    def ok(self) -> bool:
        return self.returncode == 0 and not self.timed_out


class CommandWhitelistError(RuntimeError):
    """Команда не входит в разрешённый whitelist."""


def parse_whitelist(raw: str | list[str] | None) -> list[str]:
    if not raw:
        return []
    if isinstance(raw, list):
        return [str(x).strip() for x in raw if str(x).strip()]
    return [x.strip() for x in raw.split(",") if x.strip()]


# P0: shell-метасимволы, несовместимые с моделью «один whitelisted токен».
_DANGEROUS_SHELL = re.compile(r"[;&|<>`]|\$\(|\$\{")


def _is_whitelisted(
    command: str,
    whitelist: list[str],
    allow_shell_operators: bool = False,
) -> bool:
    if not whitelist:
        return True
    stripped = command.strip()
    if not stripped:
        return False
    # P0 (TASKS.md): при непустом whitelist запрещаем составные команды.
    # P2 (TASKS.md): allow_shell_operators=True возвращает legacy-поведение
    # (проверяем только первый токен) — для случаев, когда пользователь
    # осознанно хочет `pytest ... | tail` или `git add -A && git commit`.
    if not allow_shell_operators and _DANGEROUS_SHELL.search(stripped):
        return False
    try:
        tokens = shlex.split(stripped)
    except ValueError:
        return False
    if not tokens:
        return False
    return tokens[0] in whitelist


def _truncate(text: str, limit: int = _MAX_OUTPUT_BYTES) -> tuple[str, bool]:
    encoded = text.encode("utf-8", errors="replace")
    if len(encoded) <= limit:
        return text, False
    return encoded[:limit].decode("utf-8", errors="ignore"), True


def _safe_output_path(output_path: str, root: str) -> Path | None:
    if not output_path:
        return None
    root_abs = Path(root).resolve()
    try:
        candidate = (root_abs / output_path).resolve()
        candidate.relative_to(root_abs)
    except (OSError, ValueError):
        return None
    if candidate == root_abs:
        return None
    return candidate


def _write_output(
    target: Path, command: str, result: CommandResult
) -> str | None:
    """Записать лог в target. Возвращает rel_path для result.output_path."""
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "w", encoding="utf-8") as f:
            f.write(f"$ {command}\n")
            f.write(f"exit_code: {result.returncode}\n")
            if result.timed_out:
                f.write("timed_out: yes\n")
            if result.truncated:
                f.write("truncated: yes\n")
            f.write("=" * 80 + "\n")
            f.write("STDOUT:\n")
            f.write(result.stdout)
            if result.stderr:
                f.write("\n" + "=" * 80 + "\n")
                f.write("STDERR:\n")
                f.write(result.stderr)
        return str(target)
    except OSError as e:
        log.warning("output write failed: %s", e)
        return None


def run_command(
    command: str,
    *,
    cwd: str,
    timeout: int = _DEFAULT_TIMEOUT,
    output_path: str | None = None,
    whitelist: list[str] | None = None,
    allow_shell_operators: bool = False,
) -> CommandResult:
    """Выполнить shell-команду в cwd. Никогда не бросает — возвращает
    CommandResult с returncode=-1 при ошибках спавна/таймауте."""
    if not command or not command.strip():
        return CommandResult(
            command=command or "",
            returncode=-1,
            stdout="",
            stderr="empty command",
        )

    if whitelist and not _is_whitelisted(
        command, whitelist, allow_shell_operators=allow_shell_operators
    ):
        raise CommandWhitelistError(
            f"Команда {command!r} не входит в whitelist {whitelist}"
        )

    try:
        timeout = max(1, min(int(timeout or _DEFAULT_TIMEOUT), _MAX_TIMEOUT))
    except (TypeError, ValueError):
        timeout = _DEFAULT_TIMEOUT

    log.debug("run_command: %r cwd=%s timeout=%ds", command, cwd, timeout)

    try:
        proc = subprocess.run(
            command,
            shell=True,
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            env=os.environ.copy(),
        )
    except subprocess.TimeoutExpired as e:
        stdout = (e.stdout or "")
        stderr = (e.stderr or "")
        if isinstance(stdout, bytes):
            stdout = stdout.decode("utf-8", "replace")
        if isinstance(stderr, bytes):
            stderr = stderr.decode("utf-8", "replace")
        stdout, t1 = _truncate(stdout)
        stderr, t2 = _truncate(
            (stderr + "\n" if stderr else "") + f"timed out after {timeout}s"
        )
        result = CommandResult(
            command=command,
            returncode=-1,
            stdout=stdout,
            stderr=stderr,
            timed_out=True,
            truncated=t1 or t2,
        )
    except Exception as e:  # noqa: BLE001
        return CommandResult(
            command=command,
            returncode=-1,
            stdout="",
            stderr=f"failed to spawn: {e}",
        )
    else:
        stdout, t1 = _truncate(proc.stdout or "")
        stderr, t2 = _truncate(proc.stderr or "")
        result = CommandResult(
            command=command,
            returncode=proc.returncode,
            stdout=stdout,
            stderr=stderr,
            truncated=t1 or t2,
        )

    if output_path:
        target = _safe_output_path(output_path, cwd)
        if target is None:
            result.stderr += (
                f"\n⚠️ output_path вне проекта: {output_path}"
            )
        else:
            written = _write_output(target, command, result)
            if written is None:
                result.stderr += (
                    f"\n⚠️ не удалось записать output: {output_path}"
                )
            else:
                try:
                    result.output_path = str(
                        Path(written).relative_to(Path(cwd).resolve())
                    ).replace("\\", "/")
                except ValueError:
                    result.output_path = written

    return result
