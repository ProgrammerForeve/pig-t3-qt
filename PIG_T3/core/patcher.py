import os
import json
import re

import shutil

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


def apply_llm_changes(llm_response: str, root_folder: str = "."):
    """
    Применяет изменения на основе JSON-ответа от LLM.
    Поддерживает действия: create, delete, edit.
    """
    changes_log = []

    try:
        clean_json = clean_json_text(llm_response)
        actions = json.loads(clean_json)
    except json.JSONDecodeError as e:
        return f"❌ Ошибка парсинга JSON: {str(e)}\nУбедитесь, что LLM вернула корректный JSON список."
    except Exception as e:
        return f"❌ Критическая ошибка обработки: {str(e)}"

    if not isinstance(actions, list):
        return "❌ JSON должен быть списком объектов (операций)."

    success_count = 0

    for action in actions:
        action_type = action.get('action')

        if not action_type:
            changes_log.append("⚠️ Пропущен action в блоке.")
            continue

        if action_type == 'move':
            if not action.get('source') or not action.get('destination'):
                changes_log.append("⚠️ Move: пропущен source или destination.")
                continue
            rel_path = action.get('source')
            abs_path = os.path.join(root_folder, rel_path)
        elif action_type == 'mark_step_completed':
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
                    with open(state_path, 'r', encoding='utf-8') as f:
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
                    with open(app_config_path, 'r', encoding='utf-8') as f:
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
                    with open(plan_path, 'r', encoding='utf-8') as f:
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
        elif action_type == 'edit':
            safe = _safe_path(root_folder, rel_path)
            if safe is None:
                changes_log.append(f"❌ Edit: path outside root — {rel_path}")
                continue
            abs_path = safe
            if not os.path.exists(abs_path):
                changes_log.append(f"❌ Edit: файл не найден {rel_path}")
                continue

            operations = action.get('operations', [])
            if not operations:
                changes_log.append(f"⚠️ Edit: нет операций для {rel_path}")
                continue

            try:
                try:
                    with open(abs_path, 'r', encoding='utf-8') as f:
                        lines = f.readlines()
                except UnicodeDecodeError:
                    # Если файл в UTF-16 (например, вывод PowerShell/Windows), пробуем эту кодировку
                    with open(abs_path, 'r', encoding='utf-16', errors='replace') as f:
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
                        # Удаляем дубликат сверху
                        if idx_start > 0 and new_lines_list:
                            if lines[idx_start - 1].rstrip('\r\n') == new_lines_list[0].rstrip('\r\n'):
                                new_lines_list.pop(0)
                        # Удаляем дубликат снизу
                        if idx_end < len(lines) and new_lines_list:
                            if lines[idx_end].rstrip('\r\n') == new_lines_list[-1].rstrip('\r\n'):
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
                            if find_str in full_text:
                                full_text = full_text.replace(find_str, replace_str)
                                file_changed = True
                                changes_log.append(f"✏️ Text Patch {rel_path}: замена фрагмента")
                            else:
                                changes_log.append(f"⚠️ Text Patch {rel_path}: фрагмент не найден")
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

    return "\n".join(changes_log) if changes_log else "⚠️ Нет действий для выполнения."
