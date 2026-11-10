"""Вкладка «🎓 Инфо / JSON Specs» (T-201 + T-202).

QSplitter: слева QListWidget с разделами, справа QTextBrowser
с HTML-контентом. Контент перенесён из legacy _get_text_* без
потери текста; стили нейтральные, чтобы читалось в обеих темах.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QListWidget,
    QListWidgetItem,
    QSplitter,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

log = logging.getLogger("pig_t3.gui_qt.tabs.info")

_SECTIONS = [
    ("basic", "🔰 БАЗОВАЯ ИНФО"),
    ("mechanics", "🔧 Механика вкладок"),
    ("json", "🧬 JSON Структура"),
    ("metrics", "📊 Расшифровка метрик"),
    ("ollama", "🤖 Ollama и Авто-фикс"),
]


class InfoTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()
        self._populate()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(splitter)

        self.nav = QListWidget()
        self.nav.setMaximumWidth(240)
        self.nav.currentRowChanged.connect(self._on_section_changed)
        splitter.addWidget(self.nav)

        self.content = QTextBrowser()
        self.content.setOpenExternalLinks(True)
        splitter.addWidget(self.content)

        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([220, 700])

    def _populate(self) -> None:
        for _key, title in _SECTIONS:
            QListWidgetItem(title, self.nav)
        if self.nav.count() > 0:
            self.nav.setCurrentRow(0)

    def _on_section_changed(self, row: int) -> None:
        if row < 0 or row >= len(_SECTIONS):
            return
        key = _SECTIONS[row][0]
        self.content.setHtml(self._get_content(key))

    # ---------- Content ----------

    def _get_content(self, key: str) -> str:
        return {
            "basic": self._text_basic(),
            "mechanics": self._text_mechanics(),
            "json": self._text_json(),
            "metrics": self._text_metrics(),
            "ollama": self._text_ollama(),
        }.get(key, self._text_basic())

    def _text_basic(self) -> str:
        return """
<h1>🔰 БАЗОВАЯ ИНСТРУКЦИЯ</h1>
<h2>1. Вкладка «Генератор»</h2>
<p>Создаёт «контекст» — единый файл со всем кодом вашего проекта.</p>
<ul>
  <li>Выберите папку проекта.</li>
  <li>Настройте расширения и ignore-лист.</li>
  <li>Нажмите «ГЕНЕРИРОВАТЬ КОНТЕКСТ».</li>
  <li>Отправьте полученный .txt в чат с AI.</li>
</ul>
<p>💡 Совет: включите «Нумеровать строки» и «Инструкцию для AI» — точнее редактирование.</p>
<h2>2. Вкладка «Редактор»</h2>
<p>Принимает JSON-ответ от LLM и применяет изменения.</p>
<ul>
  <li>Скопируйте JSON из ответа AI.</li>
  <li>Вставьте в поле редактора.</li>
  <li>Проверьте → Примените.</li>
</ul>
<h2>3. Вкладка «Анализ кода»</h2>
<p>Локальный аудит без отправки кода в сеть.</p>
<ul>
  <li>Нажмите «Запустить анализ».</li>
  <li>Смотрите метрики и детали проблем.</li>
</ul>
"""

    def _text_mechanics(self) -> str:
        return """
<h1>🔧 Как это работает</h1>
<h2>Генератор контекста (Analyzer)</h2>
<p>Обходит дерево файлов, игнорируя папки из «Ignore». Собирает код
в единый файл с XML-тегами <code>&lt;file path="..."&gt;</code>.</p>
<h2>Патчер (Patcher)</h2>
<ol>
  <li>Разбирает входящий JSON.</li>
  <li>Для «edit» сортирует операции снизу вверх (чтобы не сбить индексы).</li>
  <li>Безопасно перезаписывает файлы, делает бэкапы в
      <code>.pig/backups/</code>.</li>
</ol>
<h2>Анализатор качества (Scanner)</h2>
<p>Запускает subprocess: Radon CC, Radon MI, Pylint, Bandit. Результаты
парсятся из JSON и сводятся в таблицу.</p>
<h2>Оптимизатор контекста</h2>
<p>Строит граф зависимостей (imports), BFS-обход, PageRank. Жадный отбор
по комбинированному весу (LLM / PageRank / Cyclomatic Complexity).</p>
"""

    def _text_json(self) -> str:
        return """
<h1>🧬 JSON-структура для редактирования</h1>
<p>Чтобы изменить код, AI должен вернуть строго этот формат:</p>
<pre>[
  {
    "action": "create",
    "path": "utils/helper.py",
    "explanation": "Utility module created",
    "content": "def help():\\n    pass"
  },
  {
    "action": "delete",
    "path": "old_file.py"
  },
  {
    "action": "move",
    "source": "old/f.py",
    "destination": "new/f.py"
  },
  {
    "action": "edit",
    "path": "main.py",
    "operations": [
       {"type": "replace_lines", "start": 10, "end": 12,
        "content": "    new_code()\\n    fixed_line()"},
       {"type": "insert_after_line", "line": 15,
        "content": "    log.debug('Debug info')"},
       {"type": "replace_text", "find": "old", "replace": "new"}
    ]
  },
  {
    "action": "mark_step_completed",
    "step_id": "step_1",
    "completed": false,
    "append_description": "Notes for next step"
  }
]</pre>
<p>⚠️ <b>ВАЖНО:</b> при <code>replace_lines</code> не включайте контекст
(соседние неизменные строки), иначе они продублируются. Для вставки
нового блока используйте <code>insert_after_line</code>.</p>
"""

    def _text_metrics(self) -> str:
        return """
<h1>📊 Расшифровка метрик</h1>
<h2>Cyclomatic Complexity (CC)</h2>
<p>Количество развилок (if/for/while).</p>
<ul>
  <li>1–10: простой код (🟢)</li>
  <li>11–20: умеренная сложность (⚠️)</li>
  <li>21+: сложный код, риск багов (🔴)</li>
</ul>
<h2>Maintainability Index (MI)</h2>
<p>Оценка читаемости (0–100).</p>
<ul>
  <li>&gt; 20: высокая (🟢)</li>
  <li>10–20: средняя (⚠️)</li>
  <li>&lt; 10: спагетти-код (🔴)</li>
</ul>
<h2>Linter Score (Pylint)</h2>
<ul>
  <li>&gt; 8.0: отлично (🟢)</li>
  <li>5.0–8.0: замечания (⚠️)</li>
  <li>&lt; 5.0: плохо (🔴)</li>
</ul>
<h2>Security Issues (Bandit)</h2>
<p>Поиск уязвимостей: зашитые пароли, injection, unsafe functions.</p>
<ul>
  <li>0: чисто (🟢)</li>
  <li>&gt; 0: найдены (🔴)</li>
</ul>
"""

    def _text_ollama(self) -> str:
        return """
<h1>🤖 Ollama и Auto-Fix</h1>
<p>Локальные нейросети через Ollama без отправки кода в интернет.</p>
<h2>Зачем</h2>
<p>Если JSON некорректен — приложение может попросить локальную модель
исправить синтаксис.</p>
<h2>Как настроить</h2>
<ol>
  <li>Установите Ollama (ollama.com).</li>
  <li>Скачайте модель: <code>ollama pull qwen2.5-coder</code>.</li>
  <li>Перезапустите приложение — модель появится в выпадающем списке
      редактора и диалога оптимизации.</li>
</ol>
<h2>Web API (DeepSeek / Gemini)</h2>
<p>Через Playwright: приложение поднимает браузер, авторизуется в вашем
профиле и отправляет промпт. Может потребоваться интерактивная
авторизация при первом запуске.</p>
<h2>BomjAPI (ручной)</h2>
<p>Открывает диалог «промпт/ответ». Полезно, когда нет API-ключа, но
есть веб-чат ChatGPT/Claude.</p>
"""
