"""Agent backed by the Anthropic Messages API.

The only module that imports `anthropic`. Message and tool-result shapes here are
Anthropic's, and stay inside this file.
"""

import logging
from typing import Any

import anthropic

from minion.agents import RunResult
from minion.config import Settings
from minion.conversation import Conversation
from minion.tools import ToolRegistry

logger = logging.getLogger(__name__)


class ClaudeApiAgent:
    def __init__(self, config: Settings, tool_registry: ToolRegistry) -> None:
        self._client = anthropic.AsyncAnthropic(api_key=config.anthropic_api_key)
        self._model = config.agent.model
        self._max_tokens = config.agent.max_tokens
        self._effort = config.agent.effort
        self._tools = tool_registry

    async def run(
        self,
        system_prompt: str,
        prompt: str,
        max_rounds: int,
        label: str = "agent",
    ) -> RunResult:
        conversation = Conversation(max_history=200)
        conversation.add_user(prompt)
        return await self.run_conversation(
            system_prompt, conversation, max_rounds, label
        )

    async def run_conversation(
        self,
        system_prompt: str,
        conversation: Conversation,
        max_rounds: int,
        label: str = "agent",
    ) -> RunResult:
        """Run the tool-use loop over an existing conversation."""
        tools = self._tools.list_tools()
        result = RunResult(text="")

        for _ in range(max_rounds):
            response = await self._client.messages.create(
                model=self._model,
                max_tokens=self._max_tokens,
                system=system_prompt,
                messages=conversation.messages,
                tools=tools or anthropic.NOT_GIVEN,
                output_config={"effort": self._effort},
            )

            self._add_usage(result, response)
            conversation.add_assistant(response.content)

            if response.stop_reason == "tool_use":
                await self._handle_tool_use(response.content, conversation, label)
                continue

            result.text = self._extract_text(response.content)
            return result

        logger.warning("%s reached max tool rounds (%d)", label, max_rounds)
        result.text = f"{label} reached the maximum number of tool rounds."
        return result

    @staticmethod
    def _add_usage(result: RunResult, response) -> None:
        usage = getattr(response, "usage", None)
        if usage is None:
            return
        result.input_tokens += getattr(usage, "input_tokens", 0) or 0
        result.output_tokens += getattr(usage, "output_tokens", 0) or 0
        result.cache_read_tokens += getattr(usage, "cache_read_input_tokens", 0) or 0

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
