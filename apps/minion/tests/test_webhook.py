import hashlib
import hmac
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from minion.events import Event, EventDispatcher, EventHandler
from minion.sources.webhook import MAX_SKEW_SECONDS, WebhookSource
from minion.store import EventStore

SECRET = "a-secret-of-sufficient-length"
BODY = b'{"flow": "report"}'


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


def signed(body: bytes = BODY, secret: str = SECRET, timestamp: str | None = None):
    timestamp = timestamp or str(int(time.time()))
    digest = hmac.new(
        secret.encode(), f"{timestamp}.".encode() + body, hashlib.sha256
    ).hexdigest()
    return {
        "X-Minion-Timestamp": timestamp,
        "X-Minion-Signature": f"sha256={digest}",
        "Content-Type": "application/json",
    }


@pytest.fixture
def store(tmp_path):
    s = EventStore(str(tmp_path / "t.db"), agent="venus")
    yield s
    s.close()


def build(store, **kwargs):
    dispatcher = EventDispatcher()
    recorder = Recorder()
    dispatcher.register(recorder)

    app = FastAPI()
    source = WebhookSource("ha", ha_mapper, store, SECRET, **kwargs)
    source.register(app, dispatcher)
    return TestClient(app), recorder, source


@pytest.fixture
def rig(store):
    client, recorder, _ = build(store)
    return client, store, recorder


# -- the endpoint does its job ------------------------------------------------


def test_signed_payload_is_recorded_and_dispatched(rig):
    client, store, recorder = rig

    response = client.post("/hooks/ha", content=BODY, headers=signed())

    assert response.status_code == 202
    assert response.json() == {"accepted": True}
    assert [e["type"] for e in store.events_for("ha-report")] == ["trigger_received"]
    assert recorder.seen[0].payload["flow"] == "report"


def test_unmapped_payload_is_ignored_without_recording(rig):
    client, _, recorder = rig
    body = b'{"something": "else"}'

    response = client.post("/hooks/ha", content=body, headers=signed(body))

    assert response.status_code == 202
    assert response.json() == {"accepted": False}
    assert recorder.seen == []


def test_the_sender_is_not_kept_waiting(rig):
    """A run takes minutes; HA would time out and retry, turning one trigger into three."""
    client, _, _ = rig

    start = time.monotonic()
    client.post("/hooks/ha", content=BODY, headers=signed())

    assert time.monotonic() - start < 1.0


# -- and refuses everything else ----------------------------------------------


def test_unsigned_request_is_refused(rig):
    """A POST here starts an agent run, so an open route is remote code execution."""
    client, _, recorder = rig

    response = client.post("/hooks/ha", json={"flow": "report"})

    assert response.status_code == 401
    assert recorder.seen == []


def test_wrong_secret_is_refused(rig):
    client, _, recorder = rig

    response = client.post(
        "/hooks/ha", content=BODY, headers=signed(secret="not-the-right-secret-at-all")
    )

    assert response.status_code == 401
    assert recorder.seen == []


def test_tampered_body_is_refused(rig):
    """The signature covers the body, so an altered payload no longer matches."""
    client, _, recorder = rig
    headers = signed(BODY)

    response = client.post("/hooks/ha", content=b'{"flow": "something-else"}', headers=headers)

    assert response.status_code == 401
    assert recorder.seen == []


def test_replayed_request_is_refused(rig):
    """The same captured request must not work twice inside the skew window."""
    client, _, recorder = rig
    headers = signed()

    first = client.post("/hooks/ha", content=BODY, headers=headers)
    second = client.post("/hooks/ha", content=BODY, headers=headers)

    assert first.status_code == 202
    assert second.status_code == 401
    assert len(recorder.seen) == 1


def test_old_timestamp_is_refused(rig):
    """A captured request expires, so it cannot be held and used later."""
    client, _, recorder = rig
    stale = str(int(time.time()) - MAX_SKEW_SECONDS - 60)

    response = client.post("/hooks/ha", content=BODY, headers=signed(timestamp=stale))

    assert response.status_code == 401
    assert recorder.seen == []


def test_signature_without_timestamp_is_refused(rig):
    client, _, recorder = rig
    headers = signed()
    del headers["X-Minion-Timestamp"]

    response = client.post("/hooks/ha", content=BODY, headers=headers)

    assert response.status_code == 401
    assert recorder.seen == []


def test_bearer_is_refused_unless_enabled(rig):
    client, _, recorder = rig

    response = client.post(
        "/hooks/ha", content=BODY, headers={"Authorization": f"Bearer {SECRET}"}
    )

    assert response.status_code == 401
    assert recorder.seen == []


def test_bearer_works_when_explicitly_enabled(store):
    client, recorder, _ = build(store, allow_bearer=True)

    response = client.post(
        "/hooks/ha",
        content=BODY,
        headers={"Authorization": f"Bearer {SECRET}", "Content-Type": "application/json"},
    )

    assert response.status_code == 202
    assert len(recorder.seen) == 1


def test_flooding_is_rate_limited(store):
    """A leaked credential must not drain the token budget in one burst."""
    client, recorder, _ = build(store, max_per_minute=3)

    codes = [
        client.post("/hooks/ha", content=BODY, headers=signed()).status_code
        for _ in range(5)
    ]

    assert codes.count(429) == 2
    assert len(recorder.seen) <= 3


def test_a_source_without_a_secret_refuses_to_exist(store):
    """Failing closed: no secret means no route, rather than an open one."""
    with pytest.raises(ValueError, match="secret"):
        WebhookSource("ha", ha_mapper, store, "")

    with pytest.raises(ValueError, match="16 characters"):
        WebhookSource("ha", ha_mapper, store, "too-short")


def test_oversized_body_is_refused_before_parsing(rig):
    client, _, recorder = rig
    huge = b'{"flow": "' + b"x" * (300 * 1024) + b'"}'

    response = client.post("/hooks/ha", content=huge, headers=signed(huge))

    assert response.status_code == 413
    assert recorder.seen == []
