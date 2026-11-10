"""Слой совместимости: читает/пишет те же ключи, что legacy Tkinter-GUI.

Единственные отличия от старого формата:
- theme мигрируется (pink/eye_care → light, dark_pink → dark);
- ui_scale удаляется при сохранении (поле больше не поддерживается).
Остальные ключи (ui_tree_expanded, ui_tree_unchecked, history_stack,
redo_stack, excluded_paths и т.д.) — без изменений.
"""

from .theme import resolve_theme

# Ключи, которые удаляются при сохранении (устаревшие/неподдерживаемые)
_DROP_ON_SAVE = {"ui_scale"}


def load_and_migrate(config_manager) -> dict:
    """Загружает конфиг, мигрирует theme, убирает устаревшие ключи."""
    raw = config_manager.load()
    settings = dict(raw)

    # Миграция темы
    settings["theme"] = resolve_theme(settings.get("theme", "dark"))

    # Удаление устаревших ключей
    for key in _DROP_ON_SAVE:
        settings.pop(key, None)

    return settings


def save_migrated(config_manager, settings: dict) -> None:
    """Сохраняет конфиг без устаревших ключей."""
    clean = {k: v for k, v in settings.items() if k not in _DROP_ON_SAVE}
    config_manager.save(clean)
