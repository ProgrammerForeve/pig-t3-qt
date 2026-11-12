"""C7b: SettingsDialog — подгруппа LM Studio."""

from PIG_T3.gui_qt.dialogs.settings_dialog import SettingsDialog


def _base_settings(**overrides):
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
        "lmstudio_base_url": "http://localhost:1234/v1",
        "lmstudio_api_key": "lm-studio",
        "lmstudio_timeout": 600,
        "lmstudio_embeddings_model": "",
    }
    base.update(overrides)
    return base


def test_lmstudio_widgets_exist(qtbot):
    dlg = SettingsDialog(_base_settings())
    qtbot.addWidget(dlg)
    assert hasattr(dlg, "lmstudio_url_edit")
    assert hasattr(dlg, "lmstudio_key_edit")
    assert hasattr(dlg, "lmstudio_timeout_spin")
    assert hasattr(dlg, "lmstudio_embeddings_edit")


def test_lmstudio_populate(qtbot):
    dlg = SettingsDialog(
        _base_settings(
            lmstudio_base_url="http://remote:8080/v1",
            lmstudio_api_key="mykey",
            lmstudio_timeout=300,
            lmstudio_embeddings_model="nomic-embed-text-v1.5",
        )
    )
    qtbot.addWidget(dlg)
    assert dlg.lmstudio_url_edit.text() == "http://remote:8080/v1"
    assert dlg.lmstudio_key_edit.text() == "mykey"
    assert dlg.lmstudio_timeout_spin.value() == 300
    assert dlg.lmstudio_embeddings_edit.text() == "nomic-embed-text-v1.5"


def test_lmstudio_save(qtbot):
    dlg = SettingsDialog(_base_settings())
    qtbot.addWidget(dlg)
    dlg.lmstudio_url_edit.setText("http://custom:9000/v1")
    dlg.lmstudio_key_edit.setText("secret")
    dlg.lmstudio_timeout_spin.setValue(120)
    dlg.lmstudio_embeddings_edit.setText("custom-embed")
    dlg._on_save()
    out = dlg.get_updated_settings()
    assert out["lmstudio_base_url"] == "http://custom:9000/v1"
    assert out["lmstudio_api_key"] == "secret"
    assert out["lmstudio_timeout"] == 120
    assert out["lmstudio_embeddings_model"] == "custom-embed"


def test_lmstudio_url_defaults_when_empty(qtbot):
    dlg = SettingsDialog(_base_settings(lmstudio_base_url=""))
    qtbot.addWidget(dlg)
    dlg.lmstudio_url_edit.setText("")
    dlg.lmstudio_key_edit.setText("")
    dlg._on_save()
    out = dlg.get_updated_settings()
    assert out["lmstudio_base_url"] == "http://localhost:1234/v1"
    assert out["lmstudio_api_key"] == "lm-studio"
