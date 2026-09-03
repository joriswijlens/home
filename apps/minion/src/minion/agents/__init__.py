"""The seam between minion and whichever model backend runs a flow.

`Agent` is deliberately narrow: a flow hands over a system prompt and a task, and gets
text back. Everything backend-shaped — client, request format, message and tool-result
structure, the tool-use loop — lives behind it, because those shapes differ per backend
and leak through any interface that passes them around.

"Provider" is reserved for the task side (GitHub, Jira, Vikunja); this is the model side.

Switching to a cheaper model backend means adding one module next to `claude_api.py`
and changing `agent.backend` in config.
"""

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from minion.config import Settings
from minion.tools import ToolRegistry


@dataclass
class RunResult:
    """What a run produced, and what it cost.

    Usage is provider-neutral on purpose — every backend can report tokens in and out,
    and without them there is no way to enforce a spend ceiling or to see cost in
    Grafana.
    """

    text: str
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return (
            self.input_tokens
            + self.output_tokens
            + self.cache_read_tokens
            + self.cache_write_tokens
        )

    def usage(self) -> dict:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cache_read_tokens": self.cache_read_tokens,
            "cache_write_tokens": self.cache_write_tokens,
        }


@runtime_checkable
class Agent(Protocol):
    async def run(
        self,
        system_prompt: str,
        prompt: str,
        max_rounds: int,
        label: str = "agent",
    ) -> RunResult:
        """Run a task to completion, returning its text and what it cost."""
        ...


def create_agent(config: Settings, tool_registry: ToolRegistry) -> Agent:
    backend = config.agent.backend

    if backend == "claude_api":
        from minion.agents.claude_api import ClaudeApiAgent

        return ClaudeApiAgent(config, tool_registry)

    raise ValueError(
        f"Unknown agent backend: {backend!r}. "
        f"Add a module under minion/agents/ and register it here."
    )
