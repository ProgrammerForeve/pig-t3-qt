from typing import List, Dict, Any


def validate_plan(plan: List[Dict[str, Any]]) -> List[str]:
    """
    Проверяет план на корректность структуры и реалистичность.
    Возвращает список найденных замечаний.
    """
    issues: List[str] = []
    if not isinstance(plan, list) or len(plan) == 0:
        issues.append("План должен быть непустым списком.")
        return issues

    ids = set()
    for i, step in enumerate(plan):
        if not isinstance(step, dict):
            issues.append(f"Шаг {i}: элемент не является словарем.")
            continue

        if 'id' not in step:
            issues.append(f"Шаг {i}: отсутствует поле 'id'.")
        else:
            sid = str(step['id'])
            if sid in ids:
                issues.append(f"Шаг {i}: дублирующийся id '{sid}'.")
            ids.add(sid)

        if 'title' not in step:
            issues.append(f"Шаг {i}: отсутствует поле 'title'.")
        elif len(step['title'].strip()) < 3:
            issues.append(f"Шаг {i}: слишком короткое название.")

        if 'description' not in step:
            issues.append(f"Шаг {i}: отсутствует поле 'description'.")
        elif len(step['description'].strip()) < 10:
            issues.append(f"Шаг {i}: описание слишком короткое (возможно, нереалистичная задача).")

        if 'completed' not in step:
            step['completed'] = False

    return issues
