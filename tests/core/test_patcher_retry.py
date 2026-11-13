"""ADR-016: retry_with_context + read_lines через patch_context."""

from __future__ import annotations

import json

from PIG_T3.core.patcher import FailedEdit, apply_llm_changes


def _run(actions, root, **kw):
    return apply_llm_changes(json.dumps(actions), str(root), **kw)


# ---------- retry_with_context ----------


def test_failed_edit_populated(tmp_path):
    (tmp_path / "a.py").write_text("def foo(a, b):\n    return a + b\n")
    ctx: dict = {}
    _run(
        [
            {
                "action": "edit",
                "path": "a.py",
                "on_failure": "retry_with_context",
                "operations": [
                    {
                        "type": "replace_text",
                        "find": "def foo(a, c):\n    return a + b",
                        "replace": "def foo(a, b):\n    return a + b * 2",
                    }
                ],
            }
        ],
        tmp_path,
        patch_context=ctx,
    )
    assert ctx["needs_retry"] is True
    assert len(ctx["failed_edits"]) == 1
    fe = ctx["failed_edits"][0]
    assert isinstance(fe, FailedEdit)
    assert fe.path == "a.py"
    assert fe.best_match_line is not None
    assert fe.best_match_ratio > 0.6
    assert any("L1" in ln for ln in fe.context_lines)


def test_failed_edit_no_match_below_threshold(tmp_path):
    (tmp_path / "a.py").write_text("def foo(a, b):\n    return a + b\n")
    ctx: dict = {}
    _run(
        [
            {
                "action": "edit",
                "path": "a.py",
                "on_failure": "retry_with_context",
                "operations": [
                    {
                        "type": "replace_text",
                        "find": "completely different content here xxx",
                        "replace": "x",
                    }
                ],
            }
        ],
        tmp_path,
        patch_context=ctx,
    )
    assert ctx["failed_edits"] == []
    assert ctx["needs_retry"] is False


def test_no_retry_by_default(tmp_path):
    (tmp_path / "a.py").write_text("hello world\n")
    ctx: dict = {}
    _run(
        [
            {
                "action": "edit",
                "path": "a.py",
                "operations": [
                    {
                        "type": "replace_text",
                        "find": "NOT_FOUND",
                        "replace": "x",
                    }
                ],
            }
        ],
        tmp_path,
        patch_context=ctx,
    )
    assert ctx["failed_edits"] == []


# ---------- read_lines ----------


def test_read_lines_populates(tmp_path):
    (tmp_path / "a.py").write_text("line1\nline2\nline3\nline4\nline5\n")
    ctx: dict = {}
    log = _run(
        [{"action": "read_lines", "path": "a.py", "start": 2, "end": 4}],
        tmp_path,
        patch_context=ctx,
    )
    assert "📖 read_lines" in log
    assert len(ctx["read_requests"]) == 1
    rr = ctx["read_requests"][0]
    assert rr["path"] == "a.py"
    assert rr["start"] == 2
    assert rr["end"] == 4
    assert any("L2" in ln for ln in rr["lines"])


def test_read_lines_range_clamped(tmp_path):
    (tmp_path / "big.py").write_text("\n".join(f"line{i}" for i in range(500)))
    ctx: dict = {}
    _run(
        [{"action": "read_lines", "path": "big.py", "start": 1, "end": 500}],
        tmp_path,
        patch_context=ctx,
    )
    rr = ctx["read_requests"][0]
    assert rr["end"] - rr["start"] == 200


def test_read_lines_outside_root(tmp_path):
    ctx: dict = {}
    log = _run(
        [{"action": "read_lines", "path": "../etc/passwd", "start": 1, "end": 10}],
        tmp_path,
        patch_context=ctx,
    )
    assert "outside root" in log
    assert ctx["read_requests"] == []


def test_read_lines_missing_file(tmp_path):
    ctx: dict = {}
    log = _run(
        [{"action": "read_lines", "path": "nope.py", "start": 1, "end": 5}],
        tmp_path,
        patch_context=ctx,
    )
    assert "не найден" in log
    assert ctx["read_requests"] == []


# ---------- backward compat ----------


def test_without_patch_context_works(tmp_path):
    (tmp_path / "a.py").write_text("line1\nline2\n")
    log = _run(
        [{"action": "read_lines", "path": "a.py", "start": 1, "end": 2}],
        tmp_path,
    )
    assert "📖 read_lines" in log


def test_create_then_read_lines(tmp_path):
    ctx: dict = {}
    log = _run(
        [
            {"action": "create", "path": "b.py", "content": "x\n"},
            {"action": "read_lines", "path": "b.py", "start": 1, "end": 1},
        ],
        tmp_path,
        patch_context=ctx,
    )
    assert "✅ CREATE: b.py" in log
    assert "📖 read_lines" in log
    assert ctx["failed_edits"] == []
    assert len(ctx["read_requests"]) == 1
    assert ctx["applied_count"] == 1
