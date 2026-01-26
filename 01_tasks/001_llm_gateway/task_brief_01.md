# Задача 001: LLM Gateway - Queue и Batch Executor

## Что нужно сделать

Реализовать базовые компоненты LLM Gateway: очередь запросов и батч-исполнитель для централизованного доступа к LLM моделям.

## Зачем

LLM Gateway обеспечивает централизованный доступ к LLM для всех агентов системы с батчингом для оптимизации API вызовов и контроля rate limits.

## Acceptance Criteria

- [ ] AC-001: RequestQueue реализован для каждой модели
- [ ] AC-002: BatchExecutor накапливает запросы и отправляет батчами
- [ ] AC-003: LLMGateway.request() возвращает Future/Promise
- [ ] AC-004: LLMGateway.batch() для групповой отправки
- [ ] AC-005: MockLLMGateway для тестов
- [ ] AC-006: Unit тесты для всех методов
- [ ] AC-007: Логи в 04_logs/gateway/

## Контекст

**ADR-000: LLM Gateway архитектура**

LLM Gateway — централизованный модуль доступа к LLM с оптимизацией через батчинг. Все агенты системы обращаются к LLM через Gateway, а не напрямую.

**Интерфейсы и контракты:**

```python
from typing import List, Dict, Any, Optional
from enum import Enum
from dataclasses import dataclass
import asyncio
from datetime import datetime, timedelta

# ============================================
# Модели и провайдеры
# ============================================

class ModelProvider(str, Enum):
    """Поддерживаемые провайдеры LLM"""
    CLAUDE_HAIKU = "claude-haiku"
    CLAUDE_SONNET = "claude-sonnet"
    CLAUDE_OPUS = "claude-opus"
    GPT_4O_MINI = "gpt-4o-mini"
    GPT_4O = "gpt-4o"
    LOCAL_LLAMA = "local-llama"

@dataclass
class ModelConfig:
    """Конфигурация модели"""
    provider: ModelProvider
    endpoint: str
    api_key: str
    model_name: str

    # Rate limits (для информации, реальный контроль через retry)
    max_requests_per_minute: Optional[int] = None
    max_tokens_per_minute: Optional[int] = None

    # Batching конфигурация
    batch_size: int = 10
    batch_timeout_ms: int = 100

# ============================================
# Структуры запросов и ответов
# ============================================

@dataclass
class LLMMessage:
    """Сообщение в формате chat API"""
    role: str  # "system" | "user" | "assistant"
    content: str

@dataclass
class LLMTool:
    """Описание tool (для function calling)"""
    name: str
    description: str
    parameters: Dict[str, Any]

@dataclass
class LLMRequest:
    """Запрос к LLM"""
    request_id: str  # для трейсинга
    model: str  # идентификатор модели из ModelConfig
    messages: List[LLMMessage]
    tools: Optional[List[LLMTool]] = None
    temperature: float = 0.0

    # Метаданные для трейсинга
    agent_id: Optional[str] = None
    trace_id: Optional[str] = None

@dataclass
class LLMResponse:
    """Ответ от LLM"""
    request_id: str
    content: str
    tool_calls: Optional[List[Dict[str, Any]]] = None
    usage: Optional[Dict[str, int]] = None  # tokens in/out
    latency_ms: int = 0

# ============================================
# Request Queue
# ============================================

class RequestQueue:
    """
    Очередь запросов для конкретной модели.

    Каждая модель имеет свою очередь для независимого батчинга.
    """

    def __init__(self, model: str, batch_size: int, batch_timeout_ms: int):
        self.model = model
        self.batch_size = batch_size
        self.batch_timeout_ms = batch_timeout_ms
        self._queue: asyncio.Queue = asyncio.Queue()
        self._pending_batches: List[Future] = []

    async def put(self, request: LLMRequest) -> 'asyncio.Future[LLMResponse]':
        """
        Добавить запрос в очередь.

        Returns:
            Future для получения результата
        """
        future = asyncio.Future()
        await self._queue.put((request, future))
        return future

    async def get_batch(self) -> List[tuple[LLMRequest, 'asyncio.Future[LLMResponse]']]:
        """
        Получить батч запросов для обработки.

        Накапливает запросы до достижения batch_size или batch_timeout.
        """
        requests = []
        deadline = datetime.now() + timedelta(milliseconds=self.batch_timeout_ms)

        # Накапливаем первый запрос (блокируемся если очередь пуста)
        first = await self._queue.get()
        requests.append(first)

        # Накапливаем остальные с таймаутом
        while len(requests) < self.batch_size:
            try:
                timeout = (deadline - datetime.now()).total_seconds()
                if timeout <= 0:
                    break

                req = await asyncio.wait_for(self._queue.get(), timeout=timeout)
                requests.append(req)
            except asyncio.TimeoutError:
                break

        return requests

# ============================================
# Batch Executor
# ============================================

class BatchExecutor:
    """
    Исполнитель батчей запросов.

    Получает батчи из RequestQueue и отправляет в API.
    """

    def __init__(self, model_config: ModelConfig, log_dir: Optional[str] = None):
        self.config = model_config
        self.log_dir = log_dir
        self._client = self._create_client()
        self._active_batches = 0

    def _create_client(self):
        """
        Создать Langchain клиент для модели.

        Использует langchain для унифицированного доступа.
        """
        # Import здесь для избежания circular deps
        from langchain_anthropic import ChatAnthropic
        from langchain_openai import ChatOpenAI

        provider = self.config.provider

        if provider == ModelProvider.CLAUDE_HAIKU:
            return ChatAnthropic(
                model=self.config.model_name,
                api_key=self.config.api_key,
                temperature=0.0
            )
        elif provider in [ModelProvider.GPT_4O_MINI, ModelProvider.GPT_4O]:
            return ChatOpenAI(
                model=self.config.model_name,
                api_key=self.config.api_key,
                temperature=0.0
            )
        else:
            raise ValueError(f"Unsupported provider: {provider}")

    async def execute_batch(
        self,
        batch: List[tuple[LLMRequest, 'asyncio.Future[LLMResponse]']]
    ) -> None:
        """
        Отправить батч запросов в API.

        Args:
            batch: Список (request, future) пар

        Обрабатывает:
        - Конвертацию LLMRequest → langchain format
        - Отправку через langchain .batch()
        - Раздачу результатов в futures
        - Логирование
        """
        if not batch:
            return

        requests = [req for req, _ in batch]
        futures = [fut for _, fut in batch]

        start_time = datetime.now()

        try:
            # Конвертируем в langchain format
            lc_messages = [
                [(msg.role, msg.content) for msg in req.messages]
                for req in requests
            ]

            # Отправляем батч через langchain
            responses = await self._client.abatch(lc_messages)

            # Раздаём результаты
            for req, fut, resp in zip(requests, futures, responses):
                llm_resp = LLMResponse(
                    request_id=req.request_id,
                    content=resp.content,
                    usage=getattr(resp, 'usage_metadata', None),
                    latency_ms=int((datetime.now() - start_time).total_seconds() * 1000)
                )
                fut.set_result(llm_resp)

            # Логируем
            self._log_batch(requests, responses, start_time)

        except Exception as e:
            # При ошибке — все futures завершаются с исключением
            for fut in futures:
                fut.set_exception(e)

            self._log_error(requests, e)

    def _log_batch(self, requests: List[LLMRequest], responses: List, start_time: datetime):
        """Логировать успешный батч"""
        if not self.log_dir:
            return

        import json
        from pathlib import Path

        log_path = Path(self.log_dir) / "gateway" / "batches.jsonl"
        log_path.parent.mkdir(parents=True, exist_ok=True)

        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "model": self.config.model_name,
            "batch_size": len(requests),
            "request_ids": [r.request_id for r in requests],
            "latency_ms": int((datetime.now() - start_time).total_seconds() * 1000),
            "status": "success"
        }

        with open(log_path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + '\n')

    def _log_error(self, requests: List[LLMRequest], error: Exception):
        """Логировать ошибку батча"""
        if not self.log_dir:
            return

        import json
        from pathlib import Path

        log_path = Path(self.log_dir) / "gateway" / "errors.jsonl"
        log_path.parent.mkdir(parents=True, exist_ok=True)

        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "model": self.config.model_name,
            "request_ids": [r.request_id for r in requests],
            "error": str(error),
            "status": "error"
        }

        with open(log_path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + '\n')

# ============================================
# LLM Gateway
# ============================================

class LLMGateway:
    """
    Централизованный доступ к LLM через Langchain.

    Архитектура:
    1. request() добавляет запрос в очередь модели
    2. BatchExecutor забирает батчи и отправляет
    3. Response Router раздаёт результаты
    """

    def __init__(self, configs: Dict[str, ModelConfig], log_dir: Optional[str] = None):
        """
        Args:
            configs: Словарь {model_id: ModelConfig}
            log_dir: Директория для логов
        """
        self.log_dir = log_dir
        self.configs = configs

        # Создаём очереди и исполнители для каждой модели
        self._queues: Dict[str, RequestQueue] = {}
        self._executors: Dict[str, BatchExecutor] = {}

        for model_id, config in configs.items():
            self._queues[model_id] = RequestQueue(
                model=model_id,
                batch_size=config.batch_size,
                batch_timeout_ms=config.batch_timeout_ms
            )
            self._executors[model_id] = BatchExecutor(config, log_dir)

        # Фоновые задачи для обработки очередей
        self._worker_tasks: List[asyncio.Task] = []

    async def start(self):
        """Запустить фоновые обработчики очередей"""
        for model_id, queue in self._queues.items():
            executor = self._executors[model_id]
            task = asyncio.create_task(self._process_queue(model_id, queue, executor))
            self._worker_tasks.append(task)

    async def stop(self):
        """Остановить обработчики очередей"""
        for task in self._worker_tasks:
            task.cancel()
        await asyncio.gather(*self._worker_tasks, return_exceptions=True)

    async def _process_queue(
        self,
        model_id: str,
        queue: RequestQueue,
        executor: BatchExecutor
    ):
        """Фоновая задача обработки очереди"""
        while True:
            try:
                batch = await queue.get_batch()
                await executor.execute_batch(batch)
            except asyncio.CancelledError:
                break
            except Exception as e:
                # Логируем и продолжаем
                print(f"Error processing queue {model_id}: {e}")

    async def request(self, request: LLMRequest) -> LLMResponse:
        """
        Отправить запрос к LLM.

        Args:
            request: LLMRequest

        Returns:
            LLMResponse

        Метод возвращает Future — можно ждать результат или продолжать работу.
        """
        queue = self._queues.get(request.model)
        if not queue:
            raise ValueError(f"Unknown model: {request.model}")

        future = await queue.put(request)
        return await future

    async def batch(self, requests: List[LLMRequest]) -> List[LLMResponse]:
        """
        Отправить батч запросов.

        Args:
            requests: Список LLMRequest

        Returns:
            Список LLMResponse
        """
        # Группируем по моделям
        by_model: Dict[str, List[LLMRequest]] = {}
        for req in requests:
            by_model.setdefault(req.model, []).append(req)

        # Отправляем каждой модели
        results = []
        for model_id, model_requests in by_model.items():
            model_results = await asyncio.gather(*[
                self.request(req) for req in model_requests
            ])
            results.extend(model_results)

        return results
```

**Структура проекта:**

```
02_src/
├── gateway/
│   ├── __init__.py
│   ├── llm_gateway.py        # LLMGateway, RequestQueue, BatchExecutor
│   ├── models.py              # LLMRequest, LLMResponse, ModelConfig
│   └── tests/
│       ├── test_llm_gateway.py
│       ├── mock_gateway.py    # MockLLMGateway
│       └── fixtures/
│           └── sample_responses.json
04_logs/
└── gateway/
    ├── batches.jsonl
    └── errors.jsonl
```

## Примечания для Analyst

**Ключевые решения:**
1. Какой batch_size использовать по умолчанию? (10 для баланса latency/throughput)
2. Какой batch_timeout? (100ms для быстрого отклика)
3. Как логировать запросы? (JSON Lines для парсинга)
4. Нужно ли сохранять промпты в логах? (для v1.0 — только метадата)

**Важно:**
- Langchain предоставляет метод .batch() для групповой отправки
- futures позволяют асинхронную обработку — агент может продолжать работу
- Каждая модель имеет независимую очередь
- Логи содержат только метадату, не содержимое промптов (для безопасности)

**Библиотеки:**
- `langchain>=0.1.0`
- `langchain-anthropic` или `langchain-openai` (в зависимости от провайдера)

## Зависимости

Нет зависимостей от других задач (первая задача).

## Следующие задачи

После завершения:
- Задача 002: LLM Gateway Response Router и Retry (использует BatchExecutor)
- Задача 003: LLM Gateway Rate Limit Control
