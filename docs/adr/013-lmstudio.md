# ADR-013: LM Studio — OpenAI-совместимый backend

## Статус
Принято (2026-11)

## Контекст
PIG-T3 поддерживает три LLM-backend: Ollama (локальный, /api/chat),
Web (Playwright, скрейпинг чатов DeepSeek/Gemini), BomjAPI (ручной
ввод). Ollama — единственный «нативный» локальный LLM, требует
`ollama serve` на `localhost:11434`.

LM Studio (https://lmstudio.ai) — популярная альтернатива: GUI для
управления моделями (GGUF/MLX) и встроенный сервер с **OpenAI-
совместимым API** на `localhost:1234/v1`. Пользователь может
использовать одну и ту же модель через LM Studio или Ollama — но
приложение не видело LM Studio.

## Решение
Добавить **четвёртый backend** — LM Studio через OpenAI-совместимый
API:

- `core/lmstudio_client.py` — тонкий клиент
  (`/v1/chat/completions`, `/v1/embeddings`, `/v1/models`)
- `workers/llm_wrappers.py::LMStudioWrapper` — chat + optimize_context
- `core/rag/embeddings.py::LMStudioEmbeddings` — RAG embeddings
- Префикс `LM Studio: <model>` в UI-списках (OptimizeDialog,
  EditorTab, PlanTab), чтобы отличить от Ollama-моделей
- Асинхронная загрузка моделей через `LMStudioModelsWorker` с
  кешем 60 сек (симметрично OllamaModelsWorker)

## API отличия (Ollama vs LM Studio)

| | Ollama | LM Studio |
| :--- | :--- | :--- |
| Chat | `POST /api/chat` | `POST /v1/chat/completions` |
| Embeddings | `POST /api/embed` | `POST /v1/embeddings` |
| Models | `GET /api/tags` | `GET /v1/models` |
| Формат chat | `{"message": {"content": "..."}}` | `{"choices": [{"message": {"content": "..."}}]}` |
| Формат embeddings | `{"embeddings": [[...]]}` | `{"data": [{"embedding": [...], "index": N}]}` |
| API key | Не требуется | Не требуется (но принимается) |
| Порт | 11434 | 1234 |

## Обоснование

**Почему отдельный backend, а не `openai` Python-клиент:**
- `openai>=1.0` тянет ~2 MB транзитивных зависимостей, +1-2 MB к
  frozen `.exe`.
- Протокол простой (3 эндпоинта, стандартный JSON) — свой клиент
  на `requests` (уже в проекте) обходится в ~100 строк.
- Явный контроль retry/timeout, простые unit-тесты через
  `monkeypatch.setattr(requests, "post", ...)`.
- При желании легко добавить vLLM / Together / OpenAI-proxy —
  все используют один и тот же wire-format, отдельный класс на
  каждый бэкенд.

**Почему префикс `LM Studio: ` в UI, а не отдельный dropdown
«Backend: Ollama / LM Studio»:**
- Префикс не ломает существующий код: `make_llm_client` уже
  диспетчеризует по `startswith`, добавить одну ветку.
- Один список моделей — пользователь видит **все** доступные LLM
  сразу.
- Отдельный dropdown — UX сложнее (два поля вместо одного), плюс
  миграция конфигов.

**Почему асинхронная загрузка моделей (как у Ollama):**
- `GET /v1/models` — HTTP-запрос, 2-сек таймаут при недоступном
  сервере. Синхронный вызов в `__init__` диалога блокирует UI.
- Кеш 60 сек: `lmstudio_models_cache` в `app_config.json`,
  stale-while-revalidate — stale модели показываются сразу, фон
  обновляет.

**Почему embeddings в auto-цепочке (Ollama → LM Studio → ST):**
- Если у пользователя нет Ollama, но есть LM Studio с embeddings-
  моделью — RAG заработает без дополнительной настройки.
- Порядок: Ollama первая (уже поддерживается, чаще встречается);
  LM Studio вторая (легче ST); sentence-transformers третья
  (500 MB torch).

## Последствия

- **`.exe`:** `core/lmstudio_client.py` + `workers/lmstudio_models_worker.py`
  = ~200 строк, +0 новых зависимостей (requests уже в проекте).
- **Кеш в app_config.json:** новый ключ `lmstudio_models_cache`
  (тот же формат, что `ollama_models_cache`).
- **4 новых настройки:** `lmstudio_base_url`,
  `lmstudio_api_key`, `lmstudio_timeout`,
  `lmstudio_embeddings_model` (все с safe defaults —
  существующие конфиги продолжают работать).
- **`RagOptimizer.__init__`** получил опциональный `backend=`
  для инъекции готового объекта (используется `OptimizeWorker`
  чтобы пробросить LM Studio-настройки в фабрику C7a).
- **`OptimizeWorker.__init__`** получил `settings=`, чтобы
  `_make_rag_optimizer` мог читать `lmstudio_*` из конфига.
- **Известное ограничение:** LM Studio не отдаёт dimension
  embedding-модели в `/v1/models` — `LMStudioEmbeddings` делает
  probe через `embed(["probe"])` при первом обращении (как
  Ollama).