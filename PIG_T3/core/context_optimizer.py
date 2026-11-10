import os
import ast
import hashlib
import json
from typing import List, Dict, Set, Optional, Tuple
from .dependency_graph import DependencyGraph

class ContextOptimizer:
    """
    Гибридный оптимизатор контекста.
    Сочетает статический анализ графа, BFS, LLM-ранжирование и усечение файлов.
    """
    def __init__(self, root_folder: str, task: str, limit_tokens: int,
             llm_client=None, cache_dir: Optional[str] = None,
             bfs_depth: int = 2,
             greedy_llm_weight: float = 0.6,
             greedy_pr_weight: float = 0.3,
             greedy_cc_weight: float = 0.1,
             token_bytes_per_token: int = 4,
             ignore_list=None):
        self.root_folder = os.path.abspath(root_folder)
        self.task = task
        self.limit_tokens = limit_tokens
        self.llm_client = llm_client
        self.bfs_depth = bfs_depth
        self.greedy_llm_weight = greedy_llm_weight
        self.greedy_pr_weight = greedy_pr_weight
        self.greedy_cc_weight = greedy_cc_weight
        self.token_bytes_per_token = token_bytes_per_token
        # Accept str or list; normalize to stripped list of substrings.
        if isinstance(ignore_list, str):
            self.ignore_list = [x.strip() for x in ignore_list.split(",") if x.strip()]
        elif ignore_list:
            self.ignore_list = [str(x).strip() for x in ignore_list if str(x).strip()]
        else:
            self.ignore_list = []
        self.cache_dir = cache_dir or os.path.join(self.root_folder, '.pig_cache')
        os.makedirs(self.cache_dir, exist_ok=True)
        self.dep_graph = DependencyGraph(root_folder)
        self.all_files = []
        self.file_metadata = {}
        self.all_files = []
        self.file_metadata = {}

    def optimize(self, progress_callback=None, fallback_callback=None) -> List[str]:
        if progress_callback:
            progress_callback(5, "Сбор Python файлов...")
        self._collect_python_files()
        if not self.all_files:
            return []

        if progress_callback:
            progress_callback(10, "Построение графа зависимостей...")
        self.dep_graph.build(self.all_files)

        bfs_depth = self.bfs_depth
        selected_files = []
        llm_success = False

        if self.llm_client:
            if progress_callback:
                progress_callback(20, "LLM-ранжирование всех файлов...")
            self._collect_metadata(self.all_files)

            try:
                scores = self._llm_rank_files(self.all_files)
                if not scores or all(v == 50 for v in scores.values()):
                    raise ValueError("Модель вернула пустой результат или fallback-оценки.")

                if progress_callback:
                    progress_callback(50, "Отбор файлов по приоритету LLM...")

                sorted_files = sorted(self.all_files, key=lambda x: scores.get(x, 0), reverse=True)
                selected_set = set()
                current_tokens = 0

                for f in sorted_files:
                    if current_tokens >= self.limit_tokens and len(selected_files) > 0:
                        break

                    if scores.get(f, 0) == 0 and len(selected_files) > 0:
                        continue

                    if f not in selected_set:
                        tok = self._estimate_file_tokens(f)
                        if len(selected_files) == 0 or current_tokens + tok <= self.limit_tokens:
                            selected_set.add(f)
                            selected_files.append(f)
                            current_tokens += tok

                        mod = self.dep_graph.file_to_module.get(f)

                        mod = self.dep_graph.file_to_module.get(f)
                        if mod:
                            dep_mods = self.dep_graph.bfs([mod], depth=bfs_depth)
                            dep_files = self.dep_graph.get_files_for_modules(dep_mods)
                            for df in dep_files:
                                if df not in selected_set:
                                    dtok = self._estimate_file_tokens(df)
                                    if current_tokens + dtok <= self.limit_tokens:
                                        selected_set.add(df)
                                        selected_files.append(df)
                                        current_tokens += dtok

                llm_success = True
            except Exception as e:
                print(f"LLM Ranking Error: {e}")
                if fallback_callback:
                    fallback_callback(f"Не удалось использовать LLM ({e}). Выполняется оффлайн поиск.")
                llm_success = False

        if not llm_success:
            if progress_callback:
                progress_callback(20, "Определение стартовых файлов (эвристика)...")
            start_modules = self.dep_graph.get_start_nodes(self.task, self.all_files)
            if not start_modules:
                for f in self.all_files:
                    if self._file_contains_keywords(f, self.task.split()):
                        mod = self.dep_graph.file_to_module.get(f)
                        if mod:
                            start_modules.append(mod)
                            break
            if not start_modules:
                return self.all_files

            if progress_callback:
                progress_callback(40, f"BFS обход от {len(start_modules)} узлов (глубина {bfs_depth})...")
            candidate_modules = self.dep_graph.bfs(start_modules, depth=bfs_depth)
            candidate_files = self.dep_graph.get_files_for_modules(candidate_modules)

            self._collect_metadata(candidate_files)
            pagerank = self.dep_graph.pagerank()

            if progress_callback:
                progress_callback(70, "Финальный отбор с весами...")
            selected_files = self._greedy_selection(candidate_files, {}, pagerank)

        final_selection = []
        for f in selected_files:
            if self._estimate_file_tokens(f) > self.limit_tokens * 0.5:
                trimmed_path = self._trim_large_file(f)
                if trimmed_path:
                    final_selection.append(trimmed_path)
                    continue
            final_selection.append(f)

        if progress_callback:
            progress_callback(95, f"Оптимизация завершена. Отобрано {len(final_selection)} файлов")
        return final_selection

    def _collect_python_files(self):
        """Собирает все .py файлы, учитывая hardcoded + пользовательский ignore."""
        ignore_dirs = {
            'venv', '.venv', '__pycache__', '.git', '.idea',
            'node_modules', 'build', 'dist',
        }
        for root, dirs, files in os.walk(self.root_folder):
            dirs[:] = [
                d for d in dirs
                if d not in ignore_dirs
                and not any(ign in d for ign in self.ignore_list)
            ]
            for file in files:
                if not file.endswith('.py'):
                    continue
                if any(ign in file for ign in self.ignore_list):
                    continue
                self.all_files.append(os.path.join(root, file))

    def _file_contains_keywords(self, file_path: str, keywords: List[str]) -> bool:
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read().lower()
            return any(kw.lower() in content for kw in keywords if len(kw) > 3)
        except:
            return False

    def _collect_metadata(self, files: List[str]):
        """Собирает базовые метаданные: количество строк, имена классов и функций."""
        for f in files:
            try:
                with open(f, 'r', encoding='utf-8', errors='ignore') as fp:
                    content = fp.read()
                lines = content.count('\n')
                tree = ast.parse(content)
                classes = [node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]
                functions = [node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)]
                self.file_metadata[f] = {
                    'lines': lines,
                    'classes': classes,
                    'functions': functions,
                    'path': os.path.relpath(f, self.root_folder)
                }
            except:
                self.file_metadata[f] = {'lines': 0, 'classes': [], 'functions': [], 'path': f}

    def _estimate_tokens(self, files: List[str]) -> int:
        total = 0
        for f in files:
            total += self._estimate_file_tokens(f)
        return total

    def _estimate_file_tokens(self, file_path: str) -> int:
        try:
            size = os.path.getsize(file_path)
            return size // self.token_bytes_per_token  # оценка с настраиваемым коэффициентом
        except:
            return 0

    def _llm_rank_files(self, files: List[str]) -> Dict[str, float]:
        """Вызывает LLM для ранжирования переданных файлов на основе метаданных."""
        # Подготавливаем метаданные для каждого файла
        meta_list = []
        for f in files:
            meta = self.file_metadata.get(f, {})
            meta_list.append({
                'path': meta.get('path', os.path.relpath(f, self.root_folder)),
                'lines': meta.get('lines', 0),
                'classes': meta.get('classes', []),
                'functions': meta.get('functions', [])
            })
        return self.llm_client.optimize_context(self.task, meta_list)

    def _greedy_selection(self, candidate_files: List[str], llm_scores: Dict[str, float],
                          pagerank: Dict[str, float]) -> List[str]:
        """Жадный отбор файлов до лимита токенов с комбинированным весом."""
        # Нормализация PageRank
        max_pr = max(pagerank.values()) if pagerank else 1.0
        # Нормализация цикломатической сложности (заглушка, можно добавить из Radon)
        cc_scores = {}
        for f in candidate_files:
            # Упрощённо: считаем количество if/for/while как индикатор сложности
            try:
                with open(f, 'r', encoding='utf-8') as fp:
                    content = fp.read()
                cc = content.count(' if ') + content.count(' for ') + content.count(' while ')
                cc_scores[f] = cc
            except:
                cc_scores[f] = 1
        max_cc = max(cc_scores.values()) if cc_scores else 1

        # Комбинированный вес: LLM 60%, PageRank 30%, CC 10% (обратная зависимость: чем проще, тем лучше)
        weights = {}
        for f in candidate_files:
            module = self.dep_graph.file_to_module.get(f, '')
            pr = pagerank.get(module, 0.0) / max_pr if max_pr > 0 else 0.0
            llm = llm_scores.get(f, 50) / 100.0
            cc_norm = 1.0 - (cc_scores.get(f, 0) / max_cc if max_cc > 0 else 0.0)
            weight = self.greedy_llm_weight * llm + self.greedy_pr_weight * pr + self.greedy_cc_weight * cc_norm
            weights[f] = weight

        # Сортировка по убыванию веса
        sorted_files = sorted(candidate_files, key=lambda x: weights[x], reverse=True)
        selected = []
        current_tokens = 0
        for f in sorted_files:
            tokens = self._estimate_file_tokens(f)
            if not selected or current_tokens + tokens <= self.limit_tokens:
                selected.append(f)
                current_tokens += tokens
            else:
                break
        return selected

    def _trim_large_file(self, file_path: str) -> Optional[str]:
        """
        Пытается создать усечённую версию файла, оставляя только релевантные классы/функции.
        Возвращает путь к временному файлу или None, если усечение невозможно.
        """
        # Заглушка: возвращаем None, чтобы не усложнять
        return None
