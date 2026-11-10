"""TDD: NewPlanDialog (T-405)."""

import pytest
from PySide6.QtWidgets import QDialog

from PIG_T3.gui_qt.dialogs import new_plan_dialog as npd_module
from PIG_T3.gui_qt.dialogs.new_plan_dialog import NewPlanDialog


@pytest.fixture(autouse=True)
def _silence(monkeypatch):
    monkeypatch.setattr(npd_module, "_show_warning", lambda *a, **kw: None)


def test_dialog_populates_models(qtbot):
    dlg = NewPlanDialog(["None", "BomjAPI", "Web: Gemini"])
    qtbot.addWidget(dlg)
    assert dlg.model_combo.count() == 3


def test_getters(qtbot):
    dlg = NewPlanDialog(["BomjAPI"])
    qtbot.addWidget(dlg)
    dlg.concept_edit.setPlainText("  some task  ")
    assert dlg.get_concept() == "some task"
    assert dlg.get_model() == "BomjAPI"


def test_create_empty_concept_stays_open(qtbot):
    dlg = NewPlanDialog(["BomjAPI"])
    qtbot.addWidget(dlg)
    dlg._on_create()
    assert dlg.result() != QDialog.DialogCode.Accepted


def test_create_none_model_stays_open(qtbot):
    dlg = NewPlanDialog(["None"])
    qtbot.addWidget(dlg)
    dlg.concept_edit.setPlainText("task")
    dlg._on_create()
    assert dlg.result() != QDialog.DialogCode.Accepted


def test_create_valid_accepts(qtbot):
    dlg = NewPlanDialog(["BomjAPI"])
    qtbot.addWidget(dlg)
    dlg.concept_edit.setPlainText("task")
    dlg._on_create()
    assert dlg.result() == QDialog.DialogCode.Accepted
