"""The OpenCode backend, against a stand-in binary.

A real `opencode run` needs a provider and a key; what minion owns is the contract
around it — the config it hands over, the events it reads back, the failure it
surfaces. A script on PATH that replays recorded JSON lines covers exactly that.
"""

import json
import os
import stat
import textwrap

import pytest

from minion.agents import Agent, RunResult, create_agent
from minion.agents.opencode import OpenCodeAgent, OpenCodeError, _parse
from minion.config import Settings
from minion.tools import create_registry


def event(kind: str, **part) -> str:
    return json.dumps({"type": kind, "timestamp": 0, "sessionID": "ses_1", "part": part})


STEP = event(
    "step_finish",
    type="step-finish",
    reason="stop",
    cost=0.001,
    tokens={"input": 100, "output": 20, "reasoning": 5, "cache": {"read": 30, "write": 10}},
)


@pytest.fixture
def fake_opencode(tmp_path, monkeypatch):
    """Writes a `opencode` script that dumps argv+env to a file and replays `lines`."""
    record = tmp_path / "record.json"

    def install(lines: list[str], exit_code: int = 0):
        script = tmp_path / "opencode"
        script.write_text(textwrap.dedent(f"""\
            #!/usr/bin/env python3
            import json, os, sys
            json.dump({{"argv": sys.argv[1:], "cwd": os.getcwd(),
                       "config": os.environ.get("OPENCODE_CONFIG_CONTENT"),
                       "env": dict(os.environ)}}, open({str(record)!r}, "w"))
            sys.stdout.write({os.linesep.join(lines)!r} + "\\n")
            sys.exit({exit_code})
            """))
        script.chmod(script.stat().st_mode | stat.S_IEXEC)
        monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ['PATH']}")
        return lambda: json.loads(record.read_text())

    return install


def agent(**overrides) -> OpenCodeAgent:
    config = Settings(agent={"backend": "opencode", "model": "fake/model", **overrides})
    return OpenCodeAgent(config)


# -- the seam ------------------------------------------------------------------


def test_opencode_is_a_registered_backend():
    config = Settings(agent={"backend": "opencode"})
    a = create_agent(config, create_registry(config.tools))
    assert isinstance(a, OpenCodeAgent)
    assert isinstance(a, Agent)


def test_only_the_opencode_module_spawns_it():
    import pathlib

    src = pathlib.Path(__file__).parent.parent / "src" / "minion"
    offenders = [
        p.relative_to(src).as_posix()
        for p in src.rglob("*.py")
        if '"run"' in p.read_text() and "opencode" in p.read_text().lower()
    ]
    assert offenders == ["agents/opencode.py"]


# -- what goes in ----------------------------------------------------------------


async def test_the_run_is_handed_over_as_an_agent_definition(fake_opencode, tmp_path):
    recorded = fake_opencode([event("text", type="text", text="done"), STEP])
    workdir = tmp_path / "repo"
    workdir.mkdir()

    await agent().run("be terse", "fix it", max_rounds=7, label="demo", workdir=str(workdir))

    r = recorded()
    assert r["argv"][:2] == ["run", "--format"]
    assert "--pure" in r["argv"]
    assert r["argv"][-1] == "fix it"
    assert r["argv"][r["argv"].index("--dir") + 1] == str(workdir)
    assert r["cwd"] == str(workdir)

    definition = json.loads(r["config"])["agent"]["minion"]
    assert definition["prompt"] == "be terse"
    assert definition["steps"] == 7
    assert definition["model"] == "fake/model"
    assert definition["permission"]["bash"] == "allow"
    assert definition["permission"]["webfetch"] == "deny"


async def test_provider_and_env_pass_through(fake_opencode, monkeypatch):
    recorded = fake_opencode([event("text", type="text", text="ok")])
    config = Settings(
        agent={"backend": "opencode", "model": "acme/m"},
        opencode={
            "provider": {"acme": {"npm": "@ai-sdk/openai-compatible"}},
            "env": {"ACME_API_KEY": "k"},
        },
    )

    await OpenCodeAgent(config).run("s", "p", 3)

    r = recorded()
    # Settings deep-merges over default.yml, so the shipped provider sits alongside.
    assert json.loads(r["config"])["provider"]["acme"] == {"npm": "@ai-sdk/openai-compatible"}
    assert r["env"]["ACME_API_KEY"] == "k"


# -- what comes out --------------------------------------------------------------


async def test_the_last_text_is_the_result_and_tokens_are_summed(fake_opencode):
    fake_opencode([
        event("text", type="text", text="thinking about it"),
        STEP,
        event("tool_use", type="tool", tool="bash"),
        STEP,
        event("text", type="text", text="  the answer  "),
    ])

    run = await agent().run("s", "p", 3)

    assert run.text == "the answer"
    assert run.input_tokens == 200
    assert run.output_tokens == 50  # output + reasoning, both billed as output
    assert run.cache_read_tokens == 60
    assert run.cache_write_tokens == 20


def test_non_json_lines_are_ignored():
    run, errors = _parse("starting up\n" + STEP + "\n{not json\n")
    assert errors == []
    assert run.input_tokens == 100


async def test_a_provider_error_is_raised_with_its_message(fake_opencode):
    fake_opencode([
        json.dumps({
            "type": "error", "timestamp": 0, "sessionID": "s",
            "error": {"name": "APIError", "data": {"message": "model requires more memory"}},
        })
    ])

    with pytest.raises(OpenCodeError, match="model requires more memory"):
        await agent().run("s", "p", 3)


async def test_a_non_zero_exit_without_events_is_raised(fake_opencode):
    fake_opencode(["crashed before the server came up"], exit_code=2)

    with pytest.raises(OpenCodeError, match="exited 2"):
        await agent().run("s", "p", 3)


async def test_a_run_reports_usage_the_worker_can_count(fake_opencode):
    fake_opencode([STEP, event("text", type="text", text="x")])
    run = await agent().run("s", "p", 3)
    assert isinstance(run, RunResult)
    assert run.usage()["output_tokens"] == 25


async def test_mcp_and_skills_pass_through(fake_opencode):
    recorded = fake_opencode([event("text", type="text", text="ok")])
    config = Settings(
        agent={"backend": "opencode", "model": "fake/m"},
        opencode={
            "mcp": {"grafana": {"type": "local", "command": ["mcp-grafana"]}},
            "skills": {"paths": ["/opt/skills"]},
        },
    )

    await OpenCodeAgent(config).run("s", "p", 3)

    handed = json.loads(recorded()["config"])
    assert handed["mcp"]["grafana"]["command"] == ["mcp-grafana"]
    assert handed["skills"] == {"paths": ["/opt/skills"]}
