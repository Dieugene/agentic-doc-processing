"""
System SGR Agent - base class for all SGR agents.

Integrates SGR (Schema-Guided Reasoning) pattern with LLM Gateway.
"""
import asyncio
import json
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from gateway.models import LLMMessage, LLMRequest, LLMResponse, LLMTool
from gateway.simple_llm_gateway import SimpleLLMGateway
from gateway.llm_gateway import LLMGateway
from agents.tools import SGRTool, ReasoningStep


class SystemSGRAgent(ABC):
    """
    Base class for all SGR agents in the system.

    Integrates SGR Core pattern with LLM Gateway for structured reasoning.
    Provides tool execution, reasoning trace logging, and SGR loop.

    Attributes:
        agent_id: Unique agent identifier
        llm_gateway: LLM gateway instance (SimpleLLMGateway or LLMGateway)
        model: Model identifier for requests
        system_prompt: System prompt for the agent
        tools: List of available tools
        log_dir: Directory for reasoning traces (None = no logging)
        MAX_ITERATIONS: Maximum SGR loop iterations (default: 10)
    """

    MAX_ITERATIONS: int = 10

    def __init__(
        self,
        agent_id: str,
        llm_gateway: Union[SimpleLLMGateway, LLMGateway],
        model: str,
        system_prompt: str,
        tools: Optional[List[SGRTool]] = None,
        log_dir: Optional[str] = None,
    ):
        """
        Initialize SystemSGRAgent.

        Args:
            agent_id: Unique agent ID
            llm_gateway: LLM gateway instance
            model: Model identifier
            system_prompt: System prompt for the agent
            tools: List of available SGR tools
            log_dir: Directory for reasoning traces (optional)
        """
        self.agent_id = agent_id
        self.llm_gateway = llm_gateway
        self.model = model
        self.system_prompt = system_prompt
        self.tools = tools or []
        self.log_dir = log_dir

        # Reasoning trace for current request
        self._reasoning_trace: List[ReasoningStep] = []

    @abstractmethod
    async def process(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Main method for processing input data.

        Must be overridden in subclasses.

        Args:
            input_data: Input data

        Returns:
            Processing result
        """
        pass

    async def run(
        self,
        user_message: str,
        context: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Run the agent with a user message.

        Args:
            user_message: User message
            context: Additional context (optional)

        Returns:
            Agent response
        """
        # Clear reasoning trace
        self._reasoning_trace = []

        # Build messages
        messages = [
            LLMMessage(role="system", content=self.system_prompt),
            LLMMessage(role="user", content=user_message)
        ]

        # Build tools if available
        tools = None
        if self.tools:
            tools = [
                LLMTool(
                    name=tool.name,
                    description=tool.description,
                    parameters=tool.parameters_schema
                )
                for tool in self.tools
            ]

        # Step 1: Log initial analysis
        await self._log_step(
            action="think",
            thought=f"Получен запрос: {user_message[:100]}..."
        )

        # Run SGR loop
        response = await self._sgr_loop(messages, tools, context)

        # Log final answer
        await self._log_step(
            action="formulate_answer",
            final_answer=response
        )

        # Save trace
        await self._save_trace()

        return response

    async def _sgr_loop(
        self,
        messages: List[LLMMessage],
        tools: Optional[List[LLMTool]],
        context: Optional[Dict[str, Any]]
    ) -> str:
        """
        SGR reasoning loop.

        Loop logic:
        1. Send request to LLM
        2. If tool_calls present - execute tools
        3. Add results to messages
        4. Repeat until final answer or max iterations

        Args:
            messages: Current message history
            tools: Available tools
            context: Additional context

        Returns:
            Final response from LLM
        """
        for iteration in range(self.MAX_ITERATIONS):
            # Build request
            request = LLMRequest(
                request_id=f"{self.agent_id}_iter_{iteration}",
                model=self.model,
                messages=messages,
                tools=tools,
                agent_id=self.agent_id
            )

            # Send to Gateway
            response = await self.llm_gateway.request(request)

            # Check for tool calls
            if response.tool_calls:
                # Execute each tool
                for tool_call in response.tool_calls:
                    tool_name = tool_call.get("name")
                    tool_args_str = tool_call.get("arguments", "{}")

                    # Parse arguments JSON string
                    try:
                        tool_params = json.loads(tool_args_str)
                    except json.JSONDecodeError:
                        tool_params = {}

                    await self._log_step(
                        action="call_tool",
                        tool_used=tool_name,
                        tool_parameters=tool_params
                    )

                    # Find tool
                    tool = next((t for t in self.tools if t.name == tool_name), None)
                    if tool:
                        try:
                            result = await tool.execute(**tool_params)

                            # Truncate result for logging
                            result_str = str(result)[:200]
                            await self._log_step(
                                action="call_tool",
                                tool_used=tool_name,
                                tool_result=result_str
                            )

                            # Add assistant message with tool call
                            messages.append(LLMMessage(
                                role="assistant",
                                content="",  # tool call
                                tool_call=tool_call
                            ))
                            # Add tool response message with tool_call_id
                            messages.append(LLMMessage(
                                role="tool",
                                name=tool_name,
                                content=str(result),
                                tool_call=tool_call  # Pass tool_call to preserve id
                            ))
                        except Exception as e:
                            # Tool execution error
                            error_msg = f"Error executing {tool_name}: {str(e)}"
                            await self._log_step(
                                action="call_tool",
                                tool_used=tool_name,
                                tool_result=error_msg
                            )

                            # Add error as tool result
                            messages.append(LLMMessage(
                                role="assistant",
                                content="",
                                tool_call=tool_call
                            ))
                            messages.append(LLMMessage(
                                role="tool",
                                name=tool_name,
                                content=error_msg,
                                tool_call=tool_call  # Pass tool_call to preserve id
                            ))
                    else:
                        # Tool not found
                        error_msg = f"Error: Tool {tool_name} not found"
                        await self._log_step(
                            action="call_tool",
                            tool_used=tool_name,
                            tool_result=error_msg
                        )

                        messages.append(LLMMessage(
                            role="assistant",
                            content=error_msg
                        ))
                # Continue loop
            else:
                # Final answer
                return response.content

        # Max iterations exceeded
        return "Error: Maximum iterations exceeded"

    async def _log_step(self, **kwargs):
        """
        Log a reasoning step.

        Args:
            **kwargs: ReasoningStep fields
        """
        step = ReasoningStep(
            step_number=len(self._reasoning_trace) + 1,
            **kwargs
        )
        self._reasoning_trace.append(step)

    async def _save_trace(self):
        """
        Save reasoning trace to JSONL file.

        Format: One JSON line per request
        """
        if not self.log_dir:
            return

        log_path = Path(self.log_dir) / "reasoning" / f"{self.agent_id}.jsonl"
        log_path.parent.mkdir(parents=True, exist_ok=True)

        trace_entry = {
            "timestamp": datetime.now().isoformat(),
            "agent_id": self.agent_id,
            "reasoning_trace": [
                {
                    "step": s.step_number,
                    "action": s.action,
                    "thought": s.thought,
                    "tool_used": s.tool_used,
                    "tool_parameters": s.tool_parameters,
                    "tool_result": s.tool_result,
                    "final_answer": s.final_answer
                }
                for s in self._reasoning_trace
            ]
        }

        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(trace_entry, ensure_ascii=False) + "\n")
