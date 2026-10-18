"""The agent worker: a fact in, the repo's own agent run against a fresh checkout."""

import asyncio
import json
from pathlib import Path

import pytest

from minion.agents import RunResult
from minion.agent_worker import AgentWorker
from minion.config import AgentHandlerConfig, AgentsConfig, Ceiling, TasksConfig
from minion.store import EventStore

TYPE = "depot_error_detected"
TASK = f"{TYPE}-abc123"
FACT = {
    "task_id": TASK,
    "type": TYPE,
    "payload": {"fingerprint": "abc123", "labels": {"error_type": "ServletException"}},
}
VERDICT = {"outcome": "fix_proposed", "pr": "https://github.com/smartworkx/depot/pull/9"}
DEFAULTS = {"read": "allow", "edit": "allow", "bash": "allow"}


@pytest.fixture
async def store(nats_url, stream_name):
    s = await EventStore.connect(nats_url, agent="venus", stream=stream_name)
    yield s
    await s.close()


class FakeAgent:
    def __init__(self, definition, text: str, tokens: int = 100, hang: bool = False):
        self.definition = definition
        self.text = text
        self.tokens = tokens
        self.hang = hang
        self.calls: list[dict] = []

    async def run(self, system_prompt, prompt, max_rounds, label="agent", workdir=None):
        self.calls.append(
            {"system": system_prompt, "prompt": prompt, "rounds": max_rounds,
             "workdir": workdir, "files": sorted(p.name for p in Path(workdir).iterdir())}
        )
        if self.hang:
            await asyncio.sleep(3600)
        return RunResult(text=self.text, input_tokens=self.tokens)


class Rig:
    """Fake checkout, fake apm, fake agent — everything around the worker."""

    def __init__(self, store, tmp_path, *, agent_yml="max_rounds: 100\n", apm=False,
                 text=f"Fixed it.\n{json.dumps(VERDICT)}", has_agent=True,
                 tasks=None, ceiling=None):
        self.store = store
        self.tmp_path = tmp_path
        self.agent_yml = agent_yml
        self.apm = apm
        self.has_agent = has_agent
        self.text = text
        self.checkouts: list[tuple] = []
        self.installs: list[Path] = []
        self.agents: list[FakeAgent] = []
        self.config = AgentsConfig(
            checkout_dir=str(tmp_path / "checkouts"),
            apm_cache_dir=str(tmp_path / "apm"),
            handles={
                TYPE: AgentHandlerConfig(
                    repo="smartworkx/depot",
                    agent="depot_error_fixer",
                    ceiling=ceiling or Ceiling(max_rounds=40),
                )
            },
        )
        self.worker = AgentWorker(
            store, self.make_agent, self.config, tasks or TasksConfig(), DEFAULTS,
            checkout=self.checkout, install=self.install,
        )

    async def checkout(self, repo: str, ref: str, dest: Path) -> None:
        self.checkouts.append((repo, ref, dest))
        dest.mkdir(parents=True)
        (dest / "src").mkdir()
        if self.has_agent:
            agent = dest / ".agents" / "agents" / "depot_error_fixer"
            agent.mkdir(parents=True)
            (agent / "agent.yml").write_text(self.agent_yml)
            (agent / "prompt.md").write_text("You fix depot production errors.")
            if self.apm:
                (agent / "apm.yml").write_text("dependencies: {}\n")
                (agent / "apm.lock.yaml").write_text("lock: 1\n")

    async def install(self, agent_dir: Path, cache: Path) -> Path:
        self.installs.append(agent_dir)
        skills = cache / ".agents" / "skills"
        skills.mkdir(parents=True, exist_ok=True)
        return skills

    def make_agent(self, definition):
        agent = FakeAgent(definition, self.text, hang=getattr(self, "hang", False))
        self.agents.append(agent)
        return agent

    async def types(self) -> list[str]:
        return [e["type"] for e in await self.store.events_for(TASK)]


async def test_the_repos_agent_runs_in_a_fresh_checkout(store, tmp_path):
    rig = Rig(store, tmp_path)

    await rig.worker.process(FACT)

    [(repo, ref, dest)] = rig.checkouts
    assert (repo, ref) == ("smartworkx/depot", "main")
    [call] = rig.agents[0].calls
    assert call["workdir"] == str(dest)
    assert "src" in call["files"]
    assert call["system"] == "You fix depot production errors."
    assert "ServletException" in call["prompt"]


async def test_the_verdict_becomes_a_fact_and_the_run_is_recorded(store, tmp_path):
    rig = Rig(store, tmp_path)

    await rig.worker.process(FACT)

    assert await rig.types() == ["claimed", "fix_proposed", "completed"]
    events = await store.events_for(TASK)
    assert events[1]["payload"]["pr"] == VERDICT["pr"]
    assert events[2]["payload"]["usage"]["input_tokens"] == 100
    assert events[2]["payload"]["type"] == TYPE


async def test_the_checkout_is_removed_afterwards(store, tmp_path):
    rig = Rig(store, tmp_path)

    await rig.worker.process(FACT)

    assert not rig.checkouts[0][2].exists()


async def test_the_ceiling_applies_to_the_repos_agent(store, tmp_path):
    rig = Rig(store, tmp_path, agent_yml="max_rounds: 100\npermission: {webfetch: allow}\n")

    await rig.worker.process(FACT)

    definition = rig.agents[0].definition
    assert definition.max_rounds == 40
    assert definition.permission["webfetch"] == "deny"
    assert rig.agents[0].calls[0]["rounds"] == 40


async def test_apm_installs_once_per_lock_and_outside_the_checkout(store, tmp_path):
    rig = Rig(store, tmp_path, apm=True)

    await rig.worker.process(FACT)
    await rig.worker.process({**FACT, "task_id": f"{TYPE}-other"})

    assert len(rig.installs) == 1
    skills = rig.agents[0].definition.skills_dir
    assert skills is not None and str(tmp_path / "apm") in str(skills)
    assert skills == rig.agents[1].definition.skills_dir


async def test_a_completed_task_is_not_run_again(store, tmp_path):
    """Grafana repeats a firing alert every 24h; the fix was already attempted."""
    rig = Rig(store, tmp_path)

    await rig.worker.process(FACT)
    await rig.worker.process(FACT)

    assert len(rig.agents) == 1


async def test_a_repo_without_the_agent_is_a_recorded_failure(store, tmp_path):
    rig = Rig(store, tmp_path, has_agent=False)

    with pytest.raises(FileNotFoundError):
        await rig.worker.process(FACT)

    events = await store.events_for(TASK)
    assert [e["type"] for e in events] == ["claimed", "failed"]
    assert "depot_error_fixer" in events[1]["payload"]["error"]
    assert rig.agents == []


async def test_no_verdict_still_completes_without_an_outcome_fact(store, tmp_path):
    rig = Rig(store, tmp_path, text="I looked around.")

    await rig.worker.process(FACT)

    assert await rig.types() == ["claimed", "completed"]


async def test_over_budget_records_it_and_does_not_run(store, tmp_path):
    rig = Rig(store, tmp_path, ceiling=Ceiling(max_rounds=40, daily_token_budget=150))

    await rig.worker.process({**FACT, "task_id": f"{TYPE}-first"})
    await rig.worker.process({**FACT, "task_id": f"{TYPE}-second"})
    await rig.worker.process(FACT)

    assert len(rig.agents) == 2
    assert await rig.types() == ["budget_exceeded"]


async def test_a_run_that_hangs_is_stopped_and_recorded(store, tmp_path):
    rig = Rig(store, tmp_path, tasks=TasksConfig(run_timeout_minutes=0.01))
    rig.hang = True

    with pytest.raises(asyncio.TimeoutError):
        await rig.worker.process(FACT)

    assert await rig.types() == ["claimed", "timed_out"]


async def test_start_binds_the_agent_as_handler_of_its_type(store, tmp_path):
    rig = Rig(store, tmp_path)

    await rig.worker.start()
    await store.append(TASK, TYPE, FACT["payload"])
    for _ in range(50):
        if "completed" in await rig.types():
            break
        await asyncio.sleep(0.1)

    assert "completed" in await rig.types()
