import asyncio
import logging
from typing import Any

from minion.config import ToolsConfig
from minion.tools import Tool

logger = logging.getLogger(__name__)

MAX_OUTPUT = 10_000


class ShellTool(Tool):
    name = "shell"
    description = "Execute a shell command and return its output."
    parameters = {
        "command": {"type": "string", "description": "The shell command to execute"},
    }

    def __init__(self, config: ToolsConfig) -> None:
        self._timeout = config.shell_timeout

    async def execute(self, **kwargs: Any) -> str:
        command = kwargs.get("command", "")
        if not command:
            return "Error: no command provided"

        logger.info("Executing shell command: %s", command)
        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=self._timeout
            )
        except asyncio.TimeoutError:
            proc.kill()
            return f"Error: command timed out after {self._timeout}s"

        output = stdout.decode(errors="replace")
        err = stderr.decode(errors="replace")

        result = ""
        if output:
            result += output
        if err:
            result += f"\nSTDERR:\n{err}"
        if proc.returncode != 0:
            result += f"\nExit code: {proc.returncode}"

        if len(result) > MAX_OUTPUT:
            result = result[:MAX_OUTPUT] + f"\n... (truncated, {len(result)} chars total)"

        return result or "(no output)"
