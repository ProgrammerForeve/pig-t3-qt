"""Day 6: QualityTab — compact view, header click, worker callbacks."""

import pytest

from PIG_T3.core.quality import FileMetrics
from PIG_T3.gui_qt.tabs import quality as quality_module
from PIG_T3.gui_qt.tabs.quality import QualityTab


@pytest.fixture(autouse=True)
def _silence(monkeypatch):
    monkeypatch.setattr(quality_module, "_show_warning", lambda *a, **kw: None)
    monkeypatch.setattr(quality_module, "_show_error", lambda *a, **kw: None)


@pytest.fixture
def tab(qtbot):
    t = QualityTab()
    qtbot.addWidget(t)
    return t


def test_compact_off_shows_all(tab):
    tab.set_metrics([FileMetrics(path="a.py")])
    tab.cb_compact.setChecked(False)
    for i in range(7):
        assert not tab.table.isColumnHidden(i)


def test_compact_sort_changes_visible_columns(tab):
    tab.set_metrics([FileMetrics(path="a.py")])
    tab.cb_compact.setChecked(True)
    # default sort path -> visible path + cc
    assert not tab.table.isColumnHidden(1)  # path
    assert not tab.table.isColumnHidden(3)  # cc
    assert tab.table.isColumnHidden(2)  # sloc

    tab._current_sort_col = "score"
    tab._apply_compact_view()
    assert not tab.table.isColumnHidden(1)
    assert not tab.table.isColumnHidden(5)  # score
    assert tab.table.isColumnHidden(6)  # sec (не в visible)


def test_on_header_clicked_updates_sort_col(tab):
    tab.set_metrics([FileMetrics(path="a.py")])
    tab._on_header_clicked(3)  # cc
    assert tab._current_sort_col == "cc"


def test_on_scan_error_sets_status(tab):
    tab._on_scan_error("boom")
    assert "boom" in tab.status_label.text()


def test_on_scan_cancelled(tab):
    tab._on_scan_cancelled()
    assert "отмен" in tab.status_label.text().lower()


def test_on_progress_updates_bar(tab):
    tab.progress_bar.setVisible(True)
    tab._on_progress(50, "step")
    assert tab.progress_bar.value() == 50


def test_cleanup_thread_when_none(tab):
    tab._cleanup_thread()  # noop


def test_stop_scan_when_none(tab):
    tab.stop_scan()  # noop


def test_set_metrics_empty(tab):
    tab.set_metrics([])
    assert "не найдены" in tab.status_label.text().lower()


def test_details_empty_for_invalid_row(tab):
    from PySide6.QtCore import QModelIndex

    tab._on_row_changed(QModelIndex(), QModelIndex())
    # не падает
