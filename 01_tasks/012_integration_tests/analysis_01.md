# Технический план: Интеграционные тесты парсинга (Итерация 2)

## 1. Анализ задачи

Необходимо создать интеграционные тесты полного pipeline обработки документов для Итерации 2. Тесты должны проверять корректность взаимодействия всех модулей: Converter, Renderer, VLM-OCR Extractor, Skeleton Builder, File Storage.

Тестируемый pipeline:
```
file.docx / file.xlsx / file.pdf
  → Converter (→ PDF, если нужен)
  → Renderer (→ PNG)
  → Mock VLM-OCR Extractor (→ DocumentData)
  → Skeleton Builder (→ DocumentSkeleton)
  → FileStorage (сохранение)
  → FileStorage (загрузка для проверки)
```

Ключевая особенность: используется MockVLMOCR для изоляции от реального VLM-OCR API.

## 2. Текущее состояние

### Существующие модули
- **DocumentSkeleton** (`02_src/document/skeleton.py`): Полностью реализован, содержит Node, PageRange, DocumentSkeleton
- **Converter** (`02_src/processing/converter.py`): Поддерживает DOCX, XLSX, TXT → PDF с использованием fpdf2, python-docx, openpyxl
- **Renderer** (`02_src/processing/renderer.py`): PDF → PNG через pdf2image, настраиваемый DPI
- **MockVLMOCR** (`02_src/processing/mock_vlm_ocr.py`): Детерминированный mock с предопределенными ответами
- **VLMOCRExtractor** (`02_src/processing/vlm_ocr_extractor.py`): Обертка с batch prompts, возвращает DocumentData
- **SkeletonBuilder** (`02_src/processing/skeleton_builder.py`): Агрегация DocumentData → DocumentSkeleton
- **FileStorage** (`02_src/storage/file_storage.py`): JSON-персистентность скелетов

### Существующие тесты
- Unit тесты для каждого модуля в `02_src/*/tests/test_*.py`
- Fixture'ы для создания тестовых документов: `02_src/processing/tests/fixtures/create_fixtures.py`

### Стандарты тестирования
- Используется pytest с pytest-asyncio для асинхронных тестов
- Mock объекты из `mock_vlm_ocr.py` уже используются в unit тестах

## 3. Предлагаемое решение

### 3.1. Общий подход

Создать **DocumentProcessor** - тестовый оркестратор полного pipeline. Этот класс НЕ входит в scope задач 006-011 (он будет создан позже в задаче 032), но для интеграционных тестов нужен сейчас.

Тесты будут:
1. Проверять полный pipeline для каждого формата (DOCX, XLSX, PDF)
2. Проверять корректность обработки таблиц (NUMERIC, TEXT_MATRIX)
3. Проверять сохранение/загрузку через FileStorage
4. Использовать fixture'ы с предопределенными ожидаемыми результатами

### 3.2. Компоненты

#### DocumentProcessor (тестовый оркестратор)
- **Назначение:** Оркестратор полного pipeline для интеграционных тестов
- **Интерфейс:**
  ```python
  class DocumentProcessor:
      def __init__(
          self,
          converter: Converter,
          renderer: Renderer,
          vlm_extractor: VLMOCRExtractor,
          skeleton_builder: SkeletonBuilder,
          storage: FileStorage
      )

      async def process_document(self, file_path: str) -> str:
          """Полный цикл обработки. Returns: document_id"""
  ```
- **Логика:**
  1. Определить тип файла через `converter.detect_file_type()`
  2. Конвертировать в PDF если нужно (DOCX/XLSX)
  3. Рендерить PDF → PNG
  4. Извлечь данные через MockVLMOCR
  5. Построить DocumentSkeleton
  6. Сохранить в FileStorage
  7. Вернуть document_id
- **Зависимости:** Converter, Renderer, VLMOCRExtractor, SkeletonBuilder, FileStorage

#### Тестовые файлы (fixtures)
- **sample.docx**: Простой документ с 2-3 секциями и одной NUMERIC таблицей
- **sample.xlsx**: 2 листа - один с текстом + NUMERIC, второй только NUMERIC таблицы
- **sample.pdf**: Документ с TEXT_MATRIX таблицами
- **expected_results/**: JSON файлы с ожидаемой структурой DocumentSkeleton для каждого файла

#### Структура expected_results JSON
```json
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

### 3.3. Структуры данных

Все структуры данных уже определены в существующих модулях:
- `DocumentSkeleton`, `Node`, `NodeType` из `document.skeleton`
- `DocumentData` из `processing.vlm_ocr_extractor`
- `FileType` из `processing.converter`

Новые структуры только для fixture'ов (expected_results JSON).

### 3.4. Ключевые алгоритмы

#### Создание тестовых файлов (sample.docx/xlsx/pdf)
Для DOCX/XLSX использовать python-docx/openpyxl для программного создания простых документов с:
- 2-3 секции с заголовками
- Небольшой текст в каждой секции
- 1-2 таблицы (для DOCX - простая, для XLSX - числовые данные)

Для PDF можно либо:
- Создать PDF через LibreOffice из DOCX fixture
- Использовать существующий простой PDF

#### Логика проверки в тестах
1. Загрузить fixture файл
2. Запустить DocumentProcessor.process_document()
3. Загрузить сохраненный DocumentSkeleton из FileStorage
4. Сравнить с expected_results JSON:
   - Количество узлов
   - Иерархия (parent-child связи)
   - Наличие и тип таблиц
   - Привязка таблиц к секциям

### 3.5. Изменения в существующем коде

**Изменения НЕ требуются** в существующих модулях. DocumentProcessor создается только для тестов.

Новые файлы:
- `02_src/processing/tests/integration/test_full_pipeline.py`
- `02_src/processing/tests/integration/test_docx_pipeline.py`
- `02_src/processing/tests/integration/test_xlsx_pipeline.py`
- `02_src/processing/tests/integration/test_pdf_pipeline.py`
- `02_src/processing/tests/integration/test_tables.py`
- `02_src/processing/tests/fixtures/sample.docx`
- `02_src/processing/tests/fixtures/sample.xlsx`
- `02_src/processing/tests/fixtures/sample.pdf`
- `02_src/processing/tests/fixtures/expected_results/*.json`
- `02_src/processing/tests/integration/conftest.py` (pytest fixtures)

## 4. План реализации

### Шаг 1: Создать DocumentProcessor
- Файл: `02_src/processing/tests/integration/conftest.py`
- Создать класс DocumentProcessor с полной логикой pipeline
- Добавить метод `_generate_document_id()` для генерации уникальных ID

### Шаг 2: Создать тестовые fixture'ы
- Скрипт для создания sample.docx с 2-3 секциями
- Скрипт для создания sample.xlsx с 2 листами (числовые данные)
- Создать sample.pdf (либо существующий, либо сгенерированный)
- Создать expected_results JSON для каждого файла вручную (или прогнать pipeline один раз и сохранить результат)

### Шаг 3: Создать базовую структуру тестов
- Файл: `02_src/processing/tests/integration/conftest.py`
- Pytest fixtures для создания DocumentProcessor с MockVLMOCR
- Pytest fixture для временной директории FileStorage (auto cleanup)
- Pytest fixtures для путей к test файлам

### Шаг 4: Реализовать test_full_pipeline_docx
- Проверка: файл → DocumentSkeleton → сохранение → загрузка
- Asserts: количество узлов, иерархия, таблицы

### Шаг 5: Реализовать test_xlsx_with_numeric_tables
- Проверка: каждый лист = отдельная страница PDF
- Asserts: NUMERIC таблицы → node.table_data с правильной структурой

### Шаг 6: Реализовать test_pdf_with_text_matrix_tables
- Проверка: TEXT_MATRIX таблицы корректно классифицированы
- Asserts: тип таблиц, привязка к секциям

### Шаг 7: Дополнительные проверки
- Тест сохранения/загрузки через FileStorage
- Тест с DocumentProcessor с реальным файлом (если есть доступ)

### Шаг 8: Конфигурация pytest
- Добавить `pytest.ini` или обновить `pyproject.toml` для маркировки integration тестов
- Настроить отдельно запуск unit vs integration тестов

## 5. Технические критерии приемки

- [ ] TC-001: DocumentProcessor успешно обрабатывает DOCX файл от начала до конца
- [ ] TC-002: DocumentProcessor успешно обрабатывает XLSX файл с несколькими листами
- [ ] TC-003: DocumentProcessor успешно обрабатывает PDF файл
- [ ] TC-004: NUMERIC таблицы из XLSX корректно извлекаются (проверка node.table_data)
- [ ] TC-005: TEXT_MATRIX таблицы из PDF корректно классифицированы и привязаны
- [ ] TC-006: DocumentSkeleton сохраняется в FileStorage и загружается без потери данных
- [ ] TC-007: Иерархия узлов соответствует expected_results JSON
- [ ] TC-008: Тесты изолированы (используют временные директории, auto cleanup)
- [ ] TC-009: Все тесты проходят с `pytest -m integration`
- [ ] TC-010: Fixture'ы для всех тестовых файлов созданы и документированы

## 6. Важные детали для Developer

### Использование MockVLMOCR
- MockVLMOCR уже реализован в `02_src/processing/mock_vlm_ocr.py`
- Он возвращает детерминированные ответы (одинаковый вход → одинаковый выход)
- Для разных тестовых файлов можно создавать разные mock'и с разными fixture_path

### Создание тестовых файлов
- **DOCX**: Использовать `python-docx` для создания документа программно
- **XLSX**: Использовать `openpyxl` для создания Excel с числовыми данными
- **PDF**: Вариант 1 - сгенерировать из DOCX через LibreOffice (если доступен)
         Вариант 2 - использовать существующий простой PDF

### Генерация expected_results
- Вариант 1: Создать вручную (проще для простых документов)
- Вариант 2: Прогнать pipeline один раз, сохранить результат, использовать как expected
- Вариант 2 предпочтительнее для сложных документов

### Временные файлы и директории
- Использовать `tmp_path` или `tmpdir` fixture от pytest
- FileStorage должен использовать временную директорию
- Автоматическая очистка после тестов

### Изоляция тестов
- Каждый тест должен быть независимым
- Не использовать глобальное состояние
- Создавать новый DocumentProcessor для каждого теста

### Конфигурация pytest
- Создать маркировку `@pytest.mark.integration` для интеграционных тестов
- Добавить в `pyproject.toml`:
  ```toml
  [tool.pytest.ini_options]
  markers = [
      "integration: marks tests as integration tests (deselect with '-m \"not integration\"')"
  ]
  ```
- Запуск только интеграционных: `pytest -m integration`
- Запуск без интеграционных: `pytest -m "not integration"`

### Особенности Converter и Renderer
- Converter для PDF возвращает тот же путь (не создает временный файл)
- Renderer возвращает список bytes (PNG images), которые не нужно сохранять на диск
- MockVLMOCR принимает список bytes, игнорирует контент для детерминизма

### Обработка ошибок
- Тесты НЕ должны проверять обработку ошибок (это unit тесты)
- Интеграционные тесты проверяют **счастливый путь** (happy path)
- Если один из модулей падает - тест падает (это корректное поведение)

### Производительность
- VLM-OCR изолирован через mock, поэтому тесты быстрые
- Если используются реальные Converter/Renderer - они могут быть медленными
- Рассмотреть кэширование результатов рендеринга для PDF (не требуется для v1.0)

### Документация
- Добавить docstring в DocumentProcessor с описанием pipeline
- Добавить комментарии в тестах для объяснения проверок
- Создать README в `02_src/processing/tests/fixtures/` с описанием fixture'ов
