"""ADR-016: read_lines UI в EditorTab._show_result_dialog.

Диагностические тесты: inspect.getsource показывает, что реально
вставлено в editor.py после patch-применения. Если падают — значит
insert_after_line / replace_text промахнулись.
"""

from __future__ import annotations

import inspect

import pytest

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


def test_methods_exist(tab):
    assert hasattr(tab, "_show_read_context_dialog"), (
        f"missing; attrs: {[a for a in dir(tab) if 'read' in a.lower() or 'context' in a.lower()]}"
    )
    assert hasattr(tab, "_copy_with_read_context"), (
        f"missing; attrs: {[a for a in dir(tab) if 'read' in a.lower() or 'context' in a.lower()]}"
    )


def test_read_requests_block_in_source():
    src = inspect.getsource(EditorTab._show_result_dialog)
    assert "if read_requests:" in src, (
        f"read_requests block missing в _show_result_dialog. Текущий source (tail 600): ...{src[-600:]}"
    )
    assert "Показать контекст" in src, f"btn_show_ctx missing. source tail: ...{src[-600:]}"
    assert "Копировать с контекстом" in src, f"btn_copy_ctx missing. source tail: ...{src[-600:]}"


def test_show_context_dialog_source():
    src = inspect.getsource(EditorTab._show_read_context_dialog)
    assert "dlg.exec()" in src
    assert "QDialog" in src


def test_copy_with_read_context_source():
    src = inspect.getsource(EditorTab._copy_with_read_context)
    assert "copy_text_to_clipboard" in src
    assert "llm_text" in src
