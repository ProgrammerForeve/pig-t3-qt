"""OllamaModelsWorker — фоновое получение списка моделей Ollama.

`core/ollama_client.get_installed_models()` делает HTTP-запрос к
`localhost:11434` с таймаутом 2 сек. Синхронный вызов в __init__
диалога/вкладки блокирует UI на 2 сек, если Ollama не запущена.

Воркер запускается в QThread, эмитит done(models) / error(str).
Кэш (последний успешный список) хранится в app_config.json под
ключом ``ollama_models_cache`` с TTL 60 сек — stale cache показывается
сразу, фон обновляет.
"""

from __future__ import annotations

import time

from PySide6.QtCore import QObject, Signal, Slot

_MODELS_CACHE_TTL_SEC = 60
_CACHE_KEY = "ollama_models_cache"


class OllamaModelsWorker(QObject):
    done = Signal(list)  # list[str]
    error = Signal(str)

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)

    @Slot()
    def run(self) -> None:
        try:
            from ...core.ollama_client import get_installed_models

            models = get_installed_models()
            self.done.emit(list(models))
        except Exception as e:
            self.error.emit(str(e))


def get_cached_models(settings: dict) -> list[str]:
    """Вернуть закэшированный список моделей (пустой, если нет/битый)."""
    cache = settings.get(_CACHE_KEY, {})
    if not isinstance(cache, dict):
        return []
    models = cache.get("models", [])
    if not isinstance(models, list):
        return []
    return [str(m) for m in models]


def cache_is_fresh(settings: dict) -> bool:
    """True, если cache моложе TTL."""
    cache = settings.get(_CACHE_KEY, {})
    if not isinstance(cache, dict):
        return False
    try:
        ts = float(cache.get("ts", 0))
    except (TypeError, ValueError):
        return False
    return (time.time() - ts) < _MODELS_CACHE_TTL_SEC


def save_models_to_cache(settings: dict, models: list[str]) -> None:
    """Обновить cache in-place (вызывающий сохраняет settings)."""
    settings[_CACHE_KEY] = {
        "models": [str(m) for m in models],
        "ts": time.time(),
    }
