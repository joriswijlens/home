"""An agent definition, as it lives in the agents repo: `agents/<name>/`.

The portable part is standard — `apm.yml` selects plugins and skills, and
`apm install --target opencode` materializes them into `.agents/skills/`. What the
standards leave to the harness is `agent.yml`: model, round limit, permissions, and
MCP servers until apm writes those for OpenCode itself. Minion reads only that.

Its schema is coupled to the minion version, so an unknown key is an error rather
than a silently ignored typo.
"""

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict


class AgentDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = ""
    model: str | None = None
    max_rounds: int | None = None
    permission: dict[str, str] | None = None
    mcp: dict[str, Any] = {}
    skills_dir: Path | None = None


def load_agent(directory: str | Path) -> AgentDefinition:
    directory = Path(directory)
    fields = yaml.safe_load((directory / "agent.yml").read_text()) or {}
    skills = directory / ".agents" / "skills"
    return AgentDefinition(
        **fields,
        name=directory.name,
        skills_dir=skills if skills.is_dir() else None,
    )
