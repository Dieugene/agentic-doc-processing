# Review отчет: LLM Gateway - Queue и Batch Executor

## Общая оценка

**Статус:** Требует доработки

**Краткий вывод:** Реализация соответствует техническому плану, но обнаружена критическая проблема с поддержкой моделей CLAUDE_SONNET и CLAUDE_OPUS, а также неиспользуемый fixtures файл.

## Проверка соответствия ТЗ

**Технические критерии из analysis.md:**
- [x] TC-001: RequestQueue накапливает батчи до batch_size или batch_timeout - ✅ Выполнено
- [ ] TC-002: BatchExecutor создаёт корректный langchain клиент для каждого провайдера - ❌ Проблема (см. ниже)
- [x] TC-003: BatchExecutor.execute_batch() конвертирует запросы и раздаёт результаты в futures - ✅ Выполнено
- [x] TC-004: LLMGateway.start() запускает фоновые обработчики для всех моделей - ✅ Выполнено
- [x] TC-005: LLMGateway.request() возвращает корректный LLMResponse через Future - ✅ Выполнено
- [x] TC-006: LLMGateway.batch() группирует запросы по моделям - ✅ Выполнено
- [x] TC-007: Логи записываются в JSON Lines формат в 04_logs/gateway/ - ✅ Выполнено
- [x] TC-008: MockLLMGateway реализован без langchain зависимостей - ✅ Выполнено
- [ ] TC-009: Все unit тесты проходят - ❌ 6 из 15 тестов падают (см. ниже)
- [?] TC-010: Код покрывает >80% по coverage - ⚠️ Не проверено

**Acceptance Criteria из task_brief:**
- [x] AC-001: RequestQueue реализован для каждой модели - ✅ Выполнено
- [x] AC-002: BatchExecutor накапливает запросы и отправляет батчами - ✅ Выполнено
- [x] AC-003: LLMGateway.request() возвращает Future/Promise - ✅ Выполнено
- [x] AC-004: LLMGateway.batch() для групповой отправки - ✅ Выполнено
- [x] AC-005: MockLLMGateway для тестов - ✅ Выполнено
- [x] AC-006: Unit тесты для всех методов - ✅ Выполнено
- [x] AC-007: Логи в 04_logs/gateway/ - ✅ Выполнено

## Проблемы

### Проблема 1: Зависимости langchain не установлены

**Файл:** requirements.txt, виртуальное окружение

**Описание:** Зависимости добавлены в requirements.txt, но не установлены в виртуальном окружении. Тесты для BatchExecutor и LLMGateway падают с `ModuleNotFoundError: No module named 'langchain_anthropic'`. 6 из 15 тестов не проходят.

**Серьезность:** Высокая

### Проблема 2: Missing handler for CLAUDE_SONNET and CLAUDE_OPUS

**Файл:** `02_src/gateway/llm_gateway.py:101-106`

**Описание:** В методе `_create_client()` есть условие только для `ModelProvider.CLAUDE_HAIKU`, но не для `CLAUDE_SONNET` и `CLAUDE_OPUS`. При попытке использовать эти модели будет выброшено `ValueError("Unsupported provider")`.

```python
if provider == ModelProvider.CLAUDE_HAIKU:
    return ChatAnthropic(...)
elif provider in [ModelProvider.GPT_4O_MINI, ModelProvider.GPT_4O]:
    return ChatOpenAI(...)
else:
    raise ValueError(f"Unsupported provider: {provider}")
```

**Серьезность:** Критическая

### Проблема 3: Неиспользуемый fixtures файл

**Файл:** `02_src/gateway/tests/fixtures/sample_responses.json`

**Описание:** Файл создан согласно техническому плану, но нигде не используется. В `MockLLMGateway` нет загрузки данных из этого файла, все mock ответы создаются программно.

**Серьезность:** Низкая (но мертвый код)

## Положительные моменты

- Корректная реализация батчинга с timeout в `RequestQueue.get_batch()`
- Правильная обработка `future.done()` перед `set_result()` / `set_exception()` предотвращает double-set ошибок
- Чистая структура модуля с разделением на models.py и llm_gateway.py
- Полнота покрытия тестами основных сценариев (put/get_batch, execute_batch, request/batch)
- MockLLMGateway полностью независим от langchain зависимостей

## Решение

**Действие:** Вернуть Developer

**Обоснование:** Обнаружены проблемы реализации:
1. **Высокая:** Зависимости langchain не установлены в виртуальном окружении — нужно выполнить `.venv/Scripts/pip install -r requirements.txt` (Windows) или аналогично для Linux/Mac
2. **Критическая:** Отсутствует обработка CLAUDE_SONNET и CLAUDE_OPUS в `_create_client()` — эти модели будут выбрасывать "Unsupported provider"
3. **Низкая:** Fixtures файл `sample_responses.json` создан, но не используется

**Примечание:** Тесты падают на import, не на API вызовы — API ключи не требуются для запуска тестов.
