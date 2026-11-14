"""ADR-015 UI: HistoryTab smoke-тесты."""

from __future__ import annotations

import json

from PySide6.QtCore import Qt

from PIG_T3.gui_qt.models.history_tree_model import HistoryTreeModel
from PIG_T3.gui_qt.tabs.history import HistoryTab

# ---------- Model ----------


def test_model_empty_no_manager():
    m = HistoryTreeModel(None)
    from PySide6.QtCore import QModelIndex

    assert m.rowCount(QModelIndex()) == 0
    assert m.columnCount(QModelIndex()) == 1


def test_model_with_manager(qtbot, tmp_path):
    from PIG_T3.core.history_tree import HistoryTreeManager

    mgr = HistoryTreeManager(str(tmp_path))
    n1 = mgr.apply("created a.py", ["a.py"], source="editor")
    n2 = mgr.apply("edited a.py", ["a.py"], source="editor")
    m = HistoryTreeModel(mgr)
    from PySide6.QtCore import QModelIndex

    assert m.rowCount(QModelIndex()) == 1  # n1 root
    root_idx = m.index(0, 0, QModelIndex())
    assert m.rowCount(root_idx) == 1  # n2 child
    child_idx = m.index(0, 0, root_idx)
    assert m.node_id_at(root_idx) == n1
    assert m.node_id_at(child_idx) == n2


def test_model_icons(qtbot, tmp_path):
    from PIG_T3.core.history_tree import HistoryTreeManager

    mgr = HistoryTreeManager(str(tmp_path))
    mgr.apply("first", [])
    mgr.apply("second", [])
    mgr.undo()  # second -> rolled_back, current = n1
    m = HistoryTreeModel(mgr)
    from PySide6.QtCore import QModelIndex

    root_idx = m.index(0, 0, QModelIndex())
    text = m.data(root_idx, Qt.ItemDataRole.DisplayRole)
    assert "🟢" in text
    assert "🔵" in text  # n1 is current


def test_model_find_index(qtbot, tmp_path):
    from PIG_T3.core.history_tree import HistoryTreeManager

    mgr = HistoryTreeManager(str(tmp_path))
    n1 = mgr.apply("first", [])
    m = HistoryTreeModel(mgr)
    idx = m.find_index(n1)
    assert idx.isValid()
    assert m.node_id_at(idx) == n1
    assert not m.find_index("missing").isValid()


# ---------- Tab ----------


def _make_tree(tmp_path, n=2):
    (tmp_path / ".pig").mkdir()
    nodes = {}
    for i in range(n):
        nid = f"node-{i}"
        parent = None if i == 0 else f"node-{i - 1}"
        nodes[nid] = {
            "id": nid,
            "parent": parent,
            "children": [],
            "action_summary": f"action {i}",
            "source": "editor",
            "status": "applied",
            "files": ["a.py"],
            "applied_at": f"2026-11-14T00:00:0{i}",
        }
        if parent:
            nodes[parent]["children"].append(nid)
    payload = {"current": f"node-{n - 1}", "nodes": nodes}
    (tmp_path / ".pig" / "history_tree.json").write_text(json.dumps(payload), encoding="utf-8")
    return payload


def test_tab_empty_state(qtbot, tmp_path):
    tab = HistoryTab({"root_folder": str(tmp_path)})
    qtbot.addWidget(tab)
    assert "пуста" in tab.status_label.text().lower()


def test_tab_missing_path(qtbot):
    tab = HistoryTab({"root_folder": ""})
    qtbot.addWidget(tab)
    assert "Выберите папку" in tab.status_label.text()


def test_tab_set_path_reloads(qtbot, tmp_path):
    _make_tree(tmp_path, n=2)
    tab = HistoryTab({"root_folder": ""})
    qtbot.addWidget(tab)
    tab.set_path(str(tmp_path))
    assert "Нод: 2" in tab.status_label.text()


def test_tab_buttons_exist(qtbot, tmp_path):
    tab = HistoryTab({"root_folder": str(tmp_path)})
    qtbot.addWidget(tab)
    for btn in (
        tab.btn_rollback,
        tab.btn_branch,
        tab.btn_redo,
        tab.btn_delete,
        tab.btn_prune,
    ):
        assert btn is not None
        assert btn.toolTip()


def test_tab_buttons_disabled_on_empty(qtbot, tmp_path):
    tab = HistoryTab({"root_folder": str(tmp_path)})
    qtbot.addWidget(tab)
    for btn in (
        tab.btn_rollback,
        tab.btn_branch,
        tab.btn_redo,
        tab.btn_delete,
        tab.btn_prune,
    ):
        assert not btn.isEnabled()


def test_tab_buttons_state_on_populated(qtbot, tmp_path):
    _make_tree(tmp_path, n=2)
    tab = HistoryTab({"root_folder": str(tmp_path)})
    qtbot.addWidget(tab)
    assert tab.btn_rollback.isEnabled()
    assert tab.btn_branch.isEnabled()
    assert tab.btn_delete.isEnabled()
    assert not tab.btn_redo.isEnabled()
    assert not tab.btn_prune.isEnabled()


def test_tab_selection_shows_details(qtbot, tmp_path):
    _make_tree(tmp_path, n=2)
    tab = HistoryTab({"root_folder": str(tmp_path)})
    qtbot.addWidget(tab)
    from PySide6.QtCore import QModelIndex

    root_idx = tab.model.index(0, 0, QModelIndex())
    tab.tree_view.setCurrentIndex(root_idx)
    html = tab.details.toHtml()
    assert "action 0" in html


def test_tab_diff_html_from_backup(qtbot, tmp_path):
    _make_tree(tmp_path, n=1)
    backup = tmp_path / ".pig" / "backups" / "node-0"
    (backup / "before").mkdir(parents=True)
    (backup / "after").mkdir(parents=True)
    (backup / "before" / "a.py").write_text("old\n")
    (backup / "after" / "a.py").write_text("new\n")
    tab = HistoryTab({"root_folder": str(tmp_path)})
    qtbot.addWidget(tab)
    from PySide6.QtCore import QModelIndex

    root_idx = tab.model.index(0, 0, QModelIndex())
    tab.tree_view.setCurrentIndex(root_idx)
    html = tab.details.toHtml()
    assert "old" in html or "new" in html


def test_tab_missing_backup_shows_hint(qtbot, tmp_path):
    _make_tree(tmp_path, n=1)
    tab = HistoryTab({"root_folder": str(tmp_path)})
    qtbot.addWidget(tab)
    from PySide6.QtCore import QModelIndex

    root_idx = tab.model.index(0, 0, QModelIndex())
    tab.tree_view.setCurrentIndex(root_idx)
    html = tab.details.toHtml()
    assert "Бэкап не найден" in html


def test_tab_broken_json_does_not_crash(qtbot, tmp_path):
    (tmp_path / ".pig").mkdir()
    (tmp_path / ".pig" / "history_tree.json").write_text("not json", encoding="utf-8")
    tab = HistoryTab({"root_folder": str(tmp_path)})
    qtbot.addWidget(tab)
    # load failed → пустое состояние, без исключения
    assert tab.status_label.text() != ""


# ---------- Button handlers ----------


def _make_tree_with_backup(tmp_path, n=2):
    _make_tree(tmp_path, n=n)
    for i in range(n):
        nid = f"node-{i}"
        backup = tmp_path / ".pig" / "backups" / nid
        (backup / "before").mkdir(parents=True)
        (backup / "after").mkdir(parents=True)
        (backup / "before" / "a.py").write_text(f"before-{i}\n")
        (backup / "after" / "a.py").write_text(f"after-{i}\n")


def test_rollback_button_enabled_and_undoes(qtbot, tmp_path):
    _make_tree_with_backup(tmp_path, n=2)
    tab = HistoryTab({"root_folder": str(tmp_path)})
    qtbot.addWidget(tab)
    assert tab.btn_rollback.isEnabled()
    tab.btn_rollback.click()
    assert tab._manager.current == "node-0"


def test_redo_button_after_rollback(qtbot, tmp_path):
    _make_tree_with_backup(tmp_path, n=2)
    tab = HistoryTab({"root_folder": str(tmp_path)})
    qtbot.addWidget(tab)
    tab.btn_rollback.click()
    assert tab.btn_redo.isEnabled()
    tab.btn_redo.click()
    assert tab._manager.current == "node-1"


def test_branch_button_sets_current(qtbot, tmp_path):
    _make_tree(tmp_path, n=2)
    tab = HistoryTab({"root_folder": str(tmp_path)})
    qtbot.addWidget(tab)
    from PySide6.QtCore import QModelIndex

    root_idx = tab.model.index(0, 0, QModelIndex())
    tab.tree_view.setCurrentIndex(root_idx)
    assert tab.btn_branch.isEnabled()
    tab.btn_branch.click()
    assert tab._manager.current == "node-0"


def test_delete_button_with_confirm(qtbot, tmp_path, monkeypatch):
    _make_tree(tmp_path, n=1)
    tab = HistoryTab({"root_folder": str(tmp_path)})
    qtbot.addWidget(tab)
    from PySide6.QtCore import QModelIndex
    from PySide6.QtWidgets import QMessageBox

    monkeypatch.setattr(
        QMessageBox,
        "question",
        staticmethod(lambda *a, **kw: QMessageBox.StandardButton.Yes),
    )
    root_idx = tab.model.index(0, 0, QModelIndex())
    tab.tree_view.setCurrentIndex(root_idx)
    tab.btn_delete.click()
    assert len(tab._manager.nodes) == 0


def test_prune_button_enabled_when_rolled_back_exists(qtbot, tmp_path):
    _make_tree(tmp_path, n=2)
    tab = HistoryTab({"root_folder": str(tmp_path)})
    qtbot.addWidget(tab)
    assert not tab.btn_prune.isEnabled()
    tab.btn_rollback.click()
    assert tab.btn_prune.isEnabled()


def test_prune_button_removes_rolled_back(qtbot, tmp_path):
    _make_tree(tmp_path, n=2)
    tab = HistoryTab({"root_folder": str(tmp_path)})
    qtbot.addWidget(tab)
    tab.btn_rollback.click()
    n_before = len(tab._manager.nodes)
    tab.btn_prune.click()
    assert len(tab._manager.nodes) < n_before


def test_badge_shown_over_threshold(qtbot, tmp_path):
    from PIG_T3.core.history_tree import HistoryTreeManager

    mgr = HistoryTreeManager(str(tmp_path))
    for i in range(201):
        mgr.apply(f"step {i}", [])
    tab = HistoryTab({"root_folder": str(tmp_path)})
    qtbot.addWidget(tab)
    assert tab.badge.text() != ""


def test_badge_hidden_under_threshold(qtbot, tmp_path):
    _make_tree(tmp_path, n=3)
    tab = HistoryTab({"root_folder": str(tmp_path)})
    qtbot.addWidget(tab)
    assert tab.badge.text() == ""


def test_delete_button_rejected(qtbot, tmp_path, monkeypatch):
    _make_tree(tmp_path, n=1)
    tab = HistoryTab({"root_folder": str(tmp_path)})
    qtbot.addWidget(tab)
    from PySide6.QtCore import QModelIndex
    from PySide6.QtWidgets import QMessageBox

    monkeypatch.setattr(
        QMessageBox,
        "question",
        staticmethod(lambda *a, **kw: QMessageBox.StandardButton.No),
    )
    root_idx = tab.model.index(0, 0, QModelIndex())
    tab.tree_view.setCurrentIndex(root_idx)
    tab.btn_delete.click()
    assert len(tab._manager.nodes) == 1
