"""TDD: ProjectTreeModel (T-104)."""

import pytest
from PySide6.QtCore import QModelIndex, Qt

from PIG_T3.gui_qt.models.project_tree import ProjectTreeModel, TreeNode


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


def _find_top(model, name):
    """Возвращает QModelIndex top-level элемента по display-name."""
    for i in range(model.rowCount(QModelIndex())):
        idx = model.index(i, 0, QModelIndex())
        if model.data(idx, Qt.ItemDataRole.DisplayRole) == name:
            return idx
    raise AssertionError(f"{name!r} not found at top level")


# ---------- Structure ----------


def test_root_row_count(model):
    # utils (dir), main.py, README.md
    assert model.rowCount(QModelIndex()) == 3


def test_column_count_is_2(model):
    assert model.columnCount(QModelIndex()) == 2


def test_size_column_shows_bytes(model):
    idx = _find_top(model, "main.py")
    size_idx = model.index(idx.row(), 1, idx.parent())
    text = model.data(size_idx, Qt.ItemDataRole.DisplayRole)
    assert text  # не пустой
    assert "B" in text or "KB" in text or "MB" in text


def test_size_column_right_aligned(model):
    idx = _find_top(model, "main.py")
    size_idx = model.index(idx.row(), 1, idx.parent())
    align = model.data(size_idx, Qt.ItemDataRole.TextAlignmentRole)
    assert align is not None
    assert int(align) & int(Qt.AlignmentFlag.AlignRight)


def test_header_data(model):
    assert model.headerData(0, Qt.Orientation.Horizontal) == "Файл"
    assert model.headerData(1, Qt.Orientation.Horizontal) == "Размер"


def test_size_column_not_checkable(model):
    idx = _find_top(model, "main.py")
    size_idx = model.index(idx.row(), 1, idx.parent())
    flags = model.flags(size_idx)
    assert not (flags & Qt.ItemFlag.ItemIsUserCheckable)
    # но name-колонка — checkable
    name_idx = model.index(idx.row(), 0, idx.parent())
    assert model.flags(name_idx) & Qt.ItemFlag.ItemIsUserCheckable


def test_setdata_on_size_column_returns_false(model):
    idx = _find_top(model, "main.py")
    size_idx = model.index(idx.row(), 1, idx.parent())
    ok = model.setData(size_idx, Qt.CheckState.Unchecked.value, Qt.ItemDataRole.CheckStateRole)
    assert ok is False


def test_top_level_sorted_dirs_first(model):
    names = [
        model.data(model.index(i, 0, QModelIndex()), Qt.ItemDataRole.DisplayRole)
        for i in range(model.rowCount(QModelIndex()))
    ]
    assert names == ["utils", "main.py", "README.md"]


def test_file_is_leaf(model):
    idx = _find_top(model, "main.py")
    assert model.rowCount(idx) == 0


def test_folder_has_children(model):
    idx = _find_top(model, "utils")
    assert model.rowCount(idx) == 2


def test_children_sorted_alphabetically(model):
    idx = _find_top(model, "utils")
    names = [model.data(model.index(i, 0, idx), Qt.ItemDataRole.DisplayRole) for i in range(model.rowCount(idx))]
    assert names == ["__init__.py", "helper.py"]


def test_empty_tree():
    model = ProjectTreeModel("/proj", [])
    assert model.rowCount(QModelIndex()) == 0


# ---------- Roles & flags ----------


def test_default_state_checked(model):
    for i in range(model.rowCount(QModelIndex())):
        idx = model.index(i, 0, QModelIndex())
        assert model.data(idx, Qt.ItemDataRole.CheckStateRole) == Qt.CheckState.Checked


def test_flags_user_checkable(model):
    flags = model.flags(_find_top(model, "main.py"))
    assert flags & Qt.ItemFlag.ItemIsUserCheckable
    assert flags & Qt.ItemFlag.ItemIsEnabled


def test_invalid_index_returns_none(model):
    assert model.data(QModelIndex(), Qt.ItemDataRole.DisplayRole) is None


# ---------- setData & cascading ----------


def test_set_file_state(model):
    idx = _find_top(model, "main.py")
    ok = model.setData(idx, Qt.CheckState.Unchecked.value, Qt.ItemDataRole.CheckStateRole)
    assert ok
    assert model.data(idx, Qt.ItemDataRole.CheckStateRole) == Qt.CheckState.Unchecked


def test_setData_wrong_role_returns_false(model):
    idx = _find_top(model, "main.py")
    assert model.setData(idx, "x", Qt.ItemDataRole.EditRole) is False


def test_folder_toggle_cascades(model):
    idx = _find_top(model, "utils")
    model.setData(idx, Qt.CheckState.Unchecked.value, Qt.ItemDataRole.CheckStateRole)
    for j in range(model.rowCount(idx)):
        child = model.index(j, 0, idx)
        assert model.data(child, Qt.ItemDataRole.CheckStateRole) == Qt.CheckState.Unchecked


def test_child_uncheck_makes_parent_partial(model):
    utils = _find_top(model, "utils")
    child = model.index(0, 0, utils)
    model.setData(child, Qt.CheckState.Unchecked.value, Qt.ItemDataRole.CheckStateRole)
    assert model.data(utils, Qt.ItemDataRole.CheckStateRole) == Qt.CheckState.PartiallyChecked


def test_all_children_checked_makes_parent_checked(model):
    utils = _find_top(model, "utils")
    model.setData(utils, Qt.CheckState.Unchecked.value, Qt.ItemDataRole.CheckStateRole)
    for j in range(model.rowCount(utils)):
        child = model.index(j, 0, utils)
        model.setData(child, Qt.CheckState.Checked.value, Qt.ItemDataRole.CheckStateRole)
    assert model.data(utils, Qt.ItemDataRole.CheckStateRole) == Qt.CheckState.Checked


# ---------- Signal ----------


def test_signal_emitted_on_toggle(model, qtbot):
    idx = _find_top(model, "main.py")
    with qtbot.waitSignal(model.checkStateChanged, timeout=500):
        model.setData(idx, Qt.CheckState.Unchecked.value, Qt.ItemDataRole.CheckStateRole)


# ---------- Public helpers ----------


def test_checked_files_initially_all(model):
    assert sorted(model.checked_files()) == sorted(
        [
            "/proj/main.py",
            "/proj/utils/helper.py",
            "/proj/utils/__init__.py",
            "/proj/README.md",
        ]
    )


def test_checked_files_excludes_unchecked(model):
    idx = _find_top(model, "main.py")
    model.setData(idx, Qt.CheckState.Unchecked.value, Qt.ItemDataRole.CheckStateRole)
    checked = model.checked_files()
    assert "/proj/main.py" not in checked
    assert "/proj/README.md" in checked


def test_unchecked_paths(model):
    idx = _find_top(model, "main.py")
    model.setData(idx, Qt.CheckState.Unchecked.value, Qt.ItemDataRole.CheckStateRole)
    assert model.unchecked_paths() == ["main.py"]


def test_unchecked_paths_includes_fully_unchecked_dir(model):
    utils = _find_top(model, "utils")
    model.setData(utils, Qt.CheckState.Unchecked.value, Qt.ItemDataRole.CheckStateRole)
    assert model.unchecked_paths() == ["utils"]


def test_unchecked_paths_roundtrip(files):
    m1 = ProjectTreeModel("/proj", files)
    idx = m1.find_index("main.py")
    m1.setData(idx, Qt.CheckState.Unchecked.value, Qt.ItemDataRole.CheckStateRole)
    snapshot = m1.unchecked_paths()
    assert snapshot == ["main.py"]

    m2 = ProjectTreeModel("/proj", files)
    m2.set_unchecked_paths(snapshot)
    assert m2.data(m2.find_index("main.py"), Qt.ItemDataRole.CheckStateRole) == Qt.CheckState.Unchecked


def test_set_unchecked_paths_accepts_legacy_redundant_format(files):
    """Legacy stores both dir and its children; our restore must tolerate it."""
    m = ProjectTreeModel("/proj", files)
    m.set_unchecked_paths(["utils", "utils/helper.py", "utils/__init__.py"])
    utils = m.find_index("utils")
    assert m.data(utils, Qt.ItemDataRole.CheckStateRole) == Qt.CheckState.Unchecked


def test_find_index_missing_returns_invalid(model):
    assert not model.find_index("nope.txt").isValid()


def test_tree_node_dataclass():
    node = TreeNode(name="x", path="/p/x", is_dir=False)
    assert node.children == []
    assert node.check_state == Qt.CheckState.Checked


# ---------- T-110: set_all_checked ----------


def test_set_all_checked_false(model):
    model.set_all_checked(False)
    assert model.checked_files() == []


def test_set_all_checked_true(model):
    model.set_all_checked(False)
    model.set_all_checked(True)
    assert len(model.checked_files()) == 4


def test_set_all_checked_emits_signal(model, qtbot):
    with qtbot.waitSignal(model.checkStateChanged, timeout=500):
        model.set_all_checked(False)


# ---------- P2: tooltip с размером ----------


def test_tooltip_contains_size_and_tokens(model):
    idx = _find_top(model, "main.py")
    tip = model.data(idx, Qt.ItemDataRole.ToolTipRole)
    assert tip
    assert "main.py" in tip
    assert "байт" in tip
    assert "токенов" in tip


def test_tooltip_root_returns_none(model):
    assert model.data(QModelIndex(), Qt.ItemDataRole.ToolTipRole) is None
