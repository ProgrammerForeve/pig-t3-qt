"""Day 8: OptimizeDialog — async Ollama models + cache freshness."""

import time

from PIG_T3.gui_qt.dialogs.optimize_dialog import OptimizeDialog


def _settings():
    return {
        "opt_default_model": "BomjAPI",
        "opt_compression_pct": 50,
        "opt_bfs_depth": 2,
    }


def test_auto_fetch_disabled(qtbot, monkeypatch):
    """auto_fetch_models=False → воркер не стартует."""
    called: list[int] = []
    monkeypatch.setattr(OptimizeDialog, "_fetch_models_async", lambda self: called.append(1))
    dlg = OptimizeDialog(_settings(), total_tokens=1000, auto_fetch_models=False)
    qtbot.addWidget(dlg)
    assert not called


def test_auto_fetch_skipped_when_cache_fresh(qtbot, monkeypatch):
    called: list[int] = []
    monkeypatch.setattr(OptimizeDialog, "_fetch_models_async", lambda self: called.append(1))
    settings = _settings()
    settings["ollama_models_cache"] = {"models": ["qwen2.5"], "ts": time.time()}
    dlg = OptimizeDialog(settings, total_tokens=1000, auto_fetch_models=True)
    qtbot.addWidget(dlg)
    assert not called
    # qwen2.5 в combo
    items = [dlg.model_combo.itemText(i) for i in range(dlg.model_combo.count())]
    assert "qwen2.5" in items


def test_auto_fetch_runs_when_cache_stale(qtbot, monkeypatch):
    called: list[int] = []
    monkeypatch.setattr(OptimizeDialog, "_fetch_models_async", lambda self: called.append(1))
    settings = _settings()
    settings["ollama_models_cache"] = {"models": [], "ts": time.time() - 120}
    dlg = OptimizeDialog(settings, total_tokens=1000, auto_fetch_models=True)
    qtbot.addWidget(dlg)
    assert called


def test_on_models_fetched_updates_combo(qtbot):
    dlg = OptimizeDialog(_settings(), total_tokens=1000, auto_fetch_models=False)
    qtbot.addWidget(dlg)
    dlg._on_models_fetched(["qwen2.5", "llama3"])
    items = [dlg.model_combo.itemText(i) for i in range(dlg.model_combo.count())]
    assert "qwen2.5" in items
    assert "llama3" in items
    # cache обновлён
    assert dlg.settings.get("ollama_models_cache", {}).get("models") == [
        "qwen2.5",
        "llama3",
    ]


def test_on_models_fetched_keeps_current(qtbot):
    dlg = OptimizeDialog(_settings(), total_tokens=1000, auto_fetch_models=False)
    qtbot.addWidget(dlg)
    dlg.model_combo.setCurrentText("BomjAPI")
    dlg._on_models_fetched(["qwen2.5"])
    assert dlg.model_combo.currentText() == "BomjAPI"


def test_on_models_fetched_no_duplicates(qtbot):
    dlg = OptimizeDialog(_settings(), total_tokens=1000, auto_fetch_models=False)
    qtbot.addWidget(dlg)
    dlg._on_models_fetched(["BomjAPI", "BomjAPI"])
    count = sum(1 for i in range(dlg.model_combo.count()) if dlg.model_combo.itemText(i) == "BomjAPI")
    assert count == 1
