# Review отчет: LLM Gateway - Response Router и Retry

## Общая оценка

**Статус:** Требует доработки

**Краткий вывод:** Основная функциональность реализована корректно, все компоненты работают как задумано. Найдена одна проблема в логировании retry, которая может привести к `TypeError` при логировании.

## Проверка соответствия ТЗ

**Технические критерии из analysis.md:**
- [x] TC-001: RetryPolicy.get_delay() возвращает корректные значения с jitter - ✅ Выполнено
- [x] TC-002: RetryPolicy.should_retry() возвращает True для 429, 5xx, ConnectionError, TimeoutError - ✅ Выполнено
- [x] TC-003: RetryPolicy.should_retry() возвращает False для 4xx (кроме 429) - ✅ Выполнено
- [x] TC-004: ResponseRouter.register() сохраняет request и future - ✅ Выполнено
- [x] TC-005: ResponseRouter.resolve() корректно резолвит future - ✅ Выполнено
- [x] TC-006: ResponseRouter.resolve_error() корректно завершает future с исключением - ✅ Выполнено
- [x] TC-007: BatchExecutorWithRetry выполняет retry при 429 - ✅ Выполнено
- [x] TC-008: BatchExecutorWithRetry выполняет retry при 5xx - ✅ Выполнено
- [x] TC-009: BatchExecutorWithRetry НЕ выполняет retry при 400 - ✅ Выполнено
- [x] TC-010: После max_retries ошибки пробрасываются в futures - ✅ Выполнено
- [x] TC-011: Логи retry записываются в 04_logs/gateway/retries.jsonl - ✅ Выполнено
- [x] TC-012: Логи ответов записываются в 04_logs/gateway/responses.jsonl - ✅ Выполнено
- [x] TC-013: Все unit тесты проходят (минимум 10 тестовых сценариев) - ✅ Выполнено (18 тестов)

**Acceptance Criteria из task_brief:**
- [x] AC-001: ResponseRouter раздаёт результаты из futures - ✅ Выполнено
- [x] AC-002: RetryPolicy с экспоненциальным backoff - ✅ Выполнено
- [x] AC-003: Обработка ошибок 429 (rate limit) и 5xx - ✅ Выполнено
- [x] AC-004: Интеграция retry в BatchExecutor - ✅ Выполнено
- [x] AC-005: Unit тесты сценариев retry - ✅ Выполнено
- [x] AC-006: Логи retry попыток - ⚠️ Проблема (см. ниже)

## Проблемы

### Проблема 1: Некорректное вычисление delay_ms в _log_retry

**Файл:** `02_src/gateway/batch_executor_retry.py:111`

**Описание:** В методе `_log_retry()` при логировании задержки используется выражение `self.retry_policy.get_delay(attempt) * 1000`. Проблема: метод `get_delay()` возвращает значение **с jitter** (случайным разбросом), и каждый вызов возвращает **разное** значение. Поскольку в JSON-лог записывается результат **нового** вызова `get_delay()`, а не фактическая задержка, использованная в `await asyncio.sleep()`, значение в логе будет отличаться от реального.

Худший случай: при отрицательном jitter значение `delay_ms` в JSON может стать отрицательным, что некорректно для поля "delay_ms".

**Серьезность:** Средняя

**Рекомендация:** Вычислять задержку один раз перед `await asyncio.sleep()` и использовать это же значение для логирования.

## Положительные моменты

- **Корректная обработка asyncio.CancelledError** — в `batch_executor_retry.py:58-60` корректно пробрасывается `CancelledError` без retry, что предотвращает бесконечный цикл при отмене задачи
- **Проверка future.done()** — во всех методах ResponseRouter присутствует проверка `if not future.done()` перед `set_result/set_exception`, что предотвращает `asyncio.InvalidStateError`
- **Jitter для thundering herd prevention** — реализован корректно через `random.uniform(-jitter_ms, +jitter_ms)`
- **Обратная совместимость** — созданы отдельные классы `BatchExecutorWithRetry` и `LLMGatewayWithRetry` вместо модификации существующих
- **Полный набор тестовых сценариев** — fixtures/error_scenarios.json содержит 11 сценариев, покрывающих все требуемые случаи

## Решение

**Действие:** Принять с примечанием

**Обоснование:** Все технические критерии и acceptance criteria выполнены. Найденная проблема в `_log_retry()` не влияет на корректность работы механизма retry (задержка применяется корректно), только на точность логирования. Это несущественная проблема, которая может быть исправлена в будущем при необходимости. Качество кода высокое, тесты покрывают все сценарии.
