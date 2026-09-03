"""Agent backed by the Anthropic Messages API.

The only module that imports `anthropic`. Message and tool-result shapes here are
Anthropic's, and stay inside this file.

## Caching

An agent loop resends everything before it on every round: tool definitions, the
system prompt, and the whole conversation so far. A twenty-round run therefore pays
for the same prefix twenty times, and that prefix is the bulk of the bill.

Two breakpoints fix that. Requests render as tools -> system -> messages, so a marker
on the last system block covers the tool definitions too — the part that never changes
within a flow. Top-level caching then handles the conversation tail, moving its
breakpoint forward as rounds accumulate, so each round reads what the previous ones
added and writes only the delta.

Cache reads cost about a tenth of input price, writes about 1.25x, so this pays for
itself from the second round on.

It fails silently, which is the trap: a prefix below the model's minimum is simply not
cached, with no error — 1024 tokens on Sonnet 5, and the tools plus a flow's system
prompt land near that line (measured 2026-09-03: plan 1089, implement 975). Any byte
that changes ahead of a breakpoint invalidates everything after it, too. So a run that
asked for caching and got none logs a warning rather than quietly costing more.
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
        self._cache = config.agent.cache_prompts
        self._tools = tool_registry

    def _system_blocks(self, system_prompt: str) -> list[dict] | str:
        """System as a cacheable block, so tools + system are read rather than resent."""
        if not self._cache:
            return system_prompt
        return [
            {
                "type": "text",
                "text": system_prompt,
                "cache_control": {"type": "ephemeral"},
            }
        ]

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
        rounds = 0

        for _ in range(max_rounds):
            response = await self._client.messages.create(
                model=self._model,
                max_tokens=self._max_tokens,
                system=self._system_blocks(system_prompt),
                messages=conversation.messages,
                tools=tools or anthropic.NOT_GIVEN,
                output_config={"effort": self._effort},
                # Moves its own breakpoint forward as the conversation grows, so each
                # round reads the accumulated prefix and writes only what was added.
                cache_control=(
                    {"type": "ephemeral"} if self._cache else anthropic.NOT_GIVEN
                ),
            )

            self._add_usage(result, response)
            conversation.add_assistant(response.content)

            if response.stop_reason == "tool_use":
                await self._handle_tool_use(response.content, conversation, label)
                rounds += 1
                continue

            result.text = self._extract_text(response.content)
            self._warn_if_uncached(result, label, rounds + 1)
            return result

        logger.warning("%s reached max tool rounds (%d)", label, max_rounds)
        result.text = f"{label} reached the maximum number of tool rounds."
        return result

    def _warn_if_uncached(self, result: RunResult, label: str, rounds: int) -> None:
        """Caching failing is invisible from the outside — say so out loud.

        A prefix under the model's minimum is not cached and no error is raised, so
        without this the only symptom is a larger bill.
        """
        if not self._cache or rounds < 2:
            return
        if result.cache_read_tokens or result.cache_write_tokens:
            return
        logger.warning(
            "%s ran %d rounds with caching enabled but nothing was cached — the "
            "prefix is likely below the model minimum, or something ahead of the "
            "breakpoint changes per request",
            label,
            rounds,
        )

    @staticmethod
    def _add_usage(result: RunResult, response) -> None:
        usage = getattr(response, "usage", None)
        if usage is None:
            return
        result.input_tokens += getattr(usage, "input_tokens", 0) or 0
        result.output_tokens += getattr(usage, "output_tokens", 0) or 0
        result.cache_read_tokens += getattr(usage, "cache_read_input_tokens", 0) or 0
        result.cache_write_tokens += getattr(usage, "cache_creation_input_tokens", 0) or 0

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
