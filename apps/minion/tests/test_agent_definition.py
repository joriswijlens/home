"""An agent definition: `agent.yml` plus whatever `apm install` put in `.agents/skills`."""

import json

import pytest
from pydantic import ValidationError

from minion.agent_definition import load_agent
from minion.agents.opencode import OpenCodeAgent
from minion.config import Settings
from tests.test_opencode import event, fake_opencode  # noqa: F401 — fixture


def write_agent(tmp_path, yml: str, skills: bool = True):
    directory = tmp_path / "triage"
    directory.mkdir()
    (directory / "agent.yml").write_text(yml)
    if skills:
        (directory / ".agents" / "skills" / "depot").mkdir(parents=True)
    return directory


def test_loads_the_minion_part_and_finds_installed_skills(tmp_path):
    directory = write_agent(tmp_path, "model: anthropic/claude-haiku-5-5\nmax_rounds: 25\n")

    agent = load_agent(directory)

    assert agent.name == "triage"
    assert agent.model == "anthropic/claude-haiku-5-5"
    assert agent.max_rounds == 25
    assert agent.skills_dir == directory / ".agents" / "skills"


def test_no_installed_skills_is_not_an_error(tmp_path):
    directory = write_agent(tmp_path, "model: a/b\n", skills=False)

    assert load_agent(directory).skills_dir is None


def test_an_unknown_key_fails_loudly(tmp_path):
    """The schema is coupled to the minion version; a typo must not be silently ignored."""
    directory = write_agent(tmp_path, "model: a/b\nmax_round: 25\n")

    with pytest.raises(ValidationError):
        load_agent(directory)


async def test_the_definition_overrides_what_opencode_is_given(tmp_path, fake_opencode):
    recorded = fake_opencode([event("text", type="text", text="ok")])
    directory = write_agent(
        tmp_path,
        "model: anthropic/claude-haiku-5-5\n"
        "max_rounds: 7\n"
        "permission: {bash: deny}\n"
        "mcp: {loki: {type: local, command: [mcp-loki]}}\n",
    )
    config = Settings(agent={"backend": "opencode", "model": "fake/default"})

    await OpenCodeAgent(config, load_agent(directory)).run("s", "p", 40)

    handed = json.loads(recorded()["config"])
    minion = handed["agent"]["minion"]
    assert minion["model"] == "anthropic/claude-haiku-5-5"
    assert minion["steps"] == 7
    assert minion["permission"] == {"bash": "deny"}
    assert handed["mcp"]["loki"]["command"] == ["mcp-loki"]
    assert handed["skills"] == {"paths": [str(directory / ".agents" / "skills")]}
    assert "anthropic/claude-haiku-5-5" in recorded()["argv"]


def test_a_backend_that_cannot_use_a_definition_refuses_it(tmp_path):
    from minion.agents import create_agent
    from minion.tools import create_registry

    config = Settings(agent={"backend": "claude_api"}, anthropic_api_key="k")
    directory = write_agent(tmp_path, "model: a/b\n")

    with pytest.raises(ValueError):
        create_agent(config, create_registry(config.tools), load_agent(directory))
