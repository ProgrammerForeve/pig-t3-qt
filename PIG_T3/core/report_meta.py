"""Report meta + fingerprint для stale-детекта отчёта.

При генерации сохраняем fingerprint — sha256 от
(rel_path|size|mtime_ns) каждого файла. При следующем refresh_tree
сравниваем: если хоть один файл изменился/добавился/удалён — stale.

Хранится в <project>/.pig/report_meta.json.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import datetime

log = logging.getLogger("pig_t3.report_meta")


def report_meta_path(root: str) -> str:
    return os.path.join(root, ".pig", "report_meta.json")


def compute_fingerprint(files_meta: list[dict]) -> str:
    """files_meta: list[dict] с ключами rel_path, size, mtime_ns."""
    parts = sorted(
        f"{f.get('rel_path', '')}|{f.get('size', 0)}|"
        f"{f.get('mtime_ns', 0)}"
        for f in files_meta
    )
    h = hashlib.sha256()
    for p in parts:
        h.update(p.encode("utf-8"))
        h.update(b"\n")
    return h.hexdigest()


def save_report_meta(
    root: str, files_meta: list[dict], output_path: str
) -> None:
    """Сохранить fingerprint + files list + timestamp."""
    if not root or not os.path.isdir(root):
        return
    try:
        rel_output = os.path.relpath(output_path, root)
    except (ValueError, OSError):
        rel_output = output_path
    payload = {
        "fingerprint": compute_fingerprint(files_meta),
        "file_count": len(files_meta),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "output_path": rel_output,
        "files": [
            {
                "rel_path": f.get("rel_path", ""),
                "size": f.get("size", 0),
                "mtime_ns": f.get("mtime_ns", 0),
            }
            for f in files_meta
        ],
    }
    path = report_meta_path(root)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fp:
            json.dump(payload, fp, indent=2, ensure_ascii=False)
        log.debug(
            "report meta saved: %s (%d files)", path, len(files_meta)
        )
    except OSError as e:
        log.warning("report meta save failed (%s): %s", path, e)


def load_meta(root: str) -> dict | None:
    if not root or not os.path.isdir(root):
        return None
    path = report_meta_path(root)
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        log.warning("report meta load failed (%s): %s", path, e)
        return None
    if not isinstance(data, dict):
        return None
    return data


def is_stale_from_files(
    root: str, files: list[tuple[str, str]]
) -> bool | None:
    """Проверить, устарел ли отчёт относительно files.

    Args:
        root: абсолютный путь проекта
        files: список (full_path, ext) — из ProjectAnalyzer.scan_directory

    Returns:
        None — meta нет (отчёт ещё не генерировался)
        True — файлы изменились, отчёт устарел
        False — отчёт актуален
    """
    meta = load_meta(root)
    if meta is None:
        return None
    old_fp = meta.get("fingerprint", "")
    if not old_fp:
        return None
    files_meta: list[dict] = []
    for full_path, _ext in files:
        try:
            st = os.stat(full_path)
        except OSError:
            continue
        try:
            rel = os.path.relpath(full_path, root).replace("\\", "/")
        except ValueError:
            continue
        files_meta.append(
            {
                "rel_path": rel,
                "size": st.st_size,
                "mtime_ns": st.st_mtime_ns,
            }
        )
    new_fp = compute_fingerprint(files_meta)
    return old_fp != new_fp
