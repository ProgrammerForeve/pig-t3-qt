"""Structured logging для PIG-T3 (D3).

Единая точка настройки root logger. Все модули используют
``logging.getLogger(__name__)``. Формат по умолчанию:
``HH:MM:SS [LEVEL] module: message``. --verbose в main переключает
уровень на DEBUG.
"""
from __future__ import annotations

import logging
import sys


_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
_DATE_FMT = "%H:%M:%S"
_LOGGER_NAME = "pig_t3"


def setup_logging(verbose: bool = False) -> logging.Logger:
    """Настроить root logger. Идемпотентно — повторный вызов
    не добавляет новых handler'ов.

    Возвращает logger 'pig_t3' — модули могут писать в него явно
    или через getLogger(__name__) (оба работают: propagate=True).
    """
    logger = logging.getLogger(_LOGGER_NAME)
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)
    logger.propagate = False

    if not logger.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(logging.Formatter(_FORMAT, datefmt=_DATE_FMT))
        logger.addHandler(handler)

    # Приглушить шумные сторонние библиотеки
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("watchdog").setLevel(logging.WARNING)
    logging.getLogger("playwright").setLevel(logging.WARNING)

    return logger


def get_logger(name: str) -> logging.Logger:
    """Удобная обёртка над logging.getLogger с общим префиксом."""
    return logging.getLogger(f"{_LOGGER_NAME}.{name}")
