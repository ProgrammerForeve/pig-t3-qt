# ADR-010: os._exit в pytest_sessionfinish

## Статус
Принято (2026-11)

## Контекст
Даже после ADR-009 при прогоне полного сьюта `198 passed` сменялось
на `free(): invalid size` + `Fatal Python error: Aborted`.
`faulthandler` показал `Garbage-collecting <no Python frame>` — краш в
финальном GC при интерпретатор-shutdown. Shiboken уничтожает C++
Qt-объекты (QApplication, QThread, QObject) в порядке, который не
согласован с Qt-очисткой.

## Решение
Форсированный выход в `pytest_sessionfinish` через
`os._exit(exitstatus)`, минуя atexit, финальный GC и shiboken cleanup.
Аннотировано `@pytest.hookimpl(tryfirst=True)`, чтобы выполниться до
pytest-qt sessionfinish.

## Обоснование
- Процесс завершается сразу после тестов; ОС освобождает память целиком.
- Порядок C++ деструкторов больше не важен — их вообще нет.
- `exit: 0` для CI.

## Компромиссы
- Не срабатывают atexit-хуки.
- `coverage` reporter может ругаться (запись в `.coverage` в самом конце).
- `pytest-xdist` не увидит результаты (в CI `-n auto` не нужен).

Приняли: стабильность CI важнее post-test cleanup внутри интерпретатора.

## Реализация
В `tests/conftest.py`:

    @pytest.hookimpl(tryfirst=True)
    def pytest_sessionfinish(session, exitstatus):
        import contextlib
        import os
        import sys
        with contextlib.suppress(Exception):
            sys.stdout.flush()
            sys.stderr.flush()
        os._exit(int(exitstatus))

При локальной отладке `-s` результаты pytest уже напечатаны до
`os._exit`, отладочный вывод работает как обычно.

## Последствия
- Любой новый pytest-хук shutdown (`pytest_sessionfinish`,
  `pytest_unconfigure`) должен быть либо `tryfirst`, либо не
  рассчитывать на выполнение после нашего `os._exit`.
