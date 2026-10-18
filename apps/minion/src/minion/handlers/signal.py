"""Signal: one message per fact of the types it handles.

Signal is a side effect that cannot be asked "did this already happen?" — signal-api
has no sent-message query — so a `signal_sent` fact is the guard. That also makes
Grafana's 24h repeat of a still-firing alert silent: same alert, same task, already
sent. A failed send raises, which makes the store hand the fact back later.
"""

import logging

import httpx

from minion.config import SignalConfig
from minion.store import EventStore

logger = logging.getLogger(__name__)

SENT = "signal_sent"

# Labels that are minion's plumbing rather than something a person needs to read.
HIDDEN_LABELS = {"minion_event", "alertname"}


def message(fact: dict) -> str:
    payload = fact["payload"]
    labels = payload.get("labels", {})
    details = ", ".join(
        f"{k}={v}" for k, v in labels.items() if k not in HIDDEN_LABELS
    )
    lines = [
        f"{labels.get('alertname', fact['type'])}: {details}",
        f"value {payload.get('value', '?')} since {payload.get('started_at', '?')}",
    ]
    if payload.get("url"):
        lines.append(payload["url"])
    return "\n".join(lines)


class SignalHandler:
    def __init__(
        self, config: SignalConfig, store: EventStore, client: httpx.AsyncClient
    ) -> None:
        self._config = config
        self._store = store
        self._client = client

    async def on_fact(self, fact: dict) -> None:
        events = await self._store.events_for(fact["task_id"])
        if any(e["type"] == SENT for e in events):
            logger.info("Signal already sent for %s", fact["task_id"])
            return

        response = await self._client.post(
            f"{self._config.url}/v2/send",
            json={
                "number": self._config.number,
                "recipients": self._config.recipients,
                "message": message(fact),
            },
        )
        response.raise_for_status()
        await self._store.append(fact["task_id"], SENT, {"type": fact["type"]})
