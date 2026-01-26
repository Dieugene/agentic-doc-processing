# Техническое задание: SGR Agent Core интеграция

## 1. Анализ задачи

Необходимо интегрировать фреймворк SGR (Schema-Guided Reasoning) и создать базовый класс `SystemSGRAgent` для всех будущих агентов системы. Ключевая особенность: использовать **SimpleLLMGateway** (задача 001b) вместо сложной версии с батчингом и rate limiting.

SGR обеспечивает структурированное рассуждение агентов через явные tools и логирование каждого шага, что снижает галлюцинации и обеспечивает наблюдаемость.

## 2. Текущее состояние

**Существующие модули для переиспользования:**
- `02_src/gateway/models.py` — содержит `LLMRequest`, `LLMResponse`, `LLMMessage`, `LLMTool`, `ModelConfig`
- `02_src/gateway/llm_gateway.py` или SimpleLLMGateway (001b) — интерфейс `request(request) -> response`

**Что нужно создать:**
- `02_src/agents/` — новая папка для агентов
- Базовый класс `SystemSGRAgent` с интеграцией в SimpleLLMGateway
- Структуры данных для SGR: `SGRTool`, `ReasoningStep`, `ToolCall`
- Пример агента-наследника `ExampleSGRAgent`
- Unit тесты с MockLLMGateway

## 3. Предлагаемое решение

### 3.1. Общий подход

**Архитектура:**
```
SystemSGRAgent (ABC)
    ├── Интеграция с SimpleLLMGateway
    ├── SGR reasoning loop
    ├── Tools интерфейс
    └── Логирование reasoning trace

Конкретные агенты (наследники)
    ├── ExampleSGRAgent (демонстрационный)
    ├── IndexatorAgent (будущая задача)
    └── NormalizerAgent (будущая задача)
```

**Ключевые решения:**
1. SGR Core не устанавливается как external dependency — реализуем паттерн SGR нативно
2. SimpleLLMGateway используется напрямую через `request()` метод
3. Reasoning trace сохраняется в JSON Lines формат (аппенд, по одной записи на запрос агента)
4. Max iterations для SGR loop: 10 (достаточно для большинства задач)

### 3.2. Компоненты

#### Модуль `02_src/agents/sgr_agent.py`

**Назначение:** Базовый класс для всех SGR-агентов системы.

**Интерфейс:**
```python
class SystemSGRAgent(ABC):
    def __init__(
        self,
        agent_id: str,
        llm_gateway: Union[SimpleLLMGateway, LLMGateway],
        model: str,
        system_prompt: str,
        tools: Optional[List[SGRTool]] = None,
        log_dir: Optional[str] = None
    )

    @abstractmethod
    async def process(self, input_data: Dict[str, Any]) -> Dict[str, Any]

    async def run(self, user_message: str, context: Optional[Dict] = None) -> str
```

**Зависимости:**
- `gateway.models` (LLMRequest, LLMResponse, LLMMessage, LLMTool)
- `pathlib`, `json`, `datetime` (для логирования)
- `asyncio` (для async операций)

#### Модуль `02_src/agents/tools.py`

**Назначение:** Базовые классы для SGR tools.

**Интерфейс:**
```python
class SGRTool:
    name: str
    description: str
    parameters_schema: Dict[str, Any]

    async def execute(self, **kwargs) -> Any
```

**Зависимости:** None (чистый Python)

#### Модуль `02_src/agents/example_agent.py`

**Назначение:** Пример агента-наследника для демонстрации интеграции.

**Интерфейс:**
```python
class ExampleSGRAgent(SystemSGRAgent):
    async def process(self, input_data: Dict[str, Any]) -> Dict[str, Any]
```

**Tools:** `GetTimeTool` — простой tool для получения текущего времени

### 3.3. Структуры данных

#### ReasoningStep
```python
@dataclass
class ReasoningStep:
    step_number: int
    action: str  # "think" | "call_tool" | "formulate_answer"
    thought: Optional[str] = None
    tool_used: Optional[str] = None
    tool_parameters: Optional[Dict[str, Any]] = None
    tool_result: Optional[Any] = None
    final_answer: Optional[str] = None
```

#### ToolCall
```python
@dataclass
class ToolCall:
    name: str
    parameters: Dict[str, Any]
    result: Optional[Any] = None
```

### 3.4. Ключевые алгоритмы

#### SGR Reasoning Loop (метод `_sgr_loop`)

**Логика:**
1. Цикл до 10 итераций
2. На каждой итерации:
   - Сформировать `LLMRequest` из текущих сообщений + tools
   - Отправить в `llm_gateway.request()`
   - Если ответ содержит `tool_calls`:
     - Выполнить каждый tool через `tool.execute(**parameters)`
     - Логировать шаг рассуждения
     - Добавить результаты в сообщения (формат Langchain: assistant tool call + tool response)
     - Продолжить цикл
   - Если ответ без tool_calls:
     - Это финальный ответ — вернуть его
3. Если превысен max iterations — вернуть error message

**Детали:**
- Tool results обрезаются до 200 символов при логировании (避免 большие логи)
- При ошибке выполнения tool — добавить error message в сообщения как tool result

#### Логирование reasoning trace

**Логика:**
1. Перед запуском агента очистить `_reasoning_trace`
2. Каждый шаг (think, call_tool, formulate_answer) добавляется в trace
3. После завершения `run()` сохранить trace в файл:
   - Путь: `{log_dir}/reasoning/{agent_id}.jsonl`
   - Формат: JSON Lines (одна JSON строка на запрос)
   - Содержимое: timestamp, agent_id, reasoning_trace (массив шагов)

### 3.5. Изменения в существующем коде

**Не требуется изменений в существующем коде.**
- SimpleLLMGateway уже имеет нужный интерфейс
- Модели из `gateway/models` переиспользуются

**Создаются новые модули:**
- `02_src/agents/__init__.py`
- `02_src/agents/sgr_agent.py`
- `02_src/agents/tools.py`
- `02_src/agents/example_agent.py`
- `02_src/agents/tests/`

### 3.6. Структура проекта

```
02_src/
├── agents/
│   ├── __init__.py
│   ├── sgr_agent.py            # SystemSGRAgent базовый класс
│   ├── tools.py                # SGRTool, ReasoningStep, ToolCall
│   ├── example_agent.py        # ExampleSGRAgent + GetTimeTool
│   └── tests/
│       ├── __init__.py
│       ├── test_sgr_agent.py
│       ├── test_example_agent.py
│       └── fixtures/
│           └── example_trace.jsonl

04_logs/
└── reasoning/
    └── {agent_id}.jsonl
```

## 4. План реализации

1. **Создать структуры данных** (`tools.py`):
   - `SGRTool` базовый класс
   - `ReasoningStep` dataclass
   - `ToolCall` dataclass

2. **Реализовать SystemSGRAgent** (`sgr_agent.py`):
   - `__init__` с инъекцией SimpleLLMGateway
   - `run` метод с подготовкой сообщений
   - `_sgr_loop` с reasoning логикой
   - `_log_step` и `_save_trace` для логирования

3. **Создать пример агента** (`example_agent.py`):
   - `ExampleSGRAgent` с реализацией `process`
   - `GetTimeTool` для демонстрации tools

4. **Unit тесты** (`tests/`):
   - `test_sgr_agent.py`: тест базового класса с MockLLMGateway
   - `test_example_agent.py`: тест примера агента
   - Проверка сохранения trace в файл

5. **Интеграционные тесты**:
   - Запуск ExampleSGRAgent с SimpleLLMGateway (mock mode)
   - Проверка reasoning trace структуры

## 5. Технические критерии приемки

- [ ] TC-001: `SystemSGRAgent` принимает `SimpleLLMGateway` через конструктор
- [ ] TC-002: Метод `run` запускает SGR loop с max 10 итераций
- [ ] TC-003: Tools выполняются корректно, результаты добавляются в сообщения
- [ ] TC-004: Reasoning trace сохраняется в `04_logs/reasoning/{agent_id}.jsonl`
- [ ] TC-005: Формат trace соответствует схеме из раздела 3.3
- [ ] TC-006: Tool results обрезаются до 200 символов в логах
- [ ] TC-007: `ExampleSGRAgent` с `GetTimeTool` работает end-to-end
- [ ] TC-008: Unit тесты покрывают >80% кода
- [ ] TC-009: Интеграция с SimpleLLMGateway работает без ошибок

## 6. Важные детали для Developer

### 6.1. Конвертация между форматами

**Gateway → SGR:**
- Gateway возвращает `tool_calls` как `List[Dict]` в формате Langchain
- Нужно сконвертировать в вызовы `SGRTool.execute()`

**SGR → Gateway:**
- После выполнения tool нужно добавить два сообщения:
  1. Assistant message с tool call (для Langchain совместимости)
  2. Tool message с результатом

### 6.2. Формат tool calls в Gateway

Langchain формат (ожидает SimpleLLMGateway):
```python
{
    "name": "tool_name",
    "arguments": "{\"param1\": \"value1\"}",
    "id": "call_abc123"
}
```

Нужно парсить `arguments` как JSON перед вызовом `SGRTool.execute()`.

### 6.3. Обработка ошибок tools

При ошибке выполнения tool:
- Логировать error в trace
- Добавить error message как tool result
- Продолжить loop (позволяет LLM исправиться)

### 6.4. Логирование trace

**ВАЖНО:** Использовать JSON Lines формат:
- Одна строка = одна JSON запись
- Аппенд (не перезапись) для истории запросов
- Создавать директорию если не существует

### 6.5. Тестирование с Mock

Использовать `MockLLMGateway` из `02_src/gateway/tests/mock_gateway.py`:
- Предопределить ответы для tool calls
- Проверить что `request()` вызывался корректное количество раз
- Валидировать структуру запроса (messages, tools)

### 6.6. Конфигурация логов

`log_dir` опционален — если None, логирование отключено. Это удобно для unit тестов.

### 6.7. Константы

Максимальное количество итераций (10) должно быть константой класса для лёгкой настройки в будущем.

### 6.8. Типизация

Использовать `Union[SimpleLLMGateway, LLMGateway]` для поддержки обеих версий Gateway, так как интерфейс идентичен.
