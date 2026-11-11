"""C7a: LM Studio client (OpenAI-совместимый API)."""

from __future__ import annotations

import pytest

from PIG_T3.core import lmstudio_client as lms


class _FakeResponse:
    def __init__(self, json_data, status=200):
        self._json = json_data
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests

            raise requests.HTTPError(f"status {self.status_code}")

    def json(self):
        return self._json


# ---------- get_lmstudio_models ----------


def test_get_models_ok(monkeypatch):
    monkeypatch.setattr(
        lms.requests,
        "get",
        lambda *a, **kw: _FakeResponse({"data": [{"id": "b-model"}, {"id": "a-model"}]}),
    )
    assert lms.get_lmstudio_models() == ["a-model", "b-model"]


def test_get_models_empty(monkeypatch):
    monkeypatch.setattr(
        lms.requests,
        "get",
        lambda *a, **kw: _FakeResponse({"data": []}),
    )
    assert lms.get_lmstudio_models() == []


def test_get_models_500(monkeypatch):
    monkeypatch.setattr(
        lms.requests,
        "get",
        lambda *a, **kw: _FakeResponse({}, status=500),
    )
    assert lms.get_lmstudio_models() == []


def test_get_models_connection_error(monkeypatch):
    def boom(*a, **kw):
        import requests

        raise requests.ConnectionError("refused")

    monkeypatch.setattr(lms.requests, "get", boom)
    assert lms.get_lmstudio_models() == []


def test_get_models_ignores_items_without_id(monkeypatch):
    monkeypatch.setattr(
        lms.requests,
        "get",
        lambda *a, **kw: _FakeResponse({"data": [{"id": "a"}, {"no_id": True}]}),
    )
    assert lms.get_lmstudio_models() == ["a"]


# ---------- is_lmstudio_available ----------


def test_available_true(monkeypatch):
    monkeypatch.setattr(
        lms.requests,
        "get",
        lambda *a, **kw: _FakeResponse({"data": []}, status=200),
    )
    assert lms.is_lmstudio_available() is True


def test_available_false_on_500(monkeypatch):
    monkeypatch.setattr(
        lms.requests,
        "get",
        lambda *a, **kw: _FakeResponse({}, status=500),
    )
    assert lms.is_lmstudio_available() is False


def test_available_false_on_exception(monkeypatch):
    def boom(*a, **kw):
        raise Exception("boom")

    monkeypatch.setattr(lms.requests, "get", boom)
    assert lms.is_lmstudio_available() is False


# ---------- LMStudioClient.chat ----------


def test_chat_returns_content(monkeypatch):
    captured = {}

    def fake_post(url, json, headers, timeout):
        captured["url"] = url
        captured["model"] = json["model"]
        captured["messages"] = json["messages"]
        captured["auth"] = headers.get("Authorization")
        return _FakeResponse({"choices": [{"message": {"content": "hello"}}]})

    monkeypatch.setattr(lms.requests, "post", fake_post)
    client = lms.LMStudioClient("qwen2.5-coder", "http://x:1234/v1", "key")
    assert client.chat("hi") == "hello"
    assert captured["url"] == "http://x:1234/v1/chat/completions"
    assert captured["model"] == "qwen2.5-coder"
    assert captured["messages"] == [{"role": "user", "content": "hi"}]
    assert captured["auth"] == "Bearer key"


def test_chat_http_error_raises(monkeypatch):
    monkeypatch.setattr(
        lms.requests,
        "post",
        lambda *a, **kw: _FakeResponse({}, status=500),
    )
    client = lms.LMStudioClient("m")
    with pytest.raises(RuntimeError, match="chat failed"):
        client.chat("hi")


def test_chat_empty_choices_raises(monkeypatch):
    monkeypatch.setattr(
        lms.requests,
        "post",
        lambda *a, **kw: _FakeResponse({"choices": []}),
    )
    client = lms.LMStudioClient("m")
    with pytest.raises(RuntimeError, match="no choices"):
        client.chat("hi")


def test_chat_empty_content_raises(monkeypatch):
    monkeypatch.setattr(
        lms.requests,
        "post",
        lambda *a, **kw: _FakeResponse({"choices": [{"message": {"content": ""}}]}),
    )
    client = lms.LMStudioClient("m")
    with pytest.raises(RuntimeError, match="empty content"):
        client.chat("hi")
