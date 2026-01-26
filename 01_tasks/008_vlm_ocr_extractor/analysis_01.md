# Технический план: VLM-OCR Extractor (обёртка над модулем)

**Дата:** 2025-01-23
**Версия:** 1.0

---

## 1. Анализ задачи

Задача: Создать обёртку над существующим VLM-OCR модулем. VLM-OCR — это Python library с extractive API, который принимает PNG-изображения страниц и extractive prompts, возвращает структурированные результаты.

Ключевая особенность VLM-OCR: **batch prompts** — один вызов может возвращать результаты для нескольких вопросов одновременно.

Цель обёртки: Унифицированный API для остальной системы (`extract_full_document()`) + логирование + обработка ошибок.

---

## 2. Текущее состояние

### Существующие модули (релевантные)

**Нет** — это первая задача в модуле processing.

### Контракт VLM-OCR (существующий PoC)

```python
# Существующий VLM-OCR модуль предоставляет:
vlm_ocr.extract(
    images: List[bytes],    # PNG-изображения страниц
    prompts: List[str]      # extractive prompts
) -> VLMOCRResponse

# VLMOCRResponse:
#   success: bool
#   results: List[ExtractionResult]

# ExtractionResult:
#   prompt: str
#   data: Dict[str, Any]
```

### Зависимости

- Зависимость от существующего VLM-OCR модуля (external library)
- Для v1.0 кэширование не требуется (VLM-OCR сам кэширует)

---

## 3. Предлагаемое решение

### 3.1. Общий подход

**Обёртка, не реализация:** VLMOCRExtractor — это фасад над существующим модулем. Он не реализует VLM-OCR, а предоставляет удобный интерфейс для системы.

**Batch prompts оптимизация:** Один вызов VLM-OCR с тремя промптами (текст, структура, таблицы) вместо трёх отдельных вызовов.

**Обработка ошибок:** При `response.success == False` — логировать детали и пробрасывать исключение.

### 3.2. Компоненты

#### VLMOCRExtractor (основной класс)

- **Назначение:** Обёртка над VLM-OCR модулем для удобного API системы
- **Интерфейс:**
  - `__init__(vlm_ocr_module)` — принимает существующий модуль
  - `extract_full_document(images: List[bytes]) -> DocumentData` — извлечь всё за один вызов
- **Зависимости:** Существующий VLM-OCR модуль
- **Логика:**
  1. Формирует batch prompts (текст, структура, таблицы)
  2. Вызывает `vlm_ocr.extract(images, prompts)`
  3. Проверяет `response.success`
  4. Агрегирует результаты в `DocumentData`
  5. Логирует запрос/ответ

#### MockVLMOCR (для тестов)

- **Назначение:** Mock VLM-OCR модуля для unit/интеграционных тестов
- **Интерфейс:** Совпадает с VLM-OCR (`extract(images, prompts) -> VLMOCRResponse`)
- **Логика:**
  - Возвращает предопределённые ответы из fixtures
  - Детерминированный (одинаковый вход → одинаковый выход)
  - Поддерживает сценарии успеха/ошибки

#### DocumentData (структура данных)

- **Назначение:** Результат извлечения полного документа
- **Поля:**
  - `text: str` — полный текст документа
  - `structure: Dict[str, Any]` — иерархия заголовков
  - `tables: List[Dict[str, Any]]` — классифицированные таблицы

### 3.3. Структуры данных

```python
from typing import List, Dict, Any
from dataclasses import dataclass

# VLM-OCR контракты (существующий модуль)
@dataclass
class VLMOCRResponse:
    success: bool
    results: List['ExtractionResult']

@dataclass
class ExtractionResult:
    prompt: str
    data: Dict[str, Any]

# Мои структуры
@dataclass
class DocumentData:
    text: str
    structure: Dict[str, Any]
    tables: List[Dict[str, Any]]

# Пример structure:
# {
#   "headers": [
#     {"level": 1, "title": "1. Раздел", "page": 1},
#     {"level": 2, "title": "1.1. Подраздел", "page": 2}
#   ]
# }

# Пример таблицы:
# {
#   "id": "table_1",
#   "type": "NUMERIC" | "TEXT_MATRIX",
#   "page": 3,
#   "location": {"bbox": [...], "page": 3},
#   "preview": "Краткое описание"
# }
```

### 3.4. Ключевые алгоритмы

#### extract_full_document()

1. Принять список PNG-изображений страниц
2. Сформировать batch prompts:
   - "Верни весь текст с этих страниц"
   - "Опиши иерархическую структуру: заголовки и их уровни"
   - "Найди все таблицы, классифицируй (NUMERIC/TEXT_MATRIX)"
3. Вызвать `self.vlm.extract(images, prompts)`
4. Проверить `response.success`:
   - Если False → логировать ошибку + пробросить исключение
5. Агрегировать результаты:
   - `results[0].data["text"]` → `DocumentData.text`
   - `results[1].data["structure"]` → `DocumentData.structure`
   - `results[2].data["tables"]` → `DocumentData.tables`
6. Логировать запрос/ответ (JSON)
7. Вернуть `DocumentData`

#### Обработка ошибок

- **Типы ошибок:** VLM-OCR возвращает `success: False` при проблемах
- **Действия:**
  1. Логировать в `04_logs/vlm_ocr/errors.json`: timestamp, входные параметры, response
  2. Пробросить исключение `VLMExtractionException` с деталями

#### Логирование

- **Уровень:** INFO для успешных запросов, ERROR для ошибок
- **Формат:** JSON с timestamp
- **Поля лога запроса:**
  - `timestamp`
  - `num_images`
  - `prompts`
  - `success`
  - `num_results`
  - `error` (если есть)
- **Расположение:** `04_logs/vlm_ocr/requests.json`

### 3.5. Структура проекта

```
02_src/
├── processing/
│   ├── __init__.py
│   ├── vlm_ocr_extractor.py     # VLMOCRExtractor, DocumentData
│   ├── mock_vlm_ocr.py          # MockVLMOCR для тестов
│   └── tests/
│       ├── __init__.py
│       ├── test_vlm_ocr_extractor.py
│       └── fixtures/
│           └── vlm_response_samples.json

04_logs/
└── vlm_ocr/
    └── requests.json            # Логи запросов к VLM-OCR
```

---

## 4. План реализации

### Шаг 1: Создать структуры данных
- `vlm_ocr_extractor.py`: DocumentData, VLMExtractionException

### Шаг 2: Реализовать MockVLMOCR
- `mock_vlm_ocr.py`: MockVLMOCR с fixture'ами

### Шаг 3: Реализовать VLMOCRExtractor
- `__init__(vlm_ocr_module)`
- `extract_full_document(images)` с batch prompts
- Логирование запросов/ответов
- Обработка ошибок

### Шаг 4: Создать fixture'ы для тестов
- `fixtures/vlm_response_samples.json`: примеры ответов

### Шаг 5: Unit тесты
- `test_vlm_ocr_extractor.py`: тесты для VLMOCRExtractor с MockVLMOCR
- Тест успеха, тест ошибки, тест логирования

---

## 5. Технические критерии приемки

- [ ] TC-001: VLMOCRExtractor реализован с методом `extract_full_document()`
- [ ] TC-002: Batch prompts (один VLM-вызов, три результата)
- [ ] TC-003: MockVLMOCR возвращает детерминированные ответы из fixtures
- [ ] TC-004: Unit тесты покрывают сценарии успеха/ошибки
- [ ] TC-005: Логи пишутся в `04_logs/vlm_ocr/requests.json` (JSON формат)
- [ ] TC-006: При `success=False` логируется ошибка и пробрасывается исключение
- [ ] TC-007: DocumentData содержит текст, структуру, таблицы

---

## 6. Важные детали для Developer

### Специфичные риски

1. **Индексация results в VLMOCRResponse:** Результаты приходят в том же порядке что prompts. Если VLM-OCR изменит порядок — код сломается. **Решение:** маппить по полю `prompt` вместо индекса.

2. **Размер images:** VLM-OCR может работать со скользящим окном (не все страницы одномоментно). Для v1.0 предполагаем что VLM-OCR сам обрабатывает большие документы. Если нет — потребуется добавить логику sliding window в VLMOCRExtractor.

3. **Логирование больших данных:** Не логировать сами `images` (тяжёлые). Логировать только метаданные: `num_images`, промпты, статус, количество результатов.

### Контракт VLM-OCR

**Важно:** VLM-OCR модуль уже существует. Не реализовывать его — только обёртка.

Предполагаемый API (если отличается — скорректировать):
```python
vlm_ocr.extract(images: List[bytes], prompts: List[str]) -> VLMOCRResponse
```

### Fixture'ы для VLM responses

Создать `vlm_response_samples.json` с примерами:
- `success_response`: полный успешный ответ
- `error_response`: ответ с `success: False`

Формат:
```json
{
  "success_response": {
    "success": true,
    "results": [
      {
        "prompt": "Верни весь текст с этих страниц",
        "data": {"text": "Пример текста..."}
      },
      {
        "prompt": "Опиши иерархическую структуру...",
        "data": {"structure": {"headers": [...]}}
      },
      {
        "prompt": "Найди все таблицы...",
        "data": {"tables": [...]}
      }
    ]
  }
}
```

### Кэширование

Для v1.0 **не реализовывать** кэширование в VLMOCRExtractor. Предполагаем что VLM-OCR модуль сам кэширует результаты.

### Dependencies

В `requirements.txt` добавить зависимости только если нужно (для VLM-OCR module — уже должен быть установлен).

### Стиль кода

- Использовать `dataclasses` для структур данных
- Логирование через `logging` модуль
- Type hints для всех методов
- Docstrings для публичных методов

---

## 7. Ключевые решения (проработка из task_brief)

### Решение 1: Обработка ошибок VLM-OCR

**Выбрано:** Логировать в `04_logs/vlm_ocr/` + пробрасывать исключение.

**Обоснование:**
- Логи нужны для отладки и аудита (какой документ, какой запрос, почему упал)
- Исключение нужно чтобы вызывающий код мог обработать ошибку (retry, fallback)
- JSON формат удобен для парсинга и анализа

**Детали:**
- Создать кастомное исключение `VLMExtractionException`
- Логировать: timestamp, num_images, prompts, error_details из response
- Файл: `04_logs/vlm_ocr/errors.json` или отдельная секция в `requests.json`

### Решение 2: Логирование запросов/ответов

**Выбрано:** JSON логи с timestamps в `04_logs/vlm_ocr/requests.json`.

**Обоснование:**
- Observability — видеть что и когда запрашивали
- Анализ производительности (сколько времени занимает)
- Отладка — понять что пошло не так

**Что логировать:**
- `timestamp`
- `num_images` (не сами изображения!)
- `prompts`
- `success`
- `num_results`
- `error` (если есть)

**Что НЕ логировать:**
- Сами `images` (тяжело, не нужно для отладки)
- Полный `text` из results (может быть огромным)

### Решение 3: Кэширование результатов

**Выбрано:** Не реализовывать для v1.0.

**Обоснование:**
- VLM-OCR модуль сам кэширует результаты
- Для v1.0 важно проверить базовый функционал
- Кэширование можно добавить позже если нужно

**Будущее:** Если потребуется:
- Добавить `cache_dir` в `__init__`
- Вычислять hash от images + prompts
- Сохранять/загружать результаты из файлов

### Решение 4: Маппинг результатов

**Риск:** Индексация `results[0]`, `results[1]` сломается если порядок изменится.

**Выбрано:** Маппить по полю `prompt` вместо индекса.

**Обоснование:**
- Более robust к изменениям
- Явно указывает какой результат какому prompt соответствует

**Реализация:**
```python
# НЕ так:
text = response.results[0].data["text"]

# А так:
text_result = next(r for r in response.results if "текст" in r.prompt.lower())
text = text_result.data["text"]
```

Или создать helper метод `_find_result_by_prompt_keywords(response, keywords)`.
