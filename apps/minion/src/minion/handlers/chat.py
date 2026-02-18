import logging
from typing import Any

import anthropic

from minion.config import Settings
from minion.conversation import Conversation
from minion.events import Event, EventHandler
from minion.tools import ToolRegistry

logger = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 20


class ChatHandler(EventHandler):
    event_types = ["chat"]

    def __init__(
        self,
        config: Settings,
        tool_registry: ToolRegistry,
    ) -> None:
        self._client = anthropic.AsyncAnthropic(api_key=config.anthropic_api_key)
        self._model = config.agent.model
        self._max_tokens = config.agent.max_tokens
        self._system_prompt = config.agent.system_prompt.format(name=config.agent.name)
        self._tools = tool_registry
        self._conversation = Conversation(config.conversation.max_history)

    async def handle(self, event: Event) -> str | None:
        content = event.payload.get("content", "")
        if not content:
            return None

        self._conversation.add_user(content)
        return await self._run_conversation()

    async def _run_conversation(self) -> str:
        tools = self._tools.list_tools()

        for _ in range(MAX_TOOL_ROUNDS):
            response = await self._client.messages.create(
                model=self._model,
                max_tokens=self._max_tokens,
                system=self._system_prompt,
                messages=self._conversation.messages,
                tools=tools or anthropic.NOT_GIVEN,
            )

            self._conversation.add_assistant(response.content)

            if response.stop_reason == "end_turn":
                return self._extract_text(response.content)

            if response.stop_reason == "tool_use":
                await self._handle_tool_use(response.content)
                continue

            return self._extract_text(response.content)

        return "I've reached the maximum number of tool use rounds. Here's where I got to."

    async def _handle_tool_use(self, content: list[Any]) -> None:
        results: list[tuple[str, str]] = []
        for block in content:
            if block.type == "tool_use":
                logger.info("Tool call: %s(%s)", block.name, block.input)
                result = await self._tools.execute(block.name, **block.input)
                results.append((block.id, result))
        if results:
            self._conversation.add_tool_results(results)

    def _extract_text(self, content: list[Any]) -> str:
        parts = []
        for block in content:
            if block.type == "text":
                parts.append(block.text)
        return "\n".join(parts) or "(no response)"
