"""
Simple LLM Gateway implementation.

Provides simplified access to LLM models without queues, batching, or rate limiting.
Retry only for timeout errors (HTTP 408, 504).
"""
import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from .models import (
    LLMMessage,
    LLMRequest,
    LLMResponse,
    ModelConfig,
    ModelProvider,
)


class SimpleLLMGateway:
    """
    Simplified LLM Gateway without queues, batching, or rate limiting.

    Features:
    - Direct request execution without queues
    - Retry only for timeout errors (HTTP 408, 504)
    - Sequential batch processing for interface compatibility
    - JSONL logging for debugging

    Constants:
    - MAX_RETRIES: 5 attempts for timeout errors
    - RETRY_DELAY_SECONDS: 1 second between retries
    """

    MAX_RETRIES: int = 5
    RETRY_DELAY_SECONDS: float = 1.0

    def __init__(
        self,
        configs: Dict[str, ModelConfig],
        log_dir: Optional[str] = None,
    ):
        """
        Initialize SimpleLLMGateway.

        Args:
            configs: Dict {model_id: ModelConfig}
            log_dir: Directory for logs (optional)
        """
        self.log_dir = log_dir
        self.configs = configs
        self._clients: Dict[str, object] = {}

        # Create langchain clients for each model
        for model_id, config in configs.items():
            self._clients[model_id] = self._create_client(config)

        self._setup_logging()

    def _create_client(self, config: ModelConfig) -> object:
        """
        Create Langchain client for the model.

        Args:
            config: ModelConfig

        Returns:
            Langchain client (ChatAnthropic or ChatOpenAI)

        Raises:
            ValueError: If provider is not supported
        """
        from langchain_anthropic import ChatAnthropic
        from langchain_openai import ChatOpenAI

        provider = config.provider

        if provider == ModelProvider.CLAUDE_HAIKU:
            return ChatAnthropic(
                model=config.model_name,
                api_key=config.api_key,
                temperature=0.0,
                timeout=None,
            )
        elif provider == ModelProvider.CLAUDE_SONNET:
            return ChatAnthropic(
                model=config.model_name,
                api_key=config.api_key,
                temperature=0.0,
                timeout=None,
            )
        elif provider == ModelProvider.CLAUDE_OPUS:
            return ChatAnthropic(
                model=config.model_name,
                api_key=config.api_key,
                temperature=0.0,
                timeout=None,
            )
        elif provider == ModelProvider.GPT_4O_MINI:
            return ChatOpenAI(
                model=config.model_name,
                api_key=config.api_key,
                temperature=0.0,
                timeout=None,
            )
        elif provider == ModelProvider.GPT_4O:
            return ChatOpenAI(
                model=config.model_name,
                api_key=config.api_key,
                temperature=0.0,
                timeout=None,
            )
        else:
            raise ValueError(f"Unsupported provider: {provider}")

    async def request(self, request: LLMRequest) -> LLMResponse:
        """
        Send request to LLM with retry for timeout errors only.

        Args:
            request: LLMRequest

        Returns:
            LLMResponse

        Raises:
            ValueError: If model not found
            Exception: For all errors except timeout (after last retry)
        """
        client = self._clients.get(request.model)
        if not client:
            raise ValueError(f"Unknown model: {request.model}")

        # Convert to langchain format
        lc_messages = []
        for msg in request.messages:
            # Check if this is a tool call message
            if msg.tool_call:
                # Assistant message with tool call - use Langchain format
                from langchain_core.messages import AIMessage
                lc_messages.append(AIMessage(
                    content=msg.content,
                    tool_calls=[msg.tool_call]
                ))
            elif msg.role == "tool" and msg.name:
                # Tool response message
                from langchain_core.messages import ToolMessage
                lc_messages.append(ToolMessage(
                    content=msg.content,
                    tool_call_id=msg.tool_call.get("id") if msg.tool_call else "unknown"
                ))
            else:
                # Regular message
                lc_messages.append((msg.role, msg.content))

        last_exception = None

        # Retry loop (only for timeout errors)
        for attempt in range(self.MAX_RETRIES):
            try:
                start_time = asyncio.get_event_loop().time()

                # Send request
                lc_response = await client.ainvoke(lc_messages)

                # Build response
                response = LLMResponse(
                    request_id=request.request_id,
                    content=lc_response.content,
                    tool_calls=self._extract_tool_calls(lc_response),
                    usage=getattr(lc_response, "usage_metadata", None),
                    latency_ms=int(
                        (asyncio.get_event_loop().time() - start_time) * 1000
                    ),
                )

                self._log_success(request, response, attempt)
                return response

            except Exception as e:
                last_exception = e

                # Check: is this a timeout error?
                if self._is_timeout_error(e):
                    if attempt < self.MAX_RETRIES - 1:
                        # Retry with delay
                        self._log_retry(request, attempt, e)
                        await asyncio.sleep(self.RETRY_DELAY_SECONDS)
                        continue
                    else:
                        # Last attempt - crash for debugging
                        self._log_max_retries_exceeded(request, e)
                        raise

                # Not timeout - propagate immediately
                self._log_error(request, e)
                raise

        # Should not reach here, but just in case
        raise last_exception

    async def batch(self, requests: List[LLMRequest]) -> List[LLMResponse]:
        """
        Send batch of requests (sequentially, no optimization).

        Args:
            requests: List of LLMRequest

        Returns:
            List of LLMResponse
        """
        responses = []
        for req in requests:
            response = await self.request(req)
            responses.append(response)

        return responses

    def _is_timeout_error(self, error: Exception) -> bool:
        """
        Check if error is a timeout error from provider.

        Checks HTTP status codes:
        - 408 Request Timeout
        - 504 Gateway Timeout

        Args:
            error: Exception to check

        Returns:
            True if timeout error, False otherwise
        """
        # Check httpx HTTPStatusError
        if hasattr(error, "response"):
            status = getattr(error.response, "status_code", None)
            if status in [408, 504]:
                return True

        return False

    def _extract_tool_calls(self, lc_response) -> Optional[List[Dict]]:
        """
        Extract tool calls from langchain response.

        Args:
            lc_response: Langchain response

        Returns:
            List of tool calls or None
        """
        if hasattr(lc_response, "tool_calls"):
            return lc_response.tool_calls
        return None

    def _setup_logging(self):
        """Setup logging configuration."""
        self.logger = logging.getLogger(__name__)

    def _log_success(self, request: LLMRequest, response: LLMResponse, attempt: int):
        """
        Log successful request.

        Args:
            request: LLMRequest
            response: LLMResponse
            attempt: Attempt number
        """
        if not self.log_dir:
            return

        log_path = Path(self.log_dir) / "gateway" / "simple_requests.jsonl"
        log_path.parent.mkdir(parents=True, exist_ok=True)

        log_entry = {
            "timestamp": self._get_timestamp(),
            "model": request.model,
            "request_id": request.request_id,
            "agent_id": request.agent_id,
            "attempt": attempt,
            "latency_ms": response.latency_ms,
            "status": "success",
        }

        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")

    def _log_retry(self, request: LLMRequest, attempt: int, error: Exception):
        """
        Log retry attempt.

        Args:
            request: LLMRequest
            attempt: Attempt number
            error: Exception that caused retry
        """
        if not self.log_dir:
            return

        log_path = Path(self.log_dir) / "gateway" / "simple_retries.jsonl"
        log_path.parent.mkdir(parents=True, exist_ok=True)

        log_entry = {
            "timestamp": self._get_timestamp(),
            "model": request.model,
            "request_id": request.request_id,
            "attempt": attempt,
            "error": str(error),
            "error_type": type(error).__name__,
            "status": "retry",
        }

        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")

    def _log_max_retries_exceeded(self, request: LLMRequest, error: Exception):
        """
        Log max retries exceeded.

        Args:
            request: LLMRequest
            error: Exception that caused all retries to fail
        """
        if not self.log_dir:
            return

        log_path = Path(self.log_dir) / "gateway" / "simple_errors.jsonl"
        log_path.parent.mkdir(parents=True, exist_ok=True)

        log_entry = {
            "timestamp": self._get_timestamp(),
            "model": request.model,
            "request_id": request.request_id,
            "agent_id": request.agent_id,
            "error": str(error),
            "error_type": type(error).__name__,
            "max_retries": self.MAX_RETRIES,
            "status": "max_retries_exceeded",
        }

        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")

    def _log_error(self, request: LLMRequest, error: Exception):
        """
        Log non-timeout error.

        Args:
            request: LLMRequest
            error: Exception
        """
        if not self.log_dir:
            return

        log_path = Path(self.log_dir) / "gateway" / "simple_errors.jsonl"
        log_path.parent.mkdir(parents=True, exist_ok=True)

        log_entry = {
            "timestamp": self._get_timestamp(),
            "model": request.model,
            "request_id": request.request_id,
            "agent_id": request.agent_id,
            "error": str(error),
            "error_type": type(error).__name__,
            "status": "error",
        }

        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")

    def _get_timestamp(self) -> str:
        """
        Get current timestamp in ISO format.

        Returns:
            ISO format timestamp string
        """
        return datetime.now().isoformat()
