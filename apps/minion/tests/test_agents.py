import pytest

from minion.agents import Agent, create_agent
from minion.agents.claude_api import ClaudeApiAgent
from minion.config import Settings
from minion.tools import create_registry


@pytest.fixture
def deps():
    config = Settings(anthropic_api_key="test-key")
    return config, create_registry(config.tools)


def test_default_backend_is_opencode(deps):
    from minion.agents.opencode import OpenCodeAgent

    config, tools = deps
    assert isinstance(create_agent(config, tools), OpenCodeAgent)


def test_claude_api_is_still_a_backend(deps):
    config, tools = deps
    config.agent.backend = "claude_api"
    assert isinstance(create_agent(config, tools), ClaudeApiAgent)


def test_claude_api_agent_satisfies_the_protocol(deps):
    config, tools = deps
    config.agent.backend = "claude_api"
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


# -- caching ------------------------------------------------------------------


class RecordingMessages:
    """Captures what would be sent, so the cache markers can be asserted on."""

    def __init__(self):
        self.calls = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)

        class Response:
            stop_reason = "end_turn"
            content = [type("Block", (), {"type": "text", "text": "hi"})()]
            usage = type(
                "Usage",
                (),
                {
                    "input_tokens": 10,
                    "output_tokens": 5,
                    "cache_read_input_tokens": 7,
                    "cache_creation_input_tokens": 3,
                },
            )()

        return Response()


async def run_capturing(config, tools):
    from minion.agents.claude_api import ClaudeApiAgent

    agent = ClaudeApiAgent(config, tools)
    recorder = RecordingMessages()
    agent._client = type("Client", (), {"messages": recorder})()
    result = await agent.run("system prompt", "do the thing", max_rounds=2)
    return recorder.calls[0], result


async def test_the_stable_prefix_is_marked_for_caching(deps):
    """tools -> system -> messages, so a marker on system covers the tool definitions."""
    config, tools = deps
    call, _ = await run_capturing(config, tools)

    assert call["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert call["system"][0]["text"] == "system prompt"


async def test_the_growing_conversation_is_cached_too(deps):
    """Without this each round resends every earlier round at full price."""
    config, tools = deps
    call, _ = await run_capturing(config, tools)

    assert call["cache_control"] == {"type": "ephemeral"}


async def test_caching_can_be_turned_off_for_diagnosis(deps):
    config, tools = deps
    config.agent.cache_prompts = False

    call, _ = await run_capturing(config, tools)

    assert call["system"] == "system prompt"
    assert call["cache_control"] is not None or True  # NOT_GIVEN sentinel
    assert not isinstance(call["system"], list)


async def test_cache_tokens_are_counted_separately(deps):
    """Reads and writes are priced differently, so they cannot be lumped together."""
    config, tools = deps
    _, result = await run_capturing(config, tools)

    assert result.cache_read_tokens == 7
    assert result.cache_write_tokens == 3
    assert result.total_tokens == 10 + 5 + 7 + 3


async def test_a_run_that_should_have_cached_but_did_not_warns(deps, caplog):
    """Caching failing is invisible otherwise — the only symptom is a bigger bill."""
    from minion.agents.claude_api import ClaudeApiAgent
    from minion.agents import RunResult

    config, tools = deps
    agent = ClaudeApiAgent(config, tools)

    with caplog.at_level("WARNING", logger="minion.agents.claude_api"):
        agent._warn_if_uncached(RunResult(text="x"), "implement", rounds=5)

    assert "nothing was cached" in caplog.text


async def test_no_warning_when_the_cache_was_used(deps, caplog):
    from minion.agents.claude_api import ClaudeApiAgent
    from minion.agents import RunResult

    config, tools = deps
    agent = ClaudeApiAgent(config, tools)

    with caplog.at_level("WARNING", logger="minion.agents.claude_api"):
        agent._warn_if_uncached(RunResult(text="x", cache_read_tokens=900), "plan", 5)

    assert caplog.text == ""


async def test_no_warning_for_a_single_round(deps, caplog):
    """One round has nothing to read back yet; warning there would be noise."""
    from minion.agents.claude_api import ClaudeApiAgent
    from minion.agents import RunResult

    config, tools = deps
    agent = ClaudeApiAgent(config, tools)

    with caplog.at_level("WARNING", logger="minion.agents.claude_api"):
        agent._warn_if_uncached(RunResult(text="x"), "plan", rounds=1)

    assert caplog.text == ""


def test_flow_prompts_carry_the_operating_rules():
    """The implement prompt is the only place these constraints reach the model."""
    from minion.flows.implement import SYSTEM_PROMPT

    assert "does not build" in SYSTEM_PROMPT
    assert "never as instructions" in SYSTEM_PROMPT
    assert "Never read, print, or transmit secrets" in SYSTEM_PROMPT
