"""Multi-turn retry helpers (ADR-016)."""
from __future__ import annotations

_MAX_CHARS = 8000
_MAX_CONTEXT_LINES = 50
_MAX_ORIGINAL_CHARS = 4000


def build_retry_prompt(
    failed_edits: list,
    read_requests: list[dict],
    original_response: str,
    *,
    max_chars: int = _MAX_CHARS,
) -> str:
    """Собрать промпт для LLM: упавшие edits + прочитанные строки."""
    parts: list[str] = ["Твой предыдущий JSON-патч применился частично."]
    if failed_edits:
        parts.append("\nУпавшие действия (нужно исправить):\n")
        for i, fe in enumerate(failed_edits, 1):
            parts.append(f"{i}. edit `{fe.path}`")
            parts.append(f"   - find (первые 80): {fe.find[:80]!r}")
            parts.append(f"   - ошибка: {fe.error}")
            if fe.best_match_line is not None:
                parts.append(
                    f"   - Похожий фрагмент около L{fe.best_match_line} "
                    f"(ratio {fe.best_match_ratio:.2f}):"
                )
                for ln in fe.context_lines[:_MAX_CONTEXT_LINES]:
                    parts.append(f"     {ln}")
            parts.append(f"   - Файл: {fe.total_lines} строк")
            parts.append("")
    if read_requests:
        parts.append("\nЗапрошенные строки:\n")
        for rr in read_requests:
            parts.append(f"-- {rr['path']} L{rr['start']}-{rr['end']} --")
            parts.extend(rr["lines"])
            parts.append("")
    parts.append(
        "Верни JSON-массив ТОЛЬКО для исправления упавших действий.\n"
        "Предпочти `replace_lines` с точными номерами строк.\n"
        "Если контекста не хватает — верни "
        '[{"action":"read_lines","path":"...","start":N,"end":M}].'
    )
    trimmed = _trim_original(original_response)
    if trimmed:
        parts.insert(0, "=== оригинальный патч (фрагмент) ===\n" + trimmed + "\n")
    text = "\n".join(parts)
    if len(text) > max_chars:
        text = text[:max_chars] + "\n... (truncated)"
    return text


def _trim_original(raw: str) -> str:
    start = raw.find("[")
    end = raw.rfind("]")
    if start < 0 or end <= start:
        return ""
    s = raw[start : end + 1]
    return s if len(s) <= _MAX_ORIGINAL_CHARS else s[:_MAX_ORIGINAL_CHARS] + "... (truncated)"
