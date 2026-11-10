"""Главное окно: QMainWindow + QTabWidget.

Вкладка «Генератор» реализована (T-101..T-103), остальные — заглушки
до соответствующих задач (T-201, T-302, T-401, T-501).
"""

from __future__ import annotations

from importlib import metadata

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QLabel,
    QMainWindow,
    QMessageBox,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ..config import ConfigManager
from .config_compat import save_migrated
from .tabs.editor import EditorTab
from .tabs.generator import GeneratorTab
from .tabs.info import InfoTab
from .tabs.quality import QualityTab

_TAB_KEYS = ["generator", "info", "editor", "plan", "quality"]

_TAB_TITLES = {
    "generator": "🏠 Генератор",
    "info": "🎓 Инфо / JSON Specs",
    "editor": "✏️ Редактор (JSON Patcher)",
    "plan": "📝 План проекта",
    "quality": "📊 Анализ кода",
}


class MainWindow(QMainWindow):
    def __init__(self, config: ConfigManager, settings: dict):
        super().__init__()
        self.config = config
        self.settings = settings

        self._setup_window()
        self._setup_tabs()
        self._setup_statusbar()

    def _setup_window(self) -> None:
        self.setWindowTitle("AI Context Generator & Patcher (PySide6)")

        from PySide6.QtWidgets import QApplication

        screen = QApplication.primaryScreen()
        if screen is not None:
            avail = screen.availableGeometry()
            w = min(1200, max(600, avail.width() - 80))
            h = min(950, max(400, avail.height() - 80))
            self.resize(w, h)
            self.move(
                avail.left() + (avail.width() - w) // 2,
                avail.top() + (avail.height() - h) // 2,
            )
        else:
            self.resize(1200, 950)

        self.setMinimumSize(600, 400)

    def _setup_tabs(self) -> None:
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.setCentralWidget(self.tabs)

        self._tab_widgets = {}
        for key in _TAB_KEYS:
            if key == "generator":
                widget = GeneratorTab(self.settings)
                widget.settings_changed.connect(self._on_generator_settings_changed)
            elif key == "info":
                widget = InfoTab()
            elif key == "editor":
                widget = EditorTab(self.settings)
            elif key == "quality":
                widget = QualityTab()
            else:
                widget = self._make_placeholder(_TAB_TITLES[key])

        self.btn_settings = QToolButton()
        self.btn_settings.setText("⚙️")
        self.btn_settings.setToolTip("Настройки (этап 7)")
        self.btn_settings.setAutoRaise(True)
        self.btn_settings.clicked.connect(self._open_settings)
        self.tabs.setCornerWidget(self.btn_settings, Qt.Corner.TopRightCorner)

        self._apply_tab_visibility()

    def _make_placeholder(self, text: str) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        label = QLabel(f"{text}\n\n(в разработке)")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(label)
        return widget

    def _apply_tab_visibility(self) -> None:
        vis = self.settings.get("tabs_visibility", {})
        for i, key in enumerate(_TAB_KEYS):
            self.tabs.setTabVisible(i, vis.get(key, True))

    def _setup_statusbar(self) -> None:
        self.status_var = QLabel("Готов к работе")
        self.version_label = QLabel(self._get_version())
        self.statusBar().addWidget(self.status_var, 1)
        self.statusBar().addPermanentWidget(self.version_label)

    def _get_version(self) -> str:
        try:
            return f"v{metadata.version('pig-t3')}"
        except Exception:
            return "v?.?.?"

    def _open_settings(self) -> None:
        QMessageBox.information(
            self,
            "Настройки",
            "Диалог настроек будет реализован на этапе 7.",
        )

    def _on_generator_settings_changed(self) -> None:
        """Синхронизирует поля вкладки «Генератор» в self.settings
        и прокидывает путь в редактор / анализ кода."""
        generator = self._tab_widgets.get("generator")
        if generator is None:
            return
        self.settings.update(generator.collect_settings())
        root = self.settings.get("root_folder", "")
        editor = self._tab_widgets.get("editor")
        if editor is not None and hasattr(editor, "set_path"):
            editor.set_path(root)
        quality = self._tab_widgets.get("quality")
        if quality is not None and hasattr(quality, "set_path"):
            quality.set_path(root)

    def closeEvent(self, event) -> None:
        try:
            generator = self._tab_widgets.get("generator")
            if generator is not None:
                # Останавливаем воркер ПЕРВЫМ, до сохранения —
                # иначе QThread child может быть уничтожен раньше
                # cleanup и дать qFatal abort.
                if hasattr(generator, "stop_generation"):
                    generator.stop_generation()
                if hasattr(generator, "stop_optimization"):
                    generator.stop_optimization()
            editor = self._tab_widgets.get("editor")
            if editor is not None and hasattr(editor, "stop_workers"):
                editor.stop_workers()
            quality = self._tab_widgets.get("quality")
            if quality is not None and hasattr(quality, "stop_scan"):
                quality.stop_scan()
            if hasattr(generator, "commit_recent_projects"):
                generator.commit_recent_projects()
            if hasattr(generator, "capture_tree_state"):
                self.settings.update(generator.capture_tree_state())
            save_migrated(self.config, self.settings)
        except Exception as e:
            print(f"Ошибка сохранения настроек при выходе: {e}")
        event.accept()
