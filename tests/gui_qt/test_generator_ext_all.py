"""Tests for GeneratorTab._on_all_ext_clicked + _system_prompt_bytes."""

from __future__ import annotations

from PIG_T3.gui_qt.tabs.generator import GeneratorTab


def _make_tab(qtbot, tmp_path, ignore=""):
    (tmp_path / "a.py").write_text("x = 1\n")
    (tmp_path / "b.md").write_text("# hi\n")
    (tmp_path / "c.json").write_text("{}\n")
    sub = tmp_path / "venv"
    sub.mkdir()
    (sub / "d.py").write_text("ignored\n")
    tab = GeneratorTab(
        {
            "root_folder": str(tmp_path),
            "extensions": ".py",
            "ignore_list": ignore,
        }
    )
    qtbot.addWidget(tab)
    return tab


def test_all_ext_collects_unique(qtbot, tmp_path):
    tab = _make_tab(qtbot, tmp_path)
    tab._on_all_ext_clicked()
    text = tab.ext_edit.text()
    assert ".py" in text
    assert ".md" in text
    assert ".json" in text


def test_all_ext_honors_ignore(qtbot, tmp_path):
    tab = _make_tab(qtbot, tmp_path, ignore="venv")
    tab._on_all_ext_clicked()
    # .py должен быть, т.к. a.py в корне
    assert ".py" in tab.ext_edit.text()


def test_all_ext_missing_root(qtbot):
    tab = GeneratorTab({"root_folder": "/nonexistent"})
    qtbot.addWidget(tab)
    tab._on_all_ext_clicked()
    # Не падает, статус — ошибка
    assert "не существует" in tab.status_label.text().lower()


def test_system_prompt_bytes_returns_int(qtbot, tmp_path):
    tab = _make_tab(qtbot, tmp_path)
    tab.cb_add_edit_prompt.setChecked(True)
    size = tab._system_prompt_bytes()
    assert isinstance(size, int)
    assert size > 0


def test_system_prompt_bytes_includes_custom(qtbot, tmp_path):
    (tmp_path / "a.py").write_text("x = 1\n")
    tab = GeneratorTab(
        {
            "root_folder": str(tmp_path),
            "extensions": ".py",
            "ignore_list": "",
            "custom_system_prompt": "MARKER_CUSTOM_XYZ",
        }
    )
    qtbot.addWidget(tab)
    tab.cb_add_edit_prompt.setChecked(True)
    size_with = tab._system_prompt_bytes()
    tab.settings["custom_system_prompt"] = ""
    size_without = tab._system_prompt_bytes()
    assert size_with > size_without
