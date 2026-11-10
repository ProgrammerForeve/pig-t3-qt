"""TDD: clipboard — на Linux модуль сразу возвращает False (ctypes.windll недоступен)."""

from __future__ import annotations

import sys

import pytest

from PIG_T3.utils import clipboard


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="Linux/macOS path only: ctypes.windll not available",
)
def test_returns_false_on_non_windows(tmp_path):
    f = tmp_path / "test.txt"
    f.write_text("x")
    assert clipboard.copy_file_to_clipboard_windows(str(f)) is False


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="Linux/macOS only",
)
def test_returns_false_on_missing_file(tmp_path):
    assert clipboard.copy_file_to_clipboard_windows(str(tmp_path / "nope")) is False


@pytest.mark.skipif(
    sys.platform != "win32",
    reason="Windows-only",
)
def test_windows_with_windll(monkeypatch, tmp_path):
    """На Windows — проверяем, что доходит до OpenClipboard."""
    f = tmp_path / "t.txt"
    f.write_text("x")
    called = {"open": False, "set": False}

    class _FakeKernel32:
        def GlobalAlloc(self, *a):
            return 1

        def GlobalLock(self, h):
            return 1

        def GlobalUnlock(self, h):
            return 1

    class _FakeUser32:
        def OpenClipboard(self, _):
            called["open"] = True
            return True

        def EmptyClipboard(self):
            return True

        def SetClipboardData(self, *a):
            called["set"] = True
            return 1

        def CloseClipboard(self):
            return True

    import ctypes

    monkeypatch.setattr(
        ctypes,
        "windll",
        type(
            "W",
            (),
            {
                "kernel32": _FakeKernel32(),
                "user32": _FakeUser32(),
            },
        ),
    )
    result = clipboard.copy_file_to_clipboard_windows(str(f))
    assert result is True
    assert called["open"] and called["set"]
