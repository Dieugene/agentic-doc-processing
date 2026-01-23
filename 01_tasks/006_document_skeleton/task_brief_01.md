# Задача 006: Document Skeleton - структуры данных

## Что нужно сделать

Реализовать структуры данных для физического представления документа (Document Skeleton):
1. Node и связанные data classes (NodeType, PageRange, InternalStructure)
2. DocumentSkeleton интерфейс
3. FileStorage для сохранения/загрузки скелетов
4. Тестовые fixtures с примером скелета

## Зачем

Document Skeleton - фундаментальный слой данных. Все остальные модули (индексация, снэпшоты, диспетчер) зависят от него. Скелет обеспечивает:
- Физическое представление структуры документа (разделы, приложения, таблицы)
- Навигацию по документу (parent/children связи)
- Резолвинг ссылок между разделами
- Отслеживание изменений (хэширование)

## Acceptance Criteria

- [ ] AC-001: Реализованы все data classes (Node, PageRange, InternalStructure, NodeType)
- [ ] AC-002: DocumentSkeleton интерфейс реализован (все методы)
- [ ] AC-003: FileStorage для сохранения/загрузки JSON
- [ ] AC-004: Хэширование содержимого узлов
- [ ] AC-005: Unit тесты для DocumentSkeleton методов
- [ ] AC-006: Тестовый fixture с примером документа
- [ ] AC-007: Логи операций парсинга в 04_logs/parsing/

## Контекст

**Implementation Plan:**
- `00_docs/architecture/implementation_plan.md` - Iteration 2, модуль Document Skeleton

**Архитектура:**
- `00_docs/architecture/overview.md` - раздел 3.1 "Слой 1: Структурный скелет (Document Skeleton)"

**Интерфейсы и контракты:**

```python
from typing import List, Dict, Optional
from enum import Enum
from dataclasses import dataclass

class NodeType(str, Enum):
    CHAPTER = "chapter"      # Глава (1., 2., ...)
    SECTION = "section"      # Раздел
    APPENDIX = "appendix"    # Приложение
    TABLE = "table"          # Таблица
    FIGURE = "figure"        # Рисунок
    ROOT = "root"            # Корневой узел

@dataclass
class PageRange:
    start: int
    end: int

@dataclass
class InternalStructure:
    """Иерархия подпунктов внутри узла (1.1, 1.1.1, ...)"""
    raw: Dict[str, Any]

@dataclass
class Node:
    """Узел скелета документа"""
    id: str
    type: NodeType
    title: Optional[str]
    content: str
    page_range: PageRange
    parent_id: Optional[str]
    children_ids: List[str]
    internal_structure: InternalStructure
    explicit_refs: List[str]
    hash: str

class DocumentSkeleton:
    """Интерфейс доступа к скелету документа"""

    document_id: str

    async def get_node(self, node_id: str) -> Optional[Node]:
        """Получить узел по ID"""
        pass

    async def get_root(self) -> Node:
        """Получить корневой узел"""
        pass

    async def get_children(self, node_id: str) -> List[Node]:
        """Получить прямых потомков"""
        pass

    async def find_by_title(self, title_pattern: str) -> List[Node]:
        """Найти узлы по паттерну заголовка"""
        pass

    async def find_by_page_range(self, start: int, end: int) -> List[Node]:
        """Найти узлы по диапазону страниц"""
        pass

    async def resolve_reference(self, ref: str) -> Optional[Node]:
        """Резолв явной ссылки ("см. п. 5.3", "Приложение Б")"""
        pass

    async def get_document_hash(self) -> str:
        """Хэш всего документа"""
        pass
```

```python
from pathlib import Path

class FileStorage:
    """Файловое хранилище для скелетов и индексов"""

    base_path: Path

    async def save_skeleton(self, document_id: str, skeleton: DocumentSkeleton):
        """Сохранить скелет в JSON"""
        pass

    async def load_skeleton(self, document_id: str) -> Optional[DocumentSkeleton]:
        """Загрузить скелет из JSON"""
        pass

    def document_exists(self, document_id: str) -> bool:
        """Проверить существование документа"""
        pass
```

**Структура проекта:**

```
02_src/
├── document/
│   ├── __init__.py
│   ├── skeleton.py          # Node, DocumentSkeleton
│   └── storage.py           # FileStorage
├── tests/
│   ├── test_skeleton.py
│   └── fixtures/
│       └── sample_skeleton.json
04_logs/
└── parsing/
    └── (логи операций)
```

**Пример fixture (tests/fixtures/sample_skeleton.json):**

```json
{
  "document_id": "doc_sample",
  "nodes": {
    "root": {
      "id": "root",
      "type": "root",
      "title": "Документ",
      "content": "Полный текст...",
      "page_range": {"start": 1, "end": 50},
      "parent_id": null,
      "children_ids": ["section_1"],
      "internal_structure": {"raw": {}},
      "explicit_refs": [],
      "hash": "abc123"
    },
    "section_1": {
      "id": "section_1",
      "type": "chapter",
      "title": "1. Раздел",
      "content": "Текст раздела...",
      "page_range": {"start": 1, "end": 10},
      "parent_id": "root",
      "children_ids": [],
      "internal_structure": {"raw": {"1.1": {"title": "Подраздел", "page": 2}}},
      "explicit_refs": [],
      "hash": "def456"
    }
  }
}
```

**Существующий код для reference:**
- Отсутствует (первая задача в слое данных)

**Другие ссылки:**
- Python dataclasses: https://docs.python.org/3/library/dataclasses.html
- hashlib: https://docs.python.org/3/library/hashlib.html

## Примечания для Analyst

**Важно:** Детали реализации методов (например, конкретный алгоритм резолвинга ссылок) определяются на этапе создания технического задания.

**Ключевые решения для проработки:**
1. Какой формат использовать для хранения скелетов? (JSON, pickle, etc.)
2. Как реализовать резолвинг ссылок? (простой regex или полноценный парсер)
3. Как организовать внутреннее хранилище узлов? (Dict, custom index и т.д.)

## Зависимости

- Задача 004: SGR Agent Core (для понимания паттернов, но не обязательно)

## Следующие задачи

После завершения этой задачи:
- Задача 007: File Storage (может быть частью этой задачи)
- Задача 008: Document Parser (использует DocumentSkeleton)
- Задача 010: Navigation Index (использует DocumentSkeleton)
