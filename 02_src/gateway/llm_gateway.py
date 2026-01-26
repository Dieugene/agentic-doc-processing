"""
LLM Gateway implementation.

Provides centralized access to LLM models with batching optimization.
"""
import asyncio
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import AsyncIterator, Dict, List, Optional, Tuple

from .models import (
    LLMMessage,
    LLMRequest,
    LLMResponse,
    ModelConfig,
    ModelProvider,
)


class RequestQueue:
    """
    Request queue for a specific model.

    Each model has its own queue for independent batching.
    """

    def __init__(self, model: str, batch_size: int, batch_timeout_ms: int):
        self.model = model
        self.batch_size = batch_size
        self.batch_timeout_ms = batch_timeout_ms
        self._queue: asyncio.Queue = asyncio.Queue()
        self._pending_batches: List["asyncio.Future[LLMResponse]"] = []

    async def put(self, request: LLMRequest) -> "asyncio.Future[LLMResponse]":
        """
        Add request to queue.

        Returns:
            Future for getting the result
        """
        future = asyncio.Future()
        await self._queue.put((request, future))
        return future

    async def get_batch(
        self,
    ) -> List[Tuple[LLMRequest, "asyncio.Future[LLMResponse]"]]:
        """
        Get batch of requests for processing.

        Accumulates requests until batch_size or batch_timeout is reached.
        """
        requests: List[Tuple[LLMRequest, "asyncio.Future[LLMResponse]"]] = []
        deadline = datetime.now() + timedelta(milliseconds=self.batch_timeout_ms)

        # Accumulate first request (blocks if queue is empty)
        first = await self._queue.get()
        requests.append(first)

        # Accumulate rest with timeout
        while len(requests) < self.batch_size:
            try:
                timeout = (deadline - datetime.now()).total_seconds()
                if timeout <= 0:
                    break

                req = await asyncio.wait_for(self._queue.get(), timeout=timeout)
                requests.append(req)
            except asyncio.TimeoutError:
                break

        return requests


class BatchExecutor:
    """
    Batch executor for LLM requests.

    Gets batches from RequestQueue and sends to API.
    """

    def __init__(self, model_config: ModelConfig, log_dir: Optional[str] = None):
        self.config = model_config
        self.log_dir = log_dir
        self._client = self._create_client()
        self._active_batches = 0

    def _create_client(self):
        """
        Create Langchain client for the model.

        Uses langchain for unified access.
        """
        # Import here to avoid circular deps
        from langchain_anthropic import ChatAnthropic
        from langchain_openai import ChatOpenAI

        provider = self.config.provider

        if provider in [ModelProvider.CLAUDE_HAIKU, ModelProvider.CLAUDE_SONNET, ModelProvider.CLAUDE_OPUS]:
            return ChatAnthropic(
                model=self.config.model_name,
                api_key=self.config.api_key,
                temperature=0.0,
            )
        elif provider in [ModelProvider.GPT_4O_MINI, ModelProvider.GPT_4O]:
            return ChatOpenAI(
                model=self.config.model_name,
                api_key=self.config.api_key,
                temperature=0.0,
            )
        else:
            raise ValueError(f"Unsupported provider: {provider}")

    async def execute_batch(
        self,
        batch: List[Tuple[LLMRequest, "asyncio.Future[LLMResponse]"]],
    ) -> None:
        """
        Send batch of requests to API.

        Args:
            batch: List of (request, future) pairs

        Handles:
        - Converting LLMRequest → langchain format
        - Sending via langchain .abatch()
        - Distributing results to futures
        - Logging
        """
        if not batch:
            return

        requests = [req for req, _ in batch]
        futures = [fut for _, fut in batch]

        start_time = datetime.now()

        try:
            # Convert to langchain format
            lc_messages = [
                [(msg.role, msg.content) for msg in req.messages]
                for req in requests
            ]

            # Send batch via langchain
            responses = await self._client.abatch(lc_messages)

            # Distribute results
            for req, fut, resp in zip(requests, futures, responses):
                llm_resp = LLMResponse(
                    request_id=req.request_id,
                    content=resp.content,
                    usage=getattr(resp, "usage_metadata", None),
                    latency_ms=int((datetime.now() - start_time).total_seconds() * 1000),
                )
                if not fut.done():
                    fut.set_result(llm_resp)

            # Log success
            self._log_batch(requests, responses, start_time)

        except Exception as e:
            # On error — all futures complete with exception
            for fut in futures:
                if not fut.done():
                    fut.set_exception(e)

            self._log_error(requests, e)

    def _log_batch(
        self, requests: List[LLMRequest], responses: List, start_time: datetime
    ):
        """Log successful batch."""
        if not self.log_dir:
            return

        log_path = Path(self.log_dir) / "gateway" / "batches.jsonl"
        log_path.parent.mkdir(parents=True, exist_ok=True)

        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "model": self.config.model_name,
            "batch_size": len(requests),
            "request_ids": [r.request_id for r in requests],
            "latency_ms": int((datetime.now() - start_time).total_seconds() * 1000),
            "status": "success",
        }

        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")

    def _log_error(self, requests: List[LLMRequest], error: Exception):
        """Log batch error."""
        if not self.log_dir:
            return

        log_path = Path(self.log_dir) / "gateway" / "errors.jsonl"
        log_path.parent.mkdir(parents=True, exist_ok=True)

        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "model": self.config.model_name,
            "request_ids": [r.request_id for r in requests],
            "error": str(error),
            "status": "error",
        }

        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")


class LLMGateway:
    """
    Centralized access to LLM via Langchain.

    Architecture:
    1. request() adds request to model queue
    2. BatchExecutor takes batches and sends to API
    3. Results distributed via futures
    """

    def __init__(self, configs: Dict[str, ModelConfig], log_dir: Optional[str] = None):
        """
        Args:
            configs: Dict {model_id: ModelConfig}
            log_dir: Directory for logs
        """
        self.log_dir = log_dir
        self.configs = configs

        # Create queues and executors for each model
        self._queues: Dict[str, RequestQueue] = {}
        self._executors: Dict[str, BatchExecutor] = {}

        for model_id, config in configs.items():
            self._queues[model_id] = RequestQueue(
                model=model_id,
                batch_size=config.batch_size,
                batch_timeout_ms=config.batch_timeout_ms,
            )
            self._executors[model_id] = BatchExecutor(config, log_dir)

        # Background tasks for queue processing
        self._worker_tasks: List[asyncio.Task] = []

    async def start(self):
        """Start background queue processors."""
        for model_id, queue in self._queues.items():
            executor = self._executors[model_id]
            task = asyncio.create_task(self._process_queue(model_id, queue, executor))
            self._worker_tasks.append(task)

    async def stop(self):
        """Stop queue processors."""
        for task in self._worker_tasks:
            task.cancel()
        await asyncio.gather(*self._worker_tasks, return_exceptions=True)

    async def _process_queue(
        self, model_id: str, queue: RequestQueue, executor: BatchExecutor
    ):
        """Background task for queue processing."""
        while True:
            try:
                batch = await queue.get_batch()
                await executor.execute_batch(batch)
            except asyncio.CancelledError:
                break
            except Exception as e:
                # Log and continue
                print(f"Error processing queue {model_id}: {e}")

    async def request(self, request: LLMRequest) -> LLMResponse:
        """
        Send request to LLM.

        Args:
            request: LLMRequest

        Returns:
            LLMResponse

        Method returns Future — can wait for result or continue work.
        """
        queue = self._queues.get(request.model)
        if not queue:
            raise ValueError(f"Unknown model: {request.model}")

        future = await queue.put(request)
        return await future

    async def batch(self, requests: List[LLMRequest]) -> List[LLMResponse]:
        """
        Send batch of requests.

        Args:
            requests: List of LLMRequest

        Returns:
            List of LLMResponse
        """
        # Group by models
        by_model: Dict[str, List[LLMRequest]] = {}
        for req in requests:
            by_model.setdefault(req.model, []).append(req)

        # Send to each model
        results = []
        for model_id, model_requests in by_model.items():
            model_results = await asyncio.gather(
                *[self.request(req) for req in model_requests]
            )
            results.extend(model_results)

        return results
