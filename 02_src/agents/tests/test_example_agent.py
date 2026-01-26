"""
Unit tests for ExampleSGRAgent.

Tests the example agent implementation.
"""
import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from gateway.models import (
    LLMMessage,
    LLMRequest,
    LLMResponse,
    ModelConfig,
    ModelProvider,
)
from gateway.tests.mock_gateway import MockLLMGateway
from agents.example_agent import ExampleSGRAgent, GetTimeTool


class TestGetTimeTool:
    """Tests for GetTimeTool."""

    @pytest.mark.asyncio
    async def test_get_time_tool(self):
        """Test GetTimeTool execution."""
        tool = GetTimeTool()

        result = await tool.execute()

        assert isinstance(result, str)
        # Should be ISO format timestamp
        assert "T" in result or "-" in result

    def test_tool_metadata(self):
        """Test tool metadata."""
        tool = GetTimeTool()

        assert tool.name == "get_current_time"
        assert tool.description == "Получить текущее время и дату"
        assert tool.parameters_schema == {
            "type": "object",
            "properties": {},
            "required": []
        }


class TestExampleSGRAgent:
    """Tests for ExampleSGRAgent."""

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
    def example_agent(self, mock_gateway, temp_log_dir):
        """Create example agent."""
        return ExampleSGRAgent(
            agent_id="example_agent",
            llm_gateway=mock_gateway,
            model="test_model",
            log_dir=temp_log_dir
        )

    def test_agent_initialization(self, example_agent):
        """Test agent initialization."""
        assert example_agent.agent_id == "example_agent"
        assert example_agent.model == "test_model"
        assert len(example_agent.tools) == 1
        assert isinstance(example_agent.tools[0], GetTimeTool)
        assert "полезный AI-ассистент" in example_agent.system_prompt

    @pytest.mark.asyncio
    async def test_process_method(self, example_agent):
        """Test the process method."""
        input_data = {"text": "Test text for analysis"}

        result = await example_agent.process(input_data)

        assert "analysis" in result
        assert result["agent_id"] == "example_agent"
        # Mock response from gateway
        assert "Mock response" in result["analysis"]

    @pytest.mark.asyncio
    async def test_run_directly(self, example_agent):
        """Test running the agent directly."""
        response = await example_agent.run("What time is it?")

        assert isinstance(response, str)
        assert "Mock response" in response

    @pytest.mark.asyncio
    async def test_integration_with_get_time_tool(self, mock_configs, temp_log_dir):
        """Test agent with GetTimeTool."""
        mock_gateway = MockLLMGateway(configs=mock_configs)
        agent = ExampleSGRAgent(
            agent_id="example_agent",
            llm_gateway=mock_gateway,
            model="test_model",
            log_dir=temp_log_dir
        )

        # Mock gateway to call tool
        call_count = [0]

        async def mock_request(request: LLMRequest) -> LLMResponse:
            call_count[0] += 1
            if call_count[0] == 1:
                # Return tool call
                return LLMResponse(
                    request_id=request.request_id,
                    content="",
                    tool_calls=[
                        {
                            "name": "get_current_time",
                            "arguments": "{}",
                            "id": "call_123"
                        }
                    ]
                )
            else:
                # Return final answer
                return LLMResponse(
                    request_id=request.request_id,
                    content="Current time is in the tool result",
                    tool_calls=None
                )

        mock_gateway.request = mock_request

        # Run agent
        response = await agent.run("What time is it?")

        assert response == "Current time is in the tool result"
        assert call_count[0] == 2  # Initial call + after tool

    @pytest.mark.asyncio
    async def test_reasoning_trace_structure(self, example_agent, temp_log_dir):
        """Test that reasoning trace has correct structure."""
        await example_agent.run("Test message")

        log_path = Path(temp_log_dir) / "reasoning" / "example_agent.jsonl"
        assert log_path.exists()

        with open(log_path, "r", encoding="utf-8") as f:
            log_entry = json.loads(f.readline().strip())

        # Verify structure
        assert "timestamp" in log_entry
        assert "agent_id" in log_entry
        assert "reasoning_trace" in log_entry

        # Verify trace steps
        trace = log_entry["reasoning_trace"]
        assert len(trace) >= 2

        # First step should be "think"
        assert trace[0]["action"] == "think"
        assert trace[0]["step"] == 1

        # Last step should be "formulate_answer"
        assert trace[-1]["action"] == "formulate_answer"
