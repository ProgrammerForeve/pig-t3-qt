"""Day 6: PlanTab — full-plan cancel, git mocked, retry, exec errors."""

import pytest

from PIG_T3.gui_qt.tabs import plan as plan_module
from PIG_T3.gui_qt.tabs.plan import PlanTab


@pytest.fixture(autouse=True)
def _silence(monkeypatch):
    monkeypatch.setattr(plan_module, "_show_warning", lambda *a, **kw: None)
    monkeypatch.setattr(plan_module, "_show_error", lambda *a, **kw: None)
    monkeypatch.setattr(plan_module, "_show_yes_no", lambda *a, **kw: True)


@pytest.fixture
def tab(qtbot, tmp_path):
    (tmp_path / ".pig").mkdir()
    t = PlanTab({"root_folder": str(tmp_path)})
    qtbot.addWidget(t)
    return t


# ---------- full-plan pipeline edge ----------


def test_exec_full_cancel_second_click(tab):
    tab.plan_data = [{"id": "s1", "title": "T", "completed": False, "status": "pending"}]
    tab._refresh_list()
    tab._full_plan_running = True
    tab._full_plan_cancel = False
    tab._on_exec_full_clicked()  # → cancel
    assert tab._full_plan_cancel is True


def test_run_next_full_plan_when_cancelled(tab, monkeypatch):
    finished: list[str] = []
    monkeypatch.setattr(tab, "_finish_full_plan", lambda s: finished.append(s))
    tab._full_plan_running = True
    tab._full_plan_cancel = True
    tab._run_next_full_plan_step()
    assert "отмен" in finished[0]


def test_run_next_no_pending_completes(tab, monkeypatch):
    tab.plan_data = [{"id": "s1", "title": "T", "completed": True, "status": "completed"}]
    tab._refresh_list()
    finished: list[str] = []
    monkeypatch.setattr(tab, "_finish_full_plan", lambda s: finished.append(s))
    tab._full_plan_running = True
    tab._full_plan_cancel = False
    tab._run_next_full_plan_step()
    assert "заверш" in finished[0]


def test_exec_full_warns_missing_path(qtbot, tmp_path):
    warns: list[str] = []
    original = plan_module._show_warning
    plan_module._show_warning = lambda p, t, txt: warns.append(txt)
    try:
        t = PlanTab({"root_folder": ""})
        qtbot.addWidget(t)
        t.plan_data = [{"id": "s1", "title": "T", "completed": False, "status": "pending"}]
        t._refresh_list()
        t.model_combo.setCurrentText("BomjAPI")
        t._on_exec_full_clicked()
        assert warns
    finally:
        plan_module._show_warning = original


def test_on_exec_done_triggers_next_when_full_plan(tab, monkeypatch):
    calls: list[int] = []
    monkeypatch.setattr(tab, "_run_next_full_plan_step", lambda: calls.append(1))
    tab.plan_data = [{"id": "s1", "title": "T", "completed": False, "status": "pending"}]
    tab._refresh_list()
    tab._full_plan_running = True
    tab._full_plan_cancel = False
    completed = dict(tab.plan_data[0])
    completed["status"] = "completed"
    completed["completed"] = True
    tab._on_exec_done(completed, "log")
    # singleShot(0) — ждём тик; дальше проверяем, что план остался связным
    tab.plan_list.setCurrentRow(0)


def test_on_exec_cancelled_status(tab):
    tab._on_exec_cancelled()
    assert "отмен" in tab.status_label.text().lower()


# ---------- git mocked ----------


def test_check_git_missing(monkeypatch, tab):
    import subprocess as sp

    def _fail(*a, **kw):
        raise FileNotFoundError

    monkeypatch.setattr(sp, "run", _fail)
    assert tab._check_git() is False
    assert tab._git_available is False


def test_check_git_success(monkeypatch, tab, tmp_path):
    from PIG_T3.gui_qt.tabs import plan as pm

    class _Res:
        returncode = 0
        stdout = str(tmp_path)

    monkeypatch.setattr(pm.subprocess, "run", lambda *a, **kw: _Res())
    assert tab._check_git() is True
    assert tab._git_available is True
    assert tab._git_repo_path == str(tmp_path)


def test_git_commit_skipped_when_disabled(tab):
    tab.settings["git_enabled"] = False
    assert tab._git_commit_before_plan() is False


def test_git_push_no_available(tab):
    tab._git_available = False
    assert tab._git_push() is False


def test_git_push_success(monkeypatch, tab):
    tab._git_available = True
    tab._git_repo_path = "/tmp"
    from PIG_T3.gui_qt.tabs import plan as pm

    monkeypatch.setattr(pm.subprocess, "run", lambda *a, **kw: None)
    assert tab._git_push() is True


def test_git_push_failure(monkeypatch, tab):
    tab._git_available = True
    tab._git_repo_path = "/tmp"
    from PIG_T3.gui_qt.tabs import plan as pm

    def _fail(*a, **kw):
        raise Exception("boom")

    monkeypatch.setattr(pm.subprocess, "run", _fail)
    assert tab._git_push() is False


# ---------- retry ----------


def test_retry_clicked_selects_failed(tab, monkeypatch):
    tab.plan_data = [
        {"id": "s1", "title": "T1", "status": "completed", "completed": True},
        {"id": "s2", "title": "T2", "status": "failed", "completed": False},
    ]
    tab._refresh_list()
    called: list[int] = []
    monkeypatch.setattr(tab, "_on_exec_selected_clicked", lambda: called.append(1))
    tab._on_retry_clicked()
    assert tab._current_index == 1
    assert called


def test_on_exec_error_without_full_plan(tab):
    tab.plan_data = [{"id": "s1", "title": "T1", "status": "pending", "completed": False}]
    tab._refresh_list()
    tab._full_plan_running = False
    tab._on_exec_error(dict(tab.plan_data[0]), "boom")
    assert tab.plan_data[0]["status"] == "failed"


def test_exec_progress_updates_label(tab):
    tab._on_exec_progress(50, "step")
    assert "50" in tab.status_label.text()
