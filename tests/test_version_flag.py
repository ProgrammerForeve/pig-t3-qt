"""D1: --version / -V флаг в main()."""

import sys

from PIG_T3 import main as main_module


def test_version_flag(capsys, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["pig-t3", "--version"])
    main_module.main()
    captured = capsys.readouterr()
    assert "PIG-T3" in captured.out


def test_version_short_flag(capsys, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["pig-t3", "-V"])
    main_module.main()
    captured = capsys.readouterr()
    assert "PIG-T3" in captured.out


def test_get_version_returns_string():
    v = main_module._get_version()
    assert isinstance(v, str)
    assert v  # не пустая
