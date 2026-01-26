# Задача 010: Renderer (PDF → PNG)

## Что нужно сделать

Реализовать рендеринг PDF в PNG-изображения для VLM-OCR.

## Зачем

VLM-OCR работает с изображениями страниц. Renderer обеспечивает преобразование PDF в PNG для каждого листа документа.

## Acceptance Criteria

- [ ] AC-001: Renderer для PDF → PNG (постранично)
- [ ] AC-002: render_pdf_to_images() возвращает список PNG (bytes)
- [ ] AC-003: render_page_to_image() для одной страницы
- [ ] AC-004: Контроль качества изображения (DPI)
- [ ] AC-005: Unit тесты
- [ ] AC-006: Временные PNG очищаются

## Контекст

**ADR-001: Форматы документов**

Unified pipeline требует PNG для VLM-OCR:
- Любой формат → Converter → PDF → Renderer → PNG → VLM-OCR

**Интерфейсы и контракты:**

```python
from typing import List

class Renderer:
    """
    PDF → PNG (постранично).

    Использует pdf2image (обёртка над pdftoppm) или альтернативы.
    """

    def __init__(self, dpi: int = 200):
        """
        Args:
            dpi: Разрешение (dots per inch).
                 200-300 — баланс качества/размера для VLM-OCR.
        """
        self.dpi = dpi

    async def render_pdf_to_images(self, pdf_path: str) -> List[bytes]:
        """
        Рендерить PDF в список PNG-изображений.

        Args:
            pdf_path: Путь к PDF файлу

        Returns:
            Список PNG-изображений (bytes), по одному на страницу.

        Raises:
            RenderingError: если рендеринг не удалась
        """
        pass

    async def render_page_to_image(
        self,
        pdf_path: str,
        page_number: int
    ) -> bytes:
        """
        Рендерить одну страницу.

        Args:
            pdf_path: Путь к PDF файлу
            page_number: Номер страницы (1-indexed)

        Returns:
            PNG-изображение (bytes)

        Raises:
            RenderingError: если страница не существует
        """
        pass
```

**Стратегия реализации (выбор библиотек):**

- **pdf2image** (рекомендуется) — обёртка над pdftoppm
  ```bash
  pip install pdf2image
  ```
  ```python
  from pdf2image import convert_from_path
  images = convert_from_path(pdf_path, dpi=200)
  ```

- **pymupdf (fitz)** — альтернатива, быстрее
  ```bash
  pip install pymupdf
  ```
  ```python
  import fitz
  doc = fitz.open(pdf_path)
  page = doc.load_page(0)  # первая страница
  pix = page.get_pixmap(dpi=200)
  pix.save("page.png")
  ```

**Структура проекта:**

```
02_src/
├── processing/
│   ├── __init__.py
│   ├── renderer.py
│   └── tests/
│       ├── test_renderer.py
│       └── fixtures/
│           └── sample.pdf
04_logs/
└── renderer/
    └── (логи рендеринга)
```

## Примечания для Analyst

**Ключевые решения:**
1. Какой DPI использовать? (200-300 для баланса качества/размера)
2. Как обрабатывать ошибки рендеринга? (пробрасывать с детальным сообщением)
3. Нужно ли сжимать PNG? (для v1.0 — нет, VLM-OCR сам сожмет если нужно)
4. Как очищать временные PNG? (context manager или tempfile)

**Важно:** PNG — временные файлы. После VLM-OCR они не нужны (если не требуется отладка).

## Зависимости

- Задача 009: Converter (поставляет PDF)

## Следующие задачи

После завершения:
- Задача 008: VLM-OCR Extractor (использует PNG от Renderer)
