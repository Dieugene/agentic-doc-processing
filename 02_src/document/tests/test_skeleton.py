"""Unit тесты для Document Skeleton."""

import json
from typing import Any, Dict, Optional

import pytest

from document.skeleton import (
    DocumentSkeleton,
    InternalStructure,
    Node,
    NodeType,
    PageRange,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_hash():
    """Mock hash function для детерминированных тестов."""

    def _hash(content: str, table_data: Optional[Dict[str, Any]] = None) -> str:
        return f"hash_{len(content)}"

    return _hash


@pytest.fixture
def sample_nodes():
    """Набор тестовых узлов."""
    return {
        "root": Node(
            id="root",
            type=NodeType.ROOT,
            title="Test Document",
            content="Full content of test document...",
            page_range=PageRange(1, 10),
            parent_id=None,
            children_ids=["section_1", "section_2"],
            internal_structure=InternalStructure(raw={}),
            explicit_refs=[],
            hash="hash_100",
        ),
        "section_1": Node(
            id="section_1",
            type=NodeType.SECTION,
            title="1. Введение",
            content="1. Введение\nТекст введения...",
            page_range=PageRange(1, 3),
            parent_id="root",
            children_ids=[],
            internal_structure=InternalStructure(raw={}),
            explicit_refs=[],
            hash="hash_50",
        ),
        "section_2": Node(
            id="section_2",
            type=NodeType.CHAPTER,
            title="2. Основная часть",
            content="2. Основная часть\nТекст основной части...",
            page_range=PageRange(4, 8),
            parent_id="root",
            children_ids=["section_2_1"],
            internal_structure=InternalStructure(
                raw={"2.1": {"title": "Подраздел", "page": 5}}
            ),
            explicit_refs=["section_1"],
            hash="hash_60",
        ),
        "section_2_1": Node(
            id="section_2_1",
            type=NodeType.SECTION,
            title="2.1. Подраздел",
            content="2.1. Подраздел\nТекст подраздела...",
            page_range=PageRange(5, 6),
            parent_id="section_2",
            children_ids=[],
            internal_structure=InternalStructure(raw={}),
            explicit_refs=[],
            hash="hash_40",
        ),
        "appendix_a": Node(
            id="appendix_a",
            type=NodeType.APPENDIX,
            title="Приложение А. Таблицы",
            content="Таблицы с данными...",
            page_range=PageRange(9, 10),
            parent_id="root",
            children_ids=[],
            internal_structure=InternalStructure(raw={}),
            explicit_refs=[],
            hash="hash_30",
            table_data={
                "type": "numeric",
                "source": "original_file",
                "data": {"columns": ["A", "B"], "values": [[1, 2], [3, 4]]},
            },
        ),
    }


@pytest.fixture
def sample_skeleton(sample_nodes):
    """Test DocumentSkeleton instance."""
    return DocumentSkeleton(document_id="test_doc", nodes=sample_nodes)


# =============================================================================
# PageRange Tests
# =============================================================================


class TestPageRange:
    """Тесты для PageRange."""

    def test_page_range_valid(self):
        """Создание валидного диапазона."""
        pr = PageRange(1, 10)
        assert pr.start == 1
        assert pr.end == 10

    def test_page_range_same_page(self):
        """Диапазон из одной страницы."""
        pr = PageRange(5, 5)
        assert pr.start == 5
        assert pr.end == 5

    def test_page_range_invalid_start_gt_end(self):
        """Исключение при start > end."""
        with pytest.raises(ValueError, match="start must be <= end"):
            PageRange(10, 1)

    def test_page_range_negative_start(self):
        """Исключение при отрицательных значениях."""
        with pytest.raises(ValueError, match="Page numbers must be >= 1"):
            PageRange(-1, 10)

    def test_page_range_negative_end(self):
        """Исключение при отрицательных значениях."""
        with pytest.raises(ValueError, match="Page numbers must be >= 1"):
            PageRange(1, -5)

    def test_overlaps_true(self):
        """Пересечение диапазонов."""
        pr1 = PageRange(1, 5)
        pr2 = PageRange(3, 7)
        assert pr1.overlaps(pr2)
        assert pr2.overlaps(pr1)

    def test_overlaps_false(self):
        """Непересекающиеся диапазоны."""
        pr1 = PageRange(1, 5)
        pr2 = PageRange(6, 10)
        assert not pr1.overlaps(pr2)
        assert not pr2.overlaps(pr1)

    def test_overlaps_adjacent(self):
        """Смежные диапазоны не пересекаются."""
        pr1 = PageRange(1, 5)
        pr2 = PageRange(6, 10)
        assert not pr1.overlaps(pr2)

    def test_overlaps_contained(self):
        """Один диапазон содержит другой."""
        pr1 = PageRange(1, 10)
        pr2 = PageRange(3, 5)
        assert pr1.overlaps(pr2)
        assert pr2.overlaps(pr1)


# =============================================================================
# InternalStructure Tests
# =============================================================================


class TestInternalStructure:
    """Тесты для InternalStructure."""

    def test_internal_structure_default(self):
        """Пустая структура по умолчанию."""
        is_struct = InternalStructure()
        assert is_struct.raw == {}

    def test_internal_structure_with_data(self):
        """Структура с данными."""
        data = {"3.1": {"title": "Подраздел", "page": 15}}
        is_struct = InternalStructure(raw=data)
        assert is_struct.raw == data


# =============================================================================
# Node Tests
# =============================================================================


class TestNode:
    """Тесты для Node."""

    def test_node_creation(self):
        """Создание узла со всеми полями."""
        node = Node(
            id="test_node",
            type=NodeType.SECTION,
            title="Test Node",
            content="Test content",
            page_range=PageRange(1, 5),
            parent_id="root",
            children_ids=[],
            internal_structure=InternalStructure(raw={}),
            explicit_refs=[],
            hash="provided_hash",
        )
        assert node.id == "test_node"
        assert node.type == NodeType.SECTION
        assert node.title == "Test Node"
        assert node.content == "Test content"
        assert node.hash == "provided_hash"

    def test_node_hash_computation(self, mock_hash):
        """Хэш вычисляется в __post_init__ если не предоставлен."""
        node = Node(
            id="test_node",
            type=NodeType.SECTION,
            title="Test Node",
            content="Test content",
            page_range=PageRange(1, 5),
            parent_id=None,
            children_ids=[],
            internal_structure=InternalStructure(raw={}),
            explicit_refs=[],
            hash="",  # Пустой хэш - должен быть вычислен
            _hash_func=mock_hash,
        )
        assert node.hash == "hash_12"  # len("Test content")

    def test_node_hash_with_table_data(self, mock_hash):
        """Хэш учитывает table_data."""
        table_data = {"type": "numeric", "data": [[1, 2], [3, 4]]}
        node = Node(
            id="test_node",
            type=NodeType.TABLE,
            title="Test Table",
            content="Table content",
            page_range=PageRange(1, 2),
            parent_id=None,
            children_ids=[],
            internal_structure=InternalStructure(raw={}),
            explicit_refs=[],
            hash="",
            table_data=table_data,
            _hash_func=mock_hash,
        )
        # Хэш от "Table content" + str(table_data)
        expected_content_len = len("Table content") + len(str(table_data))
        assert node.hash == f"hash_{expected_content_len}"

    def test_node_hash_deterministic(self, mock_hash):
        """Одинаковый контент дает одинаковый хэш."""
        node1 = Node(
            id="node1",
            type=NodeType.SECTION,
            title="Same",
            content="Same content",
            page_range=PageRange(1, 2),
            parent_id=None,
            children_ids=[],
            internal_structure=InternalStructure(raw={}),
            explicit_refs=[],
            hash="",
            _hash_func=mock_hash,
        )
        node2 = Node(
            id="node2",
            type=NodeType.SECTION,
            title="Same",
            content="Same content",
            page_range=PageRange(3, 4),
            parent_id=None,
            children_ids=[],
            internal_structure=InternalStructure(raw={}),
            explicit_refs=[],
            hash="",
            _hash_func=mock_hash,
        )
        assert node1.hash == node2.hash

    def test_node_optional_fields(self):
        """Опциональные поля могут быть None/empty."""
        node = Node(
            id="test_node",
            type=NodeType.ROOT,
            title=None,  # Root может не иметь title
            content="Root content",
            page_range=PageRange(1, 100),
            parent_id=None,
            children_ids=[],
            internal_structure=InternalStructure(raw={}),
            explicit_refs=[],
            hash="hash_200",
        )
        assert node.title is None

    def test_node_from_dict(self):
        """Создание Node из dict (десериализация)."""
        node_dict = {
            "id": "test_node",
            "type": NodeType.SECTION,
            "title": "Test",
            "content": "Content",
            "page_range": {"start": 1, "end": 5},
            "parent_id": None,
            "children_ids": [],
            "internal_structure": {"raw": {}},
            "explicit_refs": [],
            "hash": "test_hash",
        }
        node = Node(**node_dict)
        assert isinstance(node.page_range, PageRange)
        assert isinstance(node.internal_structure, InternalStructure)


# =============================================================================
# DocumentSkeleton Tests
# =============================================================================


class TestDocumentSkeletonCreation:
    """Тесты создания DocumentSkeleton."""

    def test_skeleton_creation_empty(self):
        """Создание с пустым словарем узлов."""
        skeleton = DocumentSkeleton(document_id="empty_doc")
        assert skeleton.document_id == "empty_doc"
        assert len(skeleton._nodes) == 0

    def test_skeleton_creation_with_nodes(self, sample_nodes):
        """Создание с узлами."""
        skeleton = DocumentSkeleton(document_id="test_doc", nodes=sample_nodes)
        assert skeleton.document_id == "test_doc"
        assert len(skeleton._nodes) == 5


class TestGetNode:
    """Тесты метода get_node."""

    @pytest.mark.asyncio
    async def test_get_node_exists(self, sample_skeleton):
        """Получение существующего узла."""
        node = await sample_skeleton.get_node("root")
        assert node is not None
        assert node.id == "root"
        assert node.type == NodeType.ROOT

    @pytest.mark.asyncio
    async def test_get_node_not_exists(self, sample_skeleton):
        """None для несуществующего узла."""
        node = await sample_skeleton.get_node("nonexistent")
        assert node is None


class TestGetRoot:
    """Тесты метода get_root."""

    @pytest.mark.asyncio
    async def test_get_root(self, sample_skeleton):
        """Получение root узла."""
        root = await sample_skeleton.get_root()
        assert root.id == "root"
        assert root.type == NodeType.ROOT

    @pytest.mark.asyncio
    async def test_get_root_missing(self):
        """Исключение если root отсутствует."""
        skeleton = DocumentSkeleton(
            document_id="no_root",
            nodes={
                "section_1": Node(
                    id="section_1",
                    type=NodeType.SECTION,
                    title="Section 1",
                    content="Content",
                    page_range=PageRange(1, 5),
                    parent_id=None,
                    children_ids=[],
                    internal_structure=InternalStructure(raw={}),
                    explicit_refs=[],
                    hash="hash",
                )
            },
        )
        with pytest.raises(ValueError, match="Root node not found"):
            await skeleton.get_root()


class TestGetChildren:
    """Тесты метода get_children."""

    @pytest.mark.asyncio
    async def test_get_children(self, sample_skeleton):
        """Получение дочерних узлов."""
        children = await sample_skeleton.get_children("root")
        assert len(children) == 2
        child_ids = {c.id for c in children}
        assert child_ids == {"section_1", "section_2"}

    @pytest.mark.asyncio
    async def test_get_children_no_children(self, sample_skeleton):
        """Узел без потомков."""
        children = await sample_skeleton.get_children("section_1")
        assert len(children) == 0

    @pytest.mark.asyncio
    async def test_get_children_nonexistent_parent(self, sample_skeleton):
        """Несуществующий родитель."""
        children = await sample_skeleton.get_children("nonexistent")
        assert len(children) == 0


class TestFindByTitle:
    """Тесты метода find_by_title."""

    @pytest.mark.asyncio
    async def test_find_by_title_exact(self, sample_skeleton):
        """Точный поиск по заголовку."""
        results = await sample_skeleton.find_by_title("1. Введение")
        assert len(results) == 1
        assert results[0].id == "section_1"

    @pytest.mark.asyncio
    async def test_find_by_title_pattern(self, sample_skeleton):
        """Поиск по паттерну."""
        results = await sample_skeleton.find_by_title(r"2\.\d+")
        assert len(results) == 1
        assert results[0].id == "section_2_1"

    @pytest.mark.asyncio
    async def test_find_by_title_case_insensitive(self, sample_skeleton):
        """Поиск без учета регистра."""
        results = await sample_skeleton.find_by_title("приложение")
        assert len(results) == 1
        assert results[0].id == "appendix_a"

    @pytest.mark.asyncio
    async def test_find_by_title_no_match(self, sample_skeleton):
        """Пустой список если нет совпадений."""
        results = await sample_skeleton.find_by_title("Nonexistent Title")
        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_find_by_title_multiple_results(self, sample_nodes):
        """Несколько результатов."""
        # Добавим узлы с похожими заголовками
        sample_nodes["section_3"] = Node(
            id="section_3",
            type=NodeType.CHAPTER,
            title="3. Заключение",
            content="Заключение",
            page_range=PageRange(10, 12),
            parent_id="root",
            children_ids=[],
            internal_structure=InternalStructure(raw={}),
            explicit_refs=[],
            hash="hash",
        )
        skeleton = DocumentSkeleton(document_id="test_doc", nodes=sample_nodes)
        results = await skeleton.find_by_title(r"\d+\.")
        assert len(results) == 3


class TestFindByPageRange:
    """Тесты метода find_by_page_range."""

    @pytest.mark.asyncio
    async def test_find_by_page_range_overlap(self, sample_skeleton):
        """Поиск пересекающих узлов."""
        results = await sample_skeleton.find_by_page_range(5, 6)
        assert len(results) == 2
        result_ids = {r.id for r in results}
        assert "section_2" in result_ids
        assert "section_2_1" in result_ids

    @pytest.mark.asyncio
    async def test_find_by_page_range_exact(self, sample_skeleton):
        """Точное совпадение диапазона."""
        results = await sample_skeleton.find_by_page_range(5, 6)
        result_ids = {r.id for r in results}
        assert "section_2_1" in result_ids

    @pytest.mark.asyncio
    async def test_find_by_page_range_no_overlap(self, sample_skeleton):
        """Пустой список если нет пересечения."""
        results = await sample_skeleton.find_by_page_range(100, 110)
        assert len(results) == 0


class TestResolveReference:
    """Тесты метода resolve_reference."""

    @pytest.mark.asyncio
    async def test_resolve_reference_by_id(self, sample_skeleton):
        """Резолв по id."""
        node = await sample_skeleton.resolve_reference("section_1")
        assert node is not None
        assert node.id == "section_1"

    @pytest.mark.asyncio
    async def test_resolve_reference_by_title(self, sample_skeleton):
        """Резолв по title."""
        node = await sample_skeleton.resolve_reference("Введение")
        assert node is not None
        assert node.id == "section_1"

    @pytest.mark.asyncio
    async def test_resolve_reference_not_found(self, sample_skeleton):
        """None если не найден."""
        node = await sample_skeleton.resolve_reference("nonexistent")
        assert node is None

    @pytest.mark.asyncio
    async def test_resolve_reference_partial_title(self, sample_skeleton):
        """Частичное совпадение title."""
        node = await sample_skeleton.resolve_reference("Приложение")
        assert node is not None
        assert node.id == "appendix_a"


class TestGetDocumentHash:
    """Тесты метода get_document_hash."""

    @pytest.mark.asyncio
    async def test_get_document_hash(self, sample_skeleton):
        """Хэш всего документа."""
        doc_hash = await sample_skeleton.get_document_hash()
        assert doc_hash
        assert len(doc_hash) == 64  # SHA-256 hex digest

    @pytest.mark.asyncio
    async def test_get_document_hash_deterministic(self, sample_nodes):
        """Одинаковый набор узлов дает одинаковый хэш."""
        skeleton1 = DocumentSkeleton(document_id="doc1", nodes=sample_nodes)
        skeleton2 = DocumentSkeleton(document_id="doc2", nodes=sample_nodes)
        hash1 = await skeleton1.get_document_hash()
        hash2 = await skeleton2.get_document_hash()
        assert hash1 == hash2

    @pytest.mark.asyncio
    async def test_get_document_hash_empty(self):
        """Хэш пустого документа."""
        skeleton = DocumentSkeleton(document_id="empty")
        doc_hash = await skeleton.get_document_hash()
        assert doc_hash
        assert len(doc_hash) == 64


class TestFixtureLoading:
    """Тесты загрузки fixture."""

    def test_load_sample_skeleton(self):
        """Загрузка sample_skeleton.json."""
        import os

        fixture_path = os.path.join(
            os.path.dirname(__file__), "fixtures", "sample_skeleton.json"
        )
        with open(fixture_path) as f:
            data = json.load(f)

        assert "document_id" in data
        assert "nodes" in data
        assert "root" in data["nodes"]
        assert "section_3" in data["nodes"]
        assert "appendix_a" in data["nodes"]

    def test_create_skeleton_from_fixture(self):
        """Создание DocumentSkeleton из fixture."""
        import os

        fixture_path = os.path.join(
            os.path.dirname(__file__), "fixtures", "sample_skeleton.json"
        )
        with open(fixture_path) as f:
            data = json.load(f)

        nodes = {nid: Node(**n) for nid, n in data["nodes"].items()}
        skeleton = DocumentSkeleton(document_id=data["document_id"], nodes=nodes)

        assert skeleton.document_id == "doc_714p_sample"
        assert len(skeleton._nodes) == 3
