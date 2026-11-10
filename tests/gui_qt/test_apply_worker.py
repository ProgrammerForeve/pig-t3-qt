"""TDD: ApplyWorker / UndoRedoWorker (T-304/T-305)."""

import json

import pytest

from PIG_T3.gui_qt.workers.apply_worker import (
    ApplyWorker,
    UndoRedoWorker,
    _filter_paths,
)
from tests.helpers.threading import run_worker_and_wait

pytestmark = pytest.mark.threading


def test_filter_paths_drops_nested(tmp_path):
    assert _filter_paths(["a/b.py", "a/b/c.py", "c.py"]) == ["a/b.py", "c.py"]


def test_filter_paths_drops_absolute():
    assert _filter_paths(["/etc/passwd", "a.py"]) == ["a.py"]


def _patch_json(path: str, content: str) -> str:
    return json.dumps([{"action": "create", "path": path, "content": content}])


def test_apply_create_file(qtbot, managed_thread, tmp_path):
    patch = _patch_json("new.py", "x = 1\n")
    worker = ApplyWorker(patch, str(tmp_path))
    thread = managed_thread()
    worker.moveToThread(thread)
    args = run_worker_and_wait(qtbot, worker, thread, done_signal=worker.done)
    log, record = args
    assert "CREATE: new.py" in log
    assert "id" in record
    assert (tmp_path / "new.py").read_text() == "x = 1\n"
    assert (tmp_path / ".pig" / "backups" / record["id"] / "after" / "new.py").exists()


def test_apply_error_signal(qtbot, managed_thread, tmp_path):
    worker = ApplyWorker("not json", str(tmp_path))
    thread = managed_thread()
    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    errors = []
    worker.error.connect(errors.append)
    with qtbot.waitSignal(worker.error, timeout=2000):
        thread.start()
    assert errors


def test_undo_restores_before(qtbot, managed_thread, tmp_path):
    (tmp_path / "a.py").write_text("original\n")
    patch = json.dumps(
        [
            {
                "action": "edit",
                "path": "a.py",
                "operations": [{"type": "replace_lines", "start": 1, "end": 1, "content": "changed\n"}],
            }
        ]
    )
    aw = ApplyWorker(patch, str(tmp_path))
    t1 = managed_thread()
    aw.moveToThread(t1)
    _log, record = run_worker_and_wait(qtbot, aw, t1, done_signal=aw.done)
    assert (tmp_path / "a.py").read_text() == "changed\n"

    uw = UndoRedoWorker(str(tmp_path), record, "undo")
    t2 = managed_thread()
    uw.moveToThread(t2)
    run_worker_and_wait(qtbot, uw, t2, done_signal=uw.done)
    assert (tmp_path / "a.py").read_text() == "original\n"


def test_redo_restores_after(qtbot, managed_thread, tmp_path):
    (tmp_path / "a.py").write_text("original\n")
    patch = json.dumps(
        [
            {
                "action": "edit",
                "path": "a.py",
                "operations": [{"type": "replace_lines", "start": 1, "end": 1, "content": "changed\n"}],
            }
        ]
    )
    aw = ApplyWorker(patch, str(tmp_path))
    t1 = managed_thread()
    aw.moveToThread(t1)
    _log, record = run_worker_and_wait(qtbot, aw, t1, done_signal=aw.done)

    # undo, затем redo
    uw1 = UndoRedoWorker(str(tmp_path), record, "undo")
    t2 = managed_thread()
    uw1.moveToThread(t2)
    run_worker_and_wait(qtbot, uw1, t2, done_signal=uw1.done)

    uw2 = UndoRedoWorker(str(tmp_path), record, "redo")
    t3 = managed_thread()
    uw2.moveToThread(t3)
    run_worker_and_wait(qtbot, uw2, t3, done_signal=uw2.done)

    assert (tmp_path / "a.py").read_text() == "changed\n"
