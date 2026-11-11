"""LM Studio client — OpenAI-совместимый API на localhost:1234/v1.

LM Studio (https://lmstudio.ai) предоставляет OpenAI-совместимый
сервер: /v1/chat/completions, /v1/embeddings, /v1/models. Протокол
отличается от Ollama (/api/chat, /api/embed, /api/tags), поэтому
отдельный клиент, а не обёртка над OllamaClient.

Публичный API:
- get_lmstudio_models(base_url, api_key) -> list[str]
- is_lmstudio_available(base_url, api_key) -> bool
- LMStudioClient(model, base_url, api_key, timeout).chat(prompt) -> str
"""
from __future__ import annotations

import logging

import requests


log = logging.getLogger("pig_t3.lmstudio_client")


_DEFAULT_BASE_URL = "http://localhost:1234/v1"
_DEFAULT_API_KEY = "lm-studio"
_DEFAULT_TIMEOUT = 600
_MODELS_PROBE_TIMEOUT = 2


def _headers(api_key: str) -> dict[str, str]:
    return {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }


def get_lmstudio_models(
    base_url: str = _DEFAULT_BASE_URL,
    api_key: str = _DEFAULT_API_KEY,
    timeout: int = _MODELS_PROBE_TIMEOUT,
) -> list[str]:
    """GET /v1/models → list model IDs. [] при любой ошибке."""
    url = f"{base_url.rstrip('/')}/models"
    try:
        r = requests.get(url, headers=_headers(api_key), timeout=timeout)
        if r.status_code != 200:
            return []
        data = r.json()
        return sorted(
            item.get("id", "")
            for item in data.get("data", [])
            if item.get("id")
        )
    except Exception as e:  # noqa: BLE001
        log.debug("get_lmstudio_models failed: %s", e)
        return []


def is_lmstudio_available(
    base_url: str = _DEFAULT_BASE_URL,
    api_key: str = _DEFAULT_API_KEY,
    timeout: int = _MODELS_PROBE_TIMEOUT,
) -> bool:
    """GET /v1/models → 200? Короткий timeout, никогда не бросает."""
    try:
        r = requests.get(
            f"{base_url.rstrip('/')}/models",
            headers=_headers(api_key),
            timeout=timeout,
        )
        return r.status_code == 200
    except Exception:
        return False


class LMStudioClient:
    """Chat через /v1/chat/completions (OpenAI-формат)."""

    def __init__(
        self,
        model: str,
        base_url: str = _DEFAULT_BASE_URL,
        api_key: str = _DEFAULT_API_KEY,
        timeout: int = _DEFAULT_TIMEOUT,
    ):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    def chat(self, prompt: str) -> str:
        """POST /v1/chat/completions. Возвращает choices[0].message.content.

        Бросает RuntimeError с понятным сообщением при HTTP-ошибке,
        пустом choices или пустом content.
        """
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.7,
            "stream": False,
        }
        try:
            r = requests.post(
                f"{self.base_url}/chat/completions",
                json=payload,
                headers=_headers(self.api_key),
                timeout=self.timeout,
            )
            r.raise_for_status()
            data = r.json()
        except requests.RequestException as e:
            raise RuntimeError(
                f"LM Studio chat failed (model={self.model}): {e}. "
                f"Проверьте: LM Studio запущен, server на {self.base_url}, "
                f"модель '{self.model}' загружена."
            ) from e
        choices = data.get("choices", [])
        if not choices:
            raise RuntimeError(
                f"LM Studio returned no choices (model={self.model}): "
                f"{str(data)[:200]}"
            )
        content = choices[0].get("message", {}).get("content", "")
        if not content:
            raise RuntimeError(
                f"LM Studio returned empty content (model={self.model})"
            )
        return str(content)
