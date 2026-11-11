"""C6b: DiffDialog — секция команд."""

from PySide6.QtWidgets import QDialog

from PIG_T3.gui_qt.dialogs.diff_dialog import DiffDialog
from PIG_T3.gui_qt.workers.diff_preview import CommandSpec, FileDiff


def _d(path, status="created", diff=""):
    return FileDiff(path=path, status=status, unified_diff=diff)


def _c(command, **kw):
    return CommandSpec(command=command, **kw)


def test_only_commands_shows_list(qtbot):
    cmds = [_c("pytest tests/"), _c("ruff check")]
    dlg = DiffDialog([], commands=cmds)
    qtbot.addWidget(dlg)
    assert dlg.file_list.count() == 2
    assert "pytest tests/" in dlg.file_list.item(0).text()


def test_files_and_commands_combined(qtbot):
    diffs = [_d("a.py")]
    cmds = [_c("pytest")]
    dlg = DiffDialog(diffs, commands=cmds)
    qtbot.addWidget(dlg)
    assert dlg.file_list.count() == 2


def test_command_selected_shows_details(qtbot):
    cmds = [_c("pytest tests/", output_path=".pig/cmd/x.log", timeout_sec=60)]
    dlg = DiffDialog([], commands=cmds)
    qtbot.addWidget(dlg)
    dlg.file_list.setCurrentRow(0)
    text = dlg.diff_view.toPlainText()
    assert "pytest tests/" in text
    assert "timeout: 60" in text
    assert ".pig/cmd/x.log" in text


def test_command_abort_icon(qtbot):
    cmds = [_c("fail", on_failure="abort")]
    dlg = DiffDialog([], commands=cmds)
    qtbot.addWidget(dlg)
    assert "⏹" in dlg.file_list.item(0).text()


def test_commands_accept_rejects(qtbot):
    dlg = DiffDialog([], commands=[_c("x")])
    qtbot.addWidget(dlg)
    dlg.btn_apply.click()
    assert dlg.result() == QDialog.DialogCode.Accepted
