import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from minion.events import Event, EventDispatcher, EventHandler
from minion.sources.webhook import WebhookSource
from minion.store import EventStore


class Recorder(EventHandler):
    event_types = ["task"]

    def __init__(self):
        self.seen = []

    async def handle(self, event):
        self.seen.append(event)
        return "ok"


def ha_mapper(payload: dict) -> Event | None:
    """The whole of a push source: payload in, event out."""
    if "flow" not in payload:
        return None
    return Event(
        type="task",
        source="ha",
        payload={"task_id": f"ha-{payload['flow']}", "flow": payload["flow"]},
    )


@pytest.fixture
def rig(tmp_path):
    store = EventStore(str(tmp_path / "t.db"), agent="venus")
    dispatcher = EventDispatcher()
    recorder = Recorder()
    dispatcher.register(recorder)

    app = FastAPI()
    source = WebhookSource("ha", ha_mapper, store)
    source.register(app, dispatcher)

    yield TestClient(app), store, recorder
    store.close()


def test_accepted_payload_is_recorded_and_dispatched(rig):
    client, store, recorder = rig

    response = client.post("/hooks/ha", json={"flow": "report"})

    assert response.status_code == 202
    assert response.json() == {"accepted": True}
    assert [e["type"] for e in store.events_for("ha-report")] == ["trigger_received"]
    assert recorder.seen[0].payload["flow"] == "report"


def test_unmapped_payload_is_ignored_without_recording(rig):
    client, store, recorder = rig

    response = client.post("/hooks/ha", json={"something": "else"})

    assert response.status_code == 202
    assert response.json() == {"accepted": False}
    assert recorder.seen == []


def test_non_json_body_is_rejected(rig):
    client, _, recorder = rig

    response = client.post(
        "/hooks/ha", content=b"not json", headers={"Content-Type": "application/json"}
    )

    assert response.status_code == 400
    assert recorder.seen == []


def test_the_sender_is_not_kept_waiting(rig):
    """A run takes minutes; HA would time out and retry, turning one trigger into three."""
    import time

    client, _, _ = rig

    start = time.monotonic()
    client.post("/hooks/ha", json={"flow": "report"})

    assert time.monotonic() - start < 1.0
