"""Smoke test для PyInstaller spec (T-703).

Проверяет, что spec существует и содержит ключевые поля.
Реальная сборка .exe — вне scope pytest (медленно, требует
полного окружения); это защита от случайного удаления/поломки
файла.
"""

from pathlib import Path

_SPEC = Path(__file__).parent.parent / "pig_t3.spec"


def test_spec_file_exists():
    assert _SPEC.exists(), f"{_SPEC} not found"


def test_spec_has_entry_point():
    content = _SPEC.read_text(encoding="utf-8")
    assert '"run.py"' in content or "'run.py'" in content


def test_run_py_exists():
    run_py = _SPEC.parent / "run.py"
    assert run_py.exists(), f"{run_py} not found"
    content = run_py.read_text(encoding="utf-8")
    assert "from PIG_T3.main import main" in content


def test_spec_has_pyside6_hidden_imports():
    content = _SPEC.read_text(encoding="utf-8")
    assert "PySide6.QtWidgets" in content
    assert "PySide6.QtCore" in content


def test_spec_bundles_qt_material():
    content = _SPEC.read_text(encoding="utf-8")
    assert "qt_material" in content
    assert "qt_material/resources" in content


def test_spec_bundles_icons():
    content = _SPEC.read_text(encoding="utf-8")
    assert "logo.png" in content
    assert "icon.png" in content


def test_spec_is_windowed():
    content = _SPEC.read_text(encoding="utf-8")
    assert "console=False" in content


def test_spec_name():
    content = _SPEC.read_text(encoding="utf-8")
    assert 'name="PIG-T3"' in content


def test_spec_excludes_tkinter():
    content = _SPEC.read_text(encoding="utf-8")
    assert '"tkinter"' in content
