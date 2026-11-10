import contextlib
import sys


class NullWriter:
    def write(self, text):
        pass

    def flush(self):
        pass

    def isatty(self):
        return False


def _protect_std_streams():
    """Защита от [Errno 22] Invalid argument при использовании print() в режиме --noconsole"""
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream is None:
            setattr(sys, stream_name, NullWriter())
        else:
            try:
                stream.write("")
            except Exception:
                setattr(sys, stream_name, NullWriter())


_protect_std_streams()

# faulthandler: печатает Python-стек при SIGSEGV/SIGABRT/SIGFPE.
# Помогает локализовать C++-краши (`free(): invalid size` и т.п.),
# которые не ловятся обычным try/except.
import faulthandler as _faulthandler  # noqa: E402

try:
    import tempfile
    from pathlib import Path

    _crash_log_path = Path(tempfile.gettempdir()) / "pig_crash.log"
    _crash_log = open(_crash_log_path, "a", encoding="utf-8")  # noqa: SIM115
    _faulthandler.enable(file=_crash_log, all_threads=True)
except Exception:
    _faulthandler.enable(all_threads=True)
# Включаем поддержку высокого разрешения (DPI Awareness) для четкости на 4K
if sys.platform == "win32":
    try:
        import ctypes

        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        with contextlib.suppress(Exception):
            ctypes.windll.user32.SetProcessDPIAware()


def main():
    from .gui_qt.app import run_gui_qt

    sys.exit(run_gui_qt())


if __name__ == "__main__":
    main()
