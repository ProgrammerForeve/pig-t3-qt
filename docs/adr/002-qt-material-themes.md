# ADR-002: Qt-Material для тем

## Статус
Принято (2026-11)

## Контекст
Legacy Tkinter-GUI поддерживал 5 тем: `dark`, `light`, `pink`,
`dark_pink`, `eye_care`. В Qt есть несколько подходов к стилизации:
Qt-Material, QDarkStyleSheet, кастомный QSS.

## Решение
Использовать **Qt-Material** как базовый движок тем.
- `dark` → `dark_blue.xml`
- `light` → `light_blue.xml`
Кастомные темы (`pink`, `eye_care`, `dark_pink`) **удалены** в v1.

## Обоснование
- Qt-Material даёт современный flat-дизайн «из коробки»
- Не требует ручной стилизации десятков виджетов
- Активно поддерживается, интегрируется через `apply_stylesheet`

## Последствия
- При загрузке конфига — миграция: `pink`/`eye_care` → `light`,
  `dark_pink` → `dark` (реализовано в `gui_qt/theme.py:resolve_theme`)
- `dark`/`light` — только базовые, без выбора цветового акцента
  (расширение возможно добавлением `dark_teal.xml`/`light_teal.xml` в
  `_QT_MATERIAL`)
