"""
Integration tests for FileStorage save/load functionality.

Tests DocumentSkeleton persistence and data integrity through save/load cycles.
"""
import pytest

from document import DocumentSkeleton, InternalStructure, Node, NodeType, PageRange
from processing.tests.integration.conftest import skip_if_no_poppler
from processing.vlm_ocr_extractor import DocumentData


@pytest.mark.integration
class TestFileStoragePersistence:
    """Integration tests for FileStorage save/load functionality."""

    @pytest.mark.asyncio
    async def test_save_and_load_skeleton(self, temp_storage_dir):
        """
        Test basic save/load cycle for DocumentSkeleton.

        Validates:
        - Skeleton is saved successfully
        - Skeleton is loaded correctly
        - All data is preserved
        """
        # Create a simple skeleton
        nodes = {
            "root": Node(
                id="root",
                type=NodeType.ROOT,
                title="Test Document",
                content="Full document content",
                page_range=PageRange(1, 5),
                parent_id=None,
                children_ids=["section_1"],
                internal_structure=InternalStructure(raw={}),
                explicit_refs=[],
                hash="",
            ),
            "section_1": Node(
                id="section_1",
                type=NodeType.CHAPTER,
                title="1. Section One",
                content="Content of section 1",
                page_range=PageRange(1, 3),
                parent_id="root",
                children_ids=[],
                internal_structure=InternalStructure(raw={}),
                explicit_refs=["section_2"],
                hash="",
            ),
        }

        skeleton = DocumentSkeleton(document_id="test_doc_1", nodes=nodes)

        # Create storage and save
        from storage.file_storage import FileStorage
        storage = FileStorage(base_path=temp_storage_dir)
        await storage.save_skeleton("test_doc_1", skeleton)

        # Load skeleton
        loaded_skeleton = await storage.load_skeleton("test_doc_1")

        # Verify loaded skeleton
        assert loaded_skeleton is not None
        assert loaded_skeleton.document_id == "test_doc_1"
        assert len(loaded_skeleton._nodes) == 2

        # Verify root node
        root = await loaded_skeleton.get_node("root")
        assert root.id == "root"
        assert root.type == NodeType.ROOT
        assert root.title == "Test Document"
        assert root.content == "Full document content"

        # Verify section node
        section_1 = await loaded_skeleton.get_node("section_1")
        assert section_1.id == "section_1"
        assert section_1.type == NodeType.CHAPTER
        assert section_1.parent_id == "root"

    @pytest.mark.asyncio
    async def test_save_skeleton_with_tables(self, temp_storage_dir):
        """
        Test save/load with tables (NUMERIC and TEXT_MATRIX).

        Validates that table_data is preserved correctly.
        """
        # Create skeleton with tables
        nodes = {
            "root": Node(
                id="root",
                type=NodeType.ROOT,
                title="Doc with Tables",
                content="Content",
                page_range=PageRange(1, 3),
                parent_id=None,
                children_ids=["section_1"],
                internal_structure=InternalStructure(raw={}),
                explicit_refs=[],
                hash="",
            ),
            "section_1": Node(
                id="section_1",
                type=NodeType.SECTION,
                title="1. Section",
                content="Section content",
                page_range=PageRange(1, 2),
                parent_id="root",
                children_ids=["table_numeric", "table_text"],
                internal_structure=InternalStructure(raw={}),
                explicit_refs=[],
                hash="",
            ),
            "table_numeric": Node(
                id="table_numeric",
                type=NodeType.TABLE,
                title="Numeric Table",
                content="",
                page_range=PageRange(1, 1),
                parent_id="section_1",
                children_ids=[],
                internal_structure=InternalStructure(raw={}),
                explicit_refs=[],
                table_data={
                    "type": "numeric",
                    "source": "original_file",
                    "data": {
                        "table_id": "table_numeric",
                        "location": {"page": 1, "bbox": [0, 0, 100, 100]},
                    }
                },
                hash="",
            ),
            "table_text": Node(
                id="table_text",
                type=NodeType.TABLE,
                title="Text Matrix Table",
                content="",
                page_range=PageRange(2, 2),
                parent_id="section_1",
                children_ids=[],
                internal_structure=InternalStructure(raw={}),
                explicit_refs=[],
                table_data={
                    "type": "text_matrix",
                    "source": "vlm_ocr",
                    "data": {
                        "table_id": "table_text",
                        "location": {"page": 2, "bbox": [0, 0, 100, 100]},
                        "flattened": ["Row 1", "Row 2", "Row 3"],
                    }
                },
                hash="",
            ),
        }

        skeleton = DocumentSkeleton(document_id="doc_with_tables", nodes=nodes)

        # Save and load
        from storage.file_storage import FileStorage
        storage = FileStorage(base_path=temp_storage_dir)
        await storage.save_skeleton("doc_with_tables", skeleton)

        loaded = await storage.load_skeleton("doc_with_tables")

        # Verify tables preserved
        assert len(loaded._nodes) == 4

        # Verify NUMERIC table
        numeric_table = await loaded.get_node("table_numeric")
        assert numeric_table.table_data is not None
        assert numeric_table.table_data["type"] == "numeric"
        assert numeric_table.table_data["source"] == "original_file"

        # Verify TEXT_MATRIX table
        text_table = await loaded.get_node("table_text")
        assert text_table.table_data is not None
        assert text_table.table_data["type"] == "text_matrix"
        assert text_table.table_data["source"] == "vlm_ocr"

    @pytest.mark.asyncio
    async def test_save_skeleton_with_internal_structure(self, temp_storage_dir):
        """
        Test save/load with internal_structure data.

        Validates that internal_structure.raw is preserved.
        """
        # Create skeleton with internal_structure
        nodes = {
            "root": Node(
                id="root",
                type=NodeType.ROOT,
                title="Document",
                content="Content",
                page_range=PageRange(1, 5),
                parent_id=None,
                children_ids=["section_1"],
                internal_structure=InternalStructure(raw={
                    "1. Section": {"level": 1, "page": 1, "node_id": "section_1"},
                    "2. Section": {"level": 1, "page": 3, "node_id": "section_2"},
                }),
                explicit_refs=[],
                hash="",
            ),
            "section_1": Node(
                id="section_1",
                type=NodeType.SECTION,
                title="1. Section",
                content="Content",
                page_range=PageRange(1, 2),
                parent_id="root",
                children_ids=[],
                internal_structure=InternalStructure(raw={}),
                explicit_refs=[],
                hash="",
            ),
        }

        skeleton = DocumentSkeleton(document_id="doc_internal", nodes=nodes)

        # Save and load
        from storage.file_storage import FileStorage
        storage = FileStorage(base_path=temp_storage_dir)
        await storage.save_skeleton("doc_internal", skeleton)

        loaded = await storage.load_skeleton("doc_internal")

        # Verify internal_structure preserved
        root = await loaded.get_node("root")
        assert len(root.internal_structure.raw) == 2
        assert "1. Section" in root.internal_structure.raw
        assert root.internal_structure.raw["1. Section"]["level"] == 1
        assert root.internal_structure.raw["1. Section"]["node_id"] == "section_1"

    @pytest.mark.asyncio
    async def test_load_nonexistent_skeleton(self, temp_storage_dir):
        """
        Test loading a skeleton that doesn't exist.

        Should return None, not raise an exception.
        """
        from storage.file_storage import FileStorage
        storage = FileStorage(base_path=temp_storage_dir)

        result = await storage.load_skeleton("nonexistent_doc")

        assert result is None

    @pytest.mark.asyncio
    async def test_document_exists(self, temp_storage_dir):
        """
        Test document_exists method.
        """
        from storage.file_storage import FileStorage
        storage = FileStorage(base_path=temp_storage_dir)

        # Create and save a skeleton
        nodes = {
            "root": Node(
                id="root",
                type=NodeType.ROOT,
                title="Test",
                content="Content",
                page_range=PageRange(1, 1),
                parent_id=None,
                children_ids=[],
                internal_structure=InternalStructure(raw={}),
                explicit_refs=[],
                hash="",
            )
        }
        skeleton = DocumentSkeleton(document_id="exists_test", nodes=nodes)
        await storage.save_skeleton("exists_test", skeleton)

        # Test exists
        assert storage.document_exists("exists_test") is True
        assert storage.document_exists("does_not_exist") is False

    @pytest.mark.asyncio
    async def test_save_overwrites_existing(self, temp_storage_dir):
        """
        Test that saving a skeleton with the same ID overwrites the old one.
        """
        from storage.file_storage import FileStorage
        storage = FileStorage(base_path=temp_storage_dir)

        # Save first version
        nodes_v1 = {
            "root": Node(
                id="root",
                type=NodeType.ROOT,
                title="Version 1",
                content="V1 content",
                page_range=PageRange(1, 1),
                parent_id=None,
                children_ids=[],
                internal_structure=InternalStructure(raw={}),
                explicit_refs=[],
                hash="",
            )
        }
        skeleton_v1 = DocumentSkeleton(document_id="overwrite_test", nodes=nodes_v1)
        await storage.save_skeleton("overwrite_test", skeleton_v1)

        # Save second version
        nodes_v2 = {
            "root": Node(
                id="root",
                type=NodeType.ROOT,
                title="Version 2",
                content="V2 content",
                page_range=PageRange(1, 2),
                parent_id=None,
                children_ids=[],
                internal_structure=InternalStructure(raw={}),
                explicit_refs=[],
                hash="",
            )
        }
        skeleton_v2 = DocumentSkeleton(document_id="overwrite_test", nodes=nodes_v2)
        await storage.save_skeleton("overwrite_test", skeleton_v2)

        # Load and verify we have V2
        loaded = await storage.load_skeleton("overwrite_test")
        root = await loaded.get_node("root")
        assert root.title == "Version 2"
        assert root.content == "V2 content"
        assert root.page_range.end == 2

    @pytest.mark.asyncio
    async def test_save_skeleton_with_explicit_refs(self, temp_storage_dir):
        """
        Test that explicit_refs are preserved.
        """
        nodes = {
            "root": Node(
                id="root",
                type=NodeType.ROOT,
                title="Document",
                content="Content",
                page_range=PageRange(1, 5),
                parent_id=None,
                children_ids=[],
                internal_structure=InternalStructure(raw={}),
                explicit_refs=["section_2", "appendix_a"],
                hash="",
            )
        }

        skeleton = DocumentSkeleton(document_id="refs_test", nodes=nodes)

        # Save and load
        from storage.file_storage import FileStorage
        storage = FileStorage(base_path=temp_storage_dir)
        await storage.save_skeleton("refs_test", skeleton)

        loaded = await storage.load_skeleton("refs_test")
        root = await loaded.get_node("root")

        assert len(root.explicit_refs) == 2
        assert "section_2" in root.explicit_refs
        assert "appendix_a" in root.explicit_refs

    @pytest.mark.asyncio
    async def test_hash_preserved_through_save_load(self, temp_storage_dir):
        """
        Test that node hashes are preserved.
        """
        nodes = {
            "root": Node(
                id="root",
                type=NodeType.ROOT,
                title="Hash Test",
                content="Content for hash",
                page_range=PageRange(1, 1),
                parent_id=None,
                children_ids=[],
                internal_structure=InternalStructure(raw={}),
                explicit_refs=[],
                hash="abc123",  # Pre-computed hash
            )
        }

        skeleton = DocumentSkeleton(document_id="hash_test", nodes=nodes)

        # Save and load
        from storage.file_storage import FileStorage
        storage = FileStorage(base_path=temp_storage_dir)
        await storage.save_skeleton("hash_test", skeleton)

        loaded = await storage.load_skeleton("hash_test")
        root = await loaded.get_node("root")

        assert root.hash == "abc123"


@pytest.mark.integration
@skip_if_no_poppler
class TestFileStorageWithDocumentProcessor:
    """Integration tests combining FileStorage with DocumentProcessor."""

    @pytest.mark.asyncio
    async def test_processor_save_load_roundtrip(self, document_processor, sample_docx):
        """
        Test complete roundtrip: Processor → Save → Load → Verify.

        This is a comprehensive integration test of the entire pipeline.
        """
        # Process document
        document_id = await document_processor.process_document(str(sample_docx))

        # Load from storage
        skeleton = await document_processor.storage.load_skeleton(document_id)

        # Verify all components worked together
        assert skeleton is not None
        assert skeleton.document_id == document_id

        # Verify we can navigate the structure
        root = await skeleton.get_root()
        assert root is not None

        # Verify children can be retrieved
        children = await skeleton.get_children("root")
        assert len(children) >= 1

        # Verify document hash can be computed
        doc_hash = await skeleton.get_document_hash()
        assert doc_hash is not None
        assert len(doc_hash) > 0
