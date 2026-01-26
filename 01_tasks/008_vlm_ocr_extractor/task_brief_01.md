# Задача 008: VLM-OCR Extractor (обёртка над модулем)

## Что нужно сделать

Реализовать обёртку над существующим VLM-OCR модулем для извлечения данных из документов.

## Зачем

VLM-OCR — основной экстрактор для всех форматов. Обёртка обеспечивает унифицированный API для системы и интеграцию с остальными модулями.

## Acceptance Criteria

- [ ] AC-001: VLMOCRExtractor реализован как обёртка над существующим модулем
- [ ] AC-002: extract_full_document() с batch prompts (текст, структура, таблицы)
- [ ] AC-003: MockVLMOCR для тестирования (детерминированные ответы)
- [ ] AC-004: Unit тесты с fixture'ами
- [ ] AC-005: Логи в 04_logs/vlm_ocr/

## Контекст

**ADR-003: Интеграция VLM-OCR модуля**

VLM-OCR — существующий PoC модуль. Принцип работы:
- Вход: PNG-изображения страниц + extractive prompts
- Выход: результаты extraction согласно prompts
- Ключевая особенность: batch prompts (один вызов — несколько результатов)

**Интерфейсы и контракты:**

```python
from typing import List, Dict, Any, Union

# ============================================
# VLM-OCR Module API (существующий PoC)
# ============================================

class VLMOCRRequest:
    images: List[bytes]    # PNG-изображения страниц
    prompts: List[str]      # extractive prompts

class VLMOCRResponse:
    success: bool
    results: List['ExtractionResult']

class ExtractionResult:
    prompt: str                  # какой prompt был
    data: Dict[str, Any]         # результат extraction

# Существующий модуль предоставляет метод:
vlm_ocr.extract(images: List[bytes], prompts: List[str]) -> VLMOCRResponse


# ============================================
# Мои структуры данных (для VLM-OCR)
# ============================================

class DocumentData:
    """Результат извлечения полного документа"""
    text: str                      # полный текст документа
    structure: Dict[str, Any]       # иерархия заголовков
    tables: List[Dict[str, Any]]    # классифицированные таблицы

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


# ============================================
# Мой код: VLMOCRExtractor (обёртка)
# ============================================

class VLMOCRExtractor:
    """
    Обёртка над VLM-OCR модулем.

    Не реализует VLM-OCR, а предоставляет удобный API
    для остальной системы.
    """

    def __init__(self, vlm_ocr_module):
        """
        Инициализация с существующим VLM-OCR модулем.

        Args:
            vlm_ocr_module: существующий PoC модуль с методом extract()
        """
        self.vlm = vlm_ocr_module

    def extract_full_document(self, images: List[bytes]) -> DocumentData:
        """
        Извлечь всё из документа за один вызов.

        Batch prompts для оптимизации:
        - "Верни весь текст с этих страниц"
        - "Опиши иерархическую структуру: заголовки и их уровни"
        - "Найди все таблицы, классифицируй (NUMERIC/TEXT_MATRIX)"

        Args:
            images: Список PNG-изображений страниц

        Returns:
            DocumentData с текстом, структурой и таблицами
        """
        # Batch prompts - один VLM вызов, три результата
        response = self.vlm.extract(
            images=images,
            prompts=[
                "Верни весь текст с этих страниц",
                "Опиши иерархическую структуру: заголовки и их уровни",
                "Найди все таблицы, классифицируй (NUMERIC/TEXT_MATRIX)"
            ]
        )

        if not response.success:
            raise Exception(f"VLM-OCR extraction failed: {response}")

        # Агрегируем результаты
        return DocumentData(
            text=response.results[0].data["text"],
            structure=response.results[1].data["structure"],
            tables=response.results[2].data["tables"]
        )
```

**Структура проекта:**

```
02_src/
├── processing/
│   ├── __init__.py
│   ├── vlm_ocr_extractor.py
│   ├── mock_vlm_ocr.py          # MockVLMOCR для тестов
│   └── tests/
│       ├── test_vlm_ocr_extractor.py
│       └── fixtures/
│           └── vlm_response_samples.json
04_logs/
└── vlm_ocr/
    └── (логи запросов к VLM-OCR)
```

**MockVLMOCR для тестов:**

```python
class MockVLMOCR:
    """Mock для тестирования VLM-OCR"""

    def extract(self, images: List[bytes], prompts: List[str]) -> VLMOCRResponse:
        # Возвратить предопределённые ответы из fixtures
        return VLMOCRResponse(
            success=True,
            results=[
                ExtractionResult(
                    prompt=prompts[0],
                    data={"text": "Тестовый текст документа..."}
                ),
                ExtractionResult(
                    prompt=prompts[1],
                    data={"structure": {"headers": [...]}}
                ),
                ExtractionResult(
                    prompt=prompts[2],
                    data={"tables": [...]}
                )
            ]
        )
```

## Примечания для Analyst

**Важно:**
- VLM-OCR модуль уже существует (PoC) — не нужно его реализовывать
- Задача — создать обёртку с удобным API
- VLM-OCR может работать со скользящим окном (не все страницы одномом) — это внутри модуля

**Ключевые решения:**
1. Как обрабатывать ошибки VLM-OCR? (логировать, пробрасывать исключение)
2. Как логировать запросы/ответы? (JSON логи с timestamps)
3. Нужно ли кэшировать результаты? (для v1.0 — нет, VLM-OCR сам кэширует)

## Зависимости

- Задача 006: DocumentSkeleton (для понимания формата DocumentData)
- Задача 004: SGR Integration (не обязательно, но полезно понимать паттерны)

## Следующие задачи

После завершения:
- Задача 011: Skeleton Builder (использует VLMOCRExtractor)
- Задача 017: Table Classifier (использует VLMOCRExtractor)

## Другие ссылки

- VLM-OCR документация: (внутренняя документация PoC модуля)
