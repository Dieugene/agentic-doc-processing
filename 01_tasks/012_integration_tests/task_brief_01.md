# Задача 012: Интеграционные тесты парсинга

## Что нужно сделать

Создать интеграционные тесты полного pipeline обработки документов (Итерация 2).

## Зачем

Интеграционные тесты проверяют корректность взаимодействия всех модулей Итерации 2. Без них нельзя гарантировать работоспособность системы.

## Acceptance Criteria

- [ ] AC-001: Тест полного pipeline (file → DocumentSkeleton)
- [ ] AC-002: Тест для DOCX файла
- [ ] AC-003: Тест для Excel файла
- [ ] AC-004: Тест для PDF файла
- [ ] AC-005: Тест с NUMERIC таблицами
- [ ] AC-006: Тест с TEXT_MATRIX таблицами
- [ ] AC-007: Проверка сохранения/загрузки через FileStorage
- [ ] AC-008: Fixture'ы для всех тестовых файлов

## Контекст

**Тестируемый pipeline:**

```
file.docx / file.xlsx / file.pdf
  ↓
Converter (→ PDF, если нужен)
  ↓
Renderer (→ PNG)
  ↓
VLM-OCR Extractor (→ DocumentData)
  ↓
Skeleton Builder (→ DocumentSkeleton)
  ↓
FileStorage (сохранение)
  ↓
FileStorage (загрузка для проверки)
```

**Интерфейсы и контракты:**

```python
# ============================================
# Тестовый DocumentProcessor
# ============================================

class DocumentProcessor:
    """
    Оркестратор полного pipeline.
    Не входит в scope задач 006-011, а создаётся в задаче 032 (Pipeline Orchestrator).
    """

    def __init__(
        self,
        converter: Converter,
        renderer: Renderer,
        vlm_extractor: VLMOCRExtractor,
        skeleton_builder: SkeletonBuilder,
        storage: FileStorage
    ):
        self.converter = converter
        self.renderer = renderer
        self.vlm_extractor = vlm_extractor
        self.skeleton_builder = skeleton_builder
        self.storage = storage

    async def process_document(
        self,
        file_path: str
    ) -> str:
        """
        Полный цикл обработки документа.

        Returns:
            document_id
        """
        # 1. Определить тип файла
        file_type = await self.converter.detect_file_type(file_path)

        # 2. Конвертировать в PDF (если нужно)
        if file_type != FileType.PDF:
            pdf_path = await self.converter.convert_to_pdf(file_path, file_type)
        else:
            pdf_path = file_path

        # 3. Рендерить в PNG
        images = await self.renderer.render_pdf_to_images(pdf_path)

        # 4. Излечь данные через VLM-OCR
        document_data = self.vlm_extractor.extract_full_document(images)

        # 5. Построить скелет
        skeleton = await self.skeleton_builder.build_skeleton(
            document_id=self._generate_id(),
            document_data=document_data
        )

        # 6. Сохранить
        await self.storage.save_skeleton(skeleton.document_id, skeleton)

        return skeleton.document_id

    async def _generate_id(self) -> str:
        """Генерировать уникальный ID документа"""
        pass
```

**Структура теста:**

```python
# ============================================
# Тест 1: Полный pipeline с DOCX
# ============================================

async def test_full_pipeline_docx():
    """
    Тест полного pipeline для DOCX файла.

    Сценарий:
    1. Загрузить sample.docx
    2. Конвертировать в PDF
    3. Рендерить в PNG
    4. Излечь данные через VLM-OCR (mock)
    5. Построить DocumentSkeleton
    6. Сохранить в FileStorage

    Проверки:
    - Конвертация успешна
    - PNG созданы
    - DocumentSkeleton содержит правильное количество Node
    - Иерархия заголовков корректна
    - Таблицы классифицированы
    - Файл сохранён в FileStorage
    """
    pass


# ============================================
# Тест 2: Excel с NUMERIC таблицами
# ============================================

async def test_xlsx_with_numeric_tables():
    """
    Тест для Excel файла с числовыми таблицами.

    Сценарий:
    1. Загрузить sample.xlsx (2 листа)
    2. Лист 1: текст + NUMERIC таблица
    3. Лист 2: только NUMERIC таблицы

    Проверки:
    - Каждый лист = отдельные страницы PDF
    - NUMERIC таблицы → node.table_data (pandas-compatible)
    - Можно восстановить DataFrame для вычислений
    """
    pass


# ============================================
# Тест 3: PDF с TEXT_MATRIX таблицами
# ============================================

async def test_pdf_with_text_matrix_tables():
    """
    Тест для PDF с текстовыми таблицами.

    Сценарий:
    1. Загрузить sample.pdf
    2. VLM-OCR находит TEXT_MATRIX таблицы
    3. Таблицы прикреплены к правильным Node

    Проверки:
    - Таблицы найдены VLM-OCR
    - Тип корректен (TEXT_MATRIX)
    - Прикреплены к разделам по контенту
    """
    pass
```

**Структура проекта:**

```
02_src/
├── processing/
│   └── tests/
│       ├── integration/
│       │   ├── test_full_pipeline.py
│       │   ├── test_docx_pipeline.py
│       │   ├── test_xlsx_pipeline.py
│       │   ├── test_pdf_pipeline.py
│       │   └── test_tables.py
│       └── fixtures/
│           ├── sample.docx
│           ├── sample.xlsx
│           ├── sample.pdf
│           └── expected_results/
│               ├── docx_skeleton.json
│               ├── xlsx_skeleton.json
│               └── pdf_skeleton.json
```

**Fixture'ы для тестов:**

```json
// expected_results/docx_skeleton.json
{
  "expected_nodes": 5,
  "expected_hierarchy": {
    "root": ["section_1", "section_2"],
    "section_1": ["section_1_1", "section_1_2"]
  },
  "expected_tables": [
    {"id": "table_1", "type": "NUMERIC", "attached_to": "section_1"}
  ]
}
```

## Примечания для Analyst

**Важно:**
- Это ИНТЕГРАЦИОННЫЕ тесты — проверяют взаимодействие модулей
- MockVLMOCR используется для изоляции от реального VLM-OCR
- Можно создавать временные файлы и удалять через teardown

**Ключевые решения:**
1. Использовать pytest или unittest? (pytest — асинхронные тесты лучше)
2. Как организовать fixture'ы? (отдельная папка)
3. Нужно ли сохранять PNG для отладки? (нет, только логировать)

**Пример pytest теста:**

```python
import pytest

@pytest.mark.asyncio
async def test_full_pipeline_docx():
    processor = DocumentProcessor(
        converter=Converter(),
        renderer=Renderer(),
        vlm_extractor=MockVLMOCR(),  # mock
        skeleton_builder=SkeletonBuilder(),
        storage=FileStorage("data/")
    )

    doc_id = await processor.process_document("fixtures/sample.docx")

    # Проверки
    skeleton = await processor.storage.load_skeleton(doc_id)
    assert skeleton is not None
    assert len(await skeleton.get_all_nodes()) > 0
```

## Зависимости

Все задачи Итерации 2:
- 006: Document Skeleton
- 007: File Storage
- 008: VLM-OCR Extractor
- 009: Converter
- 010: Renderer
- 011: Skeleton Builder

## Следующие задачи

После завершения:
- Итерация 3: Navigation Index и Taxonomy
