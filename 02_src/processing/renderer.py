"""
Renderer module - PDF to PNG conversion for VLM-OCR.

Provides page-by-page rendering of PDF documents to PNG images
with configurable DPI for optimal VLM-OCR processing.
"""
from __future__ import annotations

import asyncio
import io
import logging
import os
from pathlib import Path
from typing import List, Optional

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None

try:
    from PIL import Image
except ImportError:
    Image = None


logger = logging.getLogger(__name__)


class RenderingError(Exception):
    """Raised when PDF rendering fails."""

    def __init__(self, pdf_path: str, details: str):
        """Initialize rendering error with context.

        Args:
            pdf_path: Path to the PDF that failed to render
            details: Detailed error message
        """
        self.pdf_path = pdf_path
        self.details = details
        super().__init__(f"Failed to render {pdf_path}: {details}")


class Renderer:
    """PDF to PNG renderer for VLM-OCR processing.

    Converts PDF documents into PNG images page by page.
    Uses PyMuPDF (fitz) - pure Python library without external dependencies.
    """

    def __init__(self, dpi: int = 200, log_dir: Optional[str] = None):
        """Initialize the Renderer.

        Args:
            dpi: Resolution in dots per inch (200-300 recommended for VLM-OCR)
            log_dir: Optional directory for rendering logs
        """
        if dpi < 150:
            logger.warning(f"DPI {dpi} is below 150, text may be unreadable for VLM")
        if dpi > 300:
            logger.warning(f"DPI {dpi} is above 300, file sizes may be very large")

        self.dpi = dpi
        self._setup_logging(log_dir)
        self._check_dependencies()
        logger.info(f"Initialized Renderer with dpi={dpi}")

    def _setup_logging(self, log_dir: Optional[str]) -> None:
        """Setup logging for rendering operations.

        Args:
            log_dir: Optional directory for rendering logs
        """
        if log_dir:
            log_path = Path(log_dir) / "rendering.log"
            log_path.parent.mkdir(parents=True, exist_ok=True)

            handler = logging.FileHandler(log_path)
            handler.setFormatter(
                logging.Formatter(
                    "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
                )
            )
            logger.addHandler(handler)

    def _check_dependencies(self) -> None:
        """Check if required dependencies are installed.

        Raises:
            ImportError: If PyMuPDF or Pillow are not installed
        """
        if fitz is None:
            raise ImportError(
                "PyMuPDF is required. Install with: pip install pymupdf"
            )
        if Image is None:
            raise ImportError(
                "Pillow is required. Install with: pip install Pillow"
            )

    async def render_pdf_to_images(self, pdf_path: str) -> List[bytes]:
        """Render PDF to list of PNG images.

        Args:
            pdf_path: Path to the PDF file

        Returns:
            List of PNG images as bytes, one per page

        Raises:
            FileNotFoundError: If PDF file doesn't exist
            RenderingError: If rendering fails
        """
        # Check if file exists
        if not os.path.exists(pdf_path):
            raise FileNotFoundError(f"PDF file not found: {pdf_path}")

        logger.info(f"Starting render: {pdf_path} (dpi={self.dpi})")

        try:
            # Run blocking fitz operations in thread pool
            png_images = await asyncio.to_thread(self._render_all_pages, pdf_path)

            logger.info(f"Rendering successful: {len(png_images)} pages")
            return png_images

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Rendering failed: {error_msg}")
            raise RenderingError(pdf_path, error_msg) from e

    def _render_all_pages(self, pdf_path: str) -> List[bytes]:
        """Render all pages from PDF to PNG bytes (blocking operation).

        Args:
            pdf_path: Path to the PDF file

        Returns:
            List of PNG images as bytes
        """
        doc = fitz.open(pdf_path)
        try:
            png_images = []
            for page_num in range(len(doc)):
                page = doc.load_page(page_num)
                pix = page.get_pixmap(dpi=self.dpi)

                # Convert pixmap to PIL Image
                mode = "RGB" if pix.alpha == 0 else "RGBA"
                img = Image.frombytes(mode, [pix.width, pix.height], pix.samples)
                if mode == "RGBA":
                    img = img.convert("RGB")

                # Convert to PNG bytes
                buffer = io.BytesIO()
                img.save(buffer, format="PNG")
                png_bytes = buffer.getvalue()
                png_images.append(png_bytes)
                logger.debug(f"Converted page {page_num+1}/{len(doc)} to PNG")

            return png_images
        finally:
            doc.close()

    async def render_page_to_image(
        self,
        pdf_path: str,
        page_number: int
    ) -> bytes:
        """Render a single page from PDF to PNG.

        Args:
            pdf_path: Path to the PDF file
            page_number: Page number (1-indexed)

        Returns:
            PNG image as bytes

        Raises:
            FileNotFoundError: If PDF file doesn't exist
            RenderingError: If page number is invalid or rendering fails
        """
        # Validate page number
        if page_number < 1:
            raise RenderingError(
                pdf_path,
                f"Invalid page number: {page_number} (must be >= 1, 1-indexed)"
            )

        # Check if file exists
        if not os.path.exists(pdf_path):
            raise FileNotFoundError(f"PDF file not found: {pdf_path}")

        logger.info(
            f"Rendering page {page_number} from {pdf_path} (dpi={self.dpi})"
        )

        try:
            # Run blocking fitz operations in thread pool
            png_bytes = await asyncio.to_thread(
                self._render_single_page, pdf_path, page_number
            )

            logger.info(f"Page {page_number} rendered successfully")
            return png_bytes

        except RenderingError:
            # Re-raise our own exceptions
            raise
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Page rendering failed: {error_msg}")
            raise RenderingError(pdf_path, error_msg) from e

    def _render_single_page(self, pdf_path: str, page_number: int) -> bytes:
        """Render a single page from PDF to PNG bytes (blocking operation).

        Args:
            pdf_path: Path to the PDF file
            page_number: Page number (1-indexed)

        Returns:
            PNG image as bytes

        Raises:
            RenderingError: If page doesn't exist
        """
        doc = fitz.open(pdf_path)
        try:
            # Convert to 0-indexed
            page_idx = page_number - 1

            # Check if page exists
            if page_idx >= len(doc):
                raise RenderingError(
                    pdf_path,
                    f"Page {page_number} does not exist in PDF (total pages: {len(doc)})"
                )

            page = doc.load_page(page_idx)
            pix = page.get_pixmap(dpi=self.dpi)

            # Convert pixmap to PIL Image
            mode = "RGB" if pix.alpha == 0 else "RGBA"
            img = Image.frombytes(mode, [pix.width, pix.height], pix.samples)
            if mode == "RGBA":
                img = img.convert("RGB")

            # Convert to PNG bytes
            buffer = io.BytesIO()
            img.save(buffer, format="PNG")
            return buffer.getvalue()
        finally:
            doc.close()
