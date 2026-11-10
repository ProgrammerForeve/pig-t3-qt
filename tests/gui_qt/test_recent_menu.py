"""B4: RecentProjectsMenu — populate, click, clear."""

import os

from PIG_T3.gui_qt.widgets.recent_menu import RecentProjectsMenu


def _actions(menu):
    return [a for a in menu.actions() if a.text()]


def test_empty_shows_placeholder(qtbot):
    menu = RecentProjectsMenu()
    qtbot.addWidget(menu)
    actions = _actions(menu)
    assert any("пусто" in a.text().lower() for a in actions)


def test_populated(qtbot, tmp_path):
    d1 = tmp_path / "d1"
    d2 = tmp_path / "d2"
    d1.mkdir()
    d2.mkdir()
    menu = RecentProjectsMenu()
    qtbot.addWidget(menu)
    menu.update_projects([str(d1), str(d2)])
    texts = [a.text() for a in _actions(menu)]
    assert str(d1) in texts
    assert str(d2) in texts


def test_missing_paths_filtered(qtbot, tmp_path):
    d1 = tmp_path / "d1"
    d1.mkdir()
    menu = RecentProjectsMenu()
    qtbot.addWidget(menu)
    menu.update_projects([str(d1), "/nonexistent_xyz"])
    texts = [a.text() for a in _actions(menu)]
    assert str(d1) in texts
    assert "/nonexistent_xyz" not in texts


def test_caps_at_10(qtbot, tmp_path):
    paths = []
    for i in range(15):
        d = tmp_path / f"d{i}"
        d.mkdir()
        paths.append(str(d))
    menu = RecentProjectsMenu()
    qtbot.addWidget(menu)
    menu.update_projects(paths)
    # 10 путей + "Очистить список"
    real_paths = [a for a in _actions(menu) if os.path.isdir(a.text())]
    assert len(real_paths) <= 10


def test_click_emits_signal(qtbot, tmp_path):
    d = tmp_path / "proj"
    d.mkdir()
    menu = RecentProjectsMenu()
    qtbot.addWidget(menu)
    menu.update_projects([str(d)])

    with qtbot.waitSignal(menu.project_selected, timeout=500) as blocker:
        for action in menu.actions():
            if action.text() == str(d):
                action.trigger()
                break
    assert blocker.args == [str(d)]


def test_clear_emits_signal(qtbot, tmp_path):
    d = tmp_path / "proj"
    d.mkdir()
    menu = RecentProjectsMenu()
    qtbot.addWidget(menu)
    menu.update_projects([str(d)])

    with qtbot.waitSignal(menu.recent_cleared, timeout=500):
        for action in menu.actions():
            if "Очистить" in action.text():
                action.trigger()
                break
