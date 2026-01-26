# Задача 011: Skeleton Builder (агрегация VLM-OCR результатов)

## Что нужно сделать

Реализовать агрегацию результатов VLM-OCR в DocumentSkeleton.

## Зачем

Skeleton Builder является связующим звеном между VLM-OCR (экстрактор) и DocumentSkeleton (структура данных). Преобразует неструктурированные данные в иерархический скелет.

## Acceptance Criteria

- [ ] AC-001: SkeletonBuilder реализован
- [ ] AC-002: build_skeleton() создаёт DocumentSkeleton из DocumentData
- [ ] AC-003: Иерархия заголовков → дерево Node
- [ ] AC-004: Таблицы интегрируются в Node.table_data
- [ ] AC-005: Unit тесты с fixture'ами
- [ ] AC-006: Интеграционные тесты с VLM-OCR mock

## Контекст

**ADR:**
- `00_docs/architecture/decision_001_document_formats.md`
- `00_docs/architecture/decision_003_vlm_ocr_integration.md`

**Implementation Plan:**
- `00_docs/architecture/implementation_plan.md` - Iteration 2

**Интерфейсы:**

```python
class SkeletonBuilder:
    """Агрегация результатов VLM-OCR в DocumentSkeleton"""

    async def build_skeleton(
        self,
        document_data: DocumentData,
        document_id: str
    ) -> DocumentSkeleton:
        """
        Построить DocumentSkeleton из данных VLM-OCR.

        document_data содержит:
        - text: полный текст документа
        - structure: иерархия заголовков
        - tables: список классифицированных таблиц

        Возвращает DocumentSkeleton с деревом Node.
        """
        pass

    def _build_node_tree(self, structure: Dict) -> Node:
        """Построить дерево Node из иерархии заголовков"""
        pass

    def _attach_tables(self, skeleton: DocumentSkeleton, tables: List):
        """Прикрепить таблицы к соответствующим Node"""
        pass
```

**VLM-OCR выход (DocumentData):**

```python
# Пример ожидаемого формата от VLM-OCR
DocumentData {
    text: "Полный текст документа...",
    structure: {
        "headers": [
            {"level": 1, "title": "1. Раздел", "page": 1},
            {"level": 2, "title": "1.1. Подраздел", "page": 2},
            ...
        ]
    },
    tables: [
        {"id": "table_1", "type": "NUMERIC", "page": 3, "location": {...}},
        {"id": "table_2", "type": "TEXT_MATRIX", "page": 5, "location": {...}}
    ]
}
```

**Структура проекта:**

```
02_src/
├── processing/
│   ├── __init__.py
│   ├── skeleton_builder.py
│   └── tests/
│       ├── test_skeleton_builder.py
│       └── fixtures/
│           ├── vlm_response_sample.json
│           └── expected_skeleton.json
```

## Примечания для Analyst

**Ключевые решения:**
1. Как обрабатывать разрывы в нумерации заголовков?
2. Как детектировать parent-child отношения?
3. Как прикреплять таблицы к разделам? (по странице, по контенту)

## Зависимости

- Задача 006: DocumentSkeleton (структуры данных)
- Задача 008: VLM-OCR Extractor (предоставляет DocumentData)

## Следующие задачи

После завершения:
- Задача 012: Интеграционные тесты полного pipeline
