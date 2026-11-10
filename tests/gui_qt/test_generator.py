"""TDD: каркас вкладки «Генератор» (T-101)."""

import pytest

from PIG_T3.gui_qt.tabs.generator import GeneratorTab


@pytest.fixture
def settings(tmp_path):
    return {
        "root_folder": str(tmp_path / "project"),
        "extensions": ".py, .txt",
        "ignore_list": "venv, .git",
        "output_name": "context",
    }


def test_instantiation_reads_settings(settings, qtbot):
    tab = GeneratorTab(settings)
    qtbot.addWidget(tab)
    assert tab.path_edit.text() == settings["root_folder"]
    assert tab.ext_edit.text() == ".py, .txt"
    assert tab.ignore_edit.text() == "venv, .git"
    assert tab.output_edit.text() == "context"


def test_collect_settings_returns_current_values(settings, qtbot):
    tab = GeneratorTab(settings)
    qtbot.addWidget(tab)
    tab.path_edit.setText("/new/path")
    tab.ext_edit.setText(".rs")
    tab.ignore_edit.setText("target")
    tab.output_edit.setText("out")
    result = tab.collect_settings()

    # Text fields must match exactly; extra keys (checkbox options) are
    # covered by dedicated tests in T-102.
    expected_text_fields = {
        "root_folder": "/new/path",
        "extensions": ".rs",
        "ignore_list": "target",
        "output_name": "out",
    }
    for key, value in expected_text_fields.items():
        assert result[key] == value, f"{key}: {result[key]!r} != {value!r}"


@pytest.mark.parametrize("field", ["path_edit", "ext_edit", "ignore_edit", "output_edit"])
def test_settings_changed_emitted_on_edit(settings, qtbot, field):
    tab = GeneratorTab(settings)
    qtbot.addWidget(tab)
    getattr(tab, field).setText("")
    with qtbot.waitSignal(tab.settings_changed, timeout=500):
        getattr(tab, field).setText("changed")


def test_missing_keys_use_empty_defaults(qtbot):
    tab = GeneratorTab({})
    qtbot.addWidget(tab)
    assert tab.path_edit.text() == ""
    assert tab.ext_edit.text() == ""
    assert tab.ignore_edit.text() == ""
    assert tab.output_edit.text() == ""


def test_browse_folder_sets_path(settings, qtbot, monkeypatch):
    tab = GeneratorTab(settings)
    qtbot.addWidget(tab)
    from PySide6.QtWidgets import QFileDialog

    monkeypatch.setattr(
        QFileDialog,
        "getExistingDirectory",
        staticmethod(lambda *a, **kw: "/picked/dir"),
    )
    tab.browse_folder()
    assert tab.path_edit.text() == "/picked/dir"


def test_browse_folder_cancel_keeps_path(settings, qtbot, monkeypatch):
    tab = GeneratorTab(settings)
    qtbot.addWidget(tab)
    from PySide6.QtWidgets import QFileDialog

    monkeypatch.setattr(
        QFileDialog,
        "getExistingDirectory",
        staticmethod(lambda *a, **kw: ""),
    )
    tab.browse_folder()
    assert tab.path_edit.text() == settings["root_folder"]


# ---------- T-102: опции генерации ----------


def test_checkboxes_initialized_from_settings(qtbot):
    settings = {
        "include_empty_folders": True,
        "add_edit_prompt": True,
        "include_plan": False,
        "line_numbers": True,
        "auto_copy_file": False,
    }
    tab = GeneratorTab(settings)
    qtbot.addWidget(tab)
    assert tab.cb_include_empty.isChecked()
    assert tab.cb_add_edit_prompt.isChecked()
    assert not tab.cb_include_plan.isChecked()
    assert tab.cb_line_numbers.isChecked()
    assert not tab.cb_auto_copy.isChecked()


def test_checkboxes_default_false(qtbot):
    tab = GeneratorTab({})
    qtbot.addWidget(tab)
    assert not tab.cb_include_empty.isChecked()
    assert not tab.cb_add_edit_prompt.isChecked()
    assert not tab.cb_include_plan.isChecked()
    assert not tab.cb_line_numbers.isChecked()
    assert not tab.cb_auto_copy.isChecked()


def test_collect_settings_includes_checkboxes(settings, qtbot):
    tab = GeneratorTab(settings)
    qtbot.addWidget(tab)
    tab.cb_include_empty.setChecked(True)
    tab.cb_line_numbers.setChecked(True)
    result = tab.collect_settings()
    assert result["include_empty_folders"] is True
    assert result["line_numbers"] is True
    assert result["add_edit_prompt"] is False
    assert result["include_plan"] is False
    assert result["auto_copy_file"] is False


@pytest.mark.parametrize(
    "cb_attr",
    [
        "cb_include_empty",
        "cb_add_edit_prompt",
        "cb_include_plan",
        "cb_line_numbers",
        "cb_auto_copy",
    ],
)
def test_settings_changed_emitted_on_checkbox_toggle(settings, qtbot, cb_attr):
    tab = GeneratorTab(settings)
    qtbot.addWidget(tab)
    cb = getattr(tab, cb_attr)
    with qtbot.waitSignal(tab.settings_changed, timeout=500):
        cb.toggle()


# ---------- T-103: QCompleter для недавних проектов ----------


def test_completer_attached_to_path_edit(settings, qtbot):
    settings["recent_projects"] = ["/a", "/b", "/c"]
    tab = GeneratorTab(settings)
    qtbot.addWidget(tab)
    completer = tab.path_edit.completer()
    assert completer is not None
    assert completer.model().stringList() == ["/a", "/b", "/c"]


def test_completer_empty_when_no_recent(qtbot):
    tab = GeneratorTab({})
    qtbot.addWidget(tab)
    completer = tab.path_edit.completer()
    assert completer is not None
    assert completer.model().stringList() == []


def test_commit_adds_current_path_to_front(settings, qtbot):
    settings["recent_projects"] = ["/a", "/b"]
    tab = GeneratorTab(settings)
    qtbot.addWidget(tab)
    tab.path_edit.setText("/new")
    tab.commit_recent_projects()
    assert tab.settings["recent_projects"] == ["/new", "/a", "/b"]


def test_commit_dedupes_existing(settings, qtbot):
    settings["recent_projects"] = ["/a", "/b", "/c"]
    tab = GeneratorTab(settings)
    qtbot.addWidget(tab)
    tab.path_edit.setText("/b")
    tab.commit_recent_projects()
    assert tab.settings["recent_projects"] == ["/b", "/a", "/c"]


def test_commit_caps_at_10(settings, qtbot):
    settings["recent_projects"] = [f"/p{i}" for i in range(10)]
    tab = GeneratorTab(settings)
    qtbot.addWidget(tab)
    tab.path_edit.setText("/new")
    tab.commit_recent_projects()
    recent = tab.settings["recent_projects"]
    assert len(recent) == 10
    assert recent[0] == "/new"
    assert "/p9" not in recent  # самый старый вытеснен


def test_commit_skips_empty(settings, qtbot):
    settings["recent_projects"] = ["/a"]
    tab = GeneratorTab(settings)
    qtbot.addWidget(tab)
    tab.path_edit.setText("   ")
    tab.commit_recent_projects()
    assert tab.settings["recent_projects"] == ["/a"]


def test_commit_refreshes_completer(settings, qtbot):
    settings["recent_projects"] = ["/a"]
    tab = GeneratorTab(settings)
    qtbot.addWidget(tab)
    tab.path_edit.setText("/new")
    tab.commit_recent_projects()
    completer = tab.path_edit.completer()
    assert completer.model().stringList() == ["/new", "/a"]


def test_main_window_close_commits_recent(qtbot, tmp_path, monkeypatch):
    """MainWindow.closeEvent вызывает commit_recent_projects перед save."""
    from PIG_T3.config import ConfigManager
    from PIG_T3.gui_qt.main_window import MainWindow
    from PIG_T3.gui_qt.tabs.generator import GeneratorTab

    cfg_path = tmp_path / "app_config.json"
    config = ConfigManager()
    monkeypatch.setattr(config, "config_file", str(cfg_path))

    settings = {"recent_projects": ["/old"], "root_folder": "/default"}
    window = MainWindow(config, settings)
    qtbot.addWidget(window)

    generator = window._tab_widgets["generator"]
    assert isinstance(generator, GeneratorTab)
    generator.path_edit.setText("/chosen")

    window.close()

    import json

    saved = json.loads(cfg_path.read_text())
    assert saved["recent_projects"][0] == "/chosen"


# ---------- T-105: дерево проекта ----------


def test_tree_view_and_model_exist(settings, qtbot):
    from PIG_T3.gui_qt.models.project_tree import ProjectTreeModel
    from PIG_T3.gui_qt.widgets.project_tree_view import ProjectTreeView

    tab = GeneratorTab(settings)
    qtbot.addWidget(tab)
    assert hasattr(tab, "tree_view")
    assert hasattr(tab, "tree_model")
    assert isinstance(tab.tree_view, ProjectTreeView)
    assert isinstance(tab.tree_model, ProjectTreeModel)
    assert tab.tree_view.model() is tab.tree_model


def test_tree_populated_from_scan_on_init(qtbot, tmp_path):
    (tmp_path / "a.py").write_text("x = 1")
    (tmp_path / "b.md").write_text("# hi")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "c.py").write_text("y = 2")

    settings = {
        "root_folder": str(tmp_path),
        "extensions": ".py, .md",
        "ignore_list": "",
        "output_name": "ctx",
    }
    tab = GeneratorTab(settings)
    qtbot.addWidget(tab)
    from PySide6.QtCore import QModelIndex

    assert tab.tree_model.rowCount(QModelIndex()) == 3  # a.py, b.md, sub


def test_set_tree_data_manual(settings, qtbot, tmp_path):
    from PySide6.QtCore import QModelIndex

    settings["root_folder"] = str(tmp_path)
    tab = GeneratorTab(settings)
    qtbot.addWidget(tab)
    tab.set_tree_data([(str(tmp_path / "x.py"), ".py")])
    assert tab.tree_model.rowCount(QModelIndex()) == 1


def test_tree_ignores_empty_ignore_entries(qtbot, tmp_path):
    """Пустые элементы в ignore-листе не должны блокировать весь скан."""
    (tmp_path / "a.py").write_text("x = 1")

    settings = {
        "root_folder": str(tmp_path),
        "extensions": ".py",
        "ignore_list": " , , , ",  # только пробелы и запятые
        "output_name": "ctx",
    }
    tab = GeneratorTab(settings)
    qtbot.addWidget(tab)
    from PySide6.QtCore import QModelIndex

    assert tab.tree_model.rowCount(QModelIndex()) == 1
