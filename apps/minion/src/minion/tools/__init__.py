import logging
from abc import ABC, abstractmethod
from typing import Any

from minion.config import ToolsConfig

logger = logging.getLogger(__name__)


class Tool(ABC):
    name: str
    description: str
    parameters: dict[str, Any]

    @abstractmethod
    async def execute(self, **kwargs: Any) -> str: ...

    def to_anthropic_tool(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": {
                "type": "object",
                "properties": self.parameters,
                "required": [
                    k for k, v in self.parameters.items() if not v.get("optional")
                ],
            },
        }


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool
        logger.info("Registered tool: %s", tool.name)

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def list_tools(self) -> list[dict[str, Any]]:
        return [t.to_anthropic_tool() for t in self._tools.values()]

    async def execute(self, name: str, **kwargs: Any) -> str:
        tool = self._tools.get(name)
        if not tool:
            return f"Error: unknown tool '{name}'"
        try:
            return await tool.execute(**kwargs)
        except Exception as e:
            logger.exception("Tool %s failed", name)
            return f"Error executing {name}: {e}"


def create_registry(config: ToolsConfig) -> ToolRegistry:
    from minion.tools.files import FileReadTool, FileWriteTool
    from minion.tools.git import GitTool
    from minion.tools.shell import ShellTool

    available: dict[str, type[Tool]] = {
        "shell": ShellTool,
        "file_read": FileReadTool,
        "file_write": FileWriteTool,
        "git": GitTool,
    }

    registry = ToolRegistry()
    for name in config.enabled:
        tool_cls = available.get(name)
        if tool_cls:
            registry.register(tool_cls(config))
        else:
            logger.warning("Unknown tool in config: %s", name)

    return registry
