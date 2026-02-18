import pytest

from minion.tools import ToolRegistry, Tool


class FakeTool(Tool):
    name = "fake"
    description = "A fake tool for testing"
    parameters = {"input": {"type": "string", "description": "test input"}}

    async def execute(self, **kwargs) -> str:
        return f"executed with {kwargs}"


async def test_registry_creation() -> None:
    registry = ToolRegistry()
    tool = FakeTool()
    registry.register(tool)

    assert registry.get("fake") is tool
    assert registry.get("nonexistent") is None


async def test_unknown_tool() -> None:
    registry = ToolRegistry()
    result = await registry.execute("nonexistent")
    assert "unknown tool" in result


async def test_anthropic_format() -> None:
    tool = FakeTool()
    fmt = tool.to_anthropic_tool()

    assert fmt["name"] == "fake"
    assert fmt["description"] == "A fake tool for testing"
    assert "properties" in fmt["input_schema"]
    assert "input" in fmt["input_schema"]["properties"]
