"""
Storage module for document persistence.

Provides abstract interface and file-based JSON implementation
for storing DocumentSkeleton objects.
"""
from .config import get_storage_config, setup_logging
from .file_storage import FileStorage, Storage

__all__ = ["Storage", "FileStorage", "get_storage_config", "setup_logging"]
