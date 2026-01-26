"""
LLM Gateway with Retry and Response Router.

Extends LLMGateway with retry mechanism and response routing.
"""
from typing import Dict, Optional

from .llm_gateway import LLMGateway
from .models import ModelConfig
from .response_router import ResponseRouter
from .retry_policy import RetryPolicy
from .batch_executor_retry import BatchExecutorWithRetry


class LLMGatewayWithRetry(LLMGateway):
    """
    LLMGateway with retry and ResponseRouter.
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
        # Initialize parent without executors (we'll create our own)
        super().__init__(configs, log_dir)
        self.retry_policy = retry_policy
        self.router = ResponseRouter(log_dir)

        # Replace executors with retry versions
        self._executors = {}
        for model_id, config in configs.items():
            self._executors[model_id] = BatchExecutorWithRetry(
                config, retry_policy, log_dir
            )
