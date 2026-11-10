import logging
import os
import ctypes
from ctypes import wintypes

log = logging.getLogger("pig_t3.utils.clipboard")



def copy_file_to_clipboard_windows(filepath):
    """
    Кладет ФАЙЛ (не текст) в буфер обмена Windows.
    Работает через ctypes для 64-битных систем.
    """
    try:
        # Константы
        CF_HDROP = 15
        GHND = 0x0042

        # Определение структуры DROPFILES
        class DROPFILES(ctypes.Structure):
            _fields_ = [("pFiles", wintypes.DWORD),
                        ("pt", wintypes.POINT),
                        ("fNC", wintypes.BOOL),
                        ("fWide", wintypes.BOOL)]

        # Подготовка данных
        pDropFiles = DROPFILES()
        pDropFiles.pFiles = ctypes.sizeof(DROPFILES)
        pDropFiles.fWide = True
        # Путь должен завершаться двойным null-терминатором
        files_list = os.path.abspath(filepath) + "\0\0"
        files_data = files_list.encode("utf-16le")
        total_size = ctypes.sizeof(DROPFILES) + len(files_data)

        # Настройка API функций
        kernel32 = ctypes.windll.kernel32
        user32 = ctypes.windll.user32
        kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
        kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
        kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
        kernel32.GlobalLock.restype = ctypes.c_void_p
        kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
        kernel32.GlobalUnlock.restype = wintypes.BOOL
        user32.OpenClipboard.argtypes = [wintypes.HWND]
        user32.OpenClipboard.restype = wintypes.BOOL
        user32.EmptyClipboard.argtypes = []
        user32.EmptyClipboard.restype = wintypes.BOOL
        user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
        user32.SetClipboardData.restype = wintypes.HANDLE
        user32.CloseClipboard.argtypes = []
        user32.CloseClipboard.restype = wintypes.BOOL

        # Выделение памяти
        hGlobal = kernel32.GlobalAlloc(GHND, total_size)
        if not hGlobal:
            return False
        target_ptr = kernel32.GlobalLock(hGlobal)
        if not target_ptr:
            return False

        # Копирование структуры и пути
        ctypes.memmove(target_ptr, ctypes.byref(pDropFiles), ctypes.sizeof(DROPFILES))
        ctypes.memmove(target_ptr + ctypes.sizeof(DROPFILES), files_data, len(files_data))
        kernel32.GlobalUnlock(hGlobal)

        # Работа с буфером обмена
        if not user32.OpenClipboard(None):
            return False
        user32.EmptyClipboard()
        user32.SetClipboardData(CF_HDROP, hGlobal)
        user32.CloseClipboard()
        return True
    except Exception as e:
        log.warning(f"Ошибка копирования файла в буфер: {e}")
        return False
