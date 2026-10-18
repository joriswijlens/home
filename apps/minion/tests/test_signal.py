"""The Signal handler: one message per detected error, never two."""

import json

import httpx
import pytest

from minion.config import SignalConfig
from minion.handlers.signal import SignalHandler, message
from minion.store import EventStore

CONFIG = SignalConfig(
    url="http://mars:8081", number="+31600000000", recipients=["+31611111111"]
)

FACT = {
    "task_id": "depot_error_detected-abc123",
    "type": "depot_error_detected",
    "payload": {
        "fingerprint": "abc123",
        "labels": {
            "alertname": "depot-errors",
            "minion_event": "depot_error_detected",
            "error_type": "ServletException",
            "tenant": "pax",
        },
        "value": "3",
        "started_at": "2026-10-14T08:00:00Z",
        "url": "https://grafana.example/alerting/abc123",
    },
}


@pytest.fixture
async def store(nats_url, stream_name):
    s = await EventStore.connect(nats_url, agent="venus", stream=stream_name)
    yield s
    await s.close()


def signal_api(status: int = 201):
    sent: list[dict] = []

    def respond(request: httpx.Request) -> httpx.Response:
        sent.append({"url": str(request.url), "body": json.loads(request.content)})
        return httpx.Response(status)

    return sent, httpx.AsyncClient(transport=httpx.MockTransport(respond))


def test_the_message_says_what_fired_and_where_to_look():
    text = message(FACT)

    assert "depot-errors" in text
    assert "error_type=ServletException" in text
    assert "tenant=pax" in text
    assert "minion_event" not in text
    assert "https://grafana.example/alerting/abc123" in text


async def test_a_fact_is_sent_to_every_recipient(store):
    sent, client = signal_api()

    await SignalHandler(CONFIG, store, client).on_fact(FACT)

    [request] = sent
    assert request["url"] == "http://mars:8081/v2/send"
    assert request["body"]["number"] == "+31600000000"
    assert request["body"]["recipients"] == ["+31611111111"]
    assert "depot-errors" in request["body"]["message"]


async def test_the_same_alert_again_sends_nothing(store):
    """Grafana repeats a firing alert every 24h; it is still the same error."""
    sent, client = signal_api()
    handler = SignalHandler(CONFIG, store, client)

    await handler.on_fact(FACT)
    await handler.on_fact(FACT)

    assert len(sent) == 1
    assert [e["type"] for e in await store.events_for(FACT["task_id"])] == ["signal_sent"]


async def test_a_failed_send_raises_and_records_nothing(store):
    """Raising is what makes the store redeliver it later."""
    sent, client = signal_api(status=500)

    with pytest.raises(httpx.HTTPStatusError):
        await SignalHandler(CONFIG, store, client).on_fact(FACT)

    assert await store.events_for(FACT["task_id"]) == []
