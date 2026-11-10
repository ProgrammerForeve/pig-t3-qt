"""TDD: EditorTab (T-302..T-306)."""

import json

import pytest

from PIG_T3.gui_qt.tabs import editor as editor_module
from PIG_T3.gui_qt.tabs.editor import EditorTab


@pytest.fixture(autouse=True)
def _silence(monkeypatch):
    monkeypatch.setattr(editor_module, "_show_info", lambda *a, **kw: None)
    monkeypatch.setattr(editor_module, "_show_error", lambda *a, **kw: None)
    monkeypatch.setattr(editor_module, "_show_yes_no", lambda *a, **kw: True)
    # Заглушка _show_result_dialog — иначе модальный exec() повесит прогон
    monkeypatch.setattr(EditorTab, "_show_result_dialog", lambda self, log: None)
    # Не дёргаем Ollama в списке моделей
    monkeypatch.setattr(EditorTab, "_populate_models", lambda self: self.model_combo.addItems(["None", "BomjAPI"]))


@pytest.fixture
def tab(qtbot, tmp_path):
    t = EditorTab({"root_folder": str(tmp_path)})
    qtbot.addWidget(t)
    return t


def test_paste_from_clipboard(tab, qtbot):
    from PySide6.QtWidgets import QApplication

    QApplication.clipboard().setText('[{"action": "delete", "path": "x.py"}]')
    tab._on_paste()
    assert "delete" in tab.editor_text.toPlainText()


def test_validate_ok(tab):
    tab.editor_text.setPlainText('[{"action": "delete", "path": "x.py"}]')
    assert tab._on_validate() is True
    assert "Валидный" in tab.status_label.text()


def test_validate_error(tab):
    tab.editor_text.setPlainText("not json")
    assert tab._on_validate() is False
    assert "Ошибка" in tab.status_label.text()


def test_validate_non_list(tab):
    tab.editor_text.setPlainText('{"action": "delete"}')
    assert tab._on_validate() is False


def test_apply_invalid_json_does_not_start(tab):
    tab.editor_text.setPlainText("bad")
    tab._on_apply()
    assert tab._apply_thread is None


def test_apply_success_updates_history(qtbot, tab, tmp_path):
    patch = json.dumps([{"action": "create", "path": "new.py", "content": "x=1\n"}])
    tab.editor_text.setPlainText(patch)
    with qtbot.waitSignal(tab.undo_available_changed, timeout=3000):
        tab._on_apply()
    assert len(tab.history_stack) == 1
    assert (tmp_path / "new.py").exists()


def test_undo_redo_buttons_initial_state(tab):
    assert not tab.btn_undo.isEnabled()
    assert not tab.btn_redo.isEnabled()


def test_set_path(tab, tmp_path):
    tab.set_path("/foo")
    assert tab.path_edit.text() == "/foo"


def test_load_json(tab):
    tab.load_json('[{"action": "delete", "path": "z.py"}]')
    assert "delete" in tab.editor_text.toPlainText()


# ---------- B1: diff preview ----------


def test_btn_preview_exists(tab):
    assert hasattr(tab, "btn_preview")
    assert "Просмотр" in tab.btn_preview.text()


def test_on_preview_shows_dialog(qtbot, tab, tmp_path, monkeypatch):
    """_on_preview вызывает compute_diffs + DiffDialog; Accepted → apply."""
    import json as _json

    from PySide6.QtWidgets import QDialog

    from PIG_T3.gui_qt.tabs import editor as editor_module

    patch = _json.dumps([{"action": "create", "path": "x.py", "content": "y=1\n"}])
    tab.editor_text.setPlainText(patch)

    # Мокаем compute_diffs — возвращает один FileDiff
    from PIG_T3.gui_qt.workers.diff_preview import FileDiff

    captured: list = []
    monkeypatch.setattr(
        editor_module,
        "compute_diffs",
        lambda text, path: [FileDiff(path="x.py", status="created", unified_diff="+y=1")],
    )

    # Мокаем DiffDialog.exec → Rejected (не применяем)
    def _fake_exec(self_dlg):
        captured.append(1)
        return QDialog.DialogCode.Rejected

    monkeypatch.setattr(editor_module.DiffDialog, "exec", _fake_exec)

    tab._on_preview()
    assert captured, "DiffDialog.exec не вызван"


def test_on_preview_no_diff_shows_info(tab, monkeypatch):
    from PIG_T3.gui_qt.tabs import editor as editor_module

    infos: list[str] = []
    monkeypatch.setattr(editor_module, "_show_info", lambda p, t, txt: infos.append(txt))
    monkeypatch.setattr(editor_module, "compute_diffs", lambda text, path: [])
    import json as _json

    tab.editor_text.setPlainText(_json.dumps([{"action": "create", "path": "x.py", "content": "y\n"}]))
    tab._on_preview()
    assert infos
    assert "нет" in infos[0].lower() or "пусто" in infos[0].lower()
