"""
Unit tests for FileStorage.

Tests cover save/load operations, error handling, and configuration.
"""
import json
import sys
from pathlib import Path

import pytest

from document.skeleton import DocumentSkeleton, InternalStructure, Node, NodeType, PageRange
from storage.file_storage import FileStorage, Storage, StorageError


class TestStorageABC:
    """Tests for Storage abstract base class."""

    def test_storage_is_abstract(self):
        """Storage ABC cannot be instantiated directly."""
        with pytest.raises(TypeError):
            Storage()

    def test_file_storage_is_storage(self):
        """FileStorage implements Storage interface."""
        assert issubclass(FileStorage, Storage)


class TestFileStorageInit:
    """Tests for FileStorage initialization."""

    def test_init_creates_directory(self, tmp_path):
        """Constructor creates base_path directory if it doesn't exist."""
        base = tmp_path / "data"
        storage = FileStorage(base_path=str(base))
        assert base.exists()
        assert storage.base_path == base

    def test_init_with_env_default(self, tmp_path, monkeypatch):
        """Constructor uses STORAGE_BASE_PATH from env if not provided."""
        monkeypatch.setenv("STORAGE_BASE_PATH", str(tmp_path / "data"))
        storage = FileStorage()
        assert storage.base_path == tmp_path / "data"


class TestFileStorageSave:
    """Tests for save_skeleton method."""

    @pytest.fixture
    def sample_skeleton(self):
        """Create a sample DocumentSkeleton for testing."""
        nodes = {
            "root": Node(
                id="root",
                type=NodeType.ROOT,
                title="Test Document",
                content="Root content",
                page_range=PageRange(1, 100),
                parent_id=None,
                children_ids=["section_1"],
                internal_structure=InternalStructure(),
                explicit_refs=[],
                hash="root_hash",
            ),
            "section_1": Node(
                id="section_1",
                type=NodeType.CHAPTER,
                title="1. First Section",
                content="Section content",
                page_range=PageRange(1, 10),
                parent_id="root",
                children_ids=[],
                internal_structure=InternalStructure(raw={"1.1": {"title": "Subsection", "page": 2}}),
                explicit_refs=[],
                hash="section_hash",
            ),
        }
        return DocumentSkeleton(document_id="test_doc", nodes=nodes)

    def test_save_skeleton_creates_directory(self, temp_storage, sample_skeleton):
        """save_skeleton creates document directory."""
        import asyncio

        asyncio.run(temp_storage.save_skeleton("test_doc", sample_skeleton))
        doc_dir = temp_storage.base_path / "test_doc"
        assert doc_dir.exists()
        assert doc_dir.is_dir()

    def test_save_skeleton_creates_json_file(self, temp_storage, sample_skeleton):
        """save_skeleton creates skeleton.json file."""
        import asyncio

        asyncio.run(temp_storage.save_skeleton("test_doc", sample_skeleton))
        skeleton_path = temp_storage.base_path / "test_doc" / "skeleton.json"
        assert skeleton_path.exists()
        assert skeleton_path.is_file()

    def test_save_skeleton_serializes_all_fields(self, temp_storage, sample_skeleton):
        """save_skeleton serializes all node fields to JSON."""
        import asyncio

        asyncio.run(temp_storage.save_skeleton("test_doc", sample_skeleton))

        with open(temp_storage.base_path / "test_doc" / "skeleton.json", encoding="utf-8") as f:
            data = json.load(f)

        assert data["document_id"] == "test_doc"
        assert "created_at" in data
        assert "nodes" in data
        assert "root" in data["nodes"]
        assert "section_1" in data["nodes"]

        root = data["nodes"]["root"]
        assert root["id"] == "root"
        assert root["type"] == "root"
        assert root["title"] == "Test Document"
        assert root["content"] == "Root content"
        assert root["page_range"] == {"start": 1, "end": 100}
        assert root["parent_id"] is None
        assert root["children_ids"] == ["section_1"]
        assert root["hash"] == "root_hash"

    def test_save_skeleton_with_internal_structure(self, temp_storage):
        """save_skeleton serializes internal_structure correctly."""
        import asyncio

        nodes = {
            "root": Node(
                id="root",
                type=NodeType.ROOT,
                title="Test",
                content="Content",
                page_range=PageRange(1, 10),
                parent_id=None,
                children_ids=[],
                internal_structure=InternalStructure(raw={"1.1": {"title": "Sub", "page": 2}}),
                explicit_refs=[],
                hash="hash",
            ),
        }
        skeleton = DocumentSkeleton(document_id="test", nodes=nodes)
        asyncio.run(temp_storage.save_skeleton("test", skeleton))

        with open(temp_storage.base_path / "test" / "skeleton.json", encoding="utf-8") as f:
            data = json.load(f)

        assert data["nodes"]["root"]["internal_structure"] == {"1.1": {"title": "Sub", "page": 2}}

    def test_save_skeleton_with_table_data(self, temp_storage):
        """save_skeleton serializes table_data correctly."""
        import asyncio

        nodes = {
            "root": Node(
                id="root",
                type=NodeType.ROOT,
                title="Test",
                content="Content",
                page_range=PageRange(1, 10),
                parent_id=None,
                children_ids=[],
                internal_structure=InternalStructure(),
                explicit_refs=[],
                hash="hash",
                table_data={"columns": ["A", "B"], "data": [[1, 2], [3, 4]]},
            ),
        }
        skeleton = DocumentSkeleton(document_id="test", nodes=nodes)
        asyncio.run(temp_storage.save_skeleton("test", skeleton))

        with open(temp_storage.base_path / "test" / "skeleton.json", encoding="utf-8") as f:
            data = json.load(f)

        assert data["nodes"]["root"]["table_data"] == {"columns": ["A", "B"], "data": [[1, 2], [3, 4]]}

    def test_save_skeleton_overwrites_existing(self, temp_storage, sample_skeleton):
        """save_skeleton overwrites existing skeleton.json."""
        import asyncio

        # First save
        asyncio.run(temp_storage.save_skeleton("test_doc", sample_skeleton))

        # Modify content
        sample_skeleton._nodes["root"].title = "Modified Title"

        # Second save
        asyncio.run(temp_storage.save_skeleton("test_doc", sample_skeleton))

        # Verify modification
        with open(temp_storage.base_path / "test_doc" / "skeleton.json", encoding="utf-8") as f:
            data = json.load(f)

        assert data["nodes"]["root"]["title"] == "Modified Title"

    @pytest.mark.skipif(sys.platform == "win32", reason="chmod doesn't work on Windows")
    def test_save_skeleton_permission_denied(self, temp_storage, sample_skeleton, tmp_path):
        """save_skeleton raises StorageError on permission denied."""
        import asyncio

        # Create read-only directory
        base = tmp_path / "readonly"
        base.mkdir()
        storage = FileStorage(base_path=str(base))

        # Make directory read-only
        import stat

        base.chmod(stat.S_IRUSR | stat.S_IXUSR)

        try:
            with pytest.raises(StorageError):
                asyncio.run(storage.save_skeleton("test", sample_skeleton))
        finally:
            # Restore permissions for cleanup
            base.chmod(stat.S_IRWXU)


class TestFileStorageLoad:
    """Tests for load_skeleton method."""

    def test_load_skeleton_restores_document(self, temp_storage, sample_skeleton):
        """load_skeleton restores DocumentSkeleton from JSON."""
        import asyncio

        # Save first
        asyncio.run(temp_storage.save_skeleton("test_doc", sample_skeleton))

        # Load back
        loaded = asyncio.run(temp_storage.load_skeleton("test_doc"))

        assert loaded is not None
        assert loaded.document_id == "test_doc"
        assert len(loaded._nodes) == 2
        assert "root" in loaded._nodes
        assert "section_1" in loaded._nodes

        root = loaded._nodes["root"]
        assert root.type == NodeType.ROOT
        assert root.title == sample_skeleton._nodes["root"].title
        assert root.content == sample_skeleton._nodes["root"].content

    def test_load_skeleton_not_exists(self, temp_storage):
        """load_skeleton returns None for non-existent document."""
        import asyncio

        result = asyncio.run(temp_storage.load_skeleton("nonexistent"))
        assert result is None

    def test_load_skeleton_invalid_json(self, temp_storage):
        """load_skeleton raises StorageError for corrupted JSON."""
        # Create corrupted file
        doc_dir = temp_storage.base_path / "test_doc"
        doc_dir.mkdir(parents=True, exist_ok=True)
        skeleton_path = doc_dir / "skeleton.json"
        with open(skeleton_path, "w", encoding="utf-8") as f:
            f.write("{invalid json}")

        import asyncio

        with pytest.raises(StorageError, match="Corrupted skeleton"):
            asyncio.run(temp_storage.load_skeleton("test_doc"))

    def test_load_skeleton_all_node_types(self, temp_storage):
        """load_skeleton restores all node types correctly."""
        import asyncio

        nodes = {
            "root": Node(
                id="root",
                type=NodeType.ROOT,
                title="Root",
                content="Root",
                page_range=PageRange(1, 100),
                parent_id=None,
                children_ids=["ch1", "sec1"],
                internal_structure=InternalStructure(),
                explicit_refs=[],
                hash="h1",
            ),
            "ch1": Node(
                id="ch1",
                type=NodeType.CHAPTER,
                title="Chapter",
                content="Chapter",
                page_range=PageRange(1, 50),
                parent_id="root",
                children_ids=[],
                internal_structure=InternalStructure(),
                explicit_refs=[],
                hash="h2",
            ),
            "sec1": Node(
                id="sec1",
                type=NodeType.SECTION,
                title="Section",
                content="Section",
                page_range=PageRange(51, 60),
                parent_id="root",
                children_ids=[],
                internal_structure=InternalStructure(),
                explicit_refs=[],
                hash="h3",
            ),
            "tbl1": Node(
                id="tbl1",
                type=NodeType.TABLE,
                title="Table 1",
                content="Table",
                page_range=PageRange(10, 11),
                parent_id="ch1",
                children_ids=[],
                internal_structure=InternalStructure(),
                explicit_refs=[],
                hash="h4",
                table_data={"cols": ["A"], "data": [[1]]},
            ),
        }
        skeleton = DocumentSkeleton(document_id="test", nodes=nodes)
        asyncio.run(temp_storage.save_skeleton("test", skeleton))

        loaded = asyncio.run(temp_storage.load_skeleton("test"))
        assert loaded._nodes["root"].type == NodeType.ROOT
        assert loaded._nodes["ch1"].type == NodeType.CHAPTER
        assert loaded._nodes["sec1"].type == NodeType.SECTION
        assert loaded._nodes["tbl1"].type == NodeType.TABLE
        assert loaded._nodes["tbl1"].table_data == {"cols": ["A"], "data": [[1]]}


class TestFileStorageExists:
    """Tests for document_exists method."""

    def test_document_exists_true(self, temp_storage, sample_skeleton):
        """document_exists returns True for existing document."""
        import asyncio

        asyncio.run(temp_storage.save_skeleton("test_doc", sample_skeleton))
        assert temp_storage.document_exists("test_doc") is True

    def test_document_exists_false(self, temp_storage):
        """document_exists returns False for non-existent document."""
        assert temp_storage.document_exists("nonexistent") is False


class TestFileStorageFixtures:
    """Tests using sample_skeleton.json fixture."""

    def test_load_sample_skeleton_fixture(self, temp_storage, sample_skeleton_from_json):
        """Load sample_skeleton.json fixture correctly."""
        import asyncio

        # Save fixture skeleton
        asyncio.run(temp_storage.save_skeleton("doc_714p", sample_skeleton_from_json))

        # Load back and verify
        loaded = asyncio.run(temp_storage.load_skeleton("doc_714p"))

        assert loaded.document_id == "doc_714p"
        assert len(loaded._nodes) == 5
        assert loaded._nodes["root"].type == NodeType.ROOT
        assert loaded._nodes["section_1"].type == NodeType.CHAPTER
        assert loaded._nodes["section_1_1"].type == NodeType.SECTION
        assert loaded._nodes["section_3"].table_data is not None


# Fixtures


@pytest.fixture
def temp_storage(tmp_path):
    """Create FileStorage with temporary directory for testing."""
    base = tmp_path / "data"
    return FileStorage(base_path=str(base))


@pytest.fixture
def sample_skeleton():
    """Create minimal sample DocumentSkeleton for tests."""
    nodes = {
        "root": Node(
            id="root",
            type=NodeType.ROOT,
            title="Test Document",
            content="Root content",
            page_range=PageRange(1, 100),
            parent_id=None,
            children_ids=["section_1"],
            internal_structure=InternalStructure(),
            explicit_refs=[],
            hash="root_hash",
        ),
        "section_1": Node(
            id="section_1",
            type=NodeType.CHAPTER,
            title="1. First Section",
            content="Section content",
            page_range=PageRange(1, 10),
            parent_id="root",
            children_ids=[],
            internal_structure=InternalStructure(raw={"1.1": {"title": "Subsection", "page": 2}}),
            explicit_refs=[],
            hash="section_hash",
        ),
    }
    return DocumentSkeleton(document_id="test_doc", nodes=nodes)


@pytest.fixture
def sample_skeleton_from_json():
    """Load sample_skeleton.json and return DocumentSkeleton."""
    fixtures_path = Path(__file__).parent / "fixtures" / "sample_skeleton.json"

    with open(fixtures_path, encoding="utf-8") as f:
        data = json.load(f)

    nodes = {}
    for node_id, node_data in data["nodes"].items():
        nodes[node_id] = Node(
            id=node_data["id"],
            type=NodeType(node_data["type"]),
            title=node_data.get("title"),
            content=node_data.get("content", ""),
            page_range=PageRange(**node_data["page_range"]),
            parent_id=node_data.get("parent_id"),
            children_ids=node_data.get("children_ids", []),
            internal_structure=InternalStructure(raw=node_data.get("internal_structure", {})),
            explicit_refs=node_data.get("explicit_refs", []),
            hash=node_data["hash"],
            table_data=node_data.get("table_data"),
        )

    return DocumentSkeleton(document_id=data["document_id"], nodes=nodes)
