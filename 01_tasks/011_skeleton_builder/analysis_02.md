# Техническое задание: Skeleton Builder - агрегация VLM-OCR результатов

**Версия:** 02
**Дата:** 2025-01-23
**Задача:** 011_skeleton_builder

---

## Изменения в версии 02

**На основе замечаний из review_01.md:**

1. **Добавлена детализация** по заполнению `internal_structure.raw` (Проблема 1)
2. **Обновлен список методов** класса SkeletonBuilder (Проблемы 2-3)
3. **Уточнен статус** fixture `expected_skeleton.json` (Проблема 4)

**Что сохранено из версии 01:**
- Общая архитектура и алгоритмы
- Стратегия parent-child детекции через стек
- Логика прикрепления таблиц

---

## 1. Анализ задачи

SkeletonBuilder — связующее звено между VLM-OCRExtractor и DocumentSkeleton. Превращает неструктурированные данные от VLM-OCR (DocumentData) в иерархический скелет документа (DocumentSkeleton).

**Ключевые проблемы:**
1. **Построение иерархии:** VLM-OCR возвращает плоский список заголовков с уровнями. Нужно восстановить дерево parent-child отношений.
2. **Разрывы в нумерации:** Заголовки могут быть не последовательными (1.1, 1.3, 2.1). Нужно корректно определять родителя по уровню.
3. **Прикрепление таблиц:** Таблицы нужно привязать к разделам по странице или близости к заголовку.
4. **Заполнение internal_structure:** Каждый узел должен знать о своих дочерних заголовках (только прямых потомков).

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

**Текущая реализация:**
- SkeletonBuilder реализован в `02_src/processing/skeleton_builder.py`
- Основная логика построения дерева работает корректно
- Parent-child отношения определяются верно
- Таблицы прикрепляются корректно
- **Проблема:** `internal_structure.raw` везде пустой словарь `{}`

**Стратегия моков:**
- Mock VLM-OCR возвращает предопределённый DocumentData из fixtures
- Тесты используют реальные DocumentSkeleton, не моки

---

## 3. Предлагаемое решение

### 3.1. Общий подход

**Двухэтапное построение:**
1. **Построение дерева:** Создать Node для каждого заголовка, установить parent-child связи по уровням
2. **Агрегация таблиц:** Прикрепить таблицы к ближайшим разделам по странице

**Третий этап (новый):**
3. **Заполнение internal_structure:** После построения дерева, заполнить `internal_structure.raw` для каждого узла информацией о прямых потомках

**Принципы:**
- Root node создаётся всегда, даже если document_id уже задан
- Каждый заголовок становится отдельным Node
- Parent-child определяется по уровню заголовка (level)
- Content узла — полный текст из DocumentData.text
- Tables прикрепляются к разделам по близости страницы
- `internal_structure.raw` содержит только прямых потомков (level + 1)

### 3.2. Компоненты

#### SkeletonBuilder (class)
- **Назначение:** Агрегация DocumentData в DocumentSkeleton
- **Расположение:** `02_src/processing/skeleton_builder.py`
- **Интерфейс (актуализирован):**
  - `async def build_skeleton(self, document_data: DocumentData, document_id: str) -> DocumentSkeleton`
  - `def _build_node_tree(self, structure: Dict[str, Any], full_text: str, document_id: str) -> Dict[str, Node]`
  - `def _attach_tables(self, skeleton: DocumentSkeleton, tables: List[Dict[str, Any]], nodes: Dict[str, Node]) -> None`
  - `def _update_parent_page_ranges(self, nodes: Dict[str, Node]) -> None`
  - `def _find_parent_by_level(self, level: int, stack: Dict[int, str]) -> str`
  - `def _find_table_target(self, table_page: int, nodes: Dict[str, Node]) -> Optional[str]`
  - `def _format_table_data(self, table: Dict[str, Any]) -> Dict[str, Any]`
  - `def _populate_internal_structure(self, nodes: Dict[str, Node]) -> None` — **НОВЫЙ**
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

#### InternalStructure.raw (выходной формат для каждого узла)

**Формат:**
```python
# Для узла "1. Раздел" (level 1) с детьми "1.1", "1.2" (level 2)
internal_structure = {
    "raw": {
        "1.1. Подраздел": {
            "level": 2,
            "page": 2,
            "node_id": "section_1.1"
        },
        "1.2. Еще subsection": {
            "level": 2,
            "page": 3,
            "node_id": "section_1.2"
        }
    }
}

# Для узла "1.1. Подраздел" (level 2) с детьми "1.1.1", "1.1.2" (level 3)
internal_structure = {
    "raw": {
        "1.1.1. Подподраздел": {
            "level": 3,
            "page": 4,
            "node_id": "section_1.1.1"
        },
        "1.1.2. Еще один": {
            "level": 3,
            "page": 5,
            "node_id": "section_1.1.2"
        }
    }
}

# Для листа (без детей)
internal_structure = {
    "raw": {}  # Пустой словарь
}
```

**Ключевые правила:**
1. Только прямые потомки (level = parent.level + 1)
2. Ключ — заголовок потомка (title)
3. Значение — dict с level, page, node_id
4. Листья (без детей) имеют пустой raw

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

#### Заполнение internal_structure.raw (НОВЫЙ АЛГОРИТМ)

**Когда вызывать:** После построения дерева, до прикрепления таблиц

**Алгоритм:**
```python
def _populate_internal_structure(self, nodes: Dict[str, Node]) -> None:
    """
    Заполняет internal_structure.raw для каждого узла.

    Для каждого узла находит прямых потомков (children_ids)
    и заполняет raw словарь информацией о них.

    Правила:
    - Только прямые потомки (не все потомки рекурсивно)
    - Ключ: заголовок потомка (title)
    - Значение: {level, page, node_id}
    - Листья (без детей) имеют пустой raw
    """
    for node_id, node in nodes.items():
        if not node.children_ids:
            # Лист — пустой словарь
            node.internal_structure.raw = {}
            continue

        # Заполняем для прямых потомков
        raw = {}
        for child_id in node.children_ids:
            if child_id not in nodes:
                continue

            child = nodes[child_id]

            # Пропускаем таблицы (они не в internal_structure)
            if child.type == NodeType.TABLE:
                continue

            # Добавляем в raw
            raw[child.title] = {
                "level": _extract_level_from_title(child.title),  # или хранить level отдельно
                "page": child.page_range.start,
                "node_id": child.id
            }

        node.internal_structure.raw = raw
```

**Детекция level из title (fallback):**
```python
def _extract_level_from_title(title: str) -> int:
    """
    Извлекает уровень из заголовка.

    "1. Раздел" → 1
    "1.1. Подраздел" → 2
    "2.3.4. Глубокий" → 4

    Если не удается извлечь — возвращает 0.
    """
    match = re.match(r'(\d+(?:\.\d+)*)', title)
    if match:
        level_str = match.group(1)
        return level_str.count('.') + 1
    return 0
```

**Важные детали:**
1. Таблицы (type=TABLE) **НЕ** добавляются в `internal_structure.raw`
2. Если у узла нет детей (кроме таблиц) → raw = {}
3. Root node может иметь потомков в internal_structure
4. Level можно либо хранить отдельно при создании узла, либо извлекать из title

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
   - **Важно:** таблицы НЕ добавляются в internal_structure родителя

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

**Файл:** `02_src/processing/skeleton_builder.py`

**Изменения:**
1. Добавить метод `_populate_internal_structure()`
2. Вызвать `_populate_internal_structure()` в `build_skeleton()` после `_build_node_tree()`, до `_attach_tables()`
3. Добавить поле `_level` в Node или хранить level при создании (для заполнения internal_structure)

**Новая последовательность в build_skeleton():**
```python
async def build_skeleton(self, document_data, document_id) -> DocumentSkeleton:
    # 1. Строим дерево узлов из заголовков
    nodes = self._build_node_tree(...)

    # 2. Заполняем internal_structure для каждого узла
    self._populate_internal_structure(nodes)

    # 3. Создаем DocumentSkeleton
    skeleton = DocumentSkeleton(document_id=document_id, nodes=nodes)

    # 4. Прикрепляем таблицы
    if document_data.tables:
        self._attach_tables(skeleton, document_data.tables, nodes)

    return skeleton
```

---

## 4. План реализации

**Это обновленная версия анализа. Для Developer:**

1. **Добавить метод _populate_internal_structure():**
   - Проход по всем nodes
   - Для каждого узла найти прямых потомков (children_ids)
   - Заполнить internal_structure.raw информацией о детях
   - Пропускать таблицы (type=TABLE)

2. **Обновить build_skeleton():**
   - Добавить вызов `_populate_internal_structure(nodes)` после `_build_node_tree()`
   - Перед `_attach_tables()`

3. **Опционально: Добавить хранение level:**
   - Либо добавить поле `level` в Node
   - Либо извлекать level из title в `_populate_internal_structure()`

4. **Обновить тесты:**
   - Добавить проверки на заполнение `internal_structure.raw`
   - Проверить что таблицы не попадают в internal_structure
   - Проверить что только прямые потомки в raw

5. **Fixture expected_skeleton.json:**
   - Создать опционально (не блокирует)
   - Использовать для валидации формата

---

## 5. Технические критерии приемки (обновленные)

- [x] TC-001: SkeletonBuilder реализован с методами (список актуализирован)
- [x] TC-002: `build_skeleton()` создаёт DocumentSkeleton с root node
- [x] TC-003: Все заголовки из structure.headers становятся Node
- [x] TC-004: Parent-child отношения корректны для последовательной нумерации
- [x] TC-005: Parent-child отношения корректны при разрывах
- [x] TC-006: Node.id генерируется из title (fallback на slugify)
- [x] TC-007: PageRange вычисляется корректно
- [x] TC-008: Таблицы на странице раздела прикрепляются к нему
- [x] TC-009: Таблицы вне разделов прикрепляются к ближайшему по странице
- [x] TC-010: Таблицы создаются как отдельные Node с type=TABLE
- [ ] TC-011: **table_data заполняется в формате {type, source, data}** — частично выполнено, нужно internal_structure
- [ ] TC-011a: **internal_structure.raw заполнен для узлов с детьми** — **НОВЫЙ**
- [ ] TC-011b: **internal_structure.raw пустой для листьев** — **НОВЫЙ**
- [ ] TC-011c: **таблицы не попадают в internal_structure.raw** — **НОВЫЙ**
- [x] TC-012: Unit тесты покрывают все методы (21 тест)
- [x] TC-013: Интеграционные тесты с mock VLM-OCR проходят
- [ ] TC-014: **Добавлены тесты на internal_structure** — **НОВЫЙ**

---

## 6. Важные детали для Developer

### Реализация _populate_internal_structure

**Сигнатура:**
```python
def _populate_internal_structure(self, nodes: Dict[str, Node]) -> None:
    """Заполняет internal_structure.raw для каждого узла."""
```

**Логика:**
```python
for node_id, node in nodes.items():
    raw = {}

    for child_id in node.children_ids:
        child = nodes.get(child_id)
        if not child or child.type == NodeType.TABLE:
            continue

        # Извлекаем level из title
        level = self._extract_level_from_title(child.title)

        raw[child.title] = {
            "level": level,
            "page": child.page_range.start,
            "node_id": child.id
        }

    node.internal_structure.raw = raw
```

### Извлечение level из title

**Оптимизация:** Вместо извлечения level из title каждый раз, можно:
1. Хранить level в Node при создании
2. Передавать level в `_populate_internal_structure`

**Вариант с хранением level:**
```python
# При создании узла в _build_node_tree()
node = Node(
    ...
    # Добавить level в Node (требует обновление dataclass)
    level=level,  # НОВОЕ ПОЛЕ
    ...
)
```

**Вариант с извлечением:**
```python
def _extract_level_from_title(self, title: str) -> int:
    match = re.match(r'(\d+(?:\.\d+)*)', title)
    if match:
        return match.group(1).count('.') + 1
    return 0
```

### Проверка в тестах

**Новые тесты:**
```python
def test_internal_structure_parent_with_children():
    """Узел с детьми имеет заполненный internal_structure.raw"""
    builder = SkeletonBuilder()
    # ... создать DocumentData с иерархией 1 → 1.1, 1.2

    skeleton = await builder.build_skeleton(doc_data, "test")

    section_1 = await skeleton.get_node("section_1")
    assert len(section_1.internal_structure.raw) == 2
    assert "1.1. Подраздел" in section_1.internal_structure.raw
    assert "1.2. Еще subsection" in section_1.internal_structure.raw

def test_internal_structure_leaf_empty():
    """Лист имеет пустой internal_structure.raw"""
    section_1_1 = await skeleton.get_node("section_1.1")
    assert section_1_1.internal_structure.raw == {}

def test_internal_structure_tables_excluded():
    """Таблицы не попадают в internal_structure родителя"""
    # После прикрепления таблиц
    section_1 = await skeleton.get_node("section_1")
    for title in section_1.internal_structure.raw:
        assert title.startswith("Table") is False
```

### Fixture expected_skeleton.json

**Статус:** Опционально, не блокирует

**Если создавать:**
- Формат на основе vlm_response_samples.json
- Должен соответствовать схеме DocumentSkeleton
- Использовать для валидации формата в тестах

**Пример структуры:**
```json
{
  "document_id": "test_doc",
  "nodes": {
    "root": {
      "id": "root",
      "type": "root",
      "title": "Test Document",
      "internal_structure": {
        "raw": {
          "1. Введение": {"level": 1, "page": 1, "node_id": "section_1"},
          "2. Основные требования": {"level": 1, "page": 4, "node_id": "section_2"}
        }
      }
    },
    "section_1": {
      "id": "section_1",
      "internal_structure": {
        "raw": {
          "1.1. Общие положения": {"level": 2, "page": 2, "node_id": "section_1.1"}
        }
      }
    }
  }
}
```

---

## 7. Сводка изменений

### Из analysis_01.md (сохранить):
- Общая архитектура и алгоритмы
- Parent-child детекция через стек
- Логика прикрепления таблиц
- Структуры данных DocumentData, Node, DocumentSkeleton

### Новое в analysis_02.md:
- **Детализация** заполнения `internal_structure.raw` (раздел 3.4)
- **Новый метод** `_populate_internal_structure()`
- **Обновленная последовательность** в `build_skeleton()`
- **Новые критерии** TC-011a, TC-011b, TC-011c, TC-014
- **Актуализированный список** методов класса

### Уточнения:
- Fixture expected_skeleton.json — опционально, не блокирует
- Метод `_find_parent_by_level` — положительное изменение, включен в интерфейс
- Аннотации типов в `_build_node_tree` — уже корректны в коде

---

## 8. Следующие шаги

После завершения:
- Задача 012 (Integration Tests) — полный pipeline тест
- Table Extractor (задача из Iteration 2) — извлечение NUMERIC таблиц из исходного файла
- Converter/Renderer уже реализованы, можно тестировать полный ingestion pipeline

---

**Готовность к передаче Developer:** Да, ТЗ обновлено с учетом всех замечаний из review_01.md.
