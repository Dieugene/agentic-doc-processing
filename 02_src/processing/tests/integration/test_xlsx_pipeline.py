"""
Integration tests for Excel (XLSX) document processing pipeline.

Tests the full pipeline with focus on NUMERIC table extraction from Excel sheets.
"""
import pytest

from document import NodeType
from processing.tests.integration.conftest import (
    count_nodes_by_type,
    get_all_nodes,
    skip_if_no_poppler,
)


@pytest.mark.integration
@skip_if_no_poppler
class TestXLSXPipeline:
    """Integration tests for XLSX file processing with NUMERIC tables."""

    @pytest.mark.asyncio
    async def test_full_pipeline_xlsx(self, document_processor, sample_xlsx):
        """
        Test complete XLSX processing pipeline.

        Scenario:
        1. Load sample.xlsx (with 2 sheets)
        2. Each sheet converts to PDF page
        3. Render to PNG
        4. Extract data via MockVLMOCR
        5. Build DocumentSkeleton with NUMERIC tables
        6. Save to FileStorage

        Validates:
        - Excel file is processed correctly
        - NUMERIC tables are extracted
        - Multiple sheets are handled
        """
        document_id = await document_processor.process_document(str(sample_xlsx))

        # Verify document was saved
        assert document_id is not None

        # Load skeleton from storage
        skeleton = await document_processor.storage.load_skeleton(document_id)
        assert skeleton is not None

        # Verify structure was created
        all_nodes = get_all_nodes(skeleton)
        assert len(all_nodes) > 1

    @pytest.mark.asyncio
    async def test_xlsx_numeric_tables_extracted(self, document_processor, sample_xlsx):
        """
        Verify NUMERIC tables are correctly extracted from XLSX.

        Excel files with numerical data should have tables with:
        - type: "numeric"
        - source: "original_file"
        - Pandas-compatible structure
        """
        document_id = await document_processor.process_document(str(sample_xlsx))
        skeleton = await document_processor.storage.load_skeleton(document_id)

        # Find all tables
        tables = [n for n in get_all_nodes(skeleton) if n.type == NodeType.TABLE]

        # Should have at least one table
        assert len(tables) >= 1, "XLSX should have at least one NUMERIC table"

        # Verify each NUMERIC table
        numeric_count = 0
        for table in tables:
            if table.table_data and table.table_data.get("type") == "numeric":
                numeric_count += 1

                # Verify NUMERIC table structure
                assert table.table_data["source"] == "original_file", \
                    f"Table {table.id} should have source='original_file'"

                assert "data" in table.table_data, \
                    f"Table {table.id} should have 'data' field"

                # Verify data structure contains necessary fields
                table_data = table.table_data["data"]
                assert "table_id" in table_data or "location" in table_data, \
                    f"Table {table.id} data should identify the table"

        assert numeric_count >= 1, "Should have at least one NUMERIC table"

    @pytest.mark.asyncio
    async def test_xlsx_multiple_sheets_handled(self, document_processor, sample_xlsx):
        """
        Verify multiple Excel sheets are processed correctly.

        Each sheet should be represented in the document structure.
        """
        document_id = await document_processor.process_document(str(sample_xlsx))
        skeleton = await document_processor.storage.load_skeleton(document_id)

        # Count section nodes (representing sheets)
        sections = count_nodes_by_type(skeleton, NodeType.CHAPTER) + \
                   count_nodes_by_type(skeleton, NodeType.SECTION)

        # Should have at least 2 sections (one per sheet)
        assert sections >= 2, \
            f"XLSX with 2 sheets should create at least 2 section nodes, got {sections}"

    @pytest.mark.asyncio
    async def test_xlsx_tables_attached_to_sections(self, document_processor, sample_xlsx):
        """
        Verify tables are correctly attached to section nodes.

        NUMERIC tables should be children of the sections they belong to.
        """
        document_id = await document_processor.process_document(str(sample_xlsx))
        skeleton = await document_processor.storage.load_skeleton(document_id)

        tables = [n for n in get_all_nodes(skeleton) if n.type == NodeType.TABLE]

        for table in tables:
            # Each table should have a parent
            assert table.parent_id is not None, \
                f"Table {table.id} should have a parent section"

            # Parent should exist
            parent = skeleton._nodes.get(table.parent_id)
            assert parent is not None, \
                f"Parent {table.parent_id} not found for table {table.id}"

            # Parent should be a section or chapter
            assert parent.type in [NodeType.SECTION, NodeType.CHAPTER, NodeType.ROOT], \
                f"Table {table.id} parent should be a section, got {parent.type}"

            # Parent should have table in children_ids
            assert table.id in parent.children_ids, \
                f"Table {table.id} not in parent's {table.parent_id} children"

    @pytest.mark.asyncio
    async def test_xlsx_data_can_be_reconstructed(self, document_processor, sample_xlsx):
        """
        Verify NUMERIC table data can be reconstructed for pandas.

        Table data should have the structure needed to create pandas DataFrames.
        """
        document_id = await document_processor.process_document(str(sample_xlsx))
        skeleton = await document_processor.storage.load_skeleton(document_id)

        tables = [n for n in get_all_nodes(skeleton) if n.type == NodeType.TABLE]

        for table in tables:
            if table.table_data and table.table_data.get("type") == "numeric":
                # Verify structure is pandas-compatible
                assert table.table_data is not None
                assert "data" in table.table_data

                # The data dict should allow reconstruction
                # (In production, Table Extractor will fill this with actual data)
                data = table.table_data["data"]
                assert isinstance(data, dict)

    @pytest.mark.asyncio
    async def test_xlsx_file_storage_roundtrip(self, document_processor, sample_xlsx):
        """
        Verify XLSX-processed skeleton survives save/load cycle.
        """
        document_id = await document_processor.process_document(str(sample_xlsx))

        # Load from storage
        skeleton = await document_processor.storage.load_skeleton(document_id)
        assert skeleton is not None

        # Verify tables are present after loading
        tables = [n for n in get_all_nodes(skeleton) if n.type == NodeType.TABLE]
        assert len(tables) >= 1, "Tables should be preserved in storage"

        # Verify NUMERIC type is preserved
        numeric_tables = [
            t for t in tables
            if t.table_data and t.table_data.get("type") == "numeric"
        ]
        assert len(numeric_tables) >= 1, "NUMERIC type should be preserved"

    @pytest.mark.asyncio
    async def test_xlsx_content_integrity(self, document_processor, sample_xlsx):
        """
        Verify document content is preserved through the pipeline.
        """
        document_id = await document_processor.process_document(str(sample_xlsx))
        skeleton = await document_processor.storage.load_skeleton(document_id)

        # Root should have content from MockVLMOCR
        root = await skeleton.get_root()
        assert root.content is not None
        assert len(root.content) > 0, "Root should have extracted content"

        # Verify content includes mentions of mock data
        # (MockVLMOCR returns predictable content)
        assert "Mock document text" in root.content or len(root.content) > 10


@pytest.mark.integration
@skip_if_no_poppler
class TestXLSXWithExpectedResults:
    """Integration tests that validate against expected XLSX results."""

    @pytest.mark.asyncio
    async def test_xlsx_matches_expected_structure(
        self, document_processor, sample_xlsx, xlsx_expected_result
    ):
        """Verify XLSX skeleton matches expected structure."""
        if not xlsx_expected_result:
            pytest.skip("xlsx_expected_result not available")

        document_id = await document_processor.process_document(str(sample_xlsx))
        skeleton = await document_processor.storage.load_skeleton(document_id)

        # Verify node count
        expected_nodes = xlsx_expected_result["expected_nodes"]
        actual_nodes = len(get_all_nodes(skeleton))

        # Allow some flexibility since XLSX conversion may vary
        assert actual_nodes >= expected_nodes, \
            f"Expected at least {expected_nodes} nodes, got {actual_nodes}"

        # Verify tables match
        from processing.tests.integration.conftest import assert_tables_match
        expected_tables = xlsx_expected_result["expected_tables"]
        assert_tables_match(skeleton, expected_tables)
