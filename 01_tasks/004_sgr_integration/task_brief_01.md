# Задача 004: SGR Agent Core интеграция

## Что нужно сделать

Интегрировать фреймворк SGR (Schema-Guided Reasoning) в проект:
1. Установить sgr-agent-core из репозитория
2. Создать базовый класс SystemSGRAgent для всех агентов системы
3. Реализовать интеграцию SystemSGRAgent с LLM Gateway
4. Создать пример тестового агента

## Зачем

SGR Agent Core - базовый фреймворк для всех агентов системы. Он обеспечивает:
- Жёсткое структурирование рассуждений (可控 reasoning)
- Снижение галлюцинаций через tools
- Логирование цепочки рассуждений
- Контролируемый output

Без этой интеграции невозможно создавать Indexator, Normalizer, Snapshot и другие агенты.

## Acceptance Criteria

- [ ] AC-001: sgr-agent-core установлен как зависимость (requirements.txt/pyproject.toml)
- [ ] AC-002: Создан SystemSGRAgent базовый класс
- [ ] AC-003: SystemSGRAgent переопределяет call_llm для использования LLM Gateway
- [ ] AC-004: SystemSGRAgent логирует reasoning в 04_logs/reasoning/
- [ ] AC-005: Создан пример тестового SGR-агента
- [ ] AC-006: Unit тесты для SystemSGRAgent
- [ ] AC-007: Интеграционный тест: агент → Gateway → MockAPI → ответ

## Контекст

**Implementation Plan:**
- `00_docs/architecture/implementation_plan.md` - Iteration 1, модуль SGR Agent Core Integration

**Архитектура:**
- `00_docs/architecture/overview.md` - раздел 6 "Базовый фреймворк агентов: SGR Agent Core"

**SGR репозитории:**
- Python: https://github.com/vamplabAI/sgr-agent-core
- Документация: https://vamplabai.github.io/sgr-agent-core/

**Интерфейсы и контракты:**

```python
from sgr_agent_core import SGRAgent, SGRAgentConfig
from typing import Dict, Any, List, Optional
import json
from datetime import datetime

class SystemSGRAgent(SGRAgent):
    """
    Базовый класс для всех агентов системы.

    Наследует SGRAgent из фреймворка и добавляет:
    - Автоматическую интеграцию с LLM Gateway
    - Стандартное логирование reasoning
    """

    llm_gateway: LLMGateway

    def __init__(
        self,
        config: SGRAgentConfig,
        llm_gateway: LLMGateway,
        log_dir: str = "04_logs/reasoning/"
    ):
        super().__init__(config)
        self.llm_gateway = llm_gateway
        self.log_dir = log_dir
        self.agent_id = config.agent_id

    async def call_llm(
        self,
        model: str,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict[str, Any]]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Переопределяет метод call_llm для использования Gateway.

        Вместо прямого вызова API идёт через LLMGateway.request()
        """
        from .llm_gateway.models import LLMRequest, RequestPriority

        request = LLMRequest(
            model=ModelProvider(model),
            messages=[LLMMessage(**msg) for msg in messages],
            tools=[LLMTool(**t) for t in tools] if tools else None,
            request_id=f"{self.agent_id}_{datetime.now().isoformat()}",
            priority=RequestPriority.NORMAL
        )

        response = await self.llm_gateway.request(request)

        return {
            "content": response.content,
            "tool_calls": response.tool_calls,
            "model": response.model,
            "tokens_used": response.tokens_used
        }

    async def log_reasoning(
        self,
        user_query: str,
        reasoning_trace: List[Dict[str, Any]],
        final_response: Dict[str, Any]
    ):
        """
        Логирование цепочки рассуждений.

        Формат лога:
        {
          "log_id": "reasoning_20250123_104512",
          "agent_id": "snapshot_reporting_deadlines",
          "timestamp": "2025-01-23T10:45:12Z",
          "request": {"user_query": "..."},
          "reasoning_trace": [...],
          "final_response": {...}
        }
        """
        log_entry = {
            "log_id": f"reasoning_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            "agent_id": self.agent_id,
            "timestamp": datetime.now().isoformat() + "Z",
            "request": {
                "user_query": user_query,
                "available_tools": self.get_available_tools()
            },
            "reasoning_trace": reasoning_trace,
            "final_response": final_response
        }

        import os
        os.makedirs(self.log_dir, exist_ok=True)

        log_path = os.path.join(
            self.log_dir,
            f"{self.agent_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        )

        with open(log_path, 'w', encoding='utf-8') as f:
            json.dump(log_entry, f, ensure_ascii=False, indent=2)

    def get_available_tools(self) -> List[str]:
        """Получить список доступных tools агента"""
        # Реализация в подклассах
        return []
```

**Пример тестового агента:**

```python
class TestSystemSGRAgent(SystemSGRAgent):
    """Пример SGR-агента для тестирования интеграции"""

    async def process_query(self, query: str) -> str:
        """
        Простой процесс запроса.

        Reasoning trace:
        1. analyze_query - понять запрос
        2. formulate_answer - сформировать ответ
        """

        reasoning_trace = []
        final_response = {}

        # Step 1: Analyze query
        reasoning_trace.append({
            "step": 1,
            "action": "analyze_query",
            "thought": f"Анализирую запрос: {query}",
            "tool_used": None,
            "result": "Query is a simple question"
        })

        # Step 2: Formulate answer
        reasoning_trace.append({
            "step": 2,
            "action": "formulate_answer",
            "thought": "Формулирую ответ на основе контекста",
            "tool_used": None,
            "result": f"Answer: Test response to '{query}'"
        })

        final_response = {
            "content": f"Test response to: {query}",
            "sources": [],
            "confidence": 1.0
        }

        # Логируем reasoning
        await self.log_reasoning(query, reasoning_trace, final_response)

        return final_response["content"]
```

**Структура проекта:**

```
02_src/
├── sgr_agents/
│   ├── __init__.py
│   ├── base.py              # SystemSGRAgent
│   └── test_agent.py        # TestSystemSGRAgent
├── tests/
│   ├── test_sgr_integration.py
│   └── fixtures/
│       └── reasoning_log_example.json
04_logs/
└── reasoning/
    └── (логи создаются автоматически)
```

**requirements.txt:**

```
sgr-agent-core>=0.5.0
```

или pyproject.toml:

```toml
[project]
dependencies = [
    "sgr-agent-core>=0.5.0",
]
```

**Моки для тестирования:**

- MockLLMGateway из задачи 001 для изоляции от реального API
- Unit тесты проверяют call_llm переопределение
- Проверка формата логов reasoning

**Существующий код для reference:**
- `02_src/llm_gateway/` - LLM Gateway из задачи 001

**Другие ссылки:**
- https://vamplabai.github.io/sgr-agent-core/ - Документация SGR
- https://github.com/vamplabAI/sgr-agent-core - Репозиторий

## Зависимости

- Задача 001: LLM Gateway (MockLLMGateway для тестов)

Можно начинать параллельно с задачами 001-003, если использовать mock Gateway.

## Следующие задачи

После завершения этой задачи:
- Задача 006: Document Skeleton (будет использовать SystemSGRAgent)
- Задача 011: Indexator Agent (первый реальный SGR-агент)
