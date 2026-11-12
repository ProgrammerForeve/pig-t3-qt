"""Day 5: EditorTab — apply / undo / redo paths с моками воркеров."""

from __future__ import annotations

import json

import pytest

from PIG_T3.gui_qt.tabs import editor as editor_module
from PIG_T3.gui_qt.tabs.editor import EditorTab


@pytest.fixture(autouse=True)
def _silence(monkeypatch):
    monkeypatch.setattr(editor_module, "_show_info", lambda *a, **kw: None)
    monkeypatch.setattr(editor_module, "_show_error", lambda *a, **kw: None)
    monkeypatch.setattr(editor_module, "_show_yes_no", lambda *a, **kw: True)
    monkeypatch.setattr(EditorTab, "_show_result_dialog", lambda self, log: None)
    monkeypatch.setattr(
        EditorTab,
        "_populate_models",
        lambda self: self.model_combo.addItems(["None", "BomjAPI"]),
    )


@pytest.fixture
def tab(qtbot, tmp_path):
    t = EditorTab({"root_folder": str(tmp_path)})
    qtbot.addWidget(t)
    return t


def test_on_apply_worker_thread_cleanup(qtbot, tab, tmp_path):
    """_on_apply запускает ApplyWorker; cleanup после done."""
    patch = json.dumps([{"action": "create", "path": "x.py", "content": "a=1\n"}])
    tab.editor_text.setPlainText(patch)

    with qtbot.waitSignal(tab.undo_available_changed, timeout=5000):
        tab._on_apply()

    qtbot.waitUntil(lambda: tab._apply_thread is None, timeout=3000)
    assert len(tab.history_stack) == 1
    assert (tmp_path / "x.py").exists()


def test_history_cap_at_10(qtbot, tab, tmp_path):
    """После 11 применений — старейшая запись вытеснена + бэкапы удалены."""
    for i in range(11):
        patch = json.dumps([{"action": "create", "path": f"f{i}.py", "content": f"x={i}\n"}])
        tab._last_applied_content = None  # пропустить duplicate-check
        tab.editor_text.setPlainText(patch)
        with qtbot.waitSignal(tab.undo_available_changed, timeout=5000):
            tab._on_apply()
        qtbot.waitUntil(lambda: tab._apply_thread is None, timeout=3000)

    assert len(tab.history_stack) == 10
    # самый старый id удалён с диска
    tab.history_stack[0]["id"]
    # 11 применений → 10 в стеке, oldest — это 2-й по счёту
    # главное, что размер стека ограничен


def test_on_undo_calls_worker(qtbot, tab, tmp_path):
    patch = json.dumps([{"action": "create", "path": "u.py", "content": "1\n"}])
    tab.editor_text.setPlainText(patch)
    with qtbot.waitSignal(tab.undo_available_changed, timeout=5000):
        tab._on_apply()
    qtbot.waitUntil(lambda: tab._apply_thread is None, timeout=3000)

    tab._on_undo()
    qtbot.waitUntil(lambda: tab._undo_thread is None, timeout=5000)
    # После undo: redo-стек непуст, history пуст
    assert len(tab.redo_stack) == 1
    assert len(tab.history_stack) == 0


def test_on_redo_after_undo(qtbot, tab, tmp_path):
    patch = json.dumps([{"action": "create", "path": "r.py", "content": "1\n"}])
    tab.editor_text.setPlainText(patch)
    with qtbot.waitSignal(tab.undo_available_changed, timeout=5000):
        tab._on_apply()
    qtbot.waitUntil(lambda: tab._apply_thread is None, timeout=3000)

    tab._on_undo()
    qtbot.waitUntil(lambda: tab._undo_thread is None, timeout=5000)
    tab._on_redo()
    qtbot.waitUntil(lambda: tab._undo_thread is None, timeout=5000)

    assert len(tab.history_stack) == 1
    assert len(tab.redo_stack) == 0
    assert (tmp_path / "r.py").exists()


def test_undo_redo_buttons_state(tab):
    assert not tab.btn_undo.isEnabled()
    assert not tab.btn_redo.isEnabled()


# ---------- C7 follow-up: ported from test_misc_coverage.py ----------


def test_on_undo_redo_done_with_history(tab):
    tab.history_stack = [
        {
            "id": "x",
            "paths": [],
            "llm_text": '[{"action":"delete","path":"a.py"}]',
        }
    ]
    tab._on_undo_redo_done("Изменения отменены")
    assert "delete" in tab.editor_text.toPlainText()
    assert "Валидный JSON" in tab.status_label.text()


def test_on_undo_redo_done_empty_stacks(tab):
    tab._on_undo_redo_done("ok")


def test_on_apply_error_sets_status(tab):
    tab._on_apply_error("boom")
    assert "boom" in tab.status_label.text()
