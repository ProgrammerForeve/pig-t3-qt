"""TDD: ProjectScanner — mock subprocess (radon/pylint/vulture/bandit)."""

from __future__ import annotations

import json
import subprocess

import pytest

from PIG_T3.core.quality.scanner import ProjectScanner


@pytest.fixture
def project(tmp_path):
    (tmp_path / "a.py").write_text("def f():\n    if True:\n        return 1\n    return 0\n")
    (tmp_path / "b.py").write_text("x = 1\n")
    return tmp_path


def _fake_check_output_factory(radon_cc=None, radon_mi=None, pylint=None, bandit=None):
    """Возвращает функцию-замену subprocess.check_output по аргументам cmd."""

    def _run(cmd, **kw):
        flat = " ".join(cmd) if isinstance(cmd, list) else str(cmd)
        if "radon" in flat and "cc" in flat:
            return json.dumps(radon_cc or {})
        if "radon" in flat and "mi" in flat:
            return json.dumps(radon_mi or {})
        raise AssertionError(f"unexpected check_output: {flat}")

    return _run


def _fake_run_factory(pylint_issues=None, vulture_out="", bandit_data=None):
    class _Res:
        def __init__(self, stdout=""):
            self.stdout = stdout
            self.returncode = 0

    def _run(cmd, **kw):
        flat = " ".join(cmd) if isinstance(cmd, list) else str(cmd)
        if "pylint" in flat:
            return _Res(json.dumps(pylint_issues or []))
        if "vulture" in flat:
            return _Res(vulture_out)
        if "bandit" in flat:
            return _Res(json.dumps(bandit_data or {"results": []}))
        return _Res("")

    return _run


def test_scan_finds_python_files(monkeypatch, project):
    monkeypatch.setattr(subprocess, "check_output", _fake_check_output_factory())
    monkeypatch.setattr(subprocess, "run", _fake_run_factory())
    scanner = ProjectScanner(str(project))
    metrics = scanner.scan()
    assert len(metrics) == 2
    paths = {m.path for m in metrics}
    assert "a.py" in paths
    assert "b.py" in paths


def test_scan_radon_cc(monkeypatch, project):
    a_abs = str(project / "a.py")
    b_abs = str(project / "b.py")
    cc = {
        a_abs: [{"complexity": 3}, {"complexity": 5}],
        b_abs: [],
    }
    monkeypatch.setattr(subprocess, "check_output", _fake_check_output_factory(radon_cc=cc))
    monkeypatch.setattr(subprocess, "run", _fake_run_factory())
    metrics = ProjectScanner(str(project)).scan()
    a = next(m for m in metrics if m.path == "a.py")
    assert a.complexity == 4.0  # (3+5)/2
    b = next(m for m in metrics if m.path == "b.py")
    assert b.complexity == 1.0  # empty → default


def test_scan_radon_mi(monkeypatch, project):
    a_abs = str(project / "a.py")
    mi = {a_abs: {"mi": 72.5}}
    monkeypatch.setattr(subprocess, "check_output", _fake_check_output_factory(radon_mi=mi))
    monkeypatch.setattr(subprocess, "run", _fake_run_factory())
    metrics = ProjectScanner(str(project)).scan()
    a = next(m for m in metrics if m.path == "a.py")
    assert a.maintainability == 72.5


def test_scan_pylint_issues(monkeypatch, project):
    a_abs = str(project / "a.py")
    issues = [
        {"path": a_abs, "type": "warning", "message-id": "W0611", "message": "unused import", "line": 1},
        {"path": a_abs, "type": "error", "message-id": "E0001", "message": "syntax error", "line": 2},
    ]
    monkeypatch.setattr(subprocess, "check_output", _fake_check_output_factory())
    monkeypatch.setattr(subprocess, "run", _fake_run_factory(pylint_issues=issues))
    metrics = ProjectScanner(str(project)).scan()
    a = next(m for m in metrics if m.path == "a.py")
    assert len(a.issues) == 2
    assert a.pylint_score < 10.0


def test_scan_bandit_security(monkeypatch, project):
    a_abs = str(project / "a.py")
    bandit = {
        "results": [
            {"filename": a_abs, "issue_severity": "HIGH", "issue_text": "hardcoded password", "line_number": 5},
            {"filename": a_abs, "issue_severity": "MEDIUM", "issue_text": "sql injection", "line_number": 10},
        ]
    }
    monkeypatch.setattr(subprocess, "check_output", _fake_check_output_factory())
    monkeypatch.setattr(subprocess, "run", _fake_run_factory(bandit_data=bandit))
    metrics = ProjectScanner(str(project)).scan()
    a = next(m for m in metrics if m.path == "a.py")
    assert a.security_issues == 2
    assert a.status_security == "red"


def test_scan_progress_callback(monkeypatch, project):
    monkeypatch.setattr(subprocess, "check_output", _fake_check_output_factory())
    monkeypatch.setattr(subprocess, "run", _fake_run_factory())
    events: list[tuple[int, str]] = []
    ProjectScanner(str(project)).scan(progress_callback=lambda p, m: events.append((p, m)))
    assert events
    assert events[-1][0] == 100


def test_scan_no_python_files(monkeypatch, tmp_path):
    monkeypatch.setattr(subprocess, "check_output", _fake_check_output_factory())
    monkeypatch.setattr(subprocess, "run", _fake_run_factory())
    metrics = ProjectScanner(str(tmp_path)).scan()
    assert metrics == []
