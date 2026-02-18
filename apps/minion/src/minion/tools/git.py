import asyncio
import logging
from pathlib import Path
from typing import Any

from minion.config import ToolsConfig
from minion.tools import Tool

logger = logging.getLogger(__name__)

DANGEROUS_PATTERNS = [
    "push --force",
    "push -f",
    "reset --hard",
    "clean -f",
    "branch -D",
]


class GitTool(Tool):
    name = "git"
    description = "Execute a git command in a repository."
    parameters = {
        "command": {
            "type": "string",
            "description": "Git subcommand and arguments (e.g. 'status', 'diff', 'log --oneline -10')",
        },
        "repo": {
            "type": "string",
            "description": "Path to the git repository",
            "optional": True,
        },
    }

    def __init__(self, config: ToolsConfig) -> None:
        self._repos = [Path(p) for p in config.git_repos]
        self._timeout = config.shell_timeout

    def _check_repo(self, repo: Path) -> str | None:
        resolved = repo.resolve()
        for allowed in self._repos:
            if str(resolved).startswith(str(allowed.resolve())):
                return None
        return f"Error: repo {repo} is not within allowed repos: {self._repos}"

    async def execute(self, **kwargs: Any) -> str:
        command = kwargs.get("command", "")
        repo = Path(kwargs.get("repo", str(self._repos[0])) if self._repos else ".")

        if not command:
            return "Error: no git command provided"

        for pattern in DANGEROUS_PATTERNS:
            if pattern in command:
                return f"Error: dangerous git command blocked: '{pattern}'"

        if err := self._check_repo(repo):
            return err

        full_cmd = f"git -C {repo} {command}"
        logger.info("Executing: %s", full_cmd)

        try:
            proc = await asyncio.create_subprocess_shell(
                full_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=self._timeout
            )
        except asyncio.TimeoutError:
            proc.kill()
            return f"Error: git command timed out after {self._timeout}s"

        output = stdout.decode(errors="replace")
        if stderr_text := stderr.decode(errors="replace"):
            output += f"\n{stderr_text}"

        return output.strip() or "(no output)"
