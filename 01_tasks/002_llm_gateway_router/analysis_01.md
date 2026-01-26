# Технический план: LLM Gateway - Response Router и Retry

## 1. Анализ задачи

Необходимо расширить LLM Gateway из задачи 001 двумя механизмами:
1. **Response Router** — компонент для раздачи результатов запросов от BatchExecutor агентам
2. **Retry с экспоненциальным backoff** — обработка временных ошибок API (429 rate limit, 5xx, сетевые)

Текущий BatchExecutor напрямую резолвит futures внутри execute_batch(). Новая архитектура разделяет выполнение запросов и доставку результатов.

## 2. Текущее состояние

**Существующий код из задачи 001:**
- `02_src/gateway/models.py` — LLMRequest, LLMResponse, ModelConfig
- `02_src/gateway/llm_gateway.py` — RequestQueue, BatchExecutor, LLMGateway
- `02_src/gateway/tests/mock_gateway.py` — MockLLMGateway

**Что можно переиспользовать:**
- Модели из models.py (полностью совместимы)
- BatchExecutor как базовый класс для BatchExecutorWithRetry
- LLMGateway как базовый класс для LLMGatewayWithRetry
- Логирование в 04_logs/gateway/

**Текущие ограничения:**
- BatchExecutor.execute_batch() при ошибке завершает все futures с исключением
- Нет механизма retry при временных ошибках
- Нет разделения между выполнением и доставкой результатов

## 3. Предлагаемое решение

### 3.1. Общий подход

**Архитектура:**
1. RetryPolicy — отдельный модуль с логикой retry и backoff
2. ResponseRouter — компонент регистрации и доставки результатов
3. BatchExecutorWithRetry — наследуется от BatchExecutor, добавляет retry
4. LLMGatewayWithRetry — наследуется от LLMGateway, использует новые компоненты

**Интеграция:** BatchExecutorWithRetry перезаписывает execute_batch() для добавления retry цикла. ResponseRouter интегрируется в LLMGatewayWithRetry для централизованной доставки результатов.

### 3.2. Компоненты

#### RetryPolicy
- **Назначение:** Определение логики retry (какие ошибки, сколько попыток, какая задержка)
- **Интерфейс:**
  - `should_retry(error: Exception, attempt: int) -> bool`
  - `get_delay(attempt: int) -> float` (в секундах)
- **Зависимости:** httpx.HTTPStatusError, стандартные исключения
- **Конфигурация:** max_retries, initial_delay_ms, backoff_multiplier, jitter_ms

#### ResponseRouter
- **Назначение:** Регистрация pending запросов и доставка результатов через resolve/resolve_error
- **Интерфейс:**
  - `register(request: LLMRequest, future: asyncio.Future)`
  - `resolve(response: LLMResponse)`
  - `resolve_error(request_id: str, error: Exception)`
- **Зависимости:** LLMRequest, LLMResponse из models.py
- **Хранилище:** Dict[request_id, asyncio.Future] для pending futures

#### BatchExecutorWithRetry
- **Назначение:** Расширение BatchExecutor с retry логикой
- **Интерфейс:** (наследует execute_batch от BatchExecutor)
- **Зависимости:** BatchExecutor, RetryPolicy
- **Логика:** Цикл от 0 до max_retries, при ошибке проверяет should_retry(), ждёт get_delay(), повторяет

#### LLMGatewayWithRetry
- **Назначение:** LLMGateway с интегрированным retry и ResponseRouter
- **Интерфейс:** (наследует методы от LLMGateway)
- **Зависимости:** LLMGateway, RetryPolicy, ResponseRouter
- **Изменения:** Заменяет _executors на BatchExecutorWithRetry, создаёт ResponseRouter

### 3.3. Структуры данных

**RetryPolicy (конфигурация):**
```
max_retries: int = 3
initial_delay_ms: int = 1000
backoff_multiplier: float = 2.0
jitter_ms: int = 500
```

**Логирование retry:**
```
{
  "timestamp": ISO8601,
  "model": str,
  "attempt": int,
  "request_ids": List[str],
  "error": str,
  "delay_ms": float,
  "status": "retry"
}
```

**Логирование ответов (ResponseRouter):**
```
{
  "timestamp": ISO8601,
  "request_id": str,
  "agent_id": Optional[str],
  "latency_ms": int,
  "status": "success"
}
```

### 3.4. Ключевые алгоритмы

**RetryPolicy.get_delay():**
Вычислить базовую задержку: initial_delay_ms × (backoff_multiplier ^ attempt)
Добавить случайный jitter: random.uniform(-jitter_ms, +jitter_ms)
Вернуть сумму в секундах

**RetryPolicy.should_retry():**
Проверить тип исключения:
- httpx.HTTPStatusCode с status 429 → retry
- httpx.HTTPStatusCode с status 500-599 → retry
- ConnectionError, TimeoutError → retry
- Остальные 4xx → не retry
- Прочие исключения → не retry

**BatchExecutorWithRetry.execute_batch():**
Для attempt в range(max_retries + 1):
1. Вызвать super().execute_batch(batch)
2. При успехе — вернуть
3. При ошибке — если should_retry() и attempt < max_retries:
   - Логировать retry
   - await asyncio.sleep(get_delay(attempt))
   - Продолжить цикл
4. Иначе — завершить все futures с ошибкой

**ResponseRouter.resolve():**
Найти future по request_id из pending_futures
Если найден — set_result(response) и удалить из регистров
Логировать успешный ответ

### 3.5. Изменения в существующем коде

**Новые файлы:**
- `02_src/gateway/retry_policy.py` — RetryPolicy
- `02_src/gateway/response_router.py` — ResponseRouter
- `02_src/gateway/batch_executor_retry.py` — BatchExecutorWithRetry
- `02_src/gateway/llm_gateway_retry.py` — LLMGatewayWithRetry

**Модификации:**
- `02_src/gateway/llm_gateway.py` — не изменяется (базовый класс)
- `02_src/gateway/tests/` — добавить новые тестовые файлы

**Обратная совместимость:**
- LLMGateway остаётся без изменений
- LLMGatewayWithRetry — опциональное обновление для использования retry

## 4. План реализации

1. Создать `02_src/gateway/retry_policy.py` с RetryPolicy
2. Создать `02_src/gateway/response_router.py` с ResponseRouter
3. Создать `02_src/gateway/batch_executor_retry.py` с BatchExecutorWithRetry
4. Создать `02_src/gateway/llm_gateway_retry.py` с LLMGatewayWithRetry
5. Создать `02_src/gateway/tests/test_retry_policy.py` с тестами RetryPolicy
6. Создать `02_src/gateway/tests/test_response_router.py` с тестами ResponseRouter
7. Создать `02_src/gateway/tests/test_batch_executor_retry.py` с тестами retry сценариев
8. Создать `02_src/gateway/tests/fixtures/error_scenarios.json` с тестовыми сценариями ошибок

## 5. Технические критерии приемки

- [ ] TC-001: RetryPolicy.get_delay() возвращает корректные значения с jitter
- [ ] TC-002: RetryPolicy.should_retry() возвращает True для 429, 5xx, ConnectionError, TimeoutError
- [ ] TC-003: RetryPolicy.should_retry() возвращает False для 4xx (кроме 429)
- [ ] TC-004: ResponseRouter.register() сохраняет request и future
- [ ] TC-005: ResponseRouter.resolve() корректно резолвит future
- [ ] TC-006: ResponseRouter.resolve_error() корректно завершает future с исключением
- [ ] TC-007: BatchExecutorWithRetry выполняет retry при 429
- [ ] TC-008: BatchExecutorWithRetry выполняет retry при 5xx
- [ ] TC-009: BatchExecutorWithRetry НЕ выполняет retry при 400
- [ ] TC-010: После max_retries ошибки пробрасываются в futures
- [ ] TC-011: Логи retry записываются в 04_logs/gateway/retries.jsonl
- [ ] TC-012: Логи ответов записываются в 04_logs/gateway/responses.jsonl
- [ ] TC-013: Все unit тесты проходят (минимум 10 тестовых сценариев)

## 6. Важные детали для Developer

**Специфичные риски:**

1. **Jitter критичен:** Без случайного разброса при параллельном retry множества запросов возникает "thundering herd" эффект — все retry запросы уходят одновременно, снова вызывая rate limit. Обязательно использовать random.uniform().

2. **HTTPStatusError импорт:** Для проверки status_code нужен импорт httpx. Проверить, что httpx установлен как зависимость langchain.

3. **Future.done() проверка:** Перед set_result/set_exception обязательно проверить future.done() — иначе может быть raised asyncio.InvalidStateError.

4. **Обработка asyncio.CancelledError:** В BatchExecutorWithRetry при отмене задачи нужно корректно выйти из цикла retry, не логируя как ошибку.

5. **Логирование ошибок:** ResponseRouter должен логировать ошибки даже если future не найден (warning) — это помогает отладить проблемы с request_id.

6. **Конфликты при повторном использовании:** ResponseRouter._unregister() должен удалять запрос из обоих словарей (_pending_requests и _pending_futures), иначе утечка памяти.

**Поведение при необработанных исключениях:**
- Если should_retry() вызывает unexpected exception → retry не выполняется, ошибка пробрасывается
- Это предотвращает бесконечный цикл при ошибках в логике retry

**Тестовые сценарии для fixtures/error_scenarios.json:**
- Успешный запрос — без retry
- Временная ошибка 503 — retry успешен на второй попытке
- Rate limit 429 — retry успешен на третьей попытке
- Client error 400 — не retry, ошибка пробрасывается
- После max_retries — ошибка пробрасывается всем futures в батче
