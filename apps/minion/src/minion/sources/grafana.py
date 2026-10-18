"""Grafana alert webhook → one fact per firing alert.

Grafana owns what is firing and how often (grouping, repeat interval); minion only
records it. The alert rule names its own fact with a `minion_event` label — e.g.
`depot_error_detected` — so nothing here knows about depot, and a new alert rule is
Grafana config plus a worker that owns the type, never a code change.

A POST carries a *group* of alerts, so the mapper returns a list. The alert's
fingerprint is the task's identity: the same alert repeating maps to the same task,
which is what lets the log dedupe it.
"""

import logging

from minion.events import Event
from minion.store import TOKEN

logger = logging.getLogger(__name__)

EVENT_LABEL = "minion_event"


def grafana_mapper(payload: dict) -> list[Event] | None:
    events = []
    for alert in payload.get("alerts", []):
        if alert.get("status") != "firing":
            continue
        labels = alert.get("labels", {})
        type = labels.get(EVENT_LABEL, "")
        if not TOKEN.match(type):
            logger.warning(
                "Grafana alert %r has no usable %s label — ignored",
                labels.get("alertname"),
                EVENT_LABEL,
            )
            continue
        fingerprint = alert["fingerprint"]
        events.append(
            Event(
                type=type,
                source="grafana",
                payload={
                    "task_id": f"{type}-{fingerprint}",
                    "fingerprint": fingerprint,
                    "labels": labels,
                    "value": alert.get("valueString", ""),
                    "started_at": alert.get("startsAt", ""),
                    "url": alert.get("generatorURL", ""),
                },
            )
        )
    return events or None
