# Задача 001: LLM Gateway - Queue и Batch Executor

## Что нужно сделать

Реализовать компоненты LLM Gateway для централизованного доступа к LLM:
1. Интерфейс LLMGateway с методами request() и batch()
2. Интеграцию с Langchain клиентами для каждого провайдера
3. Батчинг запросов через Langchain .batch() методы
4. MockLLMGateway для тестирования

## Зачем

LLM Gateway - фундамент всей системы. Все агенты будут обращаться к LLM через этот Gateway. Батчинг через Langchain необходим для:
- Эффективного использования API лимитов
- Контроля расходов на LLM
- Предотвращения rate limit ошибок при параллельной работе агентов

## Acceptance Criteria

- [ ] AC-001: Реализован интерфейс LLMGateway с методами request() и batch()
- [ ] AC-002: Интеграция с Langchain (ChatAnthropic, ChatOpenAI, etc.)
- [ ] AC-003: Батчинг запросов через Langchain .batch()
- [ ] AC-004: Retry с экспоненциальным backoff при ошибках
- [ ] AC-005: MockLLMGateway для тестирования (детерминированные ответы)
- [ ] AC-006: Unit тесты для batching логики
- [ ] AC-007: Логи batching операций в 04_logs/gateway/

## Контекст

**Implementation Plan:**
- `00_docs/architecture/implementation_plan.md` - Iteration 1, модуль LLM Gateway

**Архитектура:**
- `00_docs/architecture/overview.md` - раздел 7 "LLM Gateway"

**Интерфейсы и контракты:**

```python
from typing import List, Dict, Any, Optional
from enum import Enum

class ModelProvider(str, Enum):
    CLAUDE_HAIKU = "claude-haiku"
    CLAUDE_SONNET = "claude-sonnet"
    CLAUDE_OPUS = "claude-opus"
    GPT_4O_MINI = "gpt-4o-mini"
    LOCAL_LLAMA = "local-llama"

class RequestPriority(int, Enum):
    HIGH = 1   # запросы от пользователя (runtime)
    NORMAL = 2 # Eager-генерация снэпшотов
    LOW = 3    # фоновая переиндексация

class LLMMessage:
    role: str
    content: str

class LLMTool:
    name: str
    description: str
    input_schema: Dict[str, Any]

class LLMRequest:
    model: ModelProvider
    messages: List[LLMMessage]
    tools: Optional[List[LLMTool]] = None
    request_id: str
    priority: RequestPriority = RequestPriority.NORMAL
    temperature: float = 0.0
    max_tokens: Optional[int] = None

class LLMResponse:
    request_id: str
    content: str
    tool_calls: Optional[List[Dict[str, Any]]] = None
    model: str
    tokens_used: Optional[Dict[str, int]] = None

class LLMGateway:
    """Централизованный доступ к LLM"""

    def __init__(self, config: Dict[str, Any]):
        """Инициализация с конфигурацией (API keys и т.д.)"""
        pass

    async def request(self, request: LLMRequest) -> LLMResponse:
        """Отправить запрос в LLM"""
        pass

    async def batch(self, requests: List[LLMRequest]) -> List[LLMResponse]:
        """Отправить батч запросов через Langchain"""
        pass

    async def shutdown(self):
        """Graceful shutdown"""
        pass

    def get_stats(self) -> Dict[str, Any]:
        """Статистика для мониторинга"""
        pass
```

**Архитектурный подход:**

```python
"""
Архитектурное решение: Использовать Langchain клиенты

- Каждый провайдер: свой Langchain клиент
  * Claude: ChatAnthropic
  * OpenAI: ChatOpenAI
  * Local: ChatOllama или аналоги

- Батчинг: langchain .batch() методы
  * Принимает массив запросов
  * Управляет rate limits под капотом

- Retry: собственная обёртка
  * Exponential backoff
  * Максимальное количество попыток

- Конфигурация: минимальная
  * API keys (из env переменных)
  * Timeouts (определяются при реализации)
  * Retry policy (определяется при реализации)
"""
```

**Структура проекта:**

```
02_src/
├── llm_gateway/
│   ├── __init__.py
│   ├── gateway.py          # LLMGateway
│   ├── clients.py          # Langchain клиенты
│   ├── retry.py            # Retry логика
│   ├── models.py           # Data classes
│   └── mock_gateway.py     # MockLLMGateway для тестов
├── tests/
│   ├── test_gateway.py
│   └── fixtures/
│       └── mock_responses.json
04_logs/
└── gateway/
    └── (логи batching операций)
```

**Существующий код для reference:**
- Отсутствует (первая задача)

**Другие ссылки:**
- https://python.langchain.com/docs/integrations/providers/anthropic/ - Langchain + Claude
- https://python.langchain.com/docs/integrations/providers/openai/ - Langchain + OpenAI
- https://python.langchain.com/docs/expression_language/batch/ - Batch execution

## Примечания для Analyst

**Важно:** Конкретные параметры конфигурации (timeouts, retry counts и т.д.) определяются на этапе создания технического задания. Не следует их указывать в task_brief.

**Ключевые решения для проработки:**
1. Какой механизм накопления батчей? (по количеству запросов или по timeout)
2. Какой retry стратегия использовать?
3. Как логировать batching операции?

## Зависимости

Эта задача не зависит от других задач (может начинаться сразу).

## Следующие задачи

После завершения этой задачи:
- Задача 002: LLM Gateway: Response Router и Retry
- Задача 003: LLM Gateway: Rate Limit Control
