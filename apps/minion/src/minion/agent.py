"""The one place that talks to a model provider.

Everything provider-specific lives here — client construction, request shape, content
block handling. Handlers pass a system prompt, a conversation and a tool registry, and
get text back. Switching to another provider is a rewrite of this file and nothing else;
it is deliberately not a plugin interface, since there is exactly one provider today.
"""

import logging
from typing import Any

import anthropic

from minion.config import Settings
from minion.conversation import Conversation
from minion.tools import ToolRegistry

logger = logging.getLogger(__name__)


class AgentRunner:
    def __init__(self, config: Settings, tool_registry: ToolRegistry) -> None:
        self._client = anthropic.AsyncAnthropic(api_key=config.anthropic_api_key)
        self._model = config.agent.model
        self._max_tokens = config.agent.max_tokens
        self._effort = config.agent.effort
        self._tools = tool_registry

    async def run(
        self,
        system_prompt: str,
        conversation: Conversation,
        max_rounds: int,
        label: str = "agent",
    ) -> str:
        """Run the tool-use loop until the model stops, or the round budget runs out."""
        tools = self._tools.list_tools()

        for _ in range(max_rounds):
            response = await self._client.messages.create(
                model=self._model,
                max_tokens=self._max_tokens,
                system=system_prompt,
                messages=conversation.messages,
                tools=tools or anthropic.NOT_GIVEN,
                output_config={"effort": self._effort},
            )

            conversation.add_assistant(response.content)

            if response.stop_reason == "tool_use":
                await self._handle_tool_use(response.content, conversation, label)
                continue

            return self._extract_text(response.content)

        logger.warning("%s reached max tool rounds (%d)", label, max_rounds)
        return f"{label} reached the maximum number of tool rounds."

    async def _handle_tool_use(
        self, content: list[Any], conversation: Conversation, label: str
    ) -> None:
        results: list[tuple[str, str]] = []
        for block in content:
            if block.type == "tool_use":
                logger.info("%s tool call: %s(%s)", label, block.name, block.input)
                result = await self._tools.execute(block.name, **block.input)
                results.append((block.id, result))
        if results:
            conversation.add_tool_results(results)

    @staticmethod
    def _extract_text(content: list[Any]) -> str:
        parts = [block.text for block in content if block.type == "text"]
        return "\n".join(parts) or "(no response)"
