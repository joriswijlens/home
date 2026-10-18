import asyncio
import hashlib
import hmac
import time

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from minion.events import Event, EventDispatcher, EventHandler
from minion.sources.webhook import MAX_SKEW_SECONDS, WebhookSource
from minion.store import EventStore

SECRET = "a-secret-of-sufficient-length"
BODY = b'{"flow": "report"}'


class Recorder(EventHandler):
    event_types = ["task"]

    def __init__(self):
        self.seen = []
        self._arrived = asyncio.Event()

    async def handle(self, event):
        self.seen.append(event)
        self._arrived.set()
        return "ok"

    async def delivered(self) -> None:
        """Dispatch is spawned, not awaited, by the route — wait for it to land."""
        await asyncio.wait_for(self._arrived.wait(), timeout=1)


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
async def store(nats_url, stream_name):
    s = await EventStore.connect(nats_url, agent="venus", stream=stream_name)
    yield s
    await s.close()


def build(store, **kwargs):
    """A plain httpx.AsyncClient over the ASGI app — not TestClient.

    TestClient drives the app from a separate thread with its own event loop, which
    the store's NATS connection is not bound to; awaiting it from there hangs rather
    than errors. Everything here runs on one loop instead — the test's.
    """
    dispatcher = EventDispatcher()
    recorder = Recorder()
    dispatcher.register(recorder)

    app = FastAPI()
    source = WebhookSource("ha", ha_mapper, store, SECRET, **kwargs)
    source.register(app, dispatcher)

    client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
    return client, recorder, source


@pytest.fixture
async def rig(store):
    client, recorder, _ = build(store)
    yield client, store, recorder
    await client.aclose()


# -- the endpoint does its job ------------------------------------------------


async def test_signed_payload_is_recorded_and_dispatched(rig):
    client, store, recorder = rig

    response = await client.post("/hooks/ha", content=BODY, headers=signed())

    assert response.status_code == 202
    assert response.json() == {"accepted": True}
    [fact] = await store.events_for("ha-report")
    assert fact["type"] == "task"
    assert fact["payload"]["flow"] == "report"
    assert recorder.seen[0].payload["flow"] == "report"


async def test_unmapped_payload_is_ignored_without_recording(rig):
    client, _, recorder = rig
    body = b'{"something": "else"}'

    response = await client.post("/hooks/ha", content=body, headers=signed(body))

    assert response.status_code == 202
    assert response.json() == {"accepted": False}
    assert recorder.seen == []


async def test_a_mapper_may_return_several_events_from_one_post(store):
    def group(payload):
        return [
            Event(type="task", source="ha", payload={"task_id": f"ha-{n}", "flow": "report"})
            for n in payload["names"]
        ]

    dispatcher = EventDispatcher()
    recorder = Recorder()
    dispatcher.register(recorder)
    app = FastAPI()
    WebhookSource("ha", group, store, SECRET).register(app, dispatcher)
    client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
    body = b'{"names": ["a", "b"]}'

    response = await client.post("/hooks/ha", content=body, headers=signed(body))
    await client.aclose()

    assert response.status_code == 202
    assert [e["type"] for e in await store.events_for("ha-a")] == ["task"]
    assert [e["type"] for e in await store.events_for("ha-b")] == ["task"]


async def test_the_sender_is_not_kept_waiting(rig):
    """A run takes minutes; HA would time out and retry, turning one trigger into three."""
    client, _, _ = rig

    start = time.monotonic()
    await client.post("/hooks/ha", content=BODY, headers=signed())

    assert time.monotonic() - start < 1.0


# -- and refuses everything else ----------------------------------------------


async def test_unsigned_request_is_refused(rig):
    """A POST here starts an agent run, so an open route is remote code execution."""
    client, _, recorder = rig

    response = await client.post("/hooks/ha", json={"flow": "report"})

    assert response.status_code == 401
    assert recorder.seen == []


async def test_wrong_secret_is_refused(rig):
    client, _, recorder = rig

    response = await client.post(
        "/hooks/ha", content=BODY, headers=signed(secret="not-the-right-secret-at-all")
    )

    assert response.status_code == 401
    assert recorder.seen == []


async def test_tampered_body_is_refused(rig):
    """The signature covers the body, so an altered payload no longer matches."""
    client, _, recorder = rig
    headers = signed(BODY)

    response = await client.post(
        "/hooks/ha", content=b'{"flow": "something-else"}', headers=headers
    )

    assert response.status_code == 401
    assert recorder.seen == []


async def test_replayed_request_is_refused(rig):
    """The same captured request must not work twice inside the skew window."""
    client, _, recorder = rig
    headers = signed()

    first = await client.post("/hooks/ha", content=BODY, headers=headers)
    second = await client.post("/hooks/ha", content=BODY, headers=headers)

    assert first.status_code == 202
    assert second.status_code == 401
    await recorder.delivered()
    assert len(recorder.seen) == 1


async def test_old_timestamp_is_refused(rig):
    """A captured request expires, so it cannot be held and used later."""
    client, _, recorder = rig
    stale = str(int(time.time()) - MAX_SKEW_SECONDS - 60)

    response = await client.post("/hooks/ha", content=BODY, headers=signed(timestamp=stale))

    assert response.status_code == 401
    assert recorder.seen == []


async def test_signature_without_timestamp_is_refused(rig):
    client, _, recorder = rig
    headers = signed()
    del headers["X-Minion-Timestamp"]

    response = await client.post("/hooks/ha", content=BODY, headers=headers)

    assert response.status_code == 401
    assert recorder.seen == []


async def test_bearer_is_refused_unless_enabled(rig):
    client, _, recorder = rig

    response = await client.post(
        "/hooks/ha", content=BODY, headers={"Authorization": f"Bearer {SECRET}"}
    )

    assert response.status_code == 401
    assert recorder.seen == []


async def test_bearer_works_when_explicitly_enabled(store):
    client, recorder, _ = build(store, allow_bearer=True)

    response = await client.post(
        "/hooks/ha",
        content=BODY,
        headers={"Authorization": f"Bearer {SECRET}", "Content-Type": "application/json"},
    )

    assert response.status_code == 202
    await recorder.delivered()
    assert len(recorder.seen) == 1
    await client.aclose()


async def test_flooding_is_rate_limited(store):
    """A leaked credential must not drain the token budget in one burst."""
    client, recorder, _ = build(store, max_per_minute=3)

    codes = [
        (await client.post("/hooks/ha", content=BODY, headers=signed())).status_code
        for _ in range(5)
    ]

    assert codes.count(429) == 2
    assert len(recorder.seen) <= 3
    await client.aclose()


async def test_a_source_without_a_secret_refuses_to_exist(store):
    """Failing closed: no secret means no route, rather than an open one."""
    with pytest.raises(ValueError, match="secret"):
        WebhookSource("ha", ha_mapper, store, "")

    with pytest.raises(ValueError, match="16 characters"):
        WebhookSource("ha", ha_mapper, store, "too-short")


async def test_oversized_body_is_refused_before_parsing(rig):
    client, _, recorder = rig
    huge = b'{"flow": "' + b"x" * (300 * 1024) + b'"}'

    response = await client.post("/hooks/ha", content=huge, headers=signed(huge))

    assert response.status_code == 413
    assert recorder.seen == []
