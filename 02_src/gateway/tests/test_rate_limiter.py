"""
Unit tests for RateLimiter components.
"""
import asyncio
from datetime import datetime, timedelta

import pytest

from gateway.models import LLMRequest, LLMMessage, ModelConfig, ModelProvider
from gateway.rate_limiter import TokenCounter, RateLimitTracker, RateLimiter


class TestTokenCounter:
    """Tests for TokenCounter."""

    def test_count_tokens_non_empty(self):
        """TokenCounter returns non-zero for non-empty text."""
        counter = TokenCounter()
        result = counter.count_tokens("Hello world", "gpt-4o")
        assert result > 0

    def test_count_tokens_empty(self):
        """TokenCounter returns 0 for empty text."""
        counter = TokenCounter()
        result = counter.count_tokens("", "gpt-4o")
        assert result == 0

    def test_count_request_tokens_with_messages(self):
        """Count tokens in request with messages."""
        counter = TokenCounter()
        request = LLMRequest(
            request_id="test_1",
            model="gpt-4o",
            messages=[
                LLMMessage(role="user", content="Hello world"),
                LLMMessage(role="assistant", content="Hi there"),
            ]
        )
        result = counter.count_request_tokens(request)
        assert result > 0

    def test_estimate_response_tokens(self):
        """Estimate response tokens returns conservative value."""
        counter = TokenCounter()
        result = counter.estimate_response_tokens()
        assert result == 1000


class TestRateLimitTracker:
    """Tests for RateLimitTracker."""

    @pytest.mark.asyncio
    async def test_tracks_requests_in_window(self):
        """Tracker tracks requests within sliding window."""
        tracker = RateLimitTracker(window_seconds=60)

        await tracker.add_request(100)
        await tracker.add_request(200)

        requests_count, tokens_count = await tracker.get_usage()
        assert requests_count == 2
        assert tokens_count == 300

    @pytest.mark.asyncio
    async def test_sliding_window_removes_old(self):
        """Old requests outside window are removed."""
        tracker = RateLimitTracker(window_seconds=1)

        await tracker.add_request(100)
        await asyncio.sleep(1.1)
        await tracker.add_request(200)

        requests_count, tokens_count = await tracker.get_usage()
        assert requests_count == 1
        assert tokens_count == 200

    @pytest.mark.asyncio
    async def test_can_make_request_within_limits(self):
        """Request allowed when within limits."""
        tracker = RateLimitTracker(window_seconds=60)

        await tracker.add_request(100)

        can_proceed, reason = await tracker.can_make_request(max_rpm=10, max_tpm=1000)
        assert can_proceed is True
        assert reason == ""

    @pytest.mark.asyncio
    async def test_can_make_request_exceeds_rpm(self):
        """Request blocked when RPM exceeded."""
        tracker = RateLimitTracker(window_seconds=60)

        for _ in range(10):
            await tracker.add_request(100)

        can_proceed, reason = await tracker.can_make_request(max_rpm=10, max_tpm=10000)
        assert can_proceed is False
        assert "Rate limit exceeded" in reason
        assert "10 requests / 10 RPM" in reason

    @pytest.mark.asyncio
    async def test_can_make_request_exceeds_tpm(self):
        """Request blocked when TPM exceeded."""
        tracker = RateLimitTracker(window_seconds=60)

        await tracker.add_request(1000)

        can_proceed, reason = await tracker.can_make_request(max_rpm=100, max_tpm=1000)
        assert can_proceed is False
        assert "Token limit exceeded" in reason
        assert "1000 tokens / 1000 TPM" in reason

    @pytest.mark.asyncio
    async def test_wait_until_available_zero_when_available(self):
        """Wait time is 0 when request can be made."""
        tracker = RateLimitTracker(window_seconds=60)

        wait_seconds = await tracker.wait_until_available(max_rpm=10, max_tpm=1000)
        assert wait_seconds == 0.0

    @pytest.mark.asyncio
    async def test_wait_until_available_calculates_delay(self):
        """Calculates correct wait time when rate limited."""
        tracker = RateLimitTracker(window_seconds=60)

        for _ in range(10):
            await tracker.add_request(100)

        wait_seconds = await tracker.wait_until_available(max_rpm=10, max_tpm=10000)
        assert wait_seconds > 0
        assert wait_seconds <= 60


class TestRateLimiter:
    """Tests for RateLimiter."""

    def test_creates_tracker_for_each_model(self):
        """Creates tracker for each model in config."""
        configs = {
            "model1": ModelConfig(
                provider=ModelProvider.GPT_4O,
                endpoint="https://api.openai.com/v1",
                api_key="test",
                model_name="gpt-4o",
                max_requests_per_minute=10,
                max_tokens_per_minute=1000,
            ),
            "model2": ModelConfig(
                provider=ModelProvider.CLAUDE_SONNET,
                endpoint="https://api.anthropic.com/v1",
                api_key="test",
                model_name="claude-sonnet",
                max_requests_per_minute=20,
                max_tokens_per_minute=2000,
            ),
        }

        limiter = RateLimiter(configs, log_dir=None)
        assert "model1" in limiter._trackers
        assert "model2" in limiter._trackers

    @pytest.mark.asyncio
    async def test_check_request_allows_when_no_limit(self):
        """Request allowed when model has no rate limit configured."""
        config = ModelConfig(
            provider=ModelProvider.GPT_4O,
            endpoint="https://api.openai.com/v1",
            api_key="test",
            model_name="gpt-4o",
        )

        limiter = RateLimiter({"model1": config}, log_dir=None)
        request = LLMRequest(
            request_id="test_1",
            model="model1",
            messages=[LLMMessage(role="user", content="Hello")]
        )

        can_proceed, reason, wait_seconds = await limiter.check_request(request)
        assert can_proceed is True
        assert reason == ""
        assert wait_seconds == 0.0

    @pytest.mark.asyncio
    async def test_check_request_blocks_when_exceeded(self):
        """Request blocked when rate limit exceeded."""
        config = ModelConfig(
            provider=ModelProvider.GPT_4O,
            endpoint="https://api.openai.com/v1",
            api_key="test",
            model_name="gpt-4o",
            max_requests_per_minute=1,
        )

        limiter = RateLimiter({"model1": config}, log_dir=None)

        # Register one request
        request1 = LLMRequest(
            request_id="test_1",
            model="model1",
            messages=[LLMMessage(role="user", content="Hello")]
        )
        response1 = type('obj', (), {'usage': None})()
        await limiter.register_request(request1, response1)

        # Second request should be blocked
        request2 = LLMRequest(
            request_id="test_2",
            model="model1",
            messages=[LLMMessage(role="user", content="Hello")]
        )
        can_proceed, reason, wait_seconds = await limiter.check_request(request2)
        assert can_proceed is False
        assert "Rate limit exceeded" in reason
        assert wait_seconds > 0

    @pytest.mark.asyncio
    async def test_register_request_updates_tracker(self):
        """Registering request updates tracker statistics."""
        config = ModelConfig(
            provider=ModelProvider.GPT_4O,
            endpoint="https://api.openai.com/v1",
            api_key="test",
            model_name="gpt-4o",
        )

        limiter = RateLimiter({"model1": config}, log_dir=None)
        request = LLMRequest(
            request_id="test_1",
            model="model1",
            messages=[LLMMessage(role="user", content="Hello world")]
        )
        response = type('obj', (), {
            'usage': {'input_tokens': 10, 'output_tokens': 20, 'total_tokens': 30}
        })()

        await limiter.register_request(request, response)

        requests_count, tokens_count = await limiter._trackers["model1"].get_usage()
        assert requests_count == 1
        assert tokens_count == 30
