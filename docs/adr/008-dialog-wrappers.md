# ADR-008: Module-level обёртки диалогов

## Статус
Принято (2026-11)

## Контекст
При тестировании QMessageBox.information/critical/warning блокируют
прогон (модальны). Первая попытка — monkeypatch.setattr(QMessageBox,
"information", staticmethod(...)) — вызвала heap corruption
(`free(): invalid size`): патчинг статических методов shiboken-класса
рассинхронизирует внутренние кэши PySide6.

## Решение
В каждом модуле, где нужны диалоги, ввести module-level обёртки:

    def _show_info_dialog(parent, title, text):
        QMessageBox.information(parent, title, text)

Тесты патчат `module._show_info_dialog`, а не `QMessageBox` статик.

## Обоснование
- `monkeypatch.setattr(module, "_show_info_dialog", ...)` безопасен —
  это обычный Python-атрибут модуля.
- shiboken-класс не модифицируется.
- Autouse-фикстура в `tests/conftest.py` глушит диалоги для всех тестов.

## Последствия
- В коде диалогов: `_show_info`, `_show_error`, `_show_warning`,
  `_show_yes_no` на уровне модуля.
- Тесты, которым нужно проверить содержимое диалога, переопределяют
  обёртку локально через `monkeypatch`.
