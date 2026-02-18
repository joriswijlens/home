import logging
from typing import Any

logger = logging.getLogger(__name__)


class Conversation:
    def __init__(self, max_history: int = 50) -> None:
        self._messages: list[dict[str, Any]] = []
        self._max_history = max_history

    def add_user(self, content: str) -> None:
        self._messages.append({"role": "user", "content": content})
        self._trim()

    def add_assistant(self, content: Any) -> None:
        self._messages.append({"role": "assistant", "content": content})
        self._trim()

    def add_tool_results(self, results: list[tuple[str, str]]) -> None:
        """Add tool results as a single user message.

        Args:
            results: List of (tool_use_id, result_text) tuples.
        """
        self._messages.append(
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": tool_use_id,
                        "content": result,
                    }
                    for tool_use_id, result in results
                ],
            }
        )
        self._trim()

    @property
    def messages(self) -> list[dict[str, Any]]:
        return list(self._messages)

    def clear(self) -> None:
        self._messages.clear()

    def _trim(self) -> None:
        while len(self._messages) > self._max_history:
            self._messages.pop(0)
