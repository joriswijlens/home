import json
import logging
import sqlite3
import threading
from datetime import datetime, timezone
from typing import Callable

logger = logging.getLogger(__name__)

Subscriber = Callable[[dict], None]


class EventStore:
    """Append-only log of facts. The record of what happened; state is derived from it.

    `append` commits before notifying subscribers, so listeners only ever see durable
    facts. A failing subscriber is logged and skipped — the write already succeeded and
    must not be reported as failed.
    """

    def __init__(self, db_path: str, agent: str) -> None:
        # Writes arrive from the asyncio loop and from FastAPI's request threadpool
        # (a webhook), so the connection is shared across threads and guarded here.
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._lock = threading.Lock()
        self._agent = agent
        self._subscribers: list[Subscriber] = []
        self._create_tables()

    def _create_tables(self) -> None:
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT NOT NULL,
                agent TEXT NOT NULL,
                type TEXT NOT NULL,
                payload TEXT NOT NULL,
                timestamp TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_events_task ON events(task_id);
            CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp);
        """)
        self._conn.commit()

    def subscribe(self, subscriber: Subscriber) -> None:
        self._subscribers.append(subscriber)

    def append(self, task_id: str, type: str, payload: dict | None = None) -> dict:
        event = {
            "task_id": task_id,
            "agent": self._agent,
            "type": type,
            "payload": payload or {},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        with self._lock:
            self._conn.execute(
                "INSERT INTO events (task_id, agent, type, payload, timestamp) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    event["task_id"],
                    event["agent"],
                    event["type"],
                    json.dumps(event["payload"]),
                    event["timestamp"],
                ),
            )
            self._conn.commit()
        self._notify(event)
        return event

    def _notify(self, event: dict) -> None:
        for subscriber in self._subscribers:
            try:
                subscriber(event)
            except Exception:
                logger.exception("Subscriber failed for %s event", event["type"])

    def events_for(self, task_id: str) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT task_id, agent, type, payload, timestamp FROM events "
                "WHERE task_id = ? ORDER BY id",
                (task_id,),
            ).fetchall()
        return [self._row_to_event(row) for row in rows]

    def is_known(self, task_id: str) -> bool:
        with self._lock:
            row = self._conn.execute(
                "SELECT 1 FROM events WHERE task_id = ? LIMIT 1", (task_id,)
            ).fetchone()
        return row is not None

    def since(self, timestamp: str) -> list[dict]:
        """Every event newer than a timestamp, across all tasks."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT task_id, agent, type, payload, timestamp FROM events "
                "WHERE timestamp > ? ORDER BY id",
                (timestamp,),
            ).fetchall()
        return [self._row_to_event(row) for row in rows]

    def last_events(self) -> list[dict]:
        """The most recent event per task — enough to spot claims nothing followed."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT task_id, agent, type, payload, timestamp FROM events e "
                "WHERE id = (SELECT MAX(id) FROM events WHERE task_id = e.task_id)"
            ).fetchall()
        return [self._row_to_event(row) for row in rows]

    @staticmethod
    def _row_to_event(row: sqlite3.Row) -> dict:
        event = dict(row)
        event["payload"] = json.loads(event["payload"])
        return event

    def close(self) -> None:
        self._conn.close()


def log_events(event: dict) -> None:
    """Subscriber writing one JSON line per event, for the Docker Loki driver to ship."""
    logger.info(json.dumps(event))
