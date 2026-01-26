# Отчет о реализации: Skeleton Builder

## Что реализовано

SkeletonBuilder - агрегация результатов VLM-OCR в DocumentSkeleton. Превращает неструктурированные данные (DocumentData) в иерархический скелет документа с поддержкой вложенных заголовков, автоматическим определением parent-child отношений и прикреплением таблиц к разделам.

## Файлы

**Новые:**
- `02_src/processing/skeleton_builder.py` - реализация SkeletonBuilder, generate_id_from_title, level_to_node_type
- `02_src/processing/tests/test_skeleton_builder.py` - unit и интеграционные тесты (21 тест)
- `02_src/processing/tests/fixtures/expected_skeleton.json` - примеры ожидаемых структур

**Измененные:**
- `02_src/processing/__init__.py` - добавлен экспорт SkeletonBuilder, generate_id_from_title, level_to_node_type

## Особенности реализации

### Update parent page ranges с учетом собственного диапазона
**Причина:** Родительский узел должен охватывать не только детей, но и свой собственный page_range (страница заголовка).
**Решение:** В `_update_parent_page_ranges` родительский range обновляется как `min(own.start, children.min)..max(own.end, children.max)`

### Специфичность при выборе target для таблиц
**Причина:** Таблица на странице внутри нескольких section должна прикрепиться к самому специфичному (глубокому) разделу.
**Решение:** В `_find_table_target` используется composite key: `(range_size, -depth)` - минимизируем размер диапазона и максимизируем глубину вложенности

### Предпочтение SECTION/CHAPTER над ROOT при nearest search
**Причина:** Таблица между разделами должна прикрепиться к ближайшему CHAPTER/SECTION, а не к ROOT.
**Решение:** В nearest_key добавлен приоритет: `(distance, is_root, page_range.start)` - ROOT менее приоритетен при равном расстоянии

## Известные проблемы

Нет
