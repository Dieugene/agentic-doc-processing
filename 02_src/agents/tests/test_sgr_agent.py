"""
Unit tests for SystemSGRAgent.

Tests the base SGR agent functionality with mock gateway.
"""
import asyncio
import json
from pathlib import Path
from typing import Dict, List
from unittest.mock import AsyncMock, MagicMock

import pytest

from gateway.models import (
    LLMMessage,
    LLMRequest,
    LLMResponse,
    ModelConfig,
    ModelProvider,
)
from gateway.tests.mock_gateway import MockLLMGateway
from agents.sgr_agent import SystemSGRAgent
from agents.tools import SGRTool


class DummyTool(SGRTool):
    """Dummy tool for testing."""

    name = "dummy_tool"
    description = "A dummy test tool"
    parameters_schema = {
        "type": "object",
        "properties": {
            "value": {"type": "string"}
        },
        "required": ["value"]
    }

    def __init__(self, return_value="test_result"):
        self.return_value = return_value
        self.call_count = 0
        self.last_params = None

    async def execute(self, **kwargs) -> str:
        self.call_count += 1
        self.last_params = kwargs
        return self.return_value


class TestSGRAgent(SystemSGRAgent):
    """Test implementation of SystemSGRAgent."""

    async def process(self, input_data: Dict) -> Dict:
        """Simple process implementation."""
        text = input_data.get("text", "")
        response = await self.run(
            user_message=f"Process: {text}",
            context=input_data
        )
        return {"result": response}


class TestSystemSGRAgent:
    """Tests for SystemSGRAgent base class."""

    @pytest.fixture
    def mock_configs(self):
        """Mock model configs."""
        return {
            "test_model": ModelConfig(
                provider=ModelProvider.CLAUDE_HAIKU,
                endpoint="https://api.anthropic.com",
                api_key="test_key",
                model_name="claude-3-haiku-20240307"
            )
        }

    @pytest.fixture
    def mock_gateway(self, mock_configs):
        """Mock LLM gateway."""
        return MockLLMGateway(configs=mock_configs)

    @pytest.fixture
    def temp_log_dir(self, tmp_path):
        """Temporary log directory."""
        return str(tmp_path / "logs")

    @pytest.fixture
    def test_agent(self, mock_gateway, temp_log_dir):
        """Create test agent."""
        return TestSGRAgent(
            agent_id="test_agent",
            llm_gateway=mock_gateway,
            model="test_model",
            system_prompt="You are a helpful assistant.",
            log_dir=temp_log_dir
        )

    @pytest.mark.asyncio
    async def test_agent_init(self, mock_gateway, temp_log_dir):
        """Test agent initialization."""
        agent = TestSGRAgent(
            agent_id="test_agent",
            llm_gateway=mock_gateway,
            model="test_model",
            system_prompt="Test prompt",
            tools=[],
            log_dir=temp_log_dir
        )

        assert agent.agent_id == "test_agent"
        assert agent.model == "test_model"
        assert agent.system_prompt == "Test prompt"
        assert agent.tools == []
        assert agent.log_dir == temp_log_dir
        assert agent._reasoning_trace == []

    @pytest.mark.asyncio
    async def test_run_without_tools(self, test_agent):
        """Test agent run without tools."""
        response = await test_agent.run("Hello!")

        assert response == "Mock response for test_agent_iter_0"

    @pytest.mark.asyncio
    async def test_run_with_tools(self, mock_configs, temp_log_dir):
        """Test agent run with tools."""
        # Create mock gateway that returns tool call
        mock_gateway = MockLLMGateway(configs=mock_configs)

        # Create agent with tool
        dummy_tool = DummyTool(return_value="tool_result")
        agent = TestSGRAgent(
            agent_id="test_agent",
            llm_gateway=mock_gateway,
            model="test_model",
            system_prompt="You have tools.",
            tools=[dummy_tool],
            log_dir=temp_log_dir
        )

        # Mock the gateway request to simulate tool call
        original_request = mock_gateway.request

        async def mock_request_with_tool_call(request: LLMRequest) -> LLMResponse:
            # First call returns tool call
            if request.request_id == "test_agent_iter_0":
                return LLMResponse(
                    request_id=request.request_id,
                    content="",
                    tool_calls=[
                        {
                            "name": "dummy_tool",
                            "arguments": json.dumps({"value": "test"}),
                            "id": "call_123"
                        }
                    ]
                )
            # Second call returns final answer
            else:
                return LLMResponse(
                    request_id=request.request_id,
                    content="Used tool result",
                    tool_calls=None
                )

        mock_gateway.request = mock_request_with_tool_call

        # Run agent
        response = await agent.run("Use the tool")

        # Verify tool was called
        assert dummy_tool.call_count == 1
        assert dummy_tool.last_params == {"value": "test"}
        assert response == "Used tool result"

    @pytest.mark.asyncio
    async def test_reasoning_trace_logging(self, test_agent, temp_log_dir):
        """Test that reasoning trace is logged correctly."""
        await test_agent.run("Test message")

        # Check log file was created
        log_path = Path(temp_log_dir) / "reasoning" / "test_agent.jsonl"
        assert log_path.exists()

        # Read and verify log content
        with open(log_path, "r", encoding="utf-8") as f:
            log_entry = json.loads(f.readline().strip())

        assert log_entry["agent_id"] == "test_agent"
        assert "timestamp" in log_entry
        assert "reasoning_trace" in log_entry
        assert len(log_entry["reasoning_trace"]) >= 2  # think + formulate_answer

        # Verify trace structure
        trace = log_entry["reasoning_trace"]
        assert trace[0]["action"] == "think"
        assert trace[-1]["action"] == "formulate_answer"

    @pytest.mark.asyncio
    async def test_process_method(self, test_agent):
        """Test the abstract process method."""
        result = await test_agent.process({"text": "test input"})

        assert "result" in result
        assert result["result"] == "Mock response for test_agent_iter_0"

    @pytest.mark.asyncio
    async def test_max_iterations(self, mock_configs, temp_log_dir):
        """Test that agent stops after max iterations."""
        mock_gateway = MockLLMGateway(configs=mock_configs)

        # Create agent
        agent = TestSGRAgent(
            agent_id="test_agent",
            llm_gateway=mock_gateway,
            model="test_model",
            system_prompt="Test prompt",
            log_dir=temp_log_dir
        )

        # Mock gateway to always return tool calls (infinite loop scenario)
        async def mock_request_infinite_tool_calls(request: LLMRequest) -> LLMResponse:
            return LLMResponse(
                request_id=request.request_id,
                content="",
                tool_calls=[
                    {
                        "name": "dummy_tool",
                        "arguments": "{}",
                        "id": "call_123"
                    }
                ]
            )

        mock_gateway.request = mock_request_infinite_tool_calls

        # Run agent - should stop after max iterations
        response = await agent.run("Infinite loop test")

        assert response == "Error: Maximum iterations exceeded"

    @pytest.mark.asyncio
    async def test_no_logging_when_log_dir_none(self, mock_gateway):
        """Test that no error occurs when log_dir is None."""
        agent = TestSGRAgent(
            agent_id="test_agent",
            llm_gateway=mock_gateway,
            model="test_model",
            system_prompt="Test prompt",
            log_dir=None
        )

        # Should not raise error
        response = await agent.run("Test without logging")
        assert response == "Mock response for test_agent_iter_0"

    @pytest.mark.asyncio
    async def test_tool_error_handling(self, mock_configs, temp_log_dir):
        """Test that tool errors are handled gracefully."""
        mock_gateway = MockLLMGateway(configs=mock_configs)

        # Create tool that raises error
        class ErrorTool(SGRTool):
            name = "error_tool"
            description = "Tool that raises error"
            parameters_schema = {"type": "object", "properties": {}}

            async def execute(self, **kwargs):
                raise ValueError("Tool execution failed")

        error_tool = ErrorTool()

        agent = TestSGRAgent(
            agent_id="test_agent",
            llm_gateway=mock_gateway,
            model="test_model",
            system_prompt="Test prompt",
            tools=[error_tool],
            log_dir=temp_log_dir
        )

        # Mock gateway to call tool then return final answer
        call_count = [0]

        async def mock_request(request: LLMRequest) -> LLMResponse:
            call_count[0] += 1
            if call_count[0] == 1:
                return LLMResponse(
                    request_id=request.request_id,
                    content="",
                    tool_calls=[
                        {
                            "name": "error_tool",
                            "arguments": "{}",
                            "id": "call_123"
                        }
                    ]
                )
            else:
                return LLMResponse(
                    request_id=request.request_id,
                    content="Acknowledged error",
                    tool_calls=None
                )

        mock_gateway.request = mock_request

        # Should not raise error
        response = await agent.run("Test error handling")
        assert response == "Acknowledged error"

        # Verify trace contains error
        log_path = Path(temp_log_dir) / "reasoning" / "test_agent.jsonl"
        with open(log_path, "r", encoding="utf-8") as f:
            log_entry = json.loads(f.readline().strip())

        trace = log_entry["reasoning_trace"]
        # Find call_tool step with error
        error_step = next((s for s in trace if s["action"] == "call_tool" and "Error" in str(s["tool_result"])), None)
        assert error_step is not None
