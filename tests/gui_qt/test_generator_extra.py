"""Day 6: GeneratorTab — _all_file_paths, select-all sync, _detach_worker, stop_*."""

import pytest
from PySide6.QtCore import Qt

from PIG_T3.gui_qt.tabs.generator import GeneratorTab


@pytest.fixture
def tab(qtbot, tmp_path):
    (tmp_path / "a.py").write_text("x")
    (tmp_path / "b.py").write_text("y")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "c.py").write_text("z")
    t = GeneratorTab(
        {
            "root_folder": str(tmp_path),
            "extensions": ".py",
            "ignore_list": "",
        }
    )
    qtbot.addWidget(t)
    return t


def test_all_file_paths(tab):
    paths = tab._all_file_paths()
    assert len(paths) == 3
    assert all(p.endswith(".py") for p in paths)


def test_all_file_paths_empty(qtbot, tmp_path):
    t = GeneratorTab({"root_folder": str(tmp_path), "extensions": ".py", "ignore_list": ""})
    qtbot.addWidget(t)
    assert t._all_file_paths() == []


def test_sync_select_all_empty_tree(tab):
    tab.tree_model.reset_data([], tab.path_edit.text())
    tab._sync_select_all_state()
    assert tab.cb_select_all.checkState() == Qt.CheckState.Checked


def test_sync_select_all_all_checked(tab):
    tab._sync_select_all_state()
    assert tab.cb_select_all.checkState() == Qt.CheckState.Checked


def test_sync_select_all_all_unchecked(tab):
    tab.tree_model.set_all_checked(False)
    tab._sync_select_all_state()
    assert tab.cb_select_all.checkState() == Qt.CheckState.Unchecked


def test_sync_select_all_partial(tab):
    idx = tab.tree_model.find_index("a.py")
    tab.tree_model.setData(idx, Qt.CheckState.Unchecked.value, Qt.ItemDataRole.CheckStateRole)
    tab._sync_select_all_state()
    assert tab.cb_select_all.checkState() == Qt.CheckState.PartiallyChecked


def test_detach_worker_from_thread_none():
    GeneratorTab._detach_worker_from_thread(None)  # noop


def test_stop_generation_when_not_running(tab):
    tab.stop_generation()  # noop


def test_stop_optimization_when_not_running(tab):
    tab.stop_optimization()  # noop


def test_refresh_tree_resets_on_empty_path(tab):
    tab.path_edit.setText("/nonexistent_path_xyz")
    tab.refresh_tree()
    from PySide6.QtCore import QModelIndex

    assert tab.tree_model.rowCount(QModelIndex()) == 0


def test_on_generation_cancelled_updates_status(tab):
    tab._on_generation_cancelled()
    assert "отменена" in tab.status_label.text().lower()


def test_on_optimization_error(tab):
    tab._on_optimization_error("boom")
    assert "boom" in tab.status_label.text()


def test_on_optimization_cancelled(tab):
    tab._on_optimization_cancelled()
    assert "отмен" in tab.status_label.text().lower()


# ---------- C7 follow-up: ported from test_misc_coverage.py ----------


def test_format_number_small():
    from PIG_T3.gui_qt.tabs.generator import GeneratorTab

    assert GeneratorTab._format_number(42) == "42"


def test_format_number_k():
    from PIG_T3.gui_qt.tabs.generator import GeneratorTab

    assert GeneratorTab._format_number(1200) == "1.2K"
    assert GeneratorTab._format_number(45_678) == "45.68K"


def test_format_number_m():
    from PIG_T3.gui_qt.tabs.generator import GeneratorTab

    assert GeneratorTab._format_number(1_500_000) == "1.5M"


def test_estimate_total_tokens_empty(qtbot, tmp_path):
    from PIG_T3.gui_qt.tabs.generator import GeneratorTab

    tab = GeneratorTab(
        {
            "root_folder": str(tmp_path),
            "extensions": ".py",
            "ignore_list": "",
        }
    )
    qtbot.addWidget(tab)
    assert tab._estimate_total_tokens() == 1000


def test_refresh_tree_filters_by_clean_extensions(qtbot, tmp_path):
    from PySide6.QtCore import QModelIndex

    from PIG_T3.gui_qt.tabs.generator import GeneratorTab

    (tmp_path / "a.py").write_text("x")
    (tmp_path / "b.txt").write_text("y")
    tab = GeneratorTab(
        {
            "root_folder": str(tmp_path),
            "extensions": " .py , .md , ",
            "ignore_list": "",
        }
    )
    qtbot.addWidget(tab)
    names = {
        tab.tree_model.data(tab.tree_model.index(i, 0, QModelIndex()))
        for i in range(tab.tree_model.rowCount(QModelIndex()))
    }
    assert "a.py" in names
    assert "b.txt" not in names
