"""
Unit tests for Converter module.

Run with: pytest -v
"""
from pathlib import Path
import tempfile
import os

import pytest

from processing.converter import Converter, ConversionError, FileType


# Skip tests if dependencies are not installed
pytest.importorskip("fpdf")
pytest.importorskip("docx")
pytest.importorskip("openpyxl")


class TestFileType:
    """Tests for FileType enum and detection."""

    def test_file_type_values(self):
        """Test FileType enum has correct values."""
        assert FileType.PDF == "pdf"
        assert FileType.DOCX == "docx"
        assert FileType.XLSX == "xlsx"
        assert FileType.TXT == "txt"
        assert FileType.UNKNOWN == "unknown"

    @pytest.mark.asyncio
    async def test_detect_pdf(self):
        """Test PDF file type detection."""
        converter = Converter()
        assert await converter.detect_file_type("test.pdf") == FileType.PDF
        assert await converter.detect_file_type("test.PDF") == FileType.PDF

    @pytest.mark.asyncio
    async def test_detect_docx(self):
        """Test DOCX file type detection."""
        converter = Converter()
        assert await converter.detect_file_type("test.docx") == FileType.DOCX
        assert await converter.detect_file_type("test.DOCX") == FileType.DOCX

    @pytest.mark.asyncio
    async def test_detect_xlsx(self):
        """Test XLSX file type detection."""
        converter = Converter()
        assert await converter.detect_file_type("test.xlsx") == FileType.XLSX
        assert await converter.detect_file_type("test.XLSX") == FileType.XLSX

    @pytest.mark.asyncio
    async def test_detect_txt(self):
        """Test TXT file type detection."""
        converter = Converter()
        assert await converter.detect_file_type("test.txt") == FileType.TXT
        assert await converter.detect_file_type("test.TXT") == FileType.TXT

    @pytest.mark.asyncio
    async def test_detect_unknown(self):
        """Test unknown file type detection."""
        converter = Converter()
        assert await converter.detect_file_type("test.unknown") == FileType.UNKNOWN
        assert await converter.detect_file_type("test.jpg") == FileType.UNKNOWN


class TestConverter:
    """Tests for Converter class."""

    @pytest.fixture
    def converter(self):
        """Create a Converter instance for testing."""
        return Converter()

    @pytest.fixture
    def fixtures_dir(self):
        """Get the path to fixtures directory."""
        return Path(__file__).parent / "fixtures"

    @pytest.fixture
    def sample_txt(self, fixtures_dir):
        """Get path to sample.txt fixture."""
        path = fixtures_dir / "sample.txt"
        if not path.exists():
            pytest.skip(f"Fixture not found: {path}")
        return str(path)

    @pytest.fixture
    def sample_docx(self, fixtures_dir):
        """Get path to sample.docx fixture."""
        path = fixtures_dir / "sample.docx"
        if not path.exists():
            pytest.skip(f"Fixture not found: {path}")
        return str(path)

    @pytest.fixture
    def sample_xlsx(self, fixtures_dir):
        """Get path to sample.xlsx fixture."""
        path = fixtures_dir / "sample.xlsx"
        if not path.exists():
            pytest.skip(f"Fixture not found: {path}")
        return str(path)

    @pytest.mark.asyncio
    async def test_convert_nonexistent_file(self, converter):
        """Test conversion of nonexistent file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            await converter.convert_to_pdf("/nonexistent/file.txt")

    @pytest.mark.asyncio
    async def test_convert_unsupported_format(self, converter, sample_txt):
        """Test unsupported format raises ValueError."""
        # Create a temporary file with unsupported extension
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
            f.write(b"test content")
            temp_path = f.name

        try:
            with pytest.raises(ValueError, match="Unsupported file format"):
                await converter.convert_to_pdf(temp_path)
        finally:
            os.unlink(temp_path)

    @pytest.mark.asyncio
    async def test_convert_txt_to_pdf(self, converter, sample_txt):
        """Test TXT to PDF conversion."""
        pdf_path = await converter.convert_to_pdf(sample_txt)

        try:
            # Verify PDF file was created
            assert os.path.exists(pdf_path)
            assert pdf_path.endswith(".pdf")

            # Verify file has content
            assert os.path.getsize(pdf_path) > 0

            # Verify it's a PDF (starts with %PDF)
            with open(pdf_path, "rb") as f:
                header = f.read(4)
                assert header == b"%PDF"
        finally:
            # Clean up
            if os.path.exists(pdf_path):
                os.unlink(pdf_path)

    @pytest.mark.asyncio
    async def test_convert_txt_auto_detect(self, converter, sample_txt):
        """Test TXT to PDF conversion with auto-detection."""
        pdf_path = await converter.convert_to_pdf(sample_txt, file_type=None)

        try:
            assert os.path.exists(pdf_path)
            assert pdf_path.endswith(".pdf")
        finally:
            if os.path.exists(pdf_path):
                os.unlink(pdf_path)

    @pytest.mark.asyncio
    async def test_convert_docx_to_pdf(self, converter, sample_docx):
        """Test DOCX to PDF conversion."""
        pdf_path = await converter.convert_to_pdf(sample_docx)

        try:
            assert os.path.exists(pdf_path)
            assert pdf_path.endswith(".pdf")
            assert os.path.getsize(pdf_path) > 0

            # Verify PDF header
            with open(pdf_path, "rb") as f:
                header = f.read(4)
                assert header == b"%PDF"
        finally:
            if os.path.exists(pdf_path):
                os.unlink(pdf_path)

    @pytest.mark.asyncio
    async def test_convert_xlsx_to_pdf(self, converter, sample_xlsx):
        """Test XLSX to PDF conversion."""
        pdf_path = await converter.convert_to_pdf(sample_xlsx)

        try:
            assert os.path.exists(pdf_path)
            assert pdf_path.endswith(".pdf")
            assert os.path.getsize(pdf_path) > 0

            # Verify PDF header
            with open(pdf_path, "rb") as f:
                header = f.read(4)
                assert header == b"%PDF"
        finally:
            if os.path.exists(pdf_path):
                os.unlink(pdf_path)

    @pytest.mark.asyncio
    async def test_convert_pdf_returns_as_is(self, converter, sample_txt):
        """Test that PDF files are returned without conversion."""
        # First convert a file to get a PDF
        temp_pdf = await converter.convert_to_pdf(sample_txt)

        try:
            # Converting the PDF should return the same path
            result = await converter.convert_to_pdf(temp_pdf)
            assert result == temp_pdf
        finally:
            if os.path.exists(temp_pdf):
                os.unlink(temp_pdf)


class TestConversionError:
    """Tests for ConversionError exception."""

    def test_conversion_error_creation(self):
        """Test ConversionError can be created with details."""
        error = ConversionError("docx", "File is corrupted")
        assert error.file_type == "docx"
        assert error.details == "File is corrupted"
        assert "docx" in str(error)
        assert "File is corrupted" in str(error)


class TestEncodingDetection:
    """Tests for text encoding detection."""

    @pytest.fixture
    def converter(self):
        """Create a Converter instance for testing."""
        return Converter()

    def test_read_utf8_file(self, converter, tmp_path):
        """Test reading UTF-8 encoded text file."""
        # Create UTF-8 file with cyrillic
        test_file = tmp_path / "utf8_test.txt"
        test_file.write_text("Тест кириллицы", encoding="utf-8")

        content = converter._read_text_file(str(test_file))
        assert "Тест кириллицы" in content

    def test_read_cp1251_file(self, converter, tmp_path):
        """Test reading CP1251 encoded text file."""
        # Create CP1251 file with cyrillic
        test_file = tmp_path / "cp1251_test.txt"
        test_file.write_text("Тест кириллицы", encoding="cp1251")

        content = converter._read_text_file(str(test_file))
        assert "Тест кириллицы" in content or "Тест" in content
