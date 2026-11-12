"""Tests for custom_system_prompt embedded in analyzer output."""

from __future__ import annotations

from PIG_T3.core.analyzer import ProjectAnalyzer


def _make_project(tmp_path):
    (tmp_path / "main.py").write_text("print(1)\n")
    return tmp_path


def _cfg(root, **overrides):
    base = {
        "root_folder": str(root),
        "extensions": ".py",
        "ignore_list": "",
        "output_name": "ctx",
        "strict_mode": False,
        "ignore_self": False,
        "add_edit_prompt": True,
    }
    base.update(overrides)
    return base


def test_custom_prompt_appears_in_report(tmp_path):
    root = _make_project(tmp_path)
    cfg = _cfg(root, custom_system_prompt="ALWAYS write russian comments")
    _path, *_ = ProjectAnalyzer().process(cfg)
    content = (root / "ctx.txt").read_text(encoding="utf-8")
    assert "USER SYSTEM PROMPT" in content
    assert "ALWAYS write russian comments" in content


def test_custom_prompt_absent_when_empty(tmp_path):
    root = _make_project(tmp_path)
    cfg = _cfg(root, custom_system_prompt="")
    ProjectAnalyzer().process(cfg)
    content = (root / "ctx.txt").read_text(encoding="utf-8")
    assert "USER SYSTEM PROMPT" not in content
