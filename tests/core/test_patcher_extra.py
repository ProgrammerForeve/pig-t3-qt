"""Day 6+: patcher operations happy path (create/delete/move/edit/update/mark)."""

import json

from PIG_T3.core.patcher import apply_llm_changes, clean_json_text


def _run(actions, root):
    return apply_llm_changes(json.dumps(actions), str(root))


# ---------- clean_json_text ----------


def test_clean_json_markdown_block():
    text = '```json\n[{"a": 1}]\n```'
    assert clean_json_text(text) == '[{"a": 1}]'


def test_clean_json_bare_list():
    text = 'prefix [{"a": 1}] suffix'
    cleaned = clean_json_text(text)
    assert '"a"' in cleaned


def test_clean_json_plain():
    assert clean_json_text("[1, 2, 3]") == "[1, 2, 3]"


# ---------- create / delete ----------


def test_create_writes_file(tmp_path):
    log = _run([{"action": "create", "path": "a.py", "content": "x=1\n"}], tmp_path)
    assert "CREATE: a.py" in log
    assert (tmp_path / "a.py").read_text() == "x=1\n"


def test_create_with_explanation(tmp_path):
    log = _run([{"action": "create", "path": "a.py", "content": "x\n", "explanation": "created"}], tmp_path)
    assert "Пояснение: created" in log


def test_delete_file(tmp_path):
    (tmp_path / "a.py").write_text("x")
    log = _run([{"action": "delete", "path": "a.py"}], tmp_path)
    assert "DELETE: a.py" in log
    assert not (tmp_path / "a.py").exists()


def test_delete_directory(tmp_path):
    sub = tmp_path / "pkg"
    sub.mkdir()
    (sub / "a.py").write_text("x")
    log = _run([{"action": "delete", "path": "pkg"}], tmp_path)
    assert "DELETE" in log
    assert not sub.exists()


def test_delete_missing_warns(tmp_path):
    log = _run([{"action": "delete", "path": "nope.py"}], tmp_path)
    assert "не найден" in log


# ---------- move ----------


def test_move_file(tmp_path):
    (tmp_path / "old.py").write_text("x")
    log = _run([{"action": "move", "source": "old.py", "destination": "sub/new.py"}], tmp_path)
    assert "MOVE" in log
    assert (tmp_path / "sub" / "new.py").exists()
    assert not (tmp_path / "old.py").exists()


def test_move_missing_source_errors(tmp_path):
    log = _run([{"action": "move", "source": "missing.py", "destination": "new.py"}], tmp_path)
    assert "не найден" in log


# ---------- edit: replace_lines ----------


def test_edit_replace_lines(tmp_path):
    (tmp_path / "a.py").write_text("line1\nline2\nline3\n")
    log = _run(
        [
            {
                "action": "edit",
                "path": "a.py",
                "operations": [{"type": "replace_lines", "start": 2, "end": 2, "content": "REPLACED\n"}],
            }
        ],
        tmp_path,
    )
    assert "Line Patch" in log
    assert (tmp_path / "a.py").read_text() == "line1\nREPLACED\nline3\n"


def test_edit_insert_after_line(tmp_path):
    (tmp_path / "a.py").write_text("line1\nline3\n")
    log = _run(
        [
            {
                "action": "edit",
                "path": "a.py",
                "operations": [{"type": "insert_after_line", "line": 1, "content": "line2\n"}],
            }
        ],
        tmp_path,
    )
    assert "Insert" in log
    assert (tmp_path / "a.py").read_text() == "line1\nline2\nline3\n"


def test_edit_replace_text(tmp_path):
    (tmp_path / "a.py").write_text("hello world\n")
    log = _run(
        [
            {
                "action": "edit",
                "path": "a.py",
                "operations": [{"type": "replace_text", "find": "world", "replace": "there"}],
            }
        ],
        tmp_path,
    )
    assert "Text Patch" in log
    assert (tmp_path / "a.py").read_text() == "hello there\n"


def test_edit_missing_file_errors(tmp_path):
    log = _run(
        [
            {
                "action": "edit",
                "path": "missing.py",
                "operations": [{"type": "replace_lines", "start": 1, "end": 1, "content": "x"}],
            }
        ],
        tmp_path,
    )
    assert "файл не найден" in log


def test_edit_no_operations_warns(tmp_path):
    (tmp_path / "a.py").write_text("x")
    log = _run([{"action": "edit", "path": "a.py", "operations": []}], tmp_path)
    assert "нет операций" in log


# ---------- update_settings ----------


def test_update_settings_writes_app_config(tmp_path, monkeypatch):
    # создаём .pig/state.json
    (tmp_path / ".pig").mkdir()
    (tmp_path / ".pig" / "state.json").write_text(json.dumps({"extensions": ".py"}))
    log = _run(
        [
            {
                "action": "update_settings",
                "extensions": ".py, .md",
                "ignore_list": "venv",
            }
        ],
        tmp_path,
    )
    assert "SETTINGS UPDATED" in log
    state = json.loads((tmp_path / ".pig" / "state.json").read_text())
    assert state["extensions"] == ".py, .md"
    assert state["ignore_list"] == "venv"


# ---------- mark_step_completed ----------


def test_mark_step_completed(tmp_path):
    (tmp_path / ".pig").mkdir()
    plan = [
        {"id": "s1", "title": "T1", "description": "d1", "completed": False},
        {"id": "s2", "title": "T2", "description": "d2", "completed": False},
    ]
    (tmp_path / ".pig" / "plan.json").write_text(json.dumps(plan))

    log = _run([{"action": "mark_step_completed", "step_id": "s1", "explanation": "done"}], tmp_path)
    assert "ВЫПОЛНЕННЫЙ" in log
    updated = json.loads((tmp_path / ".pig" / "plan.json").read_text())
    assert updated[0]["completed"] is True
    assert updated[0]["report"] == "done"


def test_mark_step_completed_false(tmp_path):
    (tmp_path / ".pig").mkdir()
    plan = [{"id": "s1", "title": "T", "description": "d", "completed": True}]
    (tmp_path / ".pig" / "plan.json").write_text(json.dumps(plan))

    _run([{"action": "mark_step_completed", "step_id": "s1", "completed": False}], tmp_path)
    updated = json.loads((tmp_path / ".pig" / "plan.json").read_text())
    assert updated[0]["completed"] is False


def test_mark_step_completed_append_description(tmp_path):
    (tmp_path / ".pig").mkdir()
    plan = [{"id": "s1", "title": "T", "description": "orig", "completed": False}]
    (tmp_path / ".pig" / "plan.json").write_text(json.dumps(plan))

    _run([{"action": "mark_step_completed", "step_id": "s1", "append_description": "TODO: tests"}], tmp_path)
    updated = json.loads((tmp_path / ".pig" / "plan.json").read_text())
    assert "TODO: tests" in updated[0]["description"]


def test_mark_step_missing_plan_warns(tmp_path):
    log = _run([{"action": "mark_step_completed", "step_id": "s1"}], tmp_path)
    assert "План не найден" in log


# ---------- invalid JSON / non-list ----------


def test_invalid_json_returns_error(tmp_path):
    log = apply_llm_changes("not json", str(tmp_path))
    assert "Ошибка парсинга JSON" in log


def test_non_list_returns_error(tmp_path):
    log = apply_llm_changes('{"a": 1}', str(tmp_path))
    assert "должен быть списком" in log


# ---------- Whitespace-flexible edit (regression Windows/tabs) ----------


def test_replace_text_exact_still_works(tmp_path):
    (tmp_path / "a.py").write_text("hello world\n")
    _run(
        [
            {
                "action": "edit",
                "path": "a.py",
                "operations": [
                    {
                        "type": "replace_text",
                        "find": "hello world",
                        "replace": "bye world",
                    }
                ],
            }
        ],
        tmp_path,
    )
    assert (tmp_path / "a.py").read_text() == "bye world\n"


def test_replace_text_flexible_tabs_vs_spaces(tmp_path):
    """Файл с пробелами, find с табами."""
    (tmp_path / "a.py").write_text("def foo():\n    return 1\n")
    _run(
        [
            {
                "action": "edit",
                "path": "a.py",
                "operations": [
                    {
                        "type": "replace_text",
                        "find": "def foo():\n\treturn 1",
                        "replace": "def foo():\n    return 2",
                    }
                ],
            }
        ],
        tmp_path,
    )
    content = (tmp_path / "a.py").read_text()
    assert "return 2" in content
    assert "return 1" not in content


def test_replace_text_flexible_double_space(tmp_path):
    """Файл с одним пробелом, find с двумя."""
    (tmp_path / "a.py").write_text("a = 1\nb = 2\n")
    _run(
        [
            {
                "action": "edit",
                "path": "a.py",
                "operations": [
                    {
                        "type": "replace_text",
                        "find": "a  =  1",
                        "replace": "a = 10",
                    }
                ],
            }
        ],
        tmp_path,
    )
    assert "a = 10" in (tmp_path / "a.py").read_text()


def test_replace_text_flexible_preserves_indent(tmp_path):
    """Файл с indent 4, find без indent — заменяемый блок должен
    получить indent 4."""
    (tmp_path / "a.py").write_text("class C:\n    def m(self):\n        return 1\n")
    _run(
        [
            {
                "action": "edit",
                "path": "a.py",
                "operations": [
                    {
                        "type": "replace_text",
                        "find": "def m(self):\n    return 1",
                        "replace": "def m(self):\n    return 2",
                    }
                ],
            }
        ],
        tmp_path,
    )
    content = (tmp_path / "a.py").read_text()
    # Метод должен остаться в классе с indent 4
    assert "    def m(self):" in content
    assert "        return 2" in content


def test_replace_text_not_found_reports_preview(tmp_path):
    (tmp_path / "a.py").write_text("hello\n")
    log = _run(
        [
            {
                "action": "edit",
                "path": "a.py",
                "operations": [
                    {
                        "type": "replace_text",
                        "find": "completely different content",
                        "replace": "x",
                    }
                ],
            }
        ],
        tmp_path,
    )
    assert "фрагмент не найден" in log
    assert "completely different content" in log  # preview виден


def test_replace_lines_anti_dup_ignores_indent(tmp_path):
    """Если LLM прислал content с indent-дубликатом соседней строки,
    anti-dup должен удалить."""
    (tmp_path / "a.py").write_text("line1\nline2\nline3\n")
    _run(
        [
            {
                "action": "edit",
                "path": "a.py",
                "operations": [
                    {
                        "type": "replace_lines",
                        "start": 2,
                        "end": 2,
                        # content содержит line2, но с другими пробелами
                        "content": "  line2\n",
                    }
                ],
            }
        ],
        tmp_path,
    )
    content = (tmp_path / "a.py").read_text()
    # После замены: line1\n  line2\nline3 — но anti-dup должен
    # не дать двум line2 подряд
    assert content.count("line2") == 1
