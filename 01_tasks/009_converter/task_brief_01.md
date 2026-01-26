# Задача 009: Converter (DOCX/Excel → PDF)

## Что нужно сделать

Реализовать конвертацию DOCX, Excel, text-PDF в унифицированный PDF формат для последующего рендеринга в PNG.

## Зачем

VLM-OCR работает с PNG-изображениями страниц PDF. Converter обеспечивает унифицированный входной формат для всех типов документов.

## Acceptance Criteria

- [ ] AC-001: Converter для DOCX → PDF
- [ ] AC-002: Converter для Excel → PDF (многолистовый, каждый лист = страницы)
- [ ] AC-003: Converter для plain text → PDF
- [ ] AC-004: FileType enum и auto-detector по расширению
- [ ] AC-005: Обработка ошибок конвертации
- [ ] AC-006: Unit тесты с sample файлами
- [ ] AC-007: Временные PDF файлы очищаются

## Контекст

**ADR-001: Форматы документов**

Поддерживаемые форматы для v1.0:
- **PDF (любой)** — уже PDF, пропускается
- **Excel (.xlsx)** — конвертируется в PDF
- **DOCX** — конвертируется в PDF
- **TXT** — конвертируется в PDF

**Интерфейсы и контракты:**

```python
from enum import Enum
from typing import Optional

class FileType(str, Enum):
    PDF = "pdf"
    DOCX = "docx"
    XLSX = "xlsx"
    TXT = "txt"
    UNKNOWN = "unknown"

class Converter:
    """Конвертация любых форматов в PDF"""

    async def convert_to_pdf(
        self,
        file_path: str,
        file_type: Optional[FileType] = None
    ) -> str:
        """
        Конвертировать файл в PDF.

        Args:
            file_path: Путь к исходному файлу
            file_type: Тип файла (если None — auto-detect)

        Returns:
            Путь к временному PDF файлу

        Raises:
            ValueError: если формат не поддерживается
            ConversionError: если конвертация не удалась
        """
        pass

    async def detect_file_type(self, file_path: str) -> FileType:
        """Определить тип файла по расширению"""
        pass

    async def _convert_docx_to_pdf(self, docx_path: str) -> str:
        """Конвертировать DOCX в PDF"""
        pass

    async def _convert_xlsx_to_pdf(self, xlsx_path: str) -> str:
        """
        Конвертировать Excel в PDF.

        Каждый лист Excel становится отдельной страницей PDF.
        """
        pass

    async def _convert_txt_to_pdf(self, txt_path: str) -> str:
        """Конвертировать plain text в PDF"""
        pass
```

**Стратегия реализации (выбор библиотек):**

Для DOCX:
- **Вариант A:** LibreOffice (через subprocess) — надёжно, но требует установки
- **Вариант B:** python-docx + reportlab — pure Python, но сложнее
- **Рекомендация:** начать с Варианта B (python-docx + fpdf)

Для Excel:
- **Вариант A:** LibreOffice — надёжно
- **Вариант B:** openpyxl + reportlab — pure Python
- **Рекомендация:** Вариант B (openpyxl + fpdf)

**Структура проекта:**

```
02_src/
├── processing/
│   ├── __init__.py
│   ├── converter.py
│   └── tests/
│       ├── test_converter.py
│       └── fixtures/
│           ├── sample.docx
│           ├── sample.xlsx
│           └── sample.txt
04_logs/
└── converter/
    └── (логи конверсии)
```

## Примечания для Analyst

**Ключевые решения:**
1. Какие библиотеки использовать? (python-docx + fpdf или LibreOffice)
2. Как обрабатывать многолистовые Excel? (каждый лист = страница PDF)
3. Как очищать временные PDF? (context manager или atexit)

**Важно:** PDF-файлы временные — после рендеринга в PNG они удаляются. Хранить только если нужно для отладки.

## Зависимости

Эта задача не зависит от других (можно делать параллельно с 006, 007).

## Следующие задачи

После завершения:
- Задача 010: Renderer (использует PDF от Converter)
