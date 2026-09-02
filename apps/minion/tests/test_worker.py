import pytest

from minion.agents import RunResult
from minion.config import TasksConfig
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
    def __init__(self, result="done", explode=False, tokens=0, hangs=False):
        self.result = result
        self.explode = explode
        self.tokens = tokens
        self.hangs = hangs
        self.calls = []

    async def run(self, system_prompt, prompt, max_rounds, label="agent"):
        if self.explode:
            raise RuntimeError("model unavailable")
        if self.hangs:
            import asyncio

            await asyncio.sleep(3600)
        self.calls.append(prompt)
        return RunResult(text=self.result, output_tokens=self.tokens)


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


def worker(store, provider, agent, tasks=None):
    return Worker(agent, store, {"fake": provider}, {"demo": FLOW}, tasks)


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


async def test_a_wedged_run_is_stopped_and_handed_back(store):
    """A hung agent otherwise holds its claim and burns tokens until staleness expires."""
    provider, agent = FakeProvider(), FakeAgent(hangs=True)
    tasks = TasksConfig(run_timeout_minutes=0)  # 0 -> immediate timeout
    event = Event(type="task", source="fake", payload={"task": TASK})

    result = await worker(store, provider, agent, tasks).handle(event)

    assert result is None
    assert types(store) == [CLAIMED, "timed_out"]
    assert provider.released == ["task-1"]
    assert provider.reported == []


async def test_usage_is_recorded_on_completion(store):
    provider, agent = FakeProvider(), FakeAgent(tokens=1234)
    event = Event(type="task", source="fake", payload={"task": TASK})

    await worker(store, provider, agent).handle(event)

    completed = store.events_for("task-1")[-1]
    assert completed["payload"]["usage"]["output_tokens"] == 1234


async def test_the_daily_budget_stops_a_run_before_it_starts(store):
    """The check must precede the claim — spending is what we are trying to avoid."""
    store.append("earlier-task", COMPLETED, {"usage": {"output_tokens": 900}})

    provider, agent = FakeProvider(), FakeAgent()
    tasks = TasksConfig(daily_token_budget=500)
    event = Event(type="task", source="fake", payload={"task": TASK})

    assert await worker(store, provider, agent, tasks).handle(event) is None
    assert types(store) == ["budget_exceeded"]
    assert agent.calls == []
    assert provider.reported == []


async def test_budget_of_zero_means_no_limit(store):
    store.append("earlier-task", COMPLETED, {"usage": {"output_tokens": 10_000_000}})

    provider, agent = FakeProvider(), FakeAgent()
    event = Event(type="task", source="fake", payload={"task": TASK})

    assert await worker(store, provider, agent).handle(event) == "done"


async def test_runs_do_not_overlap(store):
    """One run at a time on a 1GB Pi; the rest queue rather than pile up."""
    import asyncio

    running = 0
    peak = 0

    class CountingAgent(FakeAgent):
        async def run(self, *args, **kwargs):
            nonlocal running, peak
            running += 1
            peak = max(peak, running)
            await asyncio.sleep(0.01)
            running -= 1
            return RunResult(text="done")

    provider = FakeProvider()
    w = worker(store, provider, CountingAgent(), TasksConfig(max_concurrent_runs=1))

    await asyncio.gather(*[
        w.handle(Event(type="task", source="fake", payload={"task": TASK}))
        for _ in range(4)
    ])

    assert peak == 1


async def test_stale_claims_are_handed_back(store):
    from datetime import datetime, timedelta, timezone

    from minion.worker import reclaim_stale

    old = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    with store._lock:
        store._conn.execute(
            "INSERT INTO events (task_id, agent, type, payload, timestamp) "
            'VALUES (?, ?, ?, ?, ?)',
            ("fake-demo-7", "venus", CLAIMED, '{"ref": "7", "flow": "demo"}', old),
        )
        store._conn.commit()

    provider = FakeProvider()
    count = await reclaim_stale(store, {"fake": provider}, TasksConfig())

    assert count == 1
    assert provider.released == ["fake-demo-7"]
    assert types(store, "fake-demo-7") == [CLAIMED, "released"]


async def test_a_fresh_claim_is_left_alone(store):
    from minion.worker import reclaim_stale

    store.append("fake-demo-8", CLAIMED, {"ref": "8", "flow": "demo"})
    provider = FakeProvider()

    assert await reclaim_stale(store, {"fake": provider}, TasksConfig()) == 0
    assert provider.released == []
