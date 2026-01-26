# Технический план: LLM Gateway - Queue и Batch Executor

## 1. Анализ задачи

Реализовать базовые компоненты LLM Gateway: очередь запросов (RequestQueue), батч-исполнитель (BatchExecutor) и центральный шлюз (LLMGateway) для централизованного доступа к LLM моделям с batching оптимизацией. Компоненты должны обеспечивать:
- Независимые очереди для каждой модели
- Батчинг запросов (до batch_size или batch_timeout)
- Асинхронное выполнение через futures
- Логирование метаданных в JSON Lines формате
- Mock реализацию для тестирования

## 2. Текущее состояние

**Существующая кодовая база:**
- `02_src/storage/config.py` — пример загрузки переменных окружения через dotenv
- `requirements.txt` — базовые зависимости (pytest, python-docx и др.)
- `.env.example` — пример конфигурации (нет LLM API ключей)

**Что можно переиспользовать:**
- Паттерн загрузки конфигурации из `config.py` для API ключей
- Структуру тестов из существующих модулей
- pytest и pytest-asyncio для тестирования

**Что НЕ существует:**
- Нет структуры для `02_src/gateway/`
- Нет зависимостей для Langchain
- Нет переменных окружения для LLM API

## 3. Предлагаемое решение

### 3.1. Общий подход

LLM Gateway реализует паттерн "Producer-Consumer" с batching:
1. Агенты отправляют запросы через `LLMGateway.request()`
2. Запросы попадают в `RequestQueue` (отдельная очередь на модель)
3. `BatchExecutor` забирает батчи через `get_batch()` и отправляет в API
4. Результаты раздаются через `asyncio.Future`

**Выбор технологий:**
- **asyncio** для асинхронной обработки
- **langchain** для унифицированного доступа к LLM API
- **langchain-anthropic** для Claude моделей
- **langchain-openai** для OpenAI моделей
- **dataclasses** для структур данных

### 3.2. Компоненты

#### RequestQueue
- **Назначение:** Очередь запросов для конкретной модели с накоплением батчей
- **Интерфейс:**
  - `__init__(model: str, batch_size: int, batch_timeout_ms: int)`
  - `async put(request: LLMRequest) -> asyncio.Future[LLMResponse]`
  - `async get_batch() -> List[tuple[LLMRequest, Future]]`
- **Логика:**
  - `put()`: создаёт Future, кладёт (request, future) в asyncio.Queue, возвращает Future
  - `get_batch()`: блокируется на первом элементе, затем накапливает до batch_size или batch_timeout

#### BatchExecutor
- **Назначение:** Исполнитель батчей запросов к LLM API
- **Интерфейс:**
  - `__init__(model_config: ModelConfig, log_dir: Optional[str])`
  - `_create_client() -> ChatAnthropic | ChatOpenAI` (protected метод)
  - `async execute_batch(batch: List[tuple[LLMRequest, Future]]) -> None`
- **Логика:**
  - `_create_client()`: создаёт langchain клиент по провайдеру из ModelConfig
  - `execute_batch()`: конвертирует LLMRequest в langchain формат, отправляет через `.abatch()`, раздаёт результаты в futures, логирует

#### LLMGateway
- **Назначение:** Центральный шлюз для всех агентов
- **Интерфейс:**
  - `__init__(configs: Dict[str, ModelConfig], log_dir: Optional[str])`
  - `async start() -> None` — запуск фоновых обработчиков очередей
  - `async stop() -> None` — остановка обработчиков
  - `async request(request: LLMRequest) -> LLMResponse`
  - `async batch(requests: List[LLMRequest]) -> List[LLMResponse]`
- **Логика:**
  - Создаёт RequestQueue и BatchExecutor для каждой модели из configs
  - `start()`: запускает фоновую задачу `_process_queue()` на каждую модель
  - `request()`: кладёт запрос в очередь модели, возвращает Future
  - `batch()`: группирует запросы по моделям, отправляет параллельно

#### MockLLMGateway
- **Назначение:** Mock для тестов без реальных API вызовов
- **Интерфейс:** Совпадает с LLMGateway
- **Логика:** Возвращает предопределённые ответы из fixtures без задержек

### 3.3. Структуры данных

**ModelProvider (Enum):**
```python
class ModelProvider(str, Enum):
    CLAUDE_HAIKU = "claude-haiku"
    CLAUDE_SONNET = "claude-sonnet"
    CLAUDE_OPUS = "claude-opus"
    GPT_4O_MINI = "gpt-4o-mini"
    GPT_4O = "gpt-4o"
    LOCAL_LLAMA = "local-llama"
```

**ModelConfig (dataclass):**
```python
@dataclass
class ModelConfig:
    provider: ModelProvider
    endpoint: str
    api_key: str
    model_name: str
    max_requests_per_minute: Optional[int] = None  # для информации
    max_tokens_per_minute: Optional[int] = None    # для информации
    batch_size: int = 10
    batch_timeout_ms: int = 100
```

**LLMMessage (dataclass):**
```python
@dataclass
class LLMMessage:
    role: str  # "system" | "user" | "assistant"
    content: str
```

**LLMTool (dataclass):**
```python
@dataclass
class LLMTool:
    name: str
    description: str
    parameters: Dict[str, Any]
```

**LLMRequest (dataclass):**
```python
@dataclass
class LLMRequest:
    request_id: str
    model: str
    messages: List[LLMMessage]
    tools: Optional[List[LLMTool]] = None
    temperature: float = 0.0
    agent_id: Optional[str] = None
    trace_id: Optional[str] = None
```

**LLMResponse (dataclass):**
```python
@dataclass
class LLMResponse:
    request_id: str
    content: str
    tool_calls: Optional[List[Dict[str, Any]]] = None
    usage: Optional[Dict[str, int]] = None
    latency_ms: int = 0
```

### 3.4. Ключевые алгоритмы

**Batch накопление в RequestQueue.get_batch():**
1. Блокируемся на `queue.get()` для первого запроса
2. Устанавливаем deadline = now + batch_timeout_ms
3. В цикле пока размер < batch_size:
   - Вычисляем остаток таймаута
   - Если timeout <= 0: break
   - Пытаемся получить запрос с timeout через `asyncio.wait_for()`
   - При TimeoutError: выходим из цикла
4. Возвращаем накопленный батч

**Batch execution в BatchExecutor.execute_batch():**
1. Разделяем батч на requests и futures
2. Конвертируем LLMRequest → langchain формат: список кортежей [(role, content), ...]
3. Вызываем `await client.abatch(lc_messages)`
4. Для каждой пары (request, future, response):
   - Создаём LLMResponse с latency_ms
   - Вызываем `future.set_result(llm_response)`
5. При exception: `future.set_exception(e)` для всех futures

**Логирование:**
- Успешные батчи: `04_logs/gateway/batches.jsonl`
- Ошибки: `04_logs/gateway/errors.jsonl`
- Формат: JSON Lines (одна JSON запись на строку)
- Поля: timestamp, model, batch_size, request_ids, latency_ms, status
- **Важно:** НЕ логировать содержимое промптов (безопасность, v1.0)

### 3.5. Изменения в существующем коде

**Новые файлы:**
- `02_src/gateway/__init__.py`
- `02_src/gateway/models.py` — структуры данных
- `02_src/gateway/llm_gateway.py` — LLMGateway, RequestQueue, BatchExecutor
- `02_src/gateway/tests/__init__.py`
- `02_src/gateway/tests/test_llm_gateway.py`
- `02_src/gateway/tests/mock_gateway.py` — MockLLMGateway
- `02_src/gateway/tests/fixtures/sample_responses.json`

**Обновления:**
- `requirements.txt`: добавить langchain зависимости
- `.env.example`: добавить шаблоны для LLM API ключей

## 4. План реализации

1. **Создать структуры данных** в `02_src/gateway/models.py`
   - ModelProvider enum
   - ModelConfig, LLMMessage, LLMTool, LLMRequest, LLMResponse dataclasses

2. **Добавить зависимости** в `requirements.txt`
   - langchain>=0.1.0
   - langchain-anthropic>=0.1.0
   - langchain-openai>=0.1.0

3. **Реализовать RequestQueue** в `02_src/gateway/llm_gateway.py`
   - `__init__()`, `put()`, `get_batch()`

4. **Реализовать BatchExecutor** в `02_src/gateway/llm_gateway.py`
   - `_create_client()`, `execute_batch()`, методы логирования

5. **Реализовать LLMGateway** в `02_src/gateway/llm_gateway.py`
   - `__init__()`, `start()`, `stop()`, `request()`, `batch()`, `_process_queue()`

6. **Создать MockLLMGateway** в `02_src/gateway/tests/mock_gateway.py`
   - Имитация batch execution без реальных API вызовов

7. **Написать unit тесты** в `02_src/gateway/tests/test_llm_gateway.py`
   - Тесты RequestQueue: put/get_batch
   - Тесты BatchExecutor: execute_batch с mock client
   - Тесты LLMGateway: request/batch/start/stop

8. **Обновить .env.example** шаблонами для API ключей

## 5. Технические критерии приемки

- [ ] TC-001: RequestQueue накапливает батчи до batch_size или batch_timeout
- [ ] TC-002: BatchExecutor создаёт корректный langchain клиент для каждого провайдера
- [ ] TC-003: BatchExecutor.execute_batch() конвертирует запросы и раздаёт результаты в futures
- [ ] TC-004: LLMGateway.start() запускает фоновые обработчики для всех моделей
- [ ] TC-005: LLMGateway.request() возвращает корректный LLMResponse через Future
- [ ] TC-006: LLMGateway.batch() группирует запросы по моделям
- [ ] TC-007: Логи записываются в JSON Lines формат в 04_logs/gateway/
- [ ] TC-008: MockLLMGateway реализован без langchain зависимостей
- [ ] TC-009: Все unit тесты проходят
- [ ] TC-010: Код покрывает >80% по coverage

## 6. Важные детали для Developer

### Параметры batch_size и batch_timeout
- **batch_size = 10** по умолчанию: баланс между latency (накопление) и throughput (меньше API вызовов)
- **batch_timeout = 100ms** по умолчанию: максимальное ожидание для накопления батча
- Для разных моделей могут быть разные значения (через ModelConfig)

### Конфигурация через .env
- Используй паттерн из `02_src/storage/config.py`: `load_dotenv()` + `os.getenv()`
- Добавь переменные: `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`
- При отсутствии API ключей код должен падать с понятным исключением при инициализации

### Langchain формат сообщений
- Langchain ожидает список кортежей: `[("system", "..."), ("user", "...")]`
- Не список объектов LLMMessage!
- Конвертируй в execute_batch(): `[(msg.role, msg.content) for msg in req.messages]`

### Обработка ошибок в execute_batch()
- При ошибке API: ВСЕ futures в батче должны получить exception через `set_exception()`
- Не оставляй futures висеть — это приведёт к deadlock
- Логируй ошибку в errors.jsonl

### Формат логов
- JSON Lines: одна JSON запись на строку
- Используй `json.dumps(..., ensure_ascii=False)` для поддержки кириллицы
- Поля для batches.jsonl: timestamp, model, batch_size, request_ids, latency_ms, status
- Поля для errors.jsonl: timestamp, model, request_ids, error, status

### asyncio specifics
- Future создаётся через `asyncio.Future()` или `asyncio.get_event_loop().create_future()`
- Не вызывай `.set_result()` или `.set_exception()` дважды — проверь `future.done()`
- При stop() вызови `task.cancel()` и await результатов с `return_exceptions=True`

### MockLLMGateway особенности
- Не наследуйся от LLMGateway — дублируй интерфейс
- Возвращай фиктивные LLMResponse с latency_ms = 0
- Используй fixtures из `sample_responses.json` для предопределённых ответов

### Пути к логам
- Логи должны создаваться в `04_logs/gateway/`
- Используй `Path(self.log_dir) / "gateway" / "batches.jsonl"`
- Создавай директории через `mkdir(parents=True, exist_ok=True)`
