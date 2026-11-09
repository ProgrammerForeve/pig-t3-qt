import ast
import os
import re
from typing import List, Dict, Set, Optional
import networkx as nx

class DependencyGraph:
    """
    Строит граф зависимостей Python-файлов на основе импортов.
    Для не-Python файлов возвращает пустой граф или обрабатывает через заглушки.
    """
    def __init__(self, root_folder: str):
        self.root_folder = os.path.abspath(root_folder)
        self.graph = nx.DiGraph()
        self.file_to_module = {}  # абсолютный путь -> имя модуля (точечная нотация)
        self.module_to_file = {}  # имя модуля -> абсолютный путь

    def _get_module_name(self, file_path: str) -> Optional[str]:
        """Преобразует путь к файлу в точечное имя модуля относительно корня проекта."""
        rel = os.path.relpath(file_path, self.root_folder)
        if rel.startswith('..'):
            return None
        parts = rel.replace('.py', '').split(os.sep)
        if parts[-1] == '__init__':
            parts = parts[:-1]
        if not parts:
            return None
        return '.'.join(parts)

    def build(self, file_paths: List[str]) -> nx.DiGraph:
        """
        Принимает список абсолютных путей ко всем файлам проекта (только Python).
        Возвращает ориентированный граф зависимостей.
        """
        self.graph.clear()
        self.file_to_module.clear()
        self.module_to_file.clear()

        # Регистрируем все файлы как узлы графа
        for file_path in file_paths:
            if not file_path.endswith('.py'):
                continue
            module_name = self._get_module_name(file_path)
            if module_name is None:
                continue
            self.file_to_module[file_path] = module_name
            self.module_to_file[module_name] = file_path
            self.graph.add_node(module_name, path=file_path)

        # Анализируем импорты в каждом файле
        for file_path in file_paths:
            if file_path not in self.file_to_module:
                continue
            module_name = self.file_to_module[file_path]
            imports = self._extract_imports(file_path)
            for imp in imports:
                # Ищем целевой модуль в проекте
                target_module = self._resolve_import(imp, os.path.dirname(file_path))
                if target_module and target_module in self.module_to_file:
                    self.graph.add_edge(module_name, target_module)
        return self.graph

    def _extract_imports(self, file_path: str) -> List[str]:
        """Извлекает все импортируемые имена модулей из файла."""
        imports = []
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            tree = ast.parse(content)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        imports.append(alias.name)
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        imports.append(node.module)
        except Exception:
            pass
        return imports

    def _resolve_import(self, import_name: str, current_dir: str) -> Optional[str]:
        """Пытается сопоставить имя импорта с модулем проекта."""
        # Прямое совпадение
        if import_name in self.module_to_file:
            return import_name
        # Относительный импорт (начинается с точки) - упрощённо, для простоты игнорируем
        if import_name.startswith('.'):
            return None
        # Поиск по частичному совпадению с пакетами
        parts = import_name.split('.')
        for i in range(len(parts), 0, -1):
            candidate = '.'.join(parts[:i])
            if candidate in self.module_to_file:
                return candidate
        return None

    def get_start_nodes(self, task_description: str, all_files: List[str]) -> List[str]:
        """
        Эвристически определяет стартовые файлы на основе текста задачи.
        Ищет упоминания имён классов/функций в содержимом файлов.
        Возвращает список имён модулей.
        """
        candidates = set()
        # Извлекаем возможные идентификаторы из описания задачи (CamelCase и snake_case)
        identifiers = set(re.findall(r'\b[A-Z][a-z]+(?:[A-Z][a-z]+)+\b', task_description))
        identifiers.update(re.findall(r'\b[a-z_]+\b', task_description))
        # Фильтруем короткие слова
        identifiers = {id for id in identifiers if len(id) > 3}

        for file_path in all_files:
            if not file_path.endswith('.py'):
                continue
            try:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                for id in identifiers:
                    if id in content:
                        module_name = self.file_to_module.get(file_path)
                        if module_name:
                            candidates.add(module_name)
                        break
            except Exception:
                pass
        return list(candidates)[:5]  # Ограничиваем количество стартовых узлов

    def bfs(self, start_nodes: List[str], depth: int = 2) -> Set[str]:
        """
        Обход в ширину от стартовых узлов на заданную глубину.
        Возвращает множество имён модулей.
        """
        visited = set()
        queue = [(node, 0) for node in start_nodes if node in self.graph]
        while queue:
            node, d = queue.pop(0)
            if node in visited:
                continue
            visited.add(node)
            if d < depth:
                for neighbor in self.graph.successors(node):
                    if neighbor not in visited:
                        queue.append((neighbor, d + 1))
                for neighbor in self.graph.predecessors(node):
                    if neighbor not in visited:
                        queue.append((neighbor, d + 1))
        return visited

    def pagerank(self) -> Dict[str, float]:
        """Возвращает словарь модуль -> значение PageRank."""
        if self.graph.number_of_nodes() == 0:
            return {}
        return nx.pagerank(self.graph)

    def get_files_for_modules(self, modules: Set[str]) -> List[str]:
        """Преобразует имена модулей в абсолютные пути к файлам."""
        return [self.module_to_file[m] for m in modules if m in self.module_to_file]
