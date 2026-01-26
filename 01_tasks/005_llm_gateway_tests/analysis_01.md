# Технический план: Unit тесты SimpleLLMGateway

## 1. Анализ задачи

Создать комплексные unit тесты для SimpleLLMGateway — упрощённой версии LLM Gateway без очередей, батчинга и rate limiting. SimpleLLMGateway — временный вариант для быстрого прогресса по другим задачам, поэтому тесты должны быть простыми, но полными.

**Ключевое отличие от task_brief:** task_brief описывает тесты для сложной версии (001-003), но этот ТЗ для SimpleLLMGateway (001b) — минимальной реализации с retry только для timeout ошибок.

## 2. Текущее состояние

**Существующий код:**
- `02_src/gateway/models.py` — общие модели (LLMRequest, LLMResponse, ModelConfig)
- `02_src/gateway/tests/test_llm_gateway.py` — тесты для сложной версии (001-003)
- `02_src/gateway/tests/mock_gateway.py` — MockLLMGateway для тестов

**Что переиспользуем:**
- Модели из `models.py` (они общие для обеих версий)
- Паттерны из существующих тестов (фикстуры, структура)
- MockLLMGateway как эталон интерфейса

**Что создаём заново:**
- SimpleLLMGateway (пока не реализован, только в task_brief)
- Тесты специально для SimpleLLMGateway
- Mock'и для Langchain клиентов ( timeout ошибки)

## 3. Предлагаемое решение

### 3.1. Общий подход

Создать изолированный набор тестов для SimpleLLMGateway в отдельном файле. Тесты должны покрывать:
- Основной метод `request()` с retry логикой для timeout
- Метод `batch()` (последовательные вызовы)
- Логирование в разные файлы
- Моки Langchain клиентов без реальных API вызовов

**Ключевое решение:** Использовать `unittest.mock.AsyncMock` для мокания Langchain клиентов. Не использовать существующий MockLLMGateway — он для интеграционных тестов других модулей, а не для unit тестов Gateway.

### 3.2. Компоненты

#### Тестовый файл: test_simple_gateway.py
- **Назначение:** Unit тесты для SimpleLLMGateway
- **Расположение:** `02_src/gateway/tests/test_simple_gateway.py`
- **Зависимости:** pytest, pytest-asyncio, unittest.mock

#### Фикстуры для тестов
- **simple_gateway_config:** ModelConfig для тестовой модели
- **mock_langchain_client:** AsyncMock для Langchain клиента
- **timeout_error_mock:** Mock для timeout ошибки (408/504)

### 3.3. Структуры данных

**Используем существующие модели из models.py:**
```python
LLMRequest {
  request_id: str
  model: str
  messages: List[LLMMessage]
  tools: Optional[List[LLMTool]]
  temperature: float
  agent_id: Optional[str]
}

LLMResponse {
  request_id: str
  content: str
  tool_calls: Optional[List[Dict]]
  usage: Optional[Dict[str, int]]
  latency_ms: int
}
```

**Новые структуры для тестов:**
```python
TimeoutErrorSimulation {
  status_code: int  # 408 или 504
  message: str
}
```

### 3.4. Ключевые алгоритмы

#### Тестирование retry логики
1. Мокаем Langchain клиент для генерации timeout ошибки (408)
2. Вызываем `request()` первый раз → получает timeout
3. Проверяем: лог retry записан в `simple_retries.jsonl`
4. Второй вызов возвращает успех
5. Проверяем: лог успеха записан в `simple_requests.jsonl`

#### Тестирование batch
1. Создаём 3 запроса
2. Вызываем `batch()`
3. Проверяем: ответы возвращены в том же порядке
4. Проверяем: все логи записаны

### 3.5. Изменения в существующем коде

**Не требуется:** Создаём новый файл, существующие тесты не затрагиваем.

## 4. План реализации

1. **Создать структуру тестового файла**
   - Создать `02_src/gateway/tests/test_simple_gateway.py`
   - Добавить импорты и базовые фикстуры

2. **Создать фикстуры**
   - `simple_gateway()` — создаёт экземпляр SimpleLLMGateway с моками
   - `mock_langchain_client()` — AsyncMock для клиента
   - `temp_log_dir()` — временная директория для логов

3. **Реализовать тесты инициализации**
   - TC-1: Успешное создание с configs
   - TC-2: Создание клиента для Claude
   - TC-3: Создание клиента для OpenAI
   - TC-4: Ошибка при неизвестном провайдере

4. **Реализовать тесты метода request()**
   - TC-5: Успешный запрос
   - TC-6: Timeout ошибка → retry → успех
   - TC-7: Timeout → MAX_RETRIES превышен → exception
   - TC-8: Не-timeout ошибка → сразу exception (без retry)
   - TC-9: Unknown model → ValueError

5. **Реализовать тесты метода batch()**
   - TC-10: Последовательная обработка запросов
   - TC-11: Порядок ответов совпадает с запросами
   - TC-12: Ошибка в одном из запросов → exception

6. **Реализовать тесты логирования**
   - TC-13: Лог успешного запроса в `simple_requests.jsonl`
   - TC-14: Лог retry в `simple_retries.jsonl`
   - TC-15: Лог ошибки timeout в `simple_errors.jsonl`
   - TC-16: Лог не-timeout ошибки в `simple_errors.jsonl`
   - TC-17: Формат логов (все поля присутствуют)

7. **Добавить фикстуры с timeout ошибками**
   - Mock для httpx.HTTPStatusError с 408
   - Mock для httpx.HTTPStatusError с 504
   - Helper для создания mock Langchain клиента с timeout

8. **Добавить интеграционные тесты**
   - TC-18: Полный цикл запрос-ответ
   - TC-19: Множественные retry

9. **Проверить покрытие**
   - Запустить pytest с --cov
   - Убедиться что покрытие >80%

10. **Обновить MockLLMGateway** (если нужно)
    - Проверить что MockLLMGateway совместим с SimpleLLMGateway
    - Добавить методы если не хватает

## 5. Технические критерии приемки

- [ ] TC-001: SimpleLLMGateway создаётся с configs
- [ ] TC-002: Метод request() возвращает LLMResponse при успехе
- [ ] TC-003: Timeout ошибка (408) → retry 5 раз с задержкой 1с
- [ ] TC-004: Timeout ошибка (504) → retry 5 раз с задержкой 1с
- [ ] TC-005: Не-timeout ошибка → сразу exception без retry
- [ ] TC-006: MAX_RETRIES превышен → exception
- [ ] TC-007: Метод batch() обрабатывает запросы последовательно
- [ ] TC-008: Логи записываются в `simple_requests.jsonl`
- [ ] TC-009: Логи retry записываются в `simple_retries.jsonl`
- [ ] TC-010: Логи ошибок записываются в `simple_errors.jsonl`
- [ ] TC-011: Покрытие кода >80%
- [ ] TC-012: Нет реальных API вызовов (всё замокано)

## 6. Важные детали для Developer

### Специфичные риски

**Мокание Langchain клиентов:**
- Langchain клиенты (ChatAnthropic, ChatOpenAI) имеют сложные интерфейсы
- Нужно мокать именно метод `ainvoke()` (async)
- Mock должен возвращать объект с полем `content` и опционально `tool_calls`, `usage_metadata`
- Используй `AsyncMock` из `unittest.mock`, не обычный `Mock`

**Timeout ошибки:**
- Langchain использует httpx для HTTP запросов
- Timeout возвращается как `httpx.HTTPStatusError`
- У ошибки есть атрибут `response.status_code` (408 или 504)
- Нужно создать mock объект с этой структурой для тестов

**Константы retry:**
- MAX_RETRIES = 5 (захардкожено в классе)
- RETRY_DELAY_SECONDS = 1.0
- Эти константы нельзя менять через env — тесты должны проверять именно эти значения

**Логирование:**
- Логи пишутся в JSONL формат (одна JSON строка на запись)
- Используй `tempfile.TemporaryDirectory()` для тестов чтобы не засорять 04_logs/
- Проверяй что директория создаётся автоматически если не существует
- Проверяй формат JSON (валидация, наличие полей)

### Советы по тестированию

**Для теста retry:**
```python
# Делаем mock клиент который первый раз возвращает timeout, потом успех
mock_client = AsyncMock()
mock_client.ainvoke.side_effect = [
    timeout_error,  # Первый вызов
    timeout_error,  # Второй вызов
    success_response  # Третий вызов (успех)
]
```

**Для проверки логов:**
```python
# Читаем JSONL файл
with open(log_path) as f:
    logs = [json.loads(line) for line in f]

# Проверяем последнюю запись
assert logs[-1]["status"] == "success"
```

**Для проверки задержки retry:**
```python
# Мокаем asyncio.sleep чтобы не ждать реально
with patch('asyncio.sleep') as mock_sleep:
    await gateway.request(request)
    # Проверяем что sleep вызван 1 раз с 1.0
    mock_sleep.assert_called_once_with(1.0)
```

### Отличия от test_llm_gateway.py

- **Не тестируем очереди:** SimpleLLMGateway не имеет RequestQueue
- **Не тестируем батчинг:** batch() просто последовательные вызовы
- **Проще retry:** Только timeout, без сложной политики
- **Другие логи:** Отдельные файлы (`simple_*.jsonl`)

### Покрытие

**Целевые метрики:**
- Минимум: >80%
- Стремиться: >90%

**Проверка:**
```bash
pytest 02_src/gateway/tests/test_simple_gateway.py --cov=02_src/gateway/simple_llm_gateway --cov-report=term-missing
```

**Что точно нужно покрыть:**
- Все ветки retry логики (timeout vs не-timeout)
- Все пути логирования (success, retry, error, max_retries)
- Обработка неизвестных моделей
- Создание клиентов для разных провайдеров
