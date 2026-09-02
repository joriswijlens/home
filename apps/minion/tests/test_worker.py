import pytest

from minion.events import Event
from minion.flows import Flow
from minion.providers import Task, TaskProvider
from minion.state import CLAIMED, COMPLETED, FAILED
from minion.store import EventStore
from minion.worker import Worker


_DEFAULT_CONTEXT = {"ref": "7", "title": "t"}


class FakeProvider(TaskProvider):
    """A provider with no GitHub in it — the point of the seam."""

    name = "fake"

    def __init__(self, claim_succeeds=True, context=_DEFAULT_CONTEXT):
        self.claim_succeeds = claim_succeeds
        self._context = context
        self.reported = []
        self.released = []

    async def start(self, dispatcher): ...
    async def stop(self): ...

    async def claim(self, task):
        return self.claim_succeeds

    async def context(self, task):
        return self._context

    async def report(self, task, outcome, payload):
        self.reported.append((outcome, payload))

    async def release(self, task):
        self.released.append(task.id)


class FakeAgent:
    def __init__(self, result="done", explode=False):
        self.result = result
        self.explode = explode
        self.calls = []

    async def run(self, system_prompt, prompt, max_rounds, label="agent"):
        if self.explode:
            raise RuntimeError("model unavailable")
        self.calls.append(prompt)
        return self.result


FLOW = Flow(
    name="demo",
    system_prompt="sys",
    max_rounds=5,
    build_prompt=lambda ctx: f"work on {ctx['ref']}",
)

TASK = Task(id="task-1", flow="demo", ref="7", title="t")


@pytest.fixture
def store(tmp_path):
    s = EventStore(str(tmp_path / "t.db"), agent="venus")
    yield s
    s.close()


def worker(store, provider, agent):
    return Worker(agent, store, {"fake": provider}, {"demo": FLOW})


def types(store, task_id="task-1"):
    return [e["type"] for e in store.events_for(task_id)]


async def test_happy_path_records_claim_and_completion(store):
    provider, agent = FakeProvider(), FakeAgent(result="the plan")
    event = Event(type="task", source="fake", payload={"task": TASK})

    result = await worker(store, provider, agent).handle(event)

    assert result == "the plan"
    assert types(store) == [CLAIMED, COMPLETED]
    assert provider.reported == [(COMPLETED, {"result": "the plan"})]


async def test_losing_the_claim_does_nothing_at_all(store):
    """A worker that lost the race must not run, report, or record anything."""
    provider, agent = FakeProvider(claim_succeeds=False), FakeAgent()
    event = Event(type="task", source="fake", payload={"task": TASK})

    assert await worker(store, provider, agent).handle(event) is None
    assert types(store) == []
    assert agent.calls == []
    assert provider.reported == []


async def test_unworkable_context_is_recorded_as_failed(store):
    provider, agent = FakeProvider(context=None), FakeAgent()
    event = Event(type="task", source="fake", payload={"task": TASK})

    assert await worker(store, provider, agent).handle(event) is None
    assert types(store) == [CLAIMED, FAILED]
    assert agent.calls == []


async def test_failure_records_and_hands_the_task_back(store):
    provider, agent = FakeProvider(), FakeAgent(explode=True)
    event = Event(type="task", source="fake", payload={"task": TASK})

    with pytest.raises(RuntimeError):
        await worker(store, provider, agent).handle(event)

    assert types(store) == [CLAIMED, FAILED]
    assert provider.released == ["task-1"]
    assert provider.reported == []


async def test_the_flow_receives_the_provider_context(store):
    provider, agent = FakeProvider(context={"ref": "42", "title": "x"}), FakeAgent()
    event = Event(type="task", source="fake", payload={"task": TASK})

    await worker(store, provider, agent).handle(event)

    assert agent.calls == ["work on 42"]


async def test_failure_details_are_kept(store):
    provider, agent = FakeProvider(), FakeAgent(explode=True)
    event = Event(type="task", source="fake", payload={"task": TASK})

    with pytest.raises(RuntimeError):
        await worker(store, provider, agent).handle(event)

    failed = store.events_for("task-1")[-1]
    assert "model unavailable" in failed["payload"]["error"]
