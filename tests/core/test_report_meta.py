"""Tests for report_meta (Stage 3)."""

from __future__ import annotations

import os

from PIG_T3.core.report_meta import (
    compute_fingerprint,
    is_stale_from_files,
    load_meta,
    save_report_meta,
)


def test_save_and_load(tmp_path):
    f = tmp_path / "a.py"
    f.write_text("x = 1\n", encoding="utf-8")
    st = f.stat()
    save_report_meta(
        str(tmp_path),
        [{"rel_path": "a.py", "size": st.st_size, "mtime_ns": st.st_mtime_ns}],
        str(tmp_path / "project_context.txt"),
    )
    meta = load_meta(str(tmp_path))
    assert meta is not None
    assert meta["file_count"] == 1
    assert meta["fingerprint"]
    assert meta["output_path"] == "project_context.txt"
    assert meta["files"][0]["rel_path"] == "a.py"


def test_load_missing_returns_none(tmp_path):
    assert load_meta(str(tmp_path)) is None


def test_load_invalid_root_returns_none():
    assert load_meta("") is None
    assert load_meta("/nonexistent_xyz") is None


def test_fingerprint_stable():
    files = [{"rel_path": "a.py", "size": 10, "mtime_ns": 100}]
    assert compute_fingerprint(files) == compute_fingerprint(files)


def test_fingerprint_changes_on_mtime():
    files = [{"rel_path": "a.py", "size": 10, "mtime_ns": 100}]
    fp1 = compute_fingerprint(files)
    files[0]["mtime_ns"] = 200
    assert fp1 != compute_fingerprint(files)


def test_fingerprint_changes_on_size():
    files = [{"rel_path": "a.py", "size": 10, "mtime_ns": 100}]
    fp1 = compute_fingerprint(files)
    files[0]["size"] = 20
    assert fp1 != compute_fingerprint(files)


def test_fingerprint_changes_on_new_file():
    f1 = [{"rel_path": "a.py", "size": 10, "mtime_ns": 100}]
    f2 = [
        {"rel_path": "a.py", "size": 10, "mtime_ns": 100},
        {"rel_path": "b.py", "size": 20, "mtime_ns": 200},
    ]
    assert compute_fingerprint(f1) != compute_fingerprint(f2)


def test_is_stale_no_meta(tmp_path):
    f = tmp_path / "a.py"
    f.write_text("x\n", encoding="utf-8")
    assert is_stale_from_files(str(tmp_path), [(str(f), ".py")]) is None


def test_is_stale_not_stale(tmp_path):
    f = tmp_path / "a.py"
    f.write_text("x\n", encoding="utf-8")
    st = f.stat()
    save_report_meta(
        str(tmp_path),
        [{"rel_path": "a.py", "size": st.st_size, "mtime_ns": st.st_mtime_ns}],
        str(tmp_path / "out.txt"),
    )
    result = is_stale_from_files(str(tmp_path), [(str(f), ".py")])
    assert result is False


def test_is_stale_mtime_changed(tmp_path):
    f = tmp_path / "a.py"
    f.write_text("x\n", encoding="utf-8")
    st = f.stat()
    save_report_meta(
        str(tmp_path),
        [{"rel_path": "a.py", "size": st.st_size, "mtime_ns": st.st_mtime_ns}],
        str(tmp_path / "out.txt"),
    )
    os.utime(f, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000))
    result = is_stale_from_files(str(tmp_path), [(str(f), ".py")])
    assert result is True


def test_is_stale_new_file(tmp_path):
    f = tmp_path / "a.py"
    f.write_text("x\n", encoding="utf-8")
    st = f.stat()
    save_report_meta(
        str(tmp_path),
        [{"rel_path": "a.py", "size": st.st_size, "mtime_ns": st.st_mtime_ns}],
        str(tmp_path / "out.txt"),
    )
    g = tmp_path / "b.py"
    g.write_text("y\n", encoding="utf-8")
    result = is_stale_from_files(str(tmp_path), [(str(f), ".py"), (str(g), ".py")])
    assert result is True
