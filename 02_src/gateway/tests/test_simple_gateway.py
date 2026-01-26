"""
Unit tests for SimpleLLMGateway.

Tests cover initialization, request/retry logic, batch processing, and logging.
All tests use mocks to avoid real API calls.
"""
import asyncio
import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

# Mock langchain modules before importing SimpleLLMGateway
sys.modules["langchain_anthropic"] = MagicMock()
sys.modules["langchain_openai"] = MagicMock()

from gateway.models import LLMMessage, LLMRequest, LLMResponse, ModelConfig, ModelProvider
from gateway.simple_llm_gateway import SimpleLLMGateway


@pytest.fixture
def mock_configs():
    """Create mock model configs."""
    return {
        "claude-haiku": ModelConfig(
            provider=ModelProvider.CLAUDE_HAIKU,
            endpoint="https://api.anthropic.com",
            api_key="test-key",
            model_name="claude-3-haiku-20240307",
        ),
        "gpt-4o-mini": ModelConfig(
            provider=ModelProvider.GPT_4O_MINI,
            endpoint="https://api.openai.com",
            api_key="test-key",
            model_name="gpt-4o-mini",
        ),
    }


@pytest.fixture
def mock_llm_response():
    """Create mock LLM response."""
    response = MagicMock()
    response.content = "Test response"
    response.tool_calls = None
    response.usage_metadata = {"input_tokens": 10, "output_tokens": 20}
    return response


@pytest.fixture
def sample_request():
    """Create sample LLM request."""
    return LLMRequest(
        request_id="test-001",
        model="claude-haiku",
        messages=[
            LLMMessage(role="user", content="Hello"),
        ],
        agent_id="test-agent",
    )


class TestSimpleLLMGateway:
    """Test suite for SimpleLLMGateway."""

    def test_init_creates_clients_claude_haiku(self):
        """TC-002: Creates ChatAnthropic client for Claude Haiku."""
        config = ModelConfig(
            provider=ModelProvider.CLAUDE_HAIKU,
            endpoint="https://api.anthropic.com",
            api_key="test-key",
            model_name="claude-3-haiku-20240307",
        )

        gateway = SimpleLLMGateway(configs={"haiku": config})

        # Verify client was created
        assert "haiku" in gateway._clients
        assert gateway._clients["haiku"] is not None

    def test_init_creates_clients_claude_sonnet(self):
        """TC-002: Creates ChatAnthropic client for Claude Sonnet."""
        config = ModelConfig(
            provider=ModelProvider.CLAUDE_SONNET,
            endpoint="https://api.anthropic.com",
            api_key="test-key",
            model_name="claude-3-5-sonnet-20241022",
        )

        gateway = SimpleLLMGateway(configs={"sonnet": config})

        assert "sonnet" in gateway._clients
        assert gateway._clients["sonnet"] is not None

    def test_init_creates_clients_claude_opus(self):
        """TC-002: Creates ChatAnthropic client for Claude Opus."""
        config = ModelConfig(
            provider=ModelProvider.CLAUDE_OPUS,
            endpoint="https://api.anthropic.com",
            api_key="test-key",
            model_name="claude-3-opus-20240229",
        )

        gateway = SimpleLLMGateway(configs={"opus": config})

        assert "opus" in gateway._clients
        assert gateway._clients["opus"] is not None

    def test_init_creates_clients_openai_gpt4o_mini(self):
        """TC-003: Creates ChatOpenAI client for GPT-4o-mini."""
        config = ModelConfig(
            provider=ModelProvider.GPT_4O_MINI,
            endpoint="https://api.openai.com",
            api_key="test-key",
            model_name="gpt-4o-mini",
        )

        gateway = SimpleLLMGateway(configs={"gpt4o-mini": config})

        assert "gpt4o-mini" in gateway._clients
        assert gateway._clients["gpt4o-mini"] is not None

    def test_init_creates_clients_openai_gpt4o(self):
        """TC-003: Creates ChatOpenAI client for GPT-4o."""
        config = ModelConfig(
            provider=ModelProvider.GPT_4O,
            endpoint="https://api.openai.com",
            api_key="test-key",
            model_name="gpt-4o",
        )

        gateway = SimpleLLMGateway(configs={"gpt4o": config})

        assert "gpt4o" in gateway._clients
        assert gateway._clients["gpt4o"] is not None

    def test_init_unsupported_provider_raises_error(self):
        """TC-004: Unsupported provider raises ValueError."""
        config = ModelConfig(
            provider=ModelProvider.LOCAL_LLAMA,
            endpoint="http://localhost:11434",
            api_key="",
            model_name="llama2",
        )

        with pytest.raises(ValueError, match="Unsupported provider"):
            SimpleLLMGateway(configs={"llama": config})

    def test_init_creates_clients(self, mock_configs):
        """Test that __init__ creates langchain clients for all models."""
        gateway = SimpleLLMGateway(configs=mock_configs)

        assert len(gateway._clients) == 2
        assert "claude-haiku" in gateway._clients
        assert "gpt-4o-mini" in gateway._clients

    def test_init_with_log_dir(self, mock_configs, tmp_path):
        """Test initialization with log directory."""
        log_dir = str(tmp_path / "logs")
        gateway = SimpleLLMGateway(configs=mock_configs, log_dir=log_dir)

        assert gateway.log_dir == log_dir

    @pytest.mark.asyncio
    async def test_request_success(self, mock_configs, sample_request, mock_llm_response):
        """Test successful request returns LLMResponse with latency_ms."""
        gateway = SimpleLLMGateway(configs=mock_configs)

        # Mock the langchain client
        client = gateway._clients["claude-haiku"]
        client.ainvoke = AsyncMock(return_value=mock_llm_response)

        response = await gateway.request(sample_request)

        assert isinstance(response, LLMResponse)
        assert response.request_id == "test-001"
        assert response.content == "Test response"
        assert response.latency_ms >= 0
        assert response.usage == {"input_tokens": 10, "output_tokens": 20}

    @pytest.mark.asyncio
    async def test_request_unknown_model(self, mock_configs, sample_request):
        """Test request with unknown model raises ValueError."""
        gateway = SimpleLLMGateway(configs=mock_configs)

        sample_request.model = "unknown-model"

        with pytest.raises(ValueError, match="Unknown model"):
            await gateway.request(sample_request)

    @pytest.mark.asyncio
    async def test_request_timeout_408_retries_with_delay(self, mock_configs, sample_request):
        """TC-003: Timeout 408 triggers 5 retries with 1s delay."""
        gateway = SimpleLLMGateway(configs=mock_configs, log_dir=None)

        client = gateway._clients["claude-haiku"]

        # Create timeout error 408
        timeout_error = Exception("Timeout")
        timeout_error.response = MagicMock()
        timeout_error.response.status_code = 408

        client.ainvoke = AsyncMock(side_effect=timeout_error)

        # Mock asyncio.sleep to avoid waiting and verify delay
        with patch("asyncio.sleep") as mock_sleep:
            with pytest.raises(Exception, match="Timeout"):
                await gateway.request(sample_request)

            # Should attempt 5 times (1 initial + 4 retries)
            assert client.ainvoke.call_count == 5
            # Should call sleep 4 times (between retries)
            assert mock_sleep.call_count == 4
            # Each sleep should be 1.0 seconds
            for call in mock_sleep.call_args_list:
                assert call[0][0] == 1.0

    @pytest.mark.asyncio
    async def test_request_timeout_504_retries_with_delay(self, mock_configs, sample_request):
        """TC-004: Timeout 504 triggers 5 retries with 1s delay."""
        gateway = SimpleLLMGateway(configs=mock_configs, log_dir=None)

        client = gateway._clients["claude-haiku"]

        # Create timeout error 504
        timeout_error = Exception("Timeout")
        timeout_error.response = MagicMock()
        timeout_error.response.status_code = 504

        client.ainvoke = AsyncMock(side_effect=timeout_error)

        # Mock asyncio.sleep to avoid waiting and verify delay
        with patch("asyncio.sleep") as mock_sleep:
            with pytest.raises(Exception, match="Timeout"):
                await gateway.request(sample_request)

            # Should attempt 5 times
            assert client.ainvoke.call_count == 5
            assert mock_sleep.call_count == 4

    @pytest.mark.asyncio
    async def test_request_timeout_retry(self, mock_configs, sample_request):
        """TC-006: Timeout errors trigger retry with delay, then success."""
        gateway = SimpleLLMGateway(configs=mock_configs, log_dir=None)

        # Mock client that fails with timeout error twice, then succeeds
        client = gateway._clients["claude-haiku"]

        # Create timeout error
        timeout_error = Exception("Timeout")
        timeout_error.response = MagicMock()
        timeout_error.response.status_code = 504

        mock_llm_response = MagicMock()
        mock_llm_response.content = "Success after retry"
        mock_llm_response.tool_calls = None
        mock_llm_response.usage_metadata = None

        client.ainvoke = AsyncMock(
            side_effect=[timeout_error, timeout_error, mock_llm_response]
        )

        # Mock asyncio.sleep to verify delay
        with patch("asyncio.sleep") as mock_sleep:
            response = await gateway.request(sample_request)

            assert response.content == "Success after retry"
            assert client.ainvoke.call_count == 3
            # Should call sleep twice (between 3 attempts)
            assert mock_sleep.call_count == 2

    @pytest.mark.asyncio
    async def test_request_max_retries_exceeded(self, mock_configs, sample_request):
        """Test that exceeding max retries raises exception."""
        gateway = SimpleLLMGateway(configs=mock_configs, log_dir=None)

        client = gateway._clients["claude-haiku"]

        # Create timeout error
        timeout_error = Exception("Timeout")
        timeout_error.response = MagicMock()
        timeout_error.response.status_code = 408

        client.ainvoke = AsyncMock(side_effect=timeout_error)

        with pytest.raises(Exception, match="Timeout"):
            await gateway.request(sample_request)

        # Should retry MAX_RETRIES times
        assert client.ainvoke.call_count == gateway.MAX_RETRIES

    @pytest.mark.asyncio
    async def test_request_non_timeout_error_no_retry(self, mock_configs, sample_request):
        """Test that non-timeout errors propagate immediately without retry."""
        gateway = SimpleLLMGateway(configs=mock_configs, log_dir=None)

        client = gateway._clients["claude-haiku"]

        # Create non-timeout error (e.g., authentication error)
        auth_error = Exception("Authentication failed")
        # No response attribute or different status code

        client.ainvoke = AsyncMock(side_effect=auth_error)

        with pytest.raises(Exception, match="Authentication failed"):
            await gateway.request(sample_request)

        # Should NOT retry - called only once
        assert client.ainvoke.call_count == 1

    @pytest.mark.asyncio
    async def test_batch_sequential_execution(self, mock_configs, mock_llm_response):
        """Test that batch executes requests sequentially."""
        gateway = SimpleLLMGateway(configs=mock_configs)

        client = gateway._clients["claude-haiku"]
        client.ainvoke = AsyncMock(return_value=mock_llm_response)

        requests = [
            LLMRequest(
                request_id="test-001",
                model="claude-haiku",
                messages=[LLMMessage(role="user", content="Hello 1")],
            ),
            LLMRequest(
                request_id="test-002",
                model="claude-haiku",
                messages=[LLMMessage(role="user", content="Hello 2")],
            ),
            LLMRequest(
                request_id="test-003",
                model="claude-haiku",
                messages=[LLMMessage(role="user", content="Hello 3")],
            ),
        ]

        responses = await gateway.batch(requests)

        assert len(responses) == 3
        assert all(isinstance(r, LLMResponse) for r in responses)
        assert responses[0].request_id == "test-001"
        assert responses[1].request_id == "test-002"
        assert responses[2].request_id == "test-003"

        # Should be called 3 times (sequential)
        assert client.ainvoke.call_count == 3

    def test_is_timeout_error_408(self):
        """Test _is_timeout_error detects 408 status code."""
        gateway = SimpleLLMGateway(configs={})

        error = Exception("Request timeout")
        error.response = MagicMock()
        error.response.status_code = 408

        assert gateway._is_timeout_error(error) is True

    def test_is_timeout_error_504(self):
        """Test _is_timeout_error detects 504 status code."""
        gateway = SimpleLLMGateway(configs={})

        error = Exception("Gateway timeout")
        error.response = MagicMock()
        error.response.status_code = 504

        assert gateway._is_timeout_error(error) is True

    def test_is_timeout_error_other_status(self):
        """Test _is_timeout_error returns False for other status codes."""
        gateway = SimpleLLMGateway(configs={})

        error = Exception("Internal server error")
        error.response = MagicMock()
        error.response.status_code = 500

        assert gateway._is_timeout_error(error) is False

    def test_is_timeout_error_no_response(self):
        """Test _is_timeout_error returns False when no response attribute."""
        gateway = SimpleLLMGateway(configs={})

        error = Exception("Some error")

        assert gateway._is_timeout_error(error) is False

    def test_extract_tool_calls_with_tools(self):
        """Test _extract_tool_calls extracts tool calls."""
        gateway = SimpleLLMGateway(configs={})

        mock_response = MagicMock()
        mock_response.tool_calls = [{"name": "test_func", "args": {}}]

        result = gateway._extract_tool_calls(mock_response)

        assert result == [{"name": "test_func", "args": {}}]

    def test_extract_tool_calls_without_tools(self):
        """Test _extract_tool_calls returns None when no tool calls."""
        gateway = SimpleLLMGateway(configs={})

        mock_response = MagicMock()
        del mock_response.tool_calls

        result = gateway._extract_tool_calls(mock_response)

        assert result is None

    @pytest.mark.asyncio
    async def test_request_logging(self, mock_configs, sample_request, mock_llm_response, tmp_path):
        """TC-008: Successful request logs to simple_requests.jsonl."""
        log_dir = str(tmp_path / "logs")
        gateway = SimpleLLMGateway(configs=mock_configs, log_dir=log_dir)

        client = gateway._clients["claude-haiku"]
        client.ainvoke = AsyncMock(return_value=mock_llm_response)

        await gateway.request(sample_request)

        # Check log file was created
        log_path = tmp_path / "logs" / "gateway" / "simple_requests.jsonl"
        assert log_path.exists()

        # Check log entry
        with open(log_path, "r", encoding="utf-8") as f:
            log_entry = json.loads(f.read().strip())

        assert log_entry["request_id"] == "test-001"
        assert log_entry["model"] == "claude-haiku"
        assert log_entry["agent_id"] == "test-agent"
        assert log_entry["status"] == "success"
        assert "latency_ms" in log_entry

    @pytest.mark.asyncio
    async def test_request_retry_logging(self, mock_configs, sample_request, tmp_path):
        """TC-009: Retry attempts logged to simple_retries.jsonl."""
        log_dir = str(tmp_path / "logs")
        gateway = SimpleLLMGateway(configs=mock_configs, log_dir=log_dir)

        client = gateway._clients["claude-haiku"]

        # Create timeout error
        timeout_error = Exception("Timeout")
        timeout_error.response = MagicMock()
        timeout_error.response.status_code = 408

        mock_llm_response = MagicMock()
        mock_llm_response.content = "Success after retry"
        mock_llm_response.tool_calls = None
        mock_llm_response.usage_metadata = None

        # Timeout twice, then success
        client.ainvoke = AsyncMock(
            side_effect=[timeout_error, timeout_error, mock_llm_response]
        )

        with patch("asyncio.sleep"):
            await gateway.request(sample_request)

        # Check retry log
        log_path = tmp_path / "logs" / "gateway" / "simple_retries.jsonl"
        assert log_path.exists()

        with open(log_path, "r", encoding="utf-8") as f:
            logs = [json.loads(line) for line in f]

        # Should have 2 retry logs
        assert len(logs) == 2
        assert logs[0]["request_id"] == "test-001"
        assert logs[0]["attempt"] == 0
        assert logs[0]["status"] == "retry"
        assert logs[1]["attempt"] == 1

    @pytest.mark.asyncio
    async def test_request_max_retries_logging(self, mock_configs, sample_request, tmp_path):
        """TC-010: Max retries exceeded logged to simple_errors.jsonl."""
        log_dir = str(tmp_path / "logs")
        gateway = SimpleLLMGateway(configs=mock_configs, log_dir=log_dir)

        client = gateway._clients["claude-haiku"]

        # Create timeout error
        timeout_error = Exception("Timeout")
        timeout_error.response = MagicMock()
        timeout_error.response.status_code = 408

        client.ainvoke = AsyncMock(side_effect=timeout_error)

        with patch("asyncio.sleep"):
            with pytest.raises(Exception, match="Timeout"):
                await gateway.request(sample_request)

        # Check error log
        log_path = tmp_path / "logs" / "gateway" / "simple_errors.jsonl"
        assert log_path.exists()

        with open(log_path, "r", encoding="utf-8") as f:
            log_entry = json.loads(f.read().strip())

        assert log_entry["request_id"] == "test-001"
        assert log_entry["status"] == "max_retries_exceeded"
        assert log_entry["max_retries"] == 5
        assert "error" in log_entry

    @pytest.mark.asyncio
    async def test_request_non_timeout_error_logging(self, mock_configs, sample_request, tmp_path):
        """TC-016: Non-timeout error logged to simple_errors.jsonl."""
        log_dir = str(tmp_path / "logs")
        gateway = SimpleLLMGateway(configs=mock_configs, log_dir=log_dir)

        client = gateway._clients["claude-haiku"]

        # Create non-timeout error
        auth_error = Exception("Authentication failed")

        client.ainvoke = AsyncMock(side_effect=auth_error)

        with pytest.raises(Exception, match="Authentication failed"):
            await gateway.request(sample_request)

        # Check error log
        log_path = tmp_path / "logs" / "gateway" / "simple_errors.jsonl"
        assert log_path.exists()

        with open(log_path, "r", encoding="utf-8") as f:
            log_entry = json.loads(f.read().strip())

        assert log_entry["request_id"] == "test-001"
        assert log_entry["status"] == "error"
        assert log_entry["error"] == "Authentication failed"

    @pytest.mark.asyncio
    async def test_log_format_has_all_fields(self, mock_configs, sample_request, mock_llm_response, tmp_path):
        """TC-017: Log entries have all required fields."""
        log_dir = str(tmp_path / "logs")
        gateway = SimpleLLMGateway(configs=mock_configs, log_dir=log_dir)

        client = gateway._clients["claude-haiku"]
        client.ainvoke = AsyncMock(return_value=mock_llm_response)

        await gateway.request(sample_request)

        # Check log format
        log_path = tmp_path / "logs" / "gateway" / "simple_requests.jsonl"
        with open(log_path, "r", encoding="utf-8") as f:
            log_entry = json.loads(f.read().strip())

        # Check all required fields
        required_fields = ["timestamp", "model", "request_id", "agent_id", "attempt", "latency_ms", "status"]
        for field in required_fields:
            assert field in log_entry, f"Missing field: {field}"

        # Check types
        assert isinstance(log_entry["attempt"], int)
        assert isinstance(log_entry["latency_ms"], int)
        assert log_entry["status"] == "success"


class TestSimpleLLMGatewayIntegration:
    """Integration tests for SimpleLLMGateway."""

    @pytest.mark.asyncio
    async def test_full_request_response_flow(self, tmp_path):
        """TC-018: Full cycle request-response with logging."""
        config = ModelConfig(
            provider=ModelProvider.CLAUDE_HAIKU,
            endpoint="https://api.anthropic.com",
            api_key="test-key",
            model_name="claude-3-haiku-20240307",
        )

        log_dir = str(tmp_path / "logs")
        gateway = SimpleLLMGateway(configs={"test-model": config}, log_dir=log_dir)

        # Mock client
        mock_client = gateway._clients["test-model"]
        mock_response = MagicMock()
        mock_response.content = "Integration test response"
        mock_response.tool_calls = None
        mock_response.usage_metadata = {"input_tokens": 10, "output_tokens": 20}

        mock_client.ainvoke = AsyncMock(return_value=mock_response)

        # Make request
        request = LLMRequest(
            request_id="integration-test",
            model="test-model",
            agent_id="test-agent",
            messages=[
                LLMMessage(role="system", content="You are helpful"),
                LLMMessage(role="user", content="Hello"),
            ],
        )

        response = await gateway.request(request)

        # Verify response
        assert response.request_id == "integration-test"
        assert response.content == "Integration test response"
        assert response.latency_ms >= 0

        # Verify log
        log_path = Path(log_dir) / "gateway" / "simple_requests.jsonl"
        assert log_path.exists()

        with open(log_path, "r", encoding="utf-8") as f:
            log_entry = json.loads(f.read().strip())

        assert log_entry["request_id"] == "integration-test"
        assert log_entry["status"] == "success"

    @pytest.mark.asyncio
    async def test_multiple_retries_then_success(self, tmp_path):
        """TC-019: Multiple retries followed by success."""
        config = ModelConfig(
            provider=ModelProvider.CLAUDE_HAIKU,
            endpoint="https://api.anthropic.com",
            api_key="test-key",
            model_name="claude-3-haiku-20240307",
        )

        log_dir = str(tmp_path / "logs")
        gateway = SimpleLLMGateway(configs={"test-model": config}, log_dir=log_dir)

        # Mock client
        mock_client = gateway._clients["test-model"]

        # Create timeout error
        timeout_error = Exception("Timeout")
        timeout_error.response = MagicMock()
        timeout_error.response.status_code = 408

        # Mock: 3 timeouts, then success
        mock_success_response = MagicMock()
        mock_success_response.content = "Success after retries"
        mock_success_response.tool_calls = None
        mock_success_response.usage_metadata = None

        mock_client.ainvoke = AsyncMock(
            side_effect=[timeout_error, timeout_error, timeout_error, mock_success_response]
        )

        request = LLMRequest(
            request_id="test-1",
            model="test-model",
            messages=[LLMMessage(role="user", content="Hello")],
        )

        with patch("asyncio.sleep"):
            response = await gateway.request(request)

            # Verify success after retries
            assert response.content == "Success after retries"
            assert mock_client.ainvoke.call_count == 4

            # Check retry logs
            log_path = Path(log_dir) / "gateway" / "simple_retries.jsonl"
            with open(log_path, "r", encoding="utf-8") as f:
                logs = [json.loads(line) for line in f]

            # Should have 3 retry logs
            assert len(logs) == 3
            assert logs[0]["attempt"] == 0
            assert logs[1]["attempt"] == 1
            assert logs[2]["attempt"] == 2

            # Check success log
            success_log_path = Path(log_dir) / "gateway" / "simple_requests.jsonl"
            with open(success_log_path, "r", encoding="utf-8") as f:
                success_log = json.loads(f.read().strip())

            assert success_log["request_id"] == "test-1"
            assert success_log["status"] == "success"
            assert success_log["attempt"] == 3
