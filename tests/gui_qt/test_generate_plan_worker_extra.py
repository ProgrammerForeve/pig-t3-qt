"""Day 4: generate_plan_worker — _parse_plan edges, default context."""

from __future__ import annotations

import pytest

from PIG_T3.gui_qt.workers.generate_plan_worker import GeneratePlanWorker
from tests.helpers.threading import run_worker_and_wait

pytestmark = pytest.mark.threading


class _FakeLLM:
    def __init__(self, response):
        self.response = response
        self.calls: list[str] = []

    def ask(self, prompt: str) -> str:
        self.calls.append(prompt)
        return self.response


def _worker(llm, context="ctx"):
    return GeneratePlanWorker(
        root_folder="/fake",
        concept="demo",
        model_name="fake",
        settings={},
        llm_client=llm,
        context_builder=lambda _root, _concept, _limit: context,
    )


# ---------- _parse_plan edges ----------


def test_parse_plan_non_list_returns_empty_error(qtbot, managed_thread):
    w = _worker(_FakeLLM('{"not": "a list"}'))
    t = managed_thread()
    w.moveToThread(t)
    t.started.connect(w.run)
    errors: list[str] = []
    w.error.connect(errors.append)
    with qtbot.waitSignal(w.error, timeout=2000):
        t.start()
    assert errors


def test_parse_plan_drops_non_dict_items(qtbot, managed_thread):
    resp = '[{"id": "s1", "title": "T1", "description": "d"}, "not a dict"]'
    w = _worker(_FakeLLM(resp))
    t = managed_thread()
    w.moveToThread(t)
    args = run_worker_and_wait(qtbot, w, t, done_signal=w.done)
    plan = args[0]
    assert len(plan) == 1
    assert plan[0]["id"] == "s1"


def test_parse_plan_fills_missing_fields(qtbot, managed_thread):
    resp = '[{"title": "Auto"}, {}]'
    w = _worker(_FakeLLM(resp))
    t = managed_thread()
    w.moveToThread(t)
    args = run_worker_and_wait(qtbot, w, t, done_signal=w.done)
    plan = args[0]
    assert len(plan) == 2
    # Первый: id добавлен (step_1), description пустая
    assert plan[0]["id"] == "step_1"
    assert plan[0]["title"] == "Auto"
    assert plan[0]["description"] == ""
    assert plan[0]["completed"] is False
    assert plan[0]["status"] == "pending"
    # Второй: всё автозаполнено
    assert plan[1]["id"] == "step_2"
    assert plan[1]["title"] == ""


# ---------- default context build ----------


def test_default_context_build_returns_empty_for_empty_dir(qtbot, managed_thread, tmp_path):
    resp = '[{"id": "s1", "title": "T", "description": "d"}]'
    w = GeneratePlanWorker(
        root_folder=str(tmp_path),
        concept="demo",
        model_name="fake",
        settings={},
        llm_client=_FakeLLM(resp),
        context_builder=None,  # default: ContextOptimizer (empty → "")
    )
    t = managed_thread()
    w.moveToThread(t)
    args = run_worker_and_wait(qtbot, w, t, done_signal=w.done, timeout=15000)
    plan = args[0]
    assert len(plan) == 1


def test_prompt_contains_concept_and_context_markers(qtbot, managed_thread):
    resp = '[{"id": "s1", "title": "T", "description": "d"}]'
    llm = _FakeLLM(resp)
    w = _worker(llm, context="<file path='x.py'>CONTENT</file>")
    t = managed_thread()
    w.moveToThread(t)
    run_worker_and_wait(qtbot, w, t, done_signal=w.done)
    assert "demo" in llm.calls[0]
    assert "CONTENT" in llm.calls[0]


# ---------- error paths ----------


def test_empty_llm_response_emits_error(qtbot, managed_thread):
    w = _worker(_FakeLLM(""))
    t = managed_thread()
    w.moveToThread(t)
    t.started.connect(w.run)
    errors: list[str] = []
    w.error.connect(errors.append)
    with qtbot.waitSignal(w.error, timeout=2000):
        t.start()
    assert errors
