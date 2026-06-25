import anthropic

from app.providers.base.llm import LLMError, LLMMessage, LLMProvider, LLMResponse, ToolDefinition


class AnthropicLLMProvider(LLMProvider):
    """LLMProvider backed by the Anthropic API. Uses tool_use for all
    structured output — the model is always forced to call a single tool."""

    def __init__(self, api_key: str) -> None:
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY is not configured")
        self._client = anthropic.AsyncAnthropic(api_key=api_key, timeout=90.0)

    async def call_with_tool(
        self,
        *,
        system: str,
        messages: list[LLMMessage],
        tool: ToolDefinition,
        model: str,
        max_tokens: int = 2048,
    ) -> LLMResponse:
        anthropic_messages = [{"role": m.role, "content": m.content} for m in messages]
        anthropic_tool = {
            "name": tool.name,
            "description": tool.description,
            "input_schema": tool.input_schema,
        }

        try:
            response = await self._client.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=system,
                messages=anthropic_messages,
                tools=[anthropic_tool],
                tool_choice={"type": "tool", "name": tool.name},
            )
        except anthropic.APIError as exc:
            raise LLMError(str(exc)) from exc

        tool_block = next(
            (block for block in response.content if block.type == "tool_use"), None
        )
        if tool_block is None:
            raise LLMError("Model did not return a tool_use block")

        return LLMResponse(
            tool_name=tool_block.name,
            tool_input=tool_block.input,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )
