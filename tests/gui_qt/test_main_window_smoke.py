"""T-704: smoke-тест главного окна."""

from __future__ import annotations

import pytest

from PIG_T3.config import ConfigManager
from PIG_T3.gui_qt.main_window import MainWindow
from PIG_T3.gui_qt.tabs import (
    EditorTab,
    GeneratorTab,
    InfoTab,
    PlanTab,
    QualityTab,
)


@pytest.fixture
def window(qtbot, tmp_path, monkeypatch):
    cfg_path = tmp_path / "app_config.json"
    config = ConfigManager()
    monkeypatch.setattr(config, "config_file", str(cfg_path))
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


def test_all_five_tabs_present(window):
    assert window.tabs.count() == 5


def test_generator_is_pyside6(window):
    assert isinstance(window._tab_widgets["generator"], GeneratorTab)


def test_info_is_pyside6(window):
    assert isinstance(window._tab_widgets["info"], InfoTab)


def test_editor_is_pyside6(window):
    assert isinstance(window._tab_widgets["editor"], EditorTab)


def test_plan_is_pyside6(window):
    assert isinstance(window._tab_widgets["plan"], PlanTab)


def test_quality_is_pyside6(window):
    assert isinstance(window._tab_widgets["quality"], QualityTab)


def test_no_legacy_tkinter_imports():
    import pathlib

    pkg_root = pathlib.Path(__file__).resolve().parent.parent.parent / "PIG_T3"
    forbidden = ("import tkinter", "from tkinter")
    offenders = []
    for py in pkg_root.rglob("*.py"):
        content = py.read_text(encoding="utf-8", errors="replace")
        if any(tok in content for tok in forbidden):
            offenders.append(str(py.relative_to(pkg_root.parent)))
    assert not offenders, f"tkinter found in: {offenders}"


def test_no_legacy_gui_imports():
    import pathlib

    root = pathlib.Path(__file__).resolve().parent.parent.parent
    forbidden = ("PIG_T3.gui.", "from ..gui ", "from .gui ")
    offenders = []
    for py in (root / "PIG_T3").rglob("*.py"):
        content = py.read_text(encoding="utf-8", errors="replace")
        if any(tok in content for tok in forbidden):
            offenders.append(str(py.relative_to(root)))
    assert not offenders, f"legacy gui refs in: {offenders}"


def test_window_close_does_not_raise(window, qtbot):
    window.close()
    qtbot.wait(10)
