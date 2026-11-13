"""copy_text_to_clipboard — надёжное копирование текста в буфер обмена.

Порядок на Linux (по надёжности):
1. xclip (X11) — отдельный процесс держит буфер, не зависит от Qt/WM
2. wl-copy (Wayland)
3. Qt QGuiApplication.clipboard() — fallback

macOS: pbcopy. Windows: ctypes OpenClipboard (CF_UNICODETEXT).
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys

log = logging.getLogger("pig_t3.utils.clipboard_text")

# Держим reference на xclip, чтобы не было zombie. После первого paste
# xclip завершится сам — следующий вызов создаст новый.
_xclip_proc: subprocess.Popen | None = None


def _qt_clipboard(text: str) -> bool:
    try:
        from PySide6.QtGui import QGuiApplication

        if QGuiApplication.instance() is None:
            return False
        cb = QGuiApplication.clipboard()
        if cb is None:
            return False
        cb.setText(text)
        return True
    except Exception as e:
        log.debug("Qt clipboard failed: %s", e)
        return False


def _xclip(text: str) -> bool:
    global _xclip_proc
    if not shutil.which("xclip") or not os.environ.get("DISPLAY"):
        return False
    try:
        _xclip_proc = subprocess.Popen(
            ["xclip", "-selection", "clipboard"],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        assert _xclip_proc.stdin is not None
        _xclip_proc.stdin.write(text.encode("utf-8"))
        _xclip_proc.stdin.close()
        return True
    except Exception as e:
        log.debug("xclip failed: %s", e)
        return False


def _wl_copy(text: str) -> bool:
    if not shutil.which("wl-copy"):
        return False
    if not (
        os.environ.get("WAYLAND_DISPLAY")
        or os.environ.get("XDG_SESSION_TYPE") == "wayland"
    ):
        return False
    try:
        subprocess.run(
            ["wl-copy"],
            input=text.encode("utf-8"),
            check=True,
            timeout=5,
        )
        return True
    except Exception as e:
        log.debug("wl-copy failed: %s", e)
        return False


def _pbcopy(text: str) -> bool:
    if not shutil.which("pbcopy"):
        return False
    try:
        subprocess.run(
            ["pbcopy"],
            input=text.encode("utf-8"),
            check=True,
            timeout=5,
        )
        return True
    except Exception as e:
        log.debug("pbcopy failed: %s", e)
        return False


def _win32_clipboard(text: str) -> bool:
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        user32 = ctypes.windll.user32
        if not user32.OpenClipboard(None):
            return False
        try:
            user32.EmptyClipboard()
            data = text.encode("utf-16-le") + b"\x00\x00"
            handle = kernel32.GlobalAlloc(0x0042, len(data))
            if not handle:
                return False
            ptr = kernel32.GlobalLock(handle)
            ctypes.memmove(ptr, data, len(data))
            kernel32.GlobalUnlock(handle)
            user32.SetClipboardData(13, handle)  # CF_UNICODETEXT
        finally:
            user32.CloseClipboard()
        return True
    except Exception as e:
        log.debug("win32 clipboard failed: %s", e)
        return False


def copy_text_to_clipboard(text: str) -> bool:
    """Скопировать text в системный буфер. True если удалось."""
    if not text:
        return False

    if sys.platform.startswith("linux"):
        if _xclip(text):
            return True
        if _wl_copy(text):
            return True
    elif sys.platform == "darwin":
        if _pbcopy(text):
            return True
    elif sys.platform == "win32":
        if _win32_clipboard(text):
            return True

    return _qt_clipboard(text)
