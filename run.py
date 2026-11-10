"""Entry point для PyInstaller и удобного запуска.

Импортирует PIG_T3 как пакет — относительные импорты внутри
PIG_T3/main.py работают корректно.

Использование:
    python run.py
    pyinstaller pig_t3.spec --noconfirm
"""
from PIG_T3.main import main

if __name__ == "__main__":
    main()
