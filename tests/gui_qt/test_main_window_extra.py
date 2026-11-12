"""Day 6: MainWindow — _apply_* методы, _refresh_status edge."""

import pytest

from PIG_T3.config import ConfigManager
from PIG_T3.gui_qt.main_window import _TAB_KEYS, MainWindow


@pytest.fixture
def window(qtbot, tmp_path, monkeypatch):
    cfg = tmp_path / "app_config.json"
    config = ConfigManager()
    monkeypatch.setattr(config, "config_file", str(cfg))
    w = MainWindow(
        config,
        {
            "recent_projects": [],
            "root_folder": str(tmp_path),
            "tabs_visibility": {
                "generator": True,
                "info": True,
                "editor": True,
                "plan": True,
                "quality": True,
            },
            "theme": "dark",
            "tree_row_height": 22,
        },
    )
    qtbot.addWidget(w)
    return w


def test_apply_theme_now(window):
    window.settings["theme"] = "light"
    window._apply_theme_now()  # не падает


def test_apply_tab_visibility_all_visible(window):
    window.settings["tabs_visibility"] = {k: True for k in _TAB_KEYS}
    window._apply_tab_visibility()
    for i in range(len(_TAB_KEYS)):
        assert window.tabs.isTabVisible(i)


def test_apply_tab_visibility_hides_all(window):
    window.settings["tabs_visibility"] = {k: False for k in _TAB_KEYS}
    window._apply_tab_visibility()
    for i in range(len(_TAB_KEYS)):
        assert not window.tabs.isTabVisible(i)


def test_apply_row_height_zero_noop(window):
    window.settings["tree_row_height"] = 0
    window._apply_row_height()  # noop, не падает


def test_refresh_status_active_tab_no_widget(window, monkeypatch):
    """Активная вкладка без status_label — не падает."""
    window._refresh_status_from_active_tab()  # info tab без status_label


def test_refresh_status_invalid_index(window):
    window._refresh_status_from_active_tab()  # при -1/None не падает
    window.tabs.setCurrentIndex(-1)
    window._refresh_status_from_active_tab()


def test_open_settings_cancel(window, monkeypatch):
    from PySide6.QtWidgets import QDialog

    from PIG_T3.gui_qt.dialogs import settings_dialog

    monkeypatch.setattr(
        settings_dialog.SettingsDialog,
        "exec",
        lambda self: QDialog.DialogCode.Rejected,
    )
    window._open_settings()  # ничего не меняется


def test_open_settings_accept(window, monkeypatch):
    from PySide6.QtWidgets import QDialog

    class _FakeDlg:
        DialogCode = QDialog.DialogCode

        def __init__(self, *a, **kw):
            pass

        def exec(self):
            return QDialog.DialogCode.Accepted

        def get_updated_settings(self):
            return {"theme": "light", "tree_row_height": 18}

    monkeypatch.setattr("PIG_T3.gui_qt.main_window.SettingsDialog", _FakeDlg)
    window._open_settings()
    assert window.settings["tree_row_height"] == 18


def test_close_event_stops_workers(window, qtbot, monkeypatch):
    """closeEvent вызывает stop_* у всех вкладок + сохраняет конфиг."""
    called: list[str] = []
    gen = window._tab_widgets["generator"]
    monkeypatch.setattr(gen, "stop_generation", lambda: called.append("gen"))
    monkeypatch.setattr(gen, "stop_optimization", lambda: called.append("opt"))
    monkeypatch.setattr(gen, "commit_recent_projects", lambda: called.append("recent"))
    monkeypatch.setattr(gen, "capture_tree_state", lambda: {"ui_tree_expanded": [], "ui_tree_unchecked": []})
    editor = window._tab_widgets["editor"]
    monkeypatch.setattr(editor, "stop_workers", lambda: called.append("editor"))
    plan = window._tab_widgets["plan"]
    monkeypatch.setattr(plan, "stop_workers", lambda: called.append("plan"))
    quality = window._tab_widgets["quality"]
    monkeypatch.setattr(quality, "stop_scan", lambda: called.append("quality"))

    window.close()
    assert "gen" in called
    assert "opt" in called
    assert "editor" in called
    assert "plan" in called
    assert "quality" in called


# ---------- C7 follow-up: ported from test_misc_coverage.py ----------


def test_get_version_fallback(qtbot, tmp_path, monkeypatch):
    """importlib.metadata.version падает → 'v?.?.?'."""
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
            "tabs_visibility": {
                "generator": True,
                "info": True,
                "editor": True,
                "plan": True,
                "quality": True,
            },
            "theme": "dark",
        },
    )
    qtbot.addWidget(w)
    assert w._get_version() == "v?.?.?"
