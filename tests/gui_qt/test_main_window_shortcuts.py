"""TDD: горячие клавиши MainWindow (T-707).

QShortcut в offscreen QPA не срабатывает от QTest.keyClick (ограничение
плагина). Вместо эмуляции клавиш проверяем:
- шорткаты зарегистрированы с правильными QKeySequence;
- связанные действия (методы) работают при прямом вызове.
"""

import pytest
from PySide6.QtGui import QShortcut

from PIG_T3.config import ConfigManager
from PIG_T3.gui_qt.main_window import MainWindow


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
        },
    )
    qtbot.addWidget(w)
    return w


def test_tab_shortcuts_registered(window):
    keys = {sc.key().toString() for sc in window.findChildren(QShortcut)}
    for i in range(1, 6):
        assert f"Ctrl+{i}" in keys, f"Ctrl+{i} not registered"


def test_settings_shortcut_registered(window):
    keys = {sc.key().toString() for sc in window.findChildren(QShortcut)}
    assert "Ctrl+," in keys


def test_f5_shortcut_registered(window):
    keys = {sc.key().toString() for sc in window.findChildren(QShortcut)}
    assert "F5" in keys


def test_refresh_generator_tree_switches_tab(window):
    window.tabs.setCurrentIndex(3)
    window._refresh_generator_tree()
    assert window.tabs.currentIndex() == 0


def test_refresh_generator_tree_calls_refresh(window, monkeypatch):
    generator = window._tab_widgets["generator"]
    calls: list[int] = []
    monkeypatch.setattr(generator, "refresh_tree", lambda: calls.append(1))
    window._refresh_generator_tree()
    assert calls
