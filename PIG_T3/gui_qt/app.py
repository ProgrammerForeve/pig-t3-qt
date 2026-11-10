"""QApplication bootstrap + сплеш-скрин."""

import os
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import QApplication, QSplashScreen

from ..config import ConfigManager
from .config_compat import load_and_migrate
from .main_window import MainWindow
from .theme import apply_theme


def _resource_path(name: str) -> str | None:
    """Ищет ресурс: сначала в sys._MEIPASS (frozen), затем рядом с PIG_T3/."""
    candidates = []
    if hasattr(sys, "_MEIPASS"):
        candidates.append(os.path.join(sys._MEIPASS, name))
    pkg_root = Path(__file__).resolve().parent.parent  # PIG_T3/
    candidates.append(str(pkg_root / name))
    for path in candidates:
        if os.path.exists(path):
            return path
    return None


def run_gui_qt() -> int:
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)

    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("PIG-T3")

    # Иконка окна
    icon_path = _resource_path("icon.png")
    if icon_path:
        app.setWindowIcon(QIcon(icon_path))

    # Загрузка + миграция конфига
    config = ConfigManager()
    settings = load_and_migrate(config)
    apply_theme(app, settings["theme"])

    # Сплеш-скрин (если есть logo.png)
    splash = None
    # PIG_NO_SPLASH=1 — диагностический режим без splash (на случай,
    # если краш происходит при splash.finish + deleteLater).
    if not os.environ.get("PIG_NO_SPLASH"):
        logo_path = _resource_path("logo.png")
        if logo_path:
            pixmap = QPixmap(logo_path)
            if not pixmap.isNull():
                screen = app.primaryScreen().size()
                target_h = screen.height() // 5
                if pixmap.height() > target_h:
                    pixmap = pixmap.scaledToHeight(target_h, Qt.TransformationMode.SmoothTransformation)
                splash = QSplashScreen(pixmap)
                splash.show()
                app.processEvents()

    window = MainWindow(config, settings)
    # Держим splash живым как атрибут window, чтобы GC не освободил
    # C++ объект раньше, чем event loop обработает deleteLater.
    window._splash = splash

    def _show():
        window.show()
        if splash is not None:
            try:
                splash.finish(window)
            except Exception as e:
                print(f"splash.finish error: {e}")

    if splash is not None:
        QTimer.singleShot(1000, _show)
    else:
        _show()

    return app.exec()
