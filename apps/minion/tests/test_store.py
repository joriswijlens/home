import json

import pytest

from minion.store import EventStore


@pytest.fixture
def store(tmp_path):
    s = EventStore(str(tmp_path / "test.db"), agent="venus")
    yield s
    s.close()


def test_append_and_read_back(store):
    store.append("task-1", "claimed", {"issue": 7})

    events = store.events_for("task-1")
    assert len(events) == 1
    assert events[0]["type"] == "claimed"
    assert events[0]["agent"] == "venus"
    assert events[0]["payload"] == {"issue": 7}


def test_events_are_ordered(store):
    store.append("task-1", "claimed")
    store.append("task-1", "plan_posted")
    store.append("task-1", "completed")

    assert [e["type"] for e in store.events_for("task-1")] == [
        "claimed",
        "plan_posted",
        "completed",
    ]


def test_events_are_scoped_to_their_task(store):
    store.append("task-1", "claimed")
    store.append("task-2", "claimed")

    assert len(store.events_for("task-1")) == 1
    assert store.events_for("task-3") == []


def test_is_known(store):
    assert not store.is_known("task-1")
    store.append("task-1", "claimed")
    assert store.is_known("task-1")


def test_subscribers_are_notified(store):
    seen = []
    store.subscribe(seen.append)

    store.append("task-1", "claimed", {"issue": 7})

    assert len(seen) == 1
    assert seen[0]["type"] == "claimed"
    assert seen[0]["payload"] == {"issue": 7}


def test_failing_subscriber_does_not_fail_the_append(store):
    """The write is already durable — a broken listener must not report it as failed."""
    def explode(event):
        raise RuntimeError("Loki unreachable")

    seen = []
    store.subscribe(explode)
    store.subscribe(seen.append)

    store.append("task-1", "claimed")

    assert len(store.events_for("task-1")) == 1
    assert len(seen) == 1


def test_subscribers_only_see_committed_facts(store):
    """Notification happens after commit, so a listener can always read what it was told."""
    read_back = []
    store.subscribe(lambda event: read_back.append(store.events_for(event["task_id"])))

    store.append("task-1", "claimed")

    assert len(read_back[0]) == 1


def test_payload_defaults_to_empty(store):
    store.append("task-1", "claimed")
    assert store.events_for("task-1")[0]["payload"] == {}


def test_survives_reopen(tmp_path):
    path = str(tmp_path / "test.db")
    first = EventStore(path, agent="venus")
    first.append("task-1", "claimed")
    first.close()

    second = EventStore(path, agent="venus")
    assert len(second.events_for("task-1")) == 1
    second.close()


def test_log_events_emits_one_json_line(store, caplog):
    from minion.store import log_events

    with caplog.at_level("INFO", logger="minion.store"):
        log_events({"task_id": "task-1", "type": "claimed", "payload": {}})

    assert json.loads(caplog.records[-1].message)["task_id"] == "task-1"
