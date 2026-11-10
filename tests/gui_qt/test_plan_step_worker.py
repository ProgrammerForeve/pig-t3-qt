"""TDD: PlanStepWorker (T-406)."""

from __future__ import annotations

import time

import pytest

from PIG_T3.gui_qt.workers.plan_step_worker import PlanStepWorker
from tests.helpers.threading import run_worker_and_wait

pytestmark = pytest.mark.threading


class _FakeLLM:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls: list[str] = []

    def ask(self, prompt: str) -> str:
        self.calls.append(prompt)
        if len(self.responses) > 1:
            return self.responses.pop(0)
        return self.responses[0]


def _step():
    return {
        "id": "s1",
        "title": "Setup",
        "description": "create dirs",
        "completed": False,
        "report": "",
        "status": "pending",
    }


def _make_worker(llm, step=None, max_retries=2, apply_log="OK"):
    return PlanStepWorker(
        step=step or _step(),
        plan_data=[step or _step()],
        root_folder="/fake",
        model_name="fake",
        settings={},
        llm_client=llm,
        context_builder=lambda _root, _concept, _limit: "ctx",
        apply_func=lambda llm_text, root: apply_log,
        max_retries=max_retries,
    )


def test_successful_step_with_mark(qtbot, managed_thread):
    llm = _FakeLLM(['[{"action": "mark_step_completed", "step_id": "s1"}]'])
    w = _make_worker(llm)
    t = managed_thread()
    w.moveToThread(t)
    args = run_worker_and_wait(qtbot, w, t, done_signal=w.done)
    step, _log = args
    assert step["completed"] is True
    assert step["status"] == "completed"


def test_step_without_mark_stays_pending(qtbot, managed_thread):
    llm = _FakeLLM(['[{"action": "create", "path": "a.py", "content": "x=1\\n"}]'])
    w = _make_worker(llm)
    t = managed_thread()
    w.moveToThread(t)
    args = run_worker_and_wait(qtbot, w, t, done_signal=w.done)
    step, _log = args
    assert step["completed"] is False
    assert step["status"] == "pending"


def test_prompt_contains_step_and_plan(qtbot, managed_thread):
    llm = _FakeLLM(['[{"action": "mark_step_completed", "step_id": "s1"}]'])
    w = _make_worker(llm)
    t = managed_thread()
    w.moveToThread(t)
    run_worker_and_wait(qtbot, w, t, done_signal=w.done)
    assert llm.calls
    assert "Setup" in llm.calls[0]
    assert "create dirs" in llm.calls[0]
    assert "s1" in llm.calls[0]


def test_retry_on_invalid_json(qtbot, managed_thread):
    llm = _FakeLLM(
        [
            "not json",
            '[{"action": "mark_step_completed", "step_id": "s1"}]',
        ]
    )
    w = _make_worker(llm, max_retries=1)
    t = managed_thread()
    w.moveToThread(t)
    args = run_worker_and_wait(qtbot, w, t, done_signal=w.done)
    step, _log = args
    assert step["status"] == "completed"
    assert len(llm.calls) == 2


def test_retry_exhausted_emits_error(qtbot, managed_thread):
    llm = _FakeLLM(["not json"])
    w = _make_worker(llm, max_retries=1)
    t = managed_thread()
    w.moveToThread(t)
    t.started.connect(w.run)
    errors: list = []
    w.error.connect(lambda step, msg: errors.append((step, msg)))
    with qtbot.waitSignal(w.error, timeout=5000):
        t.start()
    assert errors


def test_missing_llm_emits_error(qtbot, managed_thread):
    w = PlanStepWorker(
        step=_step(),
        plan_data=[_step()],
        root_folder="/fake",
        model_name="None",
        settings={},
        llm_client=None,
        context_builder=lambda _root, _concept, _limit: "",
    )
    t = managed_thread()
    w.moveToThread(t)
    t.started.connect(w.run)
    errors: list = []
    w.error.connect(lambda step, msg: errors.append(msg))
    with qtbot.waitSignal(w.error, timeout=2000):
        t.start()
    assert errors
    assert "LLM" in errors[0]


def test_cancel_interrupts(qtbot, managed_thread):
    class _SlowLLM:
        def ask(self, prompt):
            time.sleep(0.5)
            return '[{"action": "mark_step_completed", "step_id": "s1"}]'

    w = _make_worker(_SlowLLM())
    t = managed_thread()
    w.moveToThread(t)
    t.started.connect(w.run)
    cancelled: list[bool] = []
    w.cancelled.connect(lambda: cancelled.append(True))
    with qtbot.waitSignal(w.cancelled, timeout=3000):
        t.start()
        time.sleep(0.05)
        t.requestInterruption()
    assert cancelled


def test_append_description_from_mark(qtbot, managed_thread):
    llm = _FakeLLM(['[{"action": "mark_step_completed", "step_id": "s1", "append_description": "TODO: tests"}]'])
    w = _make_worker(llm)
    t = managed_thread()
    w.moveToThread(t)
    args = run_worker_and_wait(qtbot, w, t, done_signal=w.done)
    step, _log = args
    assert "TODO: tests" in step["description"]
