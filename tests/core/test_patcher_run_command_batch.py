"""ADR-017: run_command batch (commands[]) + report_mode."""

from __future__ import annotations

import json

from PIG_T3.core.command_runner import CommandResult
from PIG_T3.core.patcher import apply_llm_changes


class _BatchRunner:
    def __init__(self, returncodes: list[int] | None = None):
        self.calls: list[str] = []
        self._runs = list(returncodes or [])

    def __call__(self, command, *, cwd, timeout, output_path):
        self.calls.append(command)
        code = self._runs.pop(0) if self._runs else 0
        return CommandResult(
            command=command,
            returncode=code,
            stdout="" if code else f"out: {command}",
            stderr="" if code == 0 else "boom",
            output_path=None,
        )


def _actions(*items) -> str:
    return json.dumps(list(items))


def test_batch_xor_error(tmp_path):
    log = apply_llm_changes(
        _actions(
            {
                "action": "run_command",
                "command": "echo a",
                "commands": ["echo b"],
            }
        ),
        str(tmp_path),
        allow_command_execution=True,
    )
    assert "не оба" in log or "XOR" in log


def test_batch_summary_success(tmp_path):
    runner = _BatchRunner([0, 0])
    log = apply_llm_changes(
        _actions(
            {
                "action": "run_command",
                "commands": ["pytest", "ruff"],
                "report_mode": "summary",
            }
        ),
        str(tmp_path),
        allow_command_execution=True,
        runner=runner,
    )
    assert "✅ RUN 2/2" in log
    assert runner.calls == ["pytest", "ruff"]


def test_batch_summary_fail(tmp_path):
    runner = _BatchRunner([0, 1])
    log = apply_llm_changes(
        _actions(
            {
                "action": "run_command",
                "commands": ["pytest", "ruff"],
                "report_mode": "summary",
            }
        ),
        str(tmp_path),
        allow_command_execution=True,
        runner=runner,
    )
    assert "❌ RUN 1/2" in log
    assert "[2] ruff" in log


def test_batch_abort_on_fail(tmp_path):
    runner = _BatchRunner([1, 0])
    log = apply_llm_changes(
        _actions(
            {
                "action": "run_command",
                "commands": ["false", "true"],
                "on_failure": "abort",
            }
        ),
        str(tmp_path),
        allow_command_execution=True,
        runner=runner,
    )
    assert "PIPELINE ABORTED" in log
    assert runner.calls == ["false"]


def test_batch_whitelist_per_command(tmp_path):
    log = apply_llm_changes(
        _actions(
            {
                "action": "run_command",
                "commands": ["echo ok", "rm -rf /"],
                "on_failure": "abort",
            }
        ),
        str(tmp_path),
        allow_command_execution=True,
        command_whitelist="echo",
    )
    assert "не входит в whitelist" in log or "rm" in log
    assert "PIPELINE ABORTED" in log


def test_batch_empty_commands(tmp_path):
    log = apply_llm_changes(
        _actions(
            {
                "action": "run_command",
                "commands": [],
            }
        ),
        str(tmp_path),
        allow_command_execution=True,
    )
    assert "пустая" in log.lower() or "empty" in log.lower()


def test_single_still_works(tmp_path):
    runner = _BatchRunner([0])
    log = apply_llm_changes(
        _actions(
            {
                "action": "run_command",
                "command": "echo hi",
            }
        ),
        str(tmp_path),
        allow_command_execution=True,
        runner=runner,
    )
    assert "✅ RUN" in log
    assert runner.calls == ["echo hi"]


def test_batch_opt_in_required(tmp_path):
    runner = _BatchRunner([0, 0])
    log = apply_llm_changes(
        _actions(
            {
                "action": "run_command",
                "commands": ["pytest"],
            }
        ),
        str(tmp_path),
        allow_command_execution=False,
        runner=runner,
    )
    assert "RUN заблокирован" in log
    assert runner.calls == []


def test_batch_summary_includes_index_middle(tmp_path):
    """ADR-017 P1: summary показывает [N] упавшей команды в batch из 3+"""
    runner = _BatchRunner([0, 1, 0])
    log = apply_llm_changes(
        _actions(
            {
                "action": "run_command",
                "commands": ["ok1", "fail1", "ok2"],
                "report_mode": "summary",
            }
        ),
        str(tmp_path),
        allow_command_execution=True,
        runner=runner,
    )
    assert "❌ RUN 2/3: [2] fail1" in log
