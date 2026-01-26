# Техническое задание: Renderer (PDF → PNG)

## 1. Анализ задачи

Необходимо реализовать модуль **Renderer** для преобразования PDF-документов в PNG-изображения страниц. Это критический компонент unified pipeline обработки документов (ADR-001): после конвертации в PDF выполняется рендер страниц в PNG для VLM-OCR экстракции.

**Основные требования:**
- Постраничный рендеринг PDF в PNG
- Контроль качества через DPI (200-300)
- Очистка временных файлов
- Unit тесты с fixtures

## 2. Текущее состояние

### 2.1. Существующие модули

**02_src/processing/converter.py:**
- `Converter` — конвертирует DOCX/Excel/TXT в PDF
- Использует `tempfile.NamedTemporaryFile` для временных файлов
- Паттерн: `async` методы, кастомные исключения, логирование

**02_src/processing/vlm_ocr_extractor.py:**
- `VLMOCRExtractor` — принимает PNG-изображения страниц
- Ожидает `List[bytes]` PNG-изображений

**02_src/processing/__init__.py:**
- Экспортирует классы модуля processing
- Нужно будет добавить `Renderer` в `__all__`

### 2.2. Что можно переиспользовать

**Паттерны из Converter:**
- Структура исключения: `RenderingError` (по аналогии с `ConversionError`)
- Логирование операций
- Проверка зависимостей при инициализации
- Работа с временными файлами через `tempfile`

### 2.3. Зависимости

**requirements.txt:**
- Core зависимости уже есть (python-docx, openpyxl, fpdf2)
- **Нужно добавить:** pdf2image (рекомендуется) или pymupdf

## 3. Предлагаемое решение

### 3.1. Общий подход

**Выбор библиотеки:** Использовать **pdf2image** как primary реализацию.

**Обоснование:**
- Это обёртка над pdftoppm (Poppler) — стабильный и хорошо протестированный инструмент
- Простая интеграция: `convert_from_path(pdf_path, dpi=200)`
- Async-friendly (можно обернуть в async метод)
- Cross-platform поддержка

**Альтернатива (fallback):** pymupdf (fitz) — быстрее, но требует дополнительной лицензии для коммерческого использования.

### 3.2. Компоненты

#### RenderingError (Exception)
- **Назначение:** Кастомное исключение для ошибок рендеринга
- **Поля:** `pdf_path`, `details`
- **Интерфейс:**
  ```python
  class RenderingError(Exception):
      def __init__(self, pdf_path: str, details: str):
          # Сообщение: f"Failed to render {pdf_path}: {details}"
  ```

#### Renderer
- **Назначение:** Рендеринг PDF в PNG-изображения
- **Интерфейс:**
  ```python
  class Renderer:
      def __init__(self, dpi: int = 200, log_dir: Optional[str] = None)

      async def render_pdf_to_images(self, pdf_path: str) -> List[bytes]
      async def render_page_to_image(self, pdf_path: str, page_number: int) -> bytes
  ```
- **Зависимости:** pdf2image, tempfile, logging

### 3.3. Структуры данных

**Входные данные:**
- `pdf_path: str` — путь к PDF файлу

**Выходные данные:**
- `List[bytes]` — список PNG-изображений (каждый элемент = PNG bytes)
- `bytes` — одно PNG-изображение

### 3.4. Ключевые алгоритмы

#### render_pdf_to_images(pdf_path)
1. Проверить существование файла → `FileNotFoundError` если нет
2. Открыть PDF через pdf2image: `convert_from_path(pdf_path, dpi=self.dpi)`
3. Конвертировать каждый PIL Image в bytes (PNG format)
4. Вернуть список bytes

**Логика cleanup:**
- pdf2image возвращает PIL Images (в памяти)
- Конвертация в PNG bytes через `io.BytesIO`
- Временные файлы на диске не создаются (все в памяти)

#### render_page_to_image(pdf_path, page_number)
1. Проверить валидность `page_number` (1-indexed)
2. Использовать `convert_from_path` с параметром `first_page`/`last_page`
3. Конвертировать в PNG bytes
4. Вернуть bytes

**Обработка ошибок:**
- Файл не существует → `FileNotFoundError`
- Некорректный PDF → `RenderingError` с деталями от pdf2image
- `page_number` вне диапазона → `RenderingError`

### 3.5. Изменения в существующем коде

**02_src/processing/__init__.py:**
```python
# Добавить импорты
from processing.renderer import Renderer, RenderingError

# Обновить __all__
__all__ = [
    # ... existing ...
    "Renderer",
    "RenderingError",
]
```

**requirements.txt:**
```
# Добавить
pdf2image>=1.16.0
```

## 4. План реализации

1. **Добавить зависимость:** Обновить `requirements.txt` с `pdf2image>=1.16.0`

2. **Создать структуру тестов:**
   - `02_src/processing/tests/fixtures/sample.pdf` (тестовый PDF)
   - `02_src/processing/tests/test_renderer.py`

3. **Реализовать RenderingError:**
   - Кастомное исключение с полями `pdf_path`, `details`

4. **Реализовать Renderer.__init__:**
   - Принимать `dpi`, `log_dir`
   - Проверить зависимость pdf2image
   - Setup логирования (по аналогии с Converter)

5. **Реализовать render_pdf_to_images:**
   - Проверка существования файла
   - Вызов `convert_from_path`
   - Конвертация PIL Images в bytes
   - Логирование (start, success, failure)

6. **Реализовать render_page_to_image:**
   - Валидация `page_number` (>= 1)
   - Рендеринг одной страницы
   - Обработка ошибок

7. **Написать unit тесты:**
   - `test_render_pdf_to_images_success`
   - `test_render_page_to_image_success`
   - `test_file_not_found`
   - `test_invalid_page_number`
   - `test_invalid_pdf`

8. **Обновить __init__.py:**
   - Добавить импорты `Renderer`, `RenderingError`
   - Обновить `__all__`

## 5. Технические критерии приемки

- [ ] TC-001: `render_pdf_to_images()` возвращает список PNG bytes
- [ ] TC-002: Количество PNG соответствует количеству страниц в PDF
- [ ] TC-003: `render_page_to_image()` рендерит одну страницу
- [ ] TC-004: DPI=200 produces adequate quality for VLM-OCR (проверяется визуально)
- [ ] TC-005: `FileNotFoundError` при отсутствии файла
- [ ] TC-006: `RenderingError` при некорректном PDF
- [ ] TC-007: `RenderingError` при некорректном `page_number`
- [ ] TC-008: PNG bytes могут быть открыты PIL/Image
- [ ] TC-009: Unit тесты покрывают все методы
- [ ] TC-010: Временные файлы не остаются на диске
- [ ] TC-011: Логирование операций в `04_logs/renderer/`

## 6. Важные детали для Developer

### 6.1. External dependency (Poppler)

**pdf2image требует установленный Poppler:**
- Windows: скачать binaries, добавить в PATH
- Linux: `sudo apt-get install poppler-utils`
- macOS: `brew install poppler`

**Решение:** Добавить проверку в `_check_dependencies()`:
```python
try:
    from pdf2image import convert_from_path
except ImportError:
    raise ImportError("pdf2image is required. Install with: pip install pdf2image")
```

**Важно:** Не проверять наличие Poppler в коде — это external dependency. Ошибка будет при вызове `convert_from_path`, её нужно ловить и конвертировать в `RenderingError`.

### 6.2. DPI выбор

**200 DPI** — баланс между качеством и размером:
- Минимум 150 DPI для читаемости текста VLM
- 200-300 DPI — оптимум для VLM-OCR
- >300 DPI — diminishing returns, большой размер файлов

**Реализация:** Default `dpi=200`, allow override в `__init__`.

### 6.3. Конвертация PIL Image → bytes

**Pattern:**
```python
import io
from PIL import Image

img = ... # PIL Image
buffer = io.BytesIO()
img.save(buffer, format="PNG")
png_bytes = buffer.getvalue()
```

### 6.4. page_number semantics

**1-indexed** для совместимости с человеческим счётом:
- `page_number=1` → первая страница
- `page_number=0` → `RenderingError`

**pdf2image API:** Использует 1-indexed для `first_page`/`last_page`.

### 6.5. Логирование

**Уровни:**
- `info`: начало рендеринга, успешное завершение
- `error`: ошибки рендеринга с деталями

**Формат лога:**
```python
logger.info(f"Starting render: {pdf_path} (dpi={self.dpi})")
logger.info(f"Rendering successful: {len(images)} pages")
logger.error(f"Rendering failed: {error_msg}")
```

### 6.6. Тестовые fixtures

**sample.pdf:** Создать простой PDF с 2-3 страницами через fpdf2 или использовать существующий файл.

**Важно:** Fixture должен быть достаточно маленьким для быстрых тестов, но содержать текст на разных страницах.

### 6.7. Async pattern

**pdf2image sync**, но метод должен быть `async` для согласованности с API (Converter также `async`).

**Решение:** Обернуть синхронный вызов:
```python
async def render_pdf_to_images(self, pdf_path: str) -> List[bytes]:
    # ... validation ...
    images = await asyncio.to_thread(
        convert_from_path, pdf_path, dpi=self.dpi
    )
```

### 6.8. Memory considerations

**Большие PDF (100+ страниц) при DPI=300:**
- Каждая страница ~1-3 MB в памяти
- 100 страниц = 100-300 MB RAM

**Оптимизация:** Для v1.0 загружать все страницы в память. Если станет проблемой — добавить batch рендеринг (отдельный task).

### 6.9. Error handling

**pdf2image может выбросить:**
- `PDFInfoNotInstalledError` — Poppler не установлен
- `PDFPageCountError` — некорректный PDF
- `PDFSyntaxError` — сломанный PDF

**Все exceptions** → ловить и конвертировать в `RenderingError` с деталями.
