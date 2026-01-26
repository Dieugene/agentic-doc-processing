"""
Rate Limiter for LLM Gateway.

Prevents exceeding API rate limits (RPM/TPM) with sliding window tracking.
"""
import asyncio
from collections import deque
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import json

from .models import LLMRequest, LLMResponse, ModelConfig


class TokenCounter:
    """
    Token counting for requests and responses.

    Uses tiktoken for OpenAI models, fallback estimation for others.
    """

    def __init__(self):
        self._encoder = None
        try:
            import tiktoken
            self._encoder = tiktoken.get_encoding("cl100k_base")
        except ImportError:
            pass

    def count_tokens(self, text: str, model: str) -> int:
        """
        Count tokens in text.

        Args:
            text: Text to count
            model: Model identifier (for encoding selection)

        Returns:
            Approximate token count
        """
        if self._encoder:
            return len(self._encoder.encode(text))
        else:
            # Fallback: 1 token ≈ 4 characters
            return len(text) // 4

    def count_request_tokens(self, request: LLMRequest) -> int:
        """
        Count tokens in request.

        Accounts for:
        - Messages
        - Tool descriptions
        - Tool parameters
        """
        total = 0

        for msg in request.messages:
            total += self.count_tokens(msg.content, request.model)

        if request.tools:
            for tool in request.tools:
                total += self.count_tokens(tool.description, request.model)
                total += self.count_tokens(str(tool.parameters), request.model)

        return total

    def estimate_response_tokens(self) -> int:
        """
        Estimate tokens in response.

        Conservative estimate for rate limiting since actual count unknown.
        """
        return 1000


class RateLimitTracker:
    """
    Tracks rate limit usage with sliding window.

    Maintains request history for accurate RPM/TPM tracking.
    """

    def __init__(self, window_seconds: int = 60):
        """
        Args:
            window_seconds: Observation window (default 60 seconds = 1 minute)
        """
        self.window_seconds = window_seconds
        self._requests: deque[Tuple[datetime, int]] = deque()
        self._lock = asyncio.Lock()

    async def add_request(self, tokens: int):
        """
        Add request to history.

        Args:
            tokens: Token count (input + output)
        """
        async with self._lock:
            now = datetime.now()
            self._requests.append((now, tokens))

            # Remove old entries outside window
            cutoff = now - timedelta(seconds=self.window_seconds)
            while self._requests and self._requests[0][0] < cutoff:
                self._requests.popleft()

    async def get_usage(self) -> Tuple[int, int]:
        """
        Get current usage.

        Returns:
            (requests_count, tokens_count)
        """
        async with self._lock:
            now = datetime.now()
            cutoff = now - timedelta(seconds=self.window_seconds)

            while self._requests and self._requests[0][0] < cutoff:
                self._requests.popleft()

            requests_count = len(self._requests)
            tokens_count = sum(tokens for _, tokens in self._requests)

            return requests_count, tokens_count

    async def can_make_request(
        self, max_rpm: int, max_tpm: int
    ) -> Tuple[bool, str]:
        """
        Check if request can be made.

        Args:
            max_rpm: Max requests per minute (0 = no limit)
            max_tpm: Max tokens per minute (0 = no limit)

        Returns:
            (can_proceed, reason)
        """
        requests_count, tokens_count = await self.get_usage()

        if max_rpm and requests_count >= max_rpm:
            return False, f"Rate limit exceeded: {requests_count} requests / {max_rpm} RPM"

        if max_tpm and tokens_count >= max_tpm:
            return False, f"Token limit exceeded: {tokens_count} tokens / {max_tpm} TPM"

        return True, ""

    async def wait_until_available(self, max_rpm: int, max_tpm: int) -> float:
        """
        Calculate delay until slot available.

        Returns:
            Wait time in seconds (0 if available now)
        """
        async with self._lock:
            now = datetime.now()

            # Clean old entries
            cutoff = now - timedelta(seconds=self.window_seconds)
            while self._requests and self._requests[0][0] < cutoff:
                self._requests.popleft()

            # Check RPM
            if max_rpm and len(self._requests) >= max_rpm:
                oldest_time = self._requests[0][0]
                available_at = oldest_time + timedelta(seconds=self.window_seconds)
                return (available_at - now).total_seconds()

            # Check TPM
            if max_tpm:
                tokens_count = sum(tokens for _, tokens in self._requests)
                if tokens_count >= max_tpm:
                    temp_tokens = tokens_count
                    temp_queue = deque(self._requests)

                    while temp_tokens >= max_tpm and temp_queue:
                        oldest_time, old_tokens = temp_queue.popleft()
                        temp_tokens -= old_tokens

                    if temp_queue:
                        available_at = temp_queue[0][0] + timedelta(seconds=self.window_seconds)
                        return (available_at - now).total_seconds()

            return 0.0


class RateLimiter:
    """
    Rate limit control for all models.

    Creates tracker for each model based on configuration.
    """

    def __init__(self, configs: Dict[str, ModelConfig], log_dir: Optional[str] = None):
        """
        Args:
            configs: Dict {model_id: ModelConfig} with max_rpm/max_tpm
            log_dir: Directory for logs
        """
        self.log_dir = log_dir
        self.configs = configs
        self.token_counter = TokenCounter()

        # Create tracker for each model
        self._trackers: Dict[str, RateLimitTracker] = {}
        for model_id in configs.keys():
            self._trackers[model_id] = RateLimitTracker()

    async def check_request(self, request: LLMRequest) -> Tuple[bool, str, float]:
        """
        Check if request can be sent.

        Args:
            request: LLMRequest

        Returns:
            (can_proceed, reason, wait_seconds)
        """
        tracker = self._trackers.get(request.model)
        config = self.configs.get(request.model)

        if not tracker or not config:
            return True, "", 0.0

        max_rpm = config.max_requests_per_minute or 0
        max_tpm = config.max_tokens_per_minute or 0

        if not max_rpm and not max_tpm:
            return True, "", 0.0

        can_proceed, reason = await tracker.can_make_request(max_rpm, max_tpm)

        if not can_proceed:
            wait_seconds = await tracker.wait_until_available(max_rpm, max_tpm)
            return False, reason, wait_seconds

        return True, "", 0.0

    async def register_request(self, request: LLMRequest, response: LLMResponse):
        """
        Register completed request in statistics.

        Args:
            request: LLMRequest
            response: LLMResponse with usage
        """
        tracker = self._trackers.get(request.model)
        if not tracker:
            return

        input_tokens = self.token_counter.count_request_tokens(request)

        if response.usage:
            output_tokens = response.usage.get('output_tokens', response.usage.get('completion_tokens', 0))
            total_tokens = response.usage.get('total_tokens', input_tokens + output_tokens)
        else:
            output_tokens = self.token_counter.estimate_response_tokens()
            total_tokens = input_tokens + output_tokens

        await tracker.add_request(total_tokens)

        self._log_usage(request, input_tokens, output_tokens)

    def _log_usage(self, request: LLMRequest, input_tokens: int, output_tokens: int):
        """Log token usage."""
        if not self.log_dir:
            return

        log_path = Path(self.log_dir) / "gateway" / "rate_limits.jsonl"
        log_path.parent.mkdir(parents=True, exist_ok=True)

        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "model": request.model,
            "agent_id": request.agent_id,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
            "status": "success"
        }

        with open(log_path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + '\n')
