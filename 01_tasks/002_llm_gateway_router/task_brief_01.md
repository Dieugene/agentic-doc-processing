# Задача 002: LLM Gateway - Response Router и Retry

## Что нужно сделать

Реализовать Response Router для раздачи результатов агентам и механизм retry с экспоненциальным backoff при ошибках API.

## Зачем

Response Router обеспечивает корректную доставку результатов запросов агентам. Retry с backoff повышает надёжность при временных сбоях API и превышении rate limits.

## Acceptance Criteria

- [ ] AC-001: ResponseRouter раздаёт результаты из futures
- [ ] AC-002: RetryPolicy с экспоненциальным backoff
- [ ] AC-003: Обработка ошибок 429 (rate limit) и 5xx
- [ ] AC-004: Интеграция retry в BatchExecutor
- [ ] AC-005: Unit тесты сценариев retry
- [ ] AC-006: Логи retry попыток

## Контекст

**Зависимость от задачи 001:**

Эта задача расширяет BatchExecutor из задачи 001:
- Добавляет ResponseRouter
- Интегрирует retry в execute_batch()
- Обрабатывает ошибки API

**Интерфейсы и контракты:**

```python
from typing import Optional, List
from datetime import datetime, timedelta
import asyncio
import random

# ============================================
# Retry Policy
# ============================================

@dataclass
class RetryPolicy:
    """
    Политика повторных попыток при ошибках API.

    Стратегия: экспоненциальный backoff с jitter.
    """
    max_retries: int = 3
    initial_delay_ms: int = 1000
    backoff_multiplier: float = 2.0
    jitter_ms: int = 500  # случайное разброс

    def get_delay(self, attempt: int) -> float:
        """
        Вычислить задержку для попытки.

        Args:
            attempt: Номер попытки (0-indexed)

        Returns:
            Задержка в секундах
        """
        # Экспоненциальный backoff
        base_delay = self.initial_delay_ms * (self.backoff_multiplier ** attempt)

        # Добавляем jitter для избежания thundering herd
        jitter = random.uniform(-self.jitter_ms, self.jitter_ms)

        return (base_delay + jitter) / 1000

    def should_retry(self, error: Exception, attempt: int) -> bool:
        """
        Определить, нужно ли повторять попытку.

        Retry при:
        - 429 (rate limit)
        - 5xx (server errors)
        - Временные сетевые ошибки

        Не retry при:
        - 4xx (client errors, кроме 429)
        - Ошибки валидации
        """
        from httpx import HTTPStatusError

        if isinstance(error, HTTPStatusError):
            status = error.response.status_code

            # Rate limit
            if status == 429:
                return True

            # Server errors
            if 500 <= status < 600:
                return True

            # Client errors — не retry
            if 400 <= status < 500:
                return False

        # Сетевые ошибки
        if isinstance(error, (ConnectionError, TimeoutError)):
            return True

        return False

# ============================================
# Response Router
# ============================================

class ResponseRouter:
    """
    Раздаёт результаты запросов агентам.

    Отслеживает запросы и обеспечивает доставку ответов.
    """

    def __init__(self, log_dir: Optional[str] = None):
        self.log_dir = log_dir
        self._pending_requests: Dict[str, LLMRequest] = {}
        self._pending_futures: Dict[str, asyncio.Future] = {}

    def register(self, request: LLMRequest, future: asyncio.Future):
        """
        Зарегистрировать ожидающий запрос.

        Args:
            request: LLMRequest
            future: Future для результата
        """
        self._pending_requests[request.request_id] = request
        self._pending_futures[request.request_id] = future

    def resolve(self, response: LLMResponse):
        """
        Разрешить запрос с ответом.

        Args:
            response: LLMResponse с request_id
        """
        future = self._pending_futures.get(response.request_id)
        if not future:
            print(f"Warning: No future for request_id {response.request_id}")
            return

        future.set_result(response)
        self._unregister(response.request_id)

        self._log_response(response)

    def resolve_error(self, request_id: str, error: Exception):
        """
        Разрешить запрос с ошибкой.

        Args:
            request_id: ID запроса
            error: Исключение
        """
        future = self._pending_futures.get(request_id)
        if not future:
            print(f"Warning: No future for request_id {request_id}")
            return

        future.set_exception(error)
        self._unregister(request_id)

        self._log_error(request_id, error)

    def _unregister(self, request_id: str):
        """Удалить запрос из регистра"""
        self._pending_requests.pop(request_id, None)
        self._pending_futures.pop(request_id, None)

    def _log_response(self, response: LLMResponse):
        """Логировать успешный ответ"""
        if not self.log_dir:
            return

        import json
        from pathlib import Path

        log_path = Path(self.log_dir) / "gateway" / "responses.jsonl"
        log_path.parent.mkdir(parents=True, exist_ok=True)

        request = self._pending_requests.get(response.request_id)

        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "request_id": response.request_id,
            "agent_id": request.agent_id if request else None,
            "latency_ms": response.latency_ms,
            "status": "success"
        }

        with open(log_path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + '\n')

    def _log_error(self, request_id: str, error: Exception):
        """Логировать ошибку"""
        if not self.log_dir:
            return

        import json
        from pathlib import Path

        log_path = Path(self.log_dir) / "gateway" / "errors.jsonl"
        log_path.parent.mkdir(parents=True, exist_ok=True)

        request = self._pending_requests.get(request_id)

        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "request_id": request_id,
            "agent_id": request.agent_id if request else None,
            "error": str(error),
            "status": "error"
        }

        with open(log_path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + '\n')

# ============================================
# Обновлённый BatchExecutor с retry
# ============================================

class BatchExecutorWithRetry(BatchExecutor):
    """
    BatchExecutor с механизмом retry.

    Расширяет BatchExecutor из задачи 001.
    """

    def __init__(self, model_config: ModelConfig, retry_policy: RetryPolicy, log_dir: Optional[str] = None):
        super().__init__(model_config, log_dir)
        self.retry_policy = retry_policy

    async def execute_batch(
        self,
        batch: List[tuple[LLMRequest, 'asyncio.Future[LLMResponse]']]
    ) -> None:
        """
        Отправить батч запросов с retry.

        При ошибке:
        1. Проверить should_retry()
        2. Подождать get_delay()
        3. Повторить попытку
        4. После max_retries — завершить futures с ошибкой
        """
        if not batch:
            return

        for attempt in range(self.retry_policy.max_retries + 1):
            try:
                # Первая попытка или retry
                await super().execute_batch(batch)
                return  # Успех

            except Exception as e:
                # Проверяем, нужно ли retry
                if attempt < self.retry_policy.max_retries and self.retry_policy.should_retry(e, attempt):
                    # Логируем retry
                    self._log_retry(batch, attempt, e)

                    # Ждём с backoff
                    delay = self.retry_policy.get_delay(attempt)
                    await asyncio.sleep(delay)

                    # Следующая попытка
                    continue
                else:
                    # Не retry или последняя попытка неудачна
                    for _, future in batch:
                        if not future.done():
                            future.set_exception(e)

                    self._log_error(batch, e)
                    return

    def _log_retry(self, batch: List[tuple], attempt: int, error: Exception):
        """Логировать retry попытку"""
        if not self.log_dir:
            return

        import json
        from pathlib import Path

        log_path = Path(self.log_dir) / "gateway" / "retries.jsonl"
        log_path.parent.mkdir(parents=True, exist_ok=True)

        request_ids = [req.request_id for req, _ in batch]

        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "model": self.config.model_name,
            "attempt": attempt,
            "request_ids": request_ids,
            "error": str(error),
            "delay_ms": self.retry_policy.get_delay(attempt) * 1000,
            "status": "retry"
        }

        with open(log_path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + '\n')

# ============================================
# Обновлённый LLMGateway
# ============================================

class LLMGatewayWithRetry(LLMGateway):
    """
    LLMGateway с retry и ResponseRouter.
    """

    def __init__(
        self,
        configs: Dict[str, ModelConfig],
        retry_policy: RetryPolicy,
        log_dir: Optional[str] = None
    ):
        super().__init__(configs, log_dir)
        self.retry_policy = retry_policy
        self.router = ResponseRouter(log_dir)

        # Заменяем исполнители на версии с retry
        self._executors = {}
        for model_id, config in configs.items():
            self._executors[model_id] = BatchExecutorWithRetry(config, retry_policy, log_dir)
```

**Структура проекта:**

```
02_src/
├── gateway/
│   ├── __init__.py
│   ├── llm_gateway.py        # LLMGatewayWithRetry
│   ├── models.py              # LLMRequest, LLMResponse, ModelConfig
│   ├── batch_executor.py      # BatchExecutor, BatchExecutorWithRetry
│   ├── response_router.py     # ResponseRouter
│   ├── retry_policy.py        # RetryPolicy
│   └── tests/
│       ├── test_response_router.py
│       ├── test_retry_policy.py
│       ├── test_batch_executor_retry.py
│       └── fixtures/
│           └── error_scenarios.json
04_logs/
└── gateway/
    ├── responses.jsonl
    ├── retries.jsonl
    └── errors.jsonl
```

## Примечания для Analyst

**Ключевые решения:**
1. Какой max_retries использовать? (3 для баланса)
2. Какой initial_delay? (1000ms = 1 секунда)
3. Нужно ли добавлять jitter? (да, для избежания thundering herd)
4. Какие ошибки retry? (429, 5xx, сетевые)

**Важно:**
- Jitter критически важен при параллельных retry — избегаем синхронизации
- 429 (rate limit) всегда retry
- 4xx client errors (кроме 429) не retry — это ошибки приложения
- ResponseRouter отслеживает все pending запросы

**Тестовые сценарии:**
1. Успешный запрос — без retry
2. Временная ошибка 5xx — retry успешен
3. Rate limit 429 — retry успешен
4. Client error 400 — не retry
5. После max_retries — ошибка пробрасывается

## Зависимости

- Задача 001: LLM Gateway Queue и BatchExecutor

## Следующие задачи

После завершения:
- Задача 003: LLM Gateway Rate Limit Control
- Задача 005: Unit тесты LLM Gateway
