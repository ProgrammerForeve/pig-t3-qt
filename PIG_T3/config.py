import json
import logging
import os
import shutil
import sys

log = logging.getLogger("pig_t3.config")


def _user_config_dir() -> str:
    """Каталог глобальных настроек PIG-T3.

    Linux: $XDG_CONFIG_HOME/pig-t3 или ~/.config/pig-t3
    macOS: ~/Library/Application Support/PIG-T3
    Windows: %APPDATA%\\PIG-T3
    """
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
        return os.path.join(base, "PIG-T3")
    if sys.platform == "darwin":
        return os.path.expanduser("~/Library/Application Support/PIG-T3")
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return os.path.join(base, "pig-t3")


def _default_root_folder() -> str:
    """Дефолтная папка проекта для root_folder.

    Не ~/.config — это не проект. Репо (dev) или рядом с exe (frozen).
    """
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _legacy_config_file() -> str:
    """Старое место app_config.json — рядом с бинарником или в корне репо."""
    if getattr(sys, "frozen", False):
        base = os.path.dirname(sys.executable)
    else:
        base = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    return os.path.join(base, "app_config.json")


# Константа расширений
EXTENSION_TO_MARKDOWN = {
    ".cs": "csharp",
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".html": "html",
    ".css": "css",
    ".json": "json",
    ".xml": "xml",
    ".xaml": "xml",
    ".cpp": "cpp",
    ".c": "c",
    ".h": "cpp",
    ".java": "java",
    ".sql": "sql",
    ".sh": "bash",
    ".bat": "batch",
    ".txt": "text",
    ".md": "markdown",
    ".vue": "javascript",
    ".jsx": "javascript",
    ".tsx": "typescript",
    ".go": "go",
    ".rs": "rust",
    ".php": "php",
    ".rb": "ruby",
}


class ConfigManager:
    def __init__(self):
        cfg_dir = _user_config_dir()
        self.config_file = os.path.join(cfg_dir, "app_config.json")
        self._migrate_legacy()
        self.default_config = {
            "root_folder": _default_root_folder(),
            "extensions": ".py, .yml, .txt, .example",
            "ignore_list": "PIG_T3, .git, .vs, .idea, __pycache__, venv, node_modules, .lock, obj, bin, build, dist, .vscode, log.txt, auto_migration_at_startup.py, project_context.txt, database, WORK_TIME, debug, .pig",
            "output_name": "project_context",
            "include_empty_folders": False,
            "strict_mode": False,
            "ignore_self": False,
            "add_edit_prompt": False,
            "auto_copy_file": False,
            "include_plan": False,
            "line_numbers": False,
            "use_sharp_indent": False,
            "ollama_model": "None",
            "ollama_options": {"num_ctx": 24000, "num_predict": 12000, "temperature": 0.5, "top_p": 0.95, "top_k": 100},
            "opt_chunk_size": 7000,
            "opt_chunk_unit": "tokens",
            "opt_default_model": "None",
            "opt_use_rag": False,
            "allow_command_execution": False,
            "command_confirm_in_editor": True,
            "command_default_timeout": 120,
            "command_whitelist": "",
            "command_allow_shell_operators": False,
            "quality_edit_retry_max": 2,
            "quality_edit_retry_context_lines": 20,
            "quality_edit_retry_min_ratio": 0.6,
            "command_summary_max_lines": 100,
            "command_summary_min_matches": 5,
            "custom_system_prompt": "",
            "lmstudio_base_url": "http://localhost:1234/v1",
            "lmstudio_api_key": "lm-studio",
            "lmstudio_timeout": 600,
            "lmstudio_embeddings_model": "",
            "ui_tree_expanded": [],
            "ui_tree_unchecked": [],
            "theme": "dark",
            "font_size": 10,
            "tree_row_height": 28,
            "checkbox_size": 14,
            "auto_refresh_tree": True,
            "tabs_visibility": {"generator": True, "info": True, "editor": True, "plan": True, "quality": True},
            "recent_projects": [],
            "git_enabled": False,
            "git_branch_mode": "new",
            "git_auto_push": False,
            "web_api_timeout": 600,
            "web_api_stable_count": 7,
            "plan_context_max_chars": 1000000,
            "plan_step_limit_tokens": 15000,
            "plan_generation_limit_tokens": 12000,
            "quality_scan_chunk_size": 50,
            "quality_pylint_disable": "",
            "quality_pylint_max_line_length": 120,
            "quality_vulture_min_confidence": 60,
            "quality_bandit_severity": "medium",
            "quality_tool_timeout": 120,
            "quality_context_lines": 0,
            "opt_bfs_depth": 2,
            "opt_greedy_llm_weight": 0.6,
            "opt_greedy_pr_weight": 0.3,
            "opt_greedy_cc_weight": 0.1,
            "opt_token_bytes_per_token": 4,
        }

    def _migrate_legacy(self) -> None:
        """Скопировать app_config.json из старого места, если новый ещё нет."""
        legacy = _legacy_config_file()
        if legacy == self.config_file:
            return
        if not os.path.exists(legacy):
            return
        if os.path.exists(self.config_file):
            return
        try:
            os.makedirs(os.path.dirname(self.config_file), exist_ok=True)
            shutil.copy2(legacy, self.config_file)
            log.info(
                "Migrated app_config.json: %s → %s",
                legacy,
                self.config_file,
            )
        except OSError as e:
            log.warning("Config migration failed: %s", e)

    def load(self):
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, encoding="utf-8") as f:
                    return {**self.default_config, **json.load(f)}
            except Exception:
                return self.default_config
        return self.default_config

    def save(self, data):
        try:
            os.makedirs(os.path.dirname(self.config_file), exist_ok=True)
            json_str = json.dumps(data, indent=4, ensure_ascii=False)
            with open(self.config_file, "w", encoding="utf-8") as f:
                f.write(json_str)
        except Exception as e:
            log.warning(f"Не удалось сохранить настройки: {e}")
