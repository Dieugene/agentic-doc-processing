# Технический план: SimpleLLMGateway

## 1. Анализ задачи

Создать упрощённую версию LLM Gateway без очередей, батчинга и rate limiting. Основное отличие от полной версии (задачи 001-003): минимальная сложность для быстрой отладки, retry только для timeout ошибок (408, 504), остальные ошибки пробрасываются как исключения немедленно.

**Временный характер:** Это промежуточное решение для быстрого прогресса по другим задачам. В будущем может быть заменено полной версией или останется если окажется достаточным.

## 2. Текущее состояние

**Существует в кодовой базе:**
- `02_src/gateway/models.py` - LLMRequest, LLMResponse, LLMMessage, LLMTool, ModelConfig, ModelProvider
- `02_src/gateway/llm_gateway.py` - полная версия LLMGateway с RequestQueue, BatchExecutor
- `02_src/gateway/tests/` - тесты для полной версии

**Что переиспользуем:**
- Все модели из `models.py` без изменений
- Паттерн создания langchain клиентов из `llm_gateway.py`
- Структура логирования из существующего BatchExecutor

**Что НЕ создаём:**
- RequestQueue (нет очередей)
- BatchExecutor (нет батчинга)
- RateLimiter (нет rate limiting)
- ResponseRouter (не нужен при прямом вызове)

## 3. Предлагаемое решение

### 3.1. Общий подход

Создать отдельный класс `SimpleLLMGateway` в новом файле `simple_llm_gateway.py`. Класс создаёт langchain клиентов для каждой модели при инициализации и обрабатывает запросы напрямую (без очередей). Метод `request()` выполняет retry только для timeout ошибок (HTTP 408, 504). Метод `batch()` выполняет последовательные запросы для совместимости с интерфейсом.

### 3.2. Компоненты

#### SimpleLLMGateway
- **Назначение:** Упрощённый gateway без очередей и батчинга
- **Интерфейс:**
  - `__init__(configs: Dict[str, ModelConfig], log_dir: Optional[str] = None)`
  - `async request(request: LLMRequest) -> LLMResponse`
  - `async batch(requests: List[LLMRequest]) -> List[LLMResponse]`
- **Логика request():**
  1. Получить клиента для модели из `_clients`
  2. Конвертировать LLMRequest в langchain формат
  3. Retry loop (макс. 5 попыток):
     - Вызвать `client.ainvoke()`
     - При timeout ошибке → log retry, sleep 1s, продолжить
     - При любой другой ошибке → log error, пробросить исключение немедленно
     - При последней попытке с timeout → пробросить исключение
  4. Вернуть LLMResponse с latency_ms
- **Логика batch():**
  - Последовательный вызов `request()` для каждого элемента
  - Вернуть список ответов
- **Зависимости:** langchain_anthropic, langchain_openai

#### Логирование (встроенные методы)
- `_log_success()` - успешный запрос в `simple_requests.jsonl`
- `_log_retry()` - retry попытка в `simple_retries.jsonl`
- `_log_max_retries_exceeded()` - превышение лимита retry в `simple_errors.jsonl`
- `_log_error()` - не-timeout ошибка в `simple_errors.jsonl`

### 3.3. Структуры данных

**Переиспользуем из models.py:**
```
ModelProvider:
  - CLAUDE_HAIKU, CLAUDE_SONNET, CLAUDE_OPUS
  - GPT_4O_MINI, GPT_4O

ModelConfig:
  - provider: ModelProvider
  - api_key: str
  - model_name: str
  (остальные поля игнорируются в Simple версии)

LLMRequest:
  - request_id: str
  - model: str
  - messages: List[LLMMessage]
  - tools: Optional[List[LLMTool]]
  - temperature: float
  - agent_id: Optional[str]

LLMResponse:
  - request_id: str
  - content: str
  - tool_calls: Optional[List[Dict]]
  - usage: Optional[Dict[str, int]]
  - latency_ms: int
```

### 3.4. Ключевые алгоритмы

**Определение timeout ошибки:**
- Проверить есть ли у исключения атрибут `response`
- Если есть, проверить `response.status_code` в [408, 504]
- Использовать `hasattr()` и `getattr()` для безопасного доступа

**Retry логика:**
- Константы класса: `MAX_RETRIES = 5`, `RETRY_DELAY_SECONDS = 1.0`
- Только timeout ошибки trigger retry
- При любой другой ошибке - немедленный проброс исключения
- После последней неудачной попытки - проброс исключения

**Создание langchain клиента:**
- Для Claude (ModelProvider.CLAUDE_*): ChatAnthropic с timeout=None
- Для GPT (ModelProvider.GPT_*): ChatOpenAI с timeout=None
- При неизвестанном провайдере - ValueError

### 3.5. Изменения в существующем коде

**Создаваемые файлы:**
- `02_src/gateway/simple_llm_gateway.py` - основной класс
- `02_src/gateway/tests/test_simple_gateway.py` - unit тесты

**Изменения в существующих файлах:**
- `02_src/gateway/__init__.py` - добавить экспорт `SimpleLLMGateway`

**НЕ изменяем:**
- `models.py` - модели переиспользуем как есть
- `llm_gateway.py` - полная версия остаётся нетронутой
- Существующие тесты

## 4. План реализации

1. **Создать структуру файла** `simple_llm_gateway.py` с импортами и заглушкой класса
2. **Реализовать `__init__()`**:
   - Сохранить configs и log_dir
   - Создать langchain клиентов для каждой модели через `_create_client()`
   - Настроить логирование через `_setup_logging()`
3. **Реализовать `_create_client()`**:
   - Switch по ModelProvider
   - Создать ChatAnthropic или ChatOpenAI
   - Установить timeout=None
4. **Реализовать `_is_timeout_error()`**:
   - Проверка HTTP status кодов 408, 504
   - Использовать hasattr/getattr для безопасности
5. **Реализовать основной метод `request()`**:
   - Получить клиента из словаря
   - Конвертация в langchain формат
   - Retry loop с логикой timeout
   - Логирование успеха/ошибок
6. **Реализовать метод `batch()`**:
   - Последовательные вызовы request()
7. **Реализовать методы логирования**:
   - _log_success, _log_retry, _log_max_retries_exceeded, _log_error
   - Создание директорий через Path.mkdir(parents=True, exist_ok=True)
8. **Добавить экспорт в `__init__.py`**
9. **Создать unit тесты** `test_simple_gateway.py`:
   - Mock langchain клиентов
   - Тест успешного запроса
   - Тест retry при timeout
   - Тест проброса исключения при не-timeout ошибке
   - Тесть превышения max retries

## 5. Технические критерии приемки

- [ ] TC-001: SimpleLLMGateway создан в `simple_llm_gateway.py`
- [ ] TC-002: Конструктор создаёт langchain клиентов для всех моделей
- [ ] TC-003: `request()` возвращает LLMResponse с корректным latency_ms
- [ ] TC-004: Timeout ошибки (408, 504) trigger retry до 5 раз
- [ ] TC-005: При timeout retry логируется в `simple_retries.jsonl`
- [ ] TC-006: Не-timeout ошибки пробрасываются немедленно без retry
- [ ] TC-007: Превышение max retries пробрасывает исключение
- [ ] TC-008: `batch()` выполняет последовательные запросы
- [ ] TC-009: Логи создаются в `04_logs/gateway/simple/`
- [ ] TC-010: Unit тесты покрывают основные сценарии
- [ ] TC-011: Интерфейс совместим с LLMGateway (те же методы)
- [ ] TC-012: MAX_RETRIES и RETRY_DELAY_SECONDS - константы класса

## 6. Важные детали для Developer

**Timeout определение:**
- Langchain клиенты могут выбрасывать разные исключения при timeout
- Нужно проверять атрибут `response.status_code` у исключения
- httpx выбрасывает HTTPStatusError с response.status_code
- Используй `hasattr(error, 'response')` перед доступом

**Конвертация в langchain формат:**
- Langchain ожидает список кортежей: `[("role", "content"), ...]`
- LLMRequest.messages содержит объекты LLMMessage с полями role, content
- Конвертация: `[(msg.role, msg.content) для msg в request.messages]`

**tool_calls извлечение:**
- Langchain response имеет атрибут `tool_calls` (список)
- Используй `getattr(lc_response, 'tool_calls', None)` для безопасности
- Если None или пустой список - верни None в LLMResponse

**Логирование:**
- JSONL формат: одна JSON строка на запись + newline
- Используй `json.dumps(log_entry, ensure_ascii=False)` для корректного UTF-8
- `Path.mkdir(parents=True, exist_ok=True)` создаёт директорию если отсутствует

**Измерение latency:**
- Используй `asyncio.get_event_loop().time()` вместо `datetime.now()` для точности
- Latency в миллисекундах: `(end - start) * 1000`

**Совместимость типов:**
- LLMRequest и LLMResponse из `models.py` - переиспользуем без изменений
- Простая передача моделей означает совместимость с кодом использующим LLMGateway

**Потокобезопасность:**
- SimpleLLMGateway не создаёт фоновых задач (в отличие от полной версии)
- Не нужно реализовывать `start()` и `stop()` методы
- Все операции выполняются в контексте вызывающего кода
