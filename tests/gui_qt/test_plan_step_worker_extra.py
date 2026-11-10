"""Day 4: plan_step_worker — retry path, _apply_mark_to_step edges.

Дополняет tests/gui_qt/test_plan_step_worker.py.
"""

from __future__ import annotations

import time

import pytest

from PIG_T3.gui_qt.workers.plan_step_worker import PlanStepWorker
from tests.helpers.threading import run_worker_and_wait

pytestmark = pytest.mark.threading


class _SequentialLLM:
    """Возвращает ответы по очереди; последний — на все оставшиеся вызовы.

    Принимает как одиночную строку (оборачивает в [str]), так и
    список строк. Без нормализации `list('[...]')` даёт список
    символов — невалидный JSON для тестов.
    """

    def __init__(self, responses):
        if isinstance(responses, str):
            responses = [responses]
        self.responses = list(responses)
        self.calls: list[str] = []

    def ask(self, prompt: str) -> str:
        self.calls.append(prompt)
        if len(self.responses) > 1:
            return self.responses.pop(0)
        return self.responses[0]


def _step(**overrides):
    base = {
        "id": "s1",
        "title": "Setup",
        "description": "create dirs",
        "completed": False,
        "report": "",
        "status": "pending",
    }
    base.update(overrides)
    return base


def _make_worker(llm, step=None, max_retries=2, apply_log="OK", context="ctx"):
    return PlanStepWorker(
        step=step or _step(),
        plan_data=[step or _step()],
        root_folder="/fake",
        model_name="fake",
        settings={},
        llm_client=llm,
        context_builder=lambda _root, _concept, _limit: context,
        apply_func=lambda llm_text, root: apply_log,
        max_retries=max_retries,
    )


# ---------- _apply_mark_to_step edge cases ----------


def test_mark_completed_false_overrides_default(qtbot, managed_thread):
    """Явное completed: false переопределяет default true."""
    llm = _SequentialLLM(['[{"action": "mark_step_completed", "step_id": "s1", "completed": false}]'])
    w = _make_worker(llm, step=_step(completed=True))
    t = managed_thread()
    w.moveToThread(t)
    args = run_worker_and_wait(qtbot, w, t, done_signal=w.done)
    step, _log = args
    assert step["completed"] is False


def test_mark_explanation_becomes_report(qtbot, managed_thread):
    llm = _SequentialLLM('[{"action": "mark_step_completed", "step_id": "s1", "explanation": "done well"}]')
    w = _make_worker(llm, step=_step(report=""))
    t = managed_thread()
    w.moveToThread(t)
    args = run_worker_and_wait(qtbot, w, t, done_signal=w.done)
    step, _log = args
    assert step["report"] == "done well"


def test_mark_append_description_to_empty(qtbot, managed_thread):
    llm = _SequentialLLM('[{"action": "mark_step_completed", "step_id": "s1", "append_description": "TODO: tests"}]')
    w = _make_worker(llm, step=_step(description=""))
    t = managed_thread()
    w.moveToThread(t)
    args = run_worker_and_wait(qtbot, w, t, done_signal=w.done)
    step, _log = args
    assert step["description"] == "TODO: tests"


def test_no_mark_action_keeps_pending(qtbot, managed_thread):
    llm = _SequentialLLM('[{"action": "create", "path": "a.py", "content": "x"}]')
    w = _make_worker(llm)
    t = managed_thread()
    w.moveToThread(t)
    args = run_worker_and_wait(qtbot, w, t, done_signal=w.done)
    step, _log = args
    assert step["status"] == "pending"
    assert step["completed"] is False


def test_apply_log_becomes_report_when_no_mark(qtbot, managed_thread):
    llm = _SequentialLLM('[{"action": "create", "path": "a.py", "content": "x"}]')
    w = _make_worker(llm, apply_log="✅ CREATE: a.py")
    t = managed_thread()
    w.moveToThread(t)
    args = run_worker_and_wait(qtbot, w, t, done_signal=w.done)
    step, _log = args
    assert "CREATE" in step["report"]


# ---------- retry with cancellable sleep ----------


def test_retry_cancel_during_sleep_emits_cancelled(qtbot, managed_thread):
    """Второй retry прерывается во время 1-сек сна — cancelled, не error."""
    llm = _SequentialLLM(["bad json"])  # всегда падает на парсинге
    w = _make_worker(llm, max_retries=2)
    t = managed_thread()
    w.moveToThread(t)
    t.started.connect(w.run)
    cancelled: list[bool] = []
    w.cancelled.connect(lambda: cancelled.append(True))
    with qtbot.waitSignal(w.cancelled, timeout=3000):
        t.start()
        # Дать первому attempt упасть (~200ms) и войти в sleep
        time.sleep(0.3)
        t.requestInterruption()
    assert cancelled


def test_retry_exhausted_with_multiple_attempts(qtbot, managed_thread):
    llm = _SequentialLLM(["bad", "still bad", "still bad"])
    w = _make_worker(llm, max_retries=1)
    t = managed_thread()
    w.moveToThread(t)
    t.started.connect(w.run)
    errors: list = []
    w.error.connect(lambda step, msg: errors.append(msg))
    with qtbot.waitSignal(w.error, timeout=6000):
        t.start()
    assert errors
    # 2 попытки → 2 вызова LLM
    assert len(llm.calls) == 2


# ---------- missing LLM without injection ----------


def test_no_llm_client_none_model_emits_error(qtbot, managed_thread):
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


# ---------- _build_context fallback ----------


def test_default_context_build_with_no_files(qtbot, managed_thread, tmp_path):
    """Без context_builder — пробует ContextOptimizer на пустой папке."""
    llm = _SequentialLLM('[{"action": "mark_step_completed", "step_id": "s1"}]')
    w = PlanStepWorker(
        step=_step(),
        plan_data=[_step()],
        root_folder=str(tmp_path),
        model_name="fake",
        settings={},
        llm_client=llm,
        context_builder=None,  # дефолтная реализация
        apply_func=lambda t, r: "ok",
        max_retries=0,
    )
    t = managed_thread()
    w.moveToThread(t)
    args = run_worker_and_wait(qtbot, w, t, done_signal=w.done, timeout=15000)
    step, _log = args
    assert step["status"] == "completed"


# ---------- progress sequence ----------


def test_progress_emits_stages(qtbot, managed_thread):
    llm = _SequentialLLM('[{"action": "mark_step_completed", "step_id": "s1"}]')
    w = _make_worker(llm)
    t = managed_thread()
    w.moveToThread(t)
    progress: list[int] = []
    w.progress.connect(lambda p, _m: progress.append(p))
    run_worker_and_wait(qtbot, w, t, done_signal=w.done)
    # Queued-сигналы из worker-потока доставляются в main-thread
    # асинхронно; waitSignal(done) возвращается раньше, чем
    # гарантированно доставлены все progress. Дождаться 100.
    qtbot.waitUntil(lambda: 100 in progress, timeout=2000)
    assert 10 in progress
    assert 30 in progress
    assert 60 in progress
    assert 80 in progress
    assert 100 in progress
