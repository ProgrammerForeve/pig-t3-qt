# ADR-004: QAbstractItemModel для дерева и таблиц

## Статус
Принято (2026-11)

## Контекст
Legacy использовал `ttk.Treeview` с ручным управлением чекбоксами через
текстовые префиксы `✅`/`⬜` (функция `_toggle_item`). Это хрупкая
реализация: состояние чекбокса — часть display text, а не отдельное
данное.

## Решение
- Дерево проекта — `ProjectTreeModel(QAbstractItemModel)` с
  `Qt.CheckStateRole` и tristate-состоянием (`Checked`/`Unchecked`/
  `PartiallyChecked`).
- Таблица качества — `QualityTableModel(QAbstractTableModel)` +
  `QSortFilterProxyModel` для сортировки.
- Состояние хранится в модели, не в тексте.

## Обоснование
- Нативный вид чекбоксов Qt
- Сортировка через `QSortFilterProxyModel` — без ручной перестройки
- Легко тестируется (`model.setData`, `model.data`)

## Последствия
- UX-компромисс: клик по любой части строки переключает чекбокс
  (кроме треугольника раскрытия) — реализовано в `ProjectTreeView.mousePressEvent`
- Persistence формата совместим с legacy: `ui_tree_expanded` /
  `ui_tree_unchecked` — плоские списки относительных путей
