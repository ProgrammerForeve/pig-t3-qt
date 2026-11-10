# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec для PIG-T3.

Собирает single-file исполняемый файл с PySide6 + qt-material + ресурсами.

Собрать:
    pyinstaller pig_t3.spec --noconfirm

Результат:
    dist/PIG-T3        (Linux)
    dist/PIG-T3.exe    (Windows)
"""
from pathlib import Path

block_cipher = None

project_root = Path(SPECPATH).resolve()
pkg_dir = project_root / "PIG_T3"

# ---------- Resources ----------
# Иконки и логотип лежат в PIG_T3/, `_resource_path` ищет их через
# sys._MEIPASS в frozen-режиме.
app_data = [
    (str(pkg_dir / "logo.png"), "."),
    (str(pkg_dir / "icon.png"), "."),
]

# qt-material stylesheets: PyInstaller не всегда видит XML-файлы
# из пакета. Собираем явно.
qt_material_data = []
try:
    import qt_material

    qt_material_dir = Path(qt_material.__file__).parent
    resources_dir = qt_material_dir / "resources"
    if resources_dir.exists():
        qt_material_data.append((str(resources_dir), "qt_material/resources"))
except Exception as e:
    print(f"qt_material not found: {e}")

# ---------- Hidden imports ----------
hiddenimports = [
    # PySide6 — подгружается динамически
    "PySide6.QtCore",
    "PySide6.QtGui",
    "PySide6.QtWidgets",
    "PySide6.QtNetwork",
    # qt-material
    "qt_material",
    # Context optimizer / quality scanner
    "networkx",
    "radon",
    "pylint",
    "bandit",
    "vulture",
    # Web LLM backends
    "requests",
    "playwright",
    "playwright.sync_api",
]

# ---------- Excludes ----------
# Не тащим в бандл legacy Tkinter-код и тяжёлые dev-зависимости.
excludes = [
    "tkinter",
    "test",
    "unittest",
    "pydoc_data",
    "lib2to3",
    "pip",
    "setuptools",
    "wheel",
    "pytest",
    "pytest_qt",
    "pytestqt",
    "mypy",
    "ruff",
]

a = Analysis(
    ["run.py"],
    pathex=[str(project_root)],
    binaries=[],
    datas=app_data + qt_material_data,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="PIG-T3",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,           # --noconsole
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(pkg_dir / "icon.png") if (pkg_dir / "icon.png").exists() else None,
)