"""C6a: ApplyWorker прокидывает allow_command_execution в patcher."""

from __future__ import annotations

import json

import pytest

from PIG_T3.gui_qt.workers.apply_worker import ApplyWorker
from tests.helpers.threading import run_worker_and_wait

pytestmark = pytest.mark.threading


def test_apply_worker_optin_off(qtbot, managed_thread, tmp_path):
    patch = json.dumps(
        [
            {"action": "run_command", "command": "echo hi"},
        ]
    )
    w = ApplyWorker(
        patch,
        str(tmp_path),
        settings={"allow_command_execution": False},
    )
    t = managed_thread()
    w.moveToThread(t)
    args = run_worker_and_wait(qtbot, w, t, done_signal=w.done)
    log, _record = args
    assert "RUN заблокирован" in log


def test_apply_worker_optin_on(qtbot, managed_thread, tmp_path):
    patch = json.dumps(
        [
            {"action": "run_command", "command": "echo hi"},
        ]
    )
    w = ApplyWorker(
        patch,
        str(tmp_path),
        settings={
            "allow_command_execution": True,
            "command_whitelist": "echo",
        },
    )
    t = managed_thread()
    w.moveToThread(t)
    args = run_worker_and_wait(qtbot, w, t, done_signal=w.done)
    log, _record = args
    assert "✅ RUN:" in log
