"""
File-based JSON storage for DocumentSkeleton.

Provides persistence for document structures with JSON serialization.
"""
from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from document.skeleton import DocumentSkeleton, InternalStructure, Node, NodeType, PageRange

logger = logging.getLogger(__name__)


class StorageError(Exception):
    """Base exception for storage errors."""

    pass


class Storage(ABC):
    """
    Abstract base class for storage implementations.

    This abstraction allows migration to different storage backends
    (e.g., PostgreSQL) in v2.0 without changing client code.
    """

    @abstractmethod
    async def save_skeleton(self, document_id: str, skeleton: DocumentSkeleton) -> None:
        """
        Save DocumentSkeleton to storage.

        Args:
            document_id: Unique document identifier
            skeleton: DocumentSkeleton to save

        Raises:
            StorageError: If save operation fails
        """
        pass

    @abstractmethod
    async def load_skeleton(self, document_id: str) -> Optional[DocumentSkeleton]:
        """
        Load DocumentSkeleton from storage.

        Args:
            document_id: Unique document identifier

        Returns:
            DocumentSkeleton if found, None otherwise
        """
        pass

    @abstractmethod
    def document_exists(self, document_id: str) -> bool:
        """
        Check if document exists in storage.

        Args:
            document_id: Unique document identifier

        Returns:
            True if document exists, False otherwise
        """
        pass


class FileStorage(Storage):
    """
    File-based JSON storage for DocumentSkeleton.

    Storage structure:
        data/{document_id}/skeleton.json

    JSON format includes metadata and all node data.
    """

    def __init__(self, base_path: str | None = None):
        """
        Initialize FileStorage.

        Args:
            base_path: Base directory for storage. If None, uses STORAGE_BASE_PATH from env.
        """
        if base_path is None:
            from .config import get_storage_config

            base_path = get_storage_config()["base_path"]

        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)
        logger.info(f"FileStorage initialized with base_path={self.base_path}")

    async def save_skeleton(self, document_id: str, skeleton: DocumentSkeleton) -> None:
        """
        Save DocumentSkeleton to JSON file.

        Creates data/{document_id}/skeleton.json with serialized node data.

        Args:
            document_id: Unique document identifier
            skeleton: DocumentSkeleton to save

        Raises:
            StorageError: If write operation fails
        """
        doc_dir = self.base_path / document_id
        doc_dir.mkdir(parents=True, exist_ok=True)

        # Serialize all nodes
        nodes_data: Dict[str, Dict[str, Any]] = {}
        for node_id, node in skeleton._nodes.items():
            node_data = {
                "id": node.id,
                "type": node.type.value,
                "title": node.title,
                "content": node.content,
                "page_range": {"start": node.page_range.start, "end": node.page_range.end},
                "parent_id": node.parent_id,
                "children_ids": node.children_ids,
                "internal_structure": node.internal_structure.raw,
                "explicit_refs": node.explicit_refs,
                "hash": node.hash,
                "table_data": node.table_data,
            }
            nodes_data[node_id] = node_data

        skeleton_data = {
            "document_id": skeleton.document_id,
            "created_at": datetime.now().isoformat(),
            "source_file": {
                "path": None,
                "hash": None,
                "size_bytes": 0,
            },
            "nodes": nodes_data,
        }

        skeleton_path = doc_dir / "skeleton.json"

        try:
            # Atomic write: temp file + replace (cross-platform, overwrites on Windows)
            temp_path = doc_dir / "skeleton.json.tmp"
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(skeleton_data, f, ensure_ascii=False, indent=2)
            temp_path.replace(skeleton_path)  # replace() works on both Unix and Windows
            logger.info(f"Saved skeleton for document {document_id} to {skeleton_path}")
        except (IOError, OSError) as e:
            logger.error(f"Failed to write skeleton for {document_id}: {e}")
            raise StorageError(f"Failed to save skeleton for {document_id}") from e

    async def load_skeleton(self, document_id: str) -> Optional[DocumentSkeleton]:
        """
        Load DocumentSkeleton from JSON file.

        Args:
            document_id: Unique document identifier

        Returns:
            DocumentSkeleton if found, None otherwise

        Raises:
            StorageError: If JSON is corrupted
        """
        skeleton_path = self.base_path / document_id / "skeleton.json"

        if not skeleton_path.exists():
            logger.debug(f"Skeleton not found for document {document_id}")
            return None

        try:
            with open(skeleton_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except FileNotFoundError:
            logger.debug(f"Skeleton not found for document {document_id}")
            return None
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON for document {document_id}: {e}")
            raise StorageError(f"Corrupted skeleton for {document_id}: {e}") from e
        except (IOError, OSError) as e:
            logger.error(f"Failed to read skeleton for {document_id}: {e}")
            raise StorageError(f"Failed to read skeleton for {document_id}") from e

        # Reconstruct nodes
        nodes: Dict[str, Node] = {}
        for node_id, node_data in data["nodes"].items():
            nodes[node_id] = Node(
                id=node_data["id"],
                type=NodeType(node_data["type"]),
                title=node_data.get("title"),
                content=node_data.get("content", ""),
                page_range=PageRange(**node_data["page_range"]),
                parent_id=node_data.get("parent_id"),
                children_ids=node_data.get("children_ids", []),
                internal_structure=InternalStructure(raw=node_data.get("internal_structure", {})),
                explicit_refs=node_data.get("explicit_refs", []),
                hash=node_data["hash"],
                table_data=node_data.get("table_data"),
            )

        # Create DocumentSkeleton
        skeleton = DocumentSkeleton(document_id=data["document_id"], nodes=nodes)
        logger.info(f"Loaded skeleton for document {document_id} from {skeleton_path}")
        return skeleton

    def document_exists(self, document_id: str) -> bool:
        """
        Check if document skeleton exists in storage.

        Args:
            document_id: Unique document identifier

        Returns:
            True if skeleton.json exists, False otherwise
        """
        path = self.base_path / document_id / "skeleton.json"
        exists = path.exists()
        logger.debug(f"document_exists({document_id}): {exists}")
        return exists
