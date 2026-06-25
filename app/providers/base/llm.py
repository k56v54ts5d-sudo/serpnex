from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class LLMMessage:
    role: str  # "user" | "assistant"
    content: str


@dataclass
class ToolDefinition:
    name: str
    description: str
    input_schema: dict[str, Any]


@dataclass
class LLMResponse:
    tool_name: str
    tool_input: dict[str, Any]
    input_tokens: int
    output_tokens: int


class LLMProvider(ABC):
    """Abstract interface for LLM inference. All prompting and structured output
    extraction goes through this interface. Implementations must support
    tool-use / function-calling for structured output. Business logic never
    imports a concrete LLM client directly."""

    @abstractmethod
    async def call_with_tool(
        self,
        *,
        system: str,
        messages: list[LLMMessage],
        tool: ToolDefinition,
        model: str,
        max_tokens: int = 2048,
    ) -> LLMResponse:
        """Send a conversation to the LLM and force a single tool call response.
        The model must call `tool` and return its structured input.
        Raises LLMError on network failure, timeout, or schema refusal."""


class LLMError(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(f"LLM call failed: {reason}")
