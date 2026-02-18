import logging
from pathlib import Path
from typing import Any

from minion.config import ToolsConfig
from minion.tools import Tool

logger = logging.getLogger(__name__)

MAX_READ = 50_000


class FileReadTool(Tool):
    name = "file_read"
    description = "Read the contents of a file."
    parameters = {
        "path": {"type": "string", "description": "Absolute path to the file to read"},
    }

    def __init__(self, config: ToolsConfig) -> None:
        self._allowed = [Path(p) for p in config.allowed_paths]

    def _check_path(self, path: Path) -> str | None:
        resolved = path.resolve()
        for allowed in self._allowed:
            if str(resolved).startswith(str(allowed.resolve())):
                return None
        return f"Error: path {path} is not within allowed paths: {self._allowed}"

    async def execute(self, **kwargs: Any) -> str:
        path = Path(kwargs.get("path", ""))
        if err := self._check_path(path):
            return err
        if not path.exists():
            return f"Error: {path} does not exist"
        if not path.is_file():
            return f"Error: {path} is not a file"

        content = path.read_text(errors="replace")
        if len(content) > MAX_READ:
            content = content[:MAX_READ] + f"\n... (truncated, {len(content)} chars total)"
        return content


class FileWriteTool(Tool):
    name = "file_write"
    description = "Write content to a file. Creates parent directories if needed."
    parameters = {
        "path": {"type": "string", "description": "Absolute path to the file to write"},
        "content": {"type": "string", "description": "Content to write to the file"},
    }

    def __init__(self, config: ToolsConfig) -> None:
        self._allowed = [Path(p) for p in config.allowed_paths]

    def _check_path(self, path: Path) -> str | None:
        resolved = path.resolve()
        for allowed in self._allowed:
            if str(resolved).startswith(str(allowed.resolve())):
                return None
        return f"Error: path {path} is not within allowed paths: {self._allowed}"

    async def execute(self, **kwargs: Any) -> str:
        path = Path(kwargs.get("path", ""))
        content = kwargs.get("content", "")
        if err := self._check_path(path):
            return err

        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        logger.info("Wrote %d chars to %s", len(content), path)
        return f"Successfully wrote {len(content)} characters to {path}"
