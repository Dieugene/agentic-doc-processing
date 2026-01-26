"""
Retry policy for LLM Gateway API calls.

Implements exponential backoff with jitter for handling temporary API errors.
"""
import random
from dataclasses import dataclass
from typing import Optional


@dataclass
class RetryPolicy:
    """
    Retry policy with exponential backoff and jitter.

    Strategy: Exponential backoff with random jitter to avoid thundering herd.
    """

    max_retries: int = 3
    initial_delay_ms: int = 1000
    backoff_multiplier: float = 2.0
    jitter_ms: int = 500  # Random jitter range (+/-)

    def get_delay(self, attempt: int) -> float:
        """
        Calculate delay for retry attempt.

        Args:
            attempt: Attempt number (0-indexed)

        Returns:
            Delay in seconds
        """
        # Exponential backoff
        base_delay = self.initial_delay_ms * (self.backoff_multiplier ** attempt)

        # Add jitter to avoid thundering herd
        jitter = random.uniform(-self.jitter_ms, self.jitter_ms)

        return (base_delay + jitter) / 1000

    def should_retry(self, error: Exception, attempt: int) -> bool:
        """
        Determine if request should be retried.

        Retry on:
        - 429 (rate limit)
        - 5xx (server errors)
        - Temporary network errors

        Don't retry on:
        - 4xx (client errors, except 429)
        - Validation errors

        Args:
            error: The exception that occurred
            attempt: Current attempt number

        Returns:
            True if should retry, False otherwise
        """
        # Import here to avoid hard dependency
        try:
            from httpx import HTTPStatusError
        except ImportError:
            HTTPStatusError = None

        if HTTPStatusError and isinstance(error, HTTPStatusError):
            status = error.response.status_code

            # Rate limit - always retry
            if status == 429:
                return True

            # Server errors - retry
            if 500 <= status < 600:
                return True

            # Client errors - don't retry
            if 400 <= status < 500:
                return False

        # Network errors - retry
        if isinstance(error, (ConnectionError, TimeoutError)):
            return True

        # Default - don't retry
        return False
