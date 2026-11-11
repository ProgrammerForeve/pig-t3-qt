"""ApplyWorker / UndoRedoWorker — фоновое применение патча (T-304/T-305).

Контракт test_threading_contract:
- QObject, moveToThread, run() слот
- Сигналы progress/error/cancelled + собственные done
- Не трогает UI
"""

from __future__ import annotations

import logging
import os
import shutil
import uuid

from PySide6.QtCore import QObject, Signal, Slot

from ...core.patcher import apply_llm_changes, clean_json_text

log = logging.getLogger("pig_t3.apply_worker")


def _filter_paths(paths: list[str]) -> list[str]:
    """Убрать абсолютные/.. и вложенные пути (родитель покрывает детей)."""
    normalized = []
    for p in paths:
        norm = os.path.normpath(p).replace("\\", "/")
        if not os.path.isabs(norm) and not norm.startswith(".."):
            normalized.append(norm)
    normalized.sort()
    filtered = []
    for p in normalized:
        if not any(p == parent or p.startswith(parent + "/") for parent in filtered):
            filtered.append(p)
    return filtered


def _extract_paths_from_actions(data: list[dict]) -> list[str]:
    paths: list[str] = []
    for action in data:
        for key in ("path", "source", "destination"):
            if action.get(key):
                paths.append(action[key])
    return paths


def _copy_paths(src_root: str, dst_root: str, paths: list[str]) -> None:
    for p in paths:
        src = os.path.join(src_root, p)
        dst = os.path.join(dst_root, p)
        if not os.path.exists(src):
            continue
        os.makedirs(os.path.dirname(dst) or dst_root, exist_ok=True)
        if os.path.isdir(src):
            shutil.copytree(src, dst, dirs_exist_ok=True)
        else:
            shutil.copy2(src, dst)


def _restore_snapshot(root: str, backup_dir: str, paths: list[str]) -> None:
    for p in paths:
        target = os.path.join(root, p)
        backup = os.path.join(backup_dir, p)
        if os.path.exists(target):
            if os.path.isdir(target):
                shutil.rmtree(target)
            else:
                os.remove(target)
        if os.path.exists(backup):
            os.makedirs(os.path.dirname(target) or root, exist_ok=True)
            if os.path.isdir(backup):
                shutil.copytree(backup, target, dirs_exist_ok=True)
            else:
                shutil.copy2(backup, target)


class ApplyWorker(QObject):
    """Применяет JSON-патч, делает бэкап before/after, эмитит запись истории."""

    done = Signal(str, dict)  # (log, history_record)
    error = Signal(str)

    def __init__(
        self,
        llm_text: str,
        root_folder: str,
        settings: dict | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self._llm_text = llm_text
        self._root = root_folder
        self._settings = dict(settings or {})

    @Slot()
    def run(self) -> None:
        try:
            import json

            cleaned = clean_json_text(self._llm_text)
            data = json.loads(cleaned)
            if not isinstance(data, list):
                raise ValueError("JSON должен быть списком объектов")
            raw_paths = _extract_paths_from_actions(data)
            filtered = _filter_paths(raw_paths)

            patch_id = str(uuid.uuid4())
            backup_root = os.path.join(self._root, ".pig", "backups", patch_id)
            before = os.path.join(backup_root, "before")
            after = os.path.join(backup_root, "after")

            _copy_paths(self._root, before, filtered)
            log = apply_llm_changes(
                self._llm_text,
                self._root,
                allow_command_execution=bool(self._settings.get("allow_command_execution", False)),
                command_whitelist=self._settings.get("command_whitelist", ""),
                command_default_timeout=int(self._settings.get("command_default_timeout", 120)),
            )
            _copy_paths(self._root, after, filtered)

            record = {
                "id": patch_id,
                "paths": filtered,
                "llm_text": self._llm_text,
            }
            self.done.emit(log, record)
        except Exception as e:
            self.error.emit(str(e))


class UndoRedoWorker(QObject):
    """Восстанавливает before/after snapshot. action='undo'|'redo'."""

    done = Signal(str)  # status message
    error = Signal(str)

    def __init__(
        self,
        root_folder: str,
        record: dict,
        action: str,  # "undo" | "redo"
        parent=None,
    ):
        super().__init__(parent)
        self._root = root_folder
        self._record = record
        self._action = action

    @Slot()
    def run(self) -> None:
        try:
            sub = "before" if self._action == "undo" else "after"
            backup_dir = os.path.join(self._root, ".pig", "backups", self._record["id"], sub)
            _restore_snapshot(self._root, backup_dir, self._record["paths"])
            msg = "Изменения отменены" if self._action == "undo" else "Изменения повторно применены"
            self.done.emit(msg)
        except Exception as e:
            self.error.emit(str(e))
