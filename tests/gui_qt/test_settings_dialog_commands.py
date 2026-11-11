"""C6b: SettingsDialog — группа «Выполнение команд»."""

from PIG_T3.gui_qt.dialogs.settings_dialog import SettingsDialog


def _settings(**overrides):
    base = {
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
        "auto_refresh_tree": True,
        "allow_command_execution": False,
        "command_confirm_in_editor": True,
        "command_default_timeout": 120,
        "command_whitelist": "",
    }
    base.update(overrides)
    return base


def test_cmd_widgets_exist(qtbot):
    dlg = SettingsDialog(_settings())
    qtbot.addWidget(dlg)
    assert hasattr(dlg, "allow_cmd_cb")
    assert hasattr(dlg, "confirm_cmd_cb")
    assert hasattr(dlg, "cmd_timeout_spin")
    assert hasattr(dlg, "cmd_whitelist_edit")


def test_cmd_populate(qtbot):
    dlg = SettingsDialog(
        _settings(
            allow_command_execution=True,
            command_confirm_in_editor=False,
            command_default_timeout=200,
            command_whitelist="pytest,ruff",
        )
    )
    qtbot.addWidget(dlg)
    assert dlg.allow_cmd_cb.isChecked() is True
    assert dlg.confirm_cmd_cb.isChecked() is False
    assert dlg.cmd_timeout_spin.value() == 200
    assert dlg.cmd_whitelist_edit.text() == "pytest,ruff"


def test_cmd_save(qtbot):
    dlg = SettingsDialog(_settings())
    qtbot.addWidget(dlg)
    dlg.allow_cmd_cb.setChecked(True)
    dlg.cmd_whitelist_edit.setText("git")
    dlg.cmd_timeout_spin.setValue(60)
    dlg._on_save()
    out = dlg.get_updated_settings()
    assert out["allow_command_execution"] is True
    assert out["command_whitelist"] == "git"
    assert out["command_default_timeout"] == 60
