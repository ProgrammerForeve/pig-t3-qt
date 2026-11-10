"""TDD: ProjectTreeView — клик по строке = toggle (T-105)."""

import pytest
from PySide6.QtCore import QModelIndex, QPoint, Qt
from PySide6.QtWidgets import QTreeView

from PIG_T3.gui_qt.models.project_tree import ProjectTreeModel
from PIG_T3.gui_qt.widgets.project_tree_view import ProjectTreeView


@pytest.fixture
def files():
    return [
        ("/proj/main.py", ".py"),
        ("/proj/utils/helper.py", ".py"),
        ("/proj/utils/__init__.py", ".py"),
        ("/proj/README.md", ".md"),
    ]


@pytest.fixture
def model(files):
    return ProjectTreeModel("/proj", files)


@pytest.fixture
def view(qtbot, model):
    v = ProjectTreeView()
    v.setModel(model)
    qtbot.addWidget(v)
    v.resize(500, 400)
    v.show()
    qtbot.waitExposed(v)
    return v


# ---- Basic ----


def test_view_is_treeview(view):
    assert isinstance(view, QTreeView)


def test_model_attached(view, model):
    assert view.model() is model


# ---- Programmatic toggle ----


def test_toggle_check_for_index_toggles(view, model):
    idx = model.find_index("main.py")
    assert view.toggle_check_for_index(idx) is True
    assert model.data(idx, Qt.ItemDataRole.CheckStateRole) == Qt.CheckState.Unchecked


def test_toggle_check_for_index_returns_false_for_invalid(view):
    assert view.toggle_check_for_index(QModelIndex()) is False


# ---- Indicator detection ----


def test_indicator_false_for_leaf(view, model):
    idx = model.find_index("main.py")
    assert view._is_on_branch_indicator(QPoint(5, 10), idx) is False


def test_indicator_true_for_dir_at_left_edge(view, model):
    idx = model.find_index("utils")
    assert view._is_on_branch_indicator(QPoint(2, 10), idx) is True


def test_indicator_false_for_dir_at_right_edge(view, model):
    idx = model.find_index("utils")
    indentation = view.indentation()
    assert view._is_on_branch_indicator(QPoint(indentation + 20, 10), idx) is False


# ---- End-to-end click ----


def test_click_on_text_toggles_leaf(view, model, qtbot):
    idx = model.find_index("README.md")
    rect = view.visualRect(idx)
    pos = rect.center()
    qtbot.mouseClick(view.viewport(), Qt.MouseButton.LeftButton, pos=pos)
    assert model.data(idx, Qt.ItemDataRole.CheckStateRole) == Qt.CheckState.Unchecked


def test_click_on_text_toggles_folder(view, model, qtbot):
    idx = model.find_index("utils")
    rect = view.visualRect(idx)
    # click right of indicator (on text)
    indentation = view.indentation()
    pos = QPoint(indentation + 30, rect.center().y())
    qtbot.mouseClick(view.viewport(), Qt.MouseButton.LeftButton, pos=pos)
    assert model.data(idx, Qt.ItemDataRole.CheckStateRole) == Qt.CheckState.Unchecked


def test_click_on_indicator_does_not_toggle(view, model, qtbot):
    idx = model.find_index("utils")
    rect = view.visualRect(idx)
    pos = QPoint(2, rect.center().y())  # on branch indicator
    initial = model.data(idx, Qt.ItemDataRole.CheckStateRole)
    qtbot.mouseClick(view.viewport(), Qt.MouseButton.LeftButton, pos=pos)
    assert model.data(idx, Qt.ItemDataRole.CheckStateRole) == initial


# ---- reset_data ----


def test_model_reset_data_replaces_tree():
    m = ProjectTreeModel("/proj", [("/proj/a.py", ".py")])
    assert m.rowCount(QModelIndex()) == 1
    m.reset_data([("/proj/b.py", ".py"), ("/proj/c.py", ".py")], "/proj")
    assert m.rowCount(QModelIndex()) == 2


def test_model_reset_data_empty():
    m = ProjectTreeModel("/proj", [("/proj/a.py", ".py")])
    m.reset_data([], "/proj")
    assert m.rowCount(QModelIndex()) == 0
