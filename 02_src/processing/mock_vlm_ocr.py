"""
Mock VLM-OCR module для тестирования.

Предоставляет детерминированные ответы для тестирования VLMOCRExtractor.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from processing.vlm_ocr_extractor import VLMExtractionResult, VLMOCRResponse


class MockVLMOCR:
    """Mock для тестирования VLM-OCR.

    Возвращает предопределённые ответы из fixtures.
    Детерминированный: одинаковый вход → одинаковый выход.
    """

    def __init__(self, fixture_path: Path | None = None):
        """Инициализирует mock с fixture'ами.

        Args:
            fixture_path: Путь к JSON файлу с fixture'ами.
                         Если None, использует встроенные fixture'ы.
        """
        self.fixture_path = fixture_path
        self._call_count = 0

    def extract(self, images: List[bytes], prompts: List[str]) -> VLMOCRResponse:
        """Извлекает данные из изображений (mock).

        Args:
            images: PNG-изображения страниц
            prompts: Extractive prompts

        Returns:
            VLMOCRResponse с предопределёнными данными
        """
        self._call_count += 1

        # Если есть fixture file - загружаем из него
        if self.fixture_path and self.fixture_path.exists():
            return self._load_fixture_response()

        # Иначе используем встроенные mock данные
        return self._get_builtin_response(images, prompts)

    def _get_builtin_response(self, images: List[bytes], prompts: List[str]) -> VLMOCRResponse:
        """Возвращает встроенный mock ответ.

        Args:
            images: PNG-изображения (игнорируем, только для детерминизма)
            prompts: Extractive prompts

        Returns:
            VLMOCRResponse с mock данными
        """
        # Детерминизм: ответ зависит от количества изображений и промптов
        num_images = len(images)
        num_prompts = len(prompts)

        # Mock данные для текста
        text_result = VLMExtractionResult(
            prompt=prompts[0] if num_prompts > 0 else "",
            data={
                "text": f"Mock document text from {num_images} pages. "
                        f"Это пример текста документа для тестирования."
            }
        )

        # Mock данные для структуры
        structure_result = VLMExtractionResult(
            prompt=prompts[1] if num_prompts > 1 else "",
            data={
                "structure": {
                    "headers": [
                        {"level": 1, "title": "1. Раздел", "page": 1},
                        {"level": 2, "title": "1.1. Подраздел", "page": 2},
                        {"level": 2, "title": "1.2. Еще подраздел", "page": 3},
                    ]
                }
            }
        )

        # Mock данные для таблиц
        tables_result = VLMExtractionResult(
            prompt=prompts[2] if num_prompts > 2 else "",
            data={
                "tables": [
                    {
                        "id": "table_1",
                        "type": "NUMERIC",
                        "page": 2,
                        "location": {"bbox": [100, 200, 400, 300], "page": 2},
                        "preview": "Финансовые показатели за 2024 год"
                    },
                    {
                        "id": "table_2",
                        "type": "TEXT_MATRIX",
                        "page": 3,
                        "location": {"bbox": [100, 100, 400, 250], "page": 3},
                        "preview": "Сравнительная таблица характеристик"
                    }
                ]
            }
        )

        return VLMOCRResponse(
            success=True,
            results=[text_result, structure_result, tables_result]
        )

    def _load_fixture_response(self) -> VLMOCRResponse:
        """Загружает ответ из fixture JSON файла.

        Returns:
            VLMOCRResponse из fixture
        """
        try:
            with open(self.fixture_path, "r", encoding="utf-8") as f:
                fixture_data = json.load(f)

            success_response = fixture_data.get("success_response", {})

            return VLMOCRResponse(
                success=success_response.get("success", True),
                results=[
                    VLMExtractionResult(
                        prompt=r.get("prompt", ""),
                        data=r.get("data", {})
                    )
                    for r in success_response.get("results", [])
                ]
            )
        except Exception as e:
            # При ошибке загрузки возвращаем встроенный ответ
            print(f"Warning: Failed to load fixture: {e}")
            return self._get_builtin_response([], [])

    def simulate_error(self, images: List[bytes], prompts: List[str]) -> VLMOCRResponse:
        """Симулирует ошибку VLM-OCR для тестирования обработки ошибок.

        Args:
            images: PNG-изображения
            prompts: Extractive prompts

        Returns:
            VLMOCRResponse с success=False
        """
        return VLMOCRResponse(
            success=False,
            results=[]
        )

    @property
    def call_count(self) -> int:
        """Количество вызовов метода extract."""
        return self._call_count


class MockVLMOCRWithError:
    """Mock VLM-OCR который всегда возвращает ошибку.

    Для тестирования обработки ошибок в VLMOCRExtractor.
    """

    def extract(self, images: List[bytes], prompts: List[str]) -> VLMOCRResponse:
        """Извлекает данные (всегда возвращает ошибку).

        Args:
            images: PNG-изображения страниц
            prompts: Extractive prompts

        Returns:
            VLMOCRResponse с success=False
        """
        return VLMOCRResponse(success=False, results=[])
