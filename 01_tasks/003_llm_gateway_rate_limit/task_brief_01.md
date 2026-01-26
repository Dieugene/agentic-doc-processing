# Задача 003: LLM Gateway - Rate Limit Control

## Что нужно сделать

Реализовать контроль rate limits (RPM/TPM) для предотвращения превышения лимитов API провайдеров.

## Зачем

Rate Limit Control предотвращает блокировку API ключей при превышении лимитов запросов в минуту/токенов в минуту. Работает в связке с retry механизмом.

## Acceptance Criteria

- [ ] AC-001: RateLimiter отслеживает RPM/TPM для каждой модели
- [ ] AC-002: Подсчёт токенов для запросов/ответов
- [ ] AC-003: Блокировка запросов при превышении лимита
- [ ] AC-004: Интеграция в BatchExecutor (предварительная проверка)
- [ ] AC-005: Unit тесты сценариев rate limiting
- [ ] AC-006: Ли трейсинг rate limits

## Контекст

**Зависимость от задач 001-002:**

Эта задача добавляет RateLimiter, который интегрируется в BatchExecutor для предварительной проверки перед отправкой батча.

**Интерфейсы и контракты:**

```python
from typing import Dict, Optional
from datetime import datetime, timedelta
from collections import deque
import asyncio

# ============================================
# Token Counter
# ============================================

class TokenCounter:
    """
    Подсчёт токенов для запросов и ответов.

    Использует tiktoken для OpenAI и примерную оценку для Anthropic.
    """

    def __init__(self):
        # Загружаем tiktoken при необходимости
        try:
            import tiktoken
            self._encoder = tiktoken.get_encoding("cl100k_base")
        except ImportError:
            self._encoder = None

    def count_tokens(self, text: str, model: str) -> int:
        """
        Подсчитать токены в тексте.

        Args:
            text: Текст для подсчёта
            model: Модель (для выбора кодировки)

        Returns:
            Примерное количество токенов
        """
        if self._encoder:
            # Точный подсчёт для OpenAI-совместимых моделей
            return len(self._encoder.encode(text))
        else:
            # Приближённая оценка: 1 токен ≈ 4 символа
            return len(text) // 4

    def count_request_tokens(self, request: LLMRequest) -> int:
        """
        Подсчитать токены в запросе.

        Учитывает:
        - Системный промпт
        - Сообщения
        - Tool descriptions
        """
        total = 0

        for msg in request.messages:
            total += self.count_tokens(msg.content, request.model)

        if request.tools:
            for tool in request.tools:
                total += self.count_tokens(tool.description, request.model)
                # Добавляем параметры
                total += self.count_tokens(str(tool.parameters), request.model)

        return total

    def estimate_response_tokens(self) -> int:
        """
        Оценить токены в ответе.

        Для rate limiting используем консервативную оценку,
        так как реальное количество неизвестно до ответа.
        """
        return 1000  # Консервативная оценка

# ============================================
# Rate Limit Tracker
# ============================================

class RateLimitTracker:
    """
    Отслеживание использования rate limits.

    Хранит историю запросов для скользящего окна.
    """

    def __init__(self, window_seconds: int = 60):
        """
        Args:
            window_seconds: Окно наблюдения (обычно 60 секунд)
        """
        self.window_seconds = window_seconds
        self._requests: deque = deque()  # (timestamp, tokens)
        self._lock = asyncio.Lock()

    async def add_request(self, tokens: int):
        """
        Добавить запрос в историю.

        Args:
            tokens: Количество токенов (вход + выход)
        """
        async with self._lock:
            now = datetime.now()
            self._requests.append((now, tokens))

            # Удаляем старые записи за пределами окна
            cutoff = now - timedelta(seconds=self.window_seconds)
            while self._requests and self._requests[0][0] < cutoff:
                self._requests.popleft()

    async def get_usage(self) -> tuple[int, int]:
        """
        Получить текущее использование.

        Returns:
            (requests_count, tokens_count)
        """
        async with self._lock:
            # Очищаем старые
            now = datetime.now()
            cutoff = now - timedelta(seconds=self.window_seconds)

            while self._requests and self._requests[0][0] < cutoff:
                self._requests.popleft()

            requests_count = len(self._requests)
            tokens_count = sum(tokens for _, tokens in self._requests)

            return requests_count, tokens_count

    async def can_make_request(self, max_rpm: int, max_tpm: int) -> tuple[bool, str]:
        """
        Проверить, можно ли сделать запрос.

        Args:
            max_rpm: Макс. запросов в минуту
            max_tpm: Макс. токенов в минуту

        Returns:
            (can_proceed, reason)
        """
        requests_count, tokens_count = await self.get_usage()

        # Проверяем RPM
        if max_rpm and requests_count >= max_rpm:
            return False, f"Rate limit exceeded: {requests_count} requests / {max_rpm} RPM"

        # Проверяем TPM
        if max_tpm and tokens_count >= max_tpm:
            return False, f"Token limit exceeded: {tokens_count} tokens / {max_tpm} TPM"

        return True, ""

    async def wait_until_available(self, max_rpm: int, max_tpm: int) -> float:
        """
        Вычислить задержку до доступности слота.

        Returns:
            Задержка в секундах (0 если доступно сейчас)
        """
        async with self._lock:
            now = datetime.now()

            # Очищаем старые
            cutoff = now - timedelta(seconds=self.window_seconds)
            while self._requests and self._requests[0][0] < cutoff:
                self._requests.popleft()

            # Проверяем RPM
            if max_rpm and len(self._requests) >= max_rpm:
                # Самый старый запрос будет доступен через...
                oldest_time = self._requests[0][0]
                available_at = oldest_time + timedelta(seconds=self.window_seconds)
                return (available_at - now).total_seconds()

            # Проверяем TPM
            if max_tpm:
                tokens_count = sum(tokens for _, tokens in self._requests)
                if tokens_count >= max_tpm:
                    # Удаляем самые старые пока не освободим место
                    temp_tokens = tokens_count
                    temp_queue = deque(self._requests)

                    while temp_tokens >= max_tpm and temp_queue:
                        oldest_time, old_tokens = temp_queue.popleft()
                        temp_tokens -= old_tokens

                    if temp_queue:
                        available_at = temp_queue[0][0] + timedelta(seconds=self.window_seconds)
                        return (available_at - now).total_seconds()

            return 0.0

# ============================================
# Rate Limiter
# ============================================

class RateLimiter:
    """
    Контроль rate limits для всех моделей.

    Создаёт трекер для каждой модели на основе конфигурации.
    """

    def __init__(self, configs: Dict[str, ModelConfig], log_dir: Optional[str] = None):
        """
        Args:
            configs: Словарь {model_id: ModelConfig} с max_rpm/max_tpm
            log_dir: Директория для логов
        """
        self.log_dir = log_dir
        self.configs = configs
        self.token_counter = TokenCounter()

        # Создаём трекеры для каждой модели
        self._trackers: Dict[str, RateLimitTracker] = {}
        for model_id, config in configs.items():
            self._trackers[model_id] = RateLimitTracker()

    async def check_request(self, request: LLMRequest) -> tuple[bool, str, float]:
        """
        Проверить, можно ли отправить запрос.

        Args:
            request: LLMRequest

        Returns:
            (can_proceed, reason, wait_seconds)
        """
        tracker = self._trackers.get(request.model)
        config = self.configs.get(request.model)

        if not tracker or not config:
            return True, "", 0.0

        # Проверяем rate limits
        can_proceed, reason = await tracker.can_make_request(
            max_rpm=config.max_requests_per_minute or 0,
            max_tpm=config.max_tokens_per_minute or 0
        )

        if not can_proceed:
            # Вычисляем время ожидания
            wait_seconds = await tracker.wait_until_available(
                max_rpm=config.max_requests_per_minute or 0,
                max_tpm=config.max_tokens_per_minute or 0
            )
            return False, reason, wait_seconds

        return True, "", 0.0

    async def register_request(self, request: LLMRequest, response: LLMResponse):
        """
        Зарегистрировать выполненный запрос в статистике.

        Args:
            request: LLMRequest
            response: LLMResponse с usage
        """
        tracker = self._trackers.get(request.model)
        if not tracker:
            return

        # Считаем токены
        input_tokens = self.token_counter.count_request_tokens(request)

        # Из ответа берём точные данные если есть
        if response.usage:
            output_tokens = response.usage.get('output_tokens', response.usage.get('completion_tokens', 0))
            total_tokens = response.usage.get('total_tokens', input_tokens + output_tokens)
        else:
            # Оценка
            output_tokens = self.token_counter.estimate_response_tokens()
            total_tokens = input_tokens + output_tokens

        await tracker.add_request(total_tokens)

        self._log_usage(request, input_tokens, output_tokens)

    def _log_usage(self, request: LLMRequest, input_tokens: int, output_tokens: int):
        """Логировать использование токенов"""
        if not self.log_dir:
            return

        import json
        from pathlib import Path

        log_path = Path(self.log_dir) / "gateway" / "rate_limits.jsonl"
        log_path.parent.mkdir(parents=True, exist_ok=True)

        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "model": request.model,
            "agent_id": request.agent_id,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
            "status": "success"
        }

        with open(log_path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + '\n')

# ============================================
# Интеграция в BatchExecutor
# ============================================

class BatchExecutorWithRateLimit(BatchExecutorWithRetry):
    """
    BatchExecutor с проверкой rate limits.

    Перед отправкой батча проверяет rate limits.
    """

    def __init__(self, model_config: ModelConfig, retry_policy: RetryPolicy, rate_limiter: RateLimiter, log_dir: Optional[str] = None):
        super().__init__(model_config, retry_policy, log_dir)
        self.rate_limiter = rate_limiter

    async def execute_batch(
        self,
        batch: List[tuple[LLMRequest, 'asyncio.Future[LLMResponse]']]
    ) -> None:
        """
        Отправить батч с проверкой rate limits.

        1. Проверить rate limits для каждого запроса
        2. Если превышен — ждать или вернуть ошибку
        3. Отправить батч
        4. Зарегистрировать использование
        """
        if not batch:
            return

        # Проверяем rate limits
        for request, _ in batch:
            can_proceed, reason, wait_seconds = await self.rate_limiter.check_request(request)

            if not can_proceed:
                # Логируем и ждём
                self._log_rate_limit(request, reason, wait_seconds)

                if wait_seconds > 0:
                    await asyncio.sleep(wait_seconds)
                else:
                    # Не можем отправить — возвращаем ошибку
                    for _, future in batch:
                        if not future.done():
                            future.set_exception(Exception(f"Rate limit exceeded: {reason}"))
                    return

        # Отправляем батч
        await super().execute_batch(batch)

        # Регистрируем использование (после получения ответов)
        # Это делается в execute_batch после получения ответов
        # Для упрощения — здесь пропускаем, реальная регистрация в response router

    def _log_rate_limit(self, request: LLMRequest, reason: str, wait_seconds: float):
        """Логировать превышение rate limit"""
        if not self.log_dir:
            return

        import json
        from pathlib import Path

        log_path = Path(self.log_dir) / "gateway" / "rate_limits.jsonl"
        log_path.parent.mkdir(parents=True, exist_ok=True)

        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "model": request.model,
            "request_id": request.request_id,
            "agent_id": request.agent_id,
            "reason": reason,
            "wait_seconds": wait_seconds,
            "status": "rate_limited"
        }

        with open(log_path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + '\n')
```

**Структура проекта:**

```
02_src/
├── gateway/
│   ├── __init__.py
│   ├── llm_gateway.py            # LLMGateway с rate limiting
│   ├── models.py
│   ├── batch_executor.py
│   ├── response_router.py
│   ├── retry_policy.py
│   ├── rate_limiter.py           # RateLimiter, RateLimitTracker
│   ├── token_counter.py          # TokenCounter
│   └── tests/
│       ├── test_rate_limiter.py
│       ├── test_token_counter.py
│       └── fixtures/
│           └── rate_limit_scenarios.json
04_logs/
└── gateway/
    ├── rate_limits.jsonl
    └── ...
```

## Примечания для Analyst

**Ключевые решения:**
1. Какое окно наблюдения использовать? (60 секунд = 1 минута)
2. Как считать токены для Anthropic? (приближённо, tiktoken только для OpenAI)
3. Что делать при превышении? (ждать освобождения слота)
4. Нужно ли логировать все проверки? (только при превышении)

**Важно:**
- Rate limiter работает ПЕРЕД отправкой запроса (превентивно)
- Скользящее окно — более точное, чем фиксированные интервалы
- Токены считаем для входящих запросов, ответы — по usage из API
- При превышении — ждём освобождения слота, не возвращаем ошибку сразу

**Тестовые сценарии:**
1. Запросы в пределах лимита — проходят
2. Превышение RPM — ожидание освобождения
3. Превышение TPM — ожидание освобождения
4. Скользящее окно — старые запросы не учитываются

## Зависимости

- Задача 001: LLM Gateway Queue и BatchExecutor
- Задача 002: LLM Gateway Response Router и Retry

## Следующие задачи

После завершения:
- Задача 004: SGR Agent Core интеграция
- Задача 005: Unit тесты LLM Gateway
