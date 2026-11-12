"""Tests for EditorTab._show_result_dialog buttons."""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QDialog, QPushButton

from PIG_T3.gui_qt.tabs import editor as editor_module
from PIG_T3.gui_qt.tabs.editor import EditorTab


@pytest.fixture(autouse=True)
def _silence(monkeypatch):
    monkeypatch.setattr(editor_module, "_show_info", lambda *a, **kw: None)
    monkeypatch.setattr(editor_module, "_show_error", lambda *a, **kw: None)
    monkeypatch.setattr(editor_module, "_show_yes_no", lambda *a, **kw: True)
    monkeypatch.setattr(EditorTab, "_populate_models", lambda self: None)


@pytest.fixture
def tab(qtbot, tmp_path):
    t = EditorTab({"root_folder": str(tmp_path)})
    qtbot.addWidget(t)
    return t


def _capture_buttons(monkeypatch):
    captured = {}

    def fake_exec(self_dlg):
        captured["buttons"] = [b.text() for b in self_dlg.findChildren(QPushButton)]
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(QDialog, "exec", fake_exec)
    return captured


def test_result_dialog_has_copy_button(tab, monkeypatch):
    captured = _capture_buttons(monkeypatch)
    tab._show_result_dialog("just a log")
    texts = captured.get("buttons", [])
    assert any("Копировать" in t and "всё" not in t for t in texts)
    assert any("Закрыть" in t for t in texts)


def test_result_dialog_no_copy_all_when_no_output(tab, monkeypatch):
    captured = _capture_buttons(monkeypatch)
    tab._show_result_dialog("just a log, no output paths")
    texts = captured.get("buttons", [])
    assert not any("Копировать всё" in t for t in texts)
    assert not any("Открыть" in t for t in texts)


def test_result_dialog_has_copy_all_with_output(tab, monkeypatch):
    captured = _capture_buttons(monkeypatch)
    log = "✅ RUN: pytest (exit=0)\n   📄 output: .pig/cmd/test.log"
    tab._show_result_dialog(log)
    texts = captured.get("buttons", [])
    assert any("Копировать всё" in t for t in texts)
    assert any("Открыть" in t for t in texts)


def test_result_dialog_has_save_button(tab, monkeypatch):
    captured = _capture_buttons(monkeypatch)
    tab._show_result_dialog("log text")
    texts = captured.get("buttons", [])
    assert any("Сохранить" in t for t in texts)
