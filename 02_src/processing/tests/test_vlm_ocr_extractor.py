"""
Unit тесты для VLMOCRExtractor.

Тестируют обёртку над VLM-OCR модулем с использованием MockVLMOCR.
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path
from typing import Any, Dict, List

from processing.mock_vlm_ocr import MockVLMOCR, MockVLMOCRWithError
from processing.vlm_ocr_extractor import (
    DocumentData,
    VLMExtractionException,
    VLMOCRExtractor,
    VLMOCRResponse,
    VLMExtractionResult,
)


class TestVLMOCRExtractor(unittest.TestCase):
    """Тесты для VLMOCRExtractor."""

    def setUp(self):
        """Подготовка тестового окружения."""
        self.mock_vlm = MockVLMOCR()
        self.log_dir = Path("04_logs/vlm_ocr_test")
        self.extractor = VLMOCRExtractor(
            vlm_ocr_module=self.mock_vlm,
            log_dir=self.log_dir,
        )

    def tearDown(self):
        """Очистка после тестов."""
        # Удаляем тестовый лог-файл если есть
        log_file = self.log_dir / "requests.json"
        if log_file.exists():
            log_file.unlink()

    def test_extract_full_document_success(self):
        """Тест успешного извлечения полного документа."""
        # Создаем mock изображения (пустые байты)
        images = [b"fake_png_1", b"fake_png_2", b"fake_png_3"]

        # Извлекаем данные
        result = self.extractor.extract_full_document(images)

        # Проверяем результат
        self.assertIsInstance(result, DocumentData)
        self.assertIn("Mock document text", result.text)
        self.assertIn("3 pages", result.text)

        # Проверяем структуру
        self.assertIn("headers", result.structure)
        headers = result.structure["headers"]
        self.assertEqual(len(headers), 3)
        self.assertEqual(headers[0]["level"], 1)
        self.assertEqual(headers[0]["title"], "1. Раздел")

        # Проверяем таблицы
        self.assertEqual(len(result.tables), 2)
        self.assertEqual(result.tables[0]["type"], "NUMERIC")
        self.assertEqual(result.tables[1]["type"], "TEXT_MATRIX")

    def test_extract_full_document_with_batch_prompts(self):
        """Тест что batch prompts используются за один вызов."""
        images = [b"fake_png"]

        # Mock должен быть вызван 1 раз (batch prompts)
        initial_call_count = self.mock_vlm.call_count

        self.extractor.extract_full_document(images)

        # Проверяем что был только 1 вызов VLM-OCR
        self.assertEqual(self.mock_vlm.call_count, initial_call_count + 1)

    def test_extract_mapping_by_prompt_keywords(self):
        """Тест маппинга результатов по ключевым словам в prompt."""
        images = [b"fake_png"]

        result = self.extractor.extract_full_document(images)

        # Проверяем что данные корректно извлечены из разных results
        # (маппинг по "текст", "структур", "таблиц")
        self.assertIsNotNone(result.text)
        self.assertIsNotNone(result.structure)
        self.assertIsNotNone(result.tables)

    def test_extract_error_handling(self):
        """Тест обработки ошибок VLM-OCR."""
        # Создаем extractor с mock который всегда возвращает ошибку
        error_mock = MockVLMOCRWithError()
        error_extractor = VLMOCRExtractor(
            vlm_ocr_module=error_mock,
            log_dir=self.log_dir,
        )

        images = [b"fake_png"]

        # Должен быть выброшен exception
        with self.assertRaises(VLMExtractionException) as context:
            error_extractor.extract_full_document(images)

        # Проверяем details exception
        exception = context.exception
        self.assertIsNotNone(exception.response)
        self.assertFalse(exception.response.success)

    def test_logging(self):
        """Тест что запросы логируются в JSON формате."""
        images = [b"fake_png_1", b"fake_png_2"]

        # Извлекаем данные
        self.extractor.extract_full_document(images)

        # Проверяем лог-файл
        log_file = self.log_dir / "requests.json"
        self.assertTrue(log_file.exists())

        # Читаем и парсим лог
        with open(log_file, "r", encoding="utf-8") as f:
            log_entry = json.loads(f.readline())

        # Проверяем поля лога
        self.assertIn("timestamp", log_entry)
        self.assertEqual(log_entry["num_images"], 2)
        self.assertEqual(len(log_entry["prompts"]), 3)  # batch prompts
        self.assertTrue(log_entry["success"])
        self.assertEqual(log_entry["num_results"], 3)

    def test_logging_on_error(self):
        """Тест что ошибки логируются корректно."""
        error_mock = MockVLMOCRWithError()
        error_extractor = VLMOCRExtractor(
            vlm_ocr_module=error_mock,
            log_dir=self.log_dir,
        )

        images = [b"fake_png"]

        # Пытаемся извлечь (должно упасть)
        try:
            error_extractor.extract_full_document(images)
        except VLMExtractionException:
            pass

        # Проверяем лог-файл
        log_file = self.log_dir / "requests.json"
        self.assertTrue(log_file.exists())

        # Читаем лог
        with open(log_file, "r", encoding="utf-8") as f:
            log_entry = json.loads(f.readline())

        # Проверяем что success=False и есть error
        self.assertFalse(log_entry["success"])
        self.assertIn("error", log_entry)

    def test_empty_images_list(self):
        """Тест с пустым списком изображений."""
        images = []

        # Должен работать (но вернет пустые данные)
        result = self.extractor.extract_full_document(images)

        self.assertIsInstance(result, DocumentData)
        # Mock должен вернуть данные даже для 0 изображений

    def test_documentdata_defaults(self):
        """Тест значений по умолчанию для DocumentData."""
        data = DocumentData(
            text="test",
            structure={},
        )

        # tables должен быть пустым списком по умолчанию
        self.assertEqual(data.tables, [])


class TestVLMOCRResponseStructures(unittest.TestCase):
    """Тесты для структур данных VLM-OCR."""

    def test_vlm_ocr_response_success(self):
        """Тест VLMOCRResponse с успешным результатом."""
        result = VLMExtractionResult(
            prompt="test prompt",
            data={"key": "value"}
        )

        response = VLMOCRResponse(
            success=True,
            results=[result]
        )

        self.assertTrue(response.success)
        self.assertEqual(len(response.results), 1)
        self.assertEqual(response.results[0].prompt, "test prompt")

    def test_vlm_ocr_response_failure(self):
        """Тест VLMOCRResponse с ошибкой."""
        response = VLMOCRResponse(success=False)

        self.assertFalse(response.success)
        self.assertEqual(len(response.results), 0)


class TestMockVLMOCR(unittest.TestCase):
    """Тесты для MockVLMOCR."""

    def test_mock_is_deterministic(self):
        """Тест что mock возвращает детерминированные результаты."""
        mock = MockVLMOCR()

        images = [b"test1", b"test2"]
        prompts = ["prompt1", "prompt2", "prompt3"]

        # Два вызова с одинаковыми параметрами
        response1 = mock.extract(images, prompts)
        response2 = mock.extract(images, prompts)

        # Результаты должны быть одинаковыми
        self.assertEqual(response1.success, response2.success)
        self.assertEqual(len(response1.results), len(response2.results))

    def test_mock_call_count(self):
        """Тест подсчета вызовов."""
        mock = MockVLMOCR()

        self.assertEqual(mock.call_count, 0)

        mock.extract([], [])
        self.assertEqual(mock.call_count, 1)

        mock.extract([], [])
        self.assertEqual(mock.call_count, 2)

    def test_mock_with_fixture_file(self):
        """Тест загрузки fixture'ов из файла."""
        # Используем существующий fixture file
        fixture_file = Path("02_src/processing/tests/fixtures/vlm_response_samples.json")

        if fixture_file.exists():
            # Создаем mock с fixture file
            mock = MockVLMOCR(fixture_path=fixture_file)

            response = mock.extract([], [])

            self.assertTrue(response.success)
            self.assertIn("text", response.results[0].data)


if __name__ == "__main__":
    unittest.main()
