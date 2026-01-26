"""
Mock LLM Gateway for testing.

Provides mock implementation without real API calls.
"""
import asyncio
import json
from pathlib import Path
from typing import Dict, List, Optional

from gateway.models import LLMRequest, LLMResponse, ModelConfig, ModelProvider


class MockLLMGateway:
    """
    Mock LLM Gateway for testing.

    Simulates LLMGateway behavior without real API calls.
    Returns predefined responses instantly.
    """

    def __init__(
        self,
        configs: Dict[str, ModelConfig],
        log_dir: Optional[str] = None,
        mock_responses: Optional[Dict[str, str]] = None,
        fixtures_path: Optional[str] = None,
    ):
        """
        Args:
            configs: Dict {model_id: ModelConfig}
            log_dir: Directory for logs
            mock_responses: Dict {request_id: response_content} for predefined responses
            fixtures_path: Path to fixtures JSON file with predefined responses
        """
        self.configs = configs
        self.log_dir = log_dir
        self._started = False

        # Load mock responses from fixtures if provided
        self.mock_responses = mock_responses or {}
        if fixtures_path:
            self._load_fixtures(fixtures_path)

    def _load_fixtures(self, fixtures_path: str):
        """Load predefined responses from JSON fixtures file."""
        path = Path(fixtures_path)
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                fixtures = json.load(f)
                # Merge fixtures with existing mock_responses
                self.mock_responses.update(fixtures)

    async def start(self):
        """Start mock gateway."""
        self._started = True

    async def stop(self):
        """Stop mock gateway."""
        self._started = False

    async def request(self, request: LLMRequest) -> LLMResponse:
        """
        Send request to mock LLM.

        Returns predefined response or default content.
        Supports tool_calls if defined in mock_responses.
        """
        response_data = self.mock_responses.get(request.request_id)

        if isinstance(response_data, dict):
            # Support custom response format
            return LLMResponse(
                request_id=request.request_id,
                content=response_data.get("content", f"Mock response for {request.request_id}"),
                tool_calls=response_data.get("tool_calls"),
                usage=response_data.get("usage", {"input_tokens": 10, "output_tokens": 20}),
                latency_ms=response_data.get("latency_ms", 0),
            )
        elif isinstance(response_data, str):
            # Simple string response
            return LLMResponse(
                request_id=request.request_id,
                content=response_data,
                usage={"input_tokens": 10, "output_tokens": 20},
                latency_ms=0,
            )
        else:
            # Default response
            return LLMResponse(
                request_id=request.request_id,
                content=f"Mock response for {request.request_id}",
                usage={"input_tokens": 10, "output_tokens": 20},
                latency_ms=0,
            )

    async def batch(self, requests: List[LLMRequest]) -> List[LLMResponse]:
        """
        Send batch of requests to mock LLM.

        Returns responses for all requests.
        """
        results = []
        for req in requests:
            resp = await self.request(req)
            results.append(resp)
        return results
