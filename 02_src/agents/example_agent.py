"""
Example SGR Agent for demonstration and testing.

Provides a simple agent that demonstrates SGR integration.
"""
from datetime import datetime
from typing import Any, Dict

from .sgr_agent import SystemSGRAgent
from .tools import SGRTool


class GetTimeTool(SGRTool):
    """
    Simple tool for getting current time.

    Demonstrates basic tool implementation.
    """

    name = "get_current_time"
    description = "Получить текущее время и дату"
    parameters_schema = {
        "type": "object",
        "properties": {},
        "required": []
    }

    async def execute(self, **kwargs) -> str:
        """
        Get current time.

        Returns:
            ISO format timestamp
        """
        return datetime.now().isoformat()


class ExampleSGRAgent(SystemSGRAgent):
    """
    Example SGR agent for demonstration.

    A simple agent that can analyze text and use tools.
    Used for testing SGR integration.
    """

    def __init__(
        self,
        agent_id: str,
        llm_gateway,
        model: str,
        log_dir: str = None,
    ):
        """
        Initialize ExampleSGRAgent.

        Args:
            agent_id: Unique agent ID
            llm_gateway: LLM gateway instance
            model: Model identifier
            log_dir: Directory for reasoning traces
        """
        system_prompt = """Ты — полезный AI-ассистент.
Ты можешь анализировать текст и использовать доступные инструменты.
Отвечай кратко и по существу."""

        # Initialize with tools
        tools = [GetTimeTool()]
        super().__init__(
            agent_id=agent_id,
            llm_gateway=llm_gateway,
            model=model,
            system_prompt=system_prompt,
            tools=tools,
            log_dir=log_dir
        )

    async def process(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process input data.

        Example: analyze text or answer questions.

        Args:
            input_data: Input data with "text" field

        Returns:
            Processing result with analysis and agent_id
        """
        text = input_data.get("text", "")

        response = await self.run(
            user_message=f"Проанализируй текст: {text}",
            context=input_data
        )

        return {
            "analysis": response,
            "agent_id": self.agent_id
        }
