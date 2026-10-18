import asyncio
import json

import pytest

from minion.store import EventStore, HandlerAlreadyBound


@pytest.fixture
async def store(nats_url, stream_name):
    s = await EventStore.connect(nats_url, agent="venus", stream=stream_name)
    yield s
    await s.close()


async def test_append_and_read_back(store):
    await store.append("task-1", "claimed", {"issue": 7})

    events = await store.events_for("task-1")
    assert len(events) == 1
    assert events[0]["type"] == "claimed"
    assert events[0]["agent"] == "venus"
    assert events[0]["payload"] == {"issue": 7}


async def test_events_are_ordered(store):
    await store.append("task-1", "claimed")
    await store.append("task-1", "plan_posted")
    await store.append("task-1", "completed")

    events = await store.events_for("task-1")
    assert [e["type"] for e in events] == ["claimed", "plan_posted", "completed"]


async def test_events_are_scoped_to_their_task(store):
    await store.append("task-1", "claimed")
    await store.append("task-2", "claimed")

    assert len(await store.events_for("task-1")) == 1
    assert await store.events_for("task-3") == []


async def test_is_known(store):
    assert not await store.is_known("task-1")
    await store.append("task-1", "claimed")
    assert await store.is_known("task-1")


async def test_payload_defaults_to_empty(store):
    await store.append("task-1", "claimed")
    assert (await store.events_for("task-1"))[0]["payload"] == {}


async def test_since_returns_events_after_a_cutoff(store):
    from datetime import datetime, timedelta, timezone

    before = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    await store.append("task-1", "claimed")
    await store.append("task-2", "claimed")

    events = await store.since(before)
    assert len(events) == 2


async def test_since_excludes_events_before_the_cutoff(store):
    from datetime import datetime, timedelta, timezone

    await store.append("task-1", "claimed")
    future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()

    assert await store.since(future) == []


async def test_last_events_returns_the_newest_per_task(store):
    await store.append("task-1", "claimed")
    await store.append("task-1", "completed")
    await store.append("task-2", "claimed")

    last = {e["task_id"]: e["type"] for e in await store.last_events()}
    assert last == {"task-1": "completed", "task-2": "claimed"}


async def test_survives_reconnect(nats_url, stream_name):
    """A restart must resume against the same durable stream, not lose it."""
    first = await EventStore.connect(nats_url, agent="venus", stream=stream_name)
    await first.append("task-1", "claimed")
    await first.close()

    second = await EventStore.connect(nats_url, agent="venus", stream=stream_name)
    assert len(await second.events_for("task-1")) == 1
    await second.close()


# -- consume(): durable vs. ephemeral subscribers ------------------------------


async def test_a_durable_consumer_sees_events_appended_before_it_subscribed(store):
    """The whole point of durability — catch-up, not just a live tail."""
    await store.append("task-1", "claimed")

    seen = []
    await store.consume("worker", seen.append)
    await asyncio.sleep(0.3)

    assert [e["type"] for e in seen] == ["claimed"]


async def test_a_durable_consumer_also_sees_new_events(store):
    seen = []
    await store.consume("worker", seen.append)
    await asyncio.sleep(0.1)

    await store.append("task-1", "claimed")
    await asyncio.sleep(0.3)

    assert [e["type"] for e in seen] == ["claimed"]


async def test_a_durable_consumers_position_persists_across_reconnect(
    nats_url, stream_name
):
    """A restart must not redeliver what was already handled — nor lose what wasn't."""
    first = await EventStore.connect(nats_url, agent="venus", stream=stream_name)
    seen_first = []
    await first.consume("worker", seen_first.append)
    await first.append("task-1", "claimed")
    await asyncio.sleep(0.3)
    await first.close()

    assert len(seen_first) == 1

    second = await EventStore.connect(nats_url, agent="venus", stream=stream_name)
    seen_second = []
    await second.consume("worker", seen_second.append)
    await second.append("task-2", "claimed")
    await asyncio.sleep(0.3)
    await second.close()

    # Only the new fact — not task-1 again.
    assert [e["task_id"] for e in seen_second] == ["task-2"]


async def test_two_durable_consumers_each_see_everything_independently(store):
    """Fan-out: the worker and a future subscriber must not steal each other's facts."""
    seen_a, seen_b = [], []
    await store.consume("worker", seen_a.append)
    await store.consume("other", seen_b.append)
    await asyncio.sleep(0.1)

    await store.append("task-1", "claimed")
    await asyncio.sleep(0.3)

    assert [e["type"] for e in seen_a] == ["claimed"]
    assert [e["type"] for e in seen_b] == ["claimed"]


async def test_a_failing_subscriber_does_not_stop_the_consumer_loop(store):
    """The fact is already durable — one bad handler call must not lose the next one."""
    calls = []

    def flaky(event):
        calls.append(event["type"])
        if event["type"] == "first":
            raise RuntimeError("boom")

    await store.consume("worker", flaky)
    await store.append("task-1", "first")
    await store.append("task-1", "second")
    await asyncio.sleep(0.3)

    assert calls == ["first", "second"]


async def test_an_async_handler_is_awaited(store):
    seen = []

    async def handler(event):
        await asyncio.sleep(0)
        seen.append(event["type"])

    await store.consume("worker", handler)
    await store.append("task-1", "claimed")
    await asyncio.sleep(0.3)

    assert seen == ["claimed"]


def test_log_events_emits_one_json_line(caplog):
    with caplog.at_level("INFO", logger="minion.store"):
        from minion.store import log_events

        log_events({"task_id": "task-1", "type": "claimed", "payload": {}})

    assert json.loads(caplog.records[-1].message)["task_id"] == "task-1"


# -- the type is a subject token: one type, one handler ------------------------


async def test_a_handler_sees_only_its_type(store):
    await store.append("task-1", "depot_error_detected", {"n": 1})
    await store.append("task-1", "claimed")
    await store.append("task-2", "depot_error_detected", {"n": 2})

    seen = []
    await store.handle("fixer", "depot_error_detected", seen.append)
    await asyncio.sleep(0.5)

    assert [e["payload"]["n"] for e in seen] == [1, 2]


async def test_different_handlers_on_one_type_each_get_every_fact(nats_url, stream_name):
    """Fixer on Venus, Signal on Mars: both react to the same fact."""
    venus = await EventStore.connect(nats_url, agent="venus", stream=stream_name)
    mars = await EventStore.connect(nats_url, agent="mars", stream=stream_name)
    fixed, signalled = [], []
    await venus.handle("fixer", "x", fixed.append)
    await mars.handle("signal", "x", signalled.append)

    for n in range(5):
        await venus.append(f"task-{n}", "x")
    await asyncio.sleep(0.5)

    assert len(fixed) == len(signalled) == 5
    await venus.close()
    await mars.close()


async def test_a_handler_runs_on_one_worker_only(nats_url, stream_name):
    """A second process binding the same handler is refused, not load-balanced."""
    venus = await EventStore.connect(nats_url, agent="venus", stream=stream_name)
    laptop = await EventStore.connect(nats_url, agent="laptop", stream=stream_name)
    await venus.handle("fixer", "x", lambda e: None)

    with pytest.raises(HandlerAlreadyBound):
        await laptop.handle("fixer", "x", lambda e: None)

    await venus.close()
    await laptop.close()


async def test_a_handler_can_rebind_after_its_worker_stopped(nats_url, stream_name):
    """Exclusive while running — a restart, or a move to another machine, still works."""
    first = await EventStore.connect(nats_url, agent="venus", stream=stream_name)
    await first.handle("fixer", "x", lambda e: None)
    await first.close()

    second = await EventStore.connect(nats_url, agent="laptop", stream=stream_name)
    seen = []
    await second.handle("fixer", "x", seen.append)
    await second.append("task-1", "x")
    await asyncio.sleep(0.5)

    assert len(seen) == 1
    await second.close()


@pytest.mark.parametrize("bad", ["a.b", "*", ">", "", "has space"])
async def test_a_type_that_is_not_one_plain_token_is_refused(store, bad):
    with pytest.raises(ValueError):
        await store.append("task-1", bad)


async def test_a_failing_handler_gets_the_fact_again(store, monkeypatch):
    """A handler that could not do its side effect must not lose the fact."""
    import minion.store as store_module

    monkeypatch.setattr(store_module, "RETRY_DELAY_SECONDS", 0.1)
    attempts = []

    def flaky(event):
        attempts.append(event)
        if len(attempts) == 1:
            raise RuntimeError("signal-api down")

    await store.handle("signal", "x", flaky)
    await store.append("task-1", "x")
    await asyncio.sleep(1)

    assert len(attempts) == 2
