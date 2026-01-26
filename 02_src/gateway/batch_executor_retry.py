"""
Batch Executor with Retry for LLM Gateway.

Extends BatchExecutor with retry logic for temporary API errors.
"""
import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

from .llm_gateway import BatchExecutor
from .models import ModelConfig
from .retry_policy import RetryPolicy


class BatchExecutorWithRetry(BatchExecutor):
    """
    BatchExecutor with retry mechanism.

    Extends BatchExecutor from task 001 with retry logic.
    """

    def __init__(
        self,
        model_config: ModelConfig,
        retry_policy: RetryPolicy,
        log_dir: Optional[str] = None,
    ):
        super().__init__(model_config, log_dir)
        self.retry_policy = retry_policy

    async def execute_batch(
        self,
        batch: List[Tuple["LLMRequest", "asyncio.Future[LLMResponse]"]],
    ) -> None:
        """
        Send batch of requests with retry.

        On error:
        1. Check should_retry()
        2. Wait get_delay()
        3. Retry attempt
        4. After max_retries — complete futures with error

        Args:
            batch: List of (request, future) pairs
        """
        if not batch:
            return

        for attempt in range(self.retry_policy.max_retries + 1):
            try:
                # First attempt or retry
                await super().execute_batch(batch)
                return  # Success

            except asyncio.CancelledError:
                # Task was cancelled - exit immediately
                raise

            except Exception as e:
                # Check if should retry
                if (
                    attempt < self.retry_policy.max_retries
                    and self.retry_policy.should_retry(e, attempt)
                ):
                    # Log retry
                    self._log_retry(batch, attempt, e)

                    # Wait with backoff
                    delay = self.retry_policy.get_delay(attempt)
                    await asyncio.sleep(delay)

                    # Next attempt
                    continue
                else:
                    # Don't retry or last attempt failed
                    for _, future in batch:
                        if not future.done():
                            future.set_exception(e)

                    self._log_error(batch, e)
                    return

    def _log_retry(
        self, batch: List[Tuple], attempt: int, error: Exception
    ):
        """
        Log retry attempt.

        Args:
            batch: Batch of requests
            attempt: Attempt number
            error: Exception that caused retry
        """
        if not self.log_dir:
            return

        log_path = Path(self.log_dir) / "gateway" / "retries.jsonl"
        log_path.parent.mkdir(parents=True, exist_ok=True)

        request_ids = [req.request_id for req, _ in batch]

        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "model": self.config.model_name,
            "attempt": attempt,
            "request_ids": request_ids,
            "error": str(error),
            "delay_ms": self.retry_policy.get_delay(attempt) * 1000,
            "status": "retry",
        }

        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
