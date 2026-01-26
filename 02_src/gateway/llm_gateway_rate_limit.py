"""
LLM Gateway with Rate Limit.

Extends LLMGateway with rate limit control.
"""
from typing import Dict, Optional

from .llm_gateway import LLMGateway
from .models import ModelConfig
from .rate_limiter import RateLimiter
from .retry_policy import RetryPolicy
from .batch_executor_rate_limit import BatchExecutorWithRateLimit


class LLMGatewayWithRateLimit(LLMGateway):
    """
    LLMGateway with rate limit control.
    """

    def __init__(
        self,
        configs: Dict[str, ModelConfig],
        retry_policy: RetryPolicy,
        log_dir: Optional[str] = None,
    ):
        """
        Args:
            configs: Dict {model_id: ModelConfig}
            retry_policy: Retry policy for API errors
            log_dir: Directory for logs
        """
        super().__init__(configs, log_dir)
        self.retry_policy = retry_policy
        self.rate_limiter = RateLimiter(configs, log_dir)

        # Replace executors with rate limit versions
        self._executors = {}
        for model_id, config in configs.items():
            self._executors[model_id] = BatchExecutorWithRateLimit(
                config, retry_policy, self.rate_limiter, log_dir
            )
