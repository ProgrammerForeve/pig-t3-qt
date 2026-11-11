"""C6a: run_command в apply_llm_changes — opt-in, abort, whitelist."""

from __future__ import annotations

import json

from PIG_T3.core.command_runner import CommandResult
from PIG_T3.core.patcher import apply_llm_changes


def _actions(*items) -> str:
    return json.dumps(list(items))


def _cmd(command, **overrides):
    base = {"action": "run_command", "command": command}
    base.update(overrides)
    return base


class _RecordingRunner:
    def __init__(self, returncodes: list[int] | None = None):
        self.calls: list[tuple[str, dict]] = []
        self._runs = list(returncodes or [])
        self._default = 0

    def __call__(self, command, *, cwd, timeout, output_path):
        self.calls.append((command, {"cwd": cwd, "timeout": timeout, "output_path": output_path}))
        code = self._runs.pop(0) if self._runs else self._default
        return CommandResult(
            command=command,
            returncode=code,
            stdout="ok" if code == 0 else "",
            stderr="boom" if code != 0 else "",
            output_path=None,
        )


# ---------- opt-in gate ----------


def test_run_blocked_without_optin(tmp_path):
    runner = _RecordingRunner()
    log = apply_llm_changes(
        _actions(_cmd("echo hi")),
        str(tmp_path),
        runner=runner,
    )
    assert "RUN заблокирован" in log
    assert runner.calls == []


def test_run_allowed_with_optin(tmp_path):
    runner = _RecordingRunner()
    log = apply_llm_changes(
        _actions(_cmd("echo hi")),
        str(tmp_path),
        allow_command_execution=True,
        runner=runner,
    )
    assert "✅ RUN:" in log
    assert len(runner.calls) == 1
    assert runner.calls[0][0] == "echo hi"


def test_run_blocked_aborts_pipeline_if_on_failure_abort(tmp_path):
    runner = _RecordingRunner()
    log = apply_llm_changes(
        _actions(
            _cmd("echo hi", on_failure="abort"),
            {"action": "create", "path": "after.txt", "content": "x\n"},
        ),
        str(tmp_path),
        allow_command_execution=False,
        runner=runner,
    )
    assert "RUN заблокирован" in log
    assert "PIPELINE ABORTED" in log
    # create после abort не выполнен
    assert not (tmp_path / "after.txt").exists()


# ---------- failure / abort ----------


def test_run_failure_continue_does_not_abort(tmp_path):
    runner = _RecordingRunner(returncodes=[1, 0])
    log = apply_llm_changes(
        _actions(
            _cmd("false", on_failure="continue"),
            {"action": "create", "path": "after.txt", "content": "x\n"},
        ),
        str(tmp_path),
        allow_command_execution=True,
        runner=runner,
    )
    assert "❌ RUN:" in log
    assert "PIPELINE ABORTED" not in log
    assert (tmp_path / "after.txt").exists()


def test_run_failure_abort_stops_pipeline(tmp_path):
    runner = _RecordingRunner(returncodes=[1, 0])
    log = apply_llm_changes(
        _actions(
            _cmd("false", on_failure="abort"),
            {"action": "create", "path": "after.txt", "content": "x\n"},
        ),
        str(tmp_path),
        allow_command_execution=True,
        runner=runner,
    )
    assert "❌ RUN:" in log
    assert "PIPELINE ABORTED" in log
    assert not (tmp_path / "after.txt").exists()


def test_run_multiple_commands_order(tmp_path):
    runner = _RecordingRunner(returncodes=[0, 0, 0])
    apply_llm_changes(
        _actions(
            _cmd("first"),
            _cmd("second"),
            _cmd("third"),
        ),
        str(tmp_path),
        allow_command_execution=True,
        runner=runner,
    )
    assert [c[0] for c in runner.calls] == ["first", "second", "third"]


# ---------- passthrough params ----------


def test_run_passes_timeout_and_output_path(tmp_path):
    runner = _RecordingRunner()
    apply_llm_changes(
        _actions(
            _cmd(
                "echo hi",
                timeout_sec=42,
                output_path=".pig/cmd/a.log",
            )
        ),
        str(tmp_path),
        allow_command_execution=True,
        runner=runner,
    )
    _, kw = runner.calls[0]
    assert kw["timeout"] == 42
    assert kw["output_path"] == ".pig/cmd/a.log"


def test_run_empty_command_rejected(tmp_path):
    runner = _RecordingRunner()
    log = apply_llm_changes(
        _actions({"action": "run_command", "command": ""}),
        str(tmp_path),
        allow_command_execution=True,
        runner=runner,
    )
    assert "пустая команда" in log


# ---------- реальный subprocess через opt-in ----------


def test_run_real_echo_with_whitelist_ok(tmp_path):
    log = apply_llm_changes(
        _actions(_cmd("echo marker_123", on_failure="abort")),
        str(tmp_path),
        allow_command_execution=True,
        command_whitelist="echo",
    )
    assert "✅ RUN:" in log
    assert "PIPELINE ABORTED" not in log


def test_run_real_whitelist_rejects(tmp_path):
    log = apply_llm_changes(
        _actions(_cmd("rm -rf .", on_failure="abort")),
        str(tmp_path),
        allow_command_execution=True,
        command_whitelist="pytest",
    )
    assert "❌ run_command" in log or "не входит" in log
    assert "PIPELINE ABORTED" in log
