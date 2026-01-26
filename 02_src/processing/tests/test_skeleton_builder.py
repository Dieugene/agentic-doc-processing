"""
Unit и интеграционные тесты для SkeletonBuilder.
"""
import json
from pathlib import Path

import pytest

from document import DocumentSkeleton, NodeType, PageRange
from processing.skeleton_builder import SkeletonBuilder, generate_id_from_title, level_to_node_type
from processing.vlm_ocr_extractor import DocumentData


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def skeleton_builder():
    """Создает экземпляр SkeletonBuilder."""
    return SkeletonBuilder()


@pytest.fixture
def sample_document_data():
    """Создает sample DocumentData для тестов."""
    return DocumentData(
        text="Full text of the document...",
        structure={
            "headers": [
                {"level": 1, "title": "1. Introduction", "page": 1},
                {"level": 2, "title": "1.1. Overview", "page": 2},
                {"level": 2, "title": "1.2. Details", "page": 3},
                {"level": 1, "title": "2. Requirements", "page": 4},
            ]
        },
        tables=[
            {
                "id": "table_1",
                "type": "NUMERIC",
                "page": 2,
                "location": {"bbox": [100, 200, 400, 300], "page": 2},
                "preview": "Table 1. Financial indicators",
            }
        ],
    )


@pytest.fixture
def vlm_response_from_file():
    """Загружает VLM response из fixtures."""
    fixtures_path = Path(__file__).parent / "fixtures" / "vlm_response_samples.json"
    with open(fixtures_path, encoding="utf-8") as f:
        data = json.load(f)
    return data["success_response"]


def document_data_from_vlm_response(vlm_response):
    """Создает DocumentData из VLM response."""
    # Извлекаем данные из результатов VLM
    text = ""
    structure = {}
    tables = []

    for result in vlm_response["results"]:
        if "text" in result["data"]:
            text = result["data"]["text"]
        if "structure" in result["data"]:
            structure = result["data"]["structure"]
        if "tables" in result["data"]:
            tables = result["data"]["tables"]

    return DocumentData(text=text, structure=structure, tables=tables)


# ============================================================================
# Тесты helper функций
# ============================================================================

class TestHelperFunctions:
    """Тесты вспомогательных функций."""

    def test_generate_id_from_title_numeric(self):
        """Генерация ID из числового заголовка."""
        assert generate_id_from_title("1. Section") == "section_1"
        assert generate_id_from_title("2.3. Subsection") == "section_2.3"

    def test_generate_id_from_title_text(self):
        """Генерация ID из текстового заголовка."""
        # Кириллица преобразуется в slug
        result = generate_id_from_title("Введение")
        assert result.startswith("node_")
        assert "vvedenie" in result or len(result) > 5  # Либо транслит, либо slug

        # Latin работает ожидаемо
        assert generate_id_from_title("Appendix A") == "node_appendix_a"

    def test_generate_id_from_title_duplicate(self):
        """Генерация уникальных ID для дубликатов."""
        existing = {"section_1"}
        id1 = generate_id_from_title("1. Section", existing)
        assert id1 == "section_1_1"

        existing.add(id1)
        id2 = generate_id_from_title("1. Section", existing)
        assert id2 == "section_1_2"

    def test_level_to_node_type(self):
        """Определение типа узла по уровню."""
        assert level_to_node_type(1) == NodeType.CHAPTER
        assert level_to_node_type(2) == NodeType.SECTION
        assert level_to_node_type(3) == NodeType.SECTION


# ============================================================================
# Тесты build_skeleton
# ============================================================================

class TestBuildSkeleton:
    """Тесты основного метода build_skeleton."""

    @pytest.mark.asyncio
    async def test_build_skeleton_creates_root(self, skeleton_builder, sample_document_data):
        """Root node всегда создается."""
        skeleton = await skeleton_builder.build_skeleton(sample_document_data, "test_doc")

        root = await skeleton.get_root()
        assert root is not None
        assert root.id == "root"
        assert root.type == NodeType.ROOT

    @pytest.mark.asyncio
    async def test_build_skeleton_basic_hierarchy(self, skeleton_builder, sample_document_data):
        """Базовая иерархия: 1 → 1.1 → 1.2 → 2."""
        skeleton = await skeleton_builder.build_skeleton(sample_document_data, "test_doc")

        # Проверяем количество узлов (root + 4 заголовка + 1 таблица)
        assert len(skeleton._nodes) == 6

        # Проверяем структуру
        root = await skeleton.get_root()
        assert len(root.children_ids) == 2  # 1 и 2 (таблица внутри 1.1)

        section_1 = await skeleton.get_node("section_1")
        assert section_1 is not None
        assert section_1.title == "1. Introduction"
        assert section_1.parent_id == "root"
        assert len(section_1.children_ids) == 2  # 1.1 и 1.2

        section_1_1 = await skeleton.get_node("section_1.1")
        assert section_1_1 is not None
        assert section_1_1.title == "1.1. Overview"
        assert section_1_1.parent_id == "section_1"
        # Таблица на странице 2 должна быть в детях section_1.1
        assert "table_1" in section_1_1.children_ids

    @pytest.mark.asyncio
    async def test_build_skeleton_with_empty_headers(self, skeleton_builder):
        """Обработка пустых заголовков - только root."""
        document_data = DocumentData(
            text="Text without structure...",
            structure={"headers": []},
            tables=[],
        )

        skeleton = await skeleton_builder.build_skeleton(document_data, "empty_doc")

        # Только root node
        assert len(skeleton._nodes) == 1
        root = await skeleton.get_root()
        assert root.id == "root"
        assert len(root.children_ids) == 0


# ============================================================================
# Тесты parent-child отношений
# ============================================================================

class TestParentChildRelations:
    """Тесты parent-child отношений."""

    @pytest.mark.asyncio
    async def test_parent_child_sequential(self, skeleton_builder):
        """Последовательная нумерация: 1, 1.1, 1.2, 2."""
        document_data = DocumentData(
            text="Text...",
            structure={
                "headers": [
                    {"level": 1, "title": "1. First", "page": 1},
                    {"level": 2, "title": "1.1. Sub", "page": 2},
                    {"level": 2, "title": "1.2. Another", "page": 3},
                    {"level": 1, "title": "2. Second", "page": 4},
                ]
            },
            tables=[],
        )

        skeleton = await skeleton_builder.build_skeleton(document_data, "test")

        # Проверяем parent-child
        section_1 = await skeleton.get_node("section_1")
        assert section_1.parent_id == "root"
        assert set(section_1.children_ids) == {"section_1.1", "section_1.2"}

        section_1_1 = await skeleton.get_node("section_1.1")
        assert section_1_1.parent_id == "section_1"

        section_2 = await skeleton.get_node("section_2")
        assert section_2.parent_id == "root"

    @pytest.mark.asyncio
    async def test_parent_child_with_gaps(self, skeleton_builder):
        """Разрывы в нумерации: 1, 1.3, 2 (пропущен 1.1, 1.2)."""
        document_data = DocumentData(
            text="Text with gaps...",
            structure={
                "headers": [
                    {"level": 1, "title": "1. Section One", "page": 1},
                    {"level": 2, "title": "1.3. Skipped", "page": 3},
                    {"level": 1, "title": "2. Section Two", "page": 4},
                ]
            },
            tables=[],
        )

        skeleton = await skeleton_builder.build_skeleton(document_data, "test")

        # 1.3 должен быть ребенком 1
        section_1 = await skeleton.get_node("section_1")
        section_1_3 = await skeleton.get_node("section_1.3")

        assert section_1_3.parent_id == "section_1"
        assert section_1_3.id in section_1.children_ids

    @pytest.mark.asyncio
    async def test_parent_child_deep_nesting(self, skeleton_builder):
        """Deep nesting: level 3, level 4."""
        document_data = DocumentData(
            text="Deep nesting...",
            structure={
                "headers": [
                    {"level": 1, "title": "1. Chapter", "page": 1},
                    {"level": 2, "title": "1.1. Section", "page": 2},
                    {"level": 3, "title": "1.1.1. Subsection", "page": 3},
                    {"level": 4, "title": "1.1.1.1. Detail", "page": 4},
                ]
            },
            tables=[],
        )

        skeleton = await skeleton_builder.build_skeleton(document_data, "test")

        # Проверяем цепочку
        section_1 = await skeleton.get_node("section_1")
        section_1_1 = await skeleton.get_node("section_1.1")
        section_1_1_1 = await skeleton.get_node("section_1.1.1")
        section_1_1_1_1 = await skeleton.get_node("section_1.1.1.1")

        assert section_1.parent_id == "root"
        assert section_1_1.parent_id == "section_1"
        assert section_1_1_1.parent_id == "section_1.1"
        assert section_1_1_1_1.parent_id == "section_1.1.1"


# ============================================================================
# Тесты page_range
# ============================================================================

class TestPageRanges:
    """Тесты вычисления page_range."""

    @pytest.mark.asyncio
    async def test_page_range_leaf_nodes(self, skeleton_builder):
        """Листья имеют одну страницу."""
        document_data = DocumentData(
            text="Text...",
            structure={
                "headers": [
                    {"level": 1, "title": "1. Chapter", "page": 5},
                    {"level": 2, "title": "1.1. Section", "page": 7},
                ]
            },
            tables=[],
        )

        skeleton = await skeleton_builder.build_skeleton(document_data, "test")

        # Листья имеют ту же страницу что и заголовок
        section_1 = await skeleton.get_node("section_1")
        section_1_1 = await skeleton.get_node("section_1.1")

        # section_1 - родитель, должен охватывать ребенка
        assert section_1.page_range.start <= 5
        assert section_1.page_range.end >= 7

        # section_1.1 - лист (нет детей)
        assert section_1_1.page_range.start == 7
        assert section_1_1.page_range.end == 7

    @pytest.mark.asyncio
    async def test_page_range_parent_nodes(self, skeleton_builder):
        """Родители охватывают детей."""
        document_data = DocumentData(
            text="Text...",
            structure={
                "headers": [
                    {"level": 1, "title": "1. Chapter", "page": 1},
                    {"level": 2, "title": "1.1. Section A", "page": 2},
                    {"level": 2, "title": "1.2. Section B", "page": 5},
                ]
            },
            tables=[],
        )

        skeleton = await skeleton_builder.build_skeleton(document_data, "test")

        section_1 = await skeleton.get_node("section_1")
        section_1_1 = await skeleton.get_node("section_1.1")
        section_1_2 = await skeleton.get_node("section_1.2")

        # Родитель охватывает всех детей
        assert section_1.page_range.start == 1  # Минимум
        assert section_1.page_range.end == 5  # Максимум

        # Дети на своих страницах
        assert section_1_1.page_range.start == 2
        assert section_1_1.page_range.end == 2
        assert section_1_2.page_range.start == 5
        assert section_1_2.page_range.end == 5


# ============================================================================
# Тесты прикрепления таблиц
# ============================================================================

class TestAttachTables:
    """Тесты прикрепления таблиц к разделам."""

    @pytest.mark.asyncio
    async def test_attach_table_inside_section(self, skeleton_builder):
        """Таблица внутри раздела прикрепляется к нему."""
        document_data = DocumentData(
            text="Text...",
            structure={
                "headers": [
                    {"level": 1, "title": "1. Chapter", "page": 1},
                    {"level": 2, "title": "1.1. Section", "page": 2},
                ]
            },
            tables=[
                {
                    "id": "table_1",
                    "type": "NUMERIC",
                    "page": 2,
                    "location": {"bbox": [0, 0, 100, 100], "page": 2},
                    "preview": "Table on page 2",
                }
            ],
        )

        skeleton = await skeleton_builder.build_skeleton(document_data, "test")

        # Таблица должна быть прикреплена к section_1.1
        table_node = await skeleton.get_node("table_1")
        assert table_node is not None
        assert table_node.type == NodeType.TABLE
        assert table_node.parent_id == "section_1.1"

        # Родитель должен иметь таблицу в детях
        section_1_1 = await skeleton.get_node("section_1.1")
        assert "table_1" in section_1_1.children_ids

    @pytest.mark.asyncio
    async def test_attach_table_between_sections(self, skeleton_builder):
        """Таблица между разделами прикрепляется к ближайшему."""
        document_data = DocumentData(
            text="Text...",
            structure={
                "headers": [
                    {"level": 1, "title": "1. Chapter A", "page": 1},
                    {"level": 1, "title": "2. Chapter B", "page": 5},
                ]
            },
            tables=[
                {
                    "id": "table_1",
                    "type": "TEXT_MATRIX",
                    "page": 3,
                    "location": {"bbox": [0, 0, 100, 100], "page": 3},
                    "preview": "Table between chapters",
                }
            ],
        )

        skeleton = await skeleton_builder.build_skeleton(document_data, "test")

        # Таблица на странице 3 должна быть прикреплена к section_1 (ближе)
        table_node = await skeleton.get_node("table_1")
        assert table_node.parent_id == "section_1"

    @pytest.mark.asyncio
    async def test_attach_multiple_tables(self, skeleton_builder):
        """Несколько таблиц в одном разделе."""
        document_data = DocumentData(
            text="Text...",
            structure={
                "headers": [
                    {"level": 1, "title": "1. Chapter", "page": 1},
                ]
            },
            tables=[
                {
                    "id": "table_1",
                    "type": "NUMERIC",
                    "page": 1,
                    "location": {"bbox": [0, 0, 100, 100], "page": 1},
                    "preview": "First table",
                },
                {
                    "id": "table_2",
                    "type": "TEXT_MATRIX",
                    "page": 1,
                    "location": {"bbox": [0, 100, 100, 200], "page": 1},
                    "preview": "Second table",
                },
            ],
        )

        skeleton = await skeleton_builder.build_skeleton(document_data, "test")

        # Обе таблицы прикреплены к chapter
        section_1 = await skeleton.get_node("section_1")
        assert "table_1" in section_1.children_ids
        assert "table_2" in section_1.children_ids

    @pytest.mark.asyncio
    async def test_table_node_structure(self, skeleton_builder):
        """Табличный узел имеет правильную структуру."""
        document_data = DocumentData(
            text="Text...",
            structure={"headers": [{"level": 1, "title": "1. Chapter", "page": 1}]},
            tables=[
                {
                    "id": "table_numeric",
                    "type": "NUMERIC",
                    "page": 1,
                    "location": {"bbox": [0, 0, 100, 100], "page": 1},
                    "preview": "Numeric table",
                },
                {
                    "id": "table_text",
                    "type": "TEXT_MATRIX",
                    "page": 1,
                    "location": {"bbox": [0, 100, 100, 200], "page": 1},
                    "preview": "Text matrix table",
                },
            ],
        )

        skeleton = await skeleton_builder.build_skeleton(document_data, "test")

        # NUMERIC таблица
        table_numeric = await skeleton.get_node("table_numeric")
        assert table_numeric.type == NodeType.TABLE
        assert table_numeric.table_data is not None
        assert table_numeric.table_data["type"] == "numeric"
        assert table_numeric.table_data["source"] == "original_file"

        # TEXT_MATRIX таблица
        table_text = await skeleton.get_node("table_text")
        assert table_text.table_data["type"] == "text_matrix"
        assert table_text.table_data["source"] == "vlm_ocr"


# ============================================================================
# Edge cases
# ============================================================================

class TestEdgeCases:
    """Тесты граничных случаев."""

    @pytest.mark.asyncio
    async def test_empty_text(self, skeleton_builder):
        """Обработка пустого текста."""
        document_data = DocumentData(
            text="",
            structure={
                "headers": [{"level": 1, "title": "1. Chapter", "page": 1}]
            },
            tables=[],
        )

        skeleton = await skeleton_builder.build_skeleton(document_data, "test")

        section_1 = await skeleton.get_node("section_1")
        assert section_1.content == ""

    @pytest.mark.asyncio
    async def test_invalid_level(self, skeleton_builder):
        """Обработка некорректного уровня."""
        document_data = DocumentData(
            text="Text...",
            structure={
                "headers": [
                    {"level": 0, "title": "Invalid", "page": 1},  # level < 1
                ]
            },
            tables=[],
        )

        skeleton = await skeleton_builder.build_skeleton(document_data, "test")

        # Должен обработаться как level 1
        section_invalid = await skeleton.get_node("node_invalid")
        assert section_invalid.type == NodeType.CHAPTER

    @pytest.mark.asyncio
    async def test_invalid_page_raises_error(self, skeleton_builder):
        """Некорректный номер страницы вызывает ошибку."""
        document_data = DocumentData(
            text="Text...",
            structure={
                "headers": [
                    {"level": 1, "title": "Invalid", "page": 0},  # page < 1
                ]
            },
            tables=[],
        )

        with pytest.raises(ValueError, match="Page number must be >= 1"):
            await skeleton_builder.build_skeleton(document_data, "test")


# ============================================================================
# Интеграционные тесты
# ============================================================================

class TestIntegration:
    """Интеграционные тесты с VLM-OCR mock."""

    @pytest.mark.asyncio
    async def test_full_pipeline_with_vlm_response(self, skeleton_builder, vlm_response_from_file):
        """Полный pipeline: VLM response → SkeletonBuilder → DocumentSkeleton."""
        # Создаем DocumentData из VLM response
        document_data = document_data_from_vlm_response(vlm_response_from_file)

        # Строим скелет
        skeleton = await skeleton_builder.build_skeleton(document_data, "test_doc")

        # Проверяем базовую структуру
        root = await skeleton.get_root()
        assert root is not None
        assert len(skeleton._nodes) > 1  # Root + заголовки

        # Проверяем наличие таблиц
        table_nodes = [
            n for n in skeleton._nodes.values() if n.type == NodeType.TABLE
        ]
        assert len(table_nodes) == 3  # Из fixture

        # Проверяем иерархию
        section_1 = await skeleton.get_node("section_1")
        assert section_1 is not None
        assert section_1.parent_id == "root"

    @pytest.mark.asyncio
    async def test_realistic_document_structure(self, skeleton_builder):
        """Реалистичная структура документа с вложенностью."""
        document_data = DocumentData(
            text="Full realistic document text...",
            structure={
                "headers": [
                    {"level": 1, "title": "1. Introduction", "page": 1},
                    {"level": 2, "title": "1.1. Background", "page": 2},
                    {"level": 2, "title": "1.2. Objectives", "page": 3},
                    {"level": 1, "title": "2. Methodology", "page": 4},
                    {"level": 2, "title": "2.1. Data Collection", "page": 4},
                    {"level": 3, "title": "2.1.1. Sources", "page": 5},
                    {"level": 3, "title": "2.1.2. Processing", "page": 6},
                    {"level": 2, "title": "2.2. Analysis", "page": 7},
                    {"level": 1, "title": "3. Results", "page": 8},
                ]
            },
            tables=[
                {
                    "id": "table_sources",
                    "type": "TEXT_MATRIX",
                    "page": 5,
                    "location": {"bbox": [0, 0, 100, 100], "page": 5},
                    "preview": "Data sources",
                },
                {
                    "id": "table_results",
                    "type": "NUMERIC",
                    "page": 8,
                    "location": {"bbox": [0, 0, 100, 100], "page": 8},
                    "preview": "Results summary",
                },
            ],
        )

        skeleton = await skeleton_builder.build_skeleton(document_data, "realistic")

        # Проверяем структуру
        assert len(skeleton._nodes) == 12  # root + 9 заголовков + 2 таблицы

        # Проверяем вложенность уровня 3
        section_2_1_1 = await skeleton.get_node("section_2.1.1")
        assert section_2_1_1.parent_id == "section_2.1"

        section_2_1 = await skeleton.get_node("section_2.1")
        assert "section_2.1.1" in section_2_1.children_ids
        assert "section_2.1.2" in section_2_1.children_ids

        # Проверяем прикрепление таблиц
        table_sources = await skeleton.get_node("table_sources")
        assert table_sources.parent_id == "section_2.1.1"

        table_results = await skeleton.get_node("table_results")
        assert table_results.parent_id == "section_3"


# ============================================================================
# Тесты internal_structure
# ============================================================================

class TestInternalStructure:
    """Тесты заполнения internal_structure.raw."""

    @pytest.mark.asyncio
    async def test_internal_structure_parent_with_children(self, skeleton_builder):
        """Узел с детьми имеет заполненный internal_structure.raw."""
        document_data = DocumentData(
            text="Text...",
            structure={
                "headers": [
                    {"level": 1, "title": "1. Main Section", "page": 1},
                    {"level": 2, "title": "1.1. Subsection A", "page": 2},
                    {"level": 2, "title": "1.2. Subsection B", "page": 3},
                ]
            },
            tables=[],
        )

        skeleton = await skeleton_builder.build_skeleton(document_data, "test")

        section_1 = await skeleton.get_node("section_1")
        assert len(section_1.internal_structure.raw) == 2
        assert "1.1. Subsection A" in section_1.internal_structure.raw
        assert "1.2. Subsection B" in section_1.internal_structure.raw

        # Проверяем структуру данных
        subsection_a_data = section_1.internal_structure.raw["1.1. Subsection A"]
        assert subsection_a_data["level"] == 2
        assert subsection_a_data["page"] == 2
        assert subsection_a_data["node_id"] == "section_1.1"

    @pytest.mark.asyncio
    async def test_internal_structure_leaf_empty(self, skeleton_builder):
        """Лист имеет пустой internal_structure.raw."""
        document_data = DocumentData(
            text="Text...",
            structure={
                "headers": [
                    {"level": 1, "title": "1. Main", "page": 1},
                    {"level": 2, "title": "1.1. Leaf", "page": 2},
                ]
            },
            tables=[],
        )

        skeleton = await skeleton_builder.build_skeleton(document_data, "test")

        section_1_1 = await skeleton.get_node("section_1.1")
        assert section_1_1.internal_structure.raw == {}

    @pytest.mark.asyncio
    async def test_internal_structure_tables_excluded(self, skeleton_builder):
        """Таблицы не попадают в internal_structure родителя."""
        document_data = DocumentData(
            text="Text...",
            structure={
                "headers": [
                    {"level": 1, "title": "1. Section", "page": 1},
                    {"level": 2, "title": "1.1. Subsection", "page": 2},
                ]
            },
            tables=[
                {
                    "id": "table_1",
                    "type": "NUMERIC",
                    "page": 2,
                    "location": {"bbox": [0, 0, 100, 100], "page": 2},
                    "preview": "Table 1",
                }
            ],
        )

        skeleton = await skeleton_builder.build_skeleton(document_data, "test")

        # Дочерний раздел имеет таблицу в children_ids
        section_1_1 = await skeleton.get_node("section_1.1")
        assert "table_1" in section_1_1.children_ids

        # Но не в internal_structure.raw
        assert "Table 1" not in section_1_1.internal_structure.raw

        # Проверяем что в raw только реальные заголовки
        for title in section_1_1.internal_structure.raw:
            assert not title.startswith("Table")

    @pytest.mark.asyncio
    async def test_internal_structure_only_direct_children(self, skeleton_builder):
        """В internal_structure только прямые потомки, не все рекурсивно."""
        document_data = DocumentData(
            text="Text...",
            structure={
                "headers": [
                    {"level": 1, "title": "1. Main", "page": 1},
                    {"level": 2, "title": "1.1. Middle", "page": 2},
                    {"level": 3, "title": "1.1.1. Deep", "page": 3},
                ]
            },
            tables=[],
        )

        skeleton = await skeleton_builder.build_skeleton(document_data, "test")

        section_1 = await skeleton.get_node("section_1")
        # Только прямые потомки (level 2)
        assert len(section_1.internal_structure.raw) == 1
        assert "1.1. Middle" in section_1.internal_structure.raw
        # Глубокий узел не в internal_structure родителя
        assert "1.1.1. Deep" not in section_1.internal_structure.raw

    @pytest.mark.asyncio
    async def test_internal_structure_root(self, skeleton_builder):
        """Root node имеет заполненный internal_structure."""
        document_data = DocumentData(
            text="Text...",
            structure={
                "headers": [
                    {"level": 1, "title": "1. First", "page": 1},
                    {"level": 1, "title": "2. Second", "page": 2},
                ]
            },
            tables=[],
        )

        skeleton = await skeleton_builder.build_skeleton(document_data, "test")

        root = await skeleton.get_root()
        assert len(root.internal_structure.raw) == 2
        assert "1. First" in root.internal_structure.raw
        assert "2. Second" in root.internal_structure.raw

    @pytest.mark.asyncio
    async def test_extract_level_from_title(self, skeleton_builder):
        """Тест извлечения уровня из заголовка."""
        assert skeleton_builder._extract_level_from_title("1. Section") == 1
        assert skeleton_builder._extract_level_from_title("1.1. Subsection") == 2
        assert skeleton_builder._extract_level_from_title("2.3.4. Deep") == 3  # 2 точки + 1 = level 3
        assert skeleton_builder._extract_level_from_title("No number") == 0
        assert skeleton_builder._extract_level_from_title("Введение") == 0
