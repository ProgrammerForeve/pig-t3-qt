"""TDD: QualityTableModel + QualityTab (T-501..T-506)."""

from __future__ import annotations

import pytest

from PIG_T3.core.quality import FileMetrics, Issue
from PIG_T3.gui_qt.models.quality_table import QualityTableModel


def _m(path="a.py", **kw) -> FileMetrics:
    return FileMetrics(path=path, **kw)


# ---------- Модель ----------


def test_model_shape():
    m = QualityTableModel([_m("a.py"), _m("b.py")])
    from PySide6.QtCore import QModelIndex

    assert m.rowCount(QModelIndex()) == 2
    assert m.columnCount(QModelIndex()) == 7


def test_model_headers():
    m = QualityTableModel()
    from PySide6.QtCore import Qt

    assert m.headerData(0, Qt.Orientation.Horizontal) == "✓"
    assert m.headerData(1, Qt.Orientation.Horizontal) == "📄 Файл (Путь)"
    assert "Сложность" in m.headerData(3, Qt.Orientation.Horizontal)


def test_model_display_values():
    m = QualityTableModel([_m("a.py", sloc=5, complexity=2.5)])
    from PySide6.QtCore import Qt

    assert m.data(m.index(0, 1), Qt.ItemDataRole.DisplayRole) == "a.py"
    assert m.data(m.index(0, 2), Qt.ItemDataRole.DisplayRole) == "5"
    assert "2.5" in m.data(m.index(0, 3), Qt.ItemDataRole.DisplayRole)


def test_model_foreground_uses_status():
    m = QualityTableModel([_m("bad.py", complexity=25.0)])
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QColor

    brush = m.data(m.index(0, 3), Qt.ItemDataRole.ForegroundRole)
    assert brush.color() == QColor("#e06c75")  # red


def test_model_sort_ascending():
    metrics = [_m("c.py", sloc=3), _m("a.py", sloc=1), _m("b.py", sloc=2)]
    m = QualityTableModel(metrics)
    from PySide6.QtCore import Qt

    m.sort(2, Qt.SortOrder.AscendingOrder)
    order = [x.path for x in m.all_metrics()]
    assert order == ["a.py", "b.py", "c.py"]


def test_model_set_metrics():
    m = QualityTableModel()
    from PySide6.QtCore import QModelIndex

    m.set_metrics([_m("a.py")])
    assert m.rowCount(QModelIndex()) == 1


# ---------- Вкладка ----------


@pytest.fixture
def tab(qtbot, monkeypatch):
    from PIG_T3.gui_qt.tabs import quality as quality_module

    # Заглушки диалогов, чтобы не висеть на QMessageBox
    monkeypatch.setattr(quality_module, "_show_warning", lambda *a, **kw: None)
    monkeypatch.setattr(quality_module, "_show_error", lambda *a, **kw: None)
    t = quality_module.QualityTab()
    qtbot.addWidget(t)
    return t


def test_tab_has_core_widgets(tab):
    assert hasattr(tab, "btn_scan")
    assert hasattr(tab, "progress_bar")
    assert hasattr(tab, "table")
    assert hasattr(tab, "details")
    assert hasattr(tab, "cb_compact")


def test_set_path(tab):
    tab.set_path("/tmp/proj")
    assert tab.path_edit.text() == "/tmp/proj"


def test_set_metrics_updates_stats(tab):
    tab.set_metrics([_m("a.py"), _m("b.py")])
    assert "Всего: 2" in tab.status_label.text()


def test_compact_view_hides_columns(tab):
    tab.set_metrics([_m("a.py")])
    tab.cb_compact.setChecked(True)
    # при сортировке path видны path + cc
    hidden = [tab.table.isColumnHidden(i) for i in range(7)]
    assert hidden[0] is False  # check
    assert hidden[1] is False  # path
    assert hidden[2] is True  # sloc
    assert hidden[3] is False  # cc
    tab.cb_compact.setChecked(False)
    assert all(not h for h in [tab.table.isColumnHidden(i) for i in range(7)])


def test_row_selection_shows_details(tab):
    m = _m("a.py", sloc=5, complexity=2.5, maintainability=30.0, pylint_score=9.0, security_issues=0)
    tab.set_metrics([m])
    # выбрать первую строку
    tab.table.selectRow(0)
    html = tab.details.toHtml()
    assert "a.py" in html
    assert "Cyclomatic" in html


def test_details_shows_issues(tab):
    m = _m(
        "b.py",
        issues=[
            Issue(tool="pylint", msg="unused variable", line=10, severity="error"),
            Issue(tool="bandit", msg="hardcoded password", line=20, severity="warning"),
        ],
    )
    tab.set_metrics([m])
    tab.table.selectRow(0)
    html = tab.details.toHtml()
    assert "PYLINT" in html
    assert "BANDIT" in html


def test_scan_invalid_path_does_nothing(tab):
    tab.path_edit.setText("/nonexistent_path_xyz")
    tab._on_scan_clicked()
    assert tab._scan_thread is None
