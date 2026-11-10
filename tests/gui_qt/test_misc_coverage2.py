"""Day 6+: добить до 65% — simple methods с низкой ценой."""

import pytest

from PIG_T3.core.quality import FileMetrics
from PIG_T3.gui_qt.tabs.generator import GeneratorTab
from PIG_T3.gui_qt.tabs.plan import PlanTab

# ---------- GeneratorTab: browse / auto / options toggle / select-all click ----------


@pytest.fixture
def gen(qtbot, tmp_path):
    (tmp_path / "a.py").write_text("x")
    t = GeneratorTab(
        {
            "root_folder": str(tmp_path),
            "extensions": ".py",
            "ignore_list": "",
        }
    )
    qtbot.addWidget(t)
    return t


def test_browse_folder_sets_path(gen, monkeypatch):
    from PySide6.QtWidgets import QFileDialog

    monkeypatch.setattr(
        QFileDialog,
        "getExistingDirectory",
        staticmethod(lambda *a, **kw: "/picked"),
    )
    gen.browse_folder()
    assert gen.path_edit.text() == "/picked"


def test_browse_folder_cancel_keeps(gen, monkeypatch):
    from PySide6.QtWidgets import QFileDialog

    original = gen.path_edit.text()
    monkeypatch.setattr(
        QFileDialog,
        "getExistingDirectory",
        staticmethod(lambda *a, **kw: ""),
    )
    gen.browse_folder()
    assert gen.path_edit.text() == original


def test_auto_set_folder(gen):
    gen.auto_set_folder()
    # frozen → рядом с exe; иначе → корень репо
    assert gen.path_edit.text() != ""


def test_options_toggle_hide_show(gen):
    gen.options_toggle.setChecked(False)
    assert not gen.options_widget.isVisibleTo(gen)
    gen.options_toggle.setChecked(True)
    assert gen.options_widget.isVisibleTo(gen)


def test_select_all_clicked_toggles(gen):
    gen.cb_select_all.setChecked(True)
    gen._on_select_all_clicked(False)
    assert gen.tree_model.checked_files() == []


# ---------- EditorTab: paste / set_path / load_json / validate non-list ----------


@pytest.fixture
def editor(qtbot, tmp_path, monkeypatch):
    from PIG_T3.gui_qt.tabs import editor as editor_module

    monkeypatch.setattr(editor_module, "_show_info", lambda *a, **kw: None)
    monkeypatch.setattr(editor_module, "_show_error", lambda *a, **kw: None)
    monkeypatch.setattr(editor_module, "_show_yes_no", lambda *a, **kw: True)
    monkeypatch.setattr(editor_module.EditorTab, "_show_result_dialog", lambda self, log: None)
    monkeypatch.setattr(
        editor_module.EditorTab,
        "_populate_models",
        lambda self: self.model_combo.addItems(["None", "BomjAPI"]),
    )
    t = editor_module.EditorTab({"root_folder": str(tmp_path)})
    qtbot.addWidget(t)
    return t


def test_paste_from_clipboard(editor):
    from PySide6.QtWidgets import QApplication

    QApplication.clipboard().setText('[{"action":"delete","path":"x.py"}]')
    editor._on_paste()
    assert "delete" in editor.editor_text.toPlainText()
    assert "Вставлено" in editor.status_label.text()


def test_paste_empty_clipboard(editor):
    from PySide6.QtWidgets import QApplication

    QApplication.clipboard().clear()
    editor._on_paste()
    assert "пуст" in editor.status_label.text().lower()


def test_set_path(editor):
    editor.set_path("/new/path")
    assert editor.path_edit.text() == "/new/path"


def test_load_json_validates(editor):
    editor.load_json('[{"action":"delete","path":"z.py"}]')
    assert "Валидный" in editor.status_label.text()


def test_validate_non_list(editor):
    editor.editor_text.setPlainText('{"action":"delete"}')
    assert editor._on_validate() is False


def test_validate_empty(editor):
    editor.editor_text.clear()
    assert editor._on_validate() is False
    assert "Пустое" in editor.status_label.text()


# ---------- PlanTab: _get_mark / _on_rows_moved / set_path ----------


@pytest.fixture
def plan(qtbot, tmp_path, monkeypatch):
    from PIG_T3.gui_qt.tabs import plan as plan_module

    monkeypatch.setattr(plan_module, "_show_warning", lambda *a, **kw: None)
    monkeypatch.setattr(plan_module, "_show_error", lambda *a, **kw: None)
    monkeypatch.setattr(plan_module, "_show_yes_no", lambda *a, **kw: True)
    (tmp_path / ".pig").mkdir()
    t = PlanTab({"root_folder": str(tmp_path)})
    qtbot.addWidget(t)
    return t


def test_get_mark_variants():
    assert PlanTab._get_mark({"status": "in_progress"}) == "🔵"
    assert PlanTab._get_mark({"status": "failed"}) == "🔴"
    assert PlanTab._get_mark({"completed": True}) == "✅"
    assert PlanTab._get_mark({}) == "⬜"


def test_set_path_reloads(plan, tmp_path):
    import json as _json

    (tmp_path / ".pig" / "plan.json").write_text(_json.dumps([{"id": "s1", "title": "T", "description": "d"}]))
    plan.set_path(str(tmp_path))
    assert len(plan.plan_data) == 1


def test_on_rows_moved_reorders(plan):
    plan.plan_data = [
        {"id": "s1", "title": "A", "status": "pending", "completed": False},
        {"id": "s2", "title": "B", "status": "pending", "completed": False},
    ]
    plan._refresh_list()
    # swap в списке
    item = plan.plan_list.takeItem(0)
    plan.plan_list.addItem(item)
    plan._on_rows_moved()
    assert plan.plan_data[0]["id"] == "s2"


def test_on_new_plan_missing_path(qtbot, monkeypatch):
    from PIG_T3.gui_qt.tabs import plan as plan_module

    warns: list[str] = []
    monkeypatch.setattr(
        plan_module,
        "_show_warning",
        lambda p, t, txt: warns.append(txt),
    )
    t = PlanTab({"root_folder": ""})
    qtbot.addWidget(t)
    t._on_new_plan_clicked()
    assert warns


def test_on_delete_step_no_selection(plan):
    plan._current_index = -1
    plan._on_delete_step()  # noop, не падает


# ---------- QualityTab: _build_details_html без issues ----------


def test_build_details_no_issues(qtbot):
    from PIG_T3.gui_qt.tabs import quality as quality_module

    t = quality_module.QualityTab()
    qtbot.addWidget(t)
    m = FileMetrics(path="clean.py", complexity=2.0, maintainability=30.0, pylint_score=9.0, security_issues=0)
    html = t._build_details_html(m)
    assert "clean.py" in html
    assert "No issues" in html or "Great Job" in html


def test_update_stats_empty(qtbot):
    from PIG_T3.gui_qt.tabs import quality as quality_module

    t = quality_module.QualityTab()
    qtbot.addWidget(t)
    t._update_stats([])
    assert "не найдены" in t.status_label.text().lower()
