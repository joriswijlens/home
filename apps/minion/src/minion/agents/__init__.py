"""The seam between minion and whichever model backend runs a flow.

`Agent` is deliberately narrow: a flow hands over a system prompt and a task, and gets
text back. Everything backend-shaped — client, request format, message and tool-result
structure, the tool-use loop — lives behind it, because those shapes differ per backend
and leak through any interface that passes them around.

"Provider" is reserved for the task side (GitHub, Jira, Vikunja); this is the model side.

Switching to a cheaper model backend means adding one module next to `claude_api.py`
and changing `agent.backend` in config.
"""

from typing import Protocol, runtime_checkable

from minion.config import Settings
from minion.tools import ToolRegistry


@runtime_checkable
class Agent(Protocol):
    async def run(
        self,
        system_prompt: str,
        prompt: str,
        max_rounds: int,
        label: str = "agent",
    ) -> str:
        """Run a task to completion and return the final text."""
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
