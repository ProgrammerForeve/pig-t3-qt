"""Главное окно: QMainWindow + QTabWidget.

Вкладка «Генератор» реализована (T-101..T-103), остальные — заглушки
до соответствующих задач (T-201, T-302, T-401, T-501).
"""

from __future__ import annotations

import logging
from importlib import metadata

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QLabel,
    QMainWindow,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ..config import ConfigManager
from .config_compat import save_migrated
from .dialogs.settings_dialog import SettingsDialog
from .tabs.editor import EditorTab
from .tabs.generator import GeneratorTab
from .tabs.info import InfoTab
from .tabs.plan import PlanTab
from .tabs.quality import QualityTab

log = logging.getLogger("pig_t3.gui_qt.main_window")


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
        self._setup_shortcuts()

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
            elif key == "plan":
                widget = PlanTab(self.settings)
            else:
                widget = self._make_placeholder(_TAB_TITLES[key])

            self._tab_widgets[key] = widget
            self.tabs.addTab(widget, _TAB_TITLES[key])

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

        # Опрашиваем активную вкладку и показываем её локальный статус
        # в глобальном QStatusBar. Простая pull-модель: ни одна вкладка
        # не эмитит сигнал, достаточно прочитать widget.status_label.text().
        self._status_timer = QTimer(self)
        self._status_timer.setInterval(300)
        self._status_timer.timeout.connect(self._refresh_status_from_active_tab)
        self._status_timer.start()

        self.tabs.currentChanged.connect(lambda _idx: self._refresh_status_from_active_tab())

    def _refresh_status_from_active_tab(self) -> None:
        idx = self.tabs.currentIndex()
        if idx < 0 or idx >= len(_TAB_KEYS):
            return
        widget = self._tab_widgets.get(_TAB_KEYS[idx])
        if widget is None:
            return
        label = getattr(widget, "status_label", None)
        if label is not None:
            self.status_var.setText(label.text())

    def _get_version(self) -> str:
        try:
            return f"v{metadata.version('pig-t3')}"
        except Exception:
            return "v?.?.?"

    def _setup_shortcuts(self) -> None:
        """Глобальные горячие клавиши.

        ADR-007 — только осмысленные QShortcut для действий приложения.
        Ctrl+C/V/X/A/Z остаются нативными (QLineEdit и т.д.).
        """
        # Ctrl+1..5 — переключение вкладок
        for i in range(len(_TAB_KEYS)):
            sc = QShortcut(QKeySequence(f"Ctrl+{i + 1}"), self)
            sc.activated.connect(lambda idx=i: self.tabs.setCurrentIndex(idx))

        # Ctrl+, — настройки (стандарт GNOME/macOS)
        sc_settings = QShortcut(QKeySequence("Ctrl+,"), self)
        sc_settings.activated.connect(self._open_settings)

        # F5 — перейти на «Генератор» и обновить дерево
        sc_refresh = QShortcut(QKeySequence("F5"), self)
        sc_refresh.activated.connect(self._refresh_generator_tree)

    def _refresh_generator_tree(self) -> None:
        self.tabs.setCurrentIndex(_TAB_KEYS.index("generator"))
        generator = self._tab_widgets.get("generator")
        if generator is not None and hasattr(generator, "refresh_tree"):
            generator.refresh_tree()

    def _open_settings(self) -> None:
        dlg = SettingsDialog(self.settings, parent=self)
        if dlg.exec() != SettingsDialog.DialogCode.Accepted:
            return
        updated = dlg.get_updated_settings()
        self.settings.update(updated)

        # Применить без перезапуска
        self._apply_theme_now()
        self._apply_tab_visibility()
        self._apply_row_height()

    def _apply_theme_now(self) -> None:
        from PySide6.QtWidgets import QApplication

        from .theme import apply_theme

        apply_theme(QApplication.instance(), self.settings.get("theme", "dark"))

    def _apply_tab_visibility(self) -> None:
        vis = self.settings.get("tabs_visibility", {})
        for i, key in enumerate(_TAB_KEYS):
            self.tabs.setTabVisible(i, vis.get(key, True))

    def _apply_row_height(self) -> None:
        generator = self._tab_widgets.get("generator")
        if generator is not None and hasattr(generator, "tree_view"):
            h = int(self.settings.get("tree_row_height", 0) or 0)
            if h > 0:
                generator.tree_view.apply_row_height(h)

    def _on_generator_settings_changed(self) -> None:
        """Синхронизирует поля Генератора в self.settings и прокидывает
        root_folder в редактор / анализ / план."""
        try:
            generator = self._tab_widgets.get("generator")
            if generator is None:
                return
            self.settings.update(generator.collect_settings())
            root = self.settings.get("root_folder", "")
            for key in ("editor", "quality", "plan"):
                widget = self._tab_widgets.get(key)
                if widget is not None and hasattr(widget, "set_path"):
                    try:
                        widget.set_path(root)
                    except Exception as e:
                        log.warning(f"{key}.set_path error: {e}")
        except Exception as e:
            log.warning(f"_on_generator_settings_changed error: {e}")

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
            plan = self._tab_widgets.get("plan")
            if plan is not None and hasattr(plan, "stop_workers"):
                plan.stop_workers()
            if hasattr(generator, "commit_recent_projects"):
                generator.commit_recent_projects()
            if hasattr(generator, "capture_tree_state"):
                self.settings.update(generator.capture_tree_state())
            save_migrated(self.config, self.settings)
        except Exception as e:
            log.warning(f"Ошибка сохранения настроек при выходе: {e}")
        event.accept()
