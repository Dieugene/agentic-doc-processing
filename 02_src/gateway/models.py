"""
Data models for LLM Gateway.

Defines request/response structures and model configurations.
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class ModelProvider(str, Enum):
    """Supported LLM providers."""

    CLAUDE_HAIKU = "claude-haiku"
    CLAUDE_SONNET = "claude-sonnet"
    CLAUDE_OPUS = "claude-opus"
    GPT_4O_MINI = "gpt-4o-mini"
    GPT_4O = "gpt-4o"
    LOCAL_LLAMA = "local-llama"


@dataclass
class ModelConfig:
    """Configuration for an LLM model."""

    provider: ModelProvider
    endpoint: str
    api_key: str
    model_name: str

    # Rate limits (informational, actual control via retry)
    max_requests_per_minute: Optional[int] = None
    max_tokens_per_minute: Optional[int] = None

    # Batching configuration
    batch_size: int = 10
    batch_timeout_ms: int = 100


@dataclass
class LLMMessage:
    """Message in chat API format."""

    role: str  # "system" | "user" | "assistant" | "tool"
    content: str
    name: Optional[str] = None  # For tool messages
    tool_call: Optional[Dict[str, Any]] = None  # For tool calls


@dataclass
class LLMTool:
    """Tool description for function calling."""

    name: str
    description: str
    parameters: Dict[str, Any]


@dataclass
class LLMRequest:
    """Request to LLM."""

    request_id: str  # for tracing
    model: str  # model identifier from ModelConfig
    messages: List[LLMMessage]
    tools: Optional[List[LLMTool]] = None
    temperature: float = 0.0

    # Metadata for tracing
    agent_id: Optional[str] = None
    trace_id: Optional[str] = None


@dataclass
class LLMResponse:
    """Response from LLM."""

    request_id: str
    content: str
    tool_calls: Optional[List[Dict[str, Any]]] = None
    usage: Optional[Dict[str, int]] = None  # tokens in/out
    latency_ms: int = 0
