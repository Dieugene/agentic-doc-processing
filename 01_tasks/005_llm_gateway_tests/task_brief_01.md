# Задача 005: Unit тесты SimpleLLMGateway

## Что нужно сделать

Создать unit тесты для SimpleLLMGateway — упрощённой версии LLM Gateway без очередей, батчинга и rate limiting.

## Зачем

SimpleLLMGateway — временный вариант для быстрого прогресса по другим задачам. Тесты обеспечивают корректность работы retry логики для timeout ошибок и интеграцию с другими модулями.

## Примечание

**Это ИЗМЕНЁННАЯ версия task_brief.** Оригинальный task_brief описывал тесты для сложной версии LLM Gateway (задачи 001-003: RequestQueue, BatchExecutor, ResponseRouter, RetryPolicy, RateLimiter), но решение было использовать SimpleLLMGateway (задача 001b).

Задача 005 была переадаптирована Analyst на тесты SimpleLLMGateway, implementation выполнен, review пройден. Этот task_brief обновлён для отражения фактической реализации.

## Acceptance Criteria

- [x] AC-001: Тесты инициализации SimpleLLMGateway с configs
- [x] AC-002: Тесты метода request() с retry для timeout (408, 504)
- [x] AC-003: Тесты метода batch() (последовательные вызовы)
- [x] AC-004: Тесты retry логики (5 попыток, задержка 1с)
- [x] AC-005: Тесты логирования (simple_requests.jsonl, simple_retries.jsonl, simple_errors.jsonl)
- [x] AC-006: Тесты обработки не-timeout ошибок (сразу exception)
- [x] AC-007: Покрытие >80% (фактически 96%)

## Контекст

**Зависимость от задачи 001b:**

Эта задача создаёт тесты для SimpleLLMGateway:
- Простая обёртка над API (без очередей, батчинга, rate limiting)
- Retry только для timeout ошибок на стороне провайдера (408, 504)
- Константы: MAX_RETRIES=5, RETRY_DELAY_SECONDS=1.0 (в коде, не в env)

**Что уже реализовано:**
- SimpleLLMGateway в `02_src/gateway/simple_llm_gateway.py` ✅
- Тесты в `02_src/gateway/tests/test_simple_gateway.py` ✅
- Покрытие 96% (29/29 тестов проходят) ✅
- MockLLMGGateway в `02_src/gateway/tests/mock_gateway.py` (из задачи 001) ✅

**Сложная версия (001-003):**
- Задачи 001-003 реализованы, но **не используются**
- Тесты для сложной версии (RequestQueue, BatchExecutor и т.д.) не создавались
- Это ожидаемо, так как SimpleLLMGateway — временный вариант

## Структура проекта

```
02_src/
├── gateway/
│   ├── simple_llm_gateway.py     # SimpleLLMGateway
│   ├── models.py                   # Общие модели
│   └── tests/
│       ├── test_simple_gateway.py   # Тесты SimpleLLMGateway ✅
│       ├── mock_gateway.py          # MockLLMGateway (из 001) ✅
│       └── fixtures/
│           └── sample_responses.json
04_logs/
└── gateway/
    ├── simple_requests.jsonl
    ├── simple_retries.jsonl
    └── simple_errors.jsonl
```

## Примечания для Analyst

**Важно:**
- Задача уже выполнена, review пройден
- Этот task_brief обновляется для консистентности документации
- Тесты уже созданы Developer в `test_simple_gateway.py`

**Ключевые решения (уже приняты):**
1. Использовать pytest для асинхронных тестов
2. Мокать langchain клиентов через AsyncMock
3. Timeout ошибки: 408 (Request Timeout), 504 (Gateway Timeout)
4. Фикстуры для тестов в fixtures/
5. Покрытие >80% (фактически 96%)

## Зависимости

- Задача 001b: SimpleLLMGateway (тесты для него)
- Задачи 001-003: Сложная версия LLM Gateway (реализована, но не используется)

## Следующие задачи

После завершения:
- Итерация 1 полностью завершена ✅
- Можно переходить к Итерации 3 (Navigation Index & Taxonomy)
- Задача 012 (Integration Tests) готова к запуску
