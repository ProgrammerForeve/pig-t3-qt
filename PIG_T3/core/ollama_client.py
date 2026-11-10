import json
import sys
import re
import sys
import requests
from typing import Optional, Union, List


def get_installed_models() -> List[str]:
    """
    Возвращает список установленных моделей из Ollama.
    """
    try:
        response = requests.get("http://localhost:11434/api/tags", timeout=2)
        if response.status_code == 200:
            data = response.json()
            models = [model['name'] for model in data.get('models', [])]
            return sorted(models)
    except Exception:
        pass
    return []


class OllamaClient:
    def __init__(self, model: str, options: dict = None):
        self.model = model
        self.options = options or {}
        # Параметры отладки как в запросе
        self.debug_prompt = False
        self.debug_thinking = False
        self.debug_answer = False

    def fix_json(self, malformed_text: str) -> str:
        """
        Синхронная обертка для отправки запроса на исправление JSON.
        """
        prompt = f'''Fix the following JSON
Pay special attention to the SCREENING and BALANCING of brackets, quotation marks, etc.
Output ONLY fixed JSON
Do NOT DELETE/CHANGE/ADD any INFORMATION or FIELDS!
{malformed_text}'''

        if self.debug_prompt:
            print("Prompt:\n-----------------------------------------------------------\n" + prompt + "\n-----------------------------------------------------------\n")

        url = "http://localhost:11434/api/chat"

        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": True,
            "options": self.options,
            "format": "",  # ОБЯЗАТЕЛЬНО JSON
        }

        collected_content = []
        collected_thinking = []

        is_printing_thinking = False
        is_printing_answer = False

        try:
            with requests.post(url, json=payload, stream=True) as r:
                r.raise_for_status()

                for line in r.iter_lines():
                    if not line:
                        continue

                    try:
                        chunk = json.loads(line.decode('utf-8'))
                    except json.JSONDecodeError:
                        continue

                    msg = chunk.get('message', {})

                    # --- Обработка Thinking ---
                    val_thinking = msg.get('thinking', '')
                    if val_thinking:
                        collected_thinking.append(val_thinking)
                        if self.debug_thinking:
                            if not is_printing_thinking:
                                print("Thinking:\n-----------------------------------------------------------")
                                is_printing_thinking = True
                            sys.stdout.write(val_thinking)
                            sys.stdout.flush()

                    # --- Обработка Content ---
                    current_content_chunk = msg.get('content', '')

                    # Обработка tool_calls (на всякий случай, хотя здесь json format)
                    if 'tool_calls' in msg and msg['tool_calls']:
                        for tool in msg['tool_calls']:
                            func = tool.get('function', {})
                            args = func.get('arguments', '')
                            if isinstance(args, str):
                                current_content_chunk += args
                            elif isinstance(args, dict):
                                current_content_chunk += json.dumps(args)

                    if current_content_chunk:
                        collected_content.append(current_content_chunk)
                        if self.debug_answer:
                            if is_printing_thinking and not is_printing_answer:
                                print("\n-----------------------------------------------------------\n")
                                is_printing_thinking = False
                            if not is_printing_answer:
                                print("Answer:\n-----------------------------------------------------------")
                                is_printing_answer = True
                            sys.stdout.write(current_content_chunk)
                            sys.stdout.flush()

            # Завершение стриминга
            if is_printing_thinking:
                print("\n-----------------------------------------------------------\n")
            elif is_printing_answer:
                print("\n-----------------------------------------------------------\n")

            final_text = "".join(collected_content).strip()

            # Автоматическая очистка Markdown обертки, если модель вернула ```json ... ```
            md_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', final_text, re.IGNORECASE)
            if md_match:
                final_text = md_match.group(1).strip()

            return final_text

        except Exception as e:
            print(f"Ollama Error: {e}")
            return ""
    def optimize_context(self, task: str, file_metadata: list) -> dict:
        """
        Оценивает важность файлов на основе метаданных (без полного содержимого).
        file_metadata: список словарей с ключами 'path', 'lines', 'classes', 'functions'.
        Возвращает словарь {path: score}.
        """
        # Формируем краткое описание каждого файла
        context_lines = []
        for meta in file_metadata:
            path = meta.get('path', '')
            lines = meta.get('lines', 0)
            classes = ', '.join(meta.get('classes', []))
            functions = ', '.join(meta.get('functions', []))
            context_lines.append(f"File: {path}\nLines: {lines}\nClasses: {classes}\nFunctions: {functions}\n")
        context_text = "\n".join(context_lines)

        prompt = f'''You are a Senior Software Architect. Evaluate the importance of each file for the specific TASK.
TASK:
{task}

RULES:
1. Assign an integer score from 0 to 100 for each file. Gradation is allowed (e.g., 57, 83, 98, 99).
2. SCORING CRITERIA:
   - 100: ONLY if the file is explicitly mentioned in the task by exact name and MUST be in context.
   - 99: If the file name is an inexact match but clearly intended.
   - 98: Files that are 100% necessary/crucial to modify for the given task.
   - 50-97: Gradation of importance (e.g., 57, 83). Highly important, necessary for understanding logic.
   - 30-49: Useful context.
   - 0-29: Unrelated or loosely related.
3. Output ONLY a valid JSON object where keys are file paths and values are integer scores.
Example: {{"path/to/file1.py": 100, "path/to/file2.py": 30, "path/to/file3.py": 57}}

FILES:
{context_text}'''

        url = "http://localhost:11434/api/chat"
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "options": self.options,
            "format": ""
        }
        try:
            response = requests.post(url, json=payload, timeout=300)
            if response.status_code == 200:
                res_text = response.json().get('message', {}).get('content', '')
                import re, json
                match = re.search(r'\{.*\}', res_text, re.DOTALL)
                if match:
                    parsed = json.loads(match.group(0))
                    if isinstance(parsed, dict):
                        return parsed
        except Exception as e:
            print(f"Optimization LLM Error: {e}")
        # Fallback
        return {meta['path']: 50 for meta in file_metadata}
