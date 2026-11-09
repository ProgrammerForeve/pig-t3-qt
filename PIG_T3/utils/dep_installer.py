import sys
import subprocess
import importlib.util

REQUIRED_TOOLS = ["radon", "pylint", "vulture", "bandit", "networkx"]

class DependencyInstaller:
    @staticmethod
    def check_and_install(callback=None) -> bool:
        """
        Проверяет и устанавливает зависимости. 
        callback(text): функция для обновления статуса в UI.
        """
        missing = []
        for tool in REQUIRED_TOOLS:
            if importlib.util.find_spec(tool) is None:
                missing.append(tool)
        
        if not missing:
            return True
        
        if callback:
            callback(f"Установка библиотек: {', '.join(missing)}...")
            
        try:
            cmd = [sys.executable, "-m", "pip", "install"] + missing
            subprocess.check_call(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        except subprocess.CalledProcessError:
            if callback:
                callback("Ошибка установки зависимостей.")
            return False
