"""Темы: Qt-Material dark/light + миграция legacy-значений."""

from qt_material import apply_stylesheet

# Qt-Material не содержит legacy-тем pink/eye_care/dark_pink.
# Мягкая миграция: пользователь не увидит "сломанную" тему,
# просто потеряет оттенок.
_THEME_ALIASES = {
    "pink": "light",
    "eye_care": "light",
    "dark_pink": "dark",
}

# Qt-Material: чистые dark/light без цветных акцентов
_QT_MATERIAL = {
    "dark": "dark_blue.xml",
    "light": "light_blue.xml",
}


def resolve_theme(theme: str | None) -> str:
    """Приводит произвольное имя темы к 'dark' или 'light'."""
    if not theme:
        return "dark"
    theme = _THEME_ALIASES.get(theme, theme)
    if theme not in ("dark", "light"):
        theme = "dark"
    return theme


def apply_theme(app, theme: str) -> str:
    """Применяет тему. Возвращает resolved-имя (для сохранения в конфиг)."""
    resolved = resolve_theme(theme)
    apply_stylesheet(
        app,
        theme=_QT_MATERIAL[resolved],
        invert_secondary=(resolved == "light"),
    )
    return resolved
