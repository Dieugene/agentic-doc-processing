"""
Response Router for LLM Gateway.

Handles registration and delivery of LLM request results.
"""
import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

from .models import LLMRequest, LLMResponse


class ResponseRouter:
    """
    Distributes LLM responses to waiting agents.

    Tracks pending requests and ensures delivery via futures.
    """

    def __init__(self, log_dir: Optional[str] = None):
        self.log_dir = log_dir
        self._pending_requests: Dict[str, LLMRequest] = {}
        self._pending_futures: Dict[str, asyncio.Future] = {}

    def register(self, request: LLMRequest, future: asyncio.Future):
        """
        Register a pending request.

        Args:
            request: LLMRequest
            future: Future for the result
        """
        self._pending_requests[request.request_id] = request
        self._pending_futures[request.request_id] = future

    def resolve(self, response: LLMResponse):
        """
        Resolve request with response.

        Args:
            response: LLMResponse with request_id
        """
        future = self._pending_futures.get(response.request_id)
        if not future:
            print(f"Warning: No future for request_id {response.request_id}")
            return

        if not future.done():
            future.set_result(response)

        self._unregister(response.request_id)
        self._log_response(response)

    def resolve_error(self, request_id: str, error: Exception):
        """
        Resolve request with error.

        Args:
            request_id: Request ID
            error: Exception
        """
        future = self._pending_futures.get(request_id)
        if not future:
            print(f"Warning: No future for request_id {request_id}")
            return

        if not future.done():
            future.set_exception(error)

        self._unregister(request_id)
        self._log_error(request_id, error)

    def _unregister(self, request_id: str):
        """
        Remove request from registers.

        Args:
            request_id: Request ID
        """
        self._pending_requests.pop(request_id, None)
        self._pending_futures.pop(request_id, None)

    def _log_response(self, response: LLMResponse):
        """
        Log successful response.

        Args:
            response: LLMResponse
        """
        if not self.log_dir:
            return

        log_path = Path(self.log_dir) / "gateway" / "responses.jsonl"
        log_path.parent.mkdir(parents=True, exist_ok=True)

        request = self._pending_requests.get(response.request_id)

        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "request_id": response.request_id,
            "agent_id": request.agent_id if request else None,
            "latency_ms": response.latency_ms,
            "status": "success",
        }

        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")

    def _log_error(self, request_id: str, error: Exception):
        """
        Log error.

        Args:
            request_id: Request ID
            error: Exception
        """
        if not self.log_dir:
            return

        log_path = Path(self.log_dir) / "gateway" / "errors.jsonl"
        log_path.parent.mkdir(parents=True, exist_ok=True)

        request = self._pending_requests.get(request_id)

        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "request_id": request_id,
            "agent_id": request.agent_id if request else None,
            "error": str(error),
            "status": "error",
        }

        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
