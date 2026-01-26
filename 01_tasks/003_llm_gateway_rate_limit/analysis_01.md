# Технический план: LLM Gateway - Rate Limit Control

## 1. Анализ задачи

Реализовать превентивный контроль rate limits (RPM/TPM) для предотвращения превышения лимитов API провайдеров. Rate limiter работает **перед** отправкой запроса, в отличие от retry механизма который срабатывает **после** получения 429.

Задача дополняет задачи 001-002: RateLimiter интегрируется в BatchExecutorWithRetry для предварительной проверки перед отправкой батча.

## 2. Текущее состояние

**Существующие модули (задачи 001-002):**
- `models.py`: `LLMRequest`, `LLMResponse`, `ModelConfig` с полями `max_requests_per_minute`, `max_tokens_per_minute`
- `retry_policy.py`: `RetryPolicy` с экспоненциальным backoff
- `batch_executor_retry.py`: `BatchExecutorWithRetry` — переопределяет `execute_batch()`
- `llm_gateway.py`: `BatchExecutor` — базовый класс с `_log_batch()`, `_log_error()`

**Что можно переиспользовать:**
- Структура логирования из `BatchExecutor`
- `ModelConfig` для получения rate limit настроек
- Паттерн наследования от `BatchExecutorWithRetry`

## 3. Предлагаемое решение

### 3.1. Общий подход

**Архитектура:**

```
RateLimiter (координатор)
    ├── TokenCounter (подсчёт токенов)
    └── Map<model_id, RateLimitTracker> (отслеживание использования)

Интеграция:
BatchExecutorWithRateLimit extends BatchExecutorWithRetry
    └── Перед execute_batch() вызывает rate_limiter.check_request()
```

**Скользящее окно:** Хранение истории запросов за последние 60 секунд. Старые записи удаляются автоматически при каждой операции.

**Стратегия при превышении:** Ожидание освобождения слота (`wait_until_available()`), а не немедленный reject.

### 3.2. Компоненты

#### TokenCounter (`rate_limiter.py`)

- **Назначение:** Подсчёт токенов для запросов/ответов
- **Интерфейс:**
  - `count_tokens(text: str, model: str) -> int`
  - `count_request_tokens(request: LLMRequest) -> int`
  - `estimate_response_tokens() -> int`
- **Логика:**
  - При наличии `tiktoken` — точный подсчёт через encoder (cl100k_base)
  - При отсутствии `tiktoken` — приближённая оценка: `len(text) // 4`
  - Учитывает сообщения + tool descriptions + параметры
- **Зависимости:** `tiktoken` (optional, graceful degradation)

#### RateLimitTracker (`rate_limiter.py`)

- **Назначение:** Отслеживание использования в скользящем окне
- **Интерфейс:**
  - `add_request(tokens: int)` — зарегистрировать запрос
  - `get_usage() -> tuple[int, int]` — (requests_count, tokens_count)
  - `can_make_request(max_rpm, max_tpm) -> tuple[bool, str]`
  - `wait_until_available(max_rpm, max_tpm) -> float` — секунды до доступности
- **Логика:**
  - Хранит `deque[(timestamp, tokens)]`
  - При каждой операции очищает записи старше 60 секунд
  - `can_make_request()` проверяет RPM/TPM лимиты
  - `wait_until_available()` вычисляет когда освободится самый старый запрос
- **Зависимости:** `asyncio.Lock` для thread-safety

#### RateLimiter (`rate_limiter.py`)

- **Назначение:** Координация rate limiting для всех моделей
- **Интерфейс:**
  - `check_request(request: LLMRequest) -> tuple[bool, str, float]` — (can_proceed, reason, wait_seconds)
  - `register_request(request: LLMRequest, response: LLMResponse)` — обновить статистику после ответа
- **Логика:**
  - Создаёт `RateLimitTracker` для каждой модели из `configs`
  - `check_request()` вызывает `tracker.can_make_request()`
  - `register_request()` считает токены запроса+ответа, вызывает `tracker.add_request()`
  - Логирует использование в `04_logs/gateway/rate_limits.jsonl`
- **Зависимости:** `TokenCounter`, `ModelConfig`, `LLMRequest`, `LLMResponse`

#### BatchExecutorWithRateLimit (`batch_executor.py`)

- **Назначение:** BatchExecutor с превентивной проверкой rate limits
- **Интерфейс:** наследует `BatchExecutorWithRetry`, переопределяет `execute_batch()`
- **Логика:**
  1. Для каждого запроса в батче вызывает `rate_limiter.check_request()`
  2. Если превышен — логирует, ждёт `wait_seconds` или возвращает ошибку
  3. Вызывает `super().execute_batch()`
  4. После ответов — регистрирует использование (делегируется Response Router или separate pass)
- **Зависимости:** `BatchExecutorWithRetry`, `RateLimiter`

### 3.3. Структуры данных

**RateLimitTracker состояние:**
```python
window_seconds: int = 60
_requests: deque[tuple[datetime, int]]  # (timestamp, tokens)
_lock: asyncio.Lock
```

**Формат лога `rate_limits.jsonl`:**
```json
{
  "timestamp": "2025-01-23T10:45:00",
  "model": "claude-haiku",
  "request_id": "agent_123_step_5",
  "agent_id": "indexator_node_42",
  "reason": "Rate limit exceeded: 1000 requests / 1000 RPM",
  "wait_seconds": 15.5,
  "status": "rate_limited"
}
```

### 3.4. Ключевые алгоритмы

**Скользящее окно очистка:**
При каждой операции (`add_request`, `get_usage`, `can_make_request`, `wait_until_available`) вычисляется `cutoff = now - timedelta(seconds=window_seconds)`. Все записи с `timestamp < cutoff` удаляются из начала deque.

**Подсчёт токенов запроса:**
- Суммируем `count_tokens()` для каждого сообщения
- Для tools добавляем `count_tokens()` для description + parameters
- Не учитываем metadata (agent_id, trace_id)

**Оценка токенов ответа:**
- Если `response.usage` есть — берём `output_tokens` или `completion_tokens`
- Иначе — консервативная оценка 1000 токенов

**Вычисление времени ожидания:**
- Для RPM: время до истечения окна самого старого запроса
- Для TPM: удаляем самые старые запросы пока `sum(tokens) >= max_tpm`, берём время следующего

### 3.5. Изменения в существующем коде

**Модификации:**
- `batch_executor_retry.py`: `BatchExecutorWithRetry` остаётся базовым классом
- `llm_gateway_retry.py`: `LLMGatewayWithRetry` создаст `BatchExecutorWithRateLimit` вместо `BatchExecutorWithRetry`

**Новые файлы:**
- `02_src/gateway/rate_limiter.py` — `TokenCounter`, `RateLimitTracker`, `RateLimiter`
- `02_src/gateway/batch_executor_rate_limit.py` — `BatchExecutorWithRateLimit`

**Изменения в `__init__.py`:**
- Экспортировать новые классы

## 4. План реализации

1. **Шаг 1:** Создать `rate_limiter.py` с `TokenCounter` (без tiktoken зависимости, fallback на //4)
2. **Шаг 2:** Реализовать `RateLimitTracker` с deque и скользящим окном
3. **Шаг 3:** Реализовать `RateLimiter` с координацией tracker'ов и логированием
4. **Шаг 4:** Создать `BatchExecutorWithRateLimit` extending `BatchExecutorWithRetry`
5. **Шаг 5:** Добавить логирование превышений в `_log_rate_limit()`
6. **Шаг 6:** Обновить `llm_gateway_retry.py` для использования `BatchExecutorWithRateLimit`
7. **Шаг 7:** Unit тесты в `tests/test_rate_limiter.py` и `tests/test_batch_executor_rate_limit.py`

## 5. Технические критерии приемки

- [ ] TC-1: `TokenCounter.count_tokens()` возвращает ≠0 для непустого текста
- [ ] TC-2: `RateLimitTracker` корректно отслеживает RPM/TPM в скользящем окне
- [ ] TC-3: `RateLimitTracker.can_make_request()` возвращает `False` при превышении лимитов
- [ ] TC-4: `RateLimitTracker.wait_until_available()` вычисляет корректную задержку
- [ ] TC-5: `RateLimiter` работает с несколькими моделями независимо
- [ ] TC-6: `BatchExecutorWithRateLimit` блокирует запросы при превышении
- [ ] TC-7: Логи пишутся в `04_logs/gateway/rate_limits.jsonl`
- [ ] TC-8: Тесты покрывают сценарии: в пределах лимита, превышение RPM, превышение TPM, скользящее окно

## 6. Важные детали для Developer

**tiktoken optional зависимость:**
- При `ImportError` — `TokenCounter` работает с fallback (`//4`)
- Не добавляй `tiktoken` в `requirements.txt` как обязательную зависимость

**Thread-safety:**
- `RateLimitTracker` использует `asyncio.Lock` для всех операций с `_requests`
- Блокируй на минимальное время (только модификация deque)

**Логирование:**
- Логируй **только** при превышении rate limit, не каждую проверку
- Формат лога совпадает с `batches.jsonl` из `BatchExecutor`
- Создавай директорию `04_logs/gateway/` если отсутствует

**Интеграция с BatchExecutorWithRetry:**
- `execute_batch()` сначала проверяет rate limits, потом вызывает `super()` (retry)
- При превышении с `wait_seconds > 0` — жди через `asyncio.sleep()`
- При превышении с `wait_seconds == 0` — set_exception для всех futures

**Регистрация после ответа:**
- В рамках этой задачи `register_request()` вызывается отдельно (не внутри `execute_batch`)
- Реальная интеграция с Response Router — следующая задача

**Тестовые сценарии:**
- Скользящее окно: запрос сделанный 61 секунду назад не учитывается
- Консервативная оценка ответа: 1000 токенов если `usage` отсутствует
- Несколько моделей: tracker'ы независимы
