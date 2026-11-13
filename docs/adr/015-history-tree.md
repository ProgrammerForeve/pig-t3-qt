# ADR-015: Git-like tree history (undo/redo + branch from any state)

## Статус
Принято (2026-11-13, ожидает реализации)

## Контекст

Текущая история (Editor, Plan):
- `history_stack: list[record]`, `redo_stack: list[record]` — **линейная**
- `_on_undo` → pop history → push redo → apply `before/` snapshot
- `_on_redo` → pop redo → push history → apply `after/` snapshot
- **Новое действие после undo — очищает redo_stack** (`.py:432 _on_apply_done`)

Реальный сценарий в PlanTab:
1. Шаг 1 — completed ✅
2. Шаг 2 — completed ✅
3. Шаг 3 — failed ❌ (LLM написал неправильный патч)
4. Пользователь: «хочу откатиться на состояние после шага 2, попробовать шаг 3 с другим prompt»

Сейчас: откат на шаг 2 возможен (undo), но **redo шага 3 стёрт** после применения нового шага 3. Сравнить «вариант A шага 3» vs «вариант B шага 3» — невозможно.

## Решение

История становится **деревом** (технически DAG, каждый узел имеет одного родителя).

### Модель данных

```json
{
  "root": "uuid-root",
  "current": "uuid-3",
  "nodes": {
    "uuid-root": {"parent": null, "children": ["uuid-1"],
      "action_summary": "init", "status": "applied", "files": []},
    "uuid-1": {"parent": "uuid-root", "children": ["uuid-2", "uuid-3"],
      "action_summary": "edit a.py", "status": "applied", "files": ["a.py"]},
    "uuid-2": {"parent": "uuid-1", "children": [],
      "action_summary": "step 3 (attempt A)", "status": "rolled_back",
      "files": ["b.py"]},
    "uuid-3": {"parent": "uuid-1", "children": [],
      "action_summary": "step 3 (attempt B)", "status": "applied",
      "files": ["b.py"]}
  }
}
```

Файлы: `.pig/backups/<uuid>/{before,after}/` — существующий механизм (без изменений).
Хранение: `<project>/.pig/history_tree.json`.

### Операции

- **Apply** (новое действие): `parent=current`, `new_node`, `parent.children.append(new_node)`, backup before/after, `current=new_node`.
- **Undo**: `current=current.parent`, apply `before/` текущего, status=rolled_back. Redo не стирается.
- **Redo**: если у `current` один ребёнок → перейти; если несколько → диалог выбора.
- **Branch from here** (щелчок на X): `current=X`, следующее apply создаст ребёнка X → ветвление.
- **Rollback to here** (щелчок на X, забыть всё после): `current=X`, откатить всех потомков (status=rolled_back, файлы = before).

### UI — новая вкладка «🕐 История»

- `QTreeView` с `HistoryTreeModel(QAbstractItemModel)` — git log --graph style
- Иконки: 🟢 applied, 🔵 current, ⚪ rolled_back, 🔴 failed
- Клик по узлу → diff против родителя (переиспользовать DiffDialog)
- Кнопки: `↩ Rollback to here`, `🌿 Branch from here`, `↪ Redo`
- Auto-scroll к current при открытии

### LLM relevance — честный ответ

**Rollback НЕ помогает LLM напрямую.**
- Ollama, LM Studio, Web scraping, BomjAPI — отправляют **свежий prompt** на каждый запрос, без истории диалога.
- Anthropic/OpenAI prompt caching keyed by prompt hash → rollback меняет prompt → cache miss.

**Что реально даёт:**
1. **Человеку** — сравнить A vs B side-by-side. Особенно в плане из 5 шагов: шаг 3 упал, откатился, попробовал другой prompt, сравнил diff'ы.
2. **PlanTab** — откат на N шагов без потери состояния. Сейчас retry перезапускает step, но мусор от failed step остаётся в файлах.
3. **Future work (ADR-016)** — если появится «continue conversation» (отправка истории LLM), дерево даст контекст «tried A, failed, now trying B».

**Где overkill:**
- EditorTab с 1 патчем — undo/redo достаточно.
- Одиночные правки без multi-step workflow.

**Рекомендация**: реализовать в **PlanTab сначала** (высокая ценность), EditorTab переиспользует тот же `HistoryTreeManager` (UI проще, дерево опционально).

### Миграция

`.pig/editor_history.json` (linear) → **цепочка без ветвлений**: `root → 1 → 2 → 3`. При первом новом действии — обычное apply. При undo+новое — ветвление. Старые `.pig/backups/<uuid>/` переиспользуются без изменений.

## Обоснование

**Почему дерево, а не DAG с merge:**
- Merge двух веток — конфликты + resolution strategy (LLM может помочь, но это отдельная фича ADR-TBD).
- Tree покрывает 95% use cases: «откатился → попробовал другое».

**Почему JSON, не sqlite:**
- `.pig/history_tree.json` — читается глазами, легко отладить.
- Объём: 100 узлов × 200 байт = 20 KB. Не критично. sqlite — overkill.

**Почему новая вкладка, а не панель:**
- Одна история на проект (общая для Plan + Editor).
- Пользователь видит «что произошло за сессию» в одном месте.

## Последствия

**Код:**
- `core/history_tree.py` — `HistoryTreeManager`: load/save, apply/undo/redo/branch, prune (nodes > 100 → удалить мёртвые листья)
- `gui_qt/models/history_tree_model.py` — `HistoryTreeModel(QAbstractItemModel)`, quintptr internalId (ADR-009)
- `gui_qt/tabs/history.py` — `HistoryTab` (QTreeView + diff preview + кнопки)
- `EditorTab` / `PlanTab` — интегрировать вместо `history_stack`/`redo_stack`
- Миграция: `_load_history` в EditorTab читает `.pig/editor_history.json`, конвертирует в linear tree
- Тесты: `test_history_tree.py` (apply/undo/redo/branch/prune/migrate), `test_history_tab.py` (smoke)

**Backward compat:**
- `.pig/editor_history.json` мигрируется автоматически
- Кнопки ↩/↪ работают как раньше (под капотом — дерево)

**Не в scope:**
- Merge веток
- Cross-project history (per-project tree)
- Selective rollback по файлам (полный snapshot)

## Принятые решения

1. **Где показывать branch diff** → **новая вкладка `🕐 История`** (`HistoryTab`). Клик по узлу → встроенный `QTextBrowser` справа с unified diff против родителя. Переиспользует `compute_diffs` + `_diff_to_html` из `DiffDialog`. Не диалог — вкладка, потому что пользователь хочет «полистать историю» без открытия/закрытия модала на каждый узел.

2. **EditorTab и PlanTab** → **одна общая история** на проект (`.pig/history_tree.json`). Узлы с тегом `source: "editor" | "plan"` — для фильтра в UI (`☑ Editor` / `☑ Plan` чекбоксы в тулбаре HistoryTab). Причина: undo в Editor после Plan step должен вернуть состояние «до шага плана», а не «до последнего editor-патча».

3. **Rollback semantics** → **selective** (только файлы этого action). **Проще** в реализации: `node.files` уже содержит список изменённых путей (из `_extract_paths_from_actions`), для каждого — `.pig/backups/<node_id>/before/<path>`. Не нужно «перематывать» все файлы до parent — только те, что изменил узел. Меньше I/O, нет риска «откатить чужое» (файл, изменённый вне PIG-T3). Полный rollback (все файлы к parent) — не нужен, selective покрывает 100% кейсов.

4. **Retention** → **user-managed**. По умолчанию — без авто-prune. Пользователь сам удаляет узлы через контекстное меню (`🗑 Удалить узел и потомков`), либо `Очистить историю` (все кроме current). Причина: auto-prune может удалить важную ветку, которую пользователь ещё не сравнил. Если история > 200 узлов — `HistoryTab` показывает предупреждение «История > 200, рассмотрите очистку», но не удаляет автоматически.

5. **Repeated apply на branch** → **последний ребёнок, без диалога**. Если у current > 1 ребёнок и пользователь жмёт `↪ Redo` — берётся **последний применённый** (по timestamp `applied_at`). Диалог «выберите ветку» — **не показываем** (UX overkill). Если нужна другая ветка — пользователь кликает на неё в дереве (это `branch from here`, не redo).

6. **LLM conversation history** → **да для 5-step, нет для 1-step**. Для Plan step retry (~500 токенов истории): `HistoryTreeManager.get_path_to_root(current)` → сериализация в промпт. Для Editor с 1 патчем — не нужно, каждый патч independent. Детали — в ADR-016 (retry_with_context не включает всю историю, только failed_edits + surrounding actions, max 2000 токенов).
