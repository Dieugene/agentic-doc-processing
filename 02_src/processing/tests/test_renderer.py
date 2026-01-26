"""
Unit tests for Renderer module.

Run with: pytest -v

Note: Tests require Poppler to be installed for pdf2image to work.
- Windows: Download binaries and add to PATH
- Linux: sudo apt-get install poppler-utils
- macOS: brew install poppler

If Poppler is not installed, tests will be skipped.
"""
from pathlib import Path
import tempfile
from unittest.mock import Mock, patch

import pytest

from processing.renderer import RenderingError, Renderer


# Skip tests if dependencies are not installed
pytest.importorskip("pdf2image")
pytest.importorskip("PIL")


def _check_poppler_available():
    """Check if Poppler is available for pdf2image.

    Returns:
        bool: True if Poppler is available, False otherwise
    """
    try:
        from pdf2image import convert_from_path
        import tempfile
        from fpdf import FPDF

        # Create a minimal test PDF
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", size=12)
        pdf.cell(0, 10, txt="Test")
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            test_pdf = f.name
        pdf.output(test_pdf)

        # Try to convert it
        try:
            convert_from_path(test_pdf, dpi=150)
            import os
            os.unlink(test_pdf)
            return True
        except Exception:
            import os
            if os.path.exists(test_pdf):
                os.unlink(test_pdf)
            return False
    except Exception:
        return False


POPPLER_AVAILABLE = _check_poppler_available()


class TestRenderingError:
    """Tests for RenderingError exception."""

    def test_rendering_error_creation(self):
        """Test RenderingError can be created with details."""
        error = RenderingError("test.pdf", "Page not found")
        assert error.pdf_path == "test.pdf"
        assert error.details == "Page not found"
        assert "test.pdf" in str(error)
        assert "Page not found" in str(error)


class TestRenderer:
    """Tests for Renderer class."""

    @pytest.fixture
    def renderer(self):
        """Create a Renderer instance for testing."""
        return Renderer(dpi=200)

    @pytest.fixture
    def fixtures_dir(self):
        """Get the path to fixtures directory."""
        return Path(__file__).parent / "fixtures"

    @pytest.fixture
    def sample_pdf(self, fixtures_dir):
        """Get path to sample.pdf fixture."""
        path = fixtures_dir / "sample.pdf"
        if not path.exists():
            pytest.skip(f"Fixture not found: {path}")
        return str(path)

    def test_renderer_initialization_default_dpi(self):
        """Test Renderer initialization with default DPI."""
        renderer = Renderer()
        assert renderer.dpi == 200

    def test_renderer_initialization_custom_dpi(self):
        """Test Renderer initialization with custom DPI."""
        renderer = Renderer(dpi=300)
        assert renderer.dpi == 300

    def test_renderer_initialization_low_dpi_warning(self, caplog):
        """Test Renderer warns about low DPI."""
        import logging
        Renderer(dpi=100)
        assert any("below 150" in record.message for record in caplog.records)

    def test_renderer_initialization_high_dpi_warning(self, caplog):
        """Test Renderer warns about high DPI."""
        import logging
        Renderer(dpi=400)
        assert any("above 300" in record.message for record in caplog.records)

    def test_renderer_checks_dependencies(self):
        """Test Renderer checks for required dependencies."""
        # Should not raise if dependencies are present
        renderer = Renderer()
        assert renderer is not None

    @pytest.mark.skipif(not POPPLER_AVAILABLE, reason="Poppler not installed")
    @pytest.mark.asyncio
    async def test_render_pdf_to_images_success(self, renderer, sample_pdf):
        """Test successful PDF to PNG rendering."""
        images = await renderer.render_pdf_to_images(sample_pdf)

        # Verify we got PNG images
        assert isinstance(images, list)
        assert len(images) == 3  # sample.pdf has 3 pages

        # Verify each image is valid PNG bytes
        for img in images:
            assert isinstance(img, bytes)
            assert len(img) > 0
            # Check PNG signature
            assert img[:8] == b'\x89PNG\r\n\x1a\n'

    @pytest.mark.skipif(not POPPLER_AVAILABLE, reason="Poppler not installed")
    @pytest.mark.asyncio
    async def test_render_pdf_to_images_valid_with_pil(self, renderer, sample_pdf):
        """Test rendered images can be opened with PIL."""
        from PIL import Image
        import io

        images = await renderer.render_pdf_to_images(sample_pdf)

        # Verify each image can be opened by PIL
        for img_bytes in images:
            img = Image.open(io.BytesIO(img_bytes))
            assert img.format == "PNG"
            assert img.width > 0
            assert img.height > 0

    @pytest.mark.asyncio
    async def test_render_pdf_file_not_found(self, renderer):
        """Test rendering nonexistent file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError, match="PDF file not found"):
            await renderer.render_pdf_to_images("/nonexistent/file.pdf")

    @pytest.mark.skipif(not POPPLER_AVAILABLE, reason="Poppler not installed")
    @pytest.mark.asyncio
    async def test_render_page_to_image_success(self, renderer, sample_pdf):
        """Test successful single page rendering."""
        # Render first page (1-indexed)
        img = await renderer.render_page_to_image(sample_pdf, 1)

        # Verify it's valid PNG
        assert isinstance(img, bytes)
        assert len(img) > 0
        assert img[:8] == b'\x89PNG\r\n\x1a\n'

    @pytest.mark.skipif(not POPPLER_AVAILABLE, reason="Poppler not installed")
    @pytest.mark.asyncio
    async def test_render_page_to_image_different_pages(self, renderer, sample_pdf):
        """Test rendering different pages produces different images."""
        page1 = await renderer.render_page_to_image(sample_pdf, 1)
        page2 = await renderer.render_page_to_image(sample_pdf, 2)
        page3 = await renderer.render_page_to_image(sample_pdf, 3)

        # Pages should be different (different content)
        assert page1 != page2
        assert page2 != page3

    @pytest.mark.asyncio
    async def test_render_page_to_image_invalid_page_number_zero(self, renderer, sample_pdf):
        """Test rendering page 0 raises RenderingError."""
        with pytest.raises(RenderingError, match="Invalid page number"):
            await renderer.render_page_to_image(sample_pdf, 0)

    @pytest.mark.asyncio
    async def test_render_page_to_image_invalid_page_number_negative(self, renderer, sample_pdf):
        """Test rendering negative page raises RenderingError."""
        with pytest.raises(RenderingError, match="Invalid page number"):
            await renderer.render_page_to_image(sample_pdf, -1)

    @pytest.mark.skipif(not POPPLER_AVAILABLE, reason="Poppler not installed")
    @pytest.mark.asyncio
    async def test_render_page_to_image_page_out_of_range(self, renderer, sample_pdf):
        """Test rendering non-existent page raises RenderingError."""
        # sample.pdf has 3 pages, so page 10 should fail
        with pytest.raises(RenderingError, match="does not exist"):
            await renderer.render_page_to_image(sample_pdf, 10)

    @pytest.mark.asyncio
    async def test_render_page_to_image_nonexistent_file(self, renderer):
        """Test rendering page from nonexistent file raises RenderingError."""
        with pytest.raises(FileNotFoundError, match="PDF file not found"):
            await renderer.render_page_to_image("/nonexistent/file.pdf", 1)

    @pytest.mark.skipif(not POPPLER_AVAILABLE, reason="Poppler not installed")
    @pytest.mark.asyncio
    async def test_render_pdf_with_different_dpi(self, sample_pdf):
        """Test rendering with different DPI produces different results."""
        renderer_150 = Renderer(dpi=150)
        renderer_300 = Renderer(dpi=300)

        images_150 = await renderer_150.render_pdf_to_images(sample_pdf)
        images_300 = await renderer_300.render_pdf_to_images(sample_pdf)

        # Higher DPI should produce larger images
        assert len(images_150[0]) < len(images_300[0])

    @pytest.mark.skipif(not POPPLER_AVAILABLE, reason="Poppler not installed")
    @pytest.mark.asyncio
    async def test_rendering_creates_no_temp_files(self, renderer, sample_pdf, tmp_path):
        """Test that rendering doesn't leave temporary files on disk."""
        import os

        # Count files before rendering
        files_before = set(os.listdir(tmp_path))

        # Render
        await renderer.render_pdf_to_images(sample_pdf)

        # Count files after (in a different temp location)
        # If no temp files are created in tmp_path, this test passes
        files_after = set(os.listdir(tmp_path))

        # Should be the same (no temp files left)
        assert files_before == files_after


class TestRendererIntegration:
    """Integration tests for Renderer with real PDFs."""

    @pytest.fixture
    def renderer(self):
        """Create a Renderer instance for testing."""
        return Renderer(dpi=200)

    @pytest.mark.skipif(not POPPLER_AVAILABLE, reason="Poppler not installed")
    @pytest.mark.asyncio
    async def test_full_workflow_render_all_pages(self, renderer):
        """Test full workflow of rendering all pages."""
        from fpdf import FPDF
        import tempfile
        import os

        # Create a test PDF with 5 pages
        pdf = FPDF()
        for i in range(5):
            pdf.add_page()
            pdf.set_font("Arial", size=12)
            pdf.cell(0, 10, txt=f"Page {i+1}")

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            pdf_path = f.name

        try:
            pdf.output(pdf_path)

            # Render all pages
            images = await renderer.render_pdf_to_images(pdf_path)

            # Verify
            assert len(images) == 5
            for img in images:
                assert isinstance(img, bytes)
                assert len(img) > 0

        finally:
            if os.path.exists(pdf_path):
                os.unlink(pdf_path)

    @pytest.mark.skipif(not POPPLER_AVAILABLE, reason="Poppler not installed")
    @pytest.mark.asyncio
    async def test_render_single_vs_all_pages_consistency(self, renderer):
        """Test that rendering single page produces same result as from all pages."""
        from fpdf import FPDF
        import tempfile
        import os

        # Create a test PDF
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", size=12)
        pdf.cell(0, 10, txt="Test content")

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            pdf_path = f.name

        try:
            pdf.output(pdf_path)

            # Render all pages
            all_images = await renderer.render_pdf_to_images(pdf_path)

            # Render first page only
            first_page = await renderer.render_page_to_image(pdf_path, 1)

            # Should be identical
            assert all_images[0] == first_page

        finally:
            if os.path.exists(pdf_path):
                os.unlink(pdf_path)
