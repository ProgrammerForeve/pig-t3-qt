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
    assert node.payload == {}


# ---------- payload / max_nodes / delete_node ----------


def test_apply_with_payload_roundtrip(tmp_path):
    mgr = HistoryTreeManager(str(tmp_path))
    nid = mgr.apply(
        "patch",
        ["a.py"],
        payload={"llm_text": "[json]", "paths": ["a.py"]},
    )
    assert mgr.nodes[nid].payload["llm_text"] == "[json]"
    mgr2 = HistoryTreeManager(str(tmp_path))
    assert mgr2.nodes[nid].payload["llm_text"] == "[json]"


def test_max_nodes_prunes_rolled_back(tmp_path):
    mgr = HistoryTreeManager(str(tmp_path), max_nodes=3)
    mgr.apply("1", [])
    mgr.apply("2", [])
    mgr.apply("3", [])
    mgr.undo()
    mgr.apply("4", [])
    mgr.apply("5", [])
    assert len(mgr.nodes) <= 3


def test_max_nodes_keeps_path_to_current(tmp_path):
    mgr = HistoryTreeManager(str(tmp_path), max_nodes=2)
    a = mgr.apply("a", [])
    b = mgr.apply("b", [])
    c = mgr.apply("c", [])
    mgr.apply("d", [])
    assert mgr.current in mgr.nodes
    assert a in mgr.nodes or b in mgr.nodes or c in mgr.nodes


def test_delete_node_leaf(tmp_path):
    mgr = HistoryTreeManager(str(tmp_path))
    n1 = mgr.apply("1", [])
    n2 = mgr.apply("2", [])
    removed = mgr.delete_node(n2)
    assert removed == 1
    assert n2 not in mgr.nodes
    assert n1 in mgr.nodes


def test_delete_node_with_children_requires_cascade(tmp_path):
    import pytest

    mgr = HistoryTreeManager(str(tmp_path))
    mgr.apply("1", [])
    n2 = mgr.apply("2", [])
    with pytest.raises(ValueError, match="cascade"):
        mgr.delete_node(n2)


def test_delete_node_cascade(tmp_path):
    mgr = HistoryTreeManager(str(tmp_path))
    n1 = mgr.apply("1", [])
    n2 = mgr.apply("2", [])
    n3 = mgr.apply("3", [])
    removed = mgr.delete_node(n1, cascade=True)
    assert removed == 3
    assert n2 not in mgr.nodes
    assert n3 not in mgr.nodes
    assert mgr.current is None
