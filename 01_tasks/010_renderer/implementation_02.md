# Отчет о реализации: Замена pdf2image на PyMuPDF в Renderer

## Что реализовано

Заменена библиотека pdf2image (требует Poppler) на PyMuPDF (чистый Python). Интерфейс Renderer полностью сохранен, существующие тесты продолжат работать без изменений.

## Файлы

**Измененные:**
- `02_src/processing/renderer.py` - заменен pdf2image на PyMuPDF (fitz)
- `requirements.txt` - убран pdf2image, добавлен pymupdf>=1.23.0
- `02_src/processing/cli.py` - исправлен путь storage с `04_storage/skeletons` на `data` (ADR 004)
- `02_src/processing/processor.py` - исправлен дефолт `storage_base_path` на `data` (ADR 004)
- `.gitignore` - добавлен `data/` для сгенерированных данных

## Особенности реализации

### Изменен механизм рендеринга

**Причина:** pdf2image требует установленного системного пакета Poppler, что создает проблемы с зависимостями
**Решение:** Использован PyMuPDF (fitz) - чистый Python пакет без внешних зависимостей

Ключевые изменения:
- `convert_from_path()` заменен на `fitz.open()` + `page.get_pixmap()`
- Добавлены вспомогательные методы `_render_all_pages()` и `_render_single_page()` для выполнения блокирующих операций
- Конвертация pixmap → PIL Image → PNG bytes аналогична reference implementation из `05_a_reports_ETL_02/03_src/common/pdf_utils.py`

### Исправлено нарушение ADR 004

**Проблема:** task_brief_013 использовал `04_storage/skeletons` вместо `data/` из ADR 004
**Исправлено:** CLI и Processor теперь используют `data/` по умолчанию
**Структура:** `data/{document_id}/skeleton.json` (соответствует ADR 004)

### Асинхронная обработка сохранена

Блокирующие операции fitz выполняются в thread pool через `asyncio.to_thread()`, что сохраняет асинхронную архитектуру модуля.

## Известные проблемы

Нет
