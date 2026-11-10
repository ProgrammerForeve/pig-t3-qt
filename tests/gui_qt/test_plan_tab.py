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
