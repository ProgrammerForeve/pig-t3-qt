"""B1: DiffDialog — рендер и кнопки."""

from PySide6.QtWidgets import QDialog

from PIG_T3.gui_qt.dialogs.diff_dialog import DiffDialog
from PIG_T3.gui_qt.workers.diff_preview import FileDiff


def _d(path, status, diff=""):
    return FileDiff(path=path, status=status, unified_diff=diff)


def test_empty_diffs(qtbot):
    from PySide6.QtWidgets import QLabel

    dlg = DiffDialog([])
    qtbot.addWidget(dlg)
    labels = [w for w in dlg.findChildren(QLabel) if "Нет изменений" in w.text()]
    assert labels


def test_file_list_populated(qtbot):
    diffs = [
        _d("new.py", "created", "+x"),
        _d("mod.py", "modified", "-old\n+new"),
        _d("gone.py", "deleted", "-y"),
    ]
    dlg = DiffDialog(diffs)
    qtbot.addWidget(dlg)
    assert dlg.file_list.count() == 3
    assert "new.py" in dlg.file_list.item(0).text()
    assert "➕" in dlg.file_list.item(0).text()
    assert "✏️" in dlg.file_list.item(1).text()
    assert "🗑️" in dlg.file_list.item(2).text()


def test_selecting_file_shows_diff(qtbot):
    diffs = [_d("a.py", "modified", "-old\n+new")]
    dlg = DiffDialog(diffs)
    qtbot.addWidget(dlg)
    dlg.file_list.setCurrentRow(0)
    text = dlg.diff_view.toPlainText()
    assert "old" in text or "new" in text


def test_apply_accepts(qtbot):
    diffs = [_d("a.py", "created", "+x")]
    dlg = DiffDialog(diffs)
    qtbot.addWidget(dlg)
    dlg.btn_apply.click()
    assert dlg.result() == QDialog.DialogCode.Accepted


def test_cancel_rejects(qtbot):
    diffs = [_d("a.py", "created", "+x")]
    dlg = DiffDialog(diffs)
    qtbot.addWidget(dlg)
    dlg.btn_cancel.click()
    assert dlg.result() == QDialog.DialogCode.Rejected
