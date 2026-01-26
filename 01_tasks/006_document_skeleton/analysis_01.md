# Техническое задание: Document Skeleton - структуры данных

**Версия:** 01
**Дата:** 2025-01-23
**Задача:** 006_document_skeleton

---

## 1. Анализ задачи

Задача 006 — создание фундаментального слоя данных для системы Document Skeleton. Все остальные модули (индексация, снэпшоты, диспетчер) зависят от этого интерфейса.

Необходимо реализовать:
1. **Data classes** для представления узлов документа (NodeType, PageRange, InternalStructure, Node)
2. **DocumentSkeleton** класс с интерфейсом навигации по иерархической структуре
3. Unit тесты и test fixtures

**Важно:** Эта задача — только структуры данных и базовый интерфейс. Логика построения скелета из VLM-OCR будет в задаче 011, сохранение/загрузка — в задаче 007.

---

## 2. Текущее состояние

**Существующий код:** Папка `02_src/` пуста. Это первая задача с реализацией кода.

**Зависимости:**
- Задача 004 (SGR Agent Core) — для понимания паттернов, но не используется напрямую
- ADR-001 (Форматы документов) — определяет обработку числовых таблиц через Pandas
- ADR-002 (Мультидокументность) — каждый файл = отдельный Document

**Библиотеки:**
- `dataclasses` (stdlib) — для структур данных
- `hashlib` (stdlib) — для хэширования содержимого
- `typing` (stdlib) — для типов
- `pytest` — для тестов
- `pandas` — optional для table_data (NUMERIC таблицы)

---

## 3. Предлагаемое решение

### 3.1. Общий подход

**In-memory хранилище:** DocumentSkeleton хранит узлы в `Dict[str, Node]` (in-memory). Это упрощает первую версию и соответствует принципу "сначала структуры, потом логика".

**Хэширование:** SHA-256 от содержимого узла для отслеживания изменений. Для детерминированных тестов — injectable hash function.

**Сериализация:** JSON-совместимые структуры для future интеграции с File Storage (задача 007).

### 3.2. Компоненты

#### NodeType (Enum)
- **Назначение:** Типизация узлов документа
- **Значения:** CHAPTER, SECTION, APPENDIX, TABLE, FIGURE, ROOT
- **Зависимости:** `str, Enum` из `enum`

#### PageRange (dataclass)
- **Назначение:** Диапазон страниц в исходном документе
- **Поля:** `start: int`, `end: int`
- **Валидация:** `start <= end`, оба `>= 1`
- **Методы:** `__post_init__` для валидации

#### InternalStructure (dataclass)
- **Назначение:** Иерархия подпунктов внутри узла (3.1, 3.2, 3.2.1)
- **Поля:** `raw: Dict[str, Any]`
- **Формат raw:** см. пример в task_brief
- **Зависимости:** `Dict`, `Any` из `typing`

#### Node (dataclass)
- **Назначение:** Узел скелета документа
- **Поля:**
  - `id: str` — уникальный ID (например "section_3")
  - `type: NodeType` — тип узла
  - `title: Optional[str]` — заголовок
  - `content: str` — полный текст
  - `page_range: PageRange` — страницы
  - `parent_id: Optional[str]` — родитель
  - `children_ids: List[str]` — дочерние узлы
  - `internal_structure: InternalStructure` — подпункты
  - `explicit_refs: List[str]` — явные ссылки
  - `hash: str` — хэш содержимого
  - `table_data: Optional[Dict[str, Any]] = None` — для числовых таблиц
- **Методы:** `__post_init__` для вычисления хэша
- **Зависимости:** все вышеперечисленные + `List`, `Optional`

#### DocumentSkeleton (class)
- **Назначение:** Интерфейс доступа к скелету документа
- **Поля:**
  - `document_id: str`
  - `_nodes: Dict[str, Node]` — приватное хранилище
- **Конструктор:** Принимает `document_id` и опционально `nodes: Dict[str, Node]`
- **Методы:**
  - `async def get_node(self, node_id: str) -> Optional[Node]`
  - `async def get_root(self) -> Node`
  - `async def get_children(self, node_id: str) -> List[Node]`
  - `async def find_by_title(self, title_pattern: str) -> List[Node]` (regex поиск)
  - `async def find_by_page_range(self, start: int, end: int) -> List[Node]`
  - `async def resolve_reference(self, ref: str) -> Optional[Node]` (базовая версия)
  - `async def get_document_hash(self) -> str`

### 3.3. Структуры данных

#### Node.table_data формат
```python
# Для NUMERIC таблиц (из исходника через Pandas)
table_data = {
    "type": "numeric",
    "source": "original_file",  # Excel/PDF
    "data": {
        # DataFrame-совместимая структура
        # В этой задаче — placeholder, реальная интеграция в Table Extractor
        "columns": [...],
        "index": [...],
        "values": [[...]]
    }
}

# Для TEXT_MATRIX таблиц (через VLM-OCR)
table_data = {
    "type": "text_matrix",
    "source": "vlm_ocr",
    "data": {
        "flattened": [
            "Орган 'Правление' для 'Сделки до 1 млрд': принимает решение единолично",
            "..."
        ]
    }
}
```

### 3.4. Ключевые алгоритмы

#### Хэширование содержимого узла
```python
def compute_hash(content: str, table_data: Optional[Dict]) -> str:
    """SHA-256 от content + str(table_data)"""
    import hashlib
    data = content + str(table_data or "")
    return hashlib.sha256(data.encode()).hexdigest()
```

#### Поиск по заголовку (regex)
```python
def find_by_title(title_pattern: str) -> List[Node]:
    """Возвращает все узлы, где title совпадает с regex"""
    import re
    pattern = re.compile(title_pattern)
    return [node for node in self._nodes.values()
            if node.title and pattern.search(node.title)]
```

#### Поиск по диапазону страниц
```python
def find_by_page_range(start: int, end: int) -> List[Node]:
    """Возвращает узлы, пересекающие диапазон [start, end]"""
    return [node for node in self._nodes.values()
            if not (node.page_range.end < start or node.page_range.start > end)]
```

#### Базовый resolve_reference
```python
async def resolve_reference(self, ref: str) -> Optional[Node]:
    """
    Базовая версия: ищет по title или id.
    Полная версия с DocumentCollection — позже.
    """
    # Пытается найти по id
    node = await self.get_node(ref)
    if node:
        return node

    # Пытается найти по title (частичное совпадение)
    candidates = await self.find_by_title(ref)
    return candidates[0] if candidates else None
```

### 3.5. Изменения в существующем коде

**Не применимо** — это первая задача с кодом.

---

## 4. План реализации

1. **Создать структуру проекта:**
   - `02_src/document/__init__.py`
   - `02_src/document/skeleton.py`
   - `02_src/document/tests/__init__.py`
   - `02_src/document/tests/test_skeleton.py`
   - `02_src/document/tests/fixtures/sample_skeleton.json`
   - `04_logs/parsing/` (папка для логов)

2. **Реализовать data classes в skeleton.py:**
   - NodeType enum
   - PageRange dataclass с валидацией
   - InternalStructure dataclass
   - Node dataclass с вычислением хэша
   - DocumentSkeleton class с методами

3. **Создать fixture в tests/fixtures/sample_skeleton.json:**
   - Пример скелета Положения ЦБ 714-П
   - Root node + 2-3 дочерних узла
   - Один узел с table_data (numeric)

4. **Реализовать unit тесты в test_skeleton.py:**
   - Тесты создания всех data classes
   - Тесты валидации PageRange
   - Тесты вычисления хэша
   - Тесты всех методов DocumentSkeleton
   - Тесты с mock hash function для детерминизма

5. **Добавить логирование:**
   - Логировать операции создания/модификации узлов
   - Логи в `04_logs/parsing/skeleton.log`

---

## 5. Технические критерии приемки

- [ ] TC-001: Все data classes (NodeType, PageRange, InternalStructure, Node) реализованы
- [ ] TC-002: DocumentSkeleton реализует все методы из интерфейса
- [ ] TC-003: PageRange валидирует `start <= end`
- [ ] TC-004: Node вычисляет хэш содержимого в `__post_init__`
- [ ] TC-005: `get_node` возвращает `None` для несуществующего id
- [ ] TC-006: `get_root` выбрасывает исключение если root не найден
- [ ] TC-007: `find_by_title` ищет по regex, возвращает пустой список если нет совпадений
- [ ] TC-008: `find_by_page_range` находит пересекающие узлы
- [ ] TC-009: `resolve_reference` находит по id или title
- [ ] TC-010: `get_document_hash` возвращает хэш всех узлов
- [ ] TC-011: Unit тесты покрывают все методы (минимум 80% coverage)
- [ ] TC-012: Fixture sample_skeleton.json соответствует схеме
- [ ] TC-013: Логи пишутся в `04_logs/parsing/skeleton.log`

---

## 6. Важные детали для Developer

### Детерминизм хэшей в тестах
Используй dependency injection для hash function в тестах:
```python
# В production
hash_func = hashlib.sha256

# В тестах
mock_hash = lambda x: "mock_" + str(len(x))
node = Node(..., _hash_func=mock_hash)
```

### Node.__post_init__
Хэш должен вычисляться **после** инициализации всех полей:
```python
def __post_init__(self):
    if not self.hash:
        self.hash = compute_hash(self.content, self.table_data)
```

### Обработка пустых значений
- `title` может быть `None` (например для root)
- `table_data` по умолчанию `None`
- `internal_structure.raw` может быть пустым dict

### Regex в find_by_title
Используй `re.compile` с флагами `re.IGNORECASE` для более гибкого поиска.

### Логирование
Используй Python `logging` module:
```python
import logging
logger = logging.getLogger(__name__)
logger.info(f"Created node {node_id}")
```

### Структура проекта для задачи 006
```
02_src/
└── document/
    ├── __init__.py           # Экспорт NodeType, Node, DocumentSkeleton
    ├── skeleton.py           # Основная реализация
    └── tests/
        ├── __init__.py
        ├── test_skeleton.py  # Unit тесты
        └── fixtures/
            └── sample_skeleton.json

04_logs/
└── parsing/
    └── skeleton.log          # Логи операций
```

### Fixture формат
sample_skeleton.json должен быть десериализуем в Dict[str, Any] и использоваться для создания DocumentSkeleton:
```python
import json
from document.skeleton import DocumentSkeleton, Node

with open("fixtures/sample_skeleton.json") as f:
    data = json.load(f)

skeleton = DocumentSkeleton(
    document_id=data["document_id"],
    nodes={nid: Node(**n) for nid, n in data["nodes"].items()}
)
```

### resolve_reference ограничения
Базовая версия работает только в пределах одного документа:
- Не поддерживает ссылки на другие документы (требует DocumentCollection)
- Не понимает сложные паттерны типа "см. выше/ниже"
- Ищет только по точному id или частичному совпадению title

### JSON сериализация
Data classes должны быть JSON-совместимы (все поля — простые типы). Для future интеграции с File Storage (задача 007).

### Типы для typing
Используй:
- `from typing import Dict, List, Optional, Any`
- `from enum import Enum`
- `from dataclasses import dataclass, field`

---

## 7. Ключевые решения (по требованию из task_brief)

### 7.1. Организация внутреннего хранилища узлов
**Решение:** `Dict[str, Node]` в приватном поле `_nodes` класса DocumentSkeleton.

**Обоснование:**
- Простота и прозрачность для первой версии
- O(1) доступ по id
- Легко сериализуется в JSON
- Enough для dozens/hundreds of nodes (типичный документ)

**Future considerations:** Если понадобится индексация по title, page_range — добавить secondary indexes в виде Dict.

### 7.2. Вычисление хэша содержимого
**Решение:** SHA-256 от `content + str(table_data or "")` через `hashlib.sha256`.

**Обоснование:**
- SHA-256 — стандарт, детерминирован
- Учитывает и текст, и табличные данные
- Если table_data None → не влияет на хэш
- Быстро для типичных размеров контента (даже сотни страниц)

**Альтернативы рассмотрены:**
- MD5 — менее надежен
- CRC32 — слишком слабый
- BLAKE3 — избыточен для задачи

### 7.3. Формат JSON для сериализации
**Решение:** Плоский dict по аналогии с fixture из task_brief:
```json
{
  "document_id": "...",
  "nodes": {
    "node_id_1": {...fields...},
    "node_id_2": {...fields...}
  }
}
```

**Обоснование:**
- Прямое мапинг на внутреннюю структуру `_nodes`
- Легко десериализовать в `Dict[str, Node]`
- Читаем для humans
- Совместим с future File Storage

**Nested vs flat:**
- Nested (иерархический) — сложнее десериализовать
- Flat — проще, дает O(1) доступ по id
- Выбор: Flat with parent_id/children_ids для навигации

---

## 8. Тестовый план

### Unit тесты (test_skeleton.py)

#### Тесты PageRange
- `test_page_range_valid()` — создание валидного диапазона
- `test_page_range_invalid()` — исключение при start > end
- `test_page_range_negative()` — исключение при отрицательных значениях

#### Тесты Node
- `test_node_creation()` — создание всех полей
- `test_node_hash_computation()` — хэш вычисляется в __post_init__
- `test_node_hash_with_table_data()` — хэш учитывает table_data
- `test_node_hash_deterministic()` — одинаковый контент → одинаковый хэш

#### Тесты DocumentSkeleton
- `test_skeleton_creation()` — создание с nodes dict
- `test_get_node_exists()` — получение существующего узла
- `test_get_node_not_exists()` — None для несуществующего
- `test_get_root()` — получение root узла
- `test_get_root_missing()` — исключение если root отсутствует
- `test_get_children()` — получение дочерних узлов
- `test_find_by_title_regex()` — поиск по паттерну
- `test_find_by_title_no_match()` — пустой список если нет совпадений
- `test_find_by_page_range()` — поиск по диапазону
- `test_find_by_page_range_no_overlap()` — пустой список если нет пересечения
- `test_resolve_reference_by_id()` — резолв по id
- `test_resolve_reference_by_title()` — резолв по title
- `test_resolve_reference_not_found()` — None если не найден
- `test_get_document_hash()` — хэш всего документа

### Фикстуры для тестов

#### Mock hash function
```python
@pytest.fixture
def mock_hash():
    return lambda x: f"hash_{len(x)}"
```

#### Sample skeleton
```python
@pytest.fixture
def sample_skeleton():
    return DocumentSkeleton(
        document_id="test_doc",
        nodes={
            "root": Node(
                id="root",
                type=NodeType.ROOT,
                title="Test Document",
                content="Full content...",
                page_range=PageRange(1, 10),
                parent_id=None,
                children_ids=["section_1"],
                internal_structure=InternalStructure(raw={}),
                explicit_refs=[],
                hash="hash_123"
            ),
            # ... more nodes
        }
    )
```

---

## 9. Следующие шаги

После завершения этой задачи:
- Задача 007 (File Storage) будет использовать DocumentSkeleton для сериализации/десериализации
- Задача 011 (Skeleton Builder) будет создавать экземпляры Node и DocumentSkeleton из VLM-OCR данных

---

**Готовность к передаче Developer:** Да, ТЗ достаточно детально для middle+ разработчика.
