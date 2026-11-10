# Architecture Decision Records

Формат: [MADR](https://adr.github.io/madr/) (Markdown ADR, упрощённый).
Каждый ADR фиксирует одно решение, принятое при миграции GUI на PySide6.

| # | Решение | Статус |
| :--- | :--- | :--- |
| [001](001-pyside6.md) | PySide6 как GUI-фреймворк | Принято |
| [002](002-qt-material-themes.md) | Qt-Material для тем | Принято |
| [003](003-qthread-signals.md) | QThread + сигналы/слоты | Принято |
| [004](004-qabstractitemmodel.md) | QAbstractItemModel для дерева и таблиц | Принято |
| [005](005-migration-scope.md) | Scope миграции (только GUI) | Принято |
| [006](006-config-compat.md) | Совместимость конфигов | Принято |
| [007](007-native-hotkeys.md) | Нативные Qt горячие клавиши | Принято |
| [008](008-dialog-wrappers.md) | Module-level обёртки диалогов | Принято |
| [009](009-quintptr-internalid.md) | quintptr internalId вместо Python internalPointer | Принято |
| [010](010-pytest-sessionfinish.md) | os._exit в pytest_sessionfinish | Принято |