import json
import logging
import os
from datetime import datetime

from ..config import EXTENSION_TO_MARKDOWN

log = logging.getLogger("pig_t3.core.analyzer")



class ProjectAnalyzer:
    def get_markdown_lang(self, ext):
        return EXTENSION_TO_MARKDOWN.get(ext.lower(), '')

    def generate_tree(self, file_paths):
        tree = {}
        for path in sorted(file_paths):
            parts = path.split("/")
            current = tree
            for part in parts:
                current = current.setdefault(part, {})
        lines = []

        def _build(node, prefix=""):
            items = list(node.keys())
            # Сортируем по алфавиту, но элементы с '...' принудительно отправляем в конец
            items.sort(key=lambda x: (1 if x.startswith('...') else 0, x))
            for i, item in enumerate(items):
                is_last = (i == len(items) - 1)
                connector = "└── " if is_last else "├── "
                lines.append(f"{prefix}{connector}{item}")
                if node[item]:
                    ext = " " if is_last else "│ "
                    _build(node[item], prefix + ext)

        _build(tree)
        return "\n".join(lines)

    def _write_patching_instructions(
        self,
        f,
        line_numbers=False,
        use_sharp_indent=False,
        env_block="",
        custom_system_prompt="",
    ):
        instructions = [
            "\n" + "=" * 80,
            "SYSTEM INSTRUCTION: STRICT JSON ENFORCEMENT & AVAILABLE ACTIONS",
            "=" * 80,
            "CRITICAL: YOU ARE AN AUTOMATED AGENT. YOUR ENTIRE RESPONSE MUST BE A SINGLE, VALID JSON ARRAY!",
            "DO NOT write any markdown text, greetings, or explanations outside the JSON array.",
            "If you need to say something to the user, DO NOT write plain text. Put it inside the 'explanation' field of an action object!",
            "",
            "MANDATORY RULES:",
            "1. EVERY 'create' action MUST contain a 'content' field with the FULL file content. Do NOT create empty files and then edit them.",
            "2. EVERY 'edit' action MUST contain an 'operations' array. PREFER 'replace_lines' over 'replace_text'.",
            "3. 'replace_text' is DISCOURAGED. Use it ONLY if line numbers are not available. It requires exact string matching including spaces and indentation.",
            "3a. 'replace_text.find' also supports /pattern/flags regex syntax (e.g. '/def\\s+foo\\(.*\\):/im'). Use it when you need to match a variable number of whitespace or wildcard content. Flags: i (ignorecase), m (multiline), s (dotall), x (verbose).",
            "4. EVERY action except 'update_settings' and 'mark_step_completed' MUST include a 'path' field with a relative file path.",
            "5. When line numbers are provided (they are!), ALWAYS use 'replace_lines' with correct 'start' and 'end'.",
            "6. Do NOT include unchanged neighboring lines in 'content' of 'replace_lines' — that causes duplication.",
            "",
            "👉 RESPONSE STRUCTURE (JSON):",
            "Return a list of operations within a root array. Example:",
            "```json",
            "[",
            "  {",
            "    \"action\": \"update_settings\",",
            "    \"extensions\": \".py, .json\",",
            "    \"ignore_list\": \"venv, .git, temp\",",
            "    \"explanation\": \"Setting up workspace for the current task\"",
            "  },",
            "  {",
            "    \"action\": \"create\",",
            "    \"path\": \"path/to/new_file.py\",",
            "    \"explanation\": \"Created utility script for XYZ\",",
            "    \"content\": \"log.debug('Hello World')\\n\"",
            "  },",
            "  {",
            "    \"action\": \"delete\",",
            "    \"path\": \"path/to/obsolete_file.py\"",
            "  },",
            "  {",
            "    \"action\": \"move\",",
            "    \"source\": \"path/to/old_name.py\",",
            "    \"destination\": \"path/to/new_name.py\"",
            "  },",
            "  {",
            "    \"action\": \"edit\",",
            "    \"path\": \"path/to/existing_file.py\",",
            "    \"explanation\": \"Refactoring the calculation logic\",",
            "    \"operations\": [",
            "       {",
            "         \"type\": \"replace_lines\",",
            "         \"start\": 10, \"end\": 12,",
            "         \"content\": \"    new_code_here()\\n    another_line()\"",
            "       },",
            "       {",
            "         \"type\": \"insert_after_line\",",
            "         \"line\": 15,",
            "         \"content\": \"    log.debug('Debug info')\"",
            "       }",
            "    ]",
            "  },",
            "  {",
            "    \"action\": \"mark_step_completed\",",
            "    \"step_id\": \"step_1\",",
            "    \"completed\": true,",
            "    \"explanation\": \"Step completed successfully\",",
            "    \"append_description\": \"Adding extra notes for next step\"",
            "  }",
            "]",
            "```",
            "👉 OPERATIONS EXPLANATION:",
            "1. **update_settings** — Updates the project's file scanner settings. Use this to focus the context on specific files.",
            "   - 'extensions' (string): Comma-separated file extensions to include.",
            "   - 'ignore_list' (string): Comma-separated folder/file names to ignore.",
            "2. **create** — Creates a STRICTLY NEW file with its FULL content. DO NOT create empty files. Requires 'content'.",
            "3. **delete** — Deletes a file or directory recursively. Requires 'path'.",
            "4. **move** — Moves or renames a file or directory recursively. Requires 'source' and 'destination'.",
            "5. **edit** — Modifies an existing file. PREFER THIS OVER 'create' FOR EXISTING FILES! Requires 'operations' array.",
            "   - 'type: replace_lines': Replaces lines from 'start' to 'end' (inclusive, 1-based numbering). ALWAYS use this when line numbers are provided.",
            "   - 'type: insert_after_line': Inserts 'content' strictly AFTER the specified 'line' number.",
            "   - 'type: replace_text': Exact string replacement. AVOID THIS. Use only if line numbers are unavailable.",
            "6. **mark_step_completed** — Updates the Plan status (if a plan is provided). Requires 'step_id'.",
            "   - 'completed' (boolean): true to check the box, false to uncheck.",
            "   - 'explanation' / 'report': AI execution report.",
            "   - 'append_description': Text appended to the step's description for future context.",
            "7. **run_command** — Executes a shell command in the project root. Use it to VALIDATE your changes (tests, linters, git status). Requires 'command'.",
            "   - 'command' (string): full command line, OS-appropriate. See [EXECUTION ENVIRONMENT] below.",
            "   - 'output_path' (string, optional): relative path inside project, no '..'. Example: \".pig/cmd/pytest.log\". If omitted, output is not saved to disk.",
            "   - 'timeout_sec' (int, optional): 1..3600, default 120.",
            "   - 'on_failure' (string, optional): \"continue\" (default) or \"abort\". \"abort\" stops the entire action array if this command exits non-zero.",
            "   - 'explanation' (string, optional): why this command is run.",
            "   Example:",
            "   {\"action\": \"run_command\", \"command\": \"pytest tests/ -v\",",
            "    \"output_path\": \".pig/cmd/pytest.log\", \"on_failure\": \"abort\",",
            "    \"explanation\": \"Verify the new tests pass\"}",
            "",
            "run_command RULES:",
            "- Use for validation only: pytest, ruff, mypy, pylint, bandit, git status, git diff, smoke runs.",
            "- Do NOT use for destructive operations (rm -rf, git reset --hard, git push --force, DROP TABLE, format) unless the user explicitly asked in the task description.",
            "- For file changes use 'create' / 'edit' / 'move' / 'delete'. run_command is NOT a substitute.",
            "- Split long scripts into multiple run_command actions; each should be short.",
            "   - 'commands' (array, optional, XOR with 'command'): run multiple commands, summary by default. Use this to validate after all edits applied.",
            "   - 'report_mode' (string, optional): 'summary' or 'full'. Default: 'summary' for batch, 'full' for single command.",
            "   BATCH example (validate after edits, no need to read full stdout):",
            "   {\"action\": \"run_command\", \"commands\": [\"pytest tests/ -q\", \"ruff check PIG_T3/\"],",
            "    \"report_mode\": \"summary\", \"on_failure\": \"abort\", \"output_path\": \".pig/cmd/verify.log\"}",
            "- If a command's failure should stop the plan, set \"on_failure\": \"abort\".",
            "",
        ]

        # Environment metadata block (OS, shell, cwd, git, python).
        # Generated by core.agent_context.collect_environment / format_environment_block.
        if env_block:
            instructions.append(env_block)
            instructions.append("")

        if custom_system_prompt and custom_system_prompt.strip():
            instructions.extend(
                [
                    "=" * 80,
                    "USER SYSTEM PROMPT (дополнительные инструкции от пользователя):",
                    "=" * 80,
                    custom_system_prompt.strip(),
                    "",
                ]
            )

        instructions.extend([
            "🛑 ANTI-DESTRUCTION SHIELD (CRITICAL):",
            "ALWAYS use 'edit' for existing files! NEVER use 'create' to overwrite an entire existing file to change a few lines.",
            "IMPORTANT: When using 'replace_lines', do not include unchanged neighboring lines (context) in 'content'. It leads to duplication!"
        ])
        f.write("\n".join(instructions))

    def scan_directory(self, config):
        """
        Scans the directory and returns a list of valid files and empty directories.
        Used by both the GUI (for preview) and the Generator.
        """
        root_folder = config['root_folder']
        extensions = [e.strip() for e in config['extensions'].split(',') if e.strip()]
        ignore_list = [i.strip() for i in config['ignore_list'].split(',') if i.strip()]
        strict_mode = config['strict_mode']
        ignore_self = config.get("ignore_self", False)

        # Prepare forbidden paths
        forbidden_paths = set()
        if ignore_self:
            # Try to guess output file path to ignore it
            base_name = config.get('output_name', 'project_context')
            final_ext = ".txt"
            if base_name.lower().endswith('.txt') or base_name.lower().endswith('.md'):
                base_name = os.path.splitext(base_name)[0]
            output_file = os.path.join(root_folder, base_name + final_ext)

            forbidden_paths.add(os.path.normcase(os.path.abspath(output_file)))
            if config.get("config_path_abs"):
                forbidden_paths.add(os.path.normcase(os.path.abspath(config['config_path_abs'])))
            # Исключение sys.argv[0] убрано, чтобы main.py не пропадал из отчета.
            # Если нужно скрыть запускаемый скрипт, его можно просто убрать галочкой или добавить в ignore_list.

        if not os.path.exists(root_folder):
             return [], []

        paths_to_process = []
        empty_dirs = []

        for root, dirs, files in os.walk(root_folder):
            dirs[:] = [d for d in dirs if not any(ign in d for ign in ignore_list)]
            rel_root = os.path.relpath(root, root_folder)
            if rel_root != "." and any(ign in rel_root.split(os.sep) for ign in ignore_list):
                continue

            has_valid_files = False
            for file in files:
                full_path = os.path.join(root, file)
                norm_path = os.path.normcase(os.path.abspath(full_path))
                if norm_path in forbidden_paths: continue
                if any(ign in file for ign in ignore_list): continue

                matched_ext = None
                for ext_check in extensions:
                    if file.endswith(ext_check):
                        matched_ext = ext_check
                        break

                if matched_ext:
                    if strict_mode and '.' in file[:-len(matched_ext)]: continue
                    paths_to_process.append((full_path, matched_ext))
                    has_valid_files = True

            if not has_valid_files and not dirs and rel_root != ".":
                empty_dirs.append(rel_root.replace("\\", "/"))

        return paths_to_process, empty_dirs

    def process(self, config, progress_callback=None, cancel_callback=None):
        """Генерирует контекст-отчёт через двухфазный streaming.

        Phase 1: scan + чтение метаданных (lines, chars) — контент в памяти
        не задерживается, каждый файл читается и закрывается.
        Phase 2: проход по отсортированным путям, чтение + запись в отчёт
        — одновременно в памяти только один файл.

        Память: O(N) для метаданных + O(1) для контента вместо O(N * avg_size).
        I/O: каждый файл читается дважды (на NVMe незаметно, на HDD 2x).
        """
        root_folder = config["root_folder"]
        base_name = config["output_name"]
        include_empty = config.get("include_empty_folders", False)
        add_edit_prompt = config.get("add_edit_prompt", False)
        line_numbers = config.get("line_numbers", False)
        use_sharp_indent = config.get("use_sharp_indent", False)

        excluded_paths_abs = config.get("excluded_paths", None)
        if excluded_paths_abs is not None:
            excluded_paths_abs = set(excluded_paths_abs)

        final_ext = ".txt"
        if base_name.lower().endswith(".txt") or base_name.lower().endswith(".md"):
            base_name = os.path.splitext(base_name)[0]
        output_file = os.path.join(root_folder, base_name + final_ext)

        # ---------- Phase 1: scan + metadata ----------
        paths_to_process, empty_dirs = self.scan_directory(config)
        total_files_count = len(paths_to_process)
        file_metadata: list[dict] = []
        found_paths: list[str] = []
        total_lines = 0
        total_chars = 0
        excluded_files_grouped: dict = {}

        for i, (full_path, ext) in enumerate(paths_to_process):
            if cancel_callback and cancel_callback():
                return None
            rel_path = os.path.relpath(full_path, root_folder).replace("\\", "/")

            include_content = True
            if excluded_paths_abs is not None:
                if os.path.normcase(os.path.abspath(full_path)) in excluded_paths_abs:
                    include_content = False

            if include_content:
                try:
                    with open(full_path, encoding="utf-8", errors="replace") as f:
                        content = f.read()
                    lines_count = len(content.splitlines())
                    try:
                        _st = os.stat(full_path)
                        _size = _st.st_size
                        _mtime_ns = _st.st_mtime_ns
                    except OSError:
                        _size = 0
                        _mtime_ns = 0
                    file_metadata.append(
                        {
                            "full_path": full_path,
                            "rel_path": rel_path,
                            "lines": lines_count,
                            "chars": len(content),
                            "ext": ext,
                            "size": _size,
                            "mtime_ns": _mtime_ns,
                        }
                    )
                    found_paths.append(rel_path)
                    total_lines += lines_count
                    total_chars += len(content)
                except Exception as e:
                    log.warning(f"Ошибка чтения {rel_path}: {e}")
            else:
                dir_name = os.path.dirname(rel_path)
                _, real_ext = os.path.splitext(rel_path)
                key = (dir_name, real_ext.lower())
                if key not in excluded_files_grouped:
                    excluded_files_grouped[key] = {"paths": [], "count": 0}
                if excluded_files_grouped[key]["count"] < 10:
                    excluded_files_grouped[key]["paths"].append(rel_path)
                excluded_files_grouped[key]["count"] += 1

            if progress_callback:
                progress_callback(i + 1, total_files_count)

        # Group excluded files
        for (dir_name, ext_lower), group_data in excluded_files_grouped.items():
            paths = group_data["paths"]
            total_excluded = group_data["count"]
            paths.sort()
            found_paths.extend(paths)
            if total_excluded > 10:
                more_count = total_excluded - 10
                summary_name = (
                    f"... {more_count} More {ext_lower} files"
                    if ext_lower
                    else f"... {more_count} More files"
                )
                summary_path = f"{dir_name}/{summary_name}" if dir_name else summary_name
                found_paths.append(summary_path)

        file_metadata.sort(key=lambda x: x["rel_path"])

        all_tree_paths = found_paths
        if include_empty:
            all_tree_paths += [f"{d} (empty)" for d in sorted(empty_dirs)]
        tree_view = self.generate_tree(all_tree_paths)
        date_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # ---------- Phase 2: write (one file in memory) ----------
        class _Cancelled(Exception):
            pass

        try:
            with open(output_file, "w", encoding="utf-8") as f:
                intro = (
                    f"PROJECT CONTEXT REPORT\n"
                    f"Generated: {date_str}\n"
                    f"Total Files: {len(file_metadata)}\n"
                    f"Total Lines: {total_lines}\n"
                    f"Total Chars: {total_chars}\n\n"
                    f"INSTRUCTION FOR AI:\n"
                    f"This file contains the full source code of a project.\n"
                    f"The structure is provided in the <project_structure> tag.\n"
                    f'Each file\'s content is wrapped in a <file path="..."> tag.\n'
                    f"Use this context to understand the codebase.\n"
                    f"=" * 80 + "\n\n"
                )
                f.write(intro)
                f.write("<project_structure>\n")
                f.write(tree_view)
                f.write("\n</project_structure>\n\n")
                f.write("=" * 80 + "\n")
                f.write("FILE CONTENTS\n")
                f.write("=" * 80 + "\n\n")

                for idx, m in enumerate(file_metadata):
                    if idx % 10 == 0 and cancel_callback and cancel_callback():
                        raise _Cancelled()
                    try:
                        with open(m["full_path"], encoding="utf-8", errors="replace") as src:
                            content = src.read()
                    except Exception as e:
                        log.warning(f"Ошибка повторного чтения {m['rel_path']}: {e}")
                        continue

                    if line_numbers:
                        numbered = []
                        for num, line in enumerate(content.splitlines(), 1):
                            numbered.append(f"{num:4d} | {line}")
                        content = "\n".join(numbered)

                    f.write(f'<file path="{m["rel_path"]}">\n')
                    f.write(content)
                    if not content.endswith("\n"):
                        f.write("\n")
                    f.write("</file>\n\n")

                if config.get("include_plan", False):
                    plan_path = os.path.join(root_folder, ".pig", "plan.json")
                    if os.path.exists(plan_path):
                        try:
                            with open(plan_path, encoding="utf-8") as pf:
                                plan_data = json.load(pf)
                            f.write("=" * 80 + "\n")
                            f.write("PROJECT PLAN\n")
                            f.write("=" * 80 + "\n")
                            f.write(json.dumps(plan_data, indent=2, ensure_ascii=False) + "\n\n")
                        except Exception:
                            pass

                if add_edit_prompt:
                    from .agent_context import (
                        collect_environment,
                        format_environment_block,
                    )

                    env_block = format_environment_block(
                        collect_environment(root_folder)
                    )
                    self._write_patching_instructions(
                        f,
                        line_numbers,
                        use_sharp_indent,
                        env_block,
                        custom_system_prompt=config.get(
                            "custom_system_prompt", ""
                        )
                        or "",
                    )
        except _Cancelled:
            try:
                os.remove(output_file)
            except OSError:
                pass
            return None

        # Stage 3: сохранить fingerprint для stale-детекта
        try:
            from .report_meta import save_report_meta

            save_report_meta(root_folder, file_metadata, output_file)
        except Exception as e:
            log.warning("save_report_meta failed: %s", e)

        return output_file, len(file_metadata), total_lines, total_chars
