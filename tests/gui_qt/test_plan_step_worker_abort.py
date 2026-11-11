"""C6a: PlanStepWorker — PIPELINE ABORTED → failed."""

import json

import pytest

from PIG_T3.gui_qt.workers.plan_step_worker import PlanStepWorker

pytestmark = pytest.mark.threading


class _FakeLLM:
    def __init__(self, response):
        self.response = response

    def ask(self, prompt):
        return self.response


def _step():
    return {
        "id": "s1",
        "title": "T",
        "description": "d",
        "completed": False,
        "status": "pending",
        "report": "",
    }


def test_pipeline_aborted_marks_failed(qtbot, managed_thread, tmp_path):
    """Если patcher вернул PIPELINE ABORTED — step=failed."""
    llm_response = json.dumps(
        [
            {"action": "run_command", "command": "false", "on_failure": "abort"},
        ]
    )
    settings = {
        "allow_command_execution": True,
        "command_whitelist": "false",
    }
    w = PlanStepWorker(
        step=_step(),
        plan_data=[_step()],
        root_folder=str(tmp_path),
        model_name="fake",
        settings=settings,
        llm_client=_FakeLLM(llm_response),
        context_builder=lambda _r, _c, _l: "",
        max_retries=0,
    )
    t = managed_thread()
    w.moveToThread(t)
    t.started.connect(w.run)
    errors = []
    w.error.connect(lambda step, msg: errors.append((step, msg)))
    with qtbot.waitSignal(w.error, timeout=5000):
        t.start()
    assert errors
    step, msg = errors[0]
    assert step["status"] == "failed"
    assert "abort" in msg.lower() or "команда" in msg.lower()
