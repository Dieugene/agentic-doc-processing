"""
Pytest fixtures for integration tests.

Provides DocumentProcessor and test fixtures for full pipeline testing.
"""
import asyncio
import json
import shutil
import tempfile
import uuid
from pathlib import Path
from typing import Optional

import pytest

from document import DocumentSkeleton
from processing.converter import Converter
from processing.mock_vlm_ocr import MockVLMOCR
from processing.renderer import Renderer
from processing.skeleton_builder import SkeletonBuilder
from processing.vlm_ocr_extractor import VLMOCRExtractor
from storage.file_storage import FileStorage


# ============================================================================
# Poppler Availability Check
# ============================================================================

def _is_poppler_available() -> bool:
    """Check if Poppler is installed and available in PATH."""
    try:
        # Try to import pdf2image and run a simple check
        from pdf2image import convert_from_path
        import tempfile
        import os

        # Create a minimal test PDF
        try:
            from fpdf import FPDF
            pdf = FPDF()
            pdf.add_page()
            pdf.set_font("Arial", size=12)
            pdf.cell(0, 10, text="Test")
            tmp_fd, tmp_path = tempfile.mkstemp(suffix=".pdf")
            os.close(tmp_fd)
            pdf.output(tmp_path)

            # Try to convert it
            result = convert_from_path(tmp_path, dpi=100)

            # Cleanup
            os.unlink(tmp_path)
            return True
        except Exception:
            return False
    except ImportError:
        return False


POPPLER_AVAILABLE = _is_poppler_available()

skip_if_no_poppler = pytest.mark.skipif(
    not POPPLER_AVAILABLE,
    reason="Poppler not installed or not in PATH. Install from https://github.com/oschwartz10612/poppler-windows/releases/"
)


# ============================================================================
# DocumentProcessor - Test Orchestrator
# ============================================================================

class DocumentProcessor:
    """
    Test orchestrator for full document processing pipeline.

    This class is NOT part of the production code - it's only for integration tests.
    The real pipeline orchestrator will be implemented in task 032 (Pipeline Orchestrator).
    """

    def __init__(
        self,
        converter: Converter,
        renderer: Renderer,
        vlm_extractor: VLMOCRExtractor,
        skeleton_builder: SkeletonBuilder,
        storage: FileStorage,
    ):
        """Initialize DocumentProcessor with all pipeline components."""
        self.converter = converter
        self.renderer = renderer
        self.vlm_extractor = vlm_extractor
        self.skeleton_builder = skeleton_builder
        self.storage = storage

    async def process_document(self, file_path: str) -> str:
        """
        Process document through the full pipeline.

        Pipeline:
        1. Detect file type
        2. Convert to PDF (if needed)
        3. Render to PNG images
        4. Extract data via VLM-OCR (mock)
        5. Build DocumentSkeleton
        6. Save to FileStorage

        Args:
            file_path: Path to source document

        Returns:
            document_id of the processed document

        Raises:
            FileNotFoundError: If file doesn't exist
            Exception: If any pipeline step fails
        """
        # 1. Detect file type
        file_type = await self.converter.detect_file_type(file_path)

        # 2. Convert to PDF if needed
        if file_type.value != "pdf":
            pdf_path = await self.converter.convert_to_pdf(file_path, file_type)
        else:
            pdf_path = file_path

        # 3. Render PDF to PNG
        images = await self.renderer.render_pdf_to_images(pdf_path)

        # 4. Extract data via VLM-OCR (mock)
        document_data = self.vlm_extractor.extract_full_document(images)

        # 5. Build DocumentSkeleton
        document_id = self._generate_id()
        skeleton = await self.skeleton_builder.build_skeleton(
            document_id=document_id,
            document_data=document_data,
        )

        # 6. Save to FileStorage
        await self.storage.save_skeleton(skeleton.document_id, skeleton)

        return skeleton.document_id

    def _generate_id(self) -> str:
        """Generate unique document ID."""
        return f"doc_{uuid.uuid4().hex[:16]}"


# ============================================================================
# Pytest Fixtures
# ============================================================================

@pytest.fixture
def temp_storage_dir(tmp_path):
    """Create temporary directory for FileStorage."""
    storage_dir = tmp_path / "storage"
    storage_dir.mkdir()
    return str(storage_dir)


@pytest.fixture
async def document_processor(temp_storage_dir):
    """Create DocumentProcessor with all components for testing."""
    # Create components
    converter = Converter()
    renderer = Renderer(dpi=200)
    mock_vlm = MockVLMOCR()  # Uses built-in mock responses
    vlm_extractor = VLMOCRExtractor(vlm_ocr_module=mock_vlm)
    skeleton_builder = SkeletonBuilder()
    storage = FileStorage(base_path=temp_storage_dir)

    # Create processor
    processor = DocumentProcessor(
        converter=converter,
        renderer=renderer,
        vlm_extractor=vlm_extractor,
        skeleton_builder=skeleton_builder,
        storage=storage,
    )

    yield processor

    # Cleanup: remove temp files
    import shutil
    if Path(temp_storage_dir).exists():
        shutil.rmtree(temp_storage_dir, ignore_errors=True)


@pytest.fixture
def fixtures_dir():
    """Get path to fixtures directory."""
    return Path(__file__).parent.parent / "fixtures"


@pytest.fixture
def sample_docx(fixtures_dir):
    """Get path to sample.docx fixture."""
    return fixtures_dir / "sample.docx"


@pytest.fixture
def sample_xlsx(fixtures_dir):
    """Get path to sample.xlsx fixture."""
    return fixtures_dir / "sample.xlsx"


@pytest.fixture
def sample_pdf(fixtures_dir):
    """Get path to sample.pdf fixture."""
    return fixtures_dir / "sample.pdf"


@pytest.fixture
def expected_results_dir(fixtures_dir):
    """Get path to expected_results directory."""
    return fixtures_dir / "expected_results"


@pytest.fixture
def docx_expected_result(expected_results_dir):
    """Load expected result for DOCX test."""
    path = expected_results_dir / "docx_skeleton.json"
    if path.exists():
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return None


@pytest.fixture
def xlsx_expected_result(expected_results_dir):
    """Load expected result for XLSX test."""
    path = expected_results_dir / "xlsx_skeleton.json"
    if path.exists():
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return None


@pytest.fixture
def pdf_expected_result(expected_results_dir):
    """Load expected result for PDF test."""
    path = expected_results_dir / "pdf_skeleton.json"
    if path.exists():
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return None


# ============================================================================
# Helper Functions
# ============================================================================

def count_nodes_by_type(skeleton: DocumentSkeleton, node_type):
    """Count nodes of specific type in skeleton."""
    from document import NodeType
    count = 0
    for node in skeleton._nodes.values():
        if node.type == node_type:
            count += 1
    return count


def get_all_nodes(skeleton: DocumentSkeleton):
    """Get all nodes from skeleton as a list."""
    return list(skeleton._nodes.values())


def assert_hierarchy_matches(skeleton: DocumentSkeleton, expected_hierarchy: dict):
    """
    Assert that skeleton hierarchy matches expected.

    Args:
        skeleton: DocumentSkeleton to check
        expected_hierarchy: Dict with parent -> list of children mapping
                          Example: {"root": ["section_1", "section_2"],
                                   "section_1": ["section_1_1", "section_1_2"]}
    """
    for parent_id, expected_children in expected_hierarchy.items():
        parent_node = skeleton._nodes.get(parent_id)
        assert parent_node is not None, f"Parent node {parent_id} not found"

        actual_children = set(parent_node.children_ids)
        expected_children_set = set(expected_children)

        assert actual_children == expected_children_set, \
            f"Children mismatch for {parent_id}: expected {expected_children_set}, got {actual_children}"


def assert_tables_match(skeleton: DocumentSkeleton, expected_tables: list):
    """
    Assert that tables in skeleton match expected.

    Args:
        skeleton: DocumentSkeleton to check
        expected_tables: List of dicts with keys: id, type, attached_to
    """
    from document import NodeType

    for expected_table in expected_tables:
        table_id = expected_table["id"]
        table_node = skeleton._nodes.get(table_id)

        assert table_node is not None, f"Table {table_id} not found"
        assert table_node.type == NodeType.TABLE, f"Node {table_id} is not a TABLE"

        # Check type
        if expected_table["type"] == "NUMERIC":
            assert table_node.table_data["type"] == "numeric"
        elif expected_table["type"] == "TEXT_MATRIX":
            assert table_node.table_data["type"] == "text_matrix"

        # Check attachment
        attached_to = expected_table["attached_to"]
        assert table_node.parent_id == attached_to, \
            f"Table {table_id} parent mismatch: expected {attached_to}, got {table_node.parent_id}"
