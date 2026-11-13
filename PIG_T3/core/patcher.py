import difflib
import json
import logging
import os
import re
import shutil
from dataclasses import dataclass, field

log = logging.getLogger("pig_t3.patcher")


def _parse_regex_find(find_str: str) -> tuple[str, int] | None:
    """'/pattern/flags' → (pattern, flags_int). None если не regex-формат.

    Флаги: g (игнор, no-op), i (IGNORECASE), m (MULTILINE),
    s (DOTALL), x (VERBOSE), u (UNICODE).
    """
    if not find_str or len(find_str) < 3 or not find_str.startswith("/"):
        return None
    body = find_str[1:]
    last = body.rfind("/")
    if last <= 0:
        return None
    pattern = body[:last]
    flags_str = body[last + 1:]
    if not all(c in "gimsux" for c in flags_str):
        return None
    flags = 0
    for c in flags_str:
        if c == "i":
            flags |= re.IGNORECASE
        elif c == "m":
            flags |= re.MULTILINE
        elif c == "s":
            flags |= re.DOTALL
        elif c == "x":
            flags |= re.VERBOSE
        elif c == "u":
            flags |= re.UNICODE
    return pattern, flags


def _build_flexible_pattern(find_str: str) -> "re.Pattern[str]":
    """find_str → regex, где каждая последовательность whitespace
    матчит `\\s+`. Пример: '    def foo():\\n        return 1'
    → 'def\\s+foo\\(\\):\\s+return\\s+1'.
    """
    # Windows-файлы: нормализуем \r\n → \n, чтобы \s+ не съедал лишнего
    # и indent-эвристика не путалась (см. _line_indent_at).
    find_str = find_str.replace("\r\n", "\n").replace("\r", "\n")
    parts = re.split(r"(\s+)", find_str.strip("\n"))
    chunks: list[str] = []
    for p in parts:
        if not p:
            continue
        if p.isspace():
            chunks.append(r"\s+")
        else:
            chunks.append(re.escape(p))
    return re.compile("".join(chunks))


def _line_indent_at(text: str, pos: int) -> str:
    """Ведущий whitespace строки, содержащей pos. '' если pos не
    в начале строки (после indent идёт код)."""
    line_start = text.rfind("\n", 0, pos) + 1
    prefix = text[line_start:pos]
    if prefix.strip():
        return ""  # pos не в начале строки — indent не применим
    return prefix


def _shift_indent(block: str, from_indent: str, to_indent: str) -> str:
    """Сдвинуть все непустые строки block на (from_indent - to_indent)."""
    if not from_indent and not to_indent:
        return block
    if from_indent == to_indent:
        return block
    lines = block.splitlines(keepends=True)
    if not lines:
        return block

    if from_indent.startswith(to_indent):
        prefix = from_indent[len(to_indent):]
        return "".join(
            prefix + ln if ln.strip() else ln for ln in lines
        )
    if to_indent.startswith(from_indent):
        prefix = to_indent[len(from_indent):]
        return "".join(
            ln[len(prefix):] if ln.startswith(prefix) else ln
            for ln in lines
        )
    return block  # несовместимые indent'ы — оставить как есть


def _apply_replace_text(
    full_text: str, find_str: str, replace_str: str
) -> tuple[str, bool, str]:
    r"""Заменить find_str на replace_str с whitespace-flexible поиском
    и адаптацией indent. Возвращает (new_text, changed, status).

    Уровень 0: явная регулярка /pattern/flags (opt-in).
    Уровень 1: exact literal.
    Уровень 2: whitespace-flexible (\s+ для любой группы пробелов).
    """
    # Уровень 0: регулярка /pattern/flags
    parsed = _parse_regex_find(find_str) if find_str else None
    if parsed is not None:
        pattern_str, flags = parsed
        try:
            regex = re.compile(pattern_str, flags)
        except re.error as e:
            return full_text, False, f"invalid regex: {e}"
        new_text, count = regex.subn(replace_str, full_text)
        if count > 0:
            return new_text, True, f"regex ({count} match)"
        return full_text, False, "regex: 0 matches"

    # Уровень 1: exact
    if find_str in full_text:
        return full_text.replace(find_str, replace_str), True, "exact"

    # Уровень 2: whitespace-flexible
    pattern = _build_flexible_pattern(find_str)
    if not pattern.pattern:
        return full_text, False, "empty find_str"
    match = pattern.search(full_text)
    if not match:
        return full_text, False, "not found (exact + flexible)"

    old_indent = _line_indent_at(full_text, match.start())
    new_indent = _line_indent_at(replace_str, 0)
    adapted = _shift_indent(replace_str, old_indent, new_indent)

    new_text = (
        full_text[: match.start()] + adapted + full_text[match.end():]
    )
    return new_text, True, "flexible"
@dataclass
class FailedEdit:
    """Описание упавшего edit для retry_with_context."""

    path: str
    find: str
    replace: str
    error: str
    best_match_line: int | None = None
    best_match_ratio: float = 0.0
    context_lines: list[str] = field(default_factory=list)
    total_lines: int = 0


def _find_near_match(
    full_text: str, find_str: str, threshold: float = 0.6
) -> tuple[int, float, list[str]] | None:
    """Fuzzy-поиск: где find_str "почти" нашёлся.

    Returns:
        (line_1based, ratio, context_lines) — если ratio >= threshold
        None — если не нашли или ratio < threshold
    """
    if not find_str or not full_text:
        return None
    find_lines = find_str.splitlines()
    if not find_lines:
        return None
    text_lines = full_text.splitlines()
    n = len(find_lines)
    if len(text_lines) < n:
        return None
    sm = difflib.SequenceMatcher()
    sm.set_seq2(find_str)
    best_ratio = 0.0
    best_start = -1
    for i in range(len(text_lines) - n + 1):
        window = "\n".join(text_lines[i : i + n])
        sm.set_seq1(window)
        if sm.real_quick_ratio() < threshold:
            continue
        ratio = sm.ratio()
        if ratio > best_ratio:
            best_ratio = ratio
            best_start = i
    if best_ratio < threshold or best_start < 0:
        return None
    ctx_n = max(20, 3 * n)
    lo = max(0, best_start - ctx_n)
    hi = min(len(text_lines), best_start + n + ctx_n)
    context = [f"L{j + 1}: {text_lines[j]}" for j in range(lo, hi)]
    return best_start + 1, best_ratio, context



def _safe_path(root_folder: str, rel_path: str) -> str | None:
    """Резолвит rel_path внутри root_folder. None — если выход за пределы.

    Защита от path traversal в ответе LLM (`../../etc/passwd`).
    """
    if not rel_path or not isinstance(rel_path, str):
        return None
    root_abs = os.path.abspath(root_folder)
    target_abs = os.path.abspath(os.path.join(root_folder, rel_path))
    if target_abs == root_abs:
        return None  # сам корень, не файл
    if not target_abs.startswith(root_abs + os.sep):
        return None
    return target_abs


def _toposort_actions(actions: list) -> list | str:
    """Топологическая сортировка по depends_on (ADR-014)."""
    has_deps = any(
        isinstance(a, dict) and a.get("depends_on") for a in actions
    )
    if not has_deps:
        return actions
    by_id: dict[str, dict] = {
        str(a["id"]): a
        for a in actions
        if isinstance(a, dict) and a.get("id")
    }
    state: dict[str, int] = {}
    order: list[dict] = []
    no_id = [
        a for a in actions
        if not (isinstance(a, dict) and a.get("id"))
    ]

    def visit(nid: str) -> bool:
        s = state.get(nid)
        if s == 1:
            return True
        if s == 0:
            return False
        state[nid] = 0
        node = by_id[nid]
        for dep in node.get("depends_on") or []:
            d = str(dep)
            if d in by_id and not visit(d):
                return False
        state[nid] = 1
        order.append(node)
        return True

    for a in list(by_id.values()):
        if state.get(str(a["id"])) != 1:
            if not visit(str(a["id"])):
                return (
                    f"❌ Циклическая depends_on среди: "
                    f"{sorted(by_id.keys())}"
                )
    return no_id + order


def _rollback_patch(
    root_folder: str, backup_dir: str, log: list[str]
) -> None:
    """Откатить before/ и удалить созданные (after без before). ADR-014."""
    before = os.path.join(backup_dir, "before")
    after = os.path.join(backup_dir, "after")
    root = os.path.abspath(root_folder)

    def _files(base: str) -> list[str]:
        out: list[str] = []
        if not os.path.isdir(base):
            return out
        for dp, _d, fs in os.walk(base):
            for f in fs:
                out.append(
                    os.path.relpath(os.path.join(dp, f), base)
                    .replace("\\", "/")
                )
        return out

    for rel in _files(after):
        if not os.path.exists(os.path.join(before, rel)):
            target = os.path.join(root, rel)
            try:
                if os.path.isdir(target):
                    shutil.rmtree(target)
                elif os.path.exists(target):
                    os.remove(target)
                log.append(f"⏪ Rollback delete: {rel}")
            except OSError as e:
                log.append(f"⚠️ Rollback delete {rel}: {e}")

    for rel in _files(before):
        src = os.path.join(before, rel)
        dst = os.path.join(root, rel)
        try:
            os.makedirs(os.path.dirname(dst) or root, exist_ok=True)
            if os.path.isdir(src):
                shutil.copytree(src, dst, dirs_exist_ok=True)
            else:
                shutil.copy2(src, dst)
            log.append(f"⏪ Rollback restore: {rel}")
        except OSError as e:
            log.append(f"⚠️ Rollback restore {rel}: {e}")

def clean_json_text(text):
    """
    Пытается очистить текст от Markdown оберток ```json ... ``` и найти валидный JSON список.
    """
    text = text.strip()

    # Поиск блока JSON внутри Markdown
    json_match = re.search(r'```(?:json)?\s*(\[.*\])\s*```', text, re.DOTALL)
    if json_match:
        return json_match.group(1)

    # Если просто массив начинается с [ и заканчивается ]
    list_match = re.search(r'(\[\s*{.*}\s*\])', text, re.DOTALL)
    if list_match:
        return list_match.group(1)

    return text


def apply_llm_changes(
    llm_response: str,
    root_folder: str = ".",
    *,
    allow_command_execution: bool = False,
    command_whitelist: str | list[str] = "",
    command_default_timeout: int = 120,
    command_allow_shell_operators: bool = False,
    runner=None,
    patch_context: dict | None = None,
    backup_dir: str | None = None,
):
    """
    Применяет изменения на основе JSON-ответа от LLM.
    Поддерживает действия: create, delete, edit.
    """
    changes_log = []
    aborted = False

    try:
        clean_json = clean_json_text(llm_response)
        actions = json.loads(clean_json)
    except json.JSONDecodeError as e:
        return f"❌ Ошибка парсинга JSON: {e!s}\nУбедитесь, что LLM вернула корректный JSON список."
    except Exception as e:
        return f"❌ Критическая ошибка обработки: {e!s}"

    if not isinstance(actions, list):
        return "❌ JSON должен быть списком объектов (операций)."

    for _a in actions:
        if not isinstance(_a, dict):
            continue
        if _a.get("command") and _a.get("commands"):
            return (
                f"❌ run_command: укажите 'command' или 'commands', не оба "
                f"(взаимоисключающие; id={_a.get('id')})"
            )

    _ids = [
        str(a["id"])
        for a in actions
        if isinstance(a, dict) and a.get("id")
    ]
    if len(_ids) != len(set(_ids)):
        _dupes = sorted({x for x in _ids if _ids.count(x) > 1})
        return f"❌ Дублирующиеся id в патче: {_dupes}"
    _sorted = _toposort_actions(actions)
    if isinstance(_sorted, str):
        return _sorted
    actions = _sorted

    success_count = 0
    _failed_edits: list[FailedEdit] = []
    _read_requests: list[dict] = []
    applied: dict[str, str] = {}

    for action in actions:
        action_type = action.get('action')
        _aid = action.get("id")
        _deps = action.get("depends_on") or []
        if _deps and any(applied.get(str(d)) != "ok" for d in _deps):
            _missing = [
                str(d) for d in _deps
                if applied.get(str(d)) != "ok"
            ]
            changes_log.append(
                f"⏭ Skip {_aid or '?'}: deps not ok {_missing}"
            )
            if _aid:
                applied[str(_aid)] = "skipped"
            continue

        _start = len(changes_log)

        if not action_type:
            changes_log.append("⚠️ Пропущен action в блоке.")
            continue

        if action_type == 'move':
            if not action.get('source') or not action.get('destination'):
                changes_log.append("⚠️ Move: пропущен source или destination.")
                continue
            rel_path = action.get('source')
            abs_path = os.path.join(root_folder, rel_path)
        elif action_type in (
            "mark_step_completed",
            "update_settings",
            "run_command",
        ):
            rel_path = None
            abs_path = None
        else:
            rel_path = action.get('path')
            if not rel_path:
                changes_log.append("⚠️ Пропущен path в блоке.")
                continue
            abs_path = os.path.join(root_folder, rel_path)
        # --- CREATE ---
        if action_type == 'create':
            safe = _safe_path(root_folder, rel_path)
            if safe is None:
                changes_log.append(f"❌ Create: path outside root — {rel_path}")
                continue
            abs_path = safe
            content = action.get('content')
            if content is None:
                changes_log.append(f"⚠️ Create: нет контента для {rel_path}")
                continue
            try:
                os.makedirs(os.path.dirname(abs_path), exist_ok=True)
                with open(abs_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                changes_log.append(f"✅ CREATE: {rel_path}")
                if action.get('explanation'): changes_log.append(f"   💡 Пояснение: {action.get('explanation')}")
                success_count += 1
            except Exception as e:
                changes_log.append(f"❌ Create Error {rel_path}: {e}")

        # --- DELETE ---
        elif action_type == 'delete':
            safe = _safe_path(root_folder, rel_path)
            if safe is None:
                changes_log.append(f"❌ Delete: path outside root — {rel_path}")
                continue
            abs_path = safe
            if os.path.exists(abs_path):
                try:
                    if os.path.isdir(abs_path):
                        shutil.rmtree(abs_path)
                    else:
                        os.remove(abs_path)
                    changes_log.append(f"🗑️ DELETE: {rel_path}")
                    if action.get('explanation'): changes_log.append(f"   💡 Пояснение: {action.get('explanation')}")
                    success_count += 1
                except Exception as e:
                    changes_log.append(f"❌ Delete Error {rel_path}: {e}")
            else:
                changes_log.append(f"⚠️ Delete: файл или папка не найдены {rel_path}")


        # --- MOVE ---
        elif action_type == 'move':
            source_rel = action.get('source')
            dest_rel = action.get('destination')

            if not source_rel or not dest_rel:
                changes_log.append("⚠️ Move: пропущен source или destination.")
                continue

            abs_source = _safe_path(root_folder, source_rel)
            abs_dest = _safe_path(root_folder, dest_rel)
            if abs_source is None:
                changes_log.append(f"❌ Move: source outside root — {source_rel}")
                continue
            if abs_dest is None:
                changes_log.append(f"❌ Move: destination outside root — {dest_rel}")
                continue

            if not os.path.exists(abs_source):
                changes_log.append(f"❌ Move Error: исходный путь не найден {source_rel}")
                continue

            try:
                os.makedirs(os.path.dirname(abs_dest), exist_ok=True)
                shutil.move(abs_source, abs_dest)
                changes_log.append(f"🚚 MOVE: {source_rel} -> {dest_rel}")
                if action.get('explanation'): changes_log.append(f"   💡 Пояснение: {action.get('explanation')}")
                success_count += 1
            except Exception as e:
                changes_log.append(f"❌ Move Error {source_rel}: {e}")
        # --- UPDATE SETTINGS ---
        elif action_type == 'update_settings':
            extensions = action.get('extensions')
            ignore_list = action.get('ignore_list')
            state_updated = False

            # Update Project State
            state_path = os.path.join(root_folder, ".pig", "state.json")
            if os.path.exists(state_path):
                try:
                    with open(state_path, encoding='utf-8') as f:
                        state = json.load(f)
                    if extensions is not None: state['extensions'] = extensions
                    if ignore_list is not None: state['ignore_list'] = ignore_list
                    with open(state_path, 'w', encoding='utf-8') as f:
                        json.dump(state, f, indent=2, ensure_ascii=False)
                    state_updated = True
                except Exception as e:
                    changes_log.append(f"❌ Settings Update Error (Project): {e}")

            # Update App Config fallback
            try:
                base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
                app_config_path = os.path.join(base_dir, "app_config.json")
                if os.path.exists(app_config_path):
                    with open(app_config_path, encoding='utf-8') as f:
                        app_config = json.load(f)
                    if extensions is not None: app_config['extensions'] = extensions
                    if ignore_list is not None: app_config['ignore_list'] = ignore_list
                    with open(app_config_path, 'w', encoding='utf-8') as f:
                        json.dump(app_config, f, indent=4, ensure_ascii=False)
                    state_updated = True
            except Exception:
                pass

            if state_updated:
                changes_log.append(f"⚙️ SETTINGS UPDATED: ext=[{extensions}], ignore=[{ignore_list}]")
                if action.get('explanation'): changes_log.append(f"   💡 Пояснение: {action.get('explanation')}")
                success_count += 1
            else:
                changes_log.append("⚠️ Settings Update: Не удалось найти конфиг для сохранения настроек.")
        # --- MARK STEP COMPLETED ---
        elif action_type == 'mark_step_completed':
            step_id = action.get('step_id')
            if not step_id:
                changes_log.append("⚠️ Mark Step: пропущен step_id.")
                continue
            plan_path = os.path.join(root_folder, ".pig", "plan.json")
            if os.path.exists(plan_path):
                try:
                    with open(plan_path, encoding='utf-8') as f:
                        plan = json.load(f)
                    found = False
                    for step in plan:
                        if str(step.get('id')) == str(step_id):
                            # Completed status
                            if 'completed' in action:
                                step['completed'] = bool(action['completed'])
                            else:
                                step['completed'] = True  # default behavior
                            # Report
                            if 'explanation' in action:
                                step['report'] = action['explanation']
                            elif 'report' in action:
                                report_val = action['report']
                                if report_val is None or report_val == "":
                                    step['report'] = ""
                                else:
                                    step['report'] = str(report_val)
                            # Append description
                            if 'append_description' in action:
                                append_text = str(action['append_description'])
                                if append_text:
                                    current_desc = step.get('description', '')
                                    step['description'] = current_desc + '\n' + append_text if current_desc else append_text
                                    changes_log.append(f"📝 План: описание шага '{step_id}' дополнено.")
                            found = True
                            break
                    if found:
                        with open(plan_path, 'w', encoding='utf-8') as f:
                            json.dump(plan, f, indent=4, ensure_ascii=False)
                        if step.get('completed'):
                            changes_log.append(f"✅ ПЛАН: Этап '{step_id}' отмечен как ВЫПОЛНЕННЫЙ.")
                        else:
                            changes_log.append(f"🔄 ПЛАН: Этап '{step_id}' снята галочка выполнения.")
                        if step.get('report'):
                            changes_log.append(f"   📝 Отчет: {step.get('report', '')}")
                    else:
                        changes_log.append(f"⚠️ План: Этап '{step_id}' не найден.")
                except Exception as e:
                    changes_log.append(f"❌ Plan Error: {e}")
            else:
                changes_log.append("⚠️ План не найден в проекте.")
        # --- EDIT ---
        # ---------- read_lines (ADR-016) ----------
        elif action_type == "read_lines":
            safe = _safe_path(root_folder, rel_path)
            if safe is None:
                changes_log.append(
                    f"❌ read_lines: path outside root — {rel_path}"
                )
                continue
            if not os.path.isfile(safe):
                changes_log.append(
                    f"❌ read_lines: файл не найден {rel_path}"
                )
                continue
            try:
                _start = int(action.get("start", 1))
                _end = int(action.get("end", _start))
            except (TypeError, ValueError):
                changes_log.append(
                    f"⚠️ read_lines: некорректные start/end для {rel_path}"
                )
                continue
            if _end < _start:
                _start, _end = _end, _start
            if _end - _start > 200:
                _end = _start + 200
                changes_log.append(
                    f"   ⚠️ read_lines {rel_path}: диапазон обрезан до 200"
                )
            try:
                with open(safe, encoding="utf-8", errors="replace") as _rf:
                    _all_lines = _rf.readlines()
            except OSError as e:
                changes_log.append(f"❌ read_lines: {rel_path}: {e}")
                continue
            _lo = max(1, _start)
            _hi = min(len(_all_lines), _end)
            _rw_lines = [
                f"L{j}: {_all_lines[j - 1].rstrip()}"
                for j in range(_lo, _hi + 1)
            ]
            _read_requests.append(
                {
                    "path": rel_path,
                    "start": _lo,
                    "end": _hi,
                    "lines": _rw_lines,
                }
            )
            changes_log.append(
                f"📖 read_lines {rel_path}: L{_lo}-{_hi} "
                f"({len(_rw_lines)} строк)"
            )
            if action.get("id"):
                applied[str(action["id"])] = "ok"
            continue

        elif action_type == 'edit':
            safe = _safe_path(root_folder, rel_path)
            if safe is None:
                changes_log.append(f"❌ Edit: path outside root — {rel_path}")
                continue
            abs_path = safe
            if not os.path.exists(abs_path):
                changes_log.append(f"❌ Edit: файл не найден {rel_path}")
                _aid_edit = action.get("id")
                if _aid_edit:
                    applied[str(_aid_edit)] = "failed"
                if action.get("on_failure") in ("abort", "rollback"):
                    if (
                        action.get("on_failure") == "rollback"
                        and backup_dir
                    ):
                        _rollback_patch(
                            root_folder, backup_dir, changes_log
                        )
                    aborted = True
                    changes_log.append("⏹ PIPELINE ABORTED")
                    break
                continue

            operations = action.get('operations', [])
            if not operations:
                changes_log.append(f"⚠️ Edit: нет операций для {rel_path}")
                continue

            try:
                try:
                    with open(abs_path, encoding='utf-8') as f:
                        lines = f.readlines()
                except UnicodeDecodeError:
                    # Если файл в UTF-16 (например, вывод PowerShell/Windows), пробуем эту кодировку
                    with open(abs_path, encoding='utf-16', errors='replace') as f:
                        lines = f.readlines()

                file_changed = False

                # Сортируем операции замены строк с конца, чтобы не сбить индексы
                # Сортируем операции замены строк и вставки с конца, чтобы не сбить индексы
                # Группируем операции, завязанные на номера строк
                line_ops = [op for op in operations if op.get('type') in ('replace_lines', 'insert_after_line')]

                def get_op_line(op):
                    if op.get('type') == 'replace_lines':
                        return op.get('start', 0)
                    return op.get('line', 0)

                line_ops.sort(key=get_op_line, reverse=True)

                text_ops = [op for op in operations if op.get('type') == 'replace_text']

                # 1. Сначала применяем замены/вставки по номерам строк (с конца)
                for op in line_ops:
                    op_type = op.get('type')
                    new_content = op.get('content', "")
                    if new_content is None: new_content = ""

                    # Подготовка контента (добавление переноса строки если нет)
                    new_lines_list = new_content.splitlines(keepends=True)
                    if new_lines_list and not new_lines_list[-1].endswith(('\n', '\r')):
                        new_lines_list[-1] += '\n'

                    # --- LOGIC: REPLACE LINES ---
                    if op_type == 'replace_lines':
                        start = op.get('start')
                        end = op.get('end')
                        if start is None or end is None: continue

                        # Convert 1-based to 0-based
                        idx_start = max(0, start - 1)
                        idx_end = min(len(lines), end)

                        if idx_start > len(lines):
                            changes_log.append(f"⚠️ Line Error {rel_path}: строки {start}-{end} вне диапазона.")
                            continue

                        # --- Anti-Duplication Logic ---
                        # Сравниваем по .strip() — indent и \r\n не важны.
                        # Иначе anti-dup не срабатывает, если LLM скопировал
                        # соседнюю строку с другими пробелами → дублирование.
                        if idx_start > 0 and new_lines_list:
                            if lines[idx_start - 1].strip() == new_lines_list[0].strip():
                                new_lines_list.pop(0)
                        if idx_end < len(lines) and new_lines_list:
                            if lines[idx_end].strip() == new_lines_list[-1].strip():
                                new_lines_list.pop(-1)
                        # ------------------------------

                        lines[idx_start:idx_end] = new_lines_list
                        file_changed = True
                        changes_log.append(f"✏️ Line Patch {rel_path}: строки {start}-{end}")

                    # --- LOGIC: INSERT AFTER LINE ---
                    elif op_type == 'insert_after_line':
                        line_idx = op.get('line')
                        if line_idx is None: continue

                        # Индекс списка (0-based) = Номер строки (1-based)
                        # Пример: Вставить после строки 1. Список индексы: 0. insert(1, ...) вставит после 0.
                        insert_at = max(0, line_idx)
                        if insert_at > len(lines):
                             insert_at = len(lines)

                        lines[insert_at:insert_at] = new_lines_list
                        file_changed = True
                        changes_log.append(f"➕ Insert {rel_path}: после строки {line_idx}")
                # 2. Теперь применяем текстовые замены (по полному содержимому)
                if text_ops:
                    full_text = "".join(lines)
                    for op in text_ops:
                        find_str = op.get('find')
                        replace_str = op.get('replace')
                        if find_str and replace_str is not None:
                            full_text, changed, status = _apply_replace_text(
                                full_text, find_str, replace_str
                            )
                            if changed:
                                file_changed = True
                                note = "" if status == "exact" else f" ({status})"
                                changes_log.append(
                                    f"✏️ Text Patch {rel_path}: замена фрагмента{note}"
                                )
                            else:
                                preview = find_str[:60].replace("\n", "\\n")
                                changes_log.append(
                                    f"⚠️ Text Patch {rel_path}: фрагмент не найден "
                                    f"({status}) — проверьте отступы. "
                                    f"Find: {preview!r}"
                                )
                                if action.get("on_failure") == "retry_with_context":
                                    _m = _find_near_match(
                                        full_text, find_str, threshold=0.6
                                    )
                                    if _m is not None:
                                        _ln, _ratio, _ctx = _m
                                        _failed_edits.append(
                                            FailedEdit(
                                                path=rel_path,
                                                find=find_str,
                                                replace=replace_str or "",
                                                error=status,
                                                best_match_line=_ln,
                                                best_match_ratio=_ratio,
                                                context_lines=_ctx,
                                                total_lines=len(
                                                    full_text.splitlines()
                                                ),
                                            )
                                        )
                                        changes_log.append(
                                            f"   🔧 retry_with_context: "
                                            f"best_match L{_ln} "
                                            f"(ratio {_ratio:.2f})"
                                        )
                    lines = full_text.splitlines(keepends=True)

                if file_changed:
                    with open(abs_path, 'w', encoding='utf-8') as f:
                        f.writelines(lines)
                    if action.get('explanation'): changes_log.append(f"   💡 Пояснение: {action.get('explanation')}")
                    success_count += 1
                else:
                    changes_log.append(f"ℹ️ Edit {rel_path}: изменений не было.")

            except Exception as e:
                changes_log.append(f"❌ Edit Error {rel_path}: {e}")

        # ---------- run_command ----------
        elif action_type == "run_command":
            # ADR-017: XOR — либо command, либо commands
            single = action.get("command")
            batch = action.get("commands")
            if single and batch:
                changes_log.append(
                    "❌ run_command: укажите 'command' или 'commands', не оба"
                )
                continue
            commands = [
                c
                for c in (batch or ([single] if single else []))
                if isinstance(c, str) and c.strip()
            ]
            if not commands:
                changes_log.append("⚠️ run_command: пустая команда")
                continue
            if not allow_command_execution:
                changes_log.append(
                    f"⛔ RUN заблокирован (allow_command_execution=false): "
                    f"{', '.join(commands)}"
                )
                if action.get("on_failure") == "abort":
                    aborted = True
                    break
                continue

            timeout = action.get("timeout_sec", command_default_timeout)
            output_path = action.get("output_path")
            on_failure = action.get("on_failure", "continue")
            report_mode = action.get("report_mode") or (
                "summary" if batch else "full"
            )
            _is_single = len(commands) == 1
            _cmd_output = output_path if _is_single else None

            _results = []  # list[tuple[str, CommandResult | Exception]]
            _aborted_here = False

            for _cmd in commands:
                try:
                    if runner is not None:
                        _r = runner(
                            _cmd,
                            cwd=root_folder,
                            timeout=timeout,
                            output_path=_cmd_output,
                        )
                    else:
                        from .command_runner import (
                            parse_whitelist,
                            run_command,
                        )

                        _r = run_command(
                            _cmd,
                            cwd=root_folder,
                            timeout=timeout,
                            output_path=_cmd_output,
                            whitelist=parse_whitelist(command_whitelist),
                            allow_shell_operators=command_allow_shell_operators,
                        )
                except Exception as e:
                    changes_log.append(f"❌ run_command: {e}")
                    _results.append((_cmd, e))
                    if on_failure == "abort":
                        _aborted_here = True
                        break
                    continue
                _results.append((_cmd, _r))
                if not _r.ok and on_failure == "abort":
                    _aborted_here = True
                    break

            # Combined output_path для batch (single пишет сам через
            # run_command's _write_output)
            if output_path and not _is_single:
                _target_str = _safe_path(root_folder, output_path)
                if _target_str is None:
                    changes_log.append(
                        f"   ⚠️ output_path вне проекта: {output_path}"
                    )
                else:
                    try:
                        os.makedirs(
                            os.path.dirname(_target_str), exist_ok=True
                        )
                        with open(_target_str, "w", encoding="utf-8") as _f:
                            for _cmd, _r in _results:
                                _f.write(f"$ {_cmd}\n")
                                if isinstance(_r, Exception):
                                    _f.write(f"error: {_r}\n\n")
                                    continue
                                _f.write(f"exit_code: {_r.returncode}\n")
                                if _r.timed_out:
                                    _f.write("timed_out: yes\n")
                                _f.write("STDOUT:\n")
                                _f.write(_r.stdout or "")
                                if _r.stderr:
                                    _f.write("\nSTDERR:\n")
                                    _f.write(_r.stderr)
                                _f.write("\n" + "=" * 60 + "\n\n")
                        changes_log.append(
                            f"   📄 output: {output_path}"
                        )
                    except OSError:
                        changes_log.append(
                            f"   ⚠️ не удалось записать output: "
                            f"{output_path}"
                        )

            # Report
            if report_mode == "summary":
                _ok = sum(
                    1
                    for _, _r in _results
                    if not isinstance(_r, Exception) and _r.ok
                )
                _total = len(commands)
                if _ok == _total and not _aborted_here:
                    changes_log.append(
                        f"✅ RUN {_ok}/{_total}: "
                        f"{', '.join(commands)} (exit=0)"
                    )
                else:
                    _failed_idx = next(
                        (
                            i
                            for i, (_, _r) in enumerate(_results)
                            if isinstance(_r, Exception) or not _r.ok
                        ),
                        -1,
                    )
                    if 0 <= _failed_idx < len(commands):
                        changes_log.append(
                            f"❌ RUN {_ok}/{_total}: "
                            f"[{_failed_idx + 1}] {commands[_failed_idx]} "
                            f"(failed)"
                        )
                    else:
                        changes_log.append(
                            f"❌ RUN {_ok}/{_total}: (failed)"
                        )
                    try:
                        from .command_runner import summarize_output
                    except ImportError:
                        summarize_output = None  # type: ignore[assignment]

                    for _cmd, _r in _results:
                        if isinstance(_r, Exception):
                            changes_log.append(f"─── {_cmd} ───")
                            changes_log.append(f"error: {_r}")
                            continue
                        if not _r.ok:
                            changes_log.append(
                                f"─── {_cmd} (exit={_r.returncode}) ───"
                            )
                            _raw = (
                                (_r.stdout or "")
                                + "\n"
                                + (_r.stderr or "")
                            )
                            _out = (
                                summarize_output(_raw)
                                if summarize_output is not None
                                else _raw[:2000]
                            )
                            if _out:
                                changes_log.append(_out)
            else:
                for _cmd, _r in _results:
                    if isinstance(_r, Exception):
                        changes_log.append(f"❌ RUN: {_cmd}: {_r}")
                        continue
                    _st = "✅" if _r.ok else "❌"
                    changes_log.append(
                        f"{_st} RUN: {_cmd} (exit={_r.returncode}"
                        f"{', TIMEOUT' if _r.timed_out else ''})"
                    )
                    _out = (
                        (_r.stdout or "")
                        + ("\n" + _r.stderr if _r.stderr else "")
                    ).strip()
                    if _out:
                        _limit = 2000 if _r.ok else 8000
                        if len(_out) > _limit:
                            _out = (
                                _out[:_limit]
                                + "\n... (обрезано, полный лог — output_path)"
                            )
                        changes_log.append("   ─── RUN output ───")
                        changes_log.append(_out)
                        changes_log.append("   ─────────────────")

            if _aborted_here:
                aborted = True
                changes_log.append("⏹ PIPELINE ABORTED")
                break
        _slice = changes_log[_start:]
        _fail = any(
            s.startswith(("❌", "⛔", "⚠️")) for s in _slice
        )
        _ok = any(
            s.startswith((
                "✅", "🗑️", "🚚", "⚙️", "✏️", "➕", "📖",
                "ℹ️", "📄", "📝", "⏭", "🔄",
            ))
            for s in _slice
        )
        _is_ok = _ok and not _fail
        if _aid:
            applied[str(_aid)] = "ok" if _is_ok else "failed"
        if not _is_ok and action.get("on_failure") in ("abort", "rollback"):
            if action.get("on_failure") == "rollback" and backup_dir:
                _rollback_patch(root_folder, backup_dir, changes_log)
            aborted = True
            changes_log.append("⏹ PIPELINE ABORTED")
            break
        if _is_ok and action.get("on_success") == "abort":
            changes_log.append("⏹ PIPELINE ABORTED (on_success)")
            aborted = True
            break

    if patch_context is not None:
        patch_context["failed_edits"] = _failed_edits
        patch_context["read_requests"] = _read_requests
        patch_context["needs_retry"] = bool(
            _failed_edits or _read_requests
        )
        patch_context["applied_count"] = success_count

    if aborted:
        changes_log.append(
            "⏹ PIPELINE ABORTED (последующие действия не выполнены)"
        )
    return "\n".join(changes_log) if changes_log else "⚠️ Нет действий для выполнения."
