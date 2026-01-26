# Задача 006: Document Skeleton - структуры данных

## Что нужно сделать

Реализовать структуры данных для физического представления документа (DocumentSkeleton).

## Зачем

Document Skeleton - фундаментальный слой данных. Все остальные модули (индексация, снэпшоты, диспетчер) зависят от него. Скелет обеспечивает:
- Иерархическое представление структуры документа
- Навигацию по разделам
- Хранение содержимого узлов
- Отслеживание изменений (хэширование)

## Acceptance Criteria

- [ ] AC-001: Реализованы все data classes (NodeType, PageRange, InternalStructure, Node)
- [ ] AC-002: DocumentSkeleton интерфейс со всеми методами
- [ ] AC-003: Node.table_data для хранения числовых таблиц (Pandas DataFrame compatible)
- [ ] AC-004: Хэширование содержимого узлов (для инвалидации)
- [ ] AC-005: Unit тесты для всех методов
- [ ] AC-006: Тестовый fixture с примером скелета
- [ ] AC-007: Логи в 04_logs/parsing/

## Контекст

**Архитектурные решения (ADR):**

**ADR-002: Мультидокументность**
- Каждый файл = отдельный Document
- DocumentCollection для логической группировки (будущая задача)
- Ссылки между файлами резолвятся через DocumentCollection

**ADR-001: Форматы документов**
- VLM-OCR используется для ВСЕХ форматов
- Таблицы классифицируются: NUMERIC (числовые) и TEXT_MATRIX (текстовые)
- Числовые таблицы извлекаются из исходного файла → Pandas

**Интерфейсы и контракты:**

```python
from typing import List, Dict, Optional, Set
from enum import Enum
from dataclasses import dataclass, field

class NodeType(str, Enum):
    """Тип узла в скелете документа"""
    CHAPTER = "chapter"      # Глава (1., 2., ...)
    SECTION = "section"      # Раздел (1.1, 1.2, ...)
    APPENDIX = "appendix"    # Приложение
    TABLE = "table"          # Таблица
    FIGURE = "figure"        # Рисунок/схема
    ROOT = "root"            # Корневой узел

@dataclass
class PageRange:
    """Диапазон страниц в исходном документе"""
    start: int
    end: int

@dataclass
class InternalStructure:
    """Иерархия подпунктов внутри узла"""
    raw: Dict[str, Any]
    # Пример для раздела 3:
    # {
    #   "3.1": {"title": "Общие требования", "page": 15},
    #   "3.2": {"title": "Сроки представления", "page": 18},
    #   "3.2.1": {"title": "Ежемесячная", "page": 18}
    # }

@dataclass
class Node:
    """Узел скелета документа"""
    id: str                          # уникальный ID (например "section_3")
    type: NodeType                   # тип узла
    title: Optional[str]             # заголовок ("3. Требования к отчётности")
    content: str                     # полный текст узла
    page_range: PageRange            # страницы в исходном документе
    parent_id: Optional[str]         # ID родительского узла
    children_ids: List[str]          # ID дочерних узлов
    internal_structure: InternalStructure  # иерархия подпунктов
    explicit_refs: List[str]         # явные ссылки ("см. п. 5.3", "Приложение Б")
    hash: str                        # хэш содержимого (для инвалидации)
    table_data: Optional[Dict[str, Any]] = None  # для числовых таблиц (Pandas)

class DocumentSkeleton:
    """Интерфейс доступа к скелету документа

    Предоставляет навигацию по иерархической структуре документа.
    """

    document_id: str

    async def get_node(self, node_id: str) -> Optional[Node]:
        """Получить узел по ID"""
        pass

    async def get_root(self) -> Node:
        """Получить корневой узел документа"""
        pass

    async def get_children(self, node_id: str) -> List[Node]:
        """Получить прямых потомков узла"""
        pass

    async def find_by_title(self, title_pattern: str) -> List[Node]:
        """Найти узлы по паттерну заголовка (regex)"""
        pass

    async def find_by_page_range(self, start: int, end: int) -> List[Node]:
        """Найти узлы, пересекающие диапазон страниц"""
        pass

    async def resolve_reference(self, ref: str) -> Optional[Node]:
        """
        Резолв явной ссылки ("см. п. 5.3", "Приложение Б").

        Возвращает Node или None если ссылка неразрешима.
        Для полноты реализации потребуется DocumentCollection.
        """
        pass

    async def get_document_hash(self) -> str:
        """Хэш всего документа для отслеживания изменений"""
        pass
```

**Структура проекта:**

```
02_src/
├── document/
│   ├── __init__.py
│   ├── skeleton.py          # NodeType, PageRange, InternalStructure, Node, DocumentSkeleton
│   └── tests/
│       ├── test_skeleton.py
│       └── fixtures/
│           └── sample_skeleton.json
04_logs/
└── parsing/
    └── (логи операций с DocumentSkeleton)
```

**Пример fixture (tests/fixtures/sample_skeleton.json):**

```json
{
  "document_id": "doc_714p_sample",
  "root": {
    "id": "root",
    "type": "root",
    "title": "Положение ЦБ РФ 714-П",
    "content": "Полный текст документа...",
    "page_range": {"start": 1, "end": 50},
    "parent_id": null,
    "children_ids": ["section_3", "appendix_a"],
    "internal_structure": {"raw": {}},
    "explicit_refs": [],
    "hash": "abc123"
  },
  "nodes": {
    "section_3": {
      "id": "section_3",
      "type": "chapter",
      "title": "3. Требования к отчётности",
      "content": "3. Требования к отчётности\n3.1. Общие требования...",
      "page_range": {"start": 15, "end": 42},
      "parent_id": "root",
      "children_ids": [],
      "internal_structure": {
        "raw": {
          "3.1": {"title": "Общие требования", "page": 15},
          "3.2": {"title": "Сроки представления", "page": 18},
          "3.2.1": {"title": "Ежемесячная", "page": 18}
        }
      },
      "explicit_refs": ["ref:appendix:a"],
      "hash": "def456"
    },
    "appendix_a": {
      "id": "appendix_a",
      "type": "appendix",
      "title": "Приложение А. Формы отчётности",
      "content": "Таблицы...",
      "page_range": {"start": 43, "end": 50},
      "parent_id": "root",
      "children_ids": [],
      "internal_structure": {"raw": {}},
      "explicit_refs": [],
      "hash": "ghi789",
      "table_data": {
        "type": "numeric",
        "source": "original_file",
        "data": "..."  # pandas-compatible structure
      }
    }
  }
}
```

**Моки для тестирования:**

- В memory хранилище узлов (Dict-based)
- Детерминированные хэши для тестов

**Другие ссылки:**
- Python dataclasses: https://docs.python.org/3/library/dataclasses.html
- hashlib: https://docs.python.org/3/library/hashlib.html

## Примечания для Analyst

**Важно:**
- Эта задача — только структуры данных и интерфейс
- Логика построения скелета из VLM-OCR — в задаче 011 (Skeleton Builder)
- Логика сохранения/загрузки — в задаче 007 (File Storage)
- resolve_reference() можно реализовать базово сейчас, full functionality — позже

**Ключевые решения для проработки:**
1. Как организовать внутреннее хранилище узлов? (Dict, custom index)
2. Как вычислять хэш содержимого? (hashlib.sha256)
3. Какой формат JSON для сериализации?

## Зависимости

- Задача 004: SGR Agent Core (для понимания паттернов, но не обязательно)

## Следующие задачи

После завершения:
- Задача 007: File Storage (использует DocumentSkeleton для сохранения)
- Задача 011: Skeleton Builder (создаёт экземпляры Node и DocumentSkeleton)
