"""
Unit tests for BatchExecutorWithRetry.

Tests retry scenarios with mocked errors.
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

import pytest

from gateway.batch_executor_retry import BatchExecutorWithRetry
from gateway.retry_policy import RetryPolicy
from gateway.models import ModelConfig, ModelProvider, LLMRequest, LLMResponse, LLMMessage


class TestBatchExecutorWithRetry:
    """Test suite for BatchExecutorWithRetry."""

    @pytest.fixture
    def model_config(self):
        """Create a test ModelConfig."""
        return ModelConfig(
            provider=ModelProvider.CLAUDE_HAIKU,
            endpoint="https://api.anthropic.com",
            api_key="test-key",
            model_name="claude-3-haiku-20240307",
        )

    @pytest.fixture
    def retry_policy(self):
        """Create a test RetryPolicy with short delays."""
        return RetryPolicy(
            max_retries=3,
            initial_delay_ms=10,  # Short for tests
            backoff_multiplier=2.0,
            jitter_ms=0,
        )

    @pytest.fixture
    def executor(self, model_config, retry_policy):
        """Create a BatchExecutorWithRetry instance."""
        return BatchExecutorWithRetry(model_config, retry_policy, log_dir=None)

    @pytest.fixture
    def sample_batch(self):
        """Create a sample batch."""
        request = LLMRequest(
            request_id="test-req-1",
            model="claude-haiku",
            messages=[LLMMessage(role="user", content="Hello")],
        )
        future = asyncio.Future()
        return [(request, future)]

    @pytest.mark.asyncio
    async def test_success_without_retry(self, executor, sample_batch):
        """Test successful request without any retry."""
        # Mock parent execute_batch to succeed
        with patch.object(
            executor.__class__.__bases__[0], "execute_batch", new=AsyncMock()
        ) as mock_execute:
            await executor.execute_batch(sample_batch)

            # Should be called exactly once
            assert mock_execute.call_count == 1

            # Future should not be done (parent handles it)
            assert not sample_batch[0][1].done()

    @pytest.mark.asyncio
    async def test_retry_on_429_then_success(self, executor, sample_batch, retry_policy):
        """TC-007: Retry on 429 rate limit, then succeed."""
        call_count = 0

        async def mock_execute(batch):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # First call fails with 429
                class HTTPStatusError(Exception):
                    def __init__(self):
                        self.response = MagicMock()
                        self.response.status_code = 429

                raise HTTPStatusError()
            # Second call succeeds
            return None

        with patch.object(
            executor.__class__.__bases__[0], "execute_batch", new=mock_execute
        ):
            await executor.execute_batch(sample_batch)

            # Should be called twice (original + 1 retry)
            assert call_count == 2

    @pytest.mark.asyncio
    async def test_retry_on_5xx_then_success(self, executor, sample_batch, retry_policy):
        """TC-008: Retry on 5xx server error, then succeed."""
        call_count = 0

        async def mock_execute(batch):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # First call fails with 503
                class HTTPStatusError(Exception):
                    def __init__(self):
                        self.response = MagicMock()
                        self.response.status_code = 503

                raise HTTPStatusError()
            # Second call succeeds
            return None

        with patch.object(
            executor.__class__.__bases__[0], "execute_batch", new=mock_execute
        ):
            await executor.execute_batch(sample_batch)

            # Should be called twice
            assert call_count == 2

    @pytest.mark.asyncio
    async def test_no_retry_on_400(self, executor, sample_batch):
        """TC-009: No retry on 400 client error."""
        async def mock_execute(batch):
            class HTTPStatusError(Exception):
                def __init__(self):
                    self.response = MagicMock()
                    self.response.status_code = 400

            raise HTTPStatusError()

        with patch.object(
            executor.__class__.__bases__[0], "execute_batch", new=mock_execute
        ):
            await executor.execute_batch(sample_batch)

            # Future should have error
            future = sample_batch[0][1]
            assert future.done()
            with pytest.raises(Exception):  # HTTPStatusError
                future.result()

    @pytest.mark.asyncio
    async def test_no_retry_on_404(self, executor, sample_batch):
        """TC-009: No retry on 404 not found."""
        async def mock_execute(batch):
            class HTTPStatusError(Exception):
                def __init__(self):
                    self.response = MagicMock()
                    self.response.status_code = 404

            raise HTTPStatusError()

        with patch.object(
            executor.__class__.__bases__[0], "execute_batch", new=mock_execute
        ):
            await executor.execute_batch(sample_batch)

            # Future should have error
            future = sample_batch[0][1]
            assert future.done()

    @pytest.mark.asyncio
    async def test_error_after_max_retries(self, executor, sample_batch, retry_policy):
        """TC-010: After max_retries, error is propagated to futures."""
        # Always fail with 5xx
        async def mock_execute(batch):
            class HTTPStatusError(Exception):
                def __init__(self):
                    self.response = MagicMock()
                    self.response.status_code = 503

            raise HTTPStatusError()

        with patch.object(
            executor.__class__.__bases__[0], "execute_batch", new=mock_execute
        ):
            await executor.execute_batch(sample_batch)

            # Future should have error after max_retries
            future = sample_batch[0][1]
            assert future.done()
            with pytest.raises(Exception):  # HTTPStatusError
                future.result()

    @pytest.mark.asyncio
    async def test_retry_on_connection_error(self, executor, sample_batch):
        """Test retry on ConnectionError."""
        call_count = 0

        async def mock_execute(batch):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ConnectionError("Network error")
            return None

        with patch.object(
            executor.__class__.__bases__[0], "execute_batch", new=mock_execute
        ):
            await executor.execute_batch(sample_batch)

            assert call_count == 2

    @pytest.mark.asyncio
    async def test_retry_on_timeout(self, executor, sample_batch):
        """Test retry on TimeoutError."""
        call_count = 0

        async def mock_execute(batch):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise TimeoutError("Request timeout")
            return None

        with patch.object(
            executor.__class__.__bases__[0], "execute_batch", new=mock_execute
        ):
            await executor.execute_batch(sample_batch)

            assert call_count == 2

    @pytest.mark.asyncio
    async def test_cancelled_error_propagates(self, executor, sample_batch):
        """Test CancelledError is not retried."""
        async def mock_execute(batch):
            raise asyncio.CancelledError()

        with patch.object(
            executor.__class__.__bases__[0], "execute_batch", new=mock_execute
        ):
            with pytest.raises(asyncio.CancelledError):
                await executor.execute_batch(sample_batch)

    @pytest.mark.asyncio
    async def test_empty_batch(self, executor):
        """Test empty batch is handled gracefully."""
        await executor.execute_batch([])  # Should not raise
