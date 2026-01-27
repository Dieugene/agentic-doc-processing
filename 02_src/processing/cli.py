"""
CLI interface для document processing.

Запуск:
    python -m processing.cli path/to/document.docx
    python -m processing.cli path/to/report.xlsx --output-dir custom/path
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from document import NodeType
from processing.processor import DocumentProcessor
from processing.mock_vlm_ocr import MockVLMOCR  # TODO: заменить на реальный модуль


def print_tree(node, indent: int = 0, skeleton=None):
    """Вывести узел и его детей в виде дерева.

    Args:
        node: Узел DocumentSkeleton
        indent: Уровень вложенности для отступа
        skeleton: DocumentSkeleton для доступа к дочерним узлам
    """
    prefix = "  " * indent
    connector = "└── " if indent > 0 else ""

    node_type = node.type.value if hasattr(node.type, "value") else str(node.type)
    page_range = f"(стр. {node.page_range.start}-{node.page_range.end})"

    print(f"{prefix}{connector}{node.id}: [{node_type}] {node.title} {page_range}")

    for child_id in node.children_ids:
        child = skeleton._nodes.get(child_id)
        if child:
            print_tree(child, indent + 1, skeleton)


async def main():
    """Главная функция CLI."""
    parser = argparse.ArgumentParser(
        description="Обработать документ и создать DocumentSkeleton"
    )
    parser.add_argument("file_path", help="Путь к документу (DOCX/XLSX/PDF)")
    parser.add_argument(
        "--output-dir",
        default="03_data",
        help="Директория для сохранения skeleton'ов (default: 03_data)",
    )
    parser.add_argument(
        "--dpi", type=int, default=200, help="DPI для рендеринга PDF (default: 200)"
    )

    args = parser.parse_args()

    # Проверка файла
    file_path = Path(args.file_path)
    if not file_path.exists():
        print(f"❌ Файл не найден: {args.file_path}")
        sys.exit(1)

    print(f"📄 Загрузка файла: {file_path.name}")

    # Callback для прогресса
    async def progress_callback(step_name: str, duration_sec: float, details: str = ""):
        """Выводит прогресс каждого этапа."""
        emoji_map = {
            "Detect file type": "🔍",
            "Convert to PDF": "📄",
            "Render PDF to PNG": "🖼️",
            "VLM-OCR extraction": "🤖",
            "Build DocumentSkeleton": "🦴",
            "Save to FileStorage": "💾",
        }
        emoji = emoji_map.get(step_name, "✅")
        print(f"{emoji} {step_name}: {details} ({duration_sec:.2f}s)")

    # Создаем процессор с MockVLMOCR
    # TODO: В задаче 014 заменить на реальный VLM-OCR модуль
    processor = DocumentProcessor(
        vlm_ocr_module=MockVLMOCR(),
        storage_base_path=args.output_dir,
        renderer_dpi=args.dpi,
        progress_callback=progress_callback,
    )

    try:
        # Обрабатываем документ
        document_id = await processor.process_document(str(file_path))

        print(f"\n✅ Обработка завершена успешно")
        print(f"💾 Сохранено: {args.output_dir}/{document_id}/skeleton.json")
        print()

        # Загружаем skeleton для отображения
        skeleton = await processor.storage.load_skeleton(document_id)
        root = await skeleton.get_root()

        print("🌳 Структура документа:")
        print_tree(root, skeleton=skeleton)

    except FileNotFoundError as e:
        print(f"❌ Файл не найден: {e}")
        sys.exit(1)
    except ValueError as e:
        # Неподдерживаемый формат или другая валидационная ошибка
        error_msg = str(e).lower()
        if "unsupported" in error_msg or "format" in error_msg or "file type" in error_msg:
            print(f"❌ Неподдерживаемый формат файла: {file_path.suffix}")
            print(f"Поддерживаемые форматы: DOCX, XLSX, PDF")
        else:
            print(f"❌ Ошибка валидации: {e}")
        sys.exit(1)
    except ImportError as e:
        # Ошибка импорта (например, Poppler не установлен)
        error_msg = str(e).lower()
        if "poppler" in error_msg or "pdf2image" in error_msg:
            print(
                "❌ Poppler не установлен. Установите с https://github.com/oschwartz10612/poppler-windows/releases/"
            )
        else:
            print(f"❌ Ошибка импорта: {e}")
            import traceback

            traceback.print_exc()
        sys.exit(1)
    except Exception as e:
        print(f"❌ Ошибка обработки: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
