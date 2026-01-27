"""
Document Processor - оркестратор pipeline для продакшен использования.

Обрабатывает документы через полный pipeline:
Converter → Renderer → VLM-OCR → SkeletonBuilder → FileStorage
"""
from __future__ import annotations

import logging
import time
import uuid
from pathlib import Path
from typing import Awaitable, Callable, Optional

from document import DocumentSkeleton
from processing.converter import Converter, FileType
from processing.renderer import Renderer
from processing.skeleton_builder import SkeletonBuilder
from processing.vlm_ocr_extractor import DocumentData, VLMOCRExtractor
from storage.file_storage import FileStorage

logger = logging.getLogger(__name__)

# Тип для callback функции прогресса
ProgressCallback = Callable[[str, float, str], Awaitable[None]]


class DocumentProcessor:
    """Оркестратор полного pipeline обработки документов."""

    def __init__(
        self,
        vlm_ocr_module,
        storage_base_path: str = "03_data",
        renderer_dpi: int = 200,
        progress_callback: Optional[ProgressCallback] = None,
    ):
        """Инициализирует процессор со всеми компонентами pipeline.

        Args:
            vlm_ocr_module: VLM-OCR модуль (может быть MockVLMOCR или реальный)
            storage_base_path: Базовый путь для FileStorage
            renderer_dpi: DPI для рендеринга PDF→PNG
            progress_callback: Опциональный callback для прогресса (step, duration, details)
        """
        self.converter = Converter()
        self.renderer = Renderer(dpi=renderer_dpi)
        self.vlm_extractor = VLMOCRExtractor(vlm_ocr_module=vlm_ocr_module)
        self.skeleton_builder = SkeletonBuilder()
        self.storage = FileStorage(base_path=storage_base_path)
        self.progress_callback = progress_callback

        logger.info(
            f"DocumentProcessor initialized: storage={storage_base_path}, dpi={renderer_dpi}"
        )

    async def process_document(self, file_path: str) -> str:
        """Обработать документ через полный pipeline.

        Pipeline:
        1. Detect file type
        2. Convert to PDF (если нужно)
        3. Render to PNG images
        4. Extract data via VLM-OCR
        5. Build DocumentSkeleton
        6. Save to FileStorage

        Args:
            file_path: Путь к исходному документу

        Returns:
            document_id обработанного документа

        Raises:
            FileNotFoundError: Если файл не существует
            Exception: Если любой этап pipeline падает
        """
        # 1. Detect file type
        start_time = time.time()
        file_type = await self.converter.detect_file_type(file_path)
        await self._report_progress(
            "Detect file type", time.time() - start_time, f"Detected: {file_type.value}"
        )

        # 2. Convert to PDF if needed
        start_time = time.time()
        if file_type != FileType.PDF:
            pdf_path = await self.converter.convert_to_pdf(file_path, file_type)
            await self._report_progress(
                "Convert to PDF",
                time.time() - start_time,
                f"{file_type.value.upper()} → PDF",
            )
        else:
            pdf_path = file_path
            await self._report_progress(
                "Convert to PDF", time.time() - start_time, "Already PDF"
            )

        # 3. Render PDF to PNG
        start_time = time.time()
        images = await self.renderer.render_pdf_to_images(pdf_path)
        await self._report_progress(
            "Render PDF to PNG", time.time() - start_time, f"{len(images)} images"
        )

        # 4. Extract data via VLM-OCR
        start_time = time.time()
        document_data = self.vlm_extractor.extract_full_document(images)
        await self._report_progress(
            "VLM-OCR extraction", time.time() - start_time, "Document data extracted"
        )

        # 5. Build DocumentSkeleton
        start_time = time.time()
        document_id = f"doc_{uuid.uuid4().hex[:16]}"
        skeleton = await self.skeleton_builder.build_skeleton(
            document_data=document_data,
            document_id=document_id,
        )
        await self._report_progress(
            "Build DocumentSkeleton", time.time() - start_time, f"{len(skeleton._nodes)} nodes"
        )

        # 6. Save to FileStorage
        start_time = time.time()
        await self.storage.save_skeleton(skeleton.document_id, skeleton)
        await self._report_progress(
            "Save to FileStorage", time.time() - start_time, f"Saved as {document_id}"
        )

        logger.info(f"Document processed successfully: {document_id}")
        return document_id

    async def _report_progress(self, step_name: str, duration_sec: float, details: str = ""):
        """Сообщает о прогрессе через callback если предоставлен.

        Args:
            step_name: Название этапа
            duration_sec: Время выполнения в секундах
            details: Дополнительные детали
        """
        if self.progress_callback:
            await self.progress_callback(step_name, duration_sec, details)
        else:
            logger.debug(f"Progress: {step_name} ({duration_sec:.2f}s) - {details}")
