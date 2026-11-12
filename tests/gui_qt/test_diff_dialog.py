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


# ---------- P2 (issue 6): status="failed" ----------


def test_failed_status_icon(qtbot):
    diffs = [_d("a.py", "failed", "Патч не дал изменений")]
    dlg = DiffDialog(diffs)
    qtbot.addWidget(dlg)
    assert "⚠️" in dlg.file_list.item(0).text()


def test_failed_only_disables_apply(qtbot):
    diffs = [
        _d("a.py", "failed", "не найдено"),
        _d("b.py", "failed", "вне диапазона"),
    ]
    dlg = DiffDialog(diffs)
    qtbot.addWidget(dlg)
    assert not dlg.btn_apply.isEnabled()
    assert dlg.btn_apply.toolTip()


def test_failed_with_created_keeps_apply_enabled(qtbot):
    diffs = [
        _d("a.py", "failed", "не найдено"),
        _d("b.py", "created", "+x"),
    ]
    dlg = DiffDialog(diffs)
    qtbot.addWidget(dlg)
    assert dlg.btn_apply.isEnabled()


def test_failed_with_commands_keeps_apply_enabled(qtbot):
    from PIG_T3.gui_qt.workers.diff_preview import CommandSpec

    diffs = [_d("a.py", "failed", "не найдено")]
    cmds = [CommandSpec(command="pytest")]
    dlg = DiffDialog(diffs, commands=cmds)
    qtbot.addWidget(dlg)
    assert dlg.btn_apply.isEnabled()
    assert dlg.result() == QDialog.DialogCode.Rejected
