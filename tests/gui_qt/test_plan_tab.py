"""TDD: PlanTab — каркас, load/save, debounce, DnD (T-401..T-404)."""

from __future__ import annotations

import json

import pytest

from PIG_T3.gui_qt.tabs import plan as plan_module
from PIG_T3.gui_qt.tabs.plan import PlanTab


@pytest.fixture(autouse=True)
def _silence(monkeypatch):
    monkeypatch.setattr(plan_module, "_show_warning", lambda *a, **kw: None)
    monkeypatch.setattr(plan_module, "_show_error", lambda *a, **kw: None)
    monkeypatch.setattr(plan_module, "_show_yes_no", lambda *a, **kw: True)
    monkeypatch.setattr(PlanTab, "_show_warning_stub", staticmethod(lambda *a, **kw: None))


@pytest.fixture
def pig_dir(tmp_path):
    (tmp_path / ".pig").mkdir()
    return tmp_path


@pytest.fixture
def sample_plan():
    return [
        {
            "id": "step_1",
            "title": "Setup",
            "description": "create folders",
            "completed": False,
            "report": "",
            "status": "pending",
        },
        {
            "id": "step_2",
            "title": "Implement",
            "description": "add code",
            "completed": True,
            "report": "done",
            "status": "completed",
        },
    ]


@pytest.fixture
def write_plan(pig_dir, sample_plan):
    path = pig_dir / ".pig" / "plan.json"
    path.write_text(json.dumps(sample_plan, ensure_ascii=False))
    return path


# ---------- Load ----------


def test_load_empty_when_no_file(qtbot, pig_dir):
    tab = PlanTab({"root_folder": str(pig_dir)})
    qtbot.addWidget(tab)
    tab.load_plan()
    assert tab.plan_data == []


def test_load_plan_from_disk(qtbot, write_plan, pig_dir):
    tab = PlanTab({"root_folder": str(pig_dir)})
    qtbot.addWidget(tab)
    tab.load_plan()
    assert len(tab.plan_data) == 2
    assert tab.plan_list.count() == 2
    assert tab.plan_list.item(0).text().startswith("⬜")
    assert tab.plan_list.item(1).text().startswith("✅")


def test_invalid_json_loads_empty(qtbot, pig_dir):
    (pig_dir / ".pig" / "plan.json").write_text("not json")
    tab = PlanTab({"root_folder": str(pig_dir)})
    qtbot.addWidget(tab)
    tab.load_plan()
    assert tab.plan_data == []


# ---------- Save ----------


def test_save_writes_file(qtbot, pig_dir, sample_plan):
    tab = PlanTab({"root_folder": str(pig_dir)})
    qtbot.addWidget(tab)
    tab.plan_data = list(sample_plan)
    tab.save_plan_silently()
    path = pig_dir / ".pig" / "plan.json"
    assert path.exists()
    written = json.loads(path.read_text())
    assert len(written) == 2
    assert written[0]["id"] == "step_1"


# ---------- Editor sync ----------


def test_select_step_populates_editor(qtbot, write_plan, pig_dir):
    tab = PlanTab({"root_folder": str(pig_dir)})
    qtbot.addWidget(tab)
    tab.load_plan()
    tab.plan_list.setCurrentRow(0)
    assert tab.title_edit.text() == "Setup"
    assert "create folders" in tab.desc_edit.toPlainText()


def test_edit_title_saves_after_debounce(qtbot, write_plan, pig_dir):
    tab = PlanTab({"root_folder": str(pig_dir)})
    qtbot.addWidget(tab)
    tab.load_plan()
    tab.plan_list.setCurrentRow(0)
    tab.title_edit.setText("Edited Title")
    # Ждём debounce (500ms) + запас
    qtbot.wait(1500)
    written = json.loads((pig_dir / ".pig" / "plan.json").read_text())
    assert written[0]["title"] == "Edited Title"


def test_checkbox_toggles_completed(qtbot, write_plan, pig_dir):
    tab = PlanTab({"root_folder": str(pig_dir)})
    qtbot.addWidget(tab)
    tab.load_plan()
    tab.plan_list.setCurrentRow(0)
    tab.cb_completed.setChecked(True)
    qtbot.wait(1500)
    written = json.loads((pig_dir / ".pig" / "plan.json").read_text())
    assert written[0]["completed"] is True


# ---------- Delete ----------


def test_delete_step_removes_and_saves(qtbot, write_plan, pig_dir):
    tab = PlanTab({"root_folder": str(pig_dir)})
    qtbot.addWidget(tab)
    tab.load_plan()
    tab.plan_list.setCurrentRow(0)
    tab._on_delete_step()
    assert len(tab.plan_data) == 1
    written = json.loads((pig_dir / ".pig" / "plan.json").read_text())
    assert len(written) == 1


# ---------- DnD (проверяем _on_rows_moved вручную) ----------


def test_rows_moved_reorders_plan(qtbot, write_plan, pig_dir):
    tab = PlanTab({"root_folder": str(pig_dir)})
    qtbot.addWidget(tab)
    tab.load_plan()
    # Имитируем перестановку: swap items в list, затем вызвать handler
    item0 = tab.plan_list.takeItem(0)
    tab.plan_list.addItem(item0)
    tab._on_rows_moved()
    # После DnD порядок должен измениться
    written = json.loads((pig_dir / ".pig" / "plan.json").read_text())
    assert written[0]["id"] == "step_2"
    assert written[1]["id"] == "step_1"


# ---------- Init ----------


def test_tab_widgets_exist(qtbot, pig_dir):
    tab = PlanTab({"root_folder": str(pig_dir)})
    qtbot.addWidget(tab)
    assert hasattr(tab, "plan_list")
    assert hasattr(tab, "title_edit")
    assert hasattr(tab, "btn_exec_selected")
    assert hasattr(tab, "btn_exec_full")
    assert hasattr(tab, "btn_retry")


def test_set_path_reloads(qtbot, write_plan, pig_dir):
    tab = PlanTab({"root_folder": ""})
    qtbot.addWidget(tab)
    tab.set_path(str(pig_dir))
    assert len(tab.plan_data) == 2


# ---------- T-405: генерация плана ----------


def test_new_plan_clicked_warns_without_path(qtbot, monkeypatch):
    from PIG_T3.gui_qt.tabs import plan as plan_module

    warns: list[str] = []
    monkeypatch.setattr(
        plan_module,
        "_show_warning",
        lambda parent, title, text: warns.append(text),
    )
    tab = PlanTab({"root_folder": ""})
    qtbot.addWidget(tab)
    tab._on_new_plan_clicked()
    assert warns


def test_on_gen_plan_done_updates_plan(qtbot, pig_dir):
    tab = PlanTab({"root_folder": str(pig_dir)})
    qtbot.addWidget(tab)
    new_plan = [
        {"id": "s1", "title": "T1", "description": "d1", "completed": False, "report": "", "status": "pending"},
    ]
    tab._on_gen_plan_done(new_plan)
    assert tab.plan_data == new_plan
    assert tab.plan_list.count() == 1


# ---------- T-406: выполнение шага ----------


def test_on_exec_done_updates_plan(qtbot, write_plan, pig_dir):
    tab = PlanTab({"root_folder": str(pig_dir)})
    qtbot.addWidget(tab)
    tab.load_plan()
    updated = dict(tab.plan_data[0])
    updated["status"] = "completed"
    updated["completed"] = True
    updated["report"] = "OK"
    tab._on_exec_done(updated, "log")
    written = json.loads((pig_dir / ".pig" / "plan.json").read_text())
    assert written[0]["status"] == "completed"
    assert written[0]["completed"] is True


def test_on_exec_error_marks_failed(qtbot, write_plan, pig_dir):
    tab = PlanTab({"root_folder": str(pig_dir)})
    qtbot.addWidget(tab)
    tab.load_plan()
    step = dict(tab.plan_data[0])
    tab._on_exec_error(step, "boom")
    written = json.loads((pig_dir / ".pig" / "plan.json").read_text())
    assert written[0]["status"] == "failed"
    assert "boom" in written[0]["report"]


def test_exec_selected_warns_without_model(qtbot, monkeypatch, write_plan, pig_dir):
    from PIG_T3.gui_qt.tabs import plan as plan_module

    warns: list[str] = []
    monkeypatch.setattr(
        plan_module,
        "_show_warning",
        lambda parent, title, text: warns.append(text),
    )
    tab = PlanTab({"root_folder": str(pig_dir)})
    qtbot.addWidget(tab)
    tab.load_plan()
    tab.plan_list.setCurrentRow(0)
    tab.model_combo.setCurrentText("None")
    tab._on_exec_selected_clicked()
    assert warns
    assert tab._exec_thread is None


def test_exec_selected_warns_without_path(qtbot, monkeypatch):
    from PIG_T3.gui_qt.tabs import plan as plan_module

    warns: list[str] = []
    monkeypatch.setattr(
        plan_module,
        "_show_warning",
        lambda parent, title, text: warns.append(text),
    )
    tab = PlanTab({"root_folder": ""})
    qtbot.addWidget(tab)
    tab.plan_data = [{"id": "s1", "title": "T", "description": "d"}]
    tab._refresh_list()
    tab.plan_list.setCurrentRow(0)
    tab.model_combo.setCurrentText("BomjAPI")
    tab._on_exec_selected_clicked()
    assert warns
    assert tab._exec_thread is None


# ---------- T-407: выполнение всего плана ----------


def test_exec_full_warns_on_empty_plan(qtbot, monkeypatch):
    from PIG_T3.gui_qt.tabs import plan as plan_module

    warns: list[str] = []
    monkeypatch.setattr(
        plan_module,
        "_show_warning",
        lambda parent, title, text: warns.append(text),
    )
    tab = PlanTab({"root_folder": ""})
    qtbot.addWidget(tab)
    tab._on_exec_full_clicked()
    assert warns
    assert not tab._full_plan_running


def test_exec_full_warns_all_completed(qtbot, monkeypatch):
    from PIG_T3.gui_qt.tabs import plan as plan_module

    warns: list[str] = []
    monkeypatch.setattr(
        plan_module,
        "_show_warning",
        lambda parent, title, text: warns.append(text),
    )
    tab = PlanTab({"root_folder": "/tmp"})
    qtbot.addWidget(tab)
    tab.plan_data = [
        {"id": "s1", "title": "T1", "completed": True, "status": "completed"},
    ]
    tab._refresh_list()
    tab._on_exec_full_clicked()
    assert warns
    assert not tab._full_plan_running


def test_exec_full_warns_without_model(qtbot, monkeypatch, tmp_path):
    from PIG_T3.gui_qt.tabs import plan as plan_module

    warns: list[str] = []
    monkeypatch.setattr(
        plan_module,
        "_show_warning",
        lambda parent, title, text: warns.append(text),
    )
    (tmp_path / ".pig").mkdir()
    tab = PlanTab({"root_folder": str(tmp_path)})
    qtbot.addWidget(tab)
    tab.plan_data = [
        {"id": "s1", "title": "T1", "completed": False, "status": "pending"},
    ]
    tab._refresh_list()
    tab.model_combo.setCurrentText("None")
    tab._on_exec_full_clicked()
    assert warns
    assert not tab._full_plan_running


def test_finish_full_plan_restores_ui(qtbot, tmp_path):
    (tmp_path / ".pig").mkdir()
    tab = PlanTab({"root_folder": str(tmp_path)})
    qtbot.addWidget(tab)
    tab._full_plan_running = True
    tab._full_plan_cancel = False
    tab.btn_exec_full.setText("⏹ ОСТАНОВИТЬ")
    tab.progress_global.setVisible(True)
    tab._finish_full_plan("завершён")
    assert not tab._full_plan_running
    assert not tab._full_plan_cancel
    assert "ВЫПОЛНИТЬ ВЕСЬ ПЛАН" in tab.btn_exec_full.text()
    assert not tab.progress_global.isVisible()


def test_run_next_picks_first_incomplete(qtbot, tmp_path, monkeypatch):
    (tmp_path / ".pig").mkdir()
    captured: list[dict] = []

    tab = PlanTab({"root_folder": str(tmp_path)})
    qtbot.addWidget(tab)
    tab.plan_data = [
        {"id": "s1", "title": "T1", "completed": True, "status": "completed"},
        {"id": "s2", "title": "T2", "completed": False, "status": "pending"},
        {"id": "s3", "title": "T3", "completed": False, "status": "pending"},
    ]
    tab._refresh_list()
    tab.model_combo.setCurrentText("BomjAPI")

    # Перехватываем _start_exec_step, чтобы не запускать реальный воркер
    def _fake_start(step, model_name):
        captured.append(step)

    monkeypatch.setattr(tab, "_start_exec_step", _fake_start)
    tab._full_plan_running = True
    tab._run_next_full_plan_step()
    assert captured
    assert captured[0]["id"] == "s2"


def test_on_exec_done_triggers_next_step(qtbot, tmp_path, monkeypatch):
    (tmp_path / ".pig").mkdir()
    tab = PlanTab({"root_folder": str(tmp_path)})
    qtbot.addWidget(tab)
    tab.plan_data = [
        {"id": "s1", "title": "T1", "completed": True, "status": "completed"},
        {"id": "s2", "title": "T2", "completed": False, "status": "pending"},
    ]
    tab._refresh_list()

    next_step_calls: list[int] = []
    monkeypatch.setattr(
        tab,
        "_run_next_full_plan_step",
        lambda: next_step_calls.append(1),
    )
    tab._full_plan_running = True
    tab._full_plan_cancel = False

    completed_step = dict(tab.plan_data[0])
    tab._on_exec_done(completed_step, "log")
    qtbot.wait(50)  # singleShot(0) — отработка
    assert next_step_calls


def test_on_exec_error_stops_full_plan(qtbot, tmp_path, monkeypatch):
    from PIG_T3.gui_qt.tabs import plan as plan_module

    monkeypatch.setattr(plan_module, "_show_error", lambda *a, **kw: None)
    (tmp_path / ".pig").mkdir()
    tab = PlanTab({"root_folder": str(tmp_path)})
    qtbot.addWidget(tab)
    tab.plan_data = [
        {"id": "s1", "title": "T1", "completed": False, "status": "pending"},
    ]
    tab._refresh_list()
    tab._full_plan_running = True

    step = dict(tab.plan_data[0])
    tab._on_exec_error(step, "boom")
    assert not tab._full_plan_running


def test_exec_full_cancel_flag(qtbot, tmp_path):
    (tmp_path / ".pig").mkdir()
    tab = PlanTab({"root_folder": str(tmp_path)})
    qtbot.addWidget(tab)
    tab.plan_data = [
        {"id": "s1", "title": "T1", "completed": False, "status": "pending"},
    ]
    tab._refresh_list()
    tab._full_plan_running = True
    tab._full_plan_cancel = False
    tab.btn_exec_full.setText("⏹ ОСТАНОВИТЬ ПОЛНЫЙ ПЛАН")
    tab._on_exec_full_clicked()  # повторный клик → отмена
    assert tab._full_plan_cancel is True


# ---------- T-408: retry ----------


def test_retry_selects_failed_step(qtbot, tmp_path, monkeypatch):
    (tmp_path / ".pig").mkdir()
    tab = PlanTab({"root_folder": str(tmp_path)})
    qtbot.addWidget(tab)
    tab.plan_data = [
        {"id": "s1", "title": "T1", "status": "completed", "completed": True},
        {"id": "s2", "title": "T2", "status": "failed", "completed": False},
    ]
    tab._refresh_list()

    captured: list[int] = []
    monkeypatch.setattr(tab, "_on_exec_selected_clicked", lambda: captured.append(1))
    tab._on_retry_clicked()
    assert captured
    assert tab._current_index == 1


def test_on_exec_error_selects_failed_step(qtbot, tmp_path, monkeypatch):
    from PIG_T3.gui_qt.tabs import plan as plan_module

    monkeypatch.setattr(plan_module, "_show_error", lambda *a, **kw: None)
    (tmp_path / ".pig").mkdir()
    tab = PlanTab({"root_folder": str(tmp_path)})
    qtbot.addWidget(tab)
    tab.plan_data = [
        {"id": "s1", "title": "T1", "status": "pending", "completed": False},
        {"id": "s2", "title": "T2", "status": "pending", "completed": False},
    ]
    tab._refresh_list()
    tab._full_plan_running = False
    tab._on_exec_error(dict(tab.plan_data[1]), "boom")
    assert tab._current_index == 1


# ---------- T-409: git ----------


def test_check_git_returns_false_when_git_missing(qtbot, tmp_path, monkeypatch):
    from PIG_T3.gui_qt.tabs import plan as plan_module

    def _fail(*a, **kw):
        raise FileNotFoundError("git not found")

    monkeypatch.setattr(plan_module.subprocess, "run", _fail)
    tab = PlanTab({"root_folder": str(tmp_path)})
    qtbot.addWidget(tab)
    assert tab._check_git() is False
    assert tab._git_available is False


def test_git_commit_skipped_when_disabled(qtbot, tmp_path):
    tab = PlanTab({"root_folder": str(tmp_path), "git_enabled": False})
    qtbot.addWidget(tab)
    tab._git_available = True
    tab._git_repo_path = str(tmp_path)
    assert tab._git_commit_before_plan() is False


def test_git_commit_skipped_when_not_available(qtbot, tmp_path):
    tab = PlanTab({"root_folder": str(tmp_path), "git_enabled": True})
    qtbot.addWidget(tab)
    tab._git_available = False
    assert tab._git_commit_before_plan() is False


def test_git_commit_calls_subprocess(qtbot, tmp_path, monkeypatch):
    from PIG_T3.gui_qt.tabs import plan as plan_module

    calls: list[tuple] = []

    class _Res:
        returncode = 0
        stdout = ""

    def _run(*args, **kw):
        calls.append(args)
        return _Res()

    monkeypatch.setattr(plan_module.subprocess, "run", _run)
    tab = PlanTab({"root_folder": str(tmp_path), "git_enabled": True})
    qtbot.addWidget(tab)
    tab._git_available = True
    tab._git_repo_path = str(tmp_path)
    assert tab._git_commit_before_plan() is True
    flat = " ".join(str(c) for c in calls)
    assert "add" in flat
    assert "commit" in flat


def test_on_exec_done_pushes_when_auto_push(qtbot, tmp_path, monkeypatch):
    (tmp_path / ".pig").mkdir()
    tab = PlanTab(
        {
            "root_folder": str(tmp_path),
            "git_auto_push": True,
        }
    )
    qtbot.addWidget(tab)
    tab.plan_data = [{"id": "s1", "title": "T", "completed": False, "status": "pending"}]
    tab._refresh_list()
    tab._git_available = True
    pushes: list[int] = []
    monkeypatch.setattr(tab, "_git_push", lambda: pushes.append(1) or True)
    tab._full_plan_running = False

    updated = dict(tab.plan_data[0])
    updated["status"] = "completed"
    tab._on_exec_done(updated, "log")
    assert pushes


def test_start_step_runs_git_when_enabled(qtbot, tmp_path, monkeypatch):
    """_start_exec_step вызывает _check_git + _git_commit_before_plan."""
    (tmp_path / ".pig").mkdir()
    tab = PlanTab(
        {
            "root_folder": str(tmp_path),
            "git_enabled": True,
        }
    )
    qtbot.addWidget(tab)
    tab.plan_data = [{"id": "s1", "title": "T", "completed": False, "status": "pending"}]
    tab._refresh_list()
    tab._current_index = 0

    calls: list[str] = []
    monkeypatch.setattr(tab, "_check_git", lambda: calls.append("check") or True)
    tab._git_available = True
    monkeypatch.setattr(tab, "_git_commit_before_plan", lambda: calls.append("commit") or True)

    # Мокаем воркер и поток, чтобы не запускать реальный QThread
    from PySide6.QtCore import QObject, QThread, Signal

    class _FakeWorker(QObject):
        progress = Signal(int, str)
        done = Signal(dict, str)
        error = Signal(dict, str)
        cancelled = Signal()

        def __init__(self, *a, **kw):
            super().__init__()

        def moveToThread(self, t):
            pass

        def run(self):
            pass

    from PIG_T3.gui_qt.tabs import plan as plan_module

    monkeypatch.setattr(plan_module, "PlanStepWorker", _FakeWorker)
    monkeypatch.setattr(QThread, "start", lambda self: None)

    tab._start_exec_step(tab.plan_data[0], "BomjAPI")
    assert "check" in calls
    assert "commit" in calls
