"""
Integration tests for DOCX document processing pipeline.

Tests the full pipeline: DOCX → PDF → PNG → MockVLMOCR → DocumentSkeleton → FileStorage
"""
import pytest

from document import NodeType
from processing.tests.integration.conftest import (
    assert_hierarchy_matches,
    assert_tables_match,
    count_nodes_by_type,
    get_all_nodes,
    skip_if_no_poppler,
)


@pytest.mark.integration
@skip_if_no_poppler
class TestDOCXPipeline:
    """Integration tests for DOCX file processing."""

    @pytest.mark.asyncio
    async def test_full_pipeline_docx(self, document_processor, sample_docx):
        """
        Test complete DOCX processing pipeline.

        Scenario:
        1. Load sample.docx
        2. Convert to PDF
        3. Render to PNG
        4. Extract data via MockVLMOCR
        5. Build DocumentSkeleton
        6. Save to FileStorage
        7. Load from FileStorage for verification

        Validates:
        - All steps complete successfully
        - DocumentSkeleton has correct structure
        - FileStorage save/load works correctly
        """
        # Process document through full pipeline
        document_id = await document_processor.process_document(str(sample_docx))

        # Verify document was saved
        assert document_id is not None
        assert document_id.startswith("doc_")

        # Load skeleton from storage
        skeleton = await document_processor.storage.load_skeleton(document_id)
        assert skeleton is not None
        assert skeleton.document_id == document_id

        # Verify basic structure
        root = await skeleton.get_root()
        assert root is not None
        assert root.type == NodeType.ROOT

        # Verify nodes were created
        all_nodes = get_all_nodes(skeleton)
        assert len(all_nodes) > 1  # At least root + some sections

    @pytest.mark.asyncio
    async def test_docx_hierarchy_correctness(self, document_processor, sample_docx):
        """Verify document hierarchy is correctly extracted from DOCX."""
        document_id = await document_processor.process_document(str(sample_docx))
        skeleton = await document_processor.storage.load_skeleton(document_id)

        # Verify root exists
        root = await skeleton.get_root()
        assert root.id == "root"
        assert root.type == NodeType.ROOT

        # Verify there are sections (CHAPTER/SECTION nodes)
        sections_count = count_nodes_by_type(skeleton, NodeType.CHAPTER) + \
                        count_nodes_by_type(skeleton, NodeType.SECTION)
        assert sections_count > 0, "Document should have at least one section"

        # Verify parent-child relationships
        for node in get_all_nodes(skeleton):
            if node.id == "root":
                continue

            # Every non-root node should have a parent
            assert node.parent_id is not None, f"Node {node.id} has no parent"

            # Parent should exist
            parent = skeleton._nodes.get(node.parent_id)
            assert parent is not None, f"Parent {node.parent_id} not found for {node.id}"

            # Parent should have this node in children_ids
            assert node.id in parent.children_ids, \
                f"Node {node.id} not in parent's {node.parent_id} children"

    @pytest.mark.asyncio
    async def test_docx_table_extraction(self, document_processor, sample_docx):
        """Verify NUMERIC tables are extracted from DOCX."""
        document_id = await document_processor.process_document(str(sample_docx))
        skeleton = await document_processor.storage.load_skeleton(document_id)

        # Count tables
        tables_count = count_nodes_by_type(skeleton, NodeType.TABLE)
        assert tables_count >= 1, "Document should have at least one table"

        # Verify table structure
        tables = [n for n in get_all_nodes(skeleton) if n.type == NodeType.TABLE]
        for table in tables:
            assert table.table_data is not None, f"Table {table.id} should have table_data"
            assert "type" in table.table_data, f"Table {table.id} should have type in table_data"

            # Verify NUMERIC type tables
            if table.table_data["type"] == "numeric":
                assert table.table_data["source"] == "original_file"

    @pytest.mark.asyncio
    async def test_docx_file_storage_persistence(self, document_processor, sample_docx):
        """Verify FileStorage correctly saves and loads DocumentSkeleton."""
        document_id = await document_processor.process_document(str(sample_docx))

        # Load from storage
        loaded_skeleton = await document_processor.storage.load_skeleton(document_id)
        assert loaded_skeleton is not None

        # Verify document_id matches
        assert loaded_skeleton.document_id == document_id

        # Verify all nodes are present
        original_nodes = set(loaded_skeleton._nodes.keys())
        assert len(original_nodes) > 0

        # Verify can retrieve individual nodes
        for node_id in original_nodes:
            node = await loaded_skeleton.get_node(node_id)
            assert node is not None
            assert node.id == node_id

    @pytest.mark.asyncio
    async def test_docx_content_not_empty(self, document_processor, sample_docx):
        """Verify extracted content is not empty."""
        document_id = await document_processor.process_document(str(sample_docx))
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

    @pytest.mark.asyncio
    async def test_docx_page_ranges_valid(self, document_processor, sample_docx):
        """Verify all page ranges are valid."""
        document_id = await document_processor.process_document(str(sample_docx))
        skeleton = await document_processor.storage.load_skeleton(document_id)

        for node in get_all_nodes(skeleton):
            assert node.page_range.start >= 1, \
                f"Node {node.id} has invalid page_range.start: {node.page_range.start}"
            assert node.page_range.end >= node.page_range.start, \
                f"Node {node.id} has invalid page_range: {node.page_range.start}-{node.page_range.end}"

    @pytest.mark.asyncio
    async def test_docx_hashes_computed(self, document_processor, sample_docx):
        """Verify content hashes are computed for all nodes."""
        document_id = await document_processor.process_document(str(sample_docx))
        skeleton = await document_processor.storage.load_skeleton(document_id)

        for node in get_all_nodes(skeleton):
            assert node.hash is not None, f"Node {node.id} should have hash computed"
            assert len(node.hash) > 0, f"Node {node.id} hash should not be empty"


@pytest.mark.integration
@skip_if_no_poppler
class TestDOCXWithExpectedResults:
    """Integration tests that validate against expected results."""

    @pytest.mark.asyncio
    async def test_docx_matches_expected_structure(
        self, document_processor, sample_docx, docx_expected_result
    ):
        """Verify DOCX skeleton matches expected structure."""
        if not docx_expected_result:
            pytest.skip("docx_expected_result not available")

        document_id = await document_processor.process_document(str(sample_docx))
        skeleton = await document_processor.storage.load_skeleton(document_id)

        # Verify node count matches
        expected_nodes = docx_expected_result["expected_nodes"]
        actual_nodes = len(get_all_nodes(skeleton))
        assert actual_nodes == expected_nodes, \
            f"Expected {expected_nodes} nodes, got {actual_nodes}"

        # Verify hierarchy matches
        expected_hierarchy = docx_expected_result["expected_hierarchy"]
        assert_hierarchy_matches(skeleton, expected_hierarchy)

        # Verify tables match
        expected_tables = docx_expected_result["expected_tables"]
        assert_tables_match(skeleton, expected_tables)
