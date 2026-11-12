"""LMStudioModelsWorker — async fetch + cache (C7b).

Симметричен OllamaModelsWorker (D3): QThread worker, кеш в
app_config.json под ключом lmstudio_models_cache с TTL 60 сек.
"""

from __future__ import annotations

import time

from PySide6.QtCore import QObject, Signal, Slot

_MODELS_CACHE_TTL_SEC = 60
_CACHE_KEY = "lmstudio_models_cache"


class LMStudioModelsWorker(QObject):
    done = Signal(list)  # list[str]
    error = Signal(str)

    def __init__(
        self,
        base_url: str = "http://localhost:1234/v1",
        api_key: str = "lm-studio",
        parent: QObject | None = None,
    ):
        super().__init__(parent)
        self._base_url = base_url
        self._api_key = api_key

    @Slot()
    def run(self) -> None:
        try:
            from ...core.lmstudio_client import get_lmstudio_models

            models = get_lmstudio_models(self._base_url, self._api_key)
            self.done.emit(list(models))
        except Exception as e:
            self.error.emit(str(e))


def get_cached_models(settings: dict) -> list[str]:
    """Закешированный список моделей LM Studio (пустой при отсутствии)."""
    cache = settings.get(_CACHE_KEY, {})
    if not isinstance(cache, dict):
        return []
    models = cache.get("models", [])
    if not isinstance(models, list):
        return []
    return [str(m) for m in models]


def cache_is_fresh(settings: dict) -> bool:
    """True, если кеш моложе TTL."""
    cache = settings.get(_CACHE_KEY, {})
    if not isinstance(cache, dict):
        return False
    try:
        ts = float(cache.get("ts", 0))
    except (TypeError, ValueError):
        return False
    return (time.time() - ts) < _MODELS_CACHE_TTL_SEC


def save_models_to_cache(settings: dict, models: list[str]) -> None:
    """Обновить кеш in-place (вызывающий сохраняет settings)."""
    settings[_CACHE_KEY] = {
        "models": [str(m) for m in models],
        "ts": time.time(),
    }
