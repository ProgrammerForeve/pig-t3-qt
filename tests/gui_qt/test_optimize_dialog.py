"""TDD: OptimizeDialog (T-109)."""

import pytest
from PySide6.QtWidgets import QDialog

from PIG_T3.gui_qt.dialogs import optimize_dialog as od_module
from PIG_T3.gui_qt.dialogs.optimize_dialog import OptimizeDialog


@pytest.fixture(autouse=True)
def _no_ollama(monkeypatch):
    """Не дёргаем Ollama в тестах диалога — заглушка _default_models."""
    from PIG_T3.gui_qt.dialogs import optimize_dialog as od_module

    monkeypatch.setattr(od_module, "_default_models", lambda: ["None", "BomjAPI"])


MODELS = ["None", "BomjAPI", "Web: Gemini", "qwen2.5-coder"]


@pytest.fixture
def base_settings():
    return {
        "opt_default_model": "Web: Gemini",
        "opt_compression_pct": 40,
        "opt_bfs_depth": 3,
    }


def test_init_from_settings(qtbot, base_settings):
    dlg = OptimizeDialog(base_settings, total_tokens=10_000, models=MODELS)
    qtbot.addWidget(dlg)
    assert dlg.pct_slider.value() == 40
    assert dlg.depth_spin.value() == 3
    assert dlg.model_combo.currentText() == "Web: Gemini"


def test_unknown_model_falls_back_to_first(qtbot):
    settings = {"opt_default_model": "ghost", "opt_compression_pct": 50}
    dlg = OptimizeDialog(settings, total_tokens=1000, models=MODELS)
    qtbot.addWidget(dlg)
    assert dlg.model_combo.currentText() == "None"


def test_pct_slider_updates_estimate(qtbot, base_settings):
    dlg = OptimizeDialog(base_settings, total_tokens=10_000, models=MODELS)
    qtbot.addWidget(dlg)
    dlg.pct_slider.setValue(25)
    assert dlg.pct_value_label.text() == "25%"
    assert "~2500" in dlg.estimate_label.text()
    assert "10000" in dlg.estimate_label.text()


def test_ok_saves_settings_and_accepts(qtbot, base_settings):
    dlg = OptimizeDialog(base_settings, total_tokens=10_000, models=MODELS)
    qtbot.addWidget(dlg)
    dlg.task_edit.setPlainText("add CSV export")
    dlg.pct_slider.setValue(60)
    dlg.depth_spin.setValue(2)
    dlg.model_combo.setCurrentText("qwen2.5-coder")

    dlg._on_start()

    assert dlg.result() == QDialog.DialogCode.Accepted
    saved = dlg.get_updated_settings()
    assert saved["opt_compression_pct"] == 60
    assert saved["opt_bfs_depth"] == 2
    assert saved["opt_default_model"] == "qwen2.5-coder"


def test_empty_task_warns_and_stays_open(qtbot, base_settings, monkeypatch):
    warnings: list[str] = []
    monkeypatch.setattr(
        od_module,
        "_show_warning_dialog",
        lambda parent, title, text: warnings.append(text),
    )
    dlg = OptimizeDialog(base_settings, total_tokens=1000, models=MODELS)
    qtbot.addWidget(dlg)
    dlg.task_edit.setPlainText("   ")
    dlg._on_start()

    assert warnings, "warning dialog не показан"
    assert dlg.result() != QDialog.DialogCode.Accepted


def test_cancel_keeps_original_settings(qtbot, base_settings):
    dlg = OptimizeDialog(base_settings, total_tokens=1000, models=MODELS)
    qtbot.addWidget(dlg)
    dlg.pct_slider.setValue(90)
    dlg.reject()

    saved = dlg.get_updated_settings()
    # reject не вызывает _on_start, settings не тронуты
    assert saved["opt_compression_pct"] == 40


def test_get_limit_tokens(qtbot, base_settings):
    dlg = OptimizeDialog(base_settings, total_tokens=10_000, models=MODELS)
    qtbot.addWidget(dlg)
    dlg.pct_slider.setValue(30)
    assert dlg.get_limit_tokens() == 3000
