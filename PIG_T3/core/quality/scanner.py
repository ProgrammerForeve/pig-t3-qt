import logging
import os
import sys
import json
import subprocess
from typing import Dict, List
from .models import FileMetrics, Issue

log = logging.getLogger("pig_t3.core.quality.scanner")



class ProjectScanner:
    def __init__(
        self,
        root_path: str,
        chunk_size: int = 50,
        pylint_disable: str = "",
        pylint_max_line_length: int = 120,
        vulture_min_confidence: int = 60,
        bandit_severity: str = "medium",
        tool_timeout: int = 120,
    ):
        self.root = os.path.abspath(root_path)
        self.python_exe = sys.executable
        self.chunk_size = chunk_size
        self.pylint_disable = pylint_disable
        self.pylint_max_line_length = pylint_max_line_length
        self.vulture_min_confidence = vulture_min_confidence
        self.bandit_severity = bandit_severity
        self.tool_timeout = tool_timeout

    def _get_rel_path(self, path: str) -> str:
        """
        Robustly converts absolute or mixed paths to a relative path from project root.
        Handles Windows case-insensitivity and different separators.
        """
        try:
            abs_path = os.path.abspath(path)
            rel = os.path.relpath(abs_path, self.root)
            if rel.startswith("..") and os.name == 'nt':
                return path.replace("\\", "/")
            return rel.replace("\\", "/")
        except Exception:
            return path.replace("\\", "/")

    def _resolve_and_normalize(self, filename: str) -> str:
        """
        Resolves a filename from tool output to the normalized project dictionary key.
        """
        if os.path.isabs(filename):
            return self._normalize_key(filename)
        return self._normalize_key(os.path.join(self.root, filename))

    def _normalize_key(self, path: str) -> str:
        try:
            abs_path = os.path.abspath(path)
            rel = os.path.relpath(abs_path, self.root)
            if rel.startswith(".."):
                res = path.replace("\\", "/")
                return res.lower() if os.name == 'nt' else res

            if os.name == 'nt':
                rel = rel.lower()
            return rel.replace("\\", "/")
        except Exception:
            return path.replace("\\", "/")

    def scan(self, progress_callback=None) -> List[FileMetrics]:
        results_map: Dict[str, FileMetrics] = {}
        final_results: List[FileMetrics] = []

        # 1. Folders to skip to prevent freezing on huge env directories
        SKIP_DIRS = {'venv', '.venv', 'node_modules', '.git', '__pycache__', '.idea', '.vscode', 'build', 'dist', 'bin', 'obj'}

        python_files_abs = []

        def notify(percent, msg):
            if progress_callback:
                progress_callback(percent, msg)

        # 2. Structure Scan
        notify(5, "Сканирование структуры...")

        for root, dirs, files in os.walk(self.root):
            # Modify dirs in-place to skip unwanted folders
            dirs[:] = [d for d in dirs if d.lower() not in SKIP_DIRS]

            for file in files:
                if file.endswith(".py"):
                    full_path = os.path.join(root, file)
                    python_files_abs.append(full_path)

                    rel_path = self._get_rel_path(full_path)
                    norm_key = self._normalize_key(full_path)

                    metric = FileMetrics(path=rel_path)
                    results_map[norm_key] = metric
                    final_results.append(metric)

                    # Calculate SLOC
                    try:
                        with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
                            metric.sloc = sum(1 for line in f if line.strip() and not line.strip().startswith('#'))
                    except:
                        metric.sloc = 0

        total_files = len(python_files_abs)
        if total_files == 0:
            notify(100, "Python файлы не найдены.")
            return []

        log.debug(f"[DEBUG] Found {total_files} python files to scan.")

        # Chunking logic to avoid command line length limits and freezing
        chunk_size = self.chunk_size
        chunks = [python_files_abs[i:i + chunk_size] for i in range(0, len(python_files_abs), chunk_size)]

        # 3. Radon CC
        notify(10, "Анализ сложности (Radon)...")
        try:
            for idx, chunk in enumerate(chunks):
                # Progress from 10% to 30%
                pct = 10 + int(20 * (idx / len(chunks)))
                notify(pct, f"Radon CC ({idx + 1}/{len(chunks)})...")

                cmd = [self.python_exe, "-m", "radon", "cc", "-j", "-a"] + chunk
                try:
                    out = subprocess.check_output(
                        cmd, cwd=self.root, encoding='utf-8',
                        errors='replace', timeout=self.tool_timeout,
                    )
                    data, _ = json.JSONDecoder().raw_decode(out)

                    for filename, metrics in data.items():
                        key = self._resolve_and_normalize(filename)
                        if key in results_map:
                            if not metrics:
                                results_map[key].complexity = 1.0
                            else:
                                total_cc = sum(m['complexity'] for m in metrics)
                                avg_cc = total_cc / len(metrics)
                                results_map[key].complexity = round(avg_cc, 1)
                except Exception as e:
                    log.warning(f"Radon CC chunk error: {e}")
        except Exception as e:
            log.debug(f"Radon CC fatal: {e}")

        # 4. Radon MI
        notify(30, "Индекс поддерживаемости (Radon)...")
        try:
            for idx, chunk in enumerate(chunks):
                # Progress from 30% to 45%
                pct = 30 + int(15 * (idx / len(chunks)))
                notify(pct, f"Radon MI ({idx + 1}/{len(chunks)})...")

                cmd = [self.python_exe, "-m", "radon", "mi", "-j"] + chunk
                try:
                    out = subprocess.check_output(
                        cmd, cwd=self.root, encoding='utf-8',
                        errors='replace', timeout=self.tool_timeout,
                    )
                    data, _ = json.JSONDecoder().raw_decode(out)

                    for filename, metric_data in data.items():
                        key = self._resolve_and_normalize(filename)
                        if key in results_map:
                            results_map[key].maintainability = round(metric_data.get('mi', 0.0), 1)
                except Exception as e:
                    log.warning(f"Radon MI chunk error: {e}")
        except Exception as e:
            log.debug(f"Radon MI fatal: {e}")

        # 5. Pylint
        notify(45, "Проверка качества (Pylint)...")
        try:
            for idx, chunk in enumerate(chunks):
                # Progress from 45% to 80%
                pct = 45 + int(35 * (idx / len(chunks)))
                notify(pct, f"Pylint: пакет {idx + 1}/{len(chunks)}...")

                cmd = [
                    self.python_exe, "-m", "pylint",
                    "--output-format=json", "--exit-zero",
                    f"--max-line-length={self.pylint_max_line_length}",
                ]
                if self.pylint_disable:
                    cmd.append(f"--disable={self.pylint_disable}")
                cmd += chunk

                # Using subprocess.run is safer than check_output for pylint as it returns non-zero often
                proc = subprocess.run(
                    cmd, capture_output=True, text=True, encoding='utf-8',
                    errors='replace', timeout=self.tool_timeout,
                )

                if proc.stdout.strip() and (proc.stdout.startswith('[') or proc.stdout.startswith('{')):
                    try:
                        issues = json.loads(proc.stdout)
                        if isinstance(issues, list):
                            for item in issues:
                                path = item.get('path', '')
                                if not path: continue

                                key = self._normalize_key(os.path.abspath(path) if not os.path.isabs(path) else path)

                                if key in results_map:
                                    msg_type = item.get('type', 'convention')
                                    msg = f"{item.get('message-id')}: {item.get('message')}"
                                    line = item.get('line', 0)

                                    severity = 'info'
                                    penalty = 0.1
                                    if msg_type in ['error', 'fatal']:
                                        severity = 'error'
                                        penalty = 2.0
                                    elif msg_type == 'warning':
                                        severity = 'warning'
                                        penalty = 0.5
                                    elif msg_type == 'refactor':
                                        penalty = 0.25

                                    results_map[key].issues.append(Issue('pylint', msg, line, severity))
                                    results_map[key].pylint_score = max(0.0, results_map[key].pylint_score - penalty)
                    except json.JSONDecodeError:
                        pass
        except Exception as e:
            log.warning(f"Pylint error: {e}")

        # 6. Vulture (Dead code)
        notify(80, "Поиск мертвого кода (Vulture)...")
        try:
            # Vulture runs faster on all files at once usually
            cmd = [
                self.python_exe, "-m", "vulture",
                f"--min-confidence={self.vulture_min_confidence}",
            ] + python_files_abs

            # Simple heuristic guard if too many files
            if len(python_files_abs) < 500:
                proc = subprocess.run(
                    cmd, capture_output=True, text=True, encoding='utf-8',
                    errors='replace', timeout=self.tool_timeout,
                )
                for line in proc.stdout.splitlines():
                    parts = line.split(':', 2)
                    if len(parts) >= 3:
                        filename = parts[0].strip()
                        lineno = parts[1].strip()
                        msg = parts[2].strip()

                        key = self._normalize_key(os.path.abspath(filename))
                        if key in results_map:
                            results_map[key].issues.append(Issue('vulture', msg, int(lineno) if lineno.isdigit() else 0, 'info'))
            else:
                notify(85, "Skipping Vulture (too many files)...")
        except Exception as e:
            log.warning(f"Vulture error: {e}")

        # 7. Bandit
        notify(90, "Аудит безопасности (Bandit)...")
        try:
            cmd = [
                self.python_exe, "-m", "bandit", "-f", "json",
                f"--severity-level={self.bandit_severity}",
            ] + python_files_abs
            # Bandit is usually fast enough, but if it hangs, we can add chunking later
            if len(python_files_abs) < 1000:
                proc = subprocess.run(
                    cmd, capture_output=True, text=True, encoding='utf-8',
                    errors='replace', timeout=self.tool_timeout,
                )
                output = proc.stdout.strip()
                if output.startswith("{"):
                    try:
                        data = json.loads(output)
                        for item in data.get('results', []):
                            filename = item.get('filename')
                            if not filename: continue

                            key = self._normalize_key(os.path.abspath(filename))
                            if key in results_map:
                                severity = item.get('issue_severity', 'LOW').lower()
                                msg = item.get('issue_text', 'Security Issue')
                                line = item.get('line_number', 0)

                                sev_map = 'info'
                                if severity == 'high':
                                    sev_map = 'error'
                                elif severity == 'medium':
                                    sev_map = 'warning'

                                results_map[key].issues.append(Issue('bandit', f"[{severity.upper()}] {msg}", line, sev_map))

                                if severity in ['high', 'medium']:
                                    results_map[key].security_issues += 1
                    except json.JSONDecodeError:
                        pass
            else:
                notify(95, "Skipping Bandit (too many files)...")
        except Exception as e:
            log.warning(f"Bandit error: {e}")

        notify(100, "Готово!")

        # Round final scores
        for m in final_results:
            m.pylint_score = round(m.pylint_score, 2)

        return final_results
