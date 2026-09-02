import pytest

from minion.agents import Agent, create_agent
from minion.agents.claude_api import ClaudeApiAgent
from minion.config import Settings
from minion.tools import create_registry


@pytest.fixture
def deps():
    config = Settings(anthropic_api_key="test-key")
    return config, create_registry(config.tools)


def test_default_backend_is_the_claude_api_agent(deps):
    config, tools = deps
    assert isinstance(create_agent(config, tools), ClaudeApiAgent)


def test_claude_api_agent_satisfies_the_protocol(deps):
    config, tools = deps
    assert isinstance(create_agent(config, tools), Agent)


def test_unknown_backend_is_rejected(deps):
    config, tools = deps
    config.agent.backend = "some-cheaper-llm"

    with pytest.raises(ValueError, match="some-cheaper-llm"):
        create_agent(config, tools)


def test_only_the_claude_module_imports_anthropic():
    """The seam is worth nothing if provider details leak into the flows."""
    import pathlib

    src = pathlib.Path(__file__).parent.parent / "src" / "minion"
    offenders = [
        path.relative_to(src).as_posix()
        for path in src.rglob("*.py")
        if "import anthropic" in path.read_text()
    ]
    assert offenders == ["agents/claude_api.py"]
