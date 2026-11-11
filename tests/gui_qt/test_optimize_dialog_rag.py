"""C4b: чекбокс «Использовать RAG» в OptimizeDialog."""

import time

from PySide6.QtWidgets import QDialog

from PIG_T3.gui_qt.dialogs.optimize_dialog import OptimizeDialog

MODELS = ["None", "BomjAPI", "Web: Gemini"]


def _settings(**overrides):
    base = {
        "opt_default_model": "BomjAPI",
        "opt_compression_pct": 50,
        "opt_bfs_depth": 2,
        "opt_use_rag": False,
        "ollama_models_cache": {"models": [], "ts": time.time()},
    }
    base.update(overrides)
    return base


def test_rag_checkbox_exists(qtbot):
    dlg = OptimizeDialog(_settings(), total_tokens=1000, models=MODELS)
    qtbot.addWidget(dlg)
    assert hasattr(dlg, "cb_use_rag")
    assert "RAG" in dlg.cb_use_rag.text()


def test_rag_default_off(qtbot):
    dlg = OptimizeDialog(_settings(opt_use_rag=False), total_tokens=1000, models=MODELS)
    qtbot.addWidget(dlg)
    assert dlg.cb_use_rag.isChecked() is False


def test_rag_default_on_from_settings(qtbot):
    dlg = OptimizeDialog(_settings(opt_use_rag=True), total_tokens=1000, models=MODELS)
    qtbot.addWidget(dlg)
    assert dlg.cb_use_rag.isChecked() is True


def test_rag_toggle_saves_to_settings(qtbot):
    dlg = OptimizeDialog(_settings(opt_use_rag=False), total_tokens=1000, models=MODELS)
    qtbot.addWidget(dlg)
    dlg.task_edit.setPlainText("demo")
    dlg.cb_use_rag.setChecked(True)
    dlg._on_start()
    assert dlg.result() == QDialog.DialogCode.Accepted
    assert dlg.get_updated_settings()["opt_use_rag"] is True
