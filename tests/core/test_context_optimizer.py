"""TDD: ContextOptimizer — ignore_list (и базовая фильтрация .py)."""

from PIG_T3.core.context_optimizer import ContextOptimizer


def _make_py(root, rel_path, content="x = 1\n"):
    p = root / rel_path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)
    return p


def test_default_collects_all_py(tmp_path):
    _make_py(tmp_path, "a.py")
    _make_py(tmp_path, "sub/b.py")
    opt = ContextOptimizer(str(tmp_path), "task", limit_tokens=1000)
    opt._collect_python_files()
    names = {p.split("/")[-1] for p in opt.all_files}
    assert "a.py" in names
    assert "b.py" in names


def test_default_ignores_hardcoded_dirs(tmp_path):
    _make_py(tmp_path, "a.py")
    _make_py(tmp_path, "venv/lib.py")
    _make_py(tmp_path, "__pycache__/x.py")
    opt = ContextOptimizer(str(tmp_path), "task", limit_tokens=1000)
    opt._collect_python_files()
    names = {p.split("/")[-1] for p in opt.all_files}
    assert "a.py" in names
    assert "lib.py" not in names
    assert "x.py" not in names


def test_user_ignore_dirs(tmp_path):
    _make_py(tmp_path, "a.py")
    _make_py(tmp_path, ".pig/backups/before/x.py")
    _make_py(tmp_path, "logs/y.py")
    opt = ContextOptimizer(
        str(tmp_path),
        "task",
        limit_tokens=1000,
        ignore_list=".pig, logs",
    )
    opt._collect_python_files()
    names = {p.split("/")[-1] for p in opt.all_files}
    assert "a.py" in names
    assert "x.py" not in names
    assert "y.py" not in names


def test_user_ignore_files(tmp_path):
    _make_py(tmp_path, "a.py")
    _make_py(tmp_path, "project_context.py")
    opt = ContextOptimizer(
        str(tmp_path),
        "task",
        limit_tokens=1000,
        ignore_list="project_context",
    )
    opt._collect_python_files()
    names = {p.split("/")[-1] for p in opt.all_files}
    assert "a.py" in names
    assert "project_context.py" not in names


def test_ignore_list_accepts_string_with_spaces(tmp_path):
    _make_py(tmp_path, "a.py")
    _make_py(tmp_path, ".pig/z.py")
    opt = ContextOptimizer(
        str(tmp_path),
        "task",
        limit_tokens=1000,
        ignore_list=" .pig , junk , ",
    )
    assert opt.ignore_list == [".pig", "junk"]
