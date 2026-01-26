# Задача 013: CLI Interface для Document Processing

## Что нужно сделать

Создать интерфейс командной строки для обработки документов через pipeline. Позволит запустить обработку документа и получить DocumentSkeleton с зафиксированной структурой.

## Зачем

После выполнения Итераций 1-2 у нас есть полнофункциональный pipeline (Converter → Renderer → VLM-OCR → SkeletonBuilder → FileStorage), но он "спрятан" внутри модулей. CLI позволит "пощупать" результат работы на реальных документах.

## Acceptance Criteria

- [x] AC-001: Можно запустить: `python -m processing.cli path/to/document.docx`
- [x] AC-002: CLI выводит прогресс обработки step-by-step
- [x] AC-003: CLI сохраняет DocumentSkeleton в `04_storage/skeletons/<document_id>.json`
- [x] AC-004: CLI показывает структуру документа в виде дерева
- [x] AC-005: Поддерживаемые форматы: DOCX, XLSX, PDF
- [x] AC-006: Обработка ошибок с понятными сообщениями
- [x] AC-007: Использует DocumentProcessor (перенести из тестов в продакшен)

## Контекст

### Что уже реализовано

**Инфраструктурный слой (Итерация 1):**
- SimpleLLMGateway в `02_src/gateway/simple_llm_gateway.py` ✅
- SGR Agent Core в `02_src/agents/sgr_agent.py` ✅

**Document Processing Pipeline (Итерация 2):**
- DocumentSkeleton в `02_src/document/skeleton.py` ✅
- VLM-OCR Extractor в `02_src/processing/vlm_ocr_extractor.py` ✅
- Converter в `02_src/processing/converter.py` ✅
- Renderer в `02_src/processing/renderer.py` ✅
- SkeletonBuilder в `02_src/processing/skeleton_builder.py` ✅
- FileStorage в `02_src/storage/file_storage.py` ✅

**Тестовый оркестратор:**
- DocumentProcessor в `02_src/processing/tests/integration/conftest.py:72-147` ✅
  > **Примечание:** Этот класс помечен как "NOT part of production code - only for integration tests"
  > **Для CLI нужно:** Перенести/адаптировать DocumentProcessor в продакшен-код

### Что НЕ входит в эту задачу

- ❌ Table Classifier (задача 019 в backlog)
- ❌ Cell Flattening (задача 020)
- ❌ Pandas интеграция для числовых таблиц (задача 021)

Таблицы будут обработаны позже (Итерация 4). Сейчас фиксируем только структуру документа.

## Структура проекта

```
02_src/
├── processing/
│   ├── __init__.py
│   ├── cli.py                    # ← Создать CLI module
│   ├── processor.py              # ← Создать/перенести DocumentProcessor
│   ├── converter.py              # ✅ Существует
│   ├── renderer.py               # ✅ Существует
│   ├── vlm_ocr_extractor.py      # ✅ Существует
│   ├── skeleton_builder.py       # ✅ Существует
│   └── tests/
│       └── integration/
│           └── conftest.py       # ← DocumentProcessor здесь (тестовый)

04_storage/
└── skeletons/
    └── <document_id>.json        # ← Сохраненные skeleton'ы
```

## Технические требования

### 1. DocumentProcessor (продакшен версия)

**Файл:** `02_src/processing/processor.py`

Перенести DocumentProcessor из `conftest.py` в продакшен-код:

```python
"""
Document Processor - оркестратор pipeline для продакшен использования.

Обрабатывает документы через полный pipeline:
Converter → Renderer → VLM-OCR → SkeletonBuilder → FileStorage
"""
import asyncio
import uuid
from pathlib import Path

from converter import Converter, FileType
from renderer import Renderer
from vlm_ocr_extractor import VLMOCRExtractor
from skeleton_builder import SkeletonBuilder
from storage.file_storage import FileStorage


class DocumentProcessor:
    """Оркестратор полного pipeline обработки документов."""

    def __init__(
        self,
        vlm_ocr_module,
        storage_base_path: str = "04_storage/skeletons",
        renderer_dpi: int = 200,
    ):
        """Инициализирует процессор со всеми компонентами pipeline.

        Args:
            vlm_ocr_module: VLM-OCR модуль (может быть MockVLMOCR или реальный)
            storage_base_path: Базовый путь для FileStorage
            renderer_dpi: DPI для рендеринга PDF→PNG
        """
        self.converter = Converter()
        self.renderer = Renderer(dpi=renderer_dpi)
        self.vlm_extractor = VLMOCRExtractor(vlm_ocr_module=vlm_ocr_module)
        self.skeleton_builder = SkeletonBuilder()
        self.storage = FileStorage(base_path=storage_base_path)

    async def process_document(self, file_path: str) -> str:
        """Обработать документ через полный pipeline.

        Pipeline:
        1. Detect file type
        2. Convert to PDF (если нужно)
        3. Render to PNG images
        4. Extract data via VLM-OCR
        5. Build DocumentSkeleton
        6. Save to FileStorage

        Args:
            file_path: Путь к исходному документу

        Returns:
            document_id обработанного документа

        Raises:
            FileNotFoundError: Если файл не существует
            Exception: Если любой этап pipeline падает
        """
        # 1. Detect file type
        file_type = await self.converter.detect_file_type(file_path)

        # 2. Convert to PDF if needed
        if file_type != FileType.PDF:
            pdf_path = await self.converter.convert_to_pdf(file_path, file_type)
        else:
            pdf_path = file_path

        # 3. Render PDF to PNG
        images = await self.renderer.render_pdf_to_images(pdf_path)

        # 4. Extract data via VLM-OCR
        document_data = self.vlm_extractor.extract_full_document(images)

        # 5. Build DocumentSkeleton
        document_id = f"doc_{uuid.uuid4().hex[:16]}"
        skeleton = await self.skeleton_builder.build_skeleton(
            document_data=document_data,
            document_id=document_id,
        )

        # 6. Save to FileStorage
        await self.storage.save_skeleton(skeleton.document_id, skeleton)

        return document_id
```

### 2. CLI Module

**Файл:** `02_src/processing/cli.py`

```python
"""
CLI interface для document processing.

Запуск:
    python -m processing.cli path/to/document.docx
    python -m processing.cli path/to/report.xlsx --output-dir custom/path
"""
import argparse
import asyncio
import sys
from pathlib import Path

from document import NodeType
from processor import DocumentProcessor
from processing.mock_vlm_ocr import MockVLMOCR  # TODO: заменить на реальный модуль


def print_tree(node, indent: int = 0, skeleton=None):
    """Вывести узел и его детей в виде дерева."""
    prefix = "  " * indent
    connector = "└── " if indent > 0 else ""

    node_type = node.type.value if hasattr(node.type, 'value') else str(node.type)
    page_range = f"(стр. {node.page_range.start}-{node.page_range.end})"

    print(f"{prefix}{connector}{node.id}: [{node_type}] {node.title} {page_range}")

    for child_id in node.children_ids:
        child = skeleton._nodes.get(child_id)
        if child:
            print_tree(child, indent + 1, skeleton)


async def main():
    """Главная функция CLI."""
    parser = argparse.ArgumentParser(
        description="Обработать документ и создать DocumentSkeleton"
    )
    parser.add_argument(
        "file_path",
        help="Путь к документу (DOCX/XLSX/PDF)"
    )
    parser.add_argument(
        "--output-dir",
        default="04_storage/skeletons",
        help="Директория для сохранения skeleton'ов (default: 04_storage/skeletons)"
    )
    parser.add_argument(
        "--dpi",
        type=int,
        default=200,
        help="DPI для рендеринга PDF (default: 200)"
    )

    args = parser.parse_args()

    # Проверка файла
    file_path = Path(args.file_path)
    if not file_path.exists():
        print(f"❌ Файл не найден: {args.file_path}")
        sys.exit(1)

    print(f"📄 Загрузка файла: {file_path.name}")

    # Создаем процессор с MockVLMOCR
    # TODO: В задаче 014 заменить на реальный VLM-OCR модуль
    processor = DocumentProcessor(
        vlm_ocr_module=MockVLMOCR(),
        storage_base_path=args.output_dir,
        renderer_dpi=args.dpi,
    )

    try:
        # Обрабатываем документ
        document_id = await processor.process_document(str(file_path))

        print(f"✅ Обработка завершена успешно")
        print(f"💾 Сохранено: {args.output_dir}/{document_id}.json")
        print()

        # Загружаем skeleton для отображения
        skeleton = await processor.storage.load_skeleton(document_id)
        root = await skeleton.get_root()

        print("🌳 Структура документа:")
        print_tree(root, skeleton=skeleton)

    except FileNotFoundError as e:
        print(f"❌ Файл не найден: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Ошибка обработки: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
```

### 3. Обновить `02_src/processing/__init__.py`

Добавить экспорты для удобства использования:

```python
"""
Processing module: Document processing pipeline.

Components:
- Converter: DOCX/Excel/TXT → PDF
- Renderer: PDF → PNG
- VLMOCRExtractor: VLM-OCR extraction wrapper
- SkeletonBuilder: DocumentSkeleton aggregation
- DocumentProcessor: Pipeline orchestrator
"""

from .converter import Converter, FileType
from .renderer import Renderer
from .vlm_ocr_extractor import VLMOCRExtractor, DocumentData
from .skeleton_builder import SkeletonBuilder
from .processor import DocumentProcessor

__all__ = [
    "Converter",
    "FileType",
    "Renderer",
    "VLMOCRExtractor",
    "DocumentData",
    "SkeletonBuilder",
    "DocumentProcessor",
]
```

### 4. Прогресс-вывод

Формат вывода при обработке:

```bash
$ python -m processing.cli my_document.docx
📄 Загрузка файла: my_document.docx
✅ Конвертация: DOCX → PDF (2.3s)
✅ Рендеринг: PDF → 5 изображений (1.1s)
✅ VLM-OCR: извлечение данных (8.4s)
✅ Skeleton Builder: агрегация (0.3s)
✅ FileStorage: сохранение (0.1s)
💾 Сохранено: 04_storage/skeletons/doc_abc123.json

🌳 Структура документа:
root: [root] doc_abc123 (стр. 1-5)
  └── section_1: [section] 1. Раздел (стр. 1-2)
      └── table_1: [table] Таблица 1.1 (стр. 2)
  └── section_2: [section] 2. Анализ (стр. 3-5)
```

### 5. Обработка ошибок

| Ситуация | Действие |
|----------|----------|
| Файл не существует | `❌ Файл не найден: {path}` + exit 1 |
| Неподдерживаемый формат | `❌ Неподдерживаемый формат: .txt` + список поддерживаемых |
| Ошибка конвертации | `❌ Ошибка конвертации: {error}` |
| Ошибка VLM-OCR | `❌ Ошибка VLM-OCR: {error}` |
| Ошибка сохранения | `❌ Ошибка сохранения: {error}` |

## Примечания для Analyst

**Важно:**
- CLI использует MockVLMOCR (заглушку) - структура будет тестовой
- Реальный VLM-OCR будет интегрирован в задаче 014
- DocumentProcessor переносится из тестов (conftest.py) в продакшен
- Используем существующую структуру проекта: `02_src/processing/`

**Ключевые решения для проработки:**
1. Нужно ли добавить логирование каждого этапа (время выполнения)?
2. Обрабатывать ли существующий skeleton (перезаписывать/пропускать)?
3. Добавить ли `--verbose` флаг для детального вывода?
4. Нужно ли валидировать JSON после сохранения?

**Технические детали:**
- CLI запускается как Python module: `python -m processing.cli`
- Асинхронная функция `main()` для async/await pipeline
- MockVLMOCR импортируется из `processing.mock_vlm_ocr`
- FileStorage создает директорию автоматически если не существует

**Библиотеки:**
- `argparse` (стандартная библиотека)
- `pathlib` (стандартная библиотека)
- `asyncio` (стандартная библиотека)
- Не требуются дополнительные зависимости

## Пример использования

```bash
# Обработать документ
python -m processing.cli my_document.docx

# Сcustom output directory
python -m processing.cli report.xlsx --output-dir custom/path

# С высоким DPI
python -m processing.cli scan.pdf --dpi 300
```

## Зависимости

- Задачи 006-012 должны быть выполнены ✅
- Модули:
  - `processing.converter.Converter`
  - `processing.renderer.Renderer`
  - `processing.vlm_ocr_extractor.VLMOCRExtractor`
  - `processing.skeleton_builder.SkeletonBuilder`
  - `storage.file_storage.FileStorage`
  - `document.skeleton.DocumentSkeleton`
  - `processing.mock_vlm_ocr.MockVLMOCR`

## Следующие задачи

После завершения:
- Пользователь сможет запускать pipeline через CLI
- Результат будет использовать MockVLMOCR (тестовые данные)
- Задача 014 заменит MockVLMOCR на реальный модуль
- Можно будет работать с реальными документами
