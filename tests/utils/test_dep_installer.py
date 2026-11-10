"""TDD: DependencyInstaller — mock importlib + subprocess."""

from __future__ import annotations

import subprocess

from PIG_T3.utils.dep_installer import REQUIRED_TOOLS, DependencyInstaller


def _fake_find_spec(installed: set[str]):
    def _find_spec(name):
        return object() if name in installed else None

    return _find_spec


def test_all_installed_no_pip_call(monkeypatch):
    monkeypatch.setattr("importlib.util.find_spec", _fake_find_spec(set(REQUIRED_TOOLS)))
    calls: list[list[str]] = []
    monkeypatch.setattr(subprocess, "check_call", lambda cmd, **kw: calls.append(cmd))
    assert DependencyInstaller.check_and_install() is True
    assert calls == []


def test_missing_installs_via_pip(monkeypatch):
    monkeypatch.setattr("importlib.util.find_spec", _fake_find_spec({"radon", "pylint"}))
    calls: list[list[str]] = []
    monkeypatch.setattr(subprocess, "check_call", lambda cmd, **kw: calls.append(cmd))
    assert DependencyInstaller.check_and_install() is True
    assert len(calls) == 1
    cmd = calls[0]
    assert "-m" in cmd and "pip" in cmd and "install" in cmd
    assert "bandit" in cmd
    assert "vulture" in cmd
    assert "networkx" in cmd


def test_callback_receives_status(monkeypatch):
    monkeypatch.setattr("importlib.util.find_spec", _fake_find_spec(set()))
    monkeypatch.setattr(subprocess, "check_call", lambda *a, **kw: None)
    messages: list[str] = []
    DependencyInstaller.check_and_install(callback=messages.append)
    assert messages
    assert "Установка" in messages[0]


def test_pip_failure_returns_false(monkeypatch):
    monkeypatch.setattr("importlib.util.find_spec", _fake_find_spec(set()))

    def _fail(cmd, **kw):
        raise subprocess.CalledProcessError(1, cmd)

    monkeypatch.setattr(subprocess, "check_call", _fail)
    messages: list[str] = []
    assert DependencyInstaller.check_and_install(callback=messages.append) is False
    assert any("Ошибка" in m for m in messages)
