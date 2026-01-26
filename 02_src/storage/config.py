"""
Configuration for storage module.

Loads environment variables for storage paths.
Provides optional logging setup for standalone usage.
"""
import logging
import os
from pathlib import Path
from typing import Dict, Optional

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    # python-dotenv not installed, use system env only
    pass


def get_storage_config() -> Dict[str, str]:
    """
    Get storage configuration from environment variables.

    Returns:
        Dict with keys:
        - base_path: Base directory for document storage (default: "data/")
        - cache_path: Cache directory for VLM-OCR results (default: "data/cache/vlm_ocr/")

    Examples:
        >>> config = get_storage_config()
        >>> base = config["base_path"]
    """
    base_path = os.getenv("STORAGE_BASE_PATH", "data/")
    cache_path = os.getenv("STORAGE_CACHE_PATH", "data/cache/vlm_ocr/")

    return {
        "base_path": base_path,
        "cache_path": cache_path,
    }


def ensure_directories():
    """
    Ensure storage directories exist.

    Creates base_path and cache_path directories if they don't exist.
    """
    config = get_storage_config()
    base = Path(config["base_path"])
    cache = Path(config["cache_path"])

    base.mkdir(parents=True, exist_ok=True)
    cache.mkdir(parents=True, exist_ok=True)


def setup_logging(log_file: Optional[str] = None, level: int = logging.INFO) -> None:
    """
    Setup file logging for storage module (optional, for standalone usage).

    Configures a FileHandler for the storage.file_storage logger.
    For production use, prefer configuring logging at application level.

    Args:
        log_file: Path to log file (e.g., '04_logs/storage/file_storage.log').
                  If None, only console logging is configured.
        level: Logging level (default: INFO)

    Examples:
        >>> # Standalone usage
        >>> setup_logging(log_file="04_logs/storage/file_storage.log")
        >>>
        >>> # Or use application-level logging config (recommended)
        >>> import logging.config
        >>> logging.config.dictConfig({...})
    """
    logger = logging.getLogger("storage.file_storage")

    # Avoid adding duplicate handlers
    if logger.handlers:
        return

    logger.setLevel(level)

    if log_file:
        # Create directory if needed
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        # Add file handler
        handler = logging.FileHandler(log_file, encoding="utf-8")
        handler.setLevel(level)
        formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    # Ensure logger propagates to root logger
    logger.propagate = True
