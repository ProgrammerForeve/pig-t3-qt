import io

from PIG_T3.core.analyzer import ProjectAnalyzer


def test_prompt_has_flow_control():
    buf = io.StringIO()
    ProjectAnalyzer()._write_patching_instructions(buf)
    text = buf.getvalue()
    assert "FLOW CONTROL" in text
    assert "depends_on" in text
    assert "on_success" in text
    assert "rollback" in text


def test_prompt_has_retry_with_context():
    buf = io.StringIO()
    ProjectAnalyzer()._write_patching_instructions(buf)
    text = buf.getvalue()
    assert "retry_with_context" in text
    assert "read_lines" in text
