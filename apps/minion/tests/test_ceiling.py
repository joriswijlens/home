"""The ceiling: what Minion's config allows, which a repo's agent can only narrow."""

from minion.agent_definition import AgentDefinition
from minion.agent_worker import apply_ceiling
from minion.config import Ceiling

DEFAULTS = {"read": "allow", "edit": "allow", "bash": "allow", "webfetch": "deny"}


def test_rounds_are_capped():
    agent = AgentDefinition(max_rounds=100)

    assert apply_ceiling(agent, Ceiling(max_rounds=40), DEFAULTS).max_rounds == 40


def test_an_agent_without_rounds_gets_the_ceiling():
    assert apply_ceiling(AgentDefinition(), Ceiling(max_rounds=40), DEFAULTS).max_rounds == 40


def test_an_agent_may_narrow_a_permission():
    agent = AgentDefinition(permission={"bash": "deny"})

    assert apply_ceiling(agent, Ceiling(), DEFAULTS).permission["bash"] == "deny"


def test_an_agent_cannot_widen_a_permission():
    agent = AgentDefinition(permission={"webfetch": "allow"})

    assert apply_ceiling(agent, Ceiling(), DEFAULTS).permission["webfetch"] == "deny"


def test_a_tool_the_ceiling_does_not_name_is_denied():
    agent = AgentDefinition(permission={"task": "allow"})

    assert apply_ceiling(agent, Ceiling(), DEFAULTS).permission["task"] == "deny"


def test_tools_the_agent_does_not_name_keep_the_ceiling():
    permission = apply_ceiling(AgentDefinition(), Ceiling(), DEFAULTS).permission

    assert permission == DEFAULTS


def test_the_ceiling_can_set_its_own_permissions():
    ceiling = Ceiling(permission={"read": "allow"})

    assert apply_ceiling(AgentDefinition(), ceiling, DEFAULTS).permission == {"read": "allow"}


def test_only_mcp_servers_the_ceiling_allows_are_kept():
    """An MCP server is reach — a repo must not be able to add some on its own."""
    agent = AgentDefinition(mcp={"loki": {"type": "remote"}, "other": {"type": "local"}})

    kept = apply_ceiling(agent, Ceiling(mcp=["loki"]), DEFAULTS).mcp

    assert list(kept) == ["loki"]
