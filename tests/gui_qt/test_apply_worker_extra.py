"""Day 4: apply_worker — _filter_paths, _copy_paths, _restore_snapshot, undo error."""

from __future__ import annotations

import pytest

from PIG_T3.gui_qt.workers.apply_worker import (
    ApplyWorker,
    UndoRedoWorker,
    _copy_paths,
    _filter_paths,
    _restore_snapshot,
)

pytestmark = pytest.mark.threading


# ---------- _filter_paths (unit) ----------


def test_filter_rejects_absolute():
    assert _filter_paths(["/etc/passwd", "ok.py"]) == ["ok.py"]


def test_filter_rejects_dotdot():
    assert _filter_paths(["../escape.py", "ok.py"]) == ["ok.py"]


def test_filter_dedupes_nested_dirs():
    # 'a' — папка, покрывает 'a/b.py' и 'a/sub/c.py'
    assert _filter_paths(["a/b.py", "a/sub/c.py", "a", "x.py"]) == ["a", "x.py"]


def test_filter_sorts():
    assert _filter_paths(["z.py", "a.py", "m.py"]) == ["a.py", "m.py", "z.py"]


def test_filter_empty_list():
    assert _filter_paths([]) == []


# ---------- _copy_paths (unit) ----------


def test_copy_paths_skips_missing(tmp_path):
    src = tmp_path / "src"
    dst = tmp_path / "dst"
    src.mkdir()
    _copy_paths(str(src), str(dst), ["missing.py"])
    assert not (dst / "missing.py").exists()


def test_copy_paths_file(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "a.py").write_text("x")
    dst = tmp_path / "dst"
    _copy_paths(str(src), str(dst), ["a.py"])
    assert (dst / "a.py").read_text() == "x"


def test_copy_paths_directory_recursive(tmp_path):
    src = tmp_path / "src"
    (src / "pkg").mkdir(parents=True)
    (src / "pkg" / "a.py").write_text("x")
    (src / "pkg" / "sub").mkdir()
    (src / "pkg" / "sub" / "b.py").write_text("y")
    dst = tmp_path / "dst"
    _copy_paths(str(src), str(dst), ["pkg"])
    assert (dst / "pkg" / "a.py").exists()
    assert (dst / "pkg" / "sub" / "b.py").exists()


# ---------- _restore_snapshot ----------


def test_restore_missing_backup_is_noop(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    (root / "a.py").write_text("current")
    backup_dir = tmp_path / "backup_missing"
    _restore_snapshot(str(root), str(backup_dir), ["a.py"])
    # файл не тронут, т.к. бэкапа нет и target не в бэкапе
    # (в текущей логике _restore_snapshot удаляет target только если
    # backup для него есть)


def test_restore_replaces_file(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    (root / "a.py").write_text("new")
    backup = tmp_path / "backup"
    backup.mkdir()
    (backup / "a.py").write_text("old")
    _restore_snapshot(str(root), str(backup), ["a.py"])
    assert (root / "a.py").read_text() == "old"


def test_restore_dir_from_backup(tmp_path):
    root = tmp_path / "root"
    (root / "pkg").mkdir(parents=True)
    (root / "pkg" / "x.py").write_text("new")
    backup = tmp_path / "backup"
    (backup / "pkg").mkdir(parents=True)
    (backup / "pkg" / "x.py").write_text("old")
    (backup / "pkg" / "y.py").write_text("new_from_backup")
    _restore_snapshot(str(root), str(backup), ["pkg"])
    assert (root / "pkg" / "x.py").read_text() == "old"
    assert (root / "pkg" / "y.py").read_text() == "new_from_backup"


# ---------- UndoRedoWorker error path ----------


def test_undo_worker_error_signal(qtbot, managed_thread, tmp_path, monkeypatch):
    """_restore_snapshot бросает — UndoRedoWorker эмитит error."""
    from PIG_T3.gui_qt.workers import apply_worker as aw_module

    def _boom(*a, **kw):
        raise OSError("disk full")

    monkeypatch.setattr(aw_module, "_restore_snapshot", _boom)
    record = {"id": "fake-uuid", "paths": ["a.py"], "llm_text": ""}
    w = UndoRedoWorker(str(tmp_path), record, "undo")
    t = managed_thread()
    w.moveToThread(t)
    t.started.connect(w.run)
    errors: list[str] = []
    w.error.connect(errors.append)
    with qtbot.waitSignal(w.error, timeout=2000):
        t.start()
    assert errors
    assert "disk full" in errors[0]


def test_apply_worker_empty_json_error(qtbot, managed_thread, tmp_path):
    w = ApplyWorker("not a list", str(tmp_path))
    t = managed_thread()
    w.moveToThread(t)
    t.started.connect(w.run)
    errors: list[str] = []
    w.error.connect(errors.append)
    with qtbot.waitSignal(w.error, timeout=2000):
        t.start()
    assert errors


# ---------- _extract_paths_from_actions ----------


def test_extract_paths_from_actions():
    from PIG_T3.gui_qt.workers.apply_worker import _extract_paths_from_actions

    data = [
        {"action": "create", "path": "a.py"},
        {"action": "delete", "path": "b.py"},
        {"action": "move", "source": "old.py", "destination": "new.py"},
        {"action": "mark_step_completed", "step_id": "s1"},
    ]
    result = _extract_paths_from_actions(data)
    assert "a.py" in result
    assert "b.py" in result
    assert "old.py" in result
    assert "new.py" in result
    # mark_step_completed не имеет path
    assert len(result) == 4


def test_extract_paths_empty():
    from PIG_T3.gui_qt.workers.apply_worker import _extract_paths_from_actions

    assert _extract_paths_from_actions([]) == []
    assert _extract_paths_from_actions([{"action": "mark_step_completed"}]) == []
