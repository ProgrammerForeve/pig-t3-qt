"""TDD: применение настроек без перезапуска (T-603)."""

import pytest

from PIG_T3.config import ConfigManager
from PIG_T3.gui_qt.main_window import MainWindow


@pytest.fixture
def window(qtbot, tmp_path, monkeypatch):
    cfg_path = tmp_path / "app_config.json"
    config = ConfigManager()
    monkeypatch.setattr(config, "config_file", str(cfg_path))
    w = MainWindow(
        config,
        {
            "recent_projects": [],
            "tabs_visibility": {"generator": True, "info": True, "editor": True, "plan": True, "quality": True},
            "theme": "dark",
            "tree_row_height": 22,
        },
    )
    qtbot.addWidget(w)
    return w


def test_apply_tab_visibility_hides(window):
    window.settings["tabs_visibility"]["quality"] = False
    window._apply_tab_visibility()
    assert not window.tabs.isTabVisible(4)


def test_apply_row_height(window):
    window.settings["tree_row_height"] = 18
    window._apply_row_height()
    gen = window._tab_widgets["generator"]
    assert gen.tree_view.row_height() == 18
