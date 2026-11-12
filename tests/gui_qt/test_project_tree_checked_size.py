"""Tests for ProjectTreeModel.checked_size_bytes."""

from __future__ import annotations

import pytest
from PySide6.QtCore import Qt

from PIG_T3.gui_qt.models.project_tree import ProjectTreeModel


@pytest.fixture
def model(tmp_path):
    (tmp_path / "a.py").write_text("x" * 100)
    (tmp_path / "b.py").write_text("y" * 200)
    files = [
        (str(tmp_path / "a.py"), ".py"),
        (str(tmp_path / "b.py"), ".py"),
    ]
    return ProjectTreeModel(str(tmp_path), files)


def test_checked_size_bytes_all_checked(model):
    assert model.checked_size_bytes() == 300


def test_checked_size_bytes_after_uncheck(model):
    idx = model.find_index("a.py")
    model.setData(idx, Qt.CheckState.Unchecked.value, Qt.ItemDataRole.CheckStateRole)
    assert model.checked_size_bytes() == 200


def test_checked_size_bytes_empty():
    m = ProjectTreeModel("/proj", [])
    assert m.checked_size_bytes() == 0
