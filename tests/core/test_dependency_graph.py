"""Tests for DependencyGraph._extract_imports (regex-based)."""

from __future__ import annotations

from PIG_T3.core.dependency_graph import DependencyGraph


def _make():
    # Не вызываем __init__ — _IMPORT_RE class-level, _extract_imports
    # не требует состояния instance.
    return object.__new__(DependencyGraph)


def test_extract_import_simple(tmp_path):
    f = tmp_path / "a.py"
    f.write_text("import os\nimport sys\n")
    imports = _make()._extract_imports(str(f))
    assert "os" in imports
    assert "sys" in imports


def test_extract_from_import(tmp_path):
    f = tmp_path / "a.py"
    f.write_text("from foo.bar import baz\n")
    imports = _make()._extract_imports(str(f))
    assert "foo" in imports


def test_extract_multiple_imports(tmp_path):
    f = tmp_path / "a.py"
    f.write_text("import a, b, c.d\n")
    imports = _make()._extract_imports(str(f))
    assert "a" in imports
    assert "b" in imports
    assert "c" in imports


def test_extract_indented_import(tmp_path):
    f = tmp_path / "a.py"
    f.write_text("def f():\n    import os\n")
    imports = _make()._extract_imports(str(f))
    assert "os" in imports


def test_extract_empty_file(tmp_path):
    f = tmp_path / "a.py"
    f.write_text("")
    imports = _make()._extract_imports(str(f))
    assert imports == []


def test_extract_missing_file():
    imports = _make()._extract_imports("/nonexistent/path/x.py")
    assert imports == []


def test_extract_no_false_positive_in_comment(tmp_path):
    # `# import fake` — regex требует `^[ \t]*import`, `#` не пройдёт
    f = tmp_path / "a.py"
    f.write_text("# import fake\nx = 1\n")
    imports = _make()._extract_imports(str(f))
    assert "fake" not in imports
