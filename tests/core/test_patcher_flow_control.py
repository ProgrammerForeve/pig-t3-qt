import json

from PIG_T3.core.patcher import apply_llm_changes


def _apply(actions, root, **kw):
    return apply_llm_changes(json.dumps(actions), str(root), **kw)


def test_depends_on_ok(tmp_path):
    (tmp_path / "a.py").write_text("x=1\n")
    (tmp_path / "b.py").write_text("y=1\n")
    actions = [
        {
            "id": "e1",
            "action": "edit",
            "path": "a.py",
            "operations": [{"type": "replace_lines", "start": 1, "end": 1, "content": "x=2\n"}],
        },
        {
            "id": "e2",
            "action": "edit",
            "path": "b.py",
            "operations": [{"type": "replace_lines", "start": 1, "end": 1, "content": "y=2\n"}],
            "depends_on": ["e1"],
        },
    ]
    log = _apply(actions, tmp_path)
    assert "Line Patch" in log
    assert (tmp_path / "a.py").read_text() == "x=2\n"
    assert (tmp_path / "b.py").read_text() == "y=2\n"


def test_duplicate_ids(tmp_path):
    actions = [
        {"id": "e1", "action": "create", "path": "a.py", "content": "1"},
        {"id": "e1", "action": "create", "path": "b.py", "content": "2"},
    ]
    log = _apply(actions, tmp_path)
    assert "Дублирующиеся id" in log
    assert not (tmp_path / "a.py").exists()
    assert not (tmp_path / "b.py").exists()


def test_command_xor_commands(tmp_path):
    actions = [
        {
            "action": "run_command",
            "command": "echo a",
            "commands": ["echo b"],
        }
    ]
    log = _apply(actions, tmp_path, allow_command_execution=True)
    assert "взаимоисключающие" in log


def test_depends_on_skip(tmp_path):
    actions = [
        {
            "id": "e1",
            "action": "edit",
            "path": "missing.py",
            "operations": [{"type": "replace_lines", "start": 1, "end": 1, "content": "z\n"}],
        },
        {"id": "e2", "action": "create", "path": "b.py", "content": "2", "depends_on": ["e1"]},
    ]
    log = _apply(actions, tmp_path)
    assert "Skip e2" in log
    assert not (tmp_path / "b.py").exists()


def test_depends_on_transitive_skip(tmp_path):
    actions = [
        {
            "id": "e1",
            "action": "edit",
            "path": "missing.py",
            "operations": [{"type": "replace_lines", "start": 1, "end": 1, "content": "z\n"}],
        },
        {"id": "e2", "action": "create", "path": "b.py", "content": "2", "depends_on": ["e1"]},
        {"id": "e3", "action": "create", "path": "c.py", "content": "3", "depends_on": ["e2"]},
    ]
    log = _apply(actions, tmp_path)
    assert "Skip e2" in log
    assert "Skip e3" in log
    assert not (tmp_path / "b.py").exists()
    assert not (tmp_path / "c.py").exists()


def test_deadlock(tmp_path):
    actions = [
        {"id": "a", "action": "create", "path": "a.py", "content": "1", "depends_on": ["b"]},
        {"id": "b", "action": "create", "path": "b.py", "content": "1", "depends_on": ["a"]},
    ]
    log = _apply(actions, tmp_path)
    assert "Циклическая" in log
    assert not (tmp_path / "a.py").exists()
    assert not (tmp_path / "b.py").exists()


def test_on_failure_abort(tmp_path):
    actions = [
        {
            "id": "e1",
            "action": "edit",
            "path": "missing.py",
            "operations": [{"type": "replace_lines", "start": 1, "end": 1, "content": "z\n"}],
            "on_failure": "abort",
        },
        {"id": "e2", "action": "create", "path": "b.py", "content": "2"},
    ]
    log = _apply(actions, tmp_path)
    assert "PIPELINE ABORTED" in log
    assert not (tmp_path / "b.py").exists()


def test_on_success_abort(tmp_path):
    actions = [
        {"id": "e1", "action": "create", "path": "a.py", "content": "1", "on_success": "abort"},
        {"id": "e2", "action": "create", "path": "b.py", "content": "2"},
    ]
    log = _apply(actions, tmp_path)
    assert "PIPELINE ABORTED (on_success)" in log
    assert (tmp_path / "a.py").exists()
    assert not (tmp_path / "b.py").exists()


def test_rollback_restore(tmp_path):
    (tmp_path / "a.py").write_text("orig\n")
    backup = tmp_path / ".pig" / "backups" / "bk"
    (backup / "before").mkdir(parents=True)
    (backup / "before" / "a.py").write_text("orig\n")
    (backup / "after").mkdir(parents=True)
    (backup / "after" / "a.py").write_text("new\n")

    actions = [
        {
            "id": "e1",
            "action": "edit",
            "path": "a.py",
            "operations": [{"type": "replace_lines", "start": 1, "end": 1, "content": "new\n"}],
        },
        {
            "id": "e2",
            "action": "edit",
            "path": "missing.py",
            "operations": [{"type": "replace_lines", "start": 1, "end": 1, "content": "z\n"}],
            "on_failure": "rollback",
        },
    ]
    log = _apply(actions, tmp_path, backup_dir=str(backup))
    assert "Rollback restore" in log
    assert (tmp_path / "a.py").read_text() == "orig\n"


def test_rollback_deletes_created(tmp_path):
    backup = tmp_path / ".pig" / "backups" / "bk"
    (backup / "before").mkdir(parents=True)
    (backup / "after").mkdir(parents=True)
    (backup / "after" / "new.py").write_text("x\n")
    (tmp_path / "new.py").write_text("x\n")

    actions = [
        {
            "id": "e1",
            "action": "edit",
            "path": "missing.py",
            "operations": [{"type": "replace_lines", "start": 1, "end": 1, "content": "z\n"}],
            "on_failure": "rollback",
        },
    ]
    log = _apply(actions, tmp_path, backup_dir=str(backup))
    assert "Rollback delete" in log
    assert not (tmp_path / "new.py").exists()


def test_backward_compat_no_id(tmp_path):
    actions = [
        {"action": "create", "path": "a.py", "content": "1"},
        {"action": "create", "path": "b.py", "content": "2"},
    ]
    log = _apply(actions, tmp_path)
    assert (tmp_path / "a.py").exists()
    assert (tmp_path / "b.py").exists()
    assert "PIPELINE ABORTED" not in log
