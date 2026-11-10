"""B3: FileWatcher — start/stop, debounce, ignore-list."""

from __future__ import annotations

from PIG_T3.gui_qt.widgets.file_watcher import FileWatcher, _WatchdogHandler


def test_start_stop(tmp_path):
    w = FileWatcher(debounce_ms=50)
    assert w.is_running() is False
    assert w.start(str(tmp_path)) is True
    assert w.is_running() is True
    assert w.current_path() == str(tmp_path)
    w.stop()
    assert w.is_running() is False
    assert w.current_path() is None


def test_start_non_dir_returns_false(tmp_path):
    w = FileWatcher()
    assert w.start(str(tmp_path / "missing")) is False


def test_start_empty_returns_false():
    assert FileWatcher().start("") is False


def test_start_without_watchdog_returns_false(tmp_path, monkeypatch):
    """Если watchdog не установлен — start возвращает False, не падает."""
    import builtins

    real_import = builtins.__import__

    def _blocked(name, *args, **kwargs):
        if name.startswith("watchdog"):
            raise ImportError("no watchdog")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _blocked)
    w = FileWatcher()
    assert w.start(str(tmp_path)) is False


def test_debounce_emits_once(qtbot):
    w = FileWatcher(debounce_ms=80)
    events: list[int] = []
    w.changes_detected.connect(lambda: events.append(1))
    # эмулируем несколько fs-events подряд
    w._on_fs_event()
    w._on_fs_event()
    w._on_fs_event()
    qtbot.wait(200)
    assert len(events) == 1  # debounce склеил


def test_restart_changes_path(tmp_path):
    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    b.mkdir()
    w = FileWatcher(debounce_ms=50)
    w.start(str(a))
    assert w.current_path() == str(a)
    w.start(str(b))
    assert w.current_path() == str(b)
    w.stop()


# ---------- _WatchdogHandler ignore-list ----------


def _fake_event(src_path: str):
    class _E:
        pass

    e = _E()
    e.src_path = src_path
    return e


def test_handler_ignores_dot_pig():
    called: list[int] = []
    h = _WatchdogHandler(lambda: called.append(1))
    h.dispatch(_fake_event("/proj/.pig/state.json"))
    assert not called


def test_handler_ignores_venv():
    called: list[int] = []
    h = _WatchdogHandler(lambda: called.append(1))
    h.dispatch(_fake_event("/proj/venv/lib.py"))
    assert not called


def test_handler_passes_project_files():
    called: list[int] = []
    h = _WatchdogHandler(lambda: called.append(1))
    h.dispatch(_fake_event("/proj/src/a.py"))
    assert called == [1]
