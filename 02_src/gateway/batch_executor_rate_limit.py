"""
Batch Executor with Rate Limit for LLM Gateway.

Extends BatchExecutorWithRetry with rate limit checking.
"""
import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

from .batch_executor_retry import BatchExecutorWithRetry
from .models import LLMRequest, LLMResponse, ModelConfig
from .rate_limiter import RateLimiter


class BatchExecutorWithRateLimit(BatchExecutorWithRetry):
    """
    BatchExecutor with rate limit checking.

    Checks rate limits before sending batch.
    """

    def __init__(
        self,
        model_config: ModelConfig,
        retry_policy,
        rate_limiter: RateLimiter,
        log_dir: Optional[str] = None,
    ):
        """
        Args:
            model_config: Model configuration
            retry_policy: Retry policy for API errors
            rate_limiter: Rate limiter instance
            log_dir: Directory for logs
        """
        super().__init__(model_config, retry_policy, log_dir)
        self.rate_limiter = rate_limiter

    async def execute_batch(
        self,
        batch: List[Tuple[LLMRequest, "asyncio.Future[LLMResponse]"]],
    ) -> None:
        """
        Send batch with rate limit checking.

        1. Check rate limits for each request
        2. If exceeded — wait or return error
        3. Send batch
        """
        if not batch:
            return

        # Check rate limits
        for request, _ in batch:
            can_proceed, reason, wait_seconds = await self.rate_limiter.check_request(request)

            if not can_proceed:
                self._log_rate_limit(request, reason, wait_seconds)

                if wait_seconds > 0:
                    await asyncio.sleep(wait_seconds)
                else:
                    # Cannot send — return error
                    for _, future in batch:
                        if not future.done():
                            future.set_exception(Exception(f"Rate limit exceeded: {reason}"))
                    return

        # Send batch
        await super().execute_batch(batch)

    def _log_rate_limit(self, request: LLMRequest, reason: str, wait_seconds: float):
        """Log rate limit exceed."""
        if not self.log_dir:
            return

        log_path = Path(self.log_dir) / "gateway" / "rate_limits.jsonl"
        log_path.parent.mkdir(parents=True, exist_ok=True)

        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "model": request.model,
            "request_id": request.request_id,
            "agent_id": request.agent_id,
            "reason": reason,
            "wait_seconds": wait_seconds,
            "status": "rate_limited"
        }

        with open(log_path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + '\n')
