"""Diff preview перед применением JSON-патча (B1).

compute_diffs(llm_text, root_folder) эмулирует применение патча во
временной папке и возвращает unified diff для каждого изменённого
файла. Пользователь видит - / + перед тем, как нажать «Применить».

Логика patcher'а не дублируется: копируем затронутые файлы в tmp,
вызываем реальный apply_llm_changes на tmp, сравниваем.
"""

from __future__ import annotations

import contextlib
import difflib
import json
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from ...core.patcher import apply_llm_changes, clean_json_text

_FILE_ACTIONS = {"create", "delete", "edit", "move"}


@dataclass
class FileDiff:
    path: str
    status: str  # "created" | "modified" | "deleted"
    unified_diff: str  # может быть пустым, если изменения нулевые


@dataclass
class CommandSpec:
    """Команда из JSON-патча для предпросмотра (ADR-017)."""

    command: str
    output_path: str | None = None
    timeout_sec: int = 120
    on_failure: str = "continue"
    batch_index: int | None = None  # 0-based, None если одиночная
    batch_size: int = 1


def _extract_paths(data: list[dict]) -> list[str]:
    paths: list[str] = []
    for action in data:
        if not isinstance(action, dict):
            continue
        atype = action.get("action")
        if atype not in _FILE_ACTIONS:
            continue
        for key in ("path", "source", "destination"):
            v = action.get(key)
            if isinstance(v, str) and v:
                paths.append(v)
    return paths


def _filter_safe(paths: list[str], root_folder: str) -> list[str]:
    """Только относительные пути внутри root_folder, без .., без дублей.

    Использует Path.relative_to() вместо str.startswith(str(root) + "/").
    На Windows str(Path("C:\\\\root")) + "/" = "C:\\\\root/" (forward slash),
    а str(candidate) = "C:\\\\root\\\\sub\\\\file.py" (backslash). startswith
    не срабатывает → все пути отвергаются → diff всегда пустой.
    relative_to() работает независимо от ОС и разделителя.
    """
    root_abs = Path(root_folder).resolve()
    safe: list[str] = []
    for p in paths:
        try:
            candidate = (root_abs / p).resolve()
            rel = candidate.relative_to(root_abs)
        except (OSError, ValueError):
            continue
        rel_str = str(rel).replace("\\", "/")
        if not rel_str:
            continue
        safe.append(rel_str)
    safe.sort()
    deduped: list[str] = []
    for p in safe:
        if not any(p == parent or p.startswith(parent + "/") for parent in deduped):
            deduped.append(p)
    return deduped


def _snapshot(root: Path, paths: list[str]) -> dict[str, str]:
    """Снимок содержимого: {rel_path: text}. Для dir — рекурсивно."""
    result: dict[str, str] = {}
    for p in paths:
        target = root / p
        if not target.exists():
            continue
        if target.is_dir():
            for f in target.rglob("*"):
                if f.is_file():
                    rel = str(f.relative_to(root))
                    with contextlib.suppress(OSError):
                        result[rel] = f.read_text(encoding="utf-8", errors="replace")
        else:
            with contextlib.suppress(OSError):
                result[p] = target.read_text(encoding="utf-8", errors="replace")
    return result


def compute_diffs(llm_text: str, root_folder: str) -> list[FileDiff]:
    """Эмулировать патч и вернуть список изменённых файлов."""
    cleaned = clean_json_text(llm_text)
    data = json.loads(cleaned)
    if not isinstance(data, list):
        raise ValueError("Корень JSON должен быть списком [ ... ].")

    raw_paths = _extract_paths(data)
    paths = _filter_safe(raw_paths, root_folder)
    if not paths:
        if raw_paths:
            raise ValueError(f"Все {len(raw_paths)} путей из JSON вне корня проекта {root_folder!r}: {raw_paths[:3]}")
        return []

    root = Path(root_folder).resolve()
    before = _snapshot(root, paths)

    with tempfile.TemporaryDirectory(prefix="pig_diff_") as tmp:
        tmp_path = Path(tmp)
        for p in paths:
            src = root / p
            dst = tmp_path / p
            if not src.exists():
                continue
            dst.parent.mkdir(parents=True, exist_ok=True)
            if src.is_dir():
                shutil.copytree(src, dst)
            else:
                shutil.copy2(src, dst)

        with contextlib.suppress(Exception):
            apply_llm_changes(llm_text, str(tmp_path))

        after = _snapshot(tmp_path, paths)

    all_paths = sorted(set(before.keys()) | set(after.keys()))
    diffs: list[FileDiff] = []
    for p in all_paths:
        old_text = before.get(p, "")
        new_text = after.get(p, "")
        if old_text == new_text:
            continue
        if not old_text and new_text:
            status = "created"
        elif old_text and not new_text:
            status = "deleted"
        else:
            status = "modified"
        lines = list(
            difflib.unified_diff(
                old_text.splitlines(keepends=True),
                new_text.splitlines(keepends=True),
                fromfile=f"a/{p}",
                tofile=f"b/{p}",
                lineterm="\n",
            )
        )
        diffs.append(FileDiff(path=p, status=status, unified_diff="".join(lines)))

    # ISSUE 6: патч содержит edit, но apply_llm_changes в temp не дал
    # изменений (replace_text не нашёл фрагмент, replace_lines вне
    # диапазона, find == replace). Показываем причину, а не «Нет изменений».
    if not diffs:
        edit_paths = [
            a.get("path") for a in data if isinstance(a, dict) and a.get("action") == "edit" and a.get("path")
        ]
        if edit_paths:
            hint = (
                "⚠️ Патч не дал изменений для этого файла.\n"
                "Возможные причины:\n"
                "- replace_text: фрагмент 'find' не найден даже с "
                "whitespace-flexible fallback.\n"
                "- replace_text: 'find' и 'replace' идентичны.\n"
                "- replace_lines: start/end вне диапазона файла.\n"
                "- edit: операция применилась, но результат совпал с исходником.\n"
            )
            for p in edit_paths:
                if p in paths:
                    diffs.append(FileDiff(path=p, status="failed", unified_diff=hint))
    return diffs


def extract_commands(llm_text: str) -> list[CommandSpec]:
    """Извлечь все run_command из JSON (включая batch, ADR-017)."""
    try:
        data = json.loads(clean_json_text(llm_text))
    except (json.JSONDecodeError, ValueError, TypeError):
        return []
    if not isinstance(data, list):
        return []
    result: list[CommandSpec] = []
    for action in data:
        if not isinstance(action, dict):
            continue
        if action.get("action") != "run_command":
            continue
        try:
            timeout = int(action.get("timeout_sec", 120))
        except (TypeError, ValueError):
            timeout = 120
        on_failure = str(action.get("on_failure", "continue"))
        output_path = action.get("output_path")
        single = action.get("command")
        batch = action.get("commands")
        if batch and isinstance(batch, list):
            clean = [c for c in batch if isinstance(c, str) and c.strip()]
            for i, c in enumerate(clean):
                result.append(
                    CommandSpec(
                        command=c,
                        output_path=output_path,
                        timeout_sec=timeout,
                        on_failure=on_failure,
                        batch_index=i,
                        batch_size=len(clean),
                    )
                )
        elif isinstance(single, str) and single.strip():
            result.append(
                CommandSpec(
                    command=single,
                    output_path=output_path,
                    timeout_sec=timeout,
                    on_failure=on_failure,
                )
            )
    return result
