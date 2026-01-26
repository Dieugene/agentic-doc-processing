"""
Unit tests for ResponseRouter.
"""
import asyncio

import pytest

from gateway.response_router import ResponseRouter
from gateway.models import LLMRequest, LLMResponse, LLMMessage


class TestResponseRouter:
    """Test suite for ResponseRouter."""

    @pytest.fixture
    def router(self):
        """Create a ResponseRouter instance."""
        return ResponseRouter(log_dir=None)

    @pytest.fixture
    def sample_request(self):
        """Create a sample LLMRequest."""
        return LLMRequest(
            request_id="test-req-1",
            model="claude-haiku",
            messages=[LLMMessage(role="user", content="Hello")],
            agent_id="test-agent",
        )

    @pytest.fixture
    def sample_response(self):
        """Create a sample LLMResponse."""
        return LLMResponse(
            request_id="test-req-1",
            content="Hi there!",
            latency_ms=100,
        )

    def test_register_saves_request_and_future(self, router, sample_request):
        """TC-004: register saves request and future."""
        future = asyncio.Future()

        router.register(sample_request, future)

        assert sample_request.request_id in router._pending_requests
        assert router._pending_requests[sample_request.request_id] == sample_request
        assert sample_request.request_id in router._pending_futures
        assert router._pending_futures[sample_request.request_id] == future

    def test_resolve_sets_future_result(self, router, sample_request, sample_response):
        """TC-005: resolve correctly resolves future."""
        future = asyncio.Future()
        router.register(sample_request, future)

        router.resolve(sample_response)

        assert future.done()
        assert future.result() == sample_response

    def test_resolve_removes_from_registers(self, router, sample_request, sample_response):
        """TC-005: resolve removes request from registers."""
        future = asyncio.Future()
        router.register(sample_request, future)

        router.resolve(sample_response)

        assert sample_request.request_id not in router._pending_requests
        assert sample_request.request_id not in router._pending_futures

    def test_resolve_error_sets_exception(self, router, sample_request):
        """TC-006: resolve_error correctly completes future with exception."""
        future = asyncio.Future()
        router.register(sample_request, future)

        test_error = ValueError("Test error")
        router.resolve_error(sample_request.request_id, test_error)

        assert future.done()
        with pytest.raises(ValueError, match="Test error"):
            future.result()

    def test_resolve_error_removes_from_registers(self, router, sample_request):
        """TC-006: resolve_error removes request from registers."""
        future = asyncio.Future()
        router.register(sample_request, future)

        test_error = ValueError("Test error")
        router.resolve_error(sample_request.request_id, test_error)

        assert sample_request.request_id not in router._pending_requests
        assert sample_request.request_id not in router._pending_futures

    def test_resolve_with_unknown_request_id_warns(self, router, sample_response, capsys):
        """TC-005: resolve warns when future not found."""
        router.resolve(sample_response)

        captured = capsys.readouterr()
        assert "Warning: No future for request_id" in captured.out

    def test_resolve_error_with_unknown_request_id_warns(self, router, capsys):
        """TC-006: resolve_error warns when future not found."""
        router.resolve_error("unknown-id", ValueError("Test"))

        captured = capsys.readouterr()
        assert "Warning: No future for request_id" in captured.out

    def test_resolve_skips_if_future_already_done(self, router, sample_request, sample_response):
        """TC-005: resolve skips if future is already done."""
        future = asyncio.Future()
        future.set_result(LLMResponse(request_id="test", content="early"))
        router.register(sample_request, future)

        # Should not raise InvalidStateError
        router.resolve(sample_response)

        # Future should keep original result
        assert future.result().content == "early"

    def test_resolve_error_skips_if_future_already_done(self, router, sample_request):
        """TC-006: resolve_error skips if future is already done."""
        future = asyncio.Future()
        future.set_result(LLMResponse(request_id="test", content="early"))
        router.register(sample_request, future)

        # Should not raise InvalidStateError
        router.resolve_error(sample_request.request_id, ValueError("Test"))

        # Future should keep original result
        assert future.result().content == "early"
