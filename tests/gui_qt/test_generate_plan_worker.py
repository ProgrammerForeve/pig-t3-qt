"""TDD: GeneratePlanWorker (T-405)."""

from __future__ import annotations

import pytest

from PIG_T3.gui_qt.workers.generate_plan_worker import GeneratePlanWorker
from tests.helpers.threading import run_worker_and_wait

pytestmark = pytest.mark.threading


class _FakeLLM:
    def __init__(self, response: str):
        self.response = response
        self.calls: list[str] = []

    def ask(self, prompt: str) -> str:
        self.calls.append(prompt)
        return self.response


def _make_worker(llm=None, response=None, context="ctx"):
    return GeneratePlanWorker(
        root_folder="/fake",
        concept="demo concept",
        model_name="fake",
        settings={},
        llm_client=llm or _FakeLLM(response or ""),
        context_builder=lambda _root, _concept, _limit: context,
    )


def _plan_json() -> str:
    return (
        '[{"id":"s1","title":"Setup","description":"create dirs"},'
        ' {"id":"s2","title":"Impl","description":"write code"}]'
    )


def test_successful_run_emits_plan(qtbot, managed_thread):
    w = _make_worker(response=_plan_json())
    t = managed_thread()
    w.moveToThread(t)
    args = run_worker_and_wait(qtbot, w, t, done_signal=w.done)
    plan = args[0]
    assert len(plan) == 2
    assert plan[0]["title"] == "Setup"
    assert plan[0]["completed"] is False
    assert plan[0]["status"] == "pending"


def test_prompt_contains_concept_and_context(qtbot, managed_thread):
    llm = _FakeLLM(_plan_json())
    w = _make_worker(llm=llm, context="UNIQUE_CONTEXT_MARKER")
    t = managed_thread()
    w.moveToThread(t)
    run_worker_and_wait(qtbot, w, t, done_signal=w.done)
    assert "demo concept" in llm.calls[0]
    assert "UNIQUE_CONTEXT_MARKER" in llm.calls[0]


def test_progress_signals(qtbot, managed_thread):
    w = _make_worker(response=_plan_json())
    t = managed_thread()
    w.moveToThread(t)
    progress: list = []
    w.progress.connect(lambda p, m: progress.append((p, m)))
    run_worker_and_wait(qtbot, w, t, done_signal=w.done)
    assert progress
    assert progress[-1][0] == 100


def test_error_on_invalid_json(qtbot, managed_thread):
    w = _make_worker(response="not json")
    t = managed_thread()
    w.moveToThread(t)
    t.started.connect(w.run)
    errors: list[str] = []
    w.error.connect(errors.append)
    with qtbot.waitSignal(w.error, timeout=2000):
        t.start()
    assert errors
    assert "Не удалось распарсить" in errors[0]


def test_error_on_llm_exception(qtbot, managed_thread):
    class _FailingLLM:
        def ask(self, prompt):
            raise RuntimeError("api down")

    w = _make_worker(llm=_FailingLLM())
    t = managed_thread()
    w.moveToThread(t)
    t.started.connect(w.run)
    errors: list[str] = []
    w.error.connect(errors.append)
    with qtbot.waitSignal(w.error, timeout=2000):
        t.start()
    assert errors and "api down" in errors[0]


def test_cancel_interrupts(qtbot, managed_thread):
    class _SlowLLM:
        def ask(self, prompt):
            import time

            time.sleep(0.5)
            return _plan_json()

    w = _make_worker(llm=_SlowLLM())
    t = managed_thread()
    w.moveToThread(t)
    t.started.connect(w.run)
    cancelled: list[bool] = []
    w.cancelled.connect(lambda: cancelled.append(True))
    with qtbot.waitSignal(w.cancelled, timeout=3000):
        t.start()
        import time

        time.sleep(0.05)
        t.requestInterruption()
    assert cancelled


def test_missing_llm_emits_error(qtbot, managed_thread):
    w = GeneratePlanWorker(
        root_folder="/fake",
        concept="c",
        model_name="None",
        settings={},
        llm_client=None,
        context_builder=lambda _root, _concept, _limit: "",
    )
    t = managed_thread()
    w.moveToThread(t)
    t.started.connect(w.run)
    errors: list[str] = []
    w.error.connect(errors.append)
    with qtbot.waitSignal(w.error, timeout=2000):
        t.start()
    assert errors
