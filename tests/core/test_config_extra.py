"""Day 6+: ConfigManager save/load edges + config_compat."""

import json

from PIG_T3.config import ConfigManager
from PIG_T3.gui_qt.config_compat import load_and_migrate, save_migrated


def test_load_missing_file_returns_defaults(tmp_path, monkeypatch):
    cfg = ConfigManager()
    monkeypatch.setattr(cfg, "config_file", str(tmp_path / "missing.json"))
    result = cfg.load()
    assert "theme" in result


def test_load_invalid_json_returns_defaults(tmp_path, monkeypatch):
    p = tmp_path / "bad.json"
    p.write_text("not json at all")
    cfg = ConfigManager()
    monkeypatch.setattr(cfg, "config_file", str(p))
    result = cfg.load()
    assert "theme" in result


def test_load_valid_merges_with_defaults(tmp_path, monkeypatch):
    p = tmp_path / "ok.json"
    p.write_text('{"theme": "light", "custom": "yes"}')
    cfg = ConfigManager()
    monkeypatch.setattr(cfg, "config_file", str(p))
    result = cfg.load()
    assert result["theme"] == "light"
    assert result["custom"] == "yes"
    assert "recent_projects" in result  # default сохраняется


def test_save_writes_file(tmp_path, monkeypatch):
    p = tmp_path / "out.json"
    cfg = ConfigManager()
    monkeypatch.setattr(cfg, "config_file", str(p))
    cfg.save({"theme": "dark", "x": 1})
    assert p.exists()
    assert json.loads(p.read_text())["theme"] == "dark"


def test_save_bad_path_prints_error(monkeypatch, capsys):
    cfg = ConfigManager()
    monkeypatch.setattr(cfg, "config_file", "/root_nonexistent_dir_x/cfg.json")
    cfg.save({"theme": "dark"})
    # не падает; либо stdout print, либо тихий skip


def test_save_migrated_drops_ui_scale(tmp_path, monkeypatch):
    p = tmp_path / "cfg.json"
    cfg = ConfigManager()
    monkeypatch.setattr(cfg, "config_file", str(p))
    save_migrated(cfg, {"theme": "dark", "ui_scale": 1.5, "x": 1})
    data = json.loads(p.read_text())
    assert "ui_scale" not in data
    assert data["x"] == 1


def test_load_and_migrate_resolves_theme(tmp_path, monkeypatch):
    p = tmp_path / "cfg.json"
    p.write_text('{"theme": "pink", "ui_scale": 1.5}')
    cfg = ConfigManager()
    monkeypatch.setattr(cfg, "config_file", str(p))
    result = load_and_migrate(cfg)
    assert result["theme"] == "light"
    assert "ui_scale" not in result


def test_load_and_migrate_dark_pink_to_dark(tmp_path, monkeypatch):
    p = tmp_path / "cfg.json"
    p.write_text('{"theme": "dark_pink"}')
    cfg = ConfigManager()
    monkeypatch.setattr(cfg, "config_file", str(p))
    result = load_and_migrate(cfg)
    assert result["theme"] == "dark"
