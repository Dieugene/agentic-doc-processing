"""
Document Skeleton - структуры данных для физического представления документа.

Модуль предоставляет иерархическое представление структуры документа
с поддержкой навигации по разделам, хэширования содержимого и
отслеживания изменений.
"""
from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class NodeType(str, Enum):
    """Тип узла в скелете документа."""

    CHAPTER = "chapter"  # Глава (1., 2., ...)
    SECTION = "section"  # Раздел (1.1, 1.2, ...)
    APPENDIX = "appendix"  # Приложение
    TABLE = "table"  # Таблица
    FIGURE = "figure"  # Рисунок/схема
    ROOT = "root"  # Корневой узел


@dataclass
class PageRange:
    """Диапазон страниц в исходном документе."""

    start: int
    end: int

    def __post_init__(self):
        """Валидация диапазона страниц."""
        if self.start < 1 or self.end < 1:
            raise ValueError(f"Page numbers must be >= 1: got {self.start}-{self.end}")
        if self.start > self.end:
            raise ValueError(f"start must be <= end: got {self.start} > {self.end}")

    def overlaps(self, other: PageRange) -> bool:
        """Проверяет пересечение с другим диапазоном."""
        return not (self.end < other.start or self.start > other.end)


@dataclass
class InternalStructure:
    """Иерархия подпунктов внутри узла.

    Пример для раздела 3:
    {
        "3.1": {"title": "Общие требования", "page": 15},
        "3.2": {"title": "Сроки представления", "page": 18},
        "3.2.1": {"title": "Ежемесячная", "page": 18}
    }
    """

    raw: Dict[str, Any] = field(default_factory=dict)


def _compute_hash(content: str, table_data: Optional[Dict[str, Any]]) -> str:
    """Вычисляет SHA-256 хэш от содержимого."""
    data = content + str(table_data or "")
    return hashlib.sha256(data.encode()).hexdigest()


@dataclass
class Node:
    """Узел скелета документа."""

    id: str  # уникальный ID (например "section_3")
    type: NodeType  # тип узла
    title: Optional[str]  # заголовок ("3. Требования к отчётности")
    content: str  # полный текст узла
    page_range: PageRange  # страницы в исходном документе
    parent_id: Optional[str]  # ID родительского узла
    children_ids: List[str]  # ID дочерних узлов
    internal_structure: InternalStructure  # иерархия подпунктов
    explicit_refs: List[str]  # явные ссылки ("см. п. 5.3", "Приложение Б")
    hash: str  # хэш содержимого (для инвалидации)
    table_data: Optional[Dict[str, Any]] = None  # для числовых таблиц (Pandas)
    _hash_func: Callable[[str, Optional[Dict[str, Any]]], str] = field(
        default_factory=lambda: _compute_hash, compare=False, repr=False
    )

    def __post_init__(self):
        """Вычисляет хэш содержимого если не предоставлен."""
        # Преобразуем page_range из dict если нужно
        if isinstance(self.page_range, dict):
            self.page_range = PageRange(**self.page_range)

        # Преобразуем internal_structure из dict если нужно
        if isinstance(self.internal_structure, dict):
            self.internal_structure = InternalStructure(**self.internal_structure)

        # Вычисляем хэш если не предоставлен
        if not self.hash:
            self.hash = self._hash_func(self.content, self.table_data)
            logger.debug(f"Computed hash for node {self.id}: {self.hash}")


class DocumentSkeleton:
    """Интерфейс доступа к скелету документа.

    Предоставляет навигацию по иерархической структуре документа.
    """

    def __init__(
        self,
        document_id: str,
        nodes: Optional[Dict[str, Node]] = None,
    ):
        """Инициализирует скелет документа.

        Args:
            document_id: Уникальный идентификатор документа
            nodes: Словарь узлов (id -> Node). Если None, создается пустой словарь.
        """
        self.document_id = document_id
        self._nodes: Dict[str, Node] = nodes or {}
        logger.info(f"Created DocumentSkeleton for {document_id} with {len(self._nodes)} nodes")

    async def get_node(self, node_id: str) -> Optional[Node]:
        """Получить узел по ID."""
        return self._nodes.get(node_id)

    async def get_root(self) -> Node:
        """Получить корневой узел документа.

        Raises:
            ValueError: Если корневой узел не найден
        """
        for node in self._nodes.values():
            if node.type == NodeType.ROOT:
                return node
        raise ValueError(f"Root node not found in document {self.document_id}")

    async def get_children(self, node_id: str) -> List[Node]:
        """Получить прямых потомков узла."""
        node = await self.get_node(node_id)
        if not node:
            return []
        return [self._nodes[child_id] for child_id in node.children_ids if child_id in self._nodes]

    async def find_by_title(self, title_pattern: str) -> List[Node]:
        """Найти узлы по паттерну заголовка (regex)."""
        pattern = re.compile(title_pattern, re.IGNORECASE)
        result = [
            node
            for node in self._nodes.values()
            if node.title and pattern.search(node.title)
        ]
        logger.debug(f"find_by_title('{title_pattern}'): found {len(result)} nodes")
        return result

    async def find_by_page_range(self, start: int, end: int) -> List[Node]:
        """Найти узлы, пересекающие диапазон страниц."""
        search_range = PageRange(start, end)
        result = [
            node for node in self._nodes.values() if node.page_range.overlaps(search_range)
        ]
        logger.debug(f"find_by_page_range({start}, {end}): found {len(result)} nodes")
        return result

    async def resolve_reference(self, ref: str) -> Optional[Node]:
        """Резолв явной ссылки ("см. п. 5.3", "Приложение Б").

        Базовая версия: ищет по id или title.
        Полная версия с DocumentCollection — позже.

        Args:
            ref: Ссылка на узел (id или часть title)

        Returns:
            Node или None если ссылка неразрешима
        """
        # Пытаемся найти по id
        node = await self.get_node(ref)
        if node:
            return node

        # Пытаемся найти по title (частичное совпадение)
        candidates = await self.find_by_title(ref)
        if candidates:
            logger.debug(f"resolve_reference('{ref}'): found {len(candidates)} candidates")
            return candidates[0]

        logger.debug(f"resolve_reference('{ref}'): not found")
        return None

    async def get_document_hash(self) -> str:
        """Хэш всего документа для отслеживания изменений.

        Вычисляется как хэш от конкатенации хэшей всех узлов,
        отсортированных по id для детерминизма.
        """
        sorted_hashes = [self._nodes[nid].hash for nid in sorted(self._nodes.keys())]
        combined = "".join(sorted_hashes)
        doc_hash = hashlib.sha256(combined.encode()).hexdigest()
        logger.debug(f"get_document_hash: {doc_hash}")
        return doc_hash
