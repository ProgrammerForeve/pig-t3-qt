"""TDD: SettingsDialog (T-601..T-603)."""

import pytest
from PySide6.QtWidgets import QDialog

from PIG_T3.gui_qt.dialogs.settings_dialog import SettingsDialog


@pytest.fixture
def base_settings():
    return {
        "theme": "dark",
        "font_size": 10,
        "tree_row_height": 22,
        "checkbox_size": 14,
        "opt_chunk_size": 7000,
        "opt_chunk_unit": "tokens",
        "opt_bfs_depth": 2,
        "opt_greedy_llm_weight": 0.6,
        "opt_greedy_pr_weight": 0.3,
        "opt_greedy_cc_weight": 0.1,
        "opt_token_bytes_per_token": 4,
        "tabs_visibility": {
            "generator": True,
            "auto_refresh_tree": True,
            "info": True,
            "editor": True,
            "plan": True,
            "quality": True,
        },
        "git_enabled": False,
        "git_branch_mode": "new",
        "git_auto_push": False,
        "web_api_timeout": 600,
        "web_api_stable_count": 7,
        "plan_step_limit_tokens": 15000,
        "plan_generation_limit_tokens": 12000,
        "quality_scan_chunk_size": 50,
    }


def test_dialog_populates(qtbot, base_settings):
    dlg = SettingsDialog(base_settings)
    qtbot.addWidget(dlg)
    assert dlg.theme_combo.currentText() == "dark"
    assert dlg.font_size_spin.value() == 10
    assert dlg.row_height_spin.value() == 22
    assert dlg.bfs_depth_spin.value() == 2
    assert dlg.vis_checks["generator"].isChecked()


def test_unknown_theme_falls_back_dark(qtbot, base_settings):
    base_settings["theme"] = "pink"
    dlg = SettingsDialog(base_settings)
    qtbot.addWidget(dlg)
    assert dlg.theme_combo.currentText() == "dark"


def test_save_updates_settings(qtbot, base_settings):
    dlg = SettingsDialog(base_settings)
    qtbot.addWidget(dlg)
    dlg.theme_combo.setCurrentText("light")
    dlg.font_size_spin.setValue(14)
    dlg.row_height_spin.setValue(30)
    dlg.vis_checks["quality"].setChecked(False)
    dlg.git_enabled_cb.setChecked(True)
    dlg.llm_timeout_spin.setValue(300)

    dlg._on_save()

    assert dlg.result() == QDialog.DialogCode.Accepted
    saved = dlg.get_updated_settings()
    assert saved["theme"] == "light"
    assert saved["font_size"] == 14
    assert saved["tree_row_height"] == 30
    assert saved["tabs_visibility"]["quality"] is False
    assert saved["git_enabled"] is True
    assert saved["web_api_timeout"] == 300


def test_cancel_keeps_original(qtbot, base_settings):
    dlg = SettingsDialog(base_settings)
    qtbot.addWidget(dlg)
    dlg.font_size_spin.setValue(20)
    dlg.reject()
    saved = dlg.get_updated_settings()
    assert saved["font_size"] == 10


def test_bfs_and_weights_roundtrip(qtbot, base_settings):
    dlg = SettingsDialog(base_settings)
    qtbot.addWidget(dlg)
    dlg.bfs_depth_spin.setValue(4)
    dlg.llm_weight_spin.setValue(0.5)
    dlg.pr_weight_spin.setValue(0.4)
    dlg.cc_weight_spin.setValue(0.1)
    dlg._on_save()
    saved = dlg.get_updated_settings()
    assert saved["opt_bfs_depth"] == 4
    assert saved["opt_greedy_llm_weight"] == 0.5
    assert saved["opt_greedy_pr_weight"] == 0.4
    assert saved["opt_greedy_cc_weight"] == 0.1


def test_auto_refresh_toggle(qtbot, base_settings):
    dlg = SettingsDialog(base_settings)
    qtbot.addWidget(dlg)
    assert dlg.auto_refresh_cb.isChecked() is True
    dlg.auto_refresh_cb.setChecked(False)
    dlg._on_save()
    assert dlg.get_updated_settings()["auto_refresh_tree"] is False
