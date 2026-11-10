"""B2: PlanTab undo/redo — snapshots, cap, structural operations."""

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


def _step(sid, title):
    return {
        "id": sid,
        "title": title,
        "description": "d",
        "completed": False,
        "status": "pending",
    }


# ---------- Buttons initial state ----------


def test_undo_redo_buttons_disabled_initially(tab):
    assert not tab.btn_undo_plan.isEnabled()
    assert not tab.btn_redo_plan.isEnabled()


# ---------- Snapshot mechanics ----------


def test_snapshot_pushes_history(tab):
    tab.plan_data = [_step("s1", "A")]
    tab._snapshot()
    assert len(tab._history_stack) == 1
    assert tab.btn_undo_plan.isEnabled()


def test_snapshot_caps_at_10(tab):
    tab.plan_data = [_step("s1", "A")]
    for i in range(15):
        tab.plan_data = [_step(f"s{i}", f"T{i}")]
        tab._snapshot()
    assert len(tab._history_stack) == 10


def test_snapshot_clears_redo(tab):
    tab.plan_data = [_step("s1", "A")]
    tab._snapshot()
    tab.plan_data = [_step("s2", "B")]
    tab._on_undo_plan()
    assert len(tab._redo_stack) == 1
    tab._snapshot()
    assert len(tab._redo_stack) == 0


def test_snapshot_noop_when_unchanged(tab):
    tab.plan_data = [_step("s1", "A")]
    tab._snapshot()
    tab._snapshot()  # ничего не изменилось
    assert len(tab._history_stack) == 1


# ---------- Undo / Redo mechanics ----------


def test_undo_restores_previous(tab):
    tab.plan_data = [_step("s1", "A")]
    tab._snapshot()
    tab.plan_data = [_step("s2", "B")]
    tab._on_undo_plan()
    assert tab.plan_data[0]["id"] == "s1"


def test_redo_restores_undone(tab):
    tab.plan_data = [_step("s1", "A")]
    tab._snapshot()
    tab.plan_data = [_step("s2", "B")]
    tab._on_undo_plan()
    tab._on_redo_plan()
    assert tab.plan_data[0]["id"] == "s2"


def test_undo_empty_stack_noop(tab):
    tab._on_undo_plan()  # не падает


def test_redo_empty_stack_noop(tab):
    tab._on_redo_plan()  # не падает


# ---------- Integration with operations ----------


def test_delete_step_then_undo_restores(tab, tmp_path):
    tab.plan_data = [_step("s1", "A"), _step("s2", "B")]
    tab._refresh_list()
    tab.plan_list.setCurrentRow(0)
    tab._on_delete_step()
    assert len(tab.plan_data) == 1
    tab._on_undo_plan()
    assert len(tab.plan_data) == 2
    assert tab.plan_data[0]["id"] == "s1"


def test_reorder_then_undo_restores(tab):
    tab.plan_data = [_step("s1", "A"), _step("s2", "B")]
    tab._refresh_list()
    item = tab.plan_list.takeItem(0)
    tab.plan_list.addItem(item)
    tab._on_rows_moved()
    assert tab.plan_data[0]["id"] == "s2"
    tab._on_undo_plan()
    assert tab.plan_data[0]["id"] == "s1"


def test_exec_done_then_undo_restores(tab):
    tab.plan_data = [_step("s1", "A")]
    tab._refresh_list()
    completed = dict(tab.plan_data[0])
    completed["status"] = "completed"
    completed["completed"] = True
    tab._on_exec_done(completed, "log")
    assert tab.plan_data[0]["status"] == "completed"
    tab._on_undo_plan()
    assert tab.plan_data[0]["status"] == "pending"


def test_gen_plan_done_then_undo_restores(tab):
    tab.plan_data = [_step("old", "Old")]
    new_plan = [_step("new", "New")]
    tab._on_gen_plan_done(new_plan)
    assert tab.plan_data[0]["id"] == "new"
    tab._on_undo_plan()
    assert tab.plan_data[0]["id"] == "old"


# ---------- Deep copy — независимость ----------


def test_undo_uses_deep_copy(tab):
    tab.plan_data = [{"id": "s1", "title": "A", "nested": {"x": 1}}]
    tab._snapshot()
    tab.plan_data[0]["nested"]["x"] = 99
    tab.plan_data[0]["title"] = "CHANGED"
    tab._on_undo_plan()
    assert tab.plan_data[0]["nested"]["x"] == 1
    assert tab.plan_data[0]["title"] == "A"
