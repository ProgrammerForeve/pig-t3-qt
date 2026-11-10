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
