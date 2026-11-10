"""D2: Plan tab diff preview перед apply."""

import json

import pytest

from PIG_T3.gui_qt.tabs import plan as plan_module
from PIG_T3.gui_qt.tabs.plan import PlanTab
from PIG_T3.gui_qt.workers.plan_step_worker import (
    PlanStepWorker,
    apply_mark_to_step,
)


@pytest.fixture(autouse=True)
def _silence(monkeypatch):
    monkeypatch.setattr(plan_module, "_show_warning", lambda *a, **kw: None)
    monkeypatch.setattr(plan_module, "_show_error", lambda *a, **kw: None)
    monkeypatch.setattr(plan_module, "_show_yes_no", lambda *a, **kw: True)


def _step():
    return {
        "id": "s1",
        "title": "T",
        "description": "d",
        "completed": False,
        "status": "pending",
        "report": "",
    }


# ---------- apply_mark_to_step (free function) ----------


def test_apply_mark_sets_completed():
    step = _step()
    resp = '[{"action": "mark_step_completed", "step_id": "s1"}]'
    assert apply_mark_to_step(step, resp) is True
    assert step["completed"] is True


def test_apply_mark_missing_returns_false():
    step = _step()
    resp = '[{"action": "create", "path": "a.py", "content": "x"}]'
    assert apply_mark_to_step(step, resp) is False


# ---------- Worker capture mode ----------


class _FakeLLM:
    def __init__(self, response):
        self.response = response

    def ask(self, prompt):
        return self.response


def test_worker_capture_does_not_apply(qtbot, managed_thread, tmp_path):
    """capture_llm_text=True — worker НЕ пишет файл на диск."""
    from tests.helpers.threading import run_worker_and_wait

    response = '[{"action": "create", "path": "x.py", "content": "x=1\\n"}]'
    w = PlanStepWorker(
        step=_step(),
        plan_data=[_step()],
        root_folder=str(tmp_path),
        model_name="fake",
        settings={},
        llm_client=_FakeLLM(response),
        context_builder=lambda _root, _concept, _limit: "",
        capture_llm_text=True,
    )
    t = managed_thread()
    w.moveToThread(t)
    args = run_worker_and_wait(qtbot, w, t, done_signal=w.done)
    step, log = args
    assert log == "PREVIEW_PENDING"
    assert step["_pending_llm_text"] == response
    assert not (tmp_path / "x.py").exists()


def test_worker_apply_mode_writes_file(qtbot, managed_thread, tmp_path):
    """capture_llm_text=False — worker применяет (как раньше)."""
    from tests.helpers.threading import run_worker_and_wait

    response = '[{"action": "create", "path": "y.py", "content": "y=1\\n"}]'
    w = PlanStepWorker(
        step=_step(),
        plan_data=[_step()],
        root_folder=str(tmp_path),
        model_name="fake",
        settings={},
        llm_client=_FakeLLM(response),
        context_builder=lambda _root, _concept, _limit: "",
        capture_llm_text=False,
    )
    t = managed_thread()
    w.moveToThread(t)
    run_worker_and_wait(qtbot, w, t, done_signal=w.done)
    assert (tmp_path / "y.py").exists()


# ---------- PlanTab _apply_pending_with_diff ----------


@pytest.fixture
def tab(qtbot, tmp_path):
    (tmp_path / ".pig").mkdir()
    t = PlanTab({"root_folder": str(tmp_path)})
    qtbot.addWidget(t)
    return t


def test_apply_pending_shows_diff_and_applies(qtbot, tab, tmp_path, monkeypatch):
    """DiffDialog.Accepted → apply_llm_changes вызывается, файл создан."""
    from PySide6.QtWidgets import QDialog

    step = _step()
    llm_text = '[{"action": "create", "path": "z.py", "content": "z=1\\n"}]'
    monkeypatch.setattr(
        PlanTab,
        "_apply_pending_with_diff",
        PlanTab._apply_pending_with_diff,  # no-op, используем реальную
    )

    # Мокаем DiffDialog.exec
    def _fake_exec(self_dlg):
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(plan_module.DiffDialog, "exec", _fake_exec)

    result = tab._apply_pending_with_diff(step, llm_text)
    assert result is True
    assert (tmp_path / "z.py").exists()
    assert step["status"] == "pending"  # mark не было


def test_apply_pending_rejected_does_not_apply(qtbot, tab, tmp_path, monkeypatch):
    """DiffDialog.Rejected → файл НЕ создан, step остаётся pending."""
    from PySide6.QtWidgets import QDialog

    step = _step()
    llm_text = '[{"action": "create", "path": "nope.py", "content": "x\\n"}]'
    monkeypatch.setattr(
        plan_module.DiffDialog,
        "exec",
        lambda self_dlg: QDialog.DialogCode.Rejected,
    )

    result = tab._apply_pending_with_diff(step, llm_text)
    assert result is False
    assert not (tmp_path / "nope.py").exists()
    assert step["status"] == "pending"
    assert "отменено" in step["report"].lower()


def test_apply_pending_with_mark_completes(qtbot, tab, tmp_path, monkeypatch):
    """Accepted + mark_step_completed → step.completed=True."""
    from PySide6.QtWidgets import QDialog

    step = _step()
    llm_text = json.dumps(
        [
            {"action": "create", "path": "done.py", "content": "x\n"},
            {"action": "mark_step_completed", "step_id": "s1"},
        ]
    )
    monkeypatch.setattr(
        plan_module.DiffDialog,
        "exec",
        lambda self_dlg: QDialog.DialogCode.Accepted,
    )
    result = tab._apply_pending_with_diff(step, llm_text)
    assert result is True
    assert step["completed"] is True
    assert step["status"] == "completed"


def test_on_exec_done_with_pending_applies(qtbot, tab, tmp_path, monkeypatch):
    """_on_exec_done с _pending_llm_text → diff + apply + save."""
    from PySide6.QtWidgets import QDialog

    tab.plan_data = [_step()]
    tab._refresh_list()
    monkeypatch.setattr(
        plan_module.DiffDialog,
        "exec",
        lambda self_dlg: QDialog.DialogCode.Accepted,
    )
    step = dict(tab.plan_data[0])
    step["_pending_llm_text"] = json.dumps([{"action": "create", "path": "p.py", "content": "p=1\n"}])
    tab._on_exec_done(step, "PREVIEW_PENDING")
    assert (tmp_path / "p.py").exists()
    assert "_pending_llm_text" not in tab.plan_data[0]
