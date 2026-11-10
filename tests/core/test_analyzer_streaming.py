"""Day 7: streaming process — memory-safe, same output, cancel removes file."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from PIG_T3.core.analyzer import ProjectAnalyzer


@pytest.fixture
def project(tmp_path):
    (tmp_path / "a.py").write_text("print(1)\n")
    (tmp_path / "b.py").write_text("x = 2\n" * 50)  # 50 lines
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "c.md").write_text("# hi\n")
    return tmp_path


def _cfg(root, **overrides):
    base = {
        "root_folder": str(root),
        "extensions": ".py, .md",
        "ignore_list": "",
        "output_name": "ctx",
        "strict_mode": False,
        "ignore_self": False,
    }
    base.update(overrides)
    return base


def test_streaming_creates_report(project):
    analyzer = ProjectAnalyzer()
    result = analyzer.process(_cfg(project))
    assert result is not None
    path, count, lines, chars = result
    assert os.path.exists(path)
    content = Path(path).read_text(encoding="utf-8")
    assert "PROJECT CONTEXT REPORT" in content
    assert '<file path="a.py">' in content
    assert '<file path="sub/c.md">' in content
    assert count == 3
    assert lines > 0
    assert chars > 0


def test_streaming_total_lines_correct(project):
    analyzer = ProjectAnalyzer()
    _, _count, lines, _chars = analyzer.process(_cfg(project))
    # a.py: 1 line; b.py: 50 lines; c.md: 1 line → 52
    assert lines == 52


def test_streaming_content_per_file(project):
    analyzer = ProjectAnalyzer()
    path, *_ = analyzer.process(_cfg(project))
    content = Path(path).read_text(encoding="utf-8")
    # Каждый файл ровно один раз в <file>...</file>
    assert content.count('<file path="a.py">') == 1
    assert content.count('<file path="b.py">') == 1
    assert content.count('<file path="sub/c.md">') == 1


def test_streaming_cancel_during_phase1(project):
    """Отмена до Phase 2 — файл не создаётся, результат None."""
    analyzer = ProjectAnalyzer()
    calls = {"n": 0}

    def cancel():
        calls["n"] += 1
        return True  # сразу

    result = analyzer.process(_cfg(project), cancel_callback=cancel)
    assert result is None
    assert not (project / "ctx.txt").exists()


def test_streaming_cancel_during_phase2_removes_file(project):
    """Отмена в середине записи — частичный файл удалён."""
    analyzer = ProjectAnalyzer()
    # Отменяем после начала Phase 2: пропускаем ~первый файл
    state = {"phase2_started": False, "n": 0}

    # Патчим open в second phase — сложно; проще сделать cancel, который
    # возвращает True после N вызовов, где N больше phase1 count
    phase1_count = len(analyzer.scan_directory(_cfg(project))[0])

    def cancel():
        state["n"] += 1
        return state["n"] > phase1_count  # True после Phase 1

    result = analyzer.process(_cfg(project), cancel_callback=cancel)
    # Phase 2 прервалась — файл удалён
    assert result is None
    assert not (project / "ctx.txt").exists()


def test_streaming_file_deleted_between_phases(project):
    """Файл удалён между Phase 1 и Phase 2 — отчёт создан, файл пропущен."""
    analyzer = ProjectAnalyzer()
    # Удаляем файл после первой progress-нотификации до конца
    state = {"deleted": False}

    def on_progress(current, total):
        if current == total and not state["deleted"]:
            (project / "sub" / "c.md").unlink()
            state["deleted"] = True

    result = analyzer.process(_cfg(project), progress_callback=on_progress)
    assert result is not None
    path, _count, _lines, _chars = result
    content = Path(path).read_text(encoding="utf-8")
    # c.md в структуре есть (Phase 1), но контента нет (Phase 2 read fails)
    assert "c.md" in content
    # count остаётся из Phase 1 — 3 файла было обнаружено


def test_streaming_progress_called(project):
    analyzer = ProjectAnalyzer()
    events: list[tuple[int, int]] = []
    analyzer.process(_cfg(project), progress_callback=lambda c, t: events.append((c, t)))
    assert events
    assert events[-1][0] == events[-1][1]  # последний = total


def test_streaming_line_numbers(project):
    analyzer = ProjectAnalyzer()
    path, *_ = analyzer.process(_cfg(project, line_numbers=True))
    content = Path(path).read_text(encoding="utf-8")
    assert "   1 | print(1)" in content


def test_streaming_excluded_paths(project):
    analyzer = ProjectAnalyzer()
    excluded = [str(project / "a.py")]
    path, _count, *_ = analyzer.process(_cfg(project, excluded_paths=excluded))
    content = Path(path).read_text(encoding="utf-8")
    assert "a.py" in content  # в структуре
    assert "print(1)" not in content  # контент не включён


def test_streaming_include_empty(project):
    (project / "empty").mkdir()
    analyzer = ProjectAnalyzer()
    path, *_ = analyzer.process(_cfg(project, include_empty_folders=True))
    content = Path(path).read_text(encoding="utf-8")
    assert "empty" in content
