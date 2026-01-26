"""
Skeleton Builder - агрегация результатов VLM-OCR в DocumentSkeleton.

Модуль предоставляет преобразование неструктурированных данных от VLM-OCR
(DocumentData) в иерархический скелет документа (DocumentSkeleton).
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

from document import DocumentSkeleton, InternalStructure, Node, NodeType, PageRange
from processing.vlm_ocr_extractor import DocumentData

logger = logging.getLogger(__name__)


def generate_id_from_title(title: str, existing_ids: Optional[set[str]] = None) -> str:
    """Генерирует уникальный ID из заголовка.

    Args:
        title: Заголовок секции
        existing_ids: Множество уже существующих ID для проверки уникальности

    Returns:
        Уникальный ID (например "section_1" или "node_vvedenie")
    """
    existing_ids = existing_ids or set()

    # Попытка извлечь число из начала title: "1. Раздел" → "section_1"
    match = re.match(r'(\d+(?:\.\d+)*)', title)
    if match:
        base_id = f"section_{match.group(1)}"
    else:
        # Fallback: slugify
        slug = re.sub(r'[^\w]', '_', title.lower()).strip('_')
        base_id = f"node_{slug}" if slug else "node_unknown"

    # Проверяем уникальность и добавляем суффикс если нужно
    final_id = base_id
    counter = 1
    while final_id in existing_ids:
        final_id = f"{base_id}_{counter}"
        counter += 1

    return final_id


def level_to_node_type(level: int) -> NodeType:
    """Определяет тип узла по уровню заголовка.

    Args:
        level: Уровень заголовка (1, 2, 3, ...)

    Returns:
        NodeType соответствующий уровню
    """
    if level == 1:
        return NodeType.CHAPTER
    elif level >= 2:
        return NodeType.SECTION
    else:
        return NodeType.ROOT


class SkeletonBuilder:
    """Агрегация результатов VLM-OCR в DocumentSkeleton.

    Превращает неструктурированные данные от VLM-OCR (DocumentData)
    в иерархический скелет документа (DocumentSkeleton).
    """

    def __init__(self):
        """Инициализирует SkeletonBuilder."""
        logger.info("Initialized SkeletonBuilder")

    async def build_skeleton(
        self,
        document_data: DocumentData,
        document_id: str,
    ) -> DocumentSkeleton:
        """Построить DocumentSkeleton из данных VLM-OCR.

        Args:
            document_data: Данные от VLM-OCR (текст, структура, таблицы)
            document_id: Уникальный идентификатор документа

        Returns:
            DocumentSkeleton с деревом Node

        Raises:
            ValueError: При некорректных входных данных
        """
        logger.info(f"Building skeleton for document {document_id}")

        # Строим дерево узлов из заголовков
        nodes = self._build_node_tree(
            structure=document_data.structure,
            full_text=document_data.text,
            document_id=document_id,
        )

        # Заполняем internal_structure для каждого узла
        self._populate_internal_structure(nodes)

        # Создаем DocumentSkeleton
        skeleton = DocumentSkeleton(document_id=document_id, nodes=nodes)

        # Прикрепляем таблицы
        if document_data.tables:
            self._attach_tables(skeleton, document_data.tables, nodes)

        logger.info(f"Built skeleton with {len(nodes)} nodes")

        return skeleton

    def _build_node_tree(
        self,
        structure: Dict[str, Any],
        full_text: str,
        document_id: str,
    ) -> Dict[str, Node]:
        """Построить дерево Node из иерархии заголовков.

        Args:
            structure: Структура документа с заголовками
            full_text: Полный текст документа
            document_id: ID документа

        Returns:
            Словарь узлов (id -> Node)

        Raises:
            ValueError: При некорректных номерах страниц
        """
        nodes: Dict[str, Node] = {}
        existing_ids: set[str] = set()

        # Стек для отслеживания родительских узлов по уровням
        # stack[level] = node_id последнего узла на этом уровне
        stack: Dict[int, str] = {}

        headers = structure.get("headers", [])

        # Создаем root node
        root_id = "root"
        root = Node(
            id=root_id,
            type=NodeType.ROOT,
            title=document_id,
            content=full_text,
            page_range=PageRange(1, 1),  # Будет обновлен позже
            parent_id=None,
            children_ids=[],
            internal_structure=InternalStructure(raw={}),
            explicit_refs=[],
            hash="",  # Вычислится автоматически
        )
        nodes[root_id] = root
        existing_ids.add(root_id)
        stack[0] = root_id

        # Обрабатываем каждый заголовок
        for header in headers:
            level = header.get("level", 1)
            title = header.get("title", "")
            page = header.get("page", 1)

            if page < 1:
                raise ValueError(f"Page number must be >= 1: got {page}")

            if level < 1:
                level = 1
                logger.warning(f"Invalid level {header.get('level')}, using 1")

            # Определяем тип узла
            node_type = level_to_node_type(level)

            # Генерируем уникальный ID
            node_id = generate_id_from_title(title, existing_ids)
            existing_ids.add(node_id)

            # Находим родительский узел
            parent_id = self._find_parent_by_level(level, stack)

            # Создаем узел
            node = Node(
                id=node_id,
                type=node_type,
                title=title,
                content=full_text,
                page_range=PageRange(page, page),  # Сначала одна страница
                parent_id=parent_id,
                children_ids=[],
                internal_structure=InternalStructure(raw={}),
                explicit_refs=[],
                hash="",
            )
            nodes[node_id] = node

            # Обновляем стек текущего уровня
            stack[level] = node_id

            # Добавляем в children родителя
            if parent_id in nodes:
                parent = nodes[parent_id]
                if node_id not in parent.children_ids:
                    parent.children_ids.append(node_id)

            logger.debug(
                f"Created node {node_id}: level={level}, title='{title}', "
                f"parent={parent_id}, page={page}"
            )

        # Обновляем page_range для родительских узлов
        self._update_parent_page_ranges(nodes)

        return nodes

    def _find_parent_by_level(self, level: int, stack: Dict[int, str]) -> str:
        """Находит родительский node_id по уровню заголовка.

        Использует стек для поиска последнего заголовка с меньшим уровнем.

        Args:
            level: Текущий уровень заголовка
            stack: Стек уровней (level -> node_id)

        Returns:
            ID родительского узла
        """
        # Ищем ближайший меньший level
        for l in range(level - 1, -1, -1):
            if l in stack:
                return stack[l]

        return "root"  # Fallback

    def _update_parent_page_ranges(self, nodes: Dict[str, Node]) -> None:
        """Обновляет page_range для родительских узлов на основе детей.

        Для родительских узлов page_range должен охватывать все дети:
        start = min(children.start), end = max(children.end)

        Args:
            nodes: Словарь всех узлов
        """
        # Обновляем в несколько проходов снизу вверх
        max_iterations = 10  # Максимальная глубина для безопасности

        for _ in range(max_iterations):
            updated = False

            for node in nodes.values():
                if node.children_ids:
                    # Собираем page_range всех детей
                    child_ranges = [
                        nodes[cid].page_range
                        for cid in node.children_ids
                        if cid in nodes
                    ]

                    if child_ranges:
                        new_start = min(cr.start for cr in child_ranges)
                        new_end = max(cr.end for cr in child_ranges)

                        # Если у родителя уже был свой page_range, учитываем и его
                        current_start = node.page_range.start
                        current_end = node.page_range.end

                        final_start = min(current_start, new_start)
                        final_end = max(current_end, new_end)

                        if node.page_range.start != final_start or node.page_range.end != final_end:
                            node.page_range = PageRange(final_start, final_end)
                            updated = True

            if not updated:
                break

    def _attach_tables(
        self,
        skeleton: DocumentSkeleton,
        tables: List[Dict[str, Any]],
        nodes: Dict[str, Node],
    ) -> None:
        """Прикрепить таблицы к соответствующим Node.

        Args:
            skeleton: DocumentSkeleton для обновления
            tables: Список таблиц от VLM-OCR
            nodes: Словарь узлов
        """
        logger.debug(f"Attaching {len(tables)} tables to skeleton")

        for table in tables:
            table_page = table.get("page", 1)

            # Находим целевой узел
            target_id = self._find_table_target(table_page, nodes)

            if not target_id:
                logger.warning(f"Could not find target for table {table.get('id')}")
                continue

            # Создаем узел таблицы
            table_id = table.get("id", f"table_{table_page}")
            table_node = Node(
                id=table_id,
                type=NodeType.TABLE,
                title=table.get("preview", f"Table {table_id}"),
                content="",  # У таблиц нет текстового контента
                page_range=PageRange(table_page, table_page),
                parent_id=target_id,
                children_ids=[],
                internal_structure=InternalStructure(raw={}),
                explicit_refs=[],
                table_data=self._format_table_data(table),
                hash="",
            )

            # Добавляем в skeleton
            skeleton._nodes[table_id] = table_node

            # Обновляем родителя
            if target_id in nodes:
                parent = nodes[target_id]
                if table_id not in parent.children_ids:
                    parent.children_ids.append(table_id)

            logger.debug(
                f"Attached table {table_id} to {target_id} "
                f"(page {table_page}, type {table.get('type')})"
            )

    def _find_table_target(self, table_page: int, nodes: Dict[str, Node]) -> Optional[str]:
        """Находит целевой узел для прикрепления таблицы.

        Args:
            table_page: Страница таблицы
            nodes: Словарь узлов

        Returns:
            ID целевого узла или None
        """
        # 1. Точные совпадения по page_range
        candidates = [
            node
            for node in nodes.values()
            if node.type in [NodeType.CHAPTER, NodeType.SECTION]
            and node.page_range.start <= table_page <= node.page_range.end
        ]

        if candidates:
            # Выбираем самого специфичного:
            # - С наименьшим размером page_range
            # - При равном размере - с наибольшей глубиной (длинный id)
            def specificity_key(n: Node) -> tuple:
                range_size = n.page_range.end - n.page_range.start
                depth = len(n.id.split('.'))  # "1.1.1" глубже чем "1"
                return (range_size, -depth)  # Minimize range, maximize depth

            return min(candidates, key=specificity_key).id

        # 2. Ближайший по странице (предпочитаем CHAPTER/SECTION над ROOT)
        def nearest_key(n: Node) -> tuple:
            distance = abs(n.page_range.start - table_page)
            # ROOT имеет наименьший приоритет (при равном расстоянии)
            is_root = 1 if n.type == NodeType.ROOT else 0
            # При равном расстоянии предпочитаeм предыдущий (меньший start)
            return (distance, is_root, n.page_range.start)

        valid_nodes = [
            node
            for node in nodes.values()
            if node.type in [NodeType.CHAPTER, NodeType.SECTION, NodeType.ROOT]
        ]

        if valid_nodes:
            return min(valid_nodes, key=nearest_key).id

        return None

    def _format_table_data(self, table: Dict[str, Any]) -> Dict[str, Any]:
        """Форматирует данные таблицы в структуру table_data.

        Args:
            table: Сырые данные таблицы от VLM-OCR

        Returns:
            Отформатированные данные для Node.table_data
        """
        table_type = table.get("type", "TEXT_MATRIX").lower()

        if table_type == "numeric":
            return {
                "type": "numeric",
                "source": "original_file",
                "data": {
                    "table_id": table.get("id"),
                    "location": table.get("location"),
                    # Placeholder: реальные данные будут извлечены Table Extractor
                },
            }
        else:  # TEXT_MATRIX
            return {
                "type": "text_matrix",
                "source": "vlm_ocr",
                "data": {
                    "table_id": table.get("id"),
                    "location": table.get("location"),
                    "flattened": [],  # Будет заполнено VLM-OCR
                },
            }

    def _extract_level_from_title(self, title: str) -> int:
        """Извлекает уровень заголовка из его названия.

        Args:
            title: Заголовок (например "1. Раздел", "1.1. Подраздел", "2.3.4. Глубокий")

        Returns:
            Уровень заголовка (1, 2, 3, ...) или 0 если не удается извлечь

        Examples:
            >>> _extract_level_from_title("1. Раздел")
            1
            >>> _extract_level_from_title("1.1. Подраздел")
            2
            >>> _extract_level_from_title("2.3.4. Глубокий")
            4
            >>> _extract_level_from_title("Введение")
            0
        """
        match = re.match(r'(\d+(?:\.\d+)*)', title)
        if match:
            level_str = match.group(1)
            return level_str.count('.') + 1
        return 0

    def _populate_internal_structure(self, nodes: Dict[str, Node]) -> None:
        """Заполняет internal_structure.raw для каждого узла.

        Для каждого узла находит прямых потомков (children_ids)
        и заполняет raw словарь информацией о них.

        Правила:
        - Только прямые потомки (не все потомки рекурсивно)
        - Ключ: заголовок потомка (title)
        - Значение: {level, page, node_id}
        - Листья (без детей) имеют пустой raw
        - Таблицы (type=TABLE) НЕ добавляются в internal_structure

        Args:
            nodes: Словарь всех узлов (id -> Node)
        """
        for node_id, node in nodes.items():
            raw: Dict[str, Any] = {}

            for child_id in node.children_ids:
                if child_id not in nodes:
                    continue

                child = nodes[child_id]

                # Пропускаем таблицы (они не в internal_structure)
                if child.type == NodeType.TABLE:
                    continue

                # Извлекаем level из title
                level = self._extract_level_from_title(child.title)

                # Добавляем в raw
                raw[child.title] = {
                    "level": level,
                    "page": child.page_range.start,
                    "node_id": child.id
                }

            # Создаем новый InternalStructure с заполненным raw
            node.internal_structure = InternalStructure(raw=raw)

            logger.debug(
                f"Populated internal_structure for {node_id}: "
                f"{len(raw)} children"
            )
