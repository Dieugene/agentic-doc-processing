# Задача 001b: SimpleLLMGateway (временная упрощённая версия)

## Что нужно сделать

Реализовать упрощённую версию LLM Gateway — простую обёртку над API LLM провайдеров без очередей, батчинга и rate limiting.

## Зачем

Текущая реализация LLM Gateway (задачи 001-003) сложна в отладке. SimpleLLMGateway — временный вариант для быстрого прогресса по другим задачам.

**Временный характер:** Это промежуточное решение. В будущем будет заменено на полную версию или останется если окажется достаточным.

## Acceptance Criteria

- [ ] AC-001: SimpleLLMGateway с методами request() и batch()
- [ ] AC-002: Retry только для timeout ошибок (408, 504)
- [ ] AC-003: 5 попыток, задержка 1с (в коде, не в env)
- [ ] AC-004: Остальные ошибки → исключение без retry
- [ ] AC-005: Совместимый интерфейс с LLMGateway
- [ ] AC-006: Unit тесты
- [ ] AC-007: Логи в 04_logs/gateway/simple/

## Контекст

**Отличия от полной версии (001-003):**

| Характеристика | Полная версия (001-003) | SimpleLLMGateway (001b) |
|----------------|-------------------------|------------------------|
| Очереди | RequestQueue для каждой модели | ❌ Нет |
| Батчинг | BatchExecutor с Langchain | ❌ Нет |
| Rate limiting | RateLimiter (RPM/TPM) | ❌ Нет |
| Retry | Множественные типы ошибок | ✅ Только timeout (408, 504) |
| Response Router | Отдельный класс | ❌ Не нужен |
| Сложность | Высокая | Минимальная |

**Интерфейсы и контракты:**

```python
from typing import List, Dict, Any, Optional
from enum import Enum
import asyncio
import logging

# ============================================
# Модели и провайдеры (переиспользуются)
# ============================================

class ModelProvider(str, Enum):
    CLAUDE_HAIKU = "claude-haiku"
    CLAUDE_SONNET = "claude-sonnet"
    CLAUDE_OPUS = "claude-opus"
    GPT_4O_MINI = "gpt-4o-mini"
    GPT_4O = "gpt-4o"

@dataclass
class LLMMessage:
    role: str  # "system" | "user" | "assistant"
    content: str

@dataclass
class LLMTool:
    name: str
    description: str
    parameters_schema: Dict[str, Any]

@dataclass
class LLMRequest:
    request_id: str
    model: str  # идентификатор из configs
    messages: List[LLMMessage]
    tools: Optional[List[LLMTool]] = None
    temperature: float = 0.0
    agent_id: Optional[str] = None

@dataclass
class LLMResponse:
    request_id: str
    content: str
    tool_calls: Optional[List[Dict[str, Any]]] = None
    usage: Optional[Dict[str, int]] = None
    latency_ms: int = 0

# ============================================
# Simple LLM Gateway
# ============================================

class SimpleLLMGateway:
    """
    Упрощённая версия LLM Gateway.

    Без очередей, батчинга, rate limiting.
    Только retry для timeout ошибок.
    """

    # Константы retry (в коде, не в env)
    MAX_RETRIES: int = 5
    RETRY_DELAY_SECONDS: float = 1.0

    def __init__(
        self,
        configs: Dict[str, 'ModelConfig'],  # ModelConfig из задач 001-003
        log_dir: Optional[str] = None
    ):
        """
        Args:
            configs: Словарь {model_id: ModelConfig}
            log_dir: Директория для логов
        """
        self.log_dir = log_dir
        self.configs = configs
        self._clients = {}  # model_id -> langchain клиент

        # Создаём клиентов для каждой модели
        for model_id, config in configs.items():
            self._clients[model_id] = self._create_client(config)

        self._setup_logging()

    def _create_client(self, config: 'ModelConfig'):
        """
        Создать Langchain клиент для модели.

        Использует langchain для унифицированного доступа.
        """
        from langchain_anthropic import ChatAnthropic
        from langchain_openai import ChatOpenAI

        provider = config.provider

        if provider == ModelProvider.CLAUDE_HAIKU:
            return ChatAnthropic(
                model=config.model_name,
                api_key=config.api_key,
                temperature=0.0,
                timeout=None  # без искусственных ограничений
            )
        elif provider in [ModelProvider.GPT_4O_MINI, ModelProvider.GPT_4O]:
            return ChatOpenAI(
                model=config.model_name,
                api_key=config.api_key,
                temperature=0.0,
                timeout=None
            )
        else:
            raise ValueError(f"Unsupported provider: {provider}")

    async def request(self, request: LLMRequest) -> LLMResponse:
        """
        Отправить запрос к LLM с retry для timeout.

        Args:
            request: LLMRequest

        Returns:
            LLMResponse

        Raises:
            Exception: для всех ошибок кроме timeout (после последней попытки)
        """
        client = self._clients.get(request.model)
        if not client:
            raise ValueError(f"Unknown model: {request.model}")

        # Конвертируем в langchain format
        lc_messages = [(msg.role, msg.content) for msg in request.messages]

        last_exception = None

        # Retry loop (только для timeout)
        for attempt in range(self.MAX_RETRIES):
            try:
                start_time = asyncio.get_event_loop().time()

                # Отправляем запрос
                lc_response = await client.ainvoke(lc_messages)

                # Формируем ответ
                response = LLMResponse(
                    request_id=request.request_id,
                    content=lc_response.content,
                    tool_calls=self._extract_tool_calls(lc_response),
                    usage=getattr(lc_response, 'usage_metadata', None),
                    latency_ms=int((asyncio.get_event_loop().time() - start_time) * 1000)
                )

                self._log_success(request, response, attempt)
                return response

            except Exception as e:
                last_exception = e

                # Проверяем: timeout ошибка?
                if self._is_timeout_error(e):
                    if attempt < self.MAX_RETRIES - 1:
                        # Retry с задержкой
                        self._log_retry(request, attempt, e)
                        await asyncio.sleep(self.RETRY_DELAY_SECONDS)
                        continue
                    else:
                        # Последняя попытка — крашим для отладки
                        self._log_max_retries_exceeded(request, e)
                        raise

                # Не timeout — сразу пробрасываем
                self._log_error(request, e)
                raise

        # Не должно дойти сюда, но на всякий случай
        raise last_exception

    async def batch(self, requests: List[LLMRequest]) -> List[LLMResponse]:
        """
        Отправить батч запросов (последовательно, без оптимизации).

        Args:
            requests: Список LLMRequest

        Returns:
            Список LLMResponse
        """
        # Просто последовательные запросы
        responses = []
        for req in requests:
            response = await self.request(req)
            responses.append(response)

        return responses

    def _is_timeout_error(self, error: Exception) -> bool:
        """
        Проверить: timeout ошибка на стороне провайдера?

        Проверяет HTTP status codes:
        - 408 Request Timeout
        - 504 Gateway Timeout
        """
        # Проверяем httpx HTTPStatusError
        if hasattr(error, 'response'):
            status = getattr(error.response, 'status_code', None)
            if status in [408, 504]:
                return True

        return False

    def _extract_tool_calls(self, lc_response) -> Optional[List[Dict[str, Any]]]:
        """Извлечь tool calls из langchain response"""
        if hasattr(lc_response, 'tool_calls'):
            return lc_response.tool_calls
        return None

    def _setup_logging(self):
        """Настроить логирование"""
        self.logger = logging.getLogger(__name__)

    def _log_success(self, request: LLMRequest, response: LLMResponse, attempt: int):
        """Логировать успешный запрос"""
        if not self.log_dir:
            return

        import json
        from pathlib import Path

        log_path = Path(self.log_dir) / "gateway" / "simple_requests.jsonl"
        log_path.parent.mkdir(parents=True, exist_ok=True)

        log_entry = {
            "timestamp": self._get_timestamp(),
            "model": request.model,
            "request_id": request.request_id,
            "agent_id": request.agent_id,
            "attempt": attempt,
            "latency_ms": response.latency_ms,
            "status": "success"
        }

        with open(log_path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + '\n')

    def _log_retry(self, request: LLMRequest, attempt: int, error: Exception):
        """Логировать retry попытку"""
        if not self.log_dir:
            return

        import json
        from pathlib import Path

        log_path = Path(self.log_dir) / "gateway" / "simple_retries.jsonl"
        log_path.parent.mkdir(parents=True, exist_ok=True)

        log_entry = {
            "timestamp": self._get_timestamp(),
            "model": request.model,
            "request_id": request.request_id,
            "attempt": attempt,
            "error": str(error),
            "error_type": type(error).__name__,
            "status": "retry"
        }

        with open(log_path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + '\n')

    def _log_max_retries_exceeded(self, request: LLMRequest, error: Exception):
        """Логировать превышение max retries"""
        if not self.log_dir:
            return

        import json
        from pathlib import Path

        log_path = Path(self.log_dir) / "gateway" / "simple_errors.jsonl"
        log_path.parent.mkdir(parents=True, exist_ok=True)

        log_entry = {
            "timestamp": self._get_timestamp(),
            "model": request.model,
            "request_id": request.request_id,
            "agent_id": request.agent_id,
            "error": str(error),
            "error_type": type(error).__name__,
            "max_retries": self.MAX_RETRIES,
            "status": "max_retries_exceeded"
        }

        with open(log_path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + '\n')

    def _log_error(self, request: LLMRequest, error: Exception):
        """Логировать не-timeout ошибку"""
        if not self.log_dir:
            return

        import json
        from pathlib import Path

        log_path = Path(self.log_dir) / "gateway" / "simple_errors.jsonl"
        log_path.parent.mkdir(parents=True, exist_ok=True)

        log_entry = {
            "timestamp": self._get_timestamp(),
            "model": request.model,
            "request_id": request.request_id,
            "agent_id": request.agent_id,
            "error": str(error),
            "error_type": type(error).__name__,
            "status": "error"
        }

        with open(log_path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + '\n')

    def _get_timestamp(self) -> str:
        """Получить текущий timestamp"""
        from datetime import datetime
        return datetime.now().isoformat()
```

**Структура проекта:**

```
02_src/
├── gateway/
│   ├── simple_llm_gateway.py    # SimpleLLMGateway
│   └── tests/
│       ├── test_simple_gateway.py
│       └── fixtures/
│           └── sample_responses.json
04_logs/
└── gateway/
    ├── simple_requests.jsonl
    ├── simple_retries.jsonl
    └── simple_errors.jsonl
```

**Совместимость с существующим кодом:**

SimpleLLMGateway реализует **тот же интерфейс**, что и LLMGateway из задач 001-003:
- `request(request: LLMRequest) -> LLMResponse`
- `batch(requests: List[LLMRequest]) -> List[LLMResponse]`

Поэтому **не требует изменений** в:
- Задача 004 (SGR Integration) — использует интерфейс
- Задача 005 (Unit тесты) — тестирует интерфейс
- Другие модули — импортируют LLMGateway через интерфейс

## Примечания для Analyst

**Важно:**
- Никаких искусственных ограничений (timeout=None)
- Retry только для timeout (408, 504), остальные ошибки — сразу exception
- MAX_RETRIES и RETRY_DELAY_SECONDS — в коде, не в env
- При превышении max retries — проброс исключения (останов программы для отладки)

**Ключевые решения:**
1. Использовать langchain клиентов? (да, как в 001-003)
2. Как логировать retry? (отдельный файл simple_retries.jsonl)
3. Нужно ли batch() вообще? (да, для совместимости, но последовательные запросы)

**Зависимости**

Задачи 001-003 (сложная версия LLM Gateway) — для переиспользования ModelConfig и понимания интерфейса.

## Следующие задачи

После завершения:
- SimpleLLMGateway можно использовать вместо сложной версии в задачах 004-005 и далее
- Полная версия (001-003) остаётся в коде, может быть удалена или переработана позже
