"""TDD: ProjectAnalyzer — scan_directory / generate_tree / process."""

import pytest

from PIG_T3.core.analyzer import ProjectAnalyzer


@pytest.fixture
def project(tmp_path):
    """Мини-проект: py/json/md + пустая папка + вложенность + ignored."""
    (tmp_path / "main.py").write_text("print(1)\n")
    (tmp_path / "README.md").write_text("# hi\n")
    (tmp_path / "data.json").write_text('{"a": 1}\n')
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "helper.py").write_text("def h():\n    return 1\n")
    (tmp_path / "empty").mkdir()
    (tmp_path / "venv").mkdir()
    (tmp_path / "venv" / "lib.py").write_text("junk\n")
    return tmp_path


def _cfg(root, **overrides):
    base = {
        "root_folder": str(root),
        "extensions": ".py, .md",
        "ignore_list": "venv, .git",
        "output_name": "ctx",
        "strict_mode": False,
        "ignore_self": False,
    }
    base.update(overrides)
    return base


# ---------- scan_directory ----------


def test_scan_finds_matching_files(project):
    analyzer = ProjectAnalyzer()
    files, _empty = analyzer.scan_directory(_cfg(project))
    rels = {f.replace(str(project) + "/", "") for f, _ in files}
    assert rels == {"main.py", "README.md", "sub/helper.py"}


def test_scan_respects_ignore_list(project):
    analyzer = ProjectAnalyzer()
    files, _ = analyzer.scan_directory(_cfg(project))
    for full, _ in files:
        assert "venv" not in full


def test_scan_reports_empty_dirs(project):
    analyzer = ProjectAnalyzer()
    _files, empty = analyzer.scan_directory(_cfg(project))
    assert "empty" in empty


def test_scan_strict_mode_skips_double_ext(project):
    (project / "test.main.py").write_text("x\n")
    analyzer = ProjectAnalyzer()

    normal, _ = analyzer.scan_directory(_cfg(project, strict_mode=False))
    assert any("test.main.py" in f for f, _ in normal)

    strict, _ = analyzer.scan_directory(_cfg(project, strict_mode=True))
    assert not any("test.main.py" in f for f, _ in strict)


def test_scan_missing_root_returns_empty(tmp_path):
    analyzer = ProjectAnalyzer()
    files, empty = analyzer.scan_directory(_cfg(tmp_path / "does_not_exist"))
    assert files == []
    assert empty == []


def test_scan_ignore_self_skips_output(project):
    # Имитируем уже существующий project_context.txt в корне
    (project / "ctx.txt").write_text("old\n")
    analyzer = ProjectAnalyzer()
    files, _ = analyzer.scan_directory(_cfg(project, extensions=".py, .txt", ignore_self=True))
    rels = {f.replace(str(project) + "/", "") for f, _ in files}
    assert "ctx.txt" not in rels


# ---------- generate_tree ----------


def test_generate_tree_sorts_and_connects():
    analyzer = ProjectAnalyzer()
    tree = analyzer.generate_tree(["b.py", "a/x.py", "a/y.py"])
    assert "├── a" in tree or "└── a" in tree
    assert "b.py" in tree
    assert "x.py" in tree


def test_generate_tree_empty():
    analyzer = ProjectAnalyzer()
    assert analyzer.generate_tree([]) == ""


# ---------- process ----------


def test_process_writes_report(project):
    analyzer = ProjectAnalyzer()
    out = analyzer.process(_cfg(project))
    _path, count, lines, chars = out
    assert (project / "ctx.txt").exists()
    content = (project / "ctx.txt").read_text()
    assert "PROJECT CONTEXT REPORT" in content
    assert '<file path="main.py">' in content
    assert "print(1)" in content
    assert count == 3
    assert lines > 0
    assert chars > 0


def test_process_with_line_numbers(project):
    analyzer = ProjectAnalyzer()
    analyzer.process(_cfg(project, line_numbers=True))
    content = (project / "ctx.txt").read_text()
    assert "   1 | print(1)" in content


def test_process_excluded_paths_skips_content(project):
    analyzer = ProjectAnalyzer()
    excluded = [str(project / "main.py")]
    analyzer.process(_cfg(project, excluded_paths=excluded))
    content = (project / "ctx.txt").read_text()
    # main.py должен быть в структуре, но без содержимого
    assert "main.py" in content
    assert "print(1)" not in content


def test_process_include_empty_folders(project):
    analyzer = ProjectAnalyzer()
    analyzer.process(_cfg(project, include_empty_folders=True))
    content = (project / "ctx.txt").read_text()
    assert "empty" in content
