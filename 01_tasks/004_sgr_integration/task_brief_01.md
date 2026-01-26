# Задача 004: SGR Agent Core интеграция

## Что нужно сделать

Интегрировать фреймворк SGR (Schema-Guided Reasoning) и создать базовый класс SystemSGRAgent для всех агентов системы.

## Зачем

SGR обеспечивает структурированное рассуждение агентов, снижает галлюцинации и предоставляет наблюдаемость. SystemSGRAgent — базовый класс для всех агентов (Indexator, Normalizer, Dispatcher, etc.).

## Acceptance Criteria

- [ ] AC-001: SGR Core установлен как зависимость
- [ ] AC-002: SystemSGRAgent базовый класс создан
- [ ] AC-003: Интеграция с LLM Gateway
- [ ] AC-004: Tools интерфейс для SGR-агентов
- [ ] AC-005: Логирование рассуждений (reasoning trace)
- [ ] AC-006: Unit тесты SystemSGRAgent
- [ ] AC-007: Пример агента-наследника

## Контекст

**ADR-000: SGR Agent Core**

SGR (Schema-Guided Reasoning) — фреймворк для построения агентов с явным структурированием рассуждений.

**Репозитории:**
- Python: https://github.com/vamplabAI/sgr-agent-core
- Документация: https://vamplabai.github.io/sgr-agent-core/

**Ключевые концепции:**
- **Schema** — структура вывода (tools)
- **Reasoning** — явная цепочка рассуждений
- **Observability** — логирование каждого шага

**Интерфейсы и контракты:**

```python
from typing import List, Dict, Any, Optional, Callable
from abc import ABC, abstractmethod
from dataclasses import dataclass
import asyncio

# ============================================
# SGR Tools
# ============================================

class SGRTool:
    """
    Базовый класс для SGR tools.

    Tool — функция, которую агент может вызвать.
    """
    name: str
    description: str
    parameters_schema: Dict[str, Any]

    async def execute(self, **kwargs) -> Any:
        """Выполнить tool"""
        pass

@dataclass
class ToolCall:
    """Вызов tool"""
    name: str
    parameters: Dict[str, Any]
    result: Optional[Any] = None

@dataclass
class ReasoningStep:
    """Шаг рассуждения"""
    step_number: int
    action: str  # "think" | "call_tool" | "formulate_answer"
    thought: Optional[str] = None
    tool_used: Optional[str] = None
    tool_parameters: Optional[Dict[str, Any]] = None
    tool_result: Optional[Any] = None
    final_answer: Optional[str] = None

# ============================================
# System SGR Agent
# ============================================

class SystemSGRAgent(ABC):
    """
    Базовый класс для всех SGR-агентов системы.

    Интегрирует SGR Core с LLM Gateway.
    """

    def __init__(
        self,
        agent_id: str,
        llm_gateway: 'LLMGateway',
        model: str,
        system_prompt: str,
        tools: Optional[List[SGRTool]] = None,
        log_dir: Optional[str] = None
    ):
        """
        Args:
            agent_id: Уникальный ID агента
            llm_gateway: LLMGateway для запросов к LLM
            model: Модель для использования
            system_prompt: Системный промпт агента
            tools: Список доступных tools
            log_dir: Директория для логов рассуждений
        """
        self.agent_id = agent_id
        self.llm_gateway = llm_gateway
        self.model = model
        self.system_prompt = system_prompt
        self.tools = tools or []
        self.log_dir = log_dir

        # История рассуждений текущего запроса
        self._reasoning_trace: List[ReasoningStep] = []

    @abstractmethod
    async def process(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Основной метод обработки входных данных.

        Должен быть переопределён в наследниках.

        Args:
            input_data: Входные данные

        Returns:
            Результат обработки
        """
        pass

    async def run(self, user_message: str, context: Optional[Dict[str, Any]] = None) -> str:
        """
        Запустить агента с сообщением пользователя.

        Args:
            user_message: Сообщение от пользователя
            context: Дополнительный контекст

        Returns:
            Ответ агента
        """
        # Очищаем историю
        self._reasoning_trace = []

        # Формируем сообщения
        messages = [
            LLMMessage(role="system", content=self.system_prompt),
            LLMMessage(role="user", content=user_message)
        ]

        # Добавляем tools если есть
        tools = None
        if self.tools:
            tools = [
                LLMTool(
                    name=tool.name,
                    description=tool.description,
                    parameters=tool.parameters_schema
                )
                for tool in self.tools
            ]

        # Шаг 1: Анализ запроса
        await self._log_step(
            action="think",
            thought=f"Получен запрос: {user_message[:100]}..."
        )

        # Запускаем SGR loop
        response = await self._sgr_loop(messages, tools, context)

        # Логируем финальный ответ
        await self._log_step(
            action="formulate_answer",
            final_answer=response
        )

        # Сохраняем trace
        await self._save_trace()

        return response

    async def _sgr_loop(
        self,
        messages: List[LLMMessage],
        tools: Optional[List[LLMTool]],
        context: Optional[Dict[str, Any]]
    ) -> str:
        """
        SGR reasoning loop.

        1. Отправить запрос в LLM
        2. Если есть tool calls — выполнить
        3. Добавить результаты в сообщения
        4. Повторять пока не будет финального ответа
        """
        max_iterations = 10

        for iteration in range(max_iterations):
            # Формируем запрос
            request = LLMRequest(
                request_id=f"{self.agent_id}_iter_{iteration}",
                model=self.model,
                messages=messages,
                tools=tools,
                agent_id=self.agent_id
            )

            # Отправляем в Gateway
            response = await self.llm_gateway.request(request)

            # Проверяем на tool calls
            if response.tool_calls:
                # Выполняем tools
                for tool_call in response.tool_calls:
                    tool_name = tool_call.get("name")
                    tool_params = tool_call.get("parameters", {})

                    await self._log_step(
                        action="call_tool",
                        tool_used=tool_name,
                        tool_parameters=tool_params
                    )

                    # Ищем tool
                    tool = next((t for t in self.tools if t.name == tool_name), None)
                    if tool:
                        result = await tool.execute(**tool_params)

                        await self._log_step(
                            action="call_tool",
                            tool_used=tool_name,
                            tool_result=str(result)[:200]
                        )

                        # Добавляем результат в сообщения
                        messages.append(LLMMessage(
                            role="assistant",
                            content="",  # tool call
                            tool_call=tool_call
                        ))
                        messages.append(LLMMessage(
                            role="tool",
                            name=tool_name,
                            content=str(result)
                        ))
                    else:
                        # Tool не найден
                        messages.append(LLMMessage(
                            role="assistant",
                            content=f"Error: Tool {tool_name} not found"
                        ))
                # Продолжаем loop
            else:
                # Финальный ответ
                return response.content

        # Превышен max iterations
        return "Error: Maximum iterations exceeded"

    async def _log_step(self, **kwargs):
        """Логировать шаг рассуждения"""
        step = ReasoningStep(
            step_number=len(self._reasoning_trace) + 1,
            **kwargs
        )
        self._reasoning_trace.append(step)

    async def _save_trace(self):
        """Сохранить trace рассуждения"""
        if not self.log_dir:
            return

        import json
        from pathlib import Path

        log_path = Path(self.log_dir) / "reasoning" / f"{self.agent_id}.jsonl"
        log_path.parent.mkdir(parents=True, exist_ok=True)

        trace_entry = {
            "timestamp": datetime.now().isoformat(),
            "agent_id": self.agent_id,
            "reasoning_trace": [
                {
                    "step": s.step_number,
                    "action": s.action,
                    "thought": s.thought,
                    "tool_used": s.tool_used,
                    "tool_parameters": s.tool_parameters,
                    "tool_result": s.tool_result,
                    "final_answer": s.final_answer
                }
                for s in self._reasoning_trace
            ]
        }

        with open(log_path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(trace_entry, ensure_ascii=False) + '\n')

# ============================================
# Пример агента-наследника
# ============================================

class ExampleSGRAgent(SystemSGRAgent):
    """
    Пример простого SGR-агента.

    Используется для тестирования интеграции.
    """

    async def process(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Обработать входные данные.

        Пример: анализ текста
        """
        text = input_data.get("text", "")

        response = await self.run(
            user_message=f"Проанализируй текст: {text}",
            context=input_data
        )

        return {
            "analysis": response,
            "agent_id": self.agent_id
        }

# ============================================
# Пример Tool
# ============================================

class GetTimeTool(SGRTool):
    """Простой tool для получения текущего времени"""

    name = "get_current_time"
    description = "Получить текущее время и дату"
    parameters_schema = {
        "type": "object",
        "properties": {},
        "required": []
    }

    async def execute(self, **kwargs) -> str:
        from datetime import datetime
        return datetime.now().isoformat()
```

**Структура проекта:**

```
02_src/
├── agents/
│   ├── __init__.py
│   ├── sgr_agent.py            # SystemSGRAgent
│   ├── tools.py                # Базовые SGRTool классы
│   └── tests/
│       ├── test_sgr_agent.py
│       ├── test_example_agent.py
│       └── fixtures/
│           └── example_trace.jsonl
04_logs/
└── reasoning/
    └── {agent_id}.jsonl
```

## Примечания для Analyst

**Ключевые решения:**
1. Какой max_iterations для SGR loop? (10 достаточно)
2. Как логировать tool results? (обрезать до 200 символов)
3. Где хранить traces? (04_logs/reasoning/{agent_id}.jsonl)
4. Нужно ли сжимать старые traces? (для v1.0 — нет)

**Важно:**
- SystemSGRAgent — абстрактный класс, process() переопределяется
- LLM Gateway интегрируется через request()
- Tools — обычные Python async функции
- Traces сохраняются в JSON Lines для парсинга

**Установка SGR Core:**
```bash
# Из requirements.txt
sgr-agent-core>=0.1.0
```

**Тестовые сценарии:**
1. Создание ExampleAgent
2. Запуск без tools
3. Запуск с tools (get_current_time)
4. Проверка сохранения trace
5. Проверка интеграции с LLM Gateway (через Mock)

## Зависимости

- Задача 001-003: LLM Gateway (для запросов к LLM)

## Следующие задачи

После завершения:
- Задача 005: Unit тесты LLM Gateway
- Итерация 2: задачи 006+ (используют SystemSGRAgent)
