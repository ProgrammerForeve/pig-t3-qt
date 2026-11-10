"""Вкладка «📊 Анализ кода» (T-501..T-506).

QTableView + QualityTableModel + QSortFilterProxyModel.
Панель деталей ниже (QSplitter). Панель инструментов: «Сканировать»,
прогресс-бар, чекбокс «Свёрнутый вид», статус.
"""

from __future__ import annotations

import contextlib
import os

from PySide6.QtCore import QSortFilterProxyModel, Qt, QThread
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSplitter,
    QTableView,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from ...core.quality import FileMetrics
from ..models.quality_table import QualityTableModel
from ..workers.quality_worker import ScanWorker

_COLUMNS = ["path", "sloc", "cc", "mi", "score", "sec"]
_DETAIL_HEADER_STYLE = "font-size: 13px; font-weight: bold; padding: 4px; background: #0e639c; color: white;"


def _show_warning(parent, title: str, text: str) -> None:
    QMessageBox.warning(parent, title, text)


def _show_error(parent, title: str, text: str) -> None:
    QMessageBox.critical(parent, title, text)


class QualityTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._scan_thread: QThread | None = None
        self._scan_worker: ScanWorker | None = None
        self._current_sort_col: str = "path"
        self._sort_descending: bool = False

        self._setup_ui()
        self._connect_signals()

    # ---------- UI ----------

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        path_row = QHBoxLayout()
        path_row.addWidget(QLabel("Целевая папка:"))
        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText("Путь к проекту")
        path_row.addWidget(self.path_edit, 1)
        layout.addLayout(path_row)

        toolbar = QHBoxLayout()
        self.btn_scan = QPushButton("🚀 ЗАПУСТИТЬ АНАЛИЗ")
        self.status_label = QLabel("Нажмите кнопку для начала аудита")
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setMaximumWidth(280)
        self.cb_compact = QCheckBox("Свёрнутый вид (только важные)")

        toolbar.addWidget(self.btn_scan)
        toolbar.addWidget(self.progress_bar)
        toolbar.addWidget(self.status_label, 1)
        toolbar.addWidget(self.cb_compact)
        layout.addLayout(toolbar)

        splitter = QSplitter(Qt.Orientation.Vertical)
        layout.addWidget(splitter, 1)

        self.model = QualityTableModel()
        self.proxy = QSortFilterProxyModel()
        self.proxy.setSourceModel(self.model)
        self.proxy.setSortRole(Qt.ItemDataRole.UserRole + 1)
        self.proxy.setDynamicSortFilter(True)

        self.table = QTableView()
        self.table.setModel(self.proxy)
        self.table.setSortingEnabled(True)
        self.table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableView.SelectionMode.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().setVisible(False)
        splitter.addWidget(self.table)

        self.details = QTextBrowser()
        self.details.setOpenExternalLinks(True)
        splitter.addWidget(self.details)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)

    def _connect_signals(self) -> None:
        self.btn_scan.clicked.connect(self._on_scan_clicked)
        self.cb_compact.toggled.connect(self._apply_compact_view)
        self.table.selectionModel().currentRowChanged.connect(self._on_row_changed)
        self.table.horizontalHeader().sectionClicked.connect(self._on_header_clicked)

    # ---------- Public ----------

    def set_path(self, path: str) -> None:
        self.path_edit.setText(path or "")

    def set_metrics(self, metrics: list[FileMetrics]) -> None:
        self.model.set_metrics(metrics)
        self._apply_compact_view()
        self._update_stats(metrics)

    def stop_scan(self) -> None:
        thread = self._scan_thread
        if thread is not None:
            with contextlib.suppress(RuntimeError):
                thread.requestInterruption()
                thread.quit()
                thread.wait(2000)

    # ---------- Scan flow ----------

    def _on_scan_clicked(self) -> None:
        if self._scan_thread is not None:
            with contextlib.suppress(RuntimeError):
                self._scan_thread.requestInterruption()
            return
        path = self.path_edit.text().strip()
        if not path or not os.path.isdir(path):
            _show_warning(self, "Ошибка", "Выберите существующую папку проекта.")
            return

        self.btn_scan.setText("⏳ ОСТАНОВИТЬ / ПЕРЕЗАПУСТИТЬ")
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.status_label.setText("Подготовка анализаторов...")
        self.details.setHtml("")

        self._scan_worker = ScanWorker(path)
        self._scan_thread = QThread(self)
        self._scan_worker.moveToThread(self._scan_thread)
        self._scan_thread.started.connect(self._scan_worker.run)
        self._scan_worker.progress.connect(self._on_progress)
        self._scan_worker.done.connect(self._on_scan_done)
        self._scan_worker.error.connect(self._on_scan_error)
        self._scan_worker.cancelled.connect(self._on_scan_cancelled)
        for sig in (
            self._scan_worker.done,
            self._scan_worker.error,
            self._scan_worker.cancelled,
        ):
            sig.connect(self._cleanup_thread)
        self._scan_thread.start()

    def _on_progress(self, percent: int, msg: str) -> None:
        self.progress_bar.setValue(percent)
        self.status_label.setText(f"{msg} ({percent}%)")

    def _on_scan_done(self, metrics: list) -> None:
        self.set_metrics(metrics)

    def _on_scan_error(self, msg: str) -> None:
        self.status_label.setText(f"❌ {msg}")
        _show_error(self, "Ошибка", msg)

    def _on_scan_cancelled(self) -> None:
        self.status_label.setText("⏹ Сканирование отменено")

    def _cleanup_thread(self, *_args) -> None:
        thread = self._scan_thread
        self._scan_thread = None
        self._scan_worker = None
        if thread is not None:
            with contextlib.suppress(RuntimeError):
                thread.quit()
                thread.wait(3000)
        self.btn_scan.setText("🚀 ЗАПУСТИТЬ АНАЛИЗ")
        self.progress_bar.setVisible(False)

    # ---------- Stats (T-506) ----------

    def _update_stats(self, metrics: list) -> None:
        total = len(metrics)
        if total == 0:
            self.status_label.setText("Python файлы не найдены.")
            self.status_label.setStyleSheet("color: #cccccc;")
            return
        reds = sum(1 for m in metrics if m.overall_status == "red")
        yellows = sum(1 for m in metrics if m.overall_status == "yellow")
        greens = total - reds - yellows
        self.status_label.setText(f"Всего: {total} | 🔴 Critical: {reds} | ⚠️ Warnings: {yellows} | ✅ Clean: {greens}")
        self.status_label.setStyleSheet("color: #e06c75;" if reds > 0 else "color: #98c379;")

    # ---------- Details (T-503) ----------

    def _on_row_changed(self, current, _previous) -> None:
        source_row = self.proxy.mapToSource(current).row()
        metric = self.model.metrics_at(source_row)
        if metric is None:
            self.details.setHtml("")
            return
        self.details.setHtml(self._build_details_html(metric))

    def _build_details_html(self, metric: FileMetrics) -> str:
        def _row(label: str, value: str, color: str) -> str:
            return (
                f'<tr><td style="color:#cccccc;">{label}</td>'
                f'<td style="color:{color}; font-weight:bold;">{value}</td></tr>'
            )

        status_color = {
            "green": "#98c379",
            "yellow": "#e5c07b",
            "red": "#e06c75",
        }
        parts = [
            f'<div style="{_DETAIL_HEADER_STYLE}">📄 {metric.path}</div>',
            "<table cellspacing='6'>",
            _row(
                "Cyclomatic Complex.",
                f"{metric.complexity:.1f}",
                status_color[metric.status_cc],
            ),
            _row(
                "Maintainability I.",
                f"{metric.maintainability:.1f}",
                status_color[metric.status_mi],
            ),
            _row(
                "Linter Score",
                f"{metric.pylint_score:.1f}",
                status_color[metric.status_pylint],
            ),
            _row(
                "Security Issues",
                str(metric.security_issues),
                status_color[metric.status_security],
            ),
            "</table>",
        ]

        if not metric.issues:
            parts.append("<p style='color:#98c379;'>✨ Great Job! No issues detected.</p>")
        else:
            parts.append(
                f"<p style='color:#e5c07b; font-weight:bold;'>🔍 Найдено {len(metric.issues)} проблем:</p><ol>"
            )
            for issue in metric.issues:
                color = {
                    "error": "#e06c75",
                    "warning": "#e5c07b",
                    "info": "#61afef",
                }.get(issue.severity, "#cccccc")
                parts.append(
                    f"<li><span style='color:{color};'>"
                    f"[{issue.tool.upper()}] строка {issue.line}: "
                    f"{issue.msg}</span></li>"
                )
            parts.append("</ol>")

        return "".join(parts)

    # ---------- Compact view (T-505) ----------

    def _apply_compact_view(self, *_args) -> None:
        if self.cb_compact.isChecked():
            target = self._current_sort_col
            visible = {"path", "cc"} if target == "path" else {"path", target}
            for i, col in enumerate(_COLUMNS):
                self.table.setColumnHidden(i, col not in visible)
        else:
            for i in range(len(_COLUMNS)):
                self.table.setColumnHidden(i, False)

    def _on_header_clicked(self, column: int) -> None:
        self._current_sort_col = _COLUMNS[column]
        order = self.table.horizontalHeader().sortIndicatorOrder()
        self._sort_descending = order == Qt.SortOrder.DescendingOrder
        if self.cb_compact.isChecked():
            self._apply_compact_view()
