"""
VLM-OCR Extractor - обёртка над VLM-OCR модулем.

Модуль предоставляет унифицированный API для извлечения данных из документов
с помощью существующего VLM-OCR модуля.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class DocumentData:
    """Результат извлечения полного документа.

    Attributes:
        text: Полный текст документа
        structure: Иерархия заголовков с уровнями
        tables: Список классифицированных таблиц

    Example structure:
        {
            "headers": [
                {"level": 1, "title": "1. Раздел", "page": 1},
                {"level": 2, "title": "1.1. Подраздел", "page": 2}
            ]
        }

    Example table:
        {
            "id": "table_1",
            "type": "NUMERIC" | "TEXT_MATRIX",
            "page": 3,
            "location": {"bbox": [...], "page": 3},
            "preview": "Краткое описание"
        }
    """

    text: str
    structure: Dict[str, Any]
    tables: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class VLMOCRResponse:
    """Ответ от VLM-OCR модуля.

    Attributes:
        success: Успешность выполнения запроса
        results: Список результатов для каждого prompt
    """

    success: bool
    results: List[VLMExtractionResult] = field(default_factory=list)


@dataclass
class VLMExtractionResult:
    """Результат извлечения для одного prompt.

    Attributes:
        prompt: Исходный prompt
        data: Извлеченные данные
    """

    prompt: str
    data: Dict[str, Any]


class VLMExtractionException(Exception):
    """Исключение при ошибке извлечения данных VLM-OCR."""

    def __init__(self, message: str, response: Optional[VLMOCRResponse] = None):
        """Инициализирует исключение с деталями ошибки.

        Args:
            message: Сообщение об ошибке
            response: Ответ от VLM-OCR с деталями
        """
        super().__init__(message)
        self.response = response


class VLMOCRExtractor:
    """Обёртка над VLM-OCR модулем для удобного API системы.

    Не реализует VLM-OCR, а предоставляет удобный интерфейс
    для остальной системы с batch prompts оптимизацией.
    """

    # Batch prompts для извлечения полного документа
    PROMPT_TEXT = "Верни весь текст с этих страниц"
    PROMPT_STRUCTURE = "Опиши иерархическую структуру: заголовки и их уровни"
    PROMPT_TABLES = "Найди все таблицы, классифицируй (NUMERIC/TEXT_MATRIX)"

    def __init__(
        self,
        vlm_ocr_module: Any,
        log_dir: Optional[Path] = None,
    ):
        """Инициализирует экстрактор с существующим VLM-OCR модулем.

        Args:
            vlm_ocr_module: Существующий PoC модуль с методом extract()
            log_dir: Директория для логов (по умолчанию 04_logs/vlm_ocr/)
        """
        self.vlm = vlm_ocr_module
        self.log_dir = log_dir or Path("04_logs/vlm_ocr")
        self.log_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Initialized VLMOCRExtractor with log_dir={self.log_dir}")

    def extract_full_document(self, images: List[bytes]) -> DocumentData:
        """Извлечь всё из документа за один вызов.

        Использует batch prompts для оптимизации:
        - "Верни весь текст с этих страниц"
        - "Опиши иерархическую структуру: заголовки и их уровни"
        - "Найди все таблицы, классифицируй (NUMERIC/TEXT_MATRIX)"

        Args:
            images: Список PNG-изображений страниц

        Returns:
            DocumentData с текстом, структурой и таблицами

        Raises:
            VLMExtractionException: При ошибке извлечения
        """
        prompts = [self.PROMPT_TEXT, self.PROMPT_STRUCTURE, self.PROMPT_TABLES]

        logger.info(f"Extracting document from {len(images)} images with {len(prompts)} prompts")

        # Вызываем VLM-OCR с batch prompts
        response = self._call_vlm_ocr(images, prompts)

        # Логируем запрос/ответ
        self._log_request(images, prompts, response)

        # Проверяем успешность
        if not response.success:
            logger.error(f"VLM-OCR extraction failed: {response}")
            raise VLMExtractionException("VLM-OCR extraction failed", response=response)

        # Агрегируем результаты с маппингом по prompt keywords
        text = self._extract_text(response)
        structure = self._extract_structure(response)
        tables = self._extract_tables(response)

        return DocumentData(text=text, structure=structure, tables=tables)

    def _call_vlm_ocr(self, images: List[bytes], prompts: List[str]) -> VLMOCRResponse:
        """Вызывает VLM-OCR модуль.

        Args:
            images: PNG-изображения страниц
            prompts: Extractive prompts

        Returns:
            VLMOCRResponse от модуля
        """
        try:
            # Предполагаемый API VLM-OCR модуля
            raw_response = self.vlm.extract(images=images, prompts=prompts)

            # Конвертируем в наш формат если нужно
            if isinstance(raw_response, VLMOCRResponse):
                return raw_response

            # Если VLM-OCR возвращает dict или другой формат - адаптируем
            return self._adapt_response(raw_response)

        except Exception as e:
            logger.exception(f"VLM-OCR call failed: {e}")
            # Возвращаем failed response
            return VLMOCRResponse(success=False, results=[])

    def _adapt_response(self, raw_response: Any) -> VLMOCRResponse:
        """Адаптирует ответ VLM-OCR в наш формат.

        Args:
            raw_response: Сырой ответ от VLM-OCR

        Returns:
            VLMOCRResponse
        """
        # Если это dict с нужными полями
        if isinstance(raw_response, dict):
            success = raw_response.get("success", False)
            results_data = raw_response.get("results", [])

            results = [
                VLMExtractionResult(
                    prompt=r.get("prompt", ""),
                    data=r.get("data", {}),
                )
                for r in results_data
            ]

            return VLMOCRResponse(success=success, results=results)

        # Если это уже наш формат
        if isinstance(raw_response, VLMOCRResponse):
            return raw_response

        logger.warning(f"Unknown response format: {type(raw_response)}")
        return VLMOCRResponse(success=False, results=[])

    def _find_result_by_prompt_keywords(self, response: VLMOCRResponse, keywords: str) -> Dict[str, Any]:
        """Находит результат по ключевым словам в prompt.

        Args:
            response: Ответ от VLM-OCR
            keywords: Ключевые слова для поиска (например "текст")

        Returns:
            data из найденного результата

        Raises:
            VLMExtractionException: Если результат не найден
        """
        keywords_lower = keywords.lower()

        for result in response.results:
            if keywords_lower in result.prompt.lower():
                return result.data

        raise VLMExtractionException(f"No result found for keywords: {keywords}")

    def _extract_text(self, response: VLMOCRResponse) -> str:
        """Извлекает текст из ответа VLM-OCR."""
        data = self._find_result_by_prompt_keywords(response, "текст")
        return data.get("text", "")

    def _extract_structure(self, response: VLMOCRResponse) -> Dict[str, Any]:
        """Извлекает структуру из ответа VLM-OCR."""
        data = self._find_result_by_prompt_keywords(response, "структур")
        return data.get("structure", {})

    def _extract_tables(self, response: VLMOCRResponse) -> List[Dict[str, Any]]:
        """Извлекает таблицы из ответа VLM-OCR."""
        data = self._find_result_by_prompt_keywords(response, "таблиц")
        return data.get("tables", [])

    def _log_request(
        self,
        images: List[bytes],
        prompts: List[str],
        response: VLMOCRResponse,
    ) -> None:
        """Логирует запрос/ответ в JSON формате.

        Args:
            images: PNG-изображения страниц (не логируем контент)
            prompts: Extractive prompts
            response: Ответ от VLM-OCR
        """
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "num_images": len(images),
            "prompts": prompts,
            "success": response.success,
            "num_results": len(response.results),
        }

        # Добавляем ошибку если есть
        if not response.success:
            log_entry["error"] = "VLM-OCR extraction failed"

        # Пишем в лог-файл
        log_file = self.log_dir / "requests.json"
        try:
            with open(log_file, "a", encoding="utf-8") as f:
                json.dump(log_entry, f, ensure_ascii=False)
                f.write("\n")
        except Exception as e:
            logger.error(f"Failed to write log: {e}")
