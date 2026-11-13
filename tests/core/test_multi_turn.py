"""ADR-016: build_retry_prompt — failed_edits + read_requests + truncation."""

from __future__ import annotations

from PIG_T3.core.multi_turn import _trim_original, build_retry_prompt
from PIG_T3.core.patcher import FailedEdit


def _fe(path="a.py", find="x", error="not found"):
    return FailedEdit(path=path, find=find, replace="y", error=error)


def test_empty_still_has_instructions():
    text = build_retry_prompt([], [], "")
    assert "Твой предыдущий JSON-патч применился частично" in text
    assert "JSON-массив ТОЛЬКО для исправления" in text


def test_failed_edit_included():
    fe = _fe(path="src/a.py", find="def foo():", error="fragment not found")
    text = build_retry_prompt([fe], [], "")
    assert "src/a.py" in text
    assert "def foo():" in text
    assert "fragment not found" in text


def test_best_match_context_included():
    fe = FailedEdit(
        path="a.py",
        find="x",
        replace="y",
        error="not found",
        best_match_line=5,
        best_match_ratio=0.75,
        context_lines=["L4: def foo():", "L5: return 1"],
        total_lines=10,
    )
    text = build_retry_prompt([fe], [], "")
    assert "L5" in text
    assert "0.75" in text
    assert "return 1" in text
    assert "10 строк" in text


def test_read_request_included():
    rr = {
        "path": "b.py",
        "start": 10,
        "end": 20,
        "lines": ["L10: x = 1", "L11: y = 2"],
    }
    text = build_retry_prompt([], [rr], "")
    assert "b.py L10-20" in text
    assert "L10: x = 1" in text


def test_original_response_trimmed_to_4000():
    huge = "[" + ('{"action":"edit","path":"a.py"},' * 2000) + "{}]"
    text = build_retry_prompt([], [], huge)
    assert "оригинальный патч" in text
    assert "... (truncated)" in text
    assert len(text) <= 8100


def test_truncation_when_total_huge():
    fe = _fe()
    rr = {
        "path": "b.py",
        "start": 1,
        "end": 50,
        "lines": [f"L{i}: {'x' * 200}" for i in range(1, 51)],
    }
    original = "[" + ('{"action":"edit"},' * 500) + "{}]"
    text = build_retry_prompt([fe], [rr], original)
    assert len(text) <= 8100
    assert "... (truncated)" in text


def test_trim_original_no_brackets_returns_empty():
    assert _trim_original("no brackets here") == ""


def test_trim_original_extracts_list():
    assert _trim_original("prefix [1, 2, 3] suffix") == "[1, 2, 3]"


def test_trim_original_truncates_huge_list():
    raw = "[" + "x" * 5000 + "]"
    out = _trim_original(raw)
    assert out.startswith("[")
    assert out.endswith("... (truncated)")
    assert len(out) <= 4020
