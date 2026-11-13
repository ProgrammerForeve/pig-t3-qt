"""ADR-015: HistoryTreeManager — apply/undo/redo/branch/persist."""

from __future__ import annotations

from PIG_T3.core.history_tree import HistoryNode, HistoryTreeManager


def test_apply_creates_root(tmp_path):
    mgr = HistoryTreeManager(str(tmp_path))
    nid = mgr.apply("created a.py", ["a.py"])
    assert nid in mgr.nodes
    node = mgr.nodes[nid]
    assert node.parent is None
    assert node.action_summary == "created a.py"
    assert node.files == ["a.py"]
    assert mgr.current == nid


def test_apply_chain_parent(tmp_path):
    mgr = HistoryTreeManager(str(tmp_path))
    n1 = mgr.apply("first", [])
    n2 = mgr.apply("second", [])
    assert mgr.nodes[n2].parent == n1
    assert mgr.current == n2


def test_undo_moves_to_parent(tmp_path):
    mgr = HistoryTreeManager(str(tmp_path))
    n1 = mgr.apply("first", [])
    n2 = mgr.apply("second", [])
    undone = mgr.undo()
    assert undone is not None and undone.id == n2
    assert undone.status == "rolled_back"
    assert mgr.current == n1


def test_undo_root_returns_none(tmp_path):
    mgr = HistoryTreeManager(str(tmp_path))
    mgr.apply("only", [])
    assert mgr.undo() is None


def test_redo_restores(tmp_path):
    mgr = HistoryTreeManager(str(tmp_path))
    mgr.apply("first", [])
    n2 = mgr.apply("second", [])
    mgr.undo()
    redone = mgr.redo()
    assert redone is not None and redone.id == n2
    assert mgr.current == n2


def test_redo_without_undone_returns_none(tmp_path):
    mgr = HistoryTreeManager(str(tmp_path))
    mgr.apply("only", [])
    assert mgr.redo() is None


def test_persists_across_instances(tmp_path):
    mgr = HistoryTreeManager(str(tmp_path))
    nid = mgr.apply("action", ["x.py"])
    mgr2 = HistoryTreeManager(str(tmp_path))
    assert nid in mgr2.nodes
    assert mgr2.current == nid
    assert mgr2.nodes[nid].action_summary == "action"


def test_branch_from_resets_current(tmp_path):
    mgr = HistoryTreeManager(str(tmp_path))
    n1 = mgr.apply("first", [])
    mgr.apply("second", [])
    mgr.branch_from(n1)
    assert mgr.current == n1


def test_history_node_defaults():
    node = HistoryNode(id="x")
    assert node.parent is None
    assert node.children == []
    assert node.source == "editor"
    assert node.status == "applied"
