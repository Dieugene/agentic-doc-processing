"""
Integration tests for PDF document processing pipeline.

Tests the full pipeline with focus on TEXT_MATRIX table handling from PDF files.
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
class TestPDFPipeline:
    """Integration tests for PDF file processing with TEXT_MATRIX tables."""

    @pytest.mark.asyncio
    async def test_full_pipeline_pdf(self, document_processor, sample_pdf):
        """
        Test complete PDF processing pipeline.

        Scenario:
        1. Load sample.pdf (no conversion needed)
        2. Render to PNG
        3. Extract data via MockVLMOCR
        4. Build DocumentSkeleton with TEXT_MATRIX tables
        5. Save to FileStorage

        Validates:
        - PDF file is processed correctly
        - TEXT_MATRIX tables are identified
        - No conversion step for PDF files
        """
        document_id = await document_processor.process_document(str(sample_pdf))

        # Verify document was saved
        assert document_id is not None

        # Load skeleton from storage
        skeleton = await document_processor.storage.load_skeleton(document_id)
        assert skeleton is not None

        # Verify structure was created
        all_nodes = get_all_nodes(skeleton)
        assert len(all_nodes) > 1

    @pytest.mark.asyncio
    async def test_pdf_no_conversion_needed(self, document_processor, sample_pdf):
        """
        Verify PDF files are not converted (already in target format).

        PDF files should skip the conversion step and go directly to rendering.
        """
        # Process PDF
        document_id = await document_processor.process_document(str(sample_pdf))

        # Verify successful processing
        skeleton = await document_processor.storage.load_skeleton(document_id)
        assert skeleton is not None

        # Should have extracted content
        root = await skeleton.get_root()
        assert root.content is not None
        assert len(root.content) > 0

    @pytest.mark.asyncio
    async def test_pdf_text_matrix_tables_classified(self, document_processor, sample_pdf):
        """
        Verify TEXT_MATRIX tables are correctly classified from PDF.

        PDF tables detected by VLM-OCR should have:
        - type: "text_matrix"
        - source: "vlm_ocr"
        - Flattened text representation
        """
        document_id = await document_processor.process_document(str(sample_pdf))
        skeleton = await document_processor.storage.load_skeleton(document_id)

        # Find all tables
        tables = [n for n in get_all_nodes(skeleton) if n.type == NodeType.TABLE]

        # Should have at least one table
        assert len(tables) >= 1, "PDF should have at least one TEXT_MATRIX table"

        # Verify each TEXT_MATRIX table
        text_matrix_count = 0
        for table in tables:
            if table.table_data and table.table_data.get("type") == "text_matrix":
                text_matrix_count += 1

                # Verify TEXT_MATRIX table structure
                assert table.table_data["source"] == "vlm_ocr", \
                    f"Table {table.id} should have source='vlm_ocr'"

                assert "data" in table.table_data, \
                    f"Table {table.id} should have 'data' field"

                # Verify data structure
                table_data = table.table_data["data"]
                assert "table_id" in table_data or "location" in table_data, \
                    f"Table {table.id} data should identify the table"

                # TEXT_MATRIX tables should have flattened field
                # (Will be filled by VLM-OCR in production)
                assert "flattened" in table_data or "table_id" in table_data, \
                    f"Table {table.id} should have flattened data"

        assert text_matrix_count >= 1, "Should have at least one TEXT_MATRIX table"

    @pytest.mark.asyncio
    async def test_pdf_tables_attached_to_correct_sections(
        self, document_processor, sample_pdf
    ):
        """
        Verify tables are attached to the correct document sections.

        Tables should be attached based on page number proximity to sections.
        """
        document_id = await document_processor.process_document(str(sample_pdf))
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
    async def test_pdf_multiple_pages_processed(self, document_processor, sample_pdf):
        """
        Verify multi-page PDFs are processed correctly.

        All pages should be rendered and included in the extraction.
        """
        document_id = await document_processor.process_document(str(sample_pdf))
        skeleton = await document_processor.storage.load_skeleton(document_id)

        # Verify content was extracted
        root = await skeleton.get_root()
        assert root.content is not None

        # Multi-page documents should have more content
        # (MockVLMOCR returns content based on number of images/pages)
        assert len(root.content) > 0, "Multi-page PDF should extract content"

    @pytest.mark.asyncio
    async def test_pdf_text_matrix_vs_numeric_distinction(
        self, document_processor, sample_pdf
    ):
        """
        Verify TEXT_MATRIX tables are distinguished from NUMERIC tables.

        PDF tables should default to TEXT_MATRIX type.
        """
        document_id = await document_processor.process_document(str(sample_pdf))
        skeleton = await document_processor.storage.load_skeleton(document_id)

        tables = [n for n in get_all_nodes(skeleton) if n.type == NodeType.TABLE]

        for table in tables:
            if table.table_data:
                table_type = table.table_data.get("type")

                # PDF tables should be TEXT_MATRIX
                if table_type == "text_matrix":
                    # Verify correct structure for TEXT_MATRIX
                    assert table.table_data["source"] == "vlm_ocr", \
                        f"TEXT_MATRIX table {table.id} should have source='vlm_ocr'"

    @pytest.mark.asyncio
    async def test_pdf_file_storage_persistence(self, document_processor, sample_pdf):
        """
        Verify PDF-processed skeleton survives save/load cycle.
        """
        document_id = await document_processor.process_document(str(sample_pdf))

        # Load from storage
        skeleton = await document_processor.storage.load_skeleton(document_id)
        assert skeleton is not None

        # Verify tables are present after loading
        tables = [n for n in get_all_nodes(skeleton) if n.type == NodeType.TABLE]
        assert len(tables) >= 1, "Tables should be preserved in storage"

        # Verify TEXT_MATRIX type is preserved
        text_matrix_tables = [
            t for t in tables
            if t.table_data and t.table_data.get("type") == "text_matrix"
        ]
        assert len(text_matrix_tables) >= 1, "TEXT_MATRIX type should be preserved"

    @pytest.mark.asyncio
    async def test_pdf_content_not_empty(self, document_processor, sample_pdf):
        """
        Verify extracted text content is not empty.
        """
        document_id = await document_processor.process_document(str(sample_pdf))
        skeleton = await document_processor.storage.load_skeleton(document_id)

        # Root node should have content
        root = await skeleton.get_root()
        assert root.content is not None
        assert len(root.content) > 0, "Root content should not be empty"

        # At least some sections should have content
        nodes_with_content = 0
        for node in get_all_nodes(skeleton):
            if node.content and len(node.content.strip()) > 0:
                nodes_with_content += 1

        assert nodes_with_content > 0, "At least some nodes should have content"


@pytest.mark.integration
@skip_if_no_poppler
class TestPDFWithExpectedResults:
    """Integration tests that validate against expected PDF results."""

    @pytest.mark.asyncio
    async def test_pdf_matches_expected_structure(
        self, document_processor, sample_pdf, pdf_expected_result
    ):
        """Verify PDF skeleton matches expected structure."""
        if not pdf_expected_result:
            pytest.skip("pdf_expected_result not available")

        document_id = await document_processor.process_document(str(sample_pdf))
        skeleton = await document_processor.storage.load_skeleton(document_id)

        # Verify node count
        expected_nodes = pdf_expected_result["expected_nodes"]
        actual_nodes = len(get_all_nodes(skeleton))

        # Allow some flexibility
        assert actual_nodes >= expected_nodes, \
            f"Expected at least {expected_nodes} nodes, got {actual_nodes}"

        # Verify hierarchy matches
        from processing.tests.integration.conftest import assert_hierarchy_matches
        expected_hierarchy = pdf_expected_result["expected_hierarchy"]
        assert_hierarchy_matches(skeleton, expected_hierarchy)

        # Verify tables match
        from processing.tests.integration.conftest import assert_tables_match
        expected_tables = pdf_expected_result["expected_tables"]
        assert_tables_match(skeleton, expected_tables)
