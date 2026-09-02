import logging

from minion.agents.claude_api import ClaudeApiAgent
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
        # Chat is out of scope per the design; it holds provider-specific
        # conversation state, so it binds to the concrete agent.
        self._agent = ClaudeApiAgent(config, tool_registry)
        self._system_prompt = config.agent.system_prompt.format(name=config.agent.name)
        self._conversation = Conversation(config.conversation.max_history)

    async def handle(self, event: Event) -> str | None:
        content = event.payload.get("content", "")
        if not content:
            return None

        self._conversation.add_user(content)
        return await self._agent.run_conversation(
            self._system_prompt, self._conversation, MAX_TOOL_ROUNDS, "chat"
        )
