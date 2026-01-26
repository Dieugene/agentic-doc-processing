# Техническое задание: Skeleton Builder - агрегация VLM-OCR результатов

**Версия:** 01
**Дата:** 2025-01-23
**Задача:** 011_skeleton_builder

---

## 1. Анализ задачи

SkeletonBuilder — связующее звено между VLM-OCRExtractor и DocumentSkeleton. Превращает неструктурированные данные от VLM-OCR (DocumentData) в иерархический скелет документа (DocumentSkeleton).

**Ключевые проблемы:**
1. **Построение иерархии:** VLM-OCR возвращает плоский список заголовков с уровнями. Нужно восстановить дерево parent-child отношений.
2. **Разрывы в нумерации:** Заголовки могут быть не последовательными (1.1, 1.3, 2.1). Нужно корректно определять родителя по уровню.
3. **Прикрепление таблиц:** Таблицы нужно привязать к разделам по странице или близости к заголовку.

---

## 2. Текущее состояние

**Реализованные зависимости:**
- `document.skeleton.Node` — узел скелета со всеми полями
- `document.skeleton.DocumentSkeleton` — контейнер для узлов
- `document.skeleton.NodeType` — enum типов узлов
- `document.skeleton.PageRange` — диапазон страниц
- `document.skeleton.InternalStructure` — иерархия подпунктов
- `processing.vlm_ocr_extractor.DocumentData` — данные от VLM-OCR
- `processing.vlm_ocr_extractor.VLMOCRResponse` — ответ VLM-OCR

**Существующие fixtures:**
- `02_src/processing/tests/fixtures/vlm_response_samples.json` — пример ответа VLM-OCR

**Стратегия моков:**
- Mock VLM-OCR возвращает предопределённый DocumentData из fixtures
- Тесты используют реальные DocumentSkeleton, не моки

---

## 3. Предлагаемое решение

### 3.1. Общий подход

**Двухэтапное построение:**
1. **Построение дерева:** Создать Node для каждого заголовка, установить parent-child связи по уровням
2. **Агрегация таблиц:** Прикрепить таблицы к ближайшим разделам по странице

**Принципы:**
- Root node создаётся всегда, даже если document_id уже задан
- Каждый заголовок становится отдельным Node
- Parent-child определяется по уровню заголовка (level)
- Content узла — полный текст из DocumentData.text
- Tables прикрепляются к разделам по близости страницы

### 3.2. Компоненты

#### SkeletonBuilder (class)
- **Назначение:** Агрегация DocumentData в DocumentSkeleton
- **Расположение:** `02_src/processing/skeleton_builder.py`
- **Интерфейс:**
  - `async def build_skeleton(self, document_data: DocumentData, document_id: str) -> DocumentSkeleton`
  - `def _build_node_tree(self, structure: Dict[str, Any], full_text: str, document_id: str) -> Dict[str, Node]`
  - `def _attach_tables(self, skeleton: DocumentSkeleton, tables: List[Dict[str, Any]]) -> None`
- **Зависимости:**
  - `document.skeleton` — все структуры
  - `processing.vlm_ocr_extractor.DocumentData`

### 3.3. Структуры данных

#### DocumentData (входной формат)
```python
# От VLM-OCRExtractor
DocumentData {
    text: str  # Полный текст документа
    structure: {
        "headers": [
            {"level": 1, "title": "1. Раздел", "page": 1},
            {"level": 2, "title": "1.1. Подраздел", "page": 2},
            {"level": 2, "title": "1.2. Еще subsection", "page": 3},
            {"level": 1, "title": "2. Второй раздел", "page": 4}
        ]
    }
    tables: [
        {"id": "table_1", "type": "NUMERIC", "page": 2, "location": {...}},
        {"id": "table_2", "type": "TEXT_MATRIX", "page": 5, "location": {...}}
    ]
}
```

#### Node Mapping (внутренний формат)
```python
# Во время построения
_nodes = {
    "root": Node(id="root", type=NodeType.ROOT, ...),
    "section_1": Node(id="section_1", type=NodeType.CHAPTER, ...),
    "section_1.1": Node(id="section_1.1", type=NodeType.SECTION, ...),
    "section_1.2": Node(id="section_1.2", type=NodeType.SECTION, ...),
    "section_2": Node(id="section_2", type=NodeType.CHAPTER, ...)
}
```

### 3.4. Ключевые алгоритмы

#### Построение дерева по уровням заголовков

**Алгоритм:**
1. Создать root node с id="root", type=ROOT
2. Для каждого заголовка из structure.headers:
   - Определить тип узла по уровню (level 1 → CHAPTER, level 2+ → SECTION)
   - Сгенерировать id из title: `section_<число из заголовка>` или `<title.lower().replace(" ", "_")>`
   - Найти родителя: последний заголовок с меньшим level
   - Создать Node с parent_id, добавить в children_ids родителя
3. Определить page_range: для листьев — одна страница, для родителей — min(children.start) .. max(children.end)

**Детекция родителя:**
- При проходе по заголовкам слева направо поддерживать стек `stack[level] = node_id`
- Для заголовка level N: родитель = `stack[N-1]` (верхний уровень)
- Пример:
  - Заголовок "1." level 1 → parent = root
  - Заголовок "1.1" level 2 → parent = section_1
  - Заголовок "1.2" level 2 → parent = section_1
  - Заголовок "2." level 1 → parent = root

**Обработка разрывов:**
- Если level jumps: 1 → 3 (нет level 2), то parent = последний level 1
- Алгоритм стека корректно обрабатывает любые разрывы

#### Определение content для узла

**Проблема:** VLM-OCR возвращает полный текст всего документа, не разбитый по разделам.

**Решение (базовая версия):**
- Все узлы получают одинаковый content = document_data.text
- internal_structure хранит подпункты из structure.headers

**Future improvement:** Разбить текст по подпунктам (requires VLM-OCR с chunking)

#### Прикрепление таблиц к разделам

**Алгоритм:**
1. Для каждой таблицы определить target_node:
   - Найти все узлы, где table.page ∈ node.page_range
   - Если один — прикрепить к нему
   - Если несколько — выбрать с наименьшим page_range.end (самый специфичный)
   - Если ни одного — найти ближайший по page (abs(node.page_range.start - table.page))

2. Создать Node для таблицы:
   - type = NodeType.TABLE
   - title = table.preview или "Table {table.id}"
   - table_data = {type: table.type, source: "vlm_ocr", data: {...}}
   - parent_id = target_node.id
   - page_range = PageRange(table.page, table.page)

3. Добавить table node в skeleton и обновить children_ids родителя

**Формат table_data:**
```python
# NUMERIC таблицы (future)
table_data = {
    "type": "numeric",
    "source": "original_file",
    "data": {"columns": [...], "values": [[...]]}  # Placeholder
}

# TEXT_MATRIX таблицы
table_data = {
    "type": "text_matrix",
    "source": "vlm_ocr",
    "data": {
        "flattened": [],  # Заполняется VLM-OCR
        "table_id": table.id,
        "location": table.location
    }
}
```

### 3.5. Изменения в существующем коде

**Новый файл:**
- `02_src/processing/skeleton_builder.py` — реализация SkeletonBuilder

**Обновить:**
- `02_src/processing/__init__.py` — экспорт SkeletonBuilder

---

## 4. План реализации

1. **Создать структуру модуля:**
   - `02_src/processing/skeleton_builder.py`
   - `02_src/processing/tests/test_skeleton_builder.py`
   - `02_src/processing/tests/fixtures/expected_skeleton.json`

2. **Реализовать SkeletonBuilder в skeleton_builder.py:**
   - Метод `build_skeleton()` — главный entry point
   - Метод `_build_node_tree()` — построение иерархии
   - Метод `_attach_tables()` — прикрепление таблиц

3. **Создать fixture expected_skeleton.json:**
   - Пример DocumentSkeleton на основе vlm_response_samples.json
   - Root + 4-5 узлов + 2 таблицы

4. **Реализовать unit тесты:**
   - `test_build_skeleton_basic()` — базовый случай
   - `test_build_skeleton_with_gaps()` — разрывы в нумерации
   - `test_attach_tables_to_sections()` — прикрепление таблиц
   - `test_table_outside_sections()` — таблицы вне разделов
   - `test_empty_headers()` — только root node
   - `test_nested_structure()` — deep nesting (level 3+)

5. **Интеграционные тесты:**
   - Полный pipeline: VLM-OCR mock → SkeletonBuilder → DocumentSkeleton

---

## 5. Технические критерии приемки

- [ ] TC-001: SkeletonBuilder реализован с методами `build_skeleton()`, `_build_node_tree()`, `_attach_tables()`
- [ ] TC-002: `build_skeleton()` создаёт DocumentSkeleton с root node
- [ ] TC-003: Все заголовки из structure.headers становятся Node
- [ ] TC-004: Parent-child отношения корректны для последовательной нумерации (1, 1.1, 1.2, 2)
- [ ] TC-005: Parent-child отношения корректны при разрывах (1, 1.3, 2)
- [ ] TC-006: Node.id генерируется из title (fallback на slugify)
- [ ] TC-007: PageRange вычисляется корректно (листья — 1 страница, родители — диапазон детей)
- [ ] TC-008: Таблицы на странице раздела прикрепляются к нему
- [ ] TC-009: Таблицы вне разделов прикрепляются к ближайшему по странице
- [ ] TC-010: Таблицы создаются как отдельные Node с type=TABLE
- [ ] TC-011: table_data заполняется в формате {type, source, data}
- [ ] TC-012: Unit тесты покрывают все методы (минимум 80% coverage)
- [ ] TC-013: Интеграционные тесты с mock VLM-OCR проходят

---

## 6. Важные детали для Developer

### Генерация Node.id из заголовка

**Алгоритм:**
1. Попытаться извлечь число из начала title: "1. Раздел" → "section_1"
2. Если нет числа — slugify: "Введение" → "vvedenie"
3. Проверить уникальность: если id уже есть → добавить суффикс

**Примеры:**
- "1. Раздел" → "section_1"
- "1.1. Подраздел" → "section_1.1"
- "Введение" → "vvedenie"
- "Приложение А" → "appendix_a"

**Код:**
```python
import re

def generate_id_from_title(title: str) -> str:
    # Попытка извлечь число
    match = re.match(r'(\d+(?:\.\d+)*)', title)
    if match:
        return f"section_{match.group(1)}"

    # Fallback: slugify
    slug = re.sub(r'[^\w]', '_', title.lower()).strip('_')
    return f"node_{slug}"
```

### Определение типа узла по level

```python
def level_to_node_type(level: int) -> NodeType:
    if level == 1:
        return NodeType.CHAPTER
    elif level >= 2:
        return NodeType.SECTION
    else:
        return NodeType.ROOT  # Не должно случиться
```

### Parent detection через стек

```python
# Инициализация
stack = {0: "root"}  # level -> node_id

# Для каждого заголовка
def find_parent(level: int, stack: Dict[int, str]) -> str:
    # Находим ближайший меньший level
    for l in range(level - 1, -1, -1):
        if l in stack:
            return stack[l]
    return "root"  # Fallback
```

### PageRange для родителей

**Логика:**
- Листья (без детей): PageRange(header.page, header.page)
- Родители: min(children.start) .. max(children.end)

**Реализация:**
```python
# Первая проходка — создать все nodes с page_range = (page, page)
# Вторая проходка — обновить родителей
for node_id, node in nodes.items():
    if node.children_ids:
        children = [nodes[cid] for cid in node.children_ids]
        start = min(c.page_range.start for c in children)
        end = max(c.page_range.end for c in children)
        node.page_range = PageRange(start, end)
```

### Прикрепление таблиц к node

**Алгоритм выбора target:**
```python
def find_table_target(table: Dict, nodes: Dict[str, Node]) -> str:
    table_page = table["page"]

    # 1. Точные совпадения по page_range
    candidates = [
        node for node in nodes.values()
        if node.type in [NodeType.CHAPTER, NodeType.SECTION]
        and node.page_range.start <= table_page <= node.page_range.end
    ]

    if candidates:
        # Выбираем самого специфичного (с наименьшим range)
        return min(candidates, key=lambda n: n.page_range.end - n.page_range.start).id

    # 2. Ближайший по странице
    return min(
        nodes.values(),
        key=lambda n: abs(n.page_range.start - table_page)
    ).id
```

### Content для всех узлов

**Базовая версия:**
```python
# Все узлы получают одинаковый content
full_text = document_data.text
# Можно добавить заголовок в начало content
for node in nodes.values():
    if node.type != NodeType.ROOT:
        node.content = f"{node.title}\n\n{full_text}"
```

### InternalStructure для узлов

**Формирование:**
```python
# Для каждого заголовка из structure.headers
internal_structure = {
    "raw": {
        header["title"]: {
            "level": header["level"],
            "page": header["page"]
        }
        for header in all_headers
        if header["level"] >= current_node.level + 1  # Только дети
    }
}
```

### Loglevel для SkeletonBuilder

Используй `logging.DEBUG` для детальной отладки алгоритма построения:
```python
logger.debug(f"Processing header: {title}, level: {level}, parent: {parent_id}")
logger.debug(f"Stack: {stack}")
```

### Структура проекта

```
02_src/processing/
├── skeleton_builder.py          # Основная реализация
└── tests/
    ├── test_skeleton_builder.py # Unit + интеграционные тесты
    └── fixtures/
        ├── vlm_response_samples.json        # Существующий
        └── expected_skeleton.json           # Новый fixture
```

### Ошибки и edge cases

**Обработка пустых данных:**
- `structure.headers = []` → создать только root node
- `tables = []` → пропустить этап прикрепления
- `text = ""` → content будет пустой строкой

**Обработка некорректных данных:**
- `level < 1` → treat as level 1
- `page < 1` → raise ValueError
- Дубликаты title → добавить суффикс к id

---

## 7. Тестовый план

### Unit тесты (test_skeleton_builder.py)

#### Базовые тесты
- `test_build_skeleton_creates_root()` — root node всегда создается
- `test_build_skeleton_basic_hierarchy()` — 1 → 1.1 → 2 иерархия
- `test_generate_id_from_title_numeric()` — "1. Раздел" → "section_1"
- `test_generate_id_from_title_text()` — "Введение" → "vvedenie"

#### Тесты на parent-child
- `test_parent_child_sequential()` — последовательная нумерация
- `test_parent_child_with_gaps()` — разрывы: 1, 1.3, 2
- `test_parent_child_deep_nesting()` — level 3+, level 4+

#### Тесты на page_range
- `test_page_range_leaf_nodes()` — листья имеют 1 страницу
- `test_page_range_parent_nodes()` — родители охватывают детей

#### Тесты на таблицы
- `test_attach_table_inside_section()` — таблица внутри раздела
- `test_attach_table_between_sections()` — таблица между разделами
- `test_attach_multiple_tables()` — несколько таблиц в одном разделе
- `test_table_node_structure()` — table node имеет правильный type и table_data

#### Edge cases
- `test_empty_headers()` — только root node
- `test_empty_text()` — content пустая строка
- `test_duplicate_titles()` — уникальные id с суффиксами

### Интеграционные тесты

#### Полный pipeline
```python
def test_full_pipeline_with_mock_vlm():
    # 1. Загрузить fixture vlm_response_samples.json
    # 2. Создать mock VLM-OCR
    # 3. Создать VLMOCRExtractor с mock
    # 4. Вызвать extract_full_document()
    # 5. Создать SkeletonBuilder
    # 6. Вызвать build_skeleton()
    # 7. Проверить DocumentSkeleton
```

### Fixtures

#### expected_skeleton.json
Формат на основе vlm_response_samples.json:
```json
{
  "document_id": "test_doc",
  "nodes": {
    "root": {
      "id": "root",
      "type": "root",
      "title": "Test Document",
      ...
    },
    "section_1": {
      "id": "section_1",
      "type": "chapter",
      "title": "1. Введение",
      "parent_id": "root",
      "children_ids": ["section_1.1", "section_1.2"],
      ...
    },
    "table_1": {
      "id": "table_1",
      "type": "table",
      "title": "Таблица 1. Финансовые показатели",
      "table_data": {...},
      "parent_id": "section_1.1",
      ...
    }
  }
}
```

---

## 8. Следующие шаги

После завершения:
- Задача 012 (Integration Tests) — полный pipeline тест
- Table Extractor (задача из Iteration 2) — извлечение NUMERIC таблиц из исходного файла
- Converter/Renderer уже реализованы, можно тестировать полный ingestion pipeline

---

**Готовность к передаче Developer:** Да, ТЗ достаточно детально для middle+ разработчика.
