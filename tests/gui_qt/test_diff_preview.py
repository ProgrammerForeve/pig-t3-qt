"""B1: compute_diffs — эмуляция патча без записи на диск."""

from __future__ import annotations

import json

import pytest

from PIG_T3.gui_qt.workers.diff_preview import compute_diffs


def _actions(*items) -> str:
    return json.dumps(list(items))


def test_create_diff(tmp_path):
    llm = _actions({"action": "create", "path": "new.py", "content": "x = 1\n"})
    diffs = compute_diffs(llm, str(tmp_path))
    assert len(diffs) == 1
    assert diffs[0].path == "new.py"
    assert diffs[0].status == "created"
    assert "+x = 1" in diffs[0].unified_diff
    # Файл на диск НЕ записан
    assert not (tmp_path / "new.py").exists()


def test_modify_diff(tmp_path):
    (tmp_path / "a.py").write_text("old\n")
    llm = _actions(
        {
            "action": "edit",
            "path": "a.py",
            "operations": [{"type": "replace_lines", "start": 1, "end": 1, "content": "new\n"}],
        }
    )
    diffs = compute_diffs(llm, str(tmp_path))
    assert len(diffs) == 1
    assert diffs[0].status == "modified"
    assert "-old" in diffs[0].unified_diff
    assert "+new" in diffs[0].unified_diff
    # Файл на диске НЕ изменён
    assert (tmp_path / "a.py").read_text() == "old\n"


def test_delete_diff(tmp_path):
    (tmp_path / "gone.py").write_text("x\n")
    llm = _actions({"action": "delete", "path": "gone.py"})
    diffs = compute_diffs(llm, str(tmp_path))
    assert len(diffs) == 1
    assert diffs[0].status == "deleted"
    assert "-x" in diffs[0].unified_diff
    # Файл на диске НЕ удалён
    assert (tmp_path / "gone.py").exists()


def test_empty_patch(tmp_path):
    assert compute_diffs("[]", str(tmp_path)) == []


def test_path_traversal_rejected(tmp_path):
    llm = _actions({"action": "create", "path": "../escape.py", "content": "x\n"})
    diffs = compute_diffs(llm, str(tmp_path))
    assert diffs == []


def test_non_list_json_raises(tmp_path):
    with pytest.raises(ValueError):
        compute_diffs('{"a": 1}', str(tmp_path))


def test_mark_step_ignored(tmp_path):
    llm = _actions({"action": "mark_step_completed", "step_id": "s1", "completed": True})
    assert compute_diffs(llm, str(tmp_path)) == []


def test_nested_path_diff(tmp_path):
    llm = _actions({"action": "create", "path": "sub/dir/f.py", "content": "y\n"})
    diffs = compute_diffs(llm, str(tmp_path))
    assert len(diffs) == 1
    assert diffs[0].path == "sub/dir/f.py"
