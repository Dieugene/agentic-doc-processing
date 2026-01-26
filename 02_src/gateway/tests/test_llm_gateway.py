"""
Unit tests for LLM Gateway.
"""
import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Tuple

import pytest

from gateway.models import (
    LLMMessage,
    LLMRequest,
    LLMResponse,
    ModelConfig,
    ModelProvider,
)
from gateway.llm_gateway import BatchExecutor, LLMGateway, RequestQueue
from gateway.tests.mock_gateway import MockLLMGateway


class TestRequestQueue:
    """Tests for RequestQueue."""

    @pytest.mark.asyncio
    async def test_put_returns_future(self):
        """Test that put returns a Future."""
        queue = RequestQueue(model="test-model", batch_size=10, batch_timeout_ms=100)

        request = LLMRequest(
            request_id="test-1", model="test-model", messages=[LLMMessage(role="user", content="test")]
        )

        future = await queue.put(request)

        assert isinstance(future, asyncio.Future)
        assert not future.done()

    @pytest.mark.asyncio
    async def test_get_batch_waits_for_first_request(self):
        """Test that get_batch blocks until first request."""
        queue = RequestQueue(model="test-model", batch_size=10, batch_timeout_ms=100)

        # Start task that will wait
        async def get_batch_task():
            return await queue.get_batch()

        task = asyncio.create_task(get_batch_task())

        # Give task time to start waiting
        await asyncio.sleep(0.01)

        # Add request
        request = LLMRequest(
            request_id="test-1", model="test-model", messages=[LLMMessage(role="user", content="test")]
        )
        await queue.put(request)

        # Task should complete
        batch = await task
        assert len(batch) == 1
        assert batch[0][0].request_id == "test-1"

    @pytest.mark.asyncio
    async def test_get_batch_accumulates_to_batch_size(self):
        """Test that get_batch accumulates up to batch_size."""
        queue = RequestQueue(model="test-model", batch_size=3, batch_timeout_ms=100)

        # Add 3 requests
        for i in range(3):
            request = LLMRequest(
                request_id=f"test-{i}",
                model="test-model",
                messages=[LLMMessage(role="user", content=f"test {i}")],
            )
            await queue.put(request)

        batch = await queue.get_batch()
        assert len(batch) == 3

    @pytest.mark.asyncio
    async def test_get_batch_respects_timeout(self):
        """Test that get_batch returns on timeout even if batch not full."""
        queue = RequestQueue(model="test-model", batch_size=10, batch_timeout_ms=50)

        # Add 1 request
        request = LLMRequest(
            request_id="test-1", model="test-model", messages=[LLMMessage(role="user", content="test")]
        )
        await queue.put(request)

        start = datetime.now()
        batch = await queue.get_batch()
        elapsed = (datetime.now() - start).total_seconds() * 1000

        assert len(batch) == 1
        # Should timeout around 50ms (with some tolerance)
        assert 40 < elapsed < 150

    @pytest.mark.asyncio
    async def test_future_completes_on_set_result(self):
        """Test that future completes when set_result is called."""
        queue = RequestQueue(model="test-model", batch_size=10, batch_timeout_ms=100)

        request = LLMRequest(
            request_id="test-1", model="test-model", messages=[LLMMessage(role="user", content="test")]
        )
        future = await queue.put(request)

        # Get the batch and set result
        batch = await queue.get_batch()
        _, future_from_batch = batch[0]

        response = LLMResponse(request_id="test-1", content="test response")
        future_from_batch.set_result(response)

        # Original future should be completed
        assert future.done()
        assert await future == response


class TestBatchExecutor:
    """Tests for BatchExecutor."""

    def test_create_client_claude(self):
        """Test creating client for Claude model."""
        config = ModelConfig(
            provider=ModelProvider.CLAUDE_HAIKU,
            endpoint="https://api.anthropic.com",
            api_key="test-key",
            model_name="claude-3-haiku-20240307",
        )

        executor = BatchExecutor(config)
        assert executor._client is not None

        # Check client type
        from langchain_anthropic import ChatAnthropic
        assert isinstance(executor._client, ChatAnthropic)

    def test_create_client_openai(self):
        """Test creating client for OpenAI model."""
        config = ModelConfig(
            provider=ModelProvider.GPT_4O_MINI,
            endpoint="https://api.openai.com",
            api_key="test-key",
            model_name="gpt-4o-mini",
        )

        executor = BatchExecutor(config)
        assert executor._client is not None

        # Check client type
        from langchain_openai import ChatOpenAI
        assert isinstance(executor._client, ChatOpenAI)

    def test_create_client_unsupported_provider(self):
        """Test that unsupported provider raises ValueError."""
        config = ModelConfig(
            provider=ModelProvider.LOCAL_LLAMA,
            endpoint="http://localhost:11434",
            api_key="",
            model_name="llama2",
        )

        with pytest.raises(ValueError, match="Unsupported provider"):
            BatchExecutor(config)


class TestLLMGateway:
    """Tests for LLMGateway."""

    @pytest.fixture
    def mock_configs(self):
        """Create mock model configs."""
        return {
            "claude-haiku": ModelConfig(
                provider=ModelProvider.CLAUDE_HAIKU,
                endpoint="https://api.anthropic.com",
                api_key="test-key",
                model_name="claude-3-haiku-20240307",
                batch_size=2,
                batch_timeout_ms=50,
            ),
            "gpt-4o-mini": ModelConfig(
                provider=ModelProvider.GPT_4O_MINI,
                endpoint="https://api.openai.com",
                api_key="test-key",
                model_name="gpt-4o-mini",
                batch_size=2,
                batch_timeout_ms=50,
            ),
        }

    @pytest.mark.asyncio
    async def test_gateway_initialization(self, mock_configs):
        """Test gateway initialization creates queues and executors."""
        gateway = LLMGateway(mock_configs)

        assert len(gateway._queues) == 2
        assert len(gateway._executors) == 2
        assert "claude-haiku" in gateway._queues
        assert "gpt-4o-mini" in gateway._queues

    @pytest.mark.asyncio
    async def test_gateway_start_stop(self, mock_configs):
        """Test starting and stopping gateway."""
        gateway = LLMGateway(mock_configs)

        await gateway.start()
        assert len(gateway._worker_tasks) == 2

        await gateway.stop()

    @pytest.mark.asyncio
    async def test_request_unknown_model_raises_error(self, mock_configs):
        """Test that requesting unknown model raises ValueError."""
        gateway = LLMGateway(mock_configs)

        request = LLMRequest(
            request_id="test-1",
            model="unknown-model",
            messages=[LLMMessage(role="user", content="test")],
        )

        with pytest.raises(ValueError, match="Unknown model"):
            await gateway.request(request)


class TestMockLLMGateway:
    """Tests for MockLLMGateway."""

    @pytest.fixture
    def mock_configs(self):
        """Create mock model configs."""
        return {
            "test-model": ModelConfig(
                provider=ModelProvider.CLAUDE_HAIKU,
                endpoint="https://test.com",
                api_key="test-key",
                model_name="test-model",
            )
        }

    @pytest.mark.asyncio
    async def test_mock_request_returns_response(self, mock_configs):
        """Test that mock request returns LLMResponse."""
        mock_responses = {"test-1": "Custom response"}
        gateway = MockLLMGateway(mock_configs, mock_responses=mock_responses)

        request = LLMRequest(
            request_id="test-1",
            model="test-model",
            messages=[LLMMessage(role="user", content="test")],
        )

        response = await gateway.request(request)

        assert response.request_id == "test-1"
        assert response.content == "Custom response"
        assert response.latency_ms == 0

    @pytest.mark.asyncio
    async def test_mock_request_default_response(self, mock_configs):
        """Test that mock request returns default response when not predefined."""
        gateway = MockLLMGateway(mock_configs)

        request = LLMRequest(
            request_id="unknown",
            model="test-model",
            messages=[LLMMessage(role="user", content="test")],
        )

        response = await gateway.request(request)

        assert response.content == "Mock response for unknown"

    @pytest.mark.asyncio
    async def test_mock_batch_returns_multiple_responses(self, mock_configs):
        """Test that mock batch returns multiple responses."""
        gateway = MockLLMGateway(mock_configs)

        requests = [
            LLMRequest(
                request_id="test-1",
                model="test-model",
                messages=[LLMMessage(role="user", content="test 1")],
            ),
            LLMRequest(
                request_id="test-2",
                model="test-model",
                messages=[LLMMessage(role="user", content="test 2")],
            ),
        ]

        responses = await gateway.batch(requests)

        assert len(responses) == 2
        assert responses[0].request_id == "test-1"
        assert responses[1].request_id == "test-2"

    @pytest.mark.asyncio
    async def test_mock_start_stop(self, mock_configs):
        """Test mock start and stop."""
        gateway = MockLLMGateway(mock_configs)

        await gateway.start()
        assert gateway._started is True

        await gateway.stop()
        assert gateway._started is False
