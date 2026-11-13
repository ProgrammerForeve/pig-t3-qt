"""Tests for user config dir + legacy migration (Stage 1)."""

from __future__ import annotations

import json
import os
import sys

import pytest


@pytest.mark.skipif(sys.platform == "win32", reason="XDG on POSIX")
def test_user_config_dir_xdg(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    from PIG_T3.config import _user_config_dir

    assert _user_config_dir() == os.path.join(str(tmp_path), "pig-t3")


def test_config_migrate_from_legacy(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    legacy = tmp_path / "legacy_app_config.json"
    legacy.write_text('{"theme": "light", "custom": 1}', encoding="utf-8")
    monkeypatch.setattr("PIG_T3.config._legacy_config_file", lambda: str(legacy))
    from PIG_T3.config import ConfigManager

    cfg = ConfigManager()
    assert os.path.exists(cfg.config_file)
    with open(cfg.config_file, encoding="utf-8") as f:
        data = json.load(f)
    assert data["theme"] == "light"
    assert data["custom"] == 1


def test_config_no_migrate_when_new_exists(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    new_dir = tmp_path / "xdg" / "pig-t3"
    new_dir.mkdir(parents=True)
    (new_dir / "app_config.json").write_text('{"theme": "dark"}', encoding="utf-8")
    legacy = tmp_path / "legacy.json"
    legacy.write_text('{"theme": "light"}', encoding="utf-8")
    monkeypatch.setattr("PIG_T3.config._legacy_config_file", lambda: str(legacy))
    from PIG_T3.config import ConfigManager

    cfg = ConfigManager()
    with open(cfg.config_file, encoding="utf-8") as f:
        data = json.load(f)
    assert data["theme"] == "dark"
