"""
SGR (Schema-Guided Reasoning) Tools and data structures.

Provides base classes for SGR tools and reasoning trace data structures.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, Optional


class SGRTool(ABC):
    """
    Base class for SGR tools.

    Tool represents a function that an agent can call during reasoning.
    """

    name: str
    description: str
    parameters_schema: Dict[str, Any]

    @abstractmethod
    async def execute(self, **kwargs) -> Any:
        """
        Execute the tool.

        Args:
            **kwargs: Tool parameters

        Returns:
            Tool execution result
        """
        pass


@dataclass
class ToolCall:
    """
    Represents a single tool call.

    Attributes:
        name: Tool name
        parameters: Tool parameters
        result: Tool execution result (None before execution)
    """
    name: str
    parameters: Dict[str, Any]
    result: Optional[Any] = None


@dataclass
class ReasoningStep:
    """
    Represents a single step in the reasoning trace.

    Attributes:
        step_number: Step number in the reasoning chain
        action: Action type ("think" | "call_tool" | "formulate_answer")
        thought: Optional thought content for "think" action
        tool_used: Tool name for "call_tool" action
        tool_parameters: Parameters passed to tool
        tool_result: Result returned by tool (truncated to 200 chars)
        final_answer: Final answer for "formulate_answer" action
    """
    step_number: int
    action: str  # "think" | "call_tool" | "formulate_answer"
    thought: Optional[str] = None
    tool_used: Optional[str] = None
    tool_parameters: Optional[Dict[str, Any]] = None
    tool_result: Optional[Any] = None
    final_answer: Optional[str] = None
