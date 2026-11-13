"""Per-project config в <project>/.pig/config.json.

Project-keys (меняются на проект):
- extensions, ignore_list, output_name
- include_empty_folders, add_edit_prompt, include_plan, line_numbers,
  auto_copy_file, strict_mode, ignore_self, use_sharp_indent
- ui_tree_expanded, ui_tree_unchecked (состояние дерева)
- sort_by_size (визуализация)

Global-keys (в app_config.json): theme, font_size, tree_row_height,
checkbox_size, opt_*, lmstudio_*, quality_*, git_*, web_api_*,
allow_command_execution, command_*, recent_projects, tabs_visibility,
custom_system_prompt, root_folder (последний открытый проект).
"""

from __future__ import annotations

import json
import logging
import os

log = logging.getLogger("pig_t3.project_config")

PROJECT_KEYS: frozenset[str] = frozenset(
    {
        "extensions",
        "ignore_list",
        "output_name",
        "include_empty_folders",
        "add_edit_prompt",
        "include_plan",
        "line_numbers",
        "auto_copy_file",
        "strict_mode",
        "ignore_self",
        "use_sharp_indent",
        "ui_tree_expanded",
        "ui_tree_unchecked",
        "sort_by_size",
    }
)


def project_config_path(root: str) -> str:
    return os.path.join(root, ".pig", "config.json")


def load_project_config(root: str) -> dict:
    if not root or not os.path.isdir(root):
        return {}
    path = project_config_path(root)
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        log.warning("project config load failed (%s): %s", path, e)
        return {}
    if not isinstance(data, dict):
        return {}
    return {k: v for k, v in data.items() if k in PROJECT_KEYS}


def save_project_config(root: str, settings: dict) -> None:
    if not root or not os.path.isdir(root):
        log.warning(
            "project config save skipped: root=%r isdir=%s",
            root,
            os.path.isdir(root) if root else False,
        )
        return
    path = project_config_path(root)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        payload = {k: settings[k] for k in PROJECT_KEYS if k in settings}
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=4, ensure_ascii=False)
        log.debug("project config saved: %s (%d keys)", path, len(payload))
    except OSError as e:
        log.warning("project config save failed (%s): %s", path, e)


def merge_into_global(root: str, settings: dict) -> dict:
    """Вернуть settings с project-ключами из <root>/.pig/config.json."""
    merged = dict(settings)
    project = load_project_config(root)
    if project:
        merged.update(project)
    return merged
