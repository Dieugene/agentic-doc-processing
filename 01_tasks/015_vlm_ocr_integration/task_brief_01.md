# Задача 015: VLM-OCR Module Integration Architecture

## Что нужно сделать

Разработать архитектурное решение и план интеграции существующего VLM-OCR модуля из проекта `05_a_reports_ETL_02/` в текущий проект `07_agentic-doc-processing/`.

## Зачем

В проекте `05_a_reports_ETL_02/` реализован **РАБОЧИЙ** VLM-OCR pipeline с:
- VLM Client (Gemini) с throttling, retry, backoff
- SGR Adapter с schema validation (Pydantic/JSON Schema)
- Hybrid Dialogue (Gemini + Qwen для числовых полей)
- Полный ETL pipeline

**Цель:** Максимально переиспользовать проверенные компоненты, адаптировать под контракты текущего проекта, сделать модуль универсальным.

## Контекст

### Исходный проект: `05_a_reports_ETL_02/`

**Ключевые компоненты:**

1. **VLMClient** (`03_src/worker_job/vlm_client.py`):
   - Обертка над GeminiRestClient
   - Throttling: `MIN_INTERVAL_S=0.6`
   - Retry logic: `MAX_RETRIES=3`, exponential backoff + jitter
   - Rate limiting: `MAX_CALLS_PER_RUN=50`
   - Логирование всех вызовов

2. **SGRAdapter** (`03_src/worker_job/sgr_adapter.py`):
   - Single-call SGR interface
   - Schema validation: Pydantic models или JSON Schema
   - Возврат: `FieldResult(value, status, reasoning, notes)`
   - Обработка ошибок валидации

3. **HybridDialogueManager** (`03_src/worker_job/hybrid_dialogue.py`):
   - Двухфазное извлечение (Block Discovery → Field Extraction)
   - Gemini (текстовые поля) + Qwen (числовые/ID)
   - Self-correction механизм
   - Tool calls: `ask_qwen(field_id, page_num, question_text)`

4. **Pipeline** (`03_src/worker_job/pipeline.py`):
   - Field processors (33 поля аудиторского заключения)
   - Google Sheets integration
   - Diff viewing с gold standard

### Текущий проект: `07_agentic-doc-processing/`

**Ожидаемый интерфейс** (из `02_src/processing/vlm_ocr_extractor.py`):

```python
class VLMOCRExtractor:
    def extract_full_document(self, images: List[bytes]) -> DocumentData:
        """Извлечь всё из документа за один вызов.

        Использует batch prompts:
        - "Верни весь текст с этих страниц"
        - "Опиши иерархическую структуру: заголовки и их уровни"
        - "Найди все таблицы, классифицируй (NUMERIC/TEXT_MATRIX)"

        Returns:
            DocumentData(text, structure, tables)
        """
```

**Ожидаемый формат ответа:**
```json
{
  "text": "Полный текст документа...",
  "structure": {
    "headers": [
      {"level": 1, "title": "1. Введение", "page": 1},
      {"level": 2, "title": "1.1. Актуальность", "page": 2}
    ]
  },
  "tables": [
    {
      "id": "table_1",
      "type": "NUMERIC" | "TEXT_MATRIX",
      "page": 3,
      "location": {"bbox": [x1,y1,x2,y2], "page": 3},
      "preview": "Описание таблицы"
    }
  ]
}
```

### Архитектурные документы

**Текущий проект:**
- `00_docs/architecture/overview.md` - базовая архитектура
- `00_docs/architecture/decision_003_vlm_ocr_integration.md` - ADR по VLM-OCR
- `00_docs/architecture/implementation_plan.md` - план реализации
- `02_src/processing/vlm_ocr_extractor.py` - текущий контракт
- `02_src/processing/mock_vlm_ocr.py` - заглушка

**Исходный проект:**
- `05_a_reports_ETL_02/00_docs/architecture.md` - архитектура pipeline
- `05_a_reports_ETL_02/03_src/worker_job/vlm_client.py` - VLM Client
- `05_a_reports_ETL_02/03_src/worker_job/sgr_adapter.py` - SGR Adapter
- `05_a_reports_ETL_02/03_src/worker_job/hybrid_dialogue.py` - Hybrid Dialogue

## Требования к решению

### 1. Компоненты для переиспользования

**Анализировать и рекомендовать:**
- Какие компоненты из `05_a_reports_ETL_02/` переиспользовать полностью?
- Что нужно адаптировать под наш контракт?
- Что убрать (специфично для аудиторских заключений)?

**Кандидаты:**
- `VLMClient` - throttling, retry, logging (универсальный)
- `SGRAdapter` - schema validation (адаптировать под DocumentData)
- `GeminiRestClient` - low-level Gemini API
- `QwenClient` - может быть полезен для таблиц

### 2. Адаптация контрактов

**Проблема:** Разные интерфейсы

**Исходный проект:**
```python
SGRAdapter.call(prompt, schema, images, history, tools) -> FieldResult
```

**Текущий проект:**
```python
VLMOCRExtractor.extract_full_document(images) -> DocumentData
# или вызовы с batch prompts:
extract(images, ["text", "structure", "tables"]) -> VLMOCRResponse
```

**Решения для проработки:**
- Как адаптировать SGRAdapter под batch prompts?
- Как трансформировать FieldResult в DocumentData?
- Нужно ли сохранять SGR interface или делать упрощенный wrapper?

### 3. Стратегия интеграции

**Варианты:**

**A. Прямая интеграция (копипаст):**
- Скопировать `VLMClient`, `SGRAdapter` в `02_src/processing/`
- Создать адаптер под наш контракт
- Плюсы: быстро, проверенный код
- Минусы: дублирование, сложнее обновлять

**B. Общий модуль (shared):**
- Создать `02_src/vlm_ocr/` для переиспользуемых компонентов
- Использовать в обоих проектах
- Плюсы: нет дубликации, проще обновлять
- Минусы: нужна синхронизация между проектами

**C. Библиотека (separate package):**
- Вынести в отдельный пакет
- Установить как зависимость в обоих проектах
- Плюсы: чистое разделение, versioning
- Минусы: overhead на управление пакетом

### 4. Зависимости

**Проанализировать зависимости исходного проекта:**
- Gemini API (already used in current project?)
- Pydantic (для schema validation)
- Google Sheets (НЕ нужно в текущем проекте)
- Google Drive (НЕ нужно в текущем проекте)

**Решить:**
- Какие зависимости добавить в `requirements.txt`?
- Какие убрать (специфично для ETL)?

### 5. Конфигурация

**Исходный проект использует:**
```python
MIN_INTERVAL_S = 0.6
MAX_RETRIES = 3
BACKOFF_BASE = 1.0
BACKOFF_JITTER = 0.3
MAX_CALLS_PER_RUN = 50
LOW_DPI = 110
```

**Решить:**
- Оставить эти константы или сделать конфигурируемыми?
- Добавить в `.env` или hardcoded?
- Нужен ли `VLMConfig` класс?

## Ожидаемые артефакты

1. **ADR (Architecture Decision Record):**
   - `00_docs/architecture/decision_005_vlm_ocr_integration.md`
   - Выбор стратегии интеграции (A/B/C)
   - Компоненты для переиспользования
   - Компоненты для адаптации
   - Зависимости
   - Конфигурация
   - Обоснование решений

2. **Схема интеграции (Mermaid diagram):**
   - Какие компоненты откуда берутся
   - Где они будут расположены
   - Как взаимодействуют
   - Адаптеры между контрактами

3. **Список изменений:**
   - Новые файлы для создания
   - Существующие файлы для изменения
   - Зависимости для добавления
   - Конфигурация (`.env`)

4. **Следующие шаги:**
   - Передача Analyst с четким ТЗ для реализации
   - Или передача Developer напрямую (если решение простое)

## Примечания для Architect

**Важно:**
- НЕ менять ничего в `05_a_reports_ETL_02/` (только читать)
- Создать решение для текущего проекта `07_agentic-doc-processing/`
- Учесть контракты из `vlm_ocr_extractor.py`
- Учесть ADR-003 (интеграция VLM-OCR)

**Ключевые вопросы для решения:**
1. Использовать ли VLMClient "как есть" или адаптировать?
2. Нужно ли сохранять SGR (structured generation) для нашей задачи?
3. Как обрабатывать batch prompts (текст/структура/таблицы)?
4. Что делать с HybridDialogue (Gemini + Qwen)?
5. Где расположить новые модули?

**Стандарты:**
- Следовать `00_docs/standards/architect/*`
- Создавать ADR по шаблону из `00_docs/standards/tech-lead/`
- Использовать Mermaid для диаграмм
- Append-only формат (не перезаписывать документы)

## Зависимости

- `00_docs/architecture/overview.md` - базовая архитектура
- `00_docs/architecture/decision_003_vlm_ocr_integration.md` - ADR-003
- `02_src/processing/vlm_ocr_extractor.py` - текущий контракт
- `05_a_reports_ETL_02/03_src/worker_job/*` - исходная реализация
- `05_a_reports_ETL_02/00_docs/architecture.md` - архитектура источника

## Следующие задачи

После принятия архитектурного решения:
- Analyst: Детальное ТЗ для реализации
- Developer: Реализация адаптера
- Tester: Тестирование интеграции
- Task 014: Pipeline Integration & Setup (с реальным VLM-OCR)
