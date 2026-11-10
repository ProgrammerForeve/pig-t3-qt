"""TDD: apply_llm_changes — path traversal + базовые действия."""

import json

from PIG_T3.core.patcher import apply_llm_changes


def _actions(*items) -> str:
    return json.dumps(list(items))


def _create(path: str, content: str = "x\n") -> dict:
    return {"action": "create", "path": path, "content": content}


# ---------- Path traversal ----------


def test_create_outside_root_rejected(tmp_path):
    log = apply_llm_changes(_actions(_create("../escape.py")), str(tmp_path))
    assert "outside root" in log
    assert not (tmp_path.parent / "escape.py").exists()


def test_delete_outside_root_rejected(tmp_path):
    victim = tmp_path.parent / "victim.txt"
    victim.write_text("x")
    try:
        log = apply_llm_changes(
            _actions({"action": "delete", "path": "../victim.txt"}),
            str(tmp_path),
        )
        assert "outside root" in log
        assert victim.exists()
    finally:
        victim.unlink(missing_ok=True)


def test_edit_outside_root_rejected(tmp_path):
    log = apply_llm_changes(
        _actions(
            {
                "action": "edit",
                "path": "../escape.py",
                "operations": [{"type": "replace_lines", "start": 1, "end": 1, "content": "x"}],
            }
        ),
        str(tmp_path),
    )
    assert "outside root" in log


def test_move_source_outside_rejected(tmp_path):
    log = apply_llm_changes(
        _actions(
            {
                "action": "move",
                "source": "../elsewhere.py",
                "destination": "inside.py",
            }
        ),
        str(tmp_path),
    )
    assert "source outside root" in log


def test_move_destination_outside_rejected(tmp_path):
    (tmp_path / "src.py").write_text("x")
    log = apply_llm_changes(
        _actions(
            {
                "action": "move",
                "source": "src.py",
                "destination": "../escape.py",
            }
        ),
        str(tmp_path),
    )
    assert "destination outside root" in log
    assert (tmp_path / "src.py").exists()


# ---------- Happy path ----------


def test_create_inside_root_works(tmp_path):
    log = apply_llm_changes(_actions(_create("ok.py", "y = 1\n")), str(tmp_path))
    assert "CREATE: ok.py" in log
    assert (tmp_path / "ok.py").read_text() == "y = 1\n"


def test_nested_create_inside_root_works(tmp_path):
    log = apply_llm_changes(_actions(_create("sub/dir/f.py", "z\n")), str(tmp_path))
    assert "CREATE" in log
    assert (tmp_path / "sub" / "dir" / "f.py").exists()
