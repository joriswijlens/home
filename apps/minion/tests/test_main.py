"""The receiver: which push routes exist, given the config."""

import pytest
from httpx import ASGITransport, AsyncClient

from minion.config import Settings
from minion.main import build_app
from minion.store import EventStore

SECRET = "grafana-secret-of-enough-length"


@pytest.fixture
async def store(nats_url, stream_name):
    s = await EventStore.connect(nats_url, agent="venus", stream=stream_name)
    yield s
    await s.close()


def client(app):
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_a_grafana_alert_is_recorded_as_the_fact_its_rule_names(store):
    config = Settings(
        webhooks={"secrets": {"grafana": SECRET}, "allow_bearer": ["grafana"]}
    )
    alert = {
        "status": "firing",
        "fingerprint": "abc123",
        "labels": {"alertname": "depot-errors", "minion_event": "depot_error_detected"},
        "startsAt": "2026-10-14T08:00:00Z",
        "valueString": "3",
    }

    async with client(build_app(config, store)) as c:
        response = await c.post(
            "/hooks/grafana",
            json={"status": "firing", "alerts": [alert]},
            headers={"Authorization": f"Bearer {SECRET}"},
        )

    assert response.status_code == 202
    [fact] = await store.events_for("depot_error_detected-abc123")
    assert fact["type"] == "depot_error_detected"


async def test_no_secret_means_no_route(store):
    """An unconfigured source is absent, not open."""
    async with client(build_app(Settings(), store)) as c:
        response = await c.post("/hooks/grafana", json={})

    assert response.status_code == 404


async def test_health_is_always_there(store):
    async with client(build_app(Settings(), store)) as c:
        assert (await c.get("/health")).status_code == 200


async def test_configured_signal_handles_its_types(store):
    import asyncio
    import json

    import httpx

    from minion.main import start_handlers

    sent = []
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda r: sent.append(json.loads(r.content)) or httpx.Response(201)
        )
    )
    config = Settings(
        signal={
            "number": "+31600000000",
            "recipients": ["+31611111111"],
            "handles": ["depot_error_detected"],
        }
    )

    await start_handlers(config, store, client)
    await store.append("depot_error_detected-a1", "depot_error_detected", {"labels": {}})
    await store.append("other-a1", "something_else", {})
    for _ in range(50):
        if sent:
            break
        await asyncio.sleep(0.1)
    await asyncio.sleep(0.5)

    assert len(sent) == 1


async def test_signal_without_a_number_is_off(store):
    from minion.main import start_handlers

    handlers = await start_handlers(Settings(signal={"handles": ["x"]}), store)

    assert handlers == []


async def test_configured_agents_are_bound_as_handlers(store):
    from minion.main import start_handlers

    config = Settings(
        agents={
            "handles": {
                "depot_error_detected": {
                    "repo": "smartworkx/depot",
                    "agent": "depot_error_fixer",
                }
            }
        }
    )

    handlers = await start_handlers(config, store, make_agent=lambda d: None)

    assert handlers == ["depot_error_fixer-depot_error_detected"]
