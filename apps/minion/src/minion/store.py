"""Append-only log of facts, backed by NATS JetStream.

The record of what happened; state is derived from it, never stored as a status. One
subject per type and task (`<stream>.<type>.<task_id>`): a task's history is
`<stream>.*.<task_id>` in stream order, one type across all tasks is
`<stream>.<type>.>` — which is what lets exactly one handler own a type — and
`<stream>.>` is every fact, for observers.

Durable consumers are the cursor. JetStream tracks each named consumer's
acknowledged position on the server, survives a restart, and redelivers anything
un-acked — there is no separate position table to maintain. An ephemeral consumer
(no name) gets no such memory: fine for something explicitly disposable (Loki), wrong
for anything that must not miss a fact it was down for (the worker).
"""

import asyncio
import json
import logging
import re
from datetime import datetime, timezone
from typing import Awaitable, Callable

import nats
from nats.js.api import ConsumerConfig, DeliverPolicy
import nats.js.errors
from nats.js.errors import NotFoundError

logger = logging.getLogger(__name__)

Handler = Callable[[dict], "Awaitable[None] | None"]

# How long a pull waits for a message before giving up — the loop just tries again,
# so this only trades idle CPU against shutdown latency.
FETCH_TIMEOUT = 2
FETCH_BATCH = 50

# A handler whose side effect failed gets the fact again after this delay, up to
# MAX_DELIVERIES times — then it is dropped and logged, so a permanently broken
# handler cannot loop forever.
RETRY_DELAY_SECONDS = 30
MAX_DELIVERIES = 5

# A type and a task id are each one subject token: no dots, no wildcards, no spaces.
# A dot would split the token and a wildcard would subscribe to more than intended.
TOKEN = re.compile(r"^[A-Za-z0-9_-]+$")


def _token(kind: str, value: str) -> str:
    if not TOKEN.match(value or ""):
        raise ValueError(f"{kind} {value!r} must be one plain subject token")
    return value


class HandlerAlreadyBound(RuntimeError):
    """A handler runs on exactly one worker; another one already has it."""

    def __init__(self, name: str) -> None:
        super().__init__(
            f"Handler {name!r} is already running on another worker — a handler "
            f"runs in one place only. Stop it there first."
        )


class EventStore:
    def __init__(self, nc, js, stream: str, agent: str) -> None:
        self._nc = nc
        self._js = js
        self._stream = stream
        self._agent = agent
        self._consumers: list[asyncio.Task] = []
        self._handlers: list = []

    @classmethod
    async def connect(
        cls, url: str, agent: str, stream: str = "MINION_EVENTS"
    ) -> "EventStore":
        nc = await nats.connect(url)
        js = nc.jetstream()
        # Idempotent: an existing stream with the same config is left alone. No
        # retention limit is set — same as the SQLite file this replaces, which also
        # grew unbounded; revisit if disk on Venus ever becomes the constraint.
        await js.add_stream(name=stream, subjects=[f"{stream.lower()}.>"])
        return cls(nc, js, stream, agent)

    def _subject(self, type: str = "*", task_id: str = ">") -> str:
        """`<stream>.<type>.<task_id>` — the type is a token so a consumer can own it."""
        return f"{self._stream.lower()}.{type}.{task_id}"

    async def append(self, task_id: str, type: str, payload: dict | None = None) -> dict:
        event = {
            "task_id": task_id,
            "agent": self._agent,
            "type": type,
            "payload": payload or {},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        subject = self._subject(_token("type", type), _token("task id", task_id))
        await self._js.publish(subject, json.dumps(event).encode())
        return event

    async def events_for(self, task_id: str) -> list[dict]:
        return await self._drain(self._subject("*", task_id), DeliverPolicy.ALL)

    async def is_known(self, task_id: str) -> bool:
        try:
            await self._js.get_last_msg(self._stream, subject=self._subject("*", task_id))
            return True
        except NotFoundError:
            return False

    async def since(self, timestamp: str) -> list[dict]:
        """Every event newer than an ISO timestamp, across all tasks."""
        cutoff = datetime.fromisoformat(timestamp)
        return await self._drain(
            f"{self._stream.lower()}.>",
            DeliverPolicy.BY_START_TIME,
            opt_start_time=cutoff.isoformat(),
        )

    async def last_events(self) -> list[dict]:
        """The most recent event per task — enough to spot claims nothing followed.

        JetStream keeps a last message per *subject*, which is per type and task; they
        arrive in stream order, so the last one seen for a task is its newest.
        """
        newest: dict[str, dict] = {}
        for event in await self._drain(
            f"{self._stream.lower()}.>", DeliverPolicy.LAST_PER_SUBJECT
        ):
            newest[event["task_id"]] = event
        return list(newest.values())

    async def _drain(
        self, subject: str, deliver_policy: DeliverPolicy, **config
    ) -> list[dict]:
        """One-shot read: an ephemeral consumer, fetched until nothing more arrives.

        Ephemeral because this is a fresh question every call, not something to
        resume later — the position has nothing to be durable for.
        """
        sub = await self._js.pull_subscribe(
            subject,
            durable=None,
            config=ConsumerConfig(deliver_policy=deliver_policy, **config),
        )
        events = []
        while True:
            try:
                msgs = await sub.fetch(FETCH_BATCH, timeout=FETCH_TIMEOUT)
            except asyncio.TimeoutError:
                break
            if not msgs:
                break
            for msg in msgs:
                events.append(json.loads(msg.data))
                await msg.ack()
        return events

    async def consume(self, name: str | None, handler: Handler) -> asyncio.Task:
        """Run `handler` for every fact ever appended, then every new one.

        `name` set: a durable consumer. JetStream remembers its position — a restart
        resumes rather than starts over, and a fact appended while this was down is
        still delivered. `name=None`: ephemeral, sees only what arrives while running;
        appropriate only for a subscriber that is allowed to miss things (Loki).
        """
        sub = await self._js.pull_subscribe(
            f"{self._stream.lower()}.>",
            durable=name,
            config=ConsumerConfig(deliver_policy=DeliverPolicy.ALL),
        )

        async def loop() -> None:
            while True:
                try:
                    msgs = await sub.fetch(FETCH_BATCH, timeout=FETCH_TIMEOUT)
                except asyncio.TimeoutError:
                    continue
                except asyncio.CancelledError:
                    return
                for msg in msgs:
                    event = json.loads(msg.data)
                    try:
                        result = handler(event)
                        if result is not None:
                            await result
                    except Exception:
                        logger.exception(
                            "Subscriber %r failed for %s event", name, event["type"]
                        )
                    await msg.ack()

        task = asyncio.create_task(loop())
        self._consumers.append(task)
        return task

    async def handle(
        self, handler: str, type: str, fn: Handler, ack_wait: float | None = None
    ):
        """Own facts of one type as `handler` — on this worker, and only here.

        One durable consumer per (handler, type): every handler of a type gets every
        fact of it, wherever it runs. A *push* consumer without a queue group accepts
        one bound subscription, so a second process binding the same handler is
        refused rather than silently splitting the work. Once the first one stops,
        the binding is free again — a restart or a move to another machine works.

        The fact is acked once `fn` returns; a handler that starts a long run must
        schedule it and return — or pass an `ack_wait` longer than the run, so a
        worker that dies mid-run gets it back after a restart. If `fn` raises,
        the fact comes back after RETRY_DELAY_SECONDS, at most MAX_DELIVERIES times.
        """
        name = f"{_token('handler', handler)}-{_token('type', type)}"
        try:
            info = await self._js.consumer_info(self._stream, name)
            if info.push_bound:
                raise HandlerAlreadyBound(name)
        except NotFoundError:
            pass

        async def deliver(msg) -> None:
            event = json.loads(msg.data)
            try:
                result = fn(event)
                if result is not None:
                    await result
            except Exception:
                attempt = msg.metadata.num_delivered
                logger.exception(
                    "Handler %r failed for %s (attempt %d of %d)",
                    name, event["task_id"], attempt, MAX_DELIVERIES,
                )
                await msg.nak(delay=RETRY_DELAY_SECONDS)
                return
            await msg.ack()

        try:
            sub = await self._js.subscribe(
                self._subject(type),
                durable=name,
                cb=deliver,
                manual_ack=True,
                config=ConsumerConfig(
                    deliver_policy=DeliverPolicy.ALL,
                    max_deliver=MAX_DELIVERIES,
                    ack_wait=ack_wait,
                ),
            )
        except nats.js.errors.Error as exc:
            if "already bound" in str(exc):
                raise HandlerAlreadyBound(name) from exc
            raise
        self._handlers.append(sub)
        return sub

    async def close(self) -> None:
        for task in self._consumers:
            task.cancel()
        # Stop deliveries first, so no handler is handed a fact on a closing connection.
        for sub in self._handlers:
            try:
                await sub.unsubscribe()
            except Exception:
                logger.debug("Unsubscribe failed during close", exc_info=True)
        await self._nc.close()


def log_events(event: dict) -> None:
    """Subscriber writing one JSON line per event, for the Docker Loki driver to ship."""
    logger.info(json.dumps(event))
