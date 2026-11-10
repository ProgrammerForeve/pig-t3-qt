"""Day 5: majorchic_api — pure functions (no Playwright, no browser)."""

from __future__ import annotations

import pytest

from PIG_T3.utils.majorchic_api import (
    MajorchicAPIAdapter,
    _clean_text,
)

# ---------- _clean_text ----------


def test_clean_text_strips_outer():
    assert _clean_text("  hello  ") == "hello"


def test_clean_text_collapses_blank_lines():
    assert _clean_text("a\n\n\n\nb") == "a\n\nb"


def test_clean_text_preserves_indentation():
    text = "def f():\n    return 1\n"
    assert _clean_text(text) == text.strip()


def test_clean_text_empty():
    assert _clean_text("") == ""


def test_clean_text_only_whitespace():
    assert _clean_text("   \n\n  ") == ""


# ---------- MajorchicAPIAdapter._parse_payload ----------


@pytest.fixture
def adapter():
    return MajorchicAPIAdapter(backend="deepseek", headless=True)


def test_parse_payload_string(adapter):
    assert adapter._parse_payload("hello") == "hello"


def test_parse_payload_messages(adapter):
    result = adapter._parse_payload(
        {
            "messages": [
                {"role": "system", "content": "you are helpful"},
                {"role": "user", "content": "hi"},
            ]
        }
    )
    assert "system:" in result
    assert "you are helpful" in result
    assert "user:" in result
    assert "hi" in result


def test_parse_payload_prompt(adapter):
    assert adapter._parse_payload({"prompt": "p"}) == "p"


def test_parse_payload_promt_typo(adapter):
    # legacy fallback для опечатки
    assert adapter._parse_payload({"promt": "p"}) == "p"


def test_parse_payload_empty(adapter):
    assert adapter._parse_payload({}) == "Empty prompt"


# ---------- MajorchicAPIAdapter.__init__ ----------


def test_adapter_defaults(adapter):
    assert adapter.backend == "deepseek"
    assert adapter.headless is True
    assert adapter.expert_mode is True
    assert adapter.deep_think is True


def test_adapter_gemini(adapter):
    a = MajorchicAPIAdapter(backend="gemini")
    assert a.backend == "gemini"


def test_adapter_expert_off():
    a = MajorchicAPIAdapter(backend="deepseek", expert_mode=False)
    assert a.expert_mode is False


def test_adapter_custom_timeout():
    a = MajorchicAPIAdapter(timeout=100, stable_count=3)
    assert a.timeout == 100
    assert a.stable_count == 3


# ---------- close (no-op без инициализации) ----------


def test_close_without_init(adapter):
    # ai = None — ничего не падает
    adapter.close()
    assert adapter.ai is None


def test_close_after_double_call(adapter):
    adapter.close()
    adapter.close()  # idempotent
