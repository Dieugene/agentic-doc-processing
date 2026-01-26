"""
Unit tests for RetryPolicy.
"""
import asyncio
from unittest.mock import MagicMock, patch

import pytest

from gateway.retry_policy import RetryPolicy
from gateway.models import LLMRequest, LLMMessage


class TestRetryPolicy:
    """Test suite for RetryPolicy."""

    def test_get_delay_calculates_exponential_backoff(self):
        """TC-001: get_delay returns correct values with exponential backoff."""
        policy = RetryPolicy(
            max_retries=3,
            initial_delay_ms=1000,
            backoff_multiplier=2.0,
            jitter_ms=0,  # Disable jitter for predictable test
        )

        # Attempt 0: 1000ms
        delay_0 = policy.get_delay(0)
        assert delay_0 == 1.0

        # Attempt 1: 2000ms
        delay_1 = policy.get_delay(1)
        assert delay_1 == 2.0

        # Attempt 2: 4000ms
        delay_2 = policy.get_delay(2)
        assert delay_2 == 4.0

    def test_get_delay_includes_jitter(self):
        """TC-001: get_delay includes random jitter."""
        policy = RetryPolicy(
            max_retries=3,
            initial_delay_ms=1000,
            backoff_multiplier=2.0,
            jitter_ms=500,
        )

        delays = [policy.get_delay(0) for _ in range(100)]

        # With jitter, delays should vary
        assert min(delays) >= 0.5  # 1000 - 500 ms
        assert max(delays) <= 1.5  # 1000 + 500 ms
        assert len(set(delays)) > 1  # Not all the same

    def test_should_retry_true_for_429(self):
        """TC-002: should_retry returns True for 429 rate limit."""
        policy = RetryPolicy()

        # Mock HTTPStatusError with 429
        mock_error = MagicMock()
        mock_error.response.status_code = 429
        mock_error.__class__.__name__ = "HTTPStatusError"

        # Patch httpx import
        with patch("gateway.retry_policy.HTTPStatusError", type(mock_error).__bases__[0]):
            # Create real HTTPStatusError-like exception
            class HTTPStatusError(Exception):
                def __init__(self, status_code):
                    self.response = MagicMock()
                    self.response.status_code = status_code

            error = HTTPStatusError(429)
            assert policy.should_retry(error, 0) is True

    def test_should_retry_true_for_5xx(self):
        """TC-002: should_retry returns True for 5xx server errors."""
        policy = RetryPolicy()

        class HTTPStatusError(Exception):
            def __init__(self, status_code):
                self.response = MagicMock()
                self.response.status_code = status_code

        # Test various 5xx codes
        for status in [500, 502, 503, 504]:
            error = HTTPStatusError(status)
            assert policy.should_retry(error, 0) is True

    def test_should_retry_true_for_network_errors(self):
        """TC-002: should_retry returns True for ConnectionError and TimeoutError."""
        policy = RetryPolicy()

        # ConnectionError
        assert policy.should_retry(ConnectionError("Network error"), 0) is True

        # TimeoutError
        assert policy.should_retry(TimeoutError("Timeout"), 0) is True

    def test_should_retry_false_for_4xx(self):
        """TC-003: should_retry returns False for 4xx client errors (except 429)."""
        policy = RetryPolicy()

        class HTTPStatusError(Exception):
            def __init__(self, status_code):
                self.response = MagicMock()
                self.response.status_code = status_code

        # Test various 4xx codes (except 429)
        for status in [400, 401, 403, 404, 422]:
            error = HTTPStatusError(status)
            assert policy.should_retry(error, 0) is False

    def test_should_retry_false_for_generic_exceptions(self):
        """TC-003: should_retry returns False for generic exceptions."""
        policy = RetryPolicy()

        # Generic exception
        assert policy.should_retry(ValueError("Invalid input"), 0) is False
        assert policy.should_retry(RuntimeError("Unexpected error"), 0) is False
