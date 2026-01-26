# Задача 007: File Storage реализация

## Что нужно сделать

Реализовать файловое хранилище для персистентности скелетов и индексов.

## Зачем

File Storage обеспечивает сохранение и загрузку результатов обработки документов. Без него каждый запуск системы требовал бы полной переобработки через VLM-OCR (дорого).

## Acceptance Criteria

- [ ] AC-001: FileStorage класс реализован
- [ ] AC-002: save_skeleton() сериализует DocumentSkeleton в JSON
- [ ] AC-003: load_skeleton() десериализует JSON в DocumentSkeleton
- [ ] AC-004: document_exists() проверяет существование документа
- [ ] AC-005: Обработка ошибок чтения/записи
- [ ] AC-006: Unit тесты для всех методов
- [ ] AC-007: Тестовые fixture'ы

## Контекст

> **Архитектурное решение:** ADR-004 (File-based JSON для v1.0 с абстракцией для миграции)

**Ключевые решения из ADR-004:**
- File-based JSON выбран для v1.0 (PoC, 10-50 документов)
- Интерфейс `Storage` с абстракцией для будущей миграции на БД
- VLM-OCR кэш в отдельной директории `data/cache/vlm_ocr/`
- Инвалидация кэша через hash исходного файла

**Интерфейсы и контракты:**

```python
from pathlib import Path
from typing import Optional
import json

class FileStorage:
    """
    Файловое хранилище для скелетов и индексов.

    Хранение: data/{document_id}/
      - skeleton.json
      - navigation_index.json (будущая задача)
      - taxonomy.json (будущая задача)
    """

    base_path: Path

    def __init__(self, base_path: str):
        """Инициализация с базовой директорией"""
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)

    async def save_skeleton(self, document_id: str, skeleton: DocumentSkeleton):
        """
        Сохранить DocumentSkeleton в JSON.

        Сериализует все узлы в структуру:
        {
          "document_id": "...",
          "root": {...},
          "nodes": {
            "node_id_1": {...},
            "node_id_2": {...}
          }
        }
        """
        doc_dir = self.base_path / document_id
        doc_dir.mkdir(parents=True, exist_ok=True)

        # Сериализуем все узлы
        nodes_data = {}
        for node in await skeleton.get_all_nodes():
            nodes_data[node.id] = {
                "id": node.id,
                "type": node.type.value,
                "title": node.title,
                "content": node.content,
                "page_range": {"start": node.page_range.start, "end": node.page_range.end},
                "parent_id": node.parent_id,
                "children_ids": node.children_ids,
                "internal_structure": node.internal_structure.raw,
                "explicit_refs": node.explicit_refs,
                "hash": node.hash,
                "table_data": node.table_data
            }

        skeleton_data = {
            "document_id": skeleton.document_id,
            "nodes": nodes_data
        }

        skeleton_path = doc_dir / "skeleton.json"
        with open(skeleton_path, 'w', encoding='utf-8') as f:
            json.dump(skeleton_data, f, ensure_ascii=False, indent=2)

    async def load_skeleton(self, document_id: str) -> Optional[DocumentSkeleton]:
        """
        Загрузить DocumentSkeleton из JSON.

        Восстанавливает DocumentSkeleton из JSON.
        """
        skeleton_path = self.base_path / document_id / "skeleton.json"

        if not skeleton_path.exists():
            return None

        with open(skeleton_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # Реконструируем узлы
        nodes = {}
        for node_id, node_data in data["nodes"].items():
            nodes[node_id] = Node(
                id=node_data["id"],
                type=NodeType(node_data["type"]),
                title=node_data["title"],
                content=node_data["content"],
                page_range=PageRange(**node_data["page_range"]),
                parent_id=node_data["parent_id"],
                children_ids=node_data["children_ids"],
                internal_structure=InternalStructure(raw=node_data["internal_structure"]),
                explicit_refs=node_data["explicit_refs"],
                hash=node_data["hash"],
                table_data=node_data.get("table_data")
            )

        # Находим корень и создаём DocumentSkeleton
        root = next((n for n in nodes.values() if n.parent_id is None), None)
        if not root:
            raise ValueError(f"No root node found for document {document_id}")

        skeleton = DocumentSkeleton(document_id, root)
        for node_id, node in nodes.items():
            if node_id != root.id:
                skeleton._nodes[node_id] = node

        return skeleton

    def document_exists(self, document_id: str) -> bool:
        """Проверить существование документа"""
        return (self.base_path / document_id / "skeleton.json").exists()
```

**Структура проекта:**

```
02_src/
├── storage/
│   ├── __init__.py
│   ├── file_storage.py
│   └── tests/
│       ├── test_file_storage.py
│       └── fixtures/
│           └── sample_skeleton.json
04_logs/
└── storage/
    └── (логи операций)
```

**Зависимость от задачи 006:**

```python
# Для типа Node
from 02_src.document.skeleton import Node, DocumentSkeleton, NodeType, PageRange, InternalStructure
```

## Примечания для Analyst

**Важно:**
- Задача зависит от 006 (DocumentSkeleton) — нужны типы данных
- **JSON формат подтвержден ADR-004** (не требует уточнения)
- Реализовать абстракцию `Storage` для будущей миграции на БД (см. ADR-004)

**Ключевые решения:**
1. Какой base_path использовать? (config/env variable, например `data/`)
2. Как обрабатывать ошибки чтения/записи? (логировать и пробрасывать)
3. Нужно ли сжимать JSON? (для v1.0 — нет)

## Зависимости

- Задача 006: DocumentSkeleton (структуры данных)

## Следующие задачи

После завершения:
- Задача 011: Skeleton Builder (использует FileStorage для сохранения)
