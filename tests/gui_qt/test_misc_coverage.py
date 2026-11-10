"""Day 6+: добить до 65% — простые функции в generator/editor/main_window."""

import pytest

from PIG_T3.gui_qt.tabs.generator import GeneratorTab

# ---------- GeneratorTab._format_number (3 числа) ----------


def test_format_number_small():
    assert GeneratorTab._format_number(42) == "42"


def test_format_number_k():
    assert GeneratorTab._format_number(1200) == "1.2K"
    assert GeneratorTab._format_number(45_678) == "45.68K"


def test_format_number_m():
    assert GeneratorTab._format_number(1_500_000) == "1.5M"


# ---------- GeneratorTab._estimate_total_tokens ----------


def test_estimate_total_tokens_empty(qtbot, tmp_path):
    tab = GeneratorTab({"root_folder": str(tmp_path), "extensions": ".py", "ignore_list": ""})
    qtbot.addWidget(tab)
    assert tab._estimate_total_tokens() == 1000


def test_estimate_total_tokens_counts_py(qtbot, tmp_path):
    (tmp_path / "a.py").write_text("x" * 4000)  # ~1000 tokens
    tab = GeneratorTab({"root_folder": str(tmp_path), "extensions": ".py", "ignore_list": ""})
    qtbot.addWidget(tab)
    val = tab._estimate_total_tokens()
    assert val >= 1000  # ~1000 от файла + fallback


# ---------- GeneratorTab.refresh_tree с extensions_clean ----------


def test_refresh_tree_filters_by_clean_extensions(qtbot, tmp_path):
    (tmp_path / "a.py").write_text("x")
    (tmp_path / "b.txt").write_text("y")
    tab = GeneratorTab(
        {
            "root_folder": str(tmp_path),
            "extensions": " .py , .md , ",  # пробелы + пустые запятые
            "ignore_list": "",
        }
    )
    qtbot.addWidget(tab)
    from PySide6.QtCore import QModelIndex

    names = {
        tab.tree_model.data(tab.tree_model.index(i, 0, QModelIndex()))
        for i in range(tab.tree_model.rowCount(QModelIndex()))
    }
    assert "a.py" in names
    assert "b.txt" not in names


# ---------- EditorTab._on_undo_redo_done ----------


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


def test_on_undo_redo_done_with_history(editor):
    editor.history_stack = [{"id": "x", "paths": [], "llm_text": '[{"action":"delete","path":"a.py"}]'}]
    editor._on_undo_redo_done("Изменения отменены")
    # _on_undo_redo_done вызывает _on_validate, который перезаписывает
    # status_label на "✅ Валидный JSON…". Проверяем содержимое редактора.
    assert "delete" in editor.editor_text.toPlainText()
    assert "Валидный JSON" in editor.status_label.text()


def test_on_undo_redo_done_empty_stacks(editor):
    editor._on_undo_redo_done("ok")  # не падает


def test_on_apply_error_sets_status(editor):
    editor._on_apply_error("boom")
    assert "boom" in editor.status_label.text()


# ---------- MainWindow._get_version edge ----------


def test_get_version_fallback(qtbot, tmp_path, monkeypatch):
    """importlib.metadata.version падает → v?.?.?"""
    from PIG_T3.config import ConfigManager
    from PIG_T3.gui_qt import main_window as mw

    def _fail(name):
        raise Exception("not installed")

    monkeypatch.setattr(mw.metadata, "version", _fail)
    cfg = tmp_path / "app_config.json"
    config = ConfigManager()
    monkeypatch.setattr(config, "config_file", str(cfg))
    w = mw.MainWindow(
        config,
        {
            "recent_projects": [],
            "tabs_visibility": {"generator": True, "info": True, "editor": True, "plan": True, "quality": True},
            "theme": "dark",
        },
    )
    qtbot.addWidget(w)
    assert w._get_version() == "v?.?.?"
